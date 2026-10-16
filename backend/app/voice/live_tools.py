"""Live call tools (PRD §13.4): record_status and end_call.

record_status only stores the agent's view on the call; the case status is set later by
the post-call pipeline (classifier + cautious final rule, §14.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models import CaseStatus, Need

LiveStatus = Literal["SAFE_IN_PLACE", "NEEDS_EVACUATION", "NEEDS_HELP", "MEDICAL"]
_NEEDS = {n.value for n in Need}


class RecordStatus(BaseModel):
    status: LiveStatus
    needs: list[str] = []
    summary_en: str = Field(default="", description="<= 200 chars, factual")
    needs_human: bool = False


@dataclass
class CallState:
    """Everything the post-call pipeline needs from one live call."""

    incident_id: str
    resident_id: str
    attempt: int
    transcript: list[dict[str, Any]] = field(default_factory=list)
    live_status: CaseStatus | None = None
    needs: list[str] = field(default_factory=list)
    summary_en: str = ""
    needs_human: bool = False
    end_requested: bool = False

    @property
    def resident_spoke(self) -> bool:
        return any(t["role"] == "resident" and t["text"].strip() for t in self.transcript)


def apply_record_status(state: CallState, args: dict[str, Any]) -> dict[str, Any]:
    """Validate and store a record_status call. Returns the tool response."""
    try:
        rs = RecordStatus.model_validate(args)
    except Exception as exc:  # noqa: BLE001 - report back to the model, never raise
        return {"ok": False, "error": f"invalid arguments: {exc}"[:200]}
    state.live_status = CaseStatus(rs.status)
    state.needs = [n for n in rs.needs if n in _NEEDS]
    state.summary_en = rs.summary_en[:200]
    state.needs_human = rs.needs_human
    return {"ok": True, "recorded": rs.status}


def apply_end_call(state: CallState, args: dict[str, Any]) -> dict[str, Any]:
    state.end_requested = True
    return {"ok": True}


def function_declarations() -> list[dict[str, Any]]:
    """Tool schema for the Gemini Live session (§13.4)."""
    return [
        {
            "name": "record_status",
            "description": "Record the resident's situation once you know it.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "status": {"type": "STRING", "enum": list(LiveStatus.__args__)},
                    "needs": {"type": "ARRAY", "items": {"type": "STRING", "enum": sorted(_NEEDS)}},
                    "summary_en": {"type": "STRING", "description": "English, max 200 chars"},
                    "needs_human": {"type": "BOOLEAN"},
                },
                "required": ["status", "summary_en", "needs_human"],
            },
        },
        {
            "name": "end_call",
            "description": "End the call after saying goodbye.",
            "parameters": {
                "type": "OBJECT",
                "properties": {"reason": {"type": "STRING"}},
                "required": ["reason"],
            },
        },
    ]
