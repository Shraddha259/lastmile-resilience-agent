"""Case state machine (PRD §9.4) and the single writer `transition_case()` (§9.3, FR-1/FR-2).

No other code may write `cases/*.status`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google.cloud import firestore

from app.config import get_settings
from app.models import TERMINAL_STATUSES, Actor, Case, CaseStatus, IncidentStatus
from app.services import db
from app.util.errors import IncidentNotActive, InvalidTransition, NotFound, VersionConflict
from app.util.logging import get_logger
from app.util.time import utcnow

log = get_logger(__name__)

S = CaseStatus
A, P, V, C, SYS = Actor.agent, Actor.policy, Actor.volunteer, Actor.coordinator, Actor.system


def _rows() -> dict[tuple[CaseStatus, CaseStatus], frozenset[Actor]]:
    t: dict[tuple[CaseStatus, CaseStatus], set[Actor]] = {}

    def add(frm, to, *actors):
        for f in frm if isinstance(frm, tuple) else (frm,):
            for d in to if isinstance(to, tuple) else (to,):
                t.setdefault((f, d), set()).update(actors)

    add(S.PENDING, S.QUEUED, SYS)
    add((S.QUEUED, S.RETRY_SCHEDULED), S.RINGING, SYS)
    add((S.QUEUED, S.RETRY_SCHEDULED, S.RINGING), S.CONTACTING, SYS)
    add(S.RINGING, S.NO_ANSWER, SYS)
    add(
        S.CONTACTING,
        (S.SAFE_IN_PLACE, S.NEEDS_EVACUATION, S.NEEDS_HELP, S.MEDICAL, S.NO_ANSWER),
        SYS,
    )
    add(S.SAFE_IN_PLACE, (S.CONFIRMED_SAFE, S.ESCALATED), A, P)
    add(S.NO_ANSWER, (S.RETRY_SCHEDULED, S.NEXT_OF_KIN_CONTACTED), A, P)
    add(S.NEXT_OF_KIN_CONTACTED, (S.VOLUNTEER_PENDING, S.VOLUNTEER_EN_ROUTE), A, P)
    add(S.NEEDS_EVACUATION, S.SHELTER_RESERVED, A, P)
    add((S.SHELTER_RESERVED, S.NEEDS_HELP), (S.VOLUNTEER_PENDING, S.VOLUNTEER_EN_ROUTE), A, P)
    add(S.VOLUNTEER_PENDING, S.VOLUNTEER_EN_ROUTE, C, V)
    add(S.VOLUNTEER_PENDING, S.ESCALATED, C)
    add(S.MEDICAL, S.ESCALATED, A, P)
    add(S.VOLUNTEER_EN_ROUTE, (S.AT_SHELTER, S.CONFIRMED_SAFE, S.ESCALATED), V)
    add(S.AT_SHELTER, S.CONFIRMED_SAFE, V, C)
    add(S.ESCALATED, S.CONFIRMED_SAFE, C)
    # "Any non-terminal -> ESCALATED / CONFIRMED_SAFE" coordinator overrides.
    for f in CaseStatus:
        if f not in TERMINAL_STATUSES:
            add(f, (S.ESCALATED, S.CONFIRMED_SAFE), C)
    # Escalation is allowed from any non-terminal status via escalate_to_human (§12.3).
    for f in CaseStatus:
        if f not in TERMINAL_STATUSES and f not in (S.PENDING, S.QUEUED, S.RINGING, S.CONTACTING):
            add(f, S.ESCALATED, A, P)
    return {k: frozenset(v) for k, v in t.items()}


TRANSITIONS: dict[tuple[CaseStatus, CaseStatus], frozenset[Actor]] = _rows()

PATCH_WHITELIST = frozenset(
    {
        "needs",
        "assigned_shelter_id",
        "assigned_volunteer_id",
        "open_task_id",
        "human_review",
        "last_summary_en",
        "attempts",
        "confirmed_by",
        "channel",
    }
)

# Entering a contact attempt counts as one attempt (docs/DECISIONS.md D-005).
_ATTEMPT_STARTS = {
    (S.QUEUED, S.RINGING),
    (S.RETRY_SCHEDULED, S.RINGING),
    (S.QUEUED, S.CONTACTING),
    (S.RETRY_SCHEDULED, S.CONTACTING),
}


@dataclass
class Guard:
    """Facts needed by conditional transitions (PRD §9.4 'Only if' column)."""

    confidence: float | None = None
    requires_review: bool | None = None


def is_allowed(frm: CaseStatus, to: CaseStatus, actor: Actor) -> bool:
    """Return True if the (from, to, actor) triple is in the transitions table."""
    return actor in TRANSITIONS.get((frm, to), frozenset())


def check_guard(
    frm: CaseStatus,
    to: CaseStatus,
    actor: Actor,
    case: dict[str, Any],
    incident: dict[str, Any],
    guard: Guard | None,
    reason: str,
) -> str | None:
    """Return an error message if a conditional rule blocks the transition, else None."""
    s = get_settings()
    if actor in (A, P) and frm == S.SAFE_IN_PLACE and to == S.CONFIRMED_SAFE:
        if guard is None or guard.confidence is None:
            return "confirm_safe needs the classification confidence"
        if guard.confidence < s.SAFE_CONFIDENCE_MIN or guard.requires_review:
            return "Confidence below minimum or human review required"
    if frm == S.NO_ANSWER and to == S.RETRY_SCHEDULED and case.get("attempts", 0) >= s.MAX_ATTEMPTS:
        return "No attempts left"
    if (
        frm == S.NO_ANSWER
        and to == S.NEXT_OF_KIN_CONTACTED
        and case.get("attempts", 0) < s.MAX_ATTEMPTS
    ):
        return "Attempts remaining; schedule a retry first"
    if actor in (A, P) and to == S.VOLUNTEER_EN_ROUTE and not incident.get("auto_approve_dispatch"):
        return "Auto-approve is off; dispatch must wait for coordinator approval"
    if actor == C and to == S.CONFIRMED_SAFE and len(reason.strip()) < 5:
        return "A coordinator note (min 5 chars) is required"
    return None


def _group(status: CaseStatus) -> str:
    if status == S.CONFIRMED_SAFE:
        return "confirmed_safe"
    if status == S.ESCALATED:
        return "escalated"
    return "in_progress"


async def transition_case(
    incident_id: str,
    resident_id: str,
    to_status: CaseStatus,
    actor: Actor,
    reason: str,
    patch: dict[str, Any] | None = None,
    expected_version: int | None = None,
    guard: Guard | None = None,
    event_type: str = "STATUS_CHANGE",
    tool: str | None = None,
    args_summary: str | None = None,
    fallback_used: bool = False,
    model: str | None = None,
    latency_ms: int | None = None,
) -> Case:
    """Atomically move a case to `to_status` (PRD §9.3).

    Runs in a Firestore transaction on the case: validates (from, to, actor) and guards,
    checks `expected_version`, applies whitelisted `patch` fields, bumps `version`, and in
    the same commit increments incident counters and appends an `agent_events` entry.

    Raises InvalidTransition, VersionConflict, IncidentNotActive or NotFound.
    """
    to_status = CaseStatus(to_status)
    patch = dict(patch or {})
    bad = set(patch) - PATCH_WHITELIST
    if bad:
        raise InvalidTransition(f"Patch fields not allowed: {sorted(bad)}")

    inc_ref = db.incident_ref(incident_id)
    c_ref = db.case_ref(incident_id, resident_id)
    ev_ref = db.events_col(incident_id).document()
    transaction = db.transaction()
    # The incident doc is read outside the transaction: every case transition would
    # otherwise lock it (hot document). Counters use blind Increment writes instead.
    inc = await db.get_doc(inc_ref)
    if not inc:
        raise NotFound(f"Incident {incident_id} not found")

    @firestore.async_transactional
    async def _run(tx) -> dict[str, Any]:
        case_snap = await c_ref.get(transaction=tx)
        if not case_snap.exists:
            raise NotFound(f"Case {resident_id} not found in {incident_id}")
        case = case_snap.to_dict()
        frm = CaseStatus(case["status"])

        if inc.get("status") != IncidentStatus.ACTIVE and actor not in (C, SYS):
            raise IncidentNotActive(f"Incident {incident_id} is {inc.get('status')}")
        if expected_version is not None and case.get("version") != expected_version:
            raise VersionConflict(
                f"{resident_id} is at version {case.get('version')}, expected {expected_version}"
            )
        if not is_allowed(frm, to_status, actor):
            raise InvalidTransition(
                f"Cannot move {resident_id} from {frm} to {to_status} as {actor}",
                {"from": frm, "to": to_status, "actor": actor},
            )
        blocked = check_guard(frm, to_status, actor, case, inc, guard, reason)
        if blocked:
            raise InvalidTransition(
                f"Cannot move {resident_id} from {frm} to {to_status}: {blocked}",
                {"from": frm, "to": to_status, "actor": actor},
            )

        now = utcnow()
        update = {
            **patch,
            "status": to_status.value,
            "version": case.get("version", 0) + 1,
            "updated_at": now,
        }
        if (frm, to_status) in _ATTEMPT_STARTS and "attempts" not in patch:
            update["attempts"] = case.get("attempts", 0) + 1
        tx.update(c_ref, update)

        g_from, g_to = _group(frm), _group(to_status)
        if g_from != g_to:
            tx.update(
                inc_ref,
                {
                    f"counters.{g_from}": firestore.Increment(-1),
                    f"counters.{g_to}": firestore.Increment(1),
                },
            )
        tx.set(
            ev_ref,
            {
                "ts": now,
                "actor": actor.value,
                "event_type": event_type,
                "resident_id": resident_id,
                "tool": tool,
                "args_summary": args_summary,
                "result": "ok",
                "reason": reason[:300],
                "model": model,
                "latency_ms": latency_ms,
                "fallback_used": fallback_used,
                "status_from": frm.value,
                "status_to": to_status.value,
            },
        )
        db.count_writes(3 if g_from != g_to else 2)
        return {**case, **update}

    result = await _run(transaction)
    log.info(
        "transition",
        extra={
            "incident_id": incident_id,
            "resident_id": resident_id,
            "actor": actor.value,
            "status_to": to_status.value,
            "tool": tool,
            "fallback_used": fallback_used,
        },
    )
    return Case.model_validate(result)
