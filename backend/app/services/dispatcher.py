"""Event Dispatcher (PRD §5.1, §12.6). One event about one resident -> next action(s)."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any

from app.agent import decision, tools
from app.agent.context import current_incident
from app.config import get_settings
from app.models import ACTION_REQUIRED, Actor, CaseStatus, EventType, IncidentStatus
from app.policy import fallback
from app.services import db, worker
from app.util.logging import get_logger

log = get_logger(__name__)
MAX_FALLBACK_STEPS = 3
_locks: dict[tuple[str, str], asyncio.Lock] = defaultdict(asyncio.Lock)


async def run_decision(incident_id: str, event: dict[str, Any], case: dict[str, Any]):
    """Run the configured decision engine (§12.0 structured in P1; ADK is P2)."""
    if get_settings().DECISION_ENGINE != "structured":
        raise NotImplementedError("DECISION_ENGINE=adk is a [P2] feature")
    return await decision.run_decision(incident_id, event, case)


async def handle_event(incident_id: str, event: dict[str, Any]) -> None:
    """Handle one event. Never blocks an HTTP request (runs as a `dispatch` job)."""
    incident = await db.get_doc(db.incident_ref(incident_id))
    if not incident or incident.get("status") != IncidentStatus.ACTIVE:
        return
    if event["type"] == EventType.SCENARIO_STARTED:
        return  # cases, pump and TTL are set up by services.scenario.start_scenario
    rid = event["resident_id"]
    async with _locks[(incident_id, rid)]:
        token = current_incident.set(incident_id)
        try:
            await _decide(incident_id, rid, event)
        finally:
            current_incident.reset(token)


async def _decide(inc: str, rid: str, event: dict[str, Any]) -> None:
    s = get_settings()
    started = time.monotonic()
    case = await db.get_doc(db.case_ref(inc, rid))
    if not case:
        return
    status = CaseStatus(case["status"])

    # FR-20: MEDICAL is escalated immediately, before any LLM call.
    if status == CaseStatus.MEDICAL:
        await fallback.apply_step(inc, rid)
        return
    if status not in ACTION_REQUIRED:
        return

    model = None
    if not s.FORCE_FALLBACK:
        try:
            outcome = await asyncio.wait_for(
                run_decision(inc, event, case), timeout=s.AGENT_TIMEOUT_S
            )
            model = outcome.model if outcome else None
        except Exception as exc:  # timeout, model unavailable or engine error -> fallback
            db.STATS["decision_errors"] += 1
            log.warning(
                "decision failed",
                extra={
                    "incident_id": inc,
                    "resident_id": rid,
                    "error_code": getattr(exc, "code", type(exc).__name__),
                },
            )

    steps, fallback_used = 0, False
    while steps < MAX_FALLBACK_STEPS:
        case = await db.get_doc(db.case_ref(inc, rid))
        if not case or CaseStatus(case["status"]) not in ACTION_REQUIRED:
            break
        if not fallback_used:
            db.STATS["decisions_fallback"] += 1
        res = await fallback.apply_step(inc, rid)
        fallback_used, steps = True, steps + 1
        if not res.get("ok"):
            log.warning(
                "fallback step failed",
                extra={"incident_id": inc, "resident_id": rid, "error_code": res.get("error")},
            )
    else:
        # Safety net (SM-1): never leave a case stuck in an action-required status.
        case = await db.get_doc(db.case_ref(inc, rid))
        if case and CaseStatus(case["status"]) in ACTION_REQUIRED:
            await tools.escalate_to_human(
                rid, "HIGH", "Policy could not complete this case", actor=Actor.policy
            )
    log.info(
        "decision",
        extra={
            "incident_id": inc,
            "resident_id": rid,
            "event_type": event["type"],
            "fallback_used": fallback_used,
            "model": model,
            "latency_ms": int((time.monotonic() - started) * 1000),
        },
    )


@worker.job("dispatch")
async def dispatch_job(payload: dict[str, Any]) -> None:
    """INT-2: run the dispatcher for one event."""
    await handle_event(payload["incident_id"], payload["event"])


def emit(incident_id: str, event_type: EventType, resident_id: str, **extra: Any) -> None:
    """Queue an event for the dispatcher."""
    worker.enqueue(
        "dispatch",
        {
            "incident_id": incident_id,
            "event": {"type": event_type.value, "resident_id": resident_id, **extra},
        },
    )
