"""Volunteer task lifecycle (API-9/API-10 logic). Used by the volunteer bot in [P1] and
by the volunteer page endpoints in [P2]."""

from __future__ import annotations

from app.models import Actor, CaseStatus, EventType, TaskStatus, TaskType, Urgency
from app.policy.state_machine import transition_case
from app.services import db, volunteers, worker
from app.util.errors import InvalidTransition, NotFound
from app.util.ids import task_id
from app.util.time import utcnow

_NEXT_ALLOWED = {
    TaskStatus.ACCEPTED: {TaskStatus.PICKED_UP, TaskStatus.DONE, TaskStatus.CANNOT_LOCATE},
    TaskStatus.PICKED_UP: {TaskStatus.ARRIVED, TaskStatus.CANNOT_LOCATE},
    TaskStatus.ARRIVED: {TaskStatus.DONE},
}


async def _task(inc: str, tid: str) -> dict:
    t = await db.get_doc(db.task_ref(inc, tid))
    if not t:
        raise NotFound(f"Task {tid} not found")
    return t


def _emit(inc: str, rid: str, tid: str, status: str) -> None:
    worker.enqueue(
        "dispatch",
        {
            "incident_id": inc,
            "event": {
                "type": EventType.VOLUNTEER_UPDATE,
                "resident_id": rid,
                "task_id": tid,
                "status": status,
            },
        },
    )


async def accept_task(inc: str, tid: str, volunteer_id: str) -> dict:
    """Volunteer accepts an APPROVED task. VOLUNTEER_PENDING -> VOLUNTEER_EN_ROUTE if needed."""
    t = await _task(inc, tid)
    if t["status"] != TaskStatus.APPROVED or t["volunteer_id"] != volunteer_id:
        raise InvalidTransition(f"Task {tid} is {t['status']} for {t['volunteer_id']}")
    await db.update_doc(
        db.task_ref(inc, tid), {"status": TaskStatus.ACCEPTED.value, "updated_at": utcnow()}
    )
    case = await db.get_doc(db.case_ref(inc, t["resident_id"]))
    if case and case["status"] == CaseStatus.VOLUNTEER_PENDING:
        await transition_case(
            inc,
            t["resident_id"],
            CaseStatus.VOLUNTEER_EN_ROUTE,
            Actor.volunteer,
            f"{volunteer_id} accepted the task",
            event_type=EventType.VOLUNTEER_UPDATE,
            tool="accept_task",
            args_summary=tid,
        )
    _emit(inc, t["resident_id"], tid, TaskStatus.ACCEPTED)
    return {**t, "status": TaskStatus.ACCEPTED.value}


async def update_task_status(inc: str, tid: str, status: TaskStatus, note: str = "") -> dict:
    """Volunteer progress: PICKED_UP, ARRIVED, DONE or CANNOT_LOCATE (moves the case)."""
    t = await _task(inc, tid)
    cur = TaskStatus(t["status"])
    if status not in _NEXT_ALLOWED.get(cur, set()):
        raise InvalidTransition(f"Task {tid} cannot go from {cur} to {status}")
    if status == TaskStatus.CANNOT_LOCATE and len(note.strip()) < 3:
        raise InvalidTransition("A note is required for CANNOT_LOCATE")
    rid, vid = t["resident_id"], t["volunteer_id"]
    await db.update_doc(db.task_ref(inc, tid), {"status": status.value, "updated_at": utcnow()})
    why = note or f"{vid}: {status.value.replace('_', ' ').lower()}"

    if status == TaskStatus.ARRIVED:
        await transition_case(
            inc,
            rid,
            CaseStatus.AT_SHELTER,
            Actor.volunteer,
            why,
            event_type=EventType.VOLUNTEER_UPDATE,
            tool="task_status",
            args_summary=f"{tid} ARRIVED",
        )
    elif status == TaskStatus.DONE:
        await transition_case(
            inc,
            rid,
            CaseStatus.CONFIRMED_SAFE,
            Actor.volunteer,
            why,
            event_type=EventType.VOLUNTEER_UPDATE,
            tool="task_status",
            args_summary=f"{tid} DONE",
            patch={"confirmed_by": vid, "open_task_id": None},
        )
        await volunteers.release_volunteer(vid)
    elif status == TaskStatus.CANNOT_LOCATE:
        rid_task, now = task_id(), utcnow()
        await db.set_doc(
            db.task_ref(inc, rid_task),
            {
                "task_id": rid_task,
                "type": TaskType.HUMAN_REVIEW.value,
                "resident_id": rid,
                "volunteer_id": None,
                "shelter_id": None,
                "urgency": Urgency.CRITICAL.value,
                "status": TaskStatus.PENDING_APPROVAL.value,
                "briefing_en": f"Volunteer {vid} could not locate the resident. {note}"[:300],
                "briefing_volunteer_lang": {},
                "proposed_by": Actor.volunteer.value,
                "decided_by": None,
                "created_at": now,
                "updated_at": now,
            },
        )
        await transition_case(
            inc,
            rid,
            CaseStatus.ESCALATED,
            Actor.volunteer,
            why,
            event_type=EventType.VOLUNTEER_UPDATE,
            tool="task_status",
            args_summary=f"{tid} CANNOT_LOCATE",
            patch={"open_task_id": rid_task, "human_review": True},
        )
        await volunteers.release_volunteer(vid)
    _emit(inc, rid, tid, status)
    return {**t, "status": status.value}
