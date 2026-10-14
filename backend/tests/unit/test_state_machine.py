"""FR-2/FR-3/FR-4: the transitions table (PRD §9.4)."""

import pytest

from app.models import TERMINAL_STATUSES, Actor, CaseStatus
from app.policy.state_machine import TRANSITIONS, is_allowed

S, A, P, V, C, SYS = (
    CaseStatus,
    Actor.agent,
    Actor.policy,
    Actor.volunteer,
    Actor.coordinator,
    Actor.system,
)

ALLOWED = [
    (S.PENDING, S.QUEUED, SYS),
    (S.QUEUED, S.RINGING, SYS),
    (S.RETRY_SCHEDULED, S.RINGING, SYS),
    (S.QUEUED, S.CONTACTING, SYS),
    (S.RETRY_SCHEDULED, S.CONTACTING, SYS),
    (S.RINGING, S.CONTACTING, SYS),
    (S.RINGING, S.NO_ANSWER, SYS),
    (S.CONTACTING, S.SAFE_IN_PLACE, SYS),
    (S.CONTACTING, S.NEEDS_EVACUATION, SYS),
    (S.CONTACTING, S.NEEDS_HELP, SYS),
    (S.CONTACTING, S.MEDICAL, SYS),
    (S.CONTACTING, S.NO_ANSWER, SYS),
    (S.SAFE_IN_PLACE, S.CONFIRMED_SAFE, A),
    (S.SAFE_IN_PLACE, S.CONFIRMED_SAFE, P),
    (S.SAFE_IN_PLACE, S.ESCALATED, A),
    (S.SAFE_IN_PLACE, S.ESCALATED, P),
    (S.NO_ANSWER, S.RETRY_SCHEDULED, A),
    (S.NO_ANSWER, S.RETRY_SCHEDULED, P),
    (S.NO_ANSWER, S.NEXT_OF_KIN_CONTACTED, A),
    (S.NO_ANSWER, S.NEXT_OF_KIN_CONTACTED, P),
    (S.NEXT_OF_KIN_CONTACTED, S.VOLUNTEER_PENDING, P),
    (S.NEXT_OF_KIN_CONTACTED, S.VOLUNTEER_EN_ROUTE, A),
    (S.NEEDS_EVACUATION, S.SHELTER_RESERVED, A),
    (S.NEEDS_EVACUATION, S.SHELTER_RESERVED, P),
    (S.SHELTER_RESERVED, S.VOLUNTEER_PENDING, A),
    (S.NEEDS_HELP, S.VOLUNTEER_PENDING, P),
    (S.SHELTER_RESERVED, S.VOLUNTEER_EN_ROUTE, P),
    (S.NEEDS_HELP, S.VOLUNTEER_EN_ROUTE, A),
    (S.VOLUNTEER_PENDING, S.VOLUNTEER_EN_ROUTE, C),
    (S.VOLUNTEER_PENDING, S.VOLUNTEER_EN_ROUTE, V),
    (S.VOLUNTEER_PENDING, S.ESCALATED, C),
    (S.MEDICAL, S.ESCALATED, A),
    (S.MEDICAL, S.ESCALATED, P),
    (S.VOLUNTEER_EN_ROUTE, S.AT_SHELTER, V),
    (S.VOLUNTEER_EN_ROUTE, S.CONFIRMED_SAFE, V),
    (S.VOLUNTEER_EN_ROUTE, S.ESCALATED, V),
    (S.AT_SHELTER, S.CONFIRMED_SAFE, V),
    (S.AT_SHELTER, S.CONFIRMED_SAFE, C),
    (S.ESCALATED, S.CONFIRMED_SAFE, C),
]

DISALLOWED = [
    # FR-3: the agent confirms safe only from SAFE_IN_PLACE
    (S.ESCALATED, S.CONFIRMED_SAFE, A),
    (S.MEDICAL, S.CONFIRMED_SAFE, A),
    (S.NEEDS_EVACUATION, S.CONFIRMED_SAFE, A),
    (S.NO_ANSWER, S.CONFIRMED_SAFE, A),
    (S.AT_SHELTER, S.CONFIRMED_SAFE, A),
    (S.VOLUNTEER_EN_ROUTE, S.CONFIRMED_SAFE, A),
    (S.CONTACTING, S.CONFIRMED_SAFE, A),
    (S.PENDING, S.CONFIRMED_SAFE, P),
    # FR-4: the agent can never leave ESCALATED
    (S.ESCALATED, S.SAFE_IN_PLACE, A),
    (S.ESCALATED, S.RETRY_SCHEDULED, A),
    (S.ESCALATED, S.VOLUNTEER_PENDING, A),
    (S.ESCALATED, S.CONFIRMED_SAFE, P),
    # actor mismatches and skipped steps
    (S.PENDING, S.QUEUED, A),
    (S.CONTACTING, S.SAFE_IN_PLACE, A),
    (S.VOLUNTEER_PENDING, S.VOLUNTEER_EN_ROUTE, A),
    (S.VOLUNTEER_EN_ROUTE, S.AT_SHELTER, A),
    (S.AT_SHELTER, S.CONFIRMED_SAFE, P),
    (S.NEEDS_EVACUATION, S.VOLUNTEER_PENDING, P),
    (S.CONFIRMED_SAFE, S.ESCALATED, C),
    (S.QUEUED, S.SAFE_IN_PLACE, SYS),
]


@pytest.mark.parametrize(("frm", "to", "actor"), ALLOWED)
def test_FR_2_allowed_transitions(frm, to, actor):
    assert is_allowed(frm, to, actor)


@pytest.mark.parametrize(("frm", "to", "actor"), DISALLOWED)
def test_FR_2_FR_3_FR_4_disallowed_transitions(frm, to, actor):
    assert not is_allowed(frm, to, actor)


def test_FR_3_agent_confirm_safe_only_from_safe_in_place():
    for (frm, to), actors in TRANSITIONS.items():
        if to == S.CONFIRMED_SAFE and Actor.agent in actors:
            assert frm == S.SAFE_IN_PLACE


def test_FR_4_agent_never_leaves_escalated():
    for (frm, _), actors in TRANSITIONS.items():
        if frm == S.ESCALATED:
            assert Actor.agent not in actors and Actor.policy not in actors


def test_coordinator_override_from_any_non_terminal():
    for st in CaseStatus:
        if st not in TERMINAL_STATUSES:
            assert is_allowed(st, S.ESCALATED, C)
            assert is_allowed(st, S.CONFIRMED_SAFE, C)
