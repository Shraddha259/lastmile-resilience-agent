"""Job handlers INT-1, INT-3, INT-5, INT-6 (PRD §11.4). INT-2 lives in dispatcher.py.

All handlers are idempotent: each checks the current case/incident state and does nothing
if the work is already done or the incident isn't ACTIVE.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.models import (
    Actor,
    CaseStatus,
    Channel,
    CheckinState,
    EndReason,
    EventType,
    IncidentStatus,
)
from app.policy.state_machine import transition_case
from app.services import classifier, db, worker
from app.services.dispatcher import emit
from app.sim import simulator
from app.util.errors import AppError, InvalidTransition, VersionConflict
from app.util.logging import get_logger
from app.util.time import scaled, utcnow

log = get_logger(__name__)
SYS = Actor.system
PUMP_INTERVAL_S = 3
IN_FLIGHT = {CaseStatus.QUEUED, CaseStatus.CONTACTING}


async def _active(inc: str) -> dict | None:
    incident = await db.get_doc(db.incident_ref(inc))
    return incident if incident and incident.get("status") == IncidentStatus.ACTIVE else None


async def _claim_attempt(inc: str, rid: str, to: CaseStatus, case: dict, reason: str) -> bool:
    """Start an attempt exactly once: a duplicate delivery loses the version race (AC-6)."""
    try:
        await transition_case(inc, rid, to, SYS, reason, expected_version=case["version"])
        return True
    except (InvalidTransition, VersionConflict):
        return False


@worker.job("checkin")
async def checkin_job(payload: dict[str, Any]) -> None:
    """INT-1: start attempt `attempt` for one resident."""
    inc, rid, attempt = payload["incident_id"], payload["resident_id"], payload["attempt"]
    incident = await _active(inc)
    case = await db.get_doc(db.case_ref(inc, rid))
    if not incident or not case:
        return
    if case["status"] not in (CaseStatus.QUEUED, CaseStatus.RETRY_SCHEDULED):
        return
    if case.get("attempts", 0) != attempt - 1:
        return
    resident = await db.get_doc(db.resident_ref(rid))

    if resident.get("is_live_demo"):
        if not await _claim_attempt(
            inc, rid, CaseStatus.RINGING, case, f"Calling (attempt {attempt})"
        ):
            return
        await simulator.write_checkin_start(
            inc, resident, attempt, Channel.live, CheckinState.RINGING
        )
        worker.enqueue(
            "ring_timeout",
            {"incident_id": inc, "resident_id": rid, "attempt": attempt},
            delay_s=get_settings().LIVE_RING_TIMEOUT_S,
            dedupe_key=f"ring-{inc}-{rid}-{attempt}",
        )
        return

    async with worker.checkin_semaphore():
        claimed = await _claim_attempt(
            inc, rid, CaseStatus.CONTACTING, case, f"Simulated call (attempt {attempt})"
        )
        if not claimed:
            return
        await simulator.write_checkin_start(
            inc, resident, attempt, Channel.simulated, CheckinState.IN_PROGRESS
        )
        result = await simulator.run_simulated_call(
            inc, resident, attempt, incident["sim_time_scale"]
        )
    if result.stopped:
        await simulator.write_checkin_end(
            inc,
            rid,
            attempt,
            CheckinState.FAILED,
            EndReason.kill_switch,
            transcript=result.transcript,
        )
        return
    await complete_checkin(
        inc,
        rid,
        attempt,
        result.transcript,
        result.live_status,
        result.fake_classification,
        answered=result.answered,
    )


async def complete_checkin(
    inc: str,
    rid: str,
    attempt: int,
    transcript: list[dict[str, Any]],
    live_status: CaseStatus | None,
    fake_classification: dict[str, Any] | None,
    answered: bool = True,
    end_reason: EndReason = EndReason.agent_end_call,
) -> None:
    """Post-call pipeline (§11.3, §14.3): classify, apply final status, emit the event."""
    if not answered or not classifier.has_resident_speech(transcript):
        await simulator.write_checkin_end(
            inc, rid, attempt, CheckinState.NO_ANSWER, EndReason.ring_timeout, transcript=transcript
        )
        await transition_case(inc, rid, CaseStatus.NO_ANSWER, SYS, "No answer")
        emit(inc, EventType.CHECKIN_COMPLETED, rid, state="NO_ANSWER")
        return
    cls, model = await classifier.classify(transcript, live_status, cached=fake_classification)
    final, review = classifier.final_status(cls, live_status, resident_spoke=True)
    cls_doc = cls.model_dump(mode="json") | {"requires_human_review": review}
    await simulator.write_checkin_end(
        inc,
        rid,
        attempt,
        CheckinState.COMPLETED,
        end_reason,
        transcript=transcript,
        classification=cls_doc,
        live_status=live_status.value if live_status else None,
    )
    await transition_case(
        inc,
        rid,
        final,
        SYS,
        f"Check-in classified {final.value}",
        patch={
            "needs": [n.value for n in cls.needs],
            "last_summary_en": cls.summary_en,
            "human_review": review,
        },
        tool="classifier",
        args_summary=f"confidence {cls.confidence:.2f}",
        model=model,
    )
    emit(inc, EventType.CHECKIN_COMPLETED, rid, state="COMPLETED")


@worker.job("ring_timeout")
async def ring_timeout_job(payload: dict[str, Any]) -> None:
    """INT-3: a live resident didn't answer in time -> NO_ANSWER."""
    inc, rid, attempt = payload["incident_id"], payload["resident_id"], payload["attempt"]
    if not await _active(inc):
        return
    case = await db.get_doc(db.case_ref(inc, rid))
    if not case or case["status"] != CaseStatus.RINGING or case.get("attempts") != attempt:
        return
    await simulator.write_checkin_end(
        inc, rid, attempt, CheckinState.NO_ANSWER, EndReason.ring_timeout
    )
    await transition_case(inc, rid, CaseStatus.NO_ANSWER, SYS, "Ring timeout")
    emit(inc, EventType.CHECKIN_COMPLETED, rid, state="NO_ANSWER")


