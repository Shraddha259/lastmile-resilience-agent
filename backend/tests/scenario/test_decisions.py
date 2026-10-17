"""M3: structured decision engine (FR-14), validation (FR-12), AC-4. Fake GenAI, emulator."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.agent import decision, tools
from app.agent.context import current_incident
from app.config import get_settings
from app.models import TERMINAL_STATUSES, Actor, CaseStatus
from app.services import db, dispatcher

H = {"X-Demo-Passcode": "test-passcode"}


@pytest.fixture
def engine_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "FORCE_FALLBACK", False)


@pytest.fixture
async def client(fresh_db):
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _incident(
    inc: str, rid: str, status: CaseStatus, attempts: int = 1, needs: list[str] | None = None
) -> None:
    await db.set_doc(
        db.incident_ref(inc),
        {
            "incident_id": inc,
            "status": "ACTIVE",
            "auto_approve_dispatch": True,
            "sim_time_scale": 100,
            "counters": {"total": 1, "confirmed_safe": 0, "escalated": 0, "in_progress": 1},
        },
    )
    await db.set_doc(
        db.case_ref(inc, rid),
        {
            "resident_id": rid,
            "status": status.value,
            "version": 0,
            "attempts": attempts,
            "needs": needs or [],
            "human_review": False,
            "assigned_shelter_id": None,
        },
    )


async def _events(inc: str) -> list[dict]:
    return await db.list_docs(db.events_col(inc))


async def test_FR_14_full_run_uses_agent_and_rarely_falls_back(client, engine_on):
    r = await client.post(
        "/api/scenarios",
        headers=H,
        json={"scenario_id": "flood_demo", "auto_approve_dispatch": True, "sim_time_scale": 100},
    )
    inc = r.json()["incident_id"]
    loop = asyncio.get_running_loop()
    end = loop.time() + 90
    while loop.time() < end:
        cases = await db.list_cases(inc)
        if all(CaseStatus(c["status"]) in TERMINAL_STATUSES for c in cases):
            break
        await asyncio.sleep(0.5)
    by = [c["status"] for c in cases]
    safe, esc = by.count("CONFIRMED_SAFE"), by.count("ESCALATED")
    assert safe + esc == 40, {c["resident_id"]: c["status"] for c in cases}
    assert 32 <= safe <= 37, (safe, esc)

    events = await _events(inc)
    agent_actions = [e for e in events if e["actor"] == "agent" and e.get("status_to")]
    plans = [e for e in events if e["event_type"] == "AGENT_DECISION"]
    assert agent_actions and plans and all(p["model"] == "fake" for p in plans)
    attempts = db.STATS["decisions"] + db.STATS["decision_errors"]
    rate = db.STATS["decisions_fallback"] / attempts
    print(f"\nM3: {attempts} decisions, fallback rate {rate:.0%}, {safe} safe / {esc} escalated")
    assert rate < 0.2  # M3 gate (PRD §22)
    await client.post(f"/api/incidents/{inc}/stop", headers=H, json={"reason": "done"})


async def test_AC_4_agent_cannot_confirm_an_escalated_case(fresh_db):
    inc = "inc_ac4_test"
    await _incident(inc, "R-010", CaseStatus.ESCALATED)
    token = current_incident.set(inc)
    try:
        res = await tools.confirm_safe("R-010", "looks fine", actor=Actor.agent)
    finally:
        current_incident.reset(token)
    assert res["ok"] is False
    case = await db.get_doc(db.case_ref(inc, "R-010"))
    assert case["status"] == "ESCALATED" and case["version"] == 0


async def test_FR_12_rejected_plan_is_audited_and_fallback_finishes(
    fresh_db, engine_on, monkeypatch
):
    inc, rid = "inc_reject_test", "R-005"
    await _incident(inc, rid, CaseStatus.NEEDS_EVACUATION, needs=["oxygen"])
    bad = {
        "actions": [
            {
                "tool": "reserve_shelter",
                "args": {"resident_id": rid, "shelter_id": "S-99", "reason": "invented shelter"},
            }
        ],
        "overall_reason": "made up",
    }
    monkeypatch.setattr(decision, "fake_decision", lambda ctx: bad)

    await dispatcher.handle_event(inc, {"type": "CHECKIN_COMPLETED", "resident_id": rid})

    case = await db.get_doc(db.case_ref(inc, rid))
    assert case["status"] == "VOLUNTEER_EN_ROUTE"  # policy reserved a real shelter + dispatched
    assert case["assigned_shelter_id"] == "S-3"  # oxygen user -> medical-support shelter
    events = await _events(inc)
    rejected = [e for e in events if e.get("result") == "rejected"]
    assert rejected and "S-99" in rejected[0]["reason"]
    assert any(e["actor"] == "policy" and e.get("tool") == "reserve_shelter" for e in events)
