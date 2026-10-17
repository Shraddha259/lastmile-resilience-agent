"""M4 live check-ins (PRD §11.3): text mode with the fake agent, through an in-memory channel."""

import asyncio
import json

import pytest

from app.api.voice import WS_UNAUTHORIZED, answer_call
from app.config import get_settings
from app.models import Channel, CheckinState, IncidentStatus
from app.services import db, jobs, scenario, worker
from app.sim import simulator
from app.voice import sessions

INC, RID = "inc_live_test", "R-001"


class FakeChannel:
    """In-memory WebSocket: tests push frames in and read what the server sent."""

    def __init__(self):
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []
        self.closed_with: int | None = None

    def say(self, text: str) -> None:
        self.inbox.put_nowait({"text": json.dumps({"type": "user_text", "text": text})})

    def hang_up(self) -> None:
        self.inbox.put_nowait({"disconnect": True})

    async def receive(self):
        return await self.inbox.get()

    async def send_json(self, data):
        self.sent.append(data)

    async def send_bytes(self, data):
        self.sent.append({"type": "audio", "bytes": len(data)})

    async def close(self, code=1000):
        self.closed_with = code

    def frames(self, kind):
        return [f for f in self.sent if f.get("type") == kind]


async def _ringing(fresh_db) -> dict:
    """An ACTIVE incident whose live resident R-001 is RINGING on attempt 1."""
    template = await db.get_doc(fresh_db.collection("scenarios").document("flood_demo"))
    await db.set_doc(
        db.incident_ref(INC),
        {
            **{k: template[k] for k in ("title", "official_facts", "polygon", "river_line")},
            "incident_id": INC,
            "status": IncidentStatus.ACTIVE.value,
            "auto_approve_dispatch": True,
            "sim_time_scale": 100,
            "counters": {"total": 1, "confirmed_safe": 0, "escalated": 0, "in_progress": 1},
        },
    )
    await db.set_doc(
        db.case_ref(INC, RID),
        {
            "resident_id": RID,
            "status": "RINGING",
            "version": 3,
            "attempts": 1,
            "needs": [],
            "human_review": False,
            "assigned_shelter_id": None,
            "channel": Channel.live.value,
        },
    )
    resident = await db.get_doc(db.resident_ref(RID))
    await simulator.write_checkin_start(INC, resident, 1, Channel.live, CheckinState.RINGING)
    return await sessions.create_session(INC, RID)


async def _wait_status(want: set[str], limit_s: float = 10) -> dict:
    loop = asyncio.get_running_loop()
    end = loop.time() + limit_s
    while loop.time() < end:
        case = await db.get_doc(db.case_ref(INC, RID))
        if case["status"] in want:
            return case
        await asyncio.sleep(0.1)
    raise AssertionError(f"case is {case['status']}, wanted {want}")


async def test_AC_8_text_call_medical_is_recorded_and_escalated(fresh_db):
    out = await _ringing(fresh_db)
    ch = FakeChannel()
    ch.say("I'm okay but my husband fell in the kitchen and can't get up")
    code = await answer_call(out["token"], ch)

    assert code == 1000
    roles = [f["role"] for f in ch.frames("transcript")]
    assert roles == ["agent", "resident", "agent"]
    assert "automated assistant" in ch.frames("transcript")[0]["text"]  # NFR-S10
    assert ch.frames("status")[0]["live_status"] == "MEDICAL"
    assert ch.frames("call_ended")[0]["reason"] == "agent_end_call"
    ck = await db.get_doc(db.checkin_ref(INC, f"ck_{RID}_1"))
    assert (
        ck["state"] == "COMPLETED" and ck["live_status"] == "MEDICAL" and len(ck["transcript"]) == 3
    )
    case = await _wait_status({"ESCALATED"})  # FR-20: MEDICAL -> human, before any LLM decision
    assert case["human_review"] is True


async def test_token_is_one_time(fresh_db):
    out = await _ringing(fresh_db)
    ch = FakeChannel()
    ch.say("I am safe upstairs with my son")
    assert await answer_call(out["token"], ch) == 1000
    assert await answer_call(out["token"], FakeChannel()) == WS_UNAUTHORIZED
    assert await answer_call("vs_not_a_token", FakeChannel()) == WS_UNAUTHORIZED


async def test_API_8_rejects_cases_that_are_not_ringing(fresh_db):
    await _ringing(fresh_db)
    await db.update_doc(db.case_ref(INC, RID), {"status": "QUEUED"})
    with pytest.raises(sessions.NotRinging):
        await sessions.create_session(INC, RID)
    with pytest.raises(sessions.NotRinging):  # R-010 is a simulated resident
        await db.set_doc(db.case_ref(INC, "R-010"), {"resident_id": "R-010", "status": "RINGING"})
        await sessions.create_session(INC, "R-010")


async def test_AC_5_kill_switch_ends_live_call_within_2s(fresh_db):
    out = await _ringing(fresh_db)
    ch = FakeChannel()  # the resident never answers the question: the call stays open
    call = asyncio.create_task(answer_call(out["token"], ch))
    for _ in range(50):
        if sessions.open_calls(INC):
            break
        await asyncio.sleep(0.05)
    assert sessions.open_calls(INC) == 1

    t0 = asyncio.get_running_loop().time()
    await scenario.stop_incident(INC, "kill switch")
    await asyncio.wait_for(call, timeout=2)
    assert asyncio.get_running_loop().time() - t0 < 2
    assert ch.frames("call_ended")[0]["reason"] == "kill_switch" and ch.closed_with == 1000
    ck = await db.get_doc(db.checkin_ref(INC, f"ck_{RID}_1"))
    assert ck["state"] == "FAILED" and ck["end_reason"] == "kill_switch"
    assert sessions.open_calls(INC) == 0


async def test_FR_16_hangup_before_speaking_is_no_answer_then_retry(fresh_db):
    out = await _ringing(fresh_db)
    ch = FakeChannel()
    ch.hang_up()
    assert await answer_call(out["token"], ch) == 1000
    ck = await db.get_doc(db.checkin_ref(INC, f"ck_{RID}_1"))
    assert ck["state"] == "NO_ANSWER" and ck["end_reason"] == "resident_hangup"
    await _wait_status({"RETRY_SCHEDULED"})
    worker.cancel_incident(INC)


async def test_AC_9_ring_timeout_moves_to_no_answer_then_retry(fresh_db):
    await _ringing(fresh_db)
    await jobs.ring_timeout_job({"incident_id": INC, "resident_id": RID, "attempt": 1})
    await _wait_status({"RETRY_SCHEDULED"})
    worker.cancel_incident(INC)


async def test_max_call_duration_ends_the_call(fresh_db, monkeypatch):
    monkeypatch.setattr(get_settings(), "LIVE_MAX_CALL_S", 0.5)
    out = await _ringing(fresh_db)
    ch = FakeChannel()
    assert await answer_call(out["token"], ch) == 1000
    assert ch.frames("call_ended")[0]["reason"] == "max_duration"
    worker.cancel_incident(INC)
