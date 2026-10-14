"""Scenario tests (PRD §20.2): emulator + inline worker + fake GenAI, SIM_TIME_SCALE=100."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.models import TERMINAL_STATUSES, CaseStatus, IncidentStatus
from app.services import db, jobs, worker

H = {"X-Demo-Passcode": "test-passcode"}


@pytest.fixture
async def client(fresh_db):
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _start(client, **body) -> str:
    r = await client.post("/api/scenarios", json={"scenario_id": "flood_demo", **body}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()["incident_id"]


async def _wait_terminal(inc: str, limit_s: float = 90) -> list[dict]:
    loop = asyncio.get_running_loop()
    end = loop.time() + limit_s
    while loop.time() < end:
        cases = await db.list_cases(inc)
        if all(CaseStatus(c["status"]) in TERMINAL_STATUSES for c in cases):
            return cases
        await asyncio.sleep(0.5)
    stuck = {
        c["resident_id"]: c["status"]
        for c in await db.list_cases(inc)
        if CaseStatus(c["status"]) not in TERMINAL_STATUSES
    }
    raise AssertionError(f"Cases not terminal: {stuck}")


async def test_api_requires_passcode(client):
    r = await client.post("/api/scenarios", json={"scenario_id": "flood_demo"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


async def test_AC_1_cases_created_ranked_and_p1_first(client):
    inc = await _start(client)
    cases = await db.list_cases(inc)
    assert len(cases) == 40
    assert all(
        isinstance(c["risk_score"], int) and c["priority"] in ("P1", "P2", "P3") for c in cases
    )
    await asyncio.sleep(0.5)
    events = await db.list_docs(db.events_col(inc))
    queued = sorted((e for e in events if e.get("status_to") == "QUEUED"), key=lambda e: e["ts"])
    prio = {c["resident_id"]: c["priority"] for c in cases}
    n_p1 = sum(1 for p in prio.values() if p == "P1")
    first = [prio[e["resident_id"]] for e in queued[:n_p1]]
    assert first and all(p == "P1" for p in first)
    r = await client.post("/api/scenarios", json={"scenario_id": "flood_demo"}, headers=H)
    assert r.status_code == 409 and r.json()["error"]["code"] == "ACTIVE_INCIDENT_EXISTS"
    await client.post(f"/api/incidents/{inc}/stop", json={"reason": "test"}, headers=H)


async def test_AC_2_AC_10_full_run_fallback_only(client):
    inc = await _start(client, auto_approve_dispatch=True, sim_time_scale=100)
    cases = await _wait_terminal(inc)
    by = {c["resident_id"]: c["status"] for c in cases}
    safe = sum(1 for s in by.values() if s == "CONFIRMED_SAFE")
    esc = sum(1 for s in by.values() if s == "ESCALATED")
    assert safe + esc == 40
    print(f"\nAC-2 outcome: {safe} confirmed safe, {esc} escalated, stats={dict(db.STATS)}")
    assert 32 <= safe <= 37 and 3 <= esc <= 8, (safe, esc)
    # AC-10: counters equal counts recomputed from the cases
    incident = await db.get_doc(db.incident_ref(inc))
    assert incident["counters"] == {
        "total": 40,
        "confirmed_safe": safe,
        "escalated": esc,
        "in_progress": 0,
    }
    # Free-tier budget: Firestore writes per run (docs/COSTS.md)
    assert db.STATS["writes"] < 3000, db.STATS
    await client.post(f"/api/incidents/{inc}/stop", json={"reason": "done"}, headers=H)


async def test_AC_6_duplicate_checkin_counts_one_attempt(client):
    inc = await _start(client, sim_time_scale=100)
    await client.post(f"/api/incidents/{inc}/stop", json={"reason": "freeze"}, headers=H)
    await worker.drain(inc, limit_s=5)
    worker.reset_state()  # allow jobs for this incident again
    await db.update_doc(db.incident_ref(inc), {"status": IncidentStatus.ACTIVE.value})
    rid = "R-010"
    ref = db.case_ref(inc, rid)
    await db.update_doc(ref, {"status": CaseStatus.QUEUED.value, "attempts": 0})
    payload = {"incident_id": inc, "resident_id": rid, "attempt": 1}
    await asyncio.gather(jobs.checkin_job(payload), jobs.checkin_job(payload))
    assert (await db.get_doc(ref))["attempts"] == 1
    await client.post(f"/api/incidents/{inc}/stop", json={"reason": "done"}, headers=H)


async def test_kill_switch_and_reset(client):
    inc = await _start(client, sim_time_scale=100)
    await asyncio.sleep(0.3)
    r = await client.post(f"/api/incidents/{inc}/stop", json={"reason": "kill"}, headers=H)
    assert r.json() == {"status": "STOPPED"}
    await worker.drain(inc, limit_s=5)  # running jobs finish quickly, waiting ones cancel
    before = {c["resident_id"]: c["version"] for c in await db.list_cases(inc)}
    await asyncio.sleep(0.5)
    after = {c["resident_id"]: c["version"] for c in await db.list_cases(inc)}
    assert before == after  # nothing moves after the kill switch
    r = await client.post(f"/api/incidents/{inc}/reset", headers=H)
    assert r.status_code == 200
    assert await db.get_doc(db.incident_ref(inc)) is None
    assert all(s["occupied"] == 0 for s in await db.list_shelters())
