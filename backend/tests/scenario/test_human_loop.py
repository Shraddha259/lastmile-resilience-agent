"""M5 human loop (PRD §11.2 API-5/6/7, AC-3, FR-25): coordinator approvals, overrides, SITREP."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.models import CaseStatus
from app.services import db, dispatcher, sitrep, worker

H = {"X-Demo-Passcode": "test-passcode"}
INC = "inc_m5_test"


@pytest.fixture
def engine_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "FORCE_FALLBACK", False)


@pytest.fixture
async def client(fresh_db):
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    worker.cancel_incident(INC)


async def _incident(auto_approve: bool = False) -> None:
    await db.set_doc(
        db.incident_ref(INC),
        {
            "incident_id": INC,
            "status": "ACTIVE",
            "auto_approve_dispatch": auto_approve,
            "sim_time_scale": 100,
            "counters": {"total": 2, "confirmed_safe": 0, "escalated": 0, "in_progress": 2},
        },
    )


async def _case(rid: str, status: CaseStatus, **extra) -> None:
    await db.set_doc(
        db.case_ref(INC, rid),
        {
            "resident_id": rid,
            "status": status.value,
            "version": 0,
            "attempts": 1,
            "needs": [],
            "human_review": False,
            "assigned_shelter_id": None,
            "open_task_id": None,
            "last_summary_en": "test",
            **extra,
        },
    )


async def _status(rid: str) -> str:
    return (await db.get_doc(db.case_ref(INC, rid)))["status"]


async def _wait(rid: str, want: str, limit_s: float = 10) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + limit_s
    while loop.time() < end:
        if await _status(rid) == want:
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"{rid} is {await _status(rid)}, wanted {want}")


async def _pending_dispatch(rid: str = "R-010") -> dict:
    """A NEEDS_HELP case the policy turns into a dispatch waiting for approval."""
    await _incident(auto_approve=False)
    await _case(rid, CaseStatus.NEEDS_HELP)
    await dispatcher.handle_event(INC, {"type": "CHECKIN_COMPLETED", "resident_id": rid})
    case = await db.get_doc(db.case_ref(INC, rid))
    assert case["status"] == "VOLUNTEER_PENDING"
    return await db.get_doc(db.task_ref(INC, case["open_task_id"]))


async def test_API_5_approve_starts_the_volunteer_until_safe(client):
    task = await _pending_dispatch()
    assert task["status"] == "PENDING_APPROVAL"
    r = await client.post(
        f"/api/incidents/{INC}/tasks/{task['task_id']}/decision",
        headers=H,
        json={"decision": "APPROVE"},
    )
    assert r.status_code == 200, r.text
    await _wait("R-010", "CONFIRMED_SAFE")
    task = await db.get_doc(db.task_ref(INC, task["task_id"]))
    assert task["status"] == "DONE" and task["decided_by"] == "coordinator"


async def test_API_5_reject_needs_note_frees_volunteer_and_escalates(client):
    task = await _pending_dispatch()
    url = f"/api/incidents/{INC}/tasks/{task['task_id']}/decision"
    r = await client.post(url, headers=H, json={"decision": "REJECT", "note": "no"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"

    r = await client.post(url, headers=H, json={"decision": "REJECT", "note": "Road is flooded"})
    assert r.status_code == 200, r.text
    case = await db.get_doc(db.case_ref(INC, "R-010"))
    assert case["status"] == "ESCALATED" and case["human_review"] is True
    review = await db.get_doc(db.task_ref(INC, case["open_task_id"]))
    assert review["type"] == "HUMAN_REVIEW" and "Road is flooded" in review["briefing_en"]
    vol = await db.get_doc(db.volunteer_ref(task["volunteer_id"]))
    assert vol["available"] is True
    again = await client.post(url, headers=H, json={"decision": "APPROVE"})
    assert again.status_code == 409  # already decided


async def test_API_6_override_escalated_to_safe_closes_review(client):
    await _incident()
    await _case("R-011", CaseStatus.MEDICAL)
    await dispatcher.handle_event(INC, {"type": "CHECKIN_COMPLETED", "resident_id": "R-011"})
    case = await db.get_doc(db.case_ref(INC, "R-011"))
    review_id = case["open_task_id"]
    url = f"/api/incidents/{INC}/cases/R-011/override"

    r = await client.post(url, headers=H, json={"to_status": "CONFIRMED_SAFE", "note": "ok"})
    assert r.status_code == 422
    r = await client.post(
        url,
        headers=H,
        json={"to_status": "CONFIRMED_SAFE", "note": "Ambulance took husband; she is fine"},
    )
    assert r.status_code == 200, r.text
    case = await db.get_doc(db.case_ref(INC, "R-011"))
    assert case["status"] == "CONFIRMED_SAFE" and case["confirmed_by"] == "coordinator"
    assert (await db.get_doc(db.task_ref(INC, review_id)))["status"] == "DONE"
    inc = await db.get_doc(db.incident_ref(INC))
    assert inc["counters"]["confirmed_safe"] == 1 and inc["counters"]["escalated"] == 0


async def test_API_6_override_cancels_an_active_dispatch(client):
    task = await _pending_dispatch()
    r = await client.post(
        f"/api/incidents/{INC}/cases/R-010/override",
        headers=H,
        json={"to_status": "CONFIRMED_SAFE", "note": "Son picked her up"},
    )
    assert r.status_code == 200, r.text
    assert (await db.get_doc(db.task_ref(INC, task["task_id"])))["status"] == "CANCELLED"
    assert (await db.get_doc(db.volunteer_ref(task["volunteer_id"])))["available"] is True


async def test_AC_3_medical_escalates_within_2s_before_any_llm_call(client, engine_on):
    await _incident()
    await _case("R-011", CaseStatus.MEDICAL)
    t0 = asyncio.get_running_loop().time()
    await dispatcher.handle_event(INC, {"type": "CHECKIN_COMPLETED", "resident_id": "R-011"})
    assert asyncio.get_running_loop().time() - t0 < 2
    case = await db.get_doc(db.case_ref(INC, "R-011"))
    task = await db.get_doc(db.task_ref(INC, case["open_task_id"]))
    assert case["status"] == "ESCALATED"
    assert task["type"] == "HUMAN_REVIEW" and task["urgency"] == "CRITICAL"
    events = await db.list_docs(db.events_col(INC))
    assert not [e for e in events if e["event_type"] == "AGENT_DECISION"]  # no LLM decision


async def test_FR_25_sitrep_is_grounded_and_stored(client):
    await _incident()
    await _case("R-011", CaseStatus.ESCALATED, last_summary_en="Husband fell")
    await _case("R-010", CaseStatus.CONFIRMED_SAFE)
    r = await client.post(f"/api/incidents/{INC}/sitrep", headers=H)
    assert r.status_code == 202
    await worker.drain(INC, limit_s=5)
    reports = await db.list_docs(db.incident_ref(INC).collection("sitreps"))
    assert len(reports) == 1
    text = reports[0]["summary_en"]
    assert "R-011" in text and "Status:" in text and reports[0]["grounded_on_version"] == 0


def test_FR_25_sitrep_grounding_rejects_invented_ids():
    snap = {"escalated": [{"resident_id": "R-011"}], "shelters": [{"shelter_id": "S-1"}]}
    assert sitrep.grounded("R-011 needs a human; S-1 has space.", snap)
    assert not sitrep.grounded("R-011 and R-099 need help.", snap)
    assert not sitrep.grounded("Send everyone to S-9.", snap)
