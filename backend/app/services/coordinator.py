"""Coordinator actions (PRD §11.2 API-5/API-6, US-3/US-4): the human in the loop.

- decide_task: approve or reject a volunteer dispatch the agent/policy proposed.
- override_case: mark a case confirmed safe or escalated, with a mandatory note.
Every action is actor=coordinator and lands in the audit log via transition_case.
"""

from __future__ import annotations

from typing import Any

from app.models import (
    OPEN_TASK_STATUSES,
    TERMINAL_STATUSES,
    Actor,
    CaseStatus,
    EventType,
    TaskStatus,
    TaskType,
    Urgency,
)
from app.policy.state_machine import transition_case
from app.services import db, volunteers
from app.services.dispatcher import emit
from app.util.errors import InvalidTransition, NotFound, ValidationFailed
from app.util.ids import task_id
from app.util.time import utcnow

C = Actor.coordinator
NOTE_MIN = 5


def _note(note: str | None, required: bool) -> str:
    note = (note or "").strip()
    if required and len(note) < NOTE_MIN:
        raise ValidationFailed(f"A note of at least {NOTE_MIN} characters is required")
    return note[:300]


async def create_review_task(
    inc: str, rid: str, urgency: Urgency, briefing: str, proposed_by: Actor
) -> str:
    """Create a HUMAN_REVIEW task for the coordinator queue. Returns its ID."""
    tid, now = task_id(), utcnow()
    await db.set_doc(
        db.task_ref(inc, tid),
        {
            "task_id": tid,
            "type": TaskType.HUMAN_REVIEW.value,
            "resident_id": rid,
            "volunteer_id": None,
            "shelter_id": None,
            "urgency": urgency.value,
            "status": TaskStatus.PENDING_APPROVAL.value,
            "briefing_en": briefing[:300],
            "briefing_volunteer_lang": {},
            "proposed_by": proposed_by.value,
            "decided_by": None,
            "created_at": now,
            "updated_at": now,
        },
    )
    return tid


async def decide_task(inc: str, tid: str, decision: str, note: str | None) -> dict[str, Any]:
    """API-5: APPROVE starts the volunteer; REJECT frees them and hands the case to a human."""
    from app.sim import volunteer_bot  # local import avoids a cycle

    task = await db.get_doc(db.task_ref(inc, tid))
    incident = await db.get_doc(db.incident_ref(inc))
    if not task or not incident:
        raise NotFound(f"Task {tid} not found")
    if task["type"] == TaskType.HUMAN_REVIEW:
        raise InvalidTransition("Resolve human-review tasks with a case override")
    if task["status"] != TaskStatus.PENDING_APPROVAL:
        raise InvalidTransition(f"Task {tid} is already {task['status']}")
    rid, now = task["resident_id"], utcnow()

    if decision == "APPROVE":
        text = _note(note, required=False)
        await db.update_doc(
            db.task_ref(inc, tid),
            {
                "status": TaskStatus.APPROVED.value,
                "decided_by": C.value,
                "decision_note": text,
                "updated_at": now,
            },
        )
        await db.set_doc(
            db.events_col(inc).document(),
            {
                "ts": now,
                "actor": C.value,
                "event_type": EventType.TASK_DECIDED.value,
                "resident_id": rid,
                "tool": "approve_task",
                "args_summary": tid,
                "result": "ok",
                "reason": text or "Dispatch approved",
                "model": None,
                "latency_ms": None,
                "fallback_used": False,
            },
        )
        volunteer_bot.on_task_approved(inc, tid, incident["sim_time_scale"])
    elif decision == "REJECT":
        text = _note(note, required=True)
        await db.update_doc(
            db.task_ref(inc, tid),
            {
                "status": TaskStatus.REJECTED.value,
                "decided_by": C.value,
                "decision_note": text,
                "updated_at": now,
            },
        )
        if task.get("volunteer_id"):
            await volunteers.release_volunteer(task["volunteer_id"])
        case = await db.get_doc(db.case_ref(inc, rid))
        if case and case["status"] == CaseStatus.VOLUNTEER_PENDING:
            review = await create_review_task(
                inc, rid, Urgency.HIGH, f"Dispatch {tid} rejected: {text}", C
            )
            await transition_case(
                inc,
                rid,
                CaseStatus.ESCALATED,
                C,
                f"Dispatch rejected: {text}",
                event_type=EventType.TASK_DECIDED,
                tool="reject_task",
                args_summary=tid,
                patch={"open_task_id": review, "human_review": True},
            )
    else:
        raise ValidationFailed("decision must be APPROVE or REJECT")
    emit(inc, EventType.TASK_DECIDED, rid, task_id=tid, decision=decision)
    return {
        **task,
        "status": TaskStatus.APPROVED.value if decision == "APPROVE" else TaskStatus.REJECTED.value,
    }


async def override_case(inc: str, rid: str, to_status: str, note: str) -> dict[str, Any]:
    """API-6: coordinator sets CONFIRMED_SAFE or ESCALATED (note >= 5 chars, US-4)."""
    text = _note(note, required=True)
    target = CaseStatus(to_status)
    if target not in TERMINAL_STATUSES:
        raise ValidationFailed("to_status must be CONFIRMED_SAFE or ESCALATED")
    case = await db.get_doc(db.case_ref(inc, rid))
    if not case:
        raise NotFound(f"Case {rid} not found")

    patch: dict[str, Any] = {"human_review": target == CaseStatus.ESCALATED}
    if target == CaseStatus.CONFIRMED_SAFE:
        patch["confirmed_by"] = C.value
    # Close whatever task is open for this case: the coordinator now owns it.
    open_tid = case.get("open_task_id")
    task = await db.get_doc(db.task_ref(inc, open_tid)) if open_tid else None
    if task and TaskStatus(task["status"]) in OPEN_TASK_STATUSES:
        done = task["type"] == TaskType.HUMAN_REVIEW
        await db.update_doc(
            db.task_ref(inc, open_tid),
            {
                "status": (TaskStatus.DONE if done else TaskStatus.CANCELLED).value,
                "decided_by": C.value,
                "decision_note": text,
                "updated_at": utcnow(),
            },
        )
        if task.get("volunteer_id"):
            await volunteers.release_volunteer(task["volunteer_id"])
        patch["open_task_id"] = None
    if target == CaseStatus.ESCALATED:  # keep the case visible in the review queue
        patch["open_task_id"] = await create_review_task(
            inc, rid, Urgency.HIGH, f"Escalated by coordinator: {text}", C
        )

    result = await transition_case(
        inc,
        rid,
        target,
        C,
        text,
        event_type=EventType.COORDINATOR_OVERRIDE,
        tool="override",
        args_summary=target.value,
        patch=patch,
    )
    emit(inc, EventType.COORDINATOR_OVERRIDE, rid)
    return result.model_dump(mode="json")