@worker.job("pump")
async def pump_job(payload: dict[str, Any]) -> None:
    """INT-5 (FR-10): move PENDING cases to QUEUED in priority order, within the limit."""
    inc = payload["incident_id"]
    incident = await _active(inc)
    if not incident:
        return
    cases = await db.list_cases(inc)
    in_flight = sum(1 for c in cases if c["status"] in IN_FLIGHT)
    pending = sorted(
        (c for c in cases if c["status"] == CaseStatus.PENDING), key=lambda c: c.get("rank", 0)
    )
    slots = get_settings().MAX_CONCURRENT_CHECKINS - in_flight
    for c in pending[: max(0, slots)]:
        try:
            await transition_case(
                inc,
                c["resident_id"],
                CaseStatus.QUEUED,
                SYS,
                "Check-in queued",
                expected_version=c["version"],
            )
        except AppError:
            continue
        worker.enqueue(
            "checkin",
            {"incident_id": inc, "resident_id": c["resident_id"], "attempt": 1},
            dedupe_key=f"checkin-{inc}-{c['resident_id']}-1",
        )
    if len(pending) > max(0, slots):
        tick = payload.get("tick", 0) + 1
        worker.enqueue(
            "pump",
            {"incident_id": inc, "tick": tick},
            delay_s=max(0.3, scaled(PUMP_INTERVAL_S, incident["sim_time_scale"])),
            dedupe_key=f"pump-{inc}-{tick}",
        )


@worker.job("ttl")
async def ttl_job(payload: dict[str, Any]) -> None:
    """INT-6: at `ends_at`, stop the incident and mark it COMPLETED."""
    from app.services.scenario import stop_incident

    inc = payload["incident_id"]
    incident = await _active(inc)
    if not incident:
        return
    remaining = (incident["ends_at"] - utcnow()).total_seconds()
    if remaining > 1:
        worker.enqueue("ttl", payload, delay_s=remaining)
        return
    await stop_incident(inc, "TTL reached", final_status=IncidentStatus.COMPLETED)


@worker.job("recover_contacting")
async def recover_contacting_job(payload: dict[str, Any]) -> None:
    """Startup recovery: a check-in that was cut off by a restart counts as no answer."""
    inc, rid, attempt = payload["incident_id"], payload["resident_id"], payload["attempt"]
    if not await _active(inc):
        return
    case = await db.get_doc(db.case_ref(inc, rid))
    if not case or case["status"] != CaseStatus.CONTACTING or case.get("attempts") != attempt:
        return
    await simulator.write_checkin_end(inc, rid, attempt, CheckinState.FAILED, EndReason.error)
    await transition_case(inc, rid, CaseStatus.NO_ANSWER, SYS, "Call interrupted by restart")
    emit(inc, EventType.CHECKIN_COMPLETED, rid, state="FAILED")
