"""Tool-call validation (PRD §12.4, FR-12). Runs before every agent tool side effect.

The LLM proposes, code decides: anything that fails here is never executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.models import Actor, CaseStatus, TaskType, Urgency
from app.policy.state_machine import is_allowed

REASON_MAX = 200
BRIEFING_MAX = 300
MESSAGE_MAX = 300

# Tools the agent may call per case status (§12.3). find_shelters is never an action:
# candidates are pre-loaded into CONTEXT (§12.0).
_BY_STATUS: dict[CaseStatus, tuple[str, ...]] = {
    CaseStatus.SAFE_IN_PLACE: ("confirm_safe",),
    CaseStatus.NEEDS_EVACUATION: ("reserve_shelter",),
    CaseStatus.SHELTER_RESERVED: ("dispatch_volunteer",),
    CaseStatus.NEEDS_HELP: ("dispatch_volunteer",),
    CaseStatus.NEXT_OF_KIN_CONTACTED: ("dispatch_volunteer",),
}
_ALWAYS = ("escalate_to_human", "add_note")
# Status each state-changing tool moves the case to (for the transition check).
_TARGET = {
    "confirm_safe": CaseStatus.CONFIRMED_SAFE,
    "schedule_retry": CaseStatus.RETRY_SCHEDULED,
    "contact_next_of_kin": CaseStatus.NEXT_OF_KIN_CONTACTED,
    "reserve_shelter": CaseStatus.SHELTER_RESERVED,
    "dispatch_volunteer": CaseStatus.VOLUNTEER_PENDING,
    "escalate_to_human": CaseStatus.ESCALATED,
}
_DISPATCH_TYPES = {
    TaskType.ESCORT_TO_SHELTER.value,
    TaskType.ASSIST_IN_PLACE.value,
    TaskType.WELFARE_CHECK.value,
}
_URGENCY = {
    "dispatch_volunteer": {Urgency.NORMAL.value, Urgency.HIGH.value},
    "escalate_to_human": {Urgency.HIGH.value, Urgency.CRITICAL.value},
}
_REQUIRED = {
    "confirm_safe": ("reason",),
    "schedule_retry": ("reason",),
    "contact_next_of_kin": ("message_en", "reason"),
    "reserve_shelter": ("shelter_id", "reason"),
    "dispatch_volunteer": ("task_type", "urgency", "briefing_en", "reason"),
    "escalate_to_human": ("urgency", "reason"),
    "add_note": ("note",),
}
# Arguments each tool accepts (anything else the model sends is dropped).
_ACCEPTS = {
    "confirm_safe": ("reason",),
    "schedule_retry": ("reason",),
    "contact_next_of_kin": ("message_en", "reason"),
    "reserve_shelter": ("shelter_id", "reason"),
    "dispatch_volunteer": ("task_type", "urgency", "briefing_en", "reason", "volunteer_id"),
    "escalate_to_human": ("urgency", "reason"),
    "add_note": ("note",),
}
_LIMITS = {
    "reason": REASON_MAX,
    "briefing_en": BRIEFING_MAX,
    "message_en": MESSAGE_MAX,
    "note": REASON_MAX,
}


def allowed_tools(status: CaseStatus, attempts: int) -> list[str]:
    """ALLOWED_TOOLS_NOW for a case status (PRD §12.2). Empty for non-actionable statuses."""
    if status == CaseStatus.NO_ANSWER:
        main = (
            ("schedule_retry",)
            if attempts < get_settings().MAX_ATTEMPTS
            else ("contact_next_of_kin",)
        )
    else:
        main = _BY_STATUS.get(status, ())
    if not main:
        return []
    return [*main, *_ALWAYS]


def planning_tools(status: CaseStatus, attempts: int) -> list[str]:
    """Tools the model may chain in one decision (e.g. reserve_shelter then dispatch)."""
    tools = allowed_tools(status, attempts)
    if status == CaseStatus.NEEDS_EVACUATION or "contact_next_of_kin" in tools:
        tools = [*tools[:1], "dispatch_volunteer", *tools[1:]]
    return tools


@dataclass
class ValidationResult:
    ok: bool
    args: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    message: str = ""

    def as_tool_result(self) -> dict[str, Any]:
        return {"ok": False, "error": self.error, "message": self.message}


def _fail(code: str, message: str) -> ValidationResult:
    return ValidationResult(False, error=code, message=message)


def validate(
    tool: str,
    args: dict[str, Any],
    *,
    event_resident_id: str,
    case: dict[str, Any],
    candidate_shelter_ids: set[str],
    top_volunteer_ids: set[str],
) -> ValidationResult:
    """Check one proposed tool call against PRD §12.4 rules 1-5.

    Returns the cleaned (trimmed, length-limited, filtered) args on success.
    """
    status = CaseStatus(case["status"])
    # 1. Tool is allowed for the case's current status.
    if tool not in allowed_tools(status, case.get("attempts", 0)):
        return _fail("TOOL_NOT_ALLOWED", f"{tool} is not allowed while the case is {status}")
    # 2. resident_id is the event's resident (FR-11: no cross-resident actions).
    if args.get("resident_id") != event_resident_id:
        return _fail("WRONG_RESIDENT", f"resident_id must be {event_resident_id}")

    clean: dict[str, Any] = {"resident_id": event_resident_id}
    for key in _ACCEPTS[tool]:
        val = args.get(key)
        if isinstance(val, str):
            val = val.strip()
            if not val:
                val = None
        if val is None:
            continue
        # 3. Strings are trimmed and length-limited.
        if key in _LIMITS and len(val) > _LIMITS[key]:
            return _fail("TOO_LONG", f"{key} exceeds {_LIMITS[key]} characters")
        clean[key] = val
    missing = [k for k in _REQUIRED[tool] if k not in clean]
    if missing:
        return _fail("MISSING_ARGS", f"{tool} needs {', '.join(missing)}")

    # 3. Enum arguments are valid.
    if tool == "dispatch_volunteer" and clean["task_type"] not in _DISPATCH_TYPES:
        return _fail("BAD_ENUM", f"task_type must be one of {sorted(_DISPATCH_TYPES)}")
    if tool in _URGENCY and clean["urgency"] not in _URGENCY[tool]:
        return _fail("BAD_ENUM", f"urgency must be one of {sorted(_URGENCY[tool])}")

    # 4. Referenced IDs exist in the candidates given to the model.
    if tool == "reserve_shelter" and clean["shelter_id"] not in candidate_shelter_ids:
        return _fail("UNKNOWN_SHELTER", f"{clean['shelter_id']} is not a candidate shelter")
    if "volunteer_id" in clean and clean["volunteer_id"] not in top_volunteer_ids:
        return _fail("UNKNOWN_VOLUNTEER", f"{clean['volunteer_id']} is not an available volunteer")

    # 5. The transition is allowed for actor A (guards are re-checked in transition_case).
    target = _TARGET.get(tool)
    if target is not None and not is_allowed(status, target, Actor.agent):
        return _fail("INVALID_TRANSITION", f"Agent cannot move {status} to {target}")
    return ValidationResult(True, clean)
