"""[P1] Simulated volunteers (PRD §15.7, FR-23): bots move approved tasks along so cases
never stall. They call the same service functions as the API and act as actor V."""

from __future__ import annotations

from app.config import get_settings
from app.models import IncidentStatus, TaskStatus, TaskType
from app.services import db, tasks_service, worker
from app.util.time import scaled

ACCEPT_S, PICKUP_S, FINISH_S, HANDOVER_S = 20, 20, 20, 5
_AFTER = {
    TaskStatus.APPROVED: "ACCEPTED",
    TaskStatus.ACCEPTED: "PICKED_UP",
    TaskStatus.PICKED_UP: "ARRIVED",
}


def on_task_approved(inc: str, tid: str, scale: float) -> None:
    """Start the bot for a newly approved task (no-op if SIM_VOLUNTEERS is off)."""
    if get_settings().SIM_VOLUNTEERS:
        worker.enqueue(
            "volunteer_bot",
            {"incident_id": inc, "task_id": tid},
            delay_s=scaled(ACCEPT_S, scale),
            dedupe_key=f"bot-{inc}-{tid}-APPROVED",
        )


@worker.job("volunteer_bot")
async def volunteer_bot_step(payload: dict) -> None:
    """Advance one task by one step, then schedule the next step. Idempotent."""
    inc, tid = payload["incident_id"], payload["task_id"]
    incident = await db.get_doc(db.incident_ref(inc))
    task = await db.get_doc(db.task_ref(inc, tid))
    if not incident or not task or incident["status"] != IncidentStatus.ACTIVE:
        return
    scale = incident["sim_time_scale"]
    cur, ttype = TaskStatus(task["status"]), TaskType(task["type"])

    if cur == TaskStatus.APPROVED:
        await tasks_service.accept_task(inc, tid, task["volunteer_id"])
        nxt_delay = PICKUP_S if ttype == TaskType.ESCORT_TO_SHELTER else PICKUP_S + FINISH_S
    elif cur == TaskStatus.ACCEPTED and ttype == TaskType.ESCORT_TO_SHELTER:
        await tasks_service.update_task_status(inc, tid, TaskStatus.PICKED_UP)
        nxt_delay = FINISH_S
    elif cur == TaskStatus.ACCEPTED:
        resident = await db.get_doc(db.resident_ref(task["resident_id"])) or {}
        outcome = (resident.get("persona") or {}).get("volunteer_outcome")
        if outcome == TaskStatus.CANNOT_LOCATE:
            await tasks_service.update_task_status(
                inc, tid, TaskStatus.CANNOT_LOCATE, "No answer at the door; neighbours unsure"
            )
        else:
            await tasks_service.update_task_status(inc, tid, TaskStatus.DONE, "Person is safe")
        return
    elif cur == TaskStatus.PICKED_UP:
        await tasks_service.update_task_status(inc, tid, TaskStatus.ARRIVED)
        nxt_delay = HANDOVER_S
    elif cur == TaskStatus.ARRIVED:
        await tasks_service.update_task_status(inc, tid, TaskStatus.DONE, "Handed over at shelter")
        return
    else:
        return
    after = _AFTER[cur]
    worker.enqueue(
        "volunteer_bot",
        payload,
        delay_s=scaled(nxt_delay, scale),
        dedupe_key=f"bot-{inc}-{tid}-{after}",
    )
