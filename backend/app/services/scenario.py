"""Incident lifecycle: start (API-2), stop / kill switch (API-3, FR-30), reset (API-4)
and startup recovery (FR-19)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from google.cloud.firestore_v1.base_query import FieldFilter

from app.config import get_settings
from app.models import (
    TERMINAL_STATUSES,
    Actor,
    CaseStatus,
    Channel,
    EventType,
    IncidentStatus,
    ScenarioRequest,
)
from app.services import db, risk, worker
from app.services.dispatcher import emit
from app.util.errors import ActiveIncidentExists, NotFound
from app.util.ids import incident_id as new_incident_id
from app.util.logging import get_logger
from app.util.time import utcnow

log = get_logger(__name__)
SUBCOLLECTIONS = ("cases", "checkins", "tasks", "agent_events", "sitreps")

# Callbacks run on stop (live voice bridges register here in M4 to close within 2 s).
_stop_hooks: list[Callable[[str], Awaitable[None]]] = []


def on_stop(hook: Callable[[str], Awaitable[None]]) -> None:
    """Register a coroutine called with the incident ID when it stops."""
    _stop_hooks.append(hook)


async def active_incidents() -> list[dict[str, Any]]:
    q = (
        db.get_db()
        .collection("incidents")
        .where(filter=FieldFilter("status", "==", IncidentStatus.ACTIVE.value))
    )
    return await db.list_docs(q)


async def _audit(inc: str, event_type: str, reason: str, actor: Actor = Actor.system) -> None:
    await db.set_doc(
        db.events_col(inc).document(),
        {
            "ts": utcnow(),
            "actor": actor.value,
            "event_type": event_type,
            "resident_id": None,
            "tool": None,
            "args_summary": None,
            "result": "ok",
            "reason": reason,
            "model": None,
            "latency_ms": None,
            "fallback_used": False,
        },
    )


async def start_scenario(req: ScenarioRequest) -> str:
    """Create an incident and its ranked cases, then start the pump and the TTL job."""
    s = get_settings()
    if len(await active_incidents()) >= s.MAX_ACTIVE_INCIDENTS:
        raise ActiveIncidentExists("An incident is already active")
    template = await db.get_doc(db.get_db().collection("scenarios").document(req.scenario_id))
    if not template:
        raise NotFound(f"Scenario {req.scenario_id} not found (run the seed loader)")
    residents = {r["resident_id"]: r for r in await db.list_residents()}
    ranked = risk.rank_residents(
        list(residents.values()), template["polygon"], template["river_line"]
    )

    inc, now = new_incident_id(), utcnow()
    scale = req.sim_time_scale or s.SIM_TIME_SCALE
    auto = (
        s.AUTO_APPROVE_DISPATCH if req.auto_approve_dispatch is None else req.auto_approve_dispatch
    )
    incident = {
        "incident_id": inc,
        "scenario_id": req.scenario_id,
        "type": template["type"],
        "severity": template["severity"],
        "title": template["title"],
        "polygon": template["polygon"],
        "river_line": template["river_line"],
        "official_text": template["official_text"],
        "official_facts": template["official_facts"],
        "status": IncidentStatus.ACTIVE.value,
        "auto_approve_dispatch": auto,
        "sim_time_scale": scale,
        "created_at": now,
        "ends_at": now + timedelta(minutes=s.INCIDENT_TTL_MIN),
        "counters": {
            "total": len(ranked),
            "confirmed_safe": 0,
            "escalated": 0,
            "in_progress": len(ranked),
        },
    }
    await db.set_doc(db.incident_ref(inc), incident)
    cases = []
    for rank, rr in enumerate(ranked):
        res = residents[rr.resident_id]
        cases.append(
            (
                db.case_ref(inc, rr.resident_id),
                {
                    "resident_id": rr.resident_id,
                    "status": CaseStatus.PENDING.value,
                    "version": 0,
                    "risk_score": rr.risk_score,
                    "priority": rr.priority.value,
                    "risk_reasons": rr.risk_reasons,
                    "attempts": 0,
                    "channel": (
                        Channel.live if res.get("is_live_demo") else Channel.simulated
                    ).value,
                    "needs": rr.extra_needs,
                    "assigned_shelter_id": None,
                    "assigned_volunteer_id": None,
                    "open_task_id": None,
                    "human_review": False,
                    "last_summary_en": None,
                    "confirmed_by": None,
                    "age": rr.age,
                    "rank": rank,
                    "updated_at": now,
                },
            )
        )
    await db.batch_write(cases)
    await _audit(
        inc,
        EventType.SCENARIO_STARTED.value,
        f"{len(ranked)} residents at risk; auto-approve {'on' if auto else 'off'}",
    )
    _start_jobs(inc, incident)
    log.info("scenario started", extra={"incident_id": inc})
    return inc


def _start_jobs(inc: str, incident: dict[str, Any]) -> None:
    worker.enqueue("pump", {"incident_id": inc, "tick": 0}, dedupe_key=f"pump-{inc}-0")
    remaining = max(0.0, (incident["ends_at"] - utcnow()).total_seconds())
    worker.enqueue("ttl", {"incident_id": inc}, delay_s=remaining)


async def stop_incident(
    inc: str, reason: str, final_status: IncidentStatus = IncidentStatus.STOPPED
) -> dict:
    """Kill switch (FR-30): mark the incident stopped, cancel its jobs, close live calls."""
    incident = await db.get_doc(db.incident_ref(inc))
    if not incident:
        raise NotFound(f"Incident {inc} not found")
    if incident["status"] == IncidentStatus.ACTIVE:
        await db.update_doc(
            db.incident_ref(inc), {"status": final_status.value, "stopped_at": utcnow()}
        )
        await _audit(
            inc,
            "INCIDENT_STOPPED",
            reason,
            Actor.coordinator if final_status == IncidentStatus.STOPPED else Actor.system,
        )
    for hook in _stop_hooks:
        await hook(inc)
    worker.cancel_incident(inc)
    return {
        "status": final_status.value
        if incident["status"] == IncidentStatus.ACTIVE
        else incident["status"]
    }


async def reset_incident(inc: str) -> None:
    """Stop if active, delete the incident and its data, restore shelters and volunteers."""
    if await db.get_doc(db.incident_ref(inc)):
        await stop_incident(inc, "reset")
    for sub in SUBCOLLECTIONS:
        await db.delete_collection(db.incident_ref(inc).collection(sub))
    await db.incident_ref(inc).delete()
    await reset_resources()


async def reset_resources() -> None:
    """Set every shelter's `occupied` to 0 and every volunteer `available`."""
    items = [
        (db.shelter_ref(s["shelter_id"]), {**s, "occupied": 0}) for s in await db.list_shelters()
    ]
    items += [
        (db.volunteer_ref(v["volunteer_id"]), {**v, "available": True})
        for v in await db.list_volunteers()
    ]
    await db.batch_write(items)


