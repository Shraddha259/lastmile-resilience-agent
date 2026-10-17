"""FR-12: tool-call validation (PRD §12.4)."""

import pytest

from app.agent.validator import allowed_tools, planning_tools, validate
from app.models import CaseStatus as S


def case(status, attempts=1):
    return {"resident_id": "R-010", "status": status.value, "attempts": attempts}


def check(
    tool,
    args,
    status=S.NEEDS_EVACUATION,
    attempts=1,
    shelters=("S-1", "S-3"),
    vols=("V-2", "V-3", "V-6"),
):
    return validate(
        tool,
        {"resident_id": "R-010", **args},
        event_resident_id="R-010",
        case=case(status, attempts),
        candidate_shelter_ids=set(shelters),
        top_volunteer_ids=set(vols),
    )


def test_FR_12_valid_reserve_is_cleaned():
    res = check(
        "reserve_shelter",
        {"shelter_id": "S-3", "reason": "  closest with space  ", "briefing_en": "ignored"},
    )
    assert res.ok
    assert res.args == {"resident_id": "R-010", "shelter_id": "S-3", "reason": "closest with space"}


def test_FR_12_disallowed_tool_for_status():
    res = check("confirm_safe", {"reason": "x"}, status=S.NEEDS_EVACUATION)
    assert not res.ok and res.error == "TOOL_NOT_ALLOWED"


def test_FR_12_wrong_resident_rejected():
    res = validate(
        "confirm_safe",
        {"resident_id": "R-999", "reason": "x"},
        event_resident_id="R-010",
        case=case(S.SAFE_IN_PLACE),
        candidate_shelter_ids=set(),
        top_volunteer_ids=set(),
    )
    assert not res.ok and res.error == "WRONG_RESIDENT"


def test_FR_12_unknown_shelter_rejected():
    res = check("reserve_shelter", {"shelter_id": "S-9", "reason": "x"})
    assert not res.ok and res.error == "UNKNOWN_SHELTER"


def test_FR_12_unknown_volunteer_rejected():
    res = check(
        "dispatch_volunteer",
        {
            "task_type": "ESCORT_TO_SHELTER",
            "urgency": "HIGH",
            "briefing_en": "b",
            "reason": "r",
            "volunteer_id": "V-8",
        },
        status=S.SHELTER_RESERVED,
    )
    assert not res.ok and res.error == "UNKNOWN_VOLUNTEER"


def test_FR_12_over_long_strings_rejected():
    res = check("reserve_shelter", {"shelter_id": "S-1", "reason": "x" * 201})
    assert not res.ok and res.error == "TOO_LONG"
    res = check(
        "dispatch_volunteer",
        {
            "task_type": "ASSIST_IN_PLACE",
            "urgency": "NORMAL",
            "briefing_en": "b" * 301,
            "reason": "r",
        },
        status=S.NEEDS_HELP,
    )
    assert not res.ok and res.error == "TOO_LONG"


@pytest.mark.parametrize(
    ("tool", "args", "status"),
    [
        (
            "dispatch_volunteer",
            {"task_type": "HUMAN_REVIEW", "urgency": "HIGH", "briefing_en": "b", "reason": "r"},
            S.NEEDS_HELP,
        ),
        (
            "dispatch_volunteer",
            {
                "task_type": "ASSIST_IN_PLACE",
                "urgency": "CRITICAL",
                "briefing_en": "b",
                "reason": "r",
            },
            S.NEEDS_HELP,
        ),
        ("escalate_to_human", {"urgency": "NORMAL", "reason": "r"}, S.SAFE_IN_PLACE),
    ],
)
def test_FR_12_bad_enums_rejected(tool, args, status):
    res = check(tool, args, status=status)
    assert not res.ok and res.error == "BAD_ENUM"


def test_FR_12_missing_required_args():
    res = check("reserve_shelter", {"shelter_id": "S-1", "reason": "   "})
    assert not res.ok and res.error == "MISSING_ARGS"


def test_FR_12_retry_vs_next_of_kin_by_attempts():
    assert "schedule_retry" in allowed_tools(S.NO_ANSWER, attempts=1)
    assert "contact_next_of_kin" not in allowed_tools(S.NO_ANSWER, attempts=1)
    assert "contact_next_of_kin" in allowed_tools(S.NO_ANSWER, attempts=3)
    assert "schedule_retry" not in allowed_tools(S.NO_ANSWER, attempts=3)


def test_FR_20_FR_4_no_agent_tools_for_medical_or_terminal():
    for st in (S.MEDICAL, S.ESCALATED, S.CONFIRMED_SAFE, S.CONTACTING, S.VOLUNTEER_PENDING):
        assert allowed_tools(st, 1) == []


def test_planning_tools_allow_reserve_then_dispatch():
    assert planning_tools(S.NEEDS_EVACUATION, 1)[:2] == ["reserve_shelter", "dispatch_volunteer"]
    assert "dispatch_volunteer" in planning_tools(S.NO_ANSWER, 3)
    assert "find_shelters" not in planning_tools(S.NEEDS_EVACUATION, 1)
