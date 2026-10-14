"""FR-1: transition_case() against the Firestore emulator (PRD §9.3)."""

import asyncio

import pytest

from app.models import Actor, CaseStatus, IncidentStatus
from app.policy.state_machine import Guard, transition_case
from app.services import db, shelters
from app.util.errors import IncidentNotActive, InvalidTransition, VersionConflict

INC = "inc_test_0001"


async def _setup(status=CaseStatus.PENDING, inc_status=IncidentStatus.ACTIVE, attempts=0):
    await db.set_doc(
        db.incident_ref(INC),
        {
            "incident_id": INC,
            "status": inc_status.value,
            "auto_approve_dispatch": False,
            "sim_time_scale": 100,
            "counters": {"total": 1, "confirmed_safe": 0, "escalated": 0, "in_progress": 1},
        },
    )
    await db.set_doc(
        db.case_ref(INC, "R-001"),
        {
            "resident_id": "R-001",
            "status": status.value,
            "version": 0,
            "attempts": attempts,
            "human_review": False,
        },
    )


async def _events():
    return await db.list_docs(db.events_col(INC))


async def test_FR_1_transition_updates_case_counters_and_audit(fresh_db):
    await _setup(CaseStatus.SAFE_IN_PLACE)
    case = await transition_case(
        INC,
        "R-001",
        CaseStatus.CONFIRMED_SAFE,
        Actor.policy,
        "ok",
        guard=Guard(confidence=0.95, requires_review=False),
    )
    assert case.status == CaseStatus.CONFIRMED_SAFE and case.version == 1
    inc = await db.get_doc(db.incident_ref(INC))
    assert inc["counters"] == {"total": 1, "confirmed_safe": 1, "escalated": 0, "in_progress": 0}
    ev = await _events()
    assert len(ev) == 1 and ev[0]["status_to"] == "CONFIRMED_SAFE" and ev[0]["actor"] == "policy"


async def test_FR_1_version_conflict(fresh_db):
    await _setup()
    with pytest.raises(VersionConflict):
        await transition_case(
            INC, "R-001", CaseStatus.QUEUED, Actor.system, "x", expected_version=5
        )
    assert (await db.get_doc(db.case_ref(INC, "R-001")))["status"] == "PENDING"


async def test_FR_1_invalid_transition_writes_nothing(fresh_db):
    await _setup(CaseStatus.ESCALATED)
    with pytest.raises(InvalidTransition):
        await transition_case(
            INC,
            "R-001",
            CaseStatus.CONFIRMED_SAFE,
            Actor.agent,
            "x",
            guard=Guard(confidence=1.0, requires_review=False),
        )
    assert await _events() == []


async def test_FR_1_low_confidence_cannot_confirm(fresh_db):
    await _setup(CaseStatus.SAFE_IN_PLACE)
    with pytest.raises(InvalidTransition):
        await transition_case(
            INC,
            "R-001",
            CaseStatus.CONFIRMED_SAFE,
            Actor.agent,
            "x",
            guard=Guard(confidence=0.5, requires_review=False),
        )


async def test_FR_1_incident_not_active(fresh_db):
    await _setup(CaseStatus.PENDING, IncidentStatus.STOPPED)
    with pytest.raises(IncidentNotActive):
        await transition_case(INC, "R-001", CaseStatus.QUEUED, Actor.policy, "x")


async def test_FR_1_patch_whitelist(fresh_db):
    await _setup()
    with pytest.raises(InvalidTransition):
        await transition_case(
            INC, "R-001", CaseStatus.QUEUED, Actor.system, "x", patch={"risk_score": 1}
        )


async def test_FR_1_attempt_counted_on_contact(fresh_db):
    await _setup(CaseStatus.QUEUED)
    case = await transition_case(INC, "R-001", CaseStatus.CONTACTING, Actor.system, "x")
    assert case.attempts == 1


async def test_retry_guard_respects_max_attempts(fresh_db):
    await _setup(CaseStatus.NO_ANSWER, attempts=3)
    with pytest.raises(InvalidTransition):
        await transition_case(INC, "R-001", CaseStatus.RETRY_SCHEDULED, Actor.policy, "x")
    await transition_case(INC, "R-001", CaseStatus.NEXT_OF_KIN_CONTACTED, Actor.policy, "x")


async def test_AC_7_concurrent_reservations_respect_capacity(fresh_db):
    results = await asyncio.gather(*(shelters.reserve_shelter("S-3") for _ in range(12)))
    assert sum(results) == 10
    assert (await db.get_doc(db.shelter_ref("S-3")))["occupied"] == 10
