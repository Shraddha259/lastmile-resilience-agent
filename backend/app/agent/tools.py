"""Orchestrator tools (PRD §12.3).

Shared by the deterministic fallback policy (actor=policy, now) and the LLM decision
engine (actor=agent, M3). The incident comes from `current_incident` (FR-11). Every tool
returns `{"ok": True, ...}` or `{"ok": False, "error": ..., "message": ...}` and never raises.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any

from app.agent.context import current_incident
from app.config import get_settings
from app.models import Actor, CaseStatus, TaskStatus, TaskType, Urgency
from app.policy.state_machine import Guard, transition_case
from app.services import db, shelters, volunteers, worker
from app.util.errors import AppError
from app.util.ids import checkin_id, task_id
from app.util.logging import get_logger
from app.util.time import scaled, utcnow

log = get_logger(__name__)
Result = dict[str, Any]


def _err(code: str, message: str) -> Result:
    return {"ok": False, "error": code, "message": message}


def tool(fn: Callable[..., Awaitable[Result]]) -> Callable[..., Awaitable[Result]]:
    """Wrap a tool so it never raises to the caller."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs) -> Result:
        try:
            return await fn(*args, **kwargs)
        except AppError as exc:
            return _err(exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001 - tools must never raise
            log.exception("tool error", extra={"tool": fn.__name__})
            return _err("INTERNAL", f"{type(exc).__name__}")

    return wrapper


def _common(actor: Actor, model: str | None, latency_ms: int | None) -> dict[str, Any]:
    return {
        "actor": actor,
        "fallback_used": actor == Actor.policy,
        "model": model,
        "latency_ms": latency_ms,
    }


async def _load(rid: str) -> tuple[str, dict, dict, dict]:
    inc = current_incident.get()
    incident = await db.get_doc(db.incident_ref(inc))
    case = await db.get_doc(db.case_ref(inc, rid))
    resident = await db.get_doc(db.resident_ref(rid))
    if not incident or not case or not resident:
        raise AppError(f"Unknown resident {rid}")
    return inc, incident, case, resident


async def latest_classification(inc: str, case: dict) -> dict | None:
    """Return the classification from the case's latest check-in, if any."""
    ck = await db.get_doc(db.checkin_ref(inc, checkin_id(case["resident_id"], case["attempts"])))
    return (ck or {}).get("classification")


@tool
async def confirm_safe(
    resident_id: str,
    reason: str,
    *,
    actor: Actor = Actor.agent,
    model: str | None = None,
    latency_ms: int | None = None,
) -> Result:
    """SAFE_IN_PLACE -> CONFIRMED_SAFE, only with enough confidence and no review flag."""
    inc, _, case, _ = await _load(resident_id)
    cls = await latest_classification(inc, case) or {}
    guard = Guard(
        confidence=cls.get("confidence"),
        requires_review=bool(cls.get("requires_human_review") or case.get("human_review")),
    )
    await transition_case(
        inc,
        resident_id,
        CaseStatus.CONFIRMED_SAFE,
        reason=reason,
        guard=guard,
        tool="confirm_safe",
        patch={"confirmed_by": actor.value},
        **_common(actor, model, latency_ms),
    )
    return {"ok": True, "status": CaseStatus.CONFIRMED_SAFE}


@tool
async def schedule_retry(
    resident_id: str,
    reason: str,
    *,
    actor: Actor = Actor.agent,
    model: str | None = None,
    latency_ms: int | None = None,
) -> Result:
    """NO_ANSWER -> RETRY_SCHEDULED and enqueue the next check-in attempt."""
    inc, incident, case, _ = await _load(resident_id)
    attempt = case["attempts"] + 1
    delay = scaled(get_settings().RETRY_DELAY_S * case["attempts"], incident["sim_time_scale"])
    await transition_case(
        inc,
        resident_id,
        CaseStatus.RETRY_SCHEDULED,
        reason=reason,
        tool="schedule_retry",
        args_summary=f"attempt {attempt} in {delay:.0f}s",
        **_common(actor, model, latency_ms),
    )
    worker.enqueue(
        "checkin",
        {"incident_id": inc, "resident_id": resident_id, "attempt": attempt},
        delay_s=delay,
        dedupe_key=f"checkin-{inc}-{resident_id}-{attempt}",
    )
    return {"ok": True, "status": CaseStatus.RETRY_SCHEDULED, "attempt": attempt}


@tool
async def contact_next_of_kin(
    resident_id: str,
    message_en: str,
    reason: str,
    *,
    actor: Actor = Actor.agent,
    model: str | None = None,
    latency_ms: int | None = None,
) -> Result:
    """Mock next-of-kin message (§15.4); nothing is really sent. -> NEXT_OF_KIN_CONTACTED."""
    inc, _, _, resident = await _load(resident_id)
    kin = resident["next_of_kin"]
    note = f"Message sent to {kin['relation']} ({kin['phone_masked']}) — simulated: {message_en}"
    await transition_case(
        inc,
        resident_id,
        CaseStatus.NEXT_OF_KIN_CONTACTED,
        reason=reason,
        tool="contact_next_of_kin",
        args_summary=note[:300],
        **_common(actor, model, latency_ms),
    )
    return {"ok": True, "status": CaseStatus.NEXT_OF_KIN_CONTACTED}


@tool
async def find_shelters(resident_id: str, *, actor: Actor = Actor.agent, **_: Any) -> Result:
    """Read-only ranked shelter candidates (§15.2)."""
    _, _, case, resident = await _load(resident_id)
    return {"ok": True, "candidates": await shelters.find_shelters(resident, case.get("needs", []))}


@tool
async def reserve_shelter(
    resident_id: str,
    shelter_id: str,
    reason: str,
    *,
    actor: Actor = Actor.agent,
    model: str | None = None,
    latency_ms: int | None = None,
) -> Result:
    """Reserve a place transactionally, then NEEDS_EVACUATION -> SHELTER_RESERVED."""
    inc, _, case, _ = await _load(resident_id)
    if case["status"] != CaseStatus.NEEDS_EVACUATION:
        return _err("INVALID_TRANSITION", f"{resident_id} is {case['status']}")
    if not await shelters.reserve_shelter(shelter_id):
        return _err("SHELTER_FULL", f"{shelter_id} has no space")
    try:
        await transition_case(
            inc,
            resident_id,
            CaseStatus.SHELTER_RESERVED,
            reason=reason,
            tool="reserve_shelter",
            args_summary=shelter_id,
            patch={"assigned_shelter_id": shelter_id},
            **_common(actor, model, latency_ms),
        )
    except AppError:
        await shelters.release_shelter(shelter_id)
        raise
    return {"ok": True, "status": CaseStatus.SHELTER_RESERVED, "shelter_id": shelter_id}


@tool
async def dispatch_volunteer(
    resident_id: str,
    task_type: str,
    urgency: str,
    briefing_en: str,
    reason: str,
    volunteer_id: str | None = None,
    *,
    actor: Actor = Actor.agent,
    model: str | None = None,
    latency_ms: int | None = None,
) -> Result:
    """Create a volunteer task and move the case to VOLUNTEER_PENDING (or EN_ROUTE if auto)."""
    from app.sim import volunteer_bot  # local import avoids a cycle

    inc, incident, case, resident = await _load(resident_id)
    ttype, urg = TaskType(task_type), Urgency(urgency)
    if ttype == TaskType.HUMAN_REVIEW:
        return _err("VALIDATION_ERROR", "Use escalate_to_human for HUMAN_REVIEW")
    if volunteer_id:
        picks = [volunteer_id]
    else:
        picks = [
            v["volunteer_id"]
            for v in volunteers.rank_volunteers(resident, await db.list_volunteers(), limit=8)
        ]
    chosen = None
    for vid in picks:
        if await volunteers.claim_volunteer(vid):
            chosen = vid
            break
    if not chosen:
        return _err("NO_VOLUNTEER", "No volunteer available")

    auto = bool(incident.get("auto_approve_dispatch"))
    tid, now = task_id(), utcnow()
    task = {
        "task_id": tid,
        "type": ttype.value,
        "resident_id": resident_id,
        "volunteer_id": chosen,
        "shelter_id": case.get("assigned_shelter_id"),
        "urgency": urg.value,
        "status": (TaskStatus.APPROVED if auto else TaskStatus.PENDING_APPROVAL).value,
        "briefing_en": briefing_en[:300],
        "briefing_volunteer_lang": {},
        "proposed_by": actor.value,
        "decided_by": "auto" if auto else None,
        "created_at": now,
        "updated_at": now,
    }
    await db.set_doc(db.task_ref(inc, tid), task)
    to = CaseStatus.VOLUNTEER_EN_ROUTE if auto else CaseStatus.VOLUNTEER_PENDING
    try:
        await transition_case(
            inc,
            resident_id,
            to,
            reason=reason,
            tool="dispatch_volunteer",
            args_summary=f"{ttype.value} {chosen} {urg.value}",
            patch={"assigned_volunteer_id": chosen, "open_task_id": tid},
            **_common(actor, model, latency_ms),
        )
    except AppError:
        await db.update_doc(db.task_ref(inc, tid), {"status": TaskStatus.CANCELLED.value})
        await volunteers.release_volunteer(chosen)
        raise
    if auto:
        volunteer_bot.on_task_approved(inc, tid, incident["sim_time_scale"])
    return {"ok": True, "status": to, "task_id": tid, "volunteer_id": chosen}


@tool
async def escalate_to_human(
    resident_id: str,
    urgency: str,
    reason: str,
    *,
    actor: Actor = Actor.agent,
    model: str | None = None,
    latency_ms: int | None = None,
) -> Result:
    """Any non-terminal -> ESCALATED, with a HUMAN_REVIEW task for the coordinator."""
    inc, _, case, _ = await _load(resident_id)
    urg = Urgency(urgency)
    if case["status"] in (CaseStatus.ESCALATED, CaseStatus.CONFIRMED_SAFE):
        return _err("INVALID_TRANSITION", f"{resident_id} is already {case['status']}")
    tid, now = task_id(), utcnow()
    await db.set_doc(
        db.task_ref(inc, tid),
        {
            "task_id": tid,
            "type": TaskType.HUMAN_REVIEW.value,
            "resident_id": resident_id,
            "volunteer_id": None,
            "shelter_id": None,
            "urgency": urg.value,
            "status": TaskStatus.PENDING_APPROVAL.value,
            "briefing_en": reason[:300],
            "briefing_volunteer_lang": {},
            "proposed_by": actor.value,
            "decided_by": None,
            "created_at": now,
            "updated_at": now,
        },
    )
    try:
        await transition_case(
            inc,
            resident_id,
            CaseStatus.ESCALATED,
            reason=reason,
            tool="escalate_to_human",
            args_summary=urg.value,
            patch={"open_task_id": tid, "human_review": True},
            **_common(actor, model, latency_ms),
        )
    except AppError:
        await db.update_doc(db.task_ref(inc, tid), {"status": TaskStatus.CANCELLED.value})
        raise
    return {"ok": True, "status": CaseStatus.ESCALATED, "task_id": tid}


@tool
async def add_note(
    resident_id: str,
    note: str,
    *,
    actor: Actor = Actor.agent,
    model: str | None = None,
    latency_ms: int | None = None,
) -> Result:
    """Append a note to the audit log only."""
    inc = current_incident.get()
    await db.set_doc(
        db.events_col(inc).document(),
        {
            "ts": utcnow(),
            "actor": actor.value,
            "event_type": "NOTE",
            "resident_id": resident_id,
            "tool": "add_note",
            "args_summary": None,
            "result": "ok",
            "reason": note[:300],
            "model": model,
            "latency_ms": latency_ms,
            "fallback_used": actor == Actor.policy,
        },
    )
    return {"ok": True}


TOOLS: dict[str, Callable[..., Awaitable[Result]]] = {
    f.__name__: f
    for f in (
        confirm_safe,
        schedule_retry,
        contact_next_of_kin,
        find_shelters,
        reserve_shelter,
        dispatch_volunteer,
        escalate_to_human,
        add_note,
    )
}
