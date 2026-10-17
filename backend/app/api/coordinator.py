"""Coordinator commands (PRD §11.2): API-5 task decision, API-6 override, API-7 SITREP."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.services import coordinator, sitrep
from app.util.auth import require_passcode

router = APIRouter(
    prefix="/api/incidents", tags=["coordinator"], dependencies=[Depends(require_passcode)]
)


class TaskDecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    note: str = Field(default="", max_length=300)


class Override(BaseModel):
    to_status: Literal["CONFIRMED_SAFE", "ESCALATED"]
    note: str = Field(min_length=5, max_length=300)


@router.post("/{incident_id}/tasks/{task_id}/decision")
async def decide(incident_id: str, task_id: str, body: TaskDecision) -> dict:
    """API-5: approve or reject a proposed volunteer dispatch (reject needs a note)."""
    return await coordinator.decide_task(incident_id, task_id, body.decision, body.note)


@router.post("/{incident_id}/cases/{resident_id}/override")
async def override(incident_id: str, resident_id: str, body: Override) -> dict:
    """API-6: coordinator marks a case confirmed safe or escalated, with a note."""
    return await coordinator.override_case(incident_id, resident_id, body.to_status, body.note)


@router.post("/{incident_id}/sitrep", status_code=202)
async def make_sitrep(incident_id: str) -> dict:
    """API-7: generate a grounded situation report now (background job)."""
    return {"queued": sitrep.request(incident_id)}