async def recover_on_startup(stale_after_s: float = 30) -> int:
    """FR-19: re-enqueue work for ACTIVE incidents after an instance restart."""
    from app.services import jobs  # noqa: F401 - registers job handlers
    from app.sim import volunteer_bot  # noqa: F401 - registers the bot job

    n = 0
    for incident in await active_incidents():
        inc = incident["incident_id"]
        _start_jobs(inc, incident)
        now = utcnow()
        for c in await db.list_cases(inc):
            st = CaseStatus(c["status"])
            if st in TERMINAL_STATUSES or st == CaseStatus.PENDING:
                continue
            if (now - c["updated_at"]).total_seconds() < stale_after_s:
                continue
            rid, n = c["resident_id"], n + 1
            payload = {"incident_id": inc, "resident_id": rid}
            if st in (CaseStatus.QUEUED, CaseStatus.RETRY_SCHEDULED):
                worker.enqueue("checkin", {**payload, "attempt": c["attempts"] + 1})
            elif st == CaseStatus.RINGING:
                worker.enqueue("ring_timeout", {**payload, "attempt": c["attempts"]})
            elif st == CaseStatus.CONTACTING:
                worker.enqueue("recover_contacting", {**payload, "attempt": c["attempts"]})
            elif c.get("open_task_id") and st in (
                CaseStatus.VOLUNTEER_PENDING,
                CaseStatus.VOLUNTEER_EN_ROUTE,
                CaseStatus.AT_SHELTER,
            ):
                if incident.get("auto_approve_dispatch") or st != CaseStatus.VOLUNTEER_PENDING:
                    worker.enqueue(
                        "volunteer_bot", {"incident_id": inc, "task_id": c["open_task_id"]}
                    )
            else:
                emit(inc, EventType.TIMER_FIRED, rid)
        log.info("recovered incident", extra={"incident_id": inc})
    return n
