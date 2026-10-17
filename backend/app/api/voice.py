"""Live check-in endpoints: API-8 voice sessions and the voice WebSocket (PRD §11.2-11.3)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, WebSocket
from pydantic import BaseModel

from app.config import get_settings
from app.models import Actor, CaseStatus, CheckinState
from app.policy.state_machine import transition_case
from app.services import db
from app.util.auth import require_passcode
from app.util.errors import AppError
from app.util.ids import checkin_id
from app.util.logging import get_logger
from app.util.time import utcnow
from app.voice import live_bridge, sessions

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["voice"], dependencies=[Depends(require_passcode)])
ws_router = APIRouter(tags=["voice"])

# WebSocket close codes (§11.3).
WS_UNAUTHORIZED, WS_FORBIDDEN, WS_CONFLICT = 4401, 4403, 4409


class VoiceSessionRequest(BaseModel):
    incident_id: str
    resident_id: str


@router.post("/voice/sessions", status_code=201)
async def create_voice_session(body: VoiceSessionRequest) -> dict[str, Any]:
    """API-8: one-time token (10 min) to answer a RINGING live resident's call."""
    out = await sessions.create_session(body.incident_id, body.resident_id)
    path = f"/ws/voice?token={out['token']}"
    base = (
        (get_settings().SERVICE_URL or "").replace("https://", "wss://").replace("http://", "ws://")
    )
    return {
        "token": out["token"],
        "ws_url": f"{base}{path}" if base else path,
        "ws_path": path,
        "expires_at": out["expires_at"],
        "mode": live_bridge.effective_mode(),
    }


class StarletteChannel:
    """Adapts a Starlette WebSocket to the bridge's Channel protocol."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.closed = False

    async def receive(self) -> dict[str, Any]:
        if self.closed:
            return {"disconnect": True}
        msg = await self.ws.receive()
        if msg["type"] == "websocket.disconnect":
            self.closed = True
            return {"disconnect": True}
        return {"bytes": msg.get("bytes"), "text": msg.get("text")}

    async def send_json(self, data: dict[str, Any]) -> None:
        if not self.closed:
            await self.ws.send_json(data)

    async def send_bytes(self, data: bytes) -> None:
        if not self.closed:
            await self.ws.send_bytes(data)

    async def close(self, code: int = 1000) -> None:
        if not self.closed:
            self.closed = True
            await self.ws.close(code)


async def answer_call(token: str, ch: live_bridge.Channel) -> int:
    """Validate the token, move RINGING -> CONTACTING and run the call.

    Returns a WebSocket close code: 1000 after a call, 4401/4409 if it couldn't start.
    """
    data = await sessions.claim_token(token) if token else None
    if not data:
        return WS_UNAUTHORIZED
    inc, rid, attempt = data["incident_id"], data["resident_id"], data["attempt"]
    incident = await db.get_doc(db.incident_ref(inc))
    resident = await db.get_doc(db.resident_ref(rid))
    case = await db.get_doc(db.case_ref(inc, rid))
    if (
        not (incident and resident and case)
        or case["status"] != CaseStatus.RINGING
        or case.get("attempts") != attempt
    ):
        return WS_UNAUTHORIZED
    try:
        await transition_case(
            inc,
            rid,
            CaseStatus.CONTACTING,
            Actor.system,
            "Live call answered",
            expected_version=case["version"],
        )
    except AppError:
        return WS_CONFLICT
    await db.update_doc(
        db.checkin_ref(inc, checkin_id(rid, attempt)),
        {"state": CheckinState.IN_PROGRESS.value, "started_at": utcnow()},
    )

    handle = sessions.CallHandle(inc)
    sessions.register(handle)
    try:
        await live_bridge.run_call(
            ch,
            incident=incident,
            resident=resident,
            attempt=attempt,
            handle=handle,
            mode=live_bridge.effective_mode(),
        )
    except Exception:  # noqa: BLE001 - never leave the case stuck in CONTACTING
        log.exception("live call crashed", extra={"incident_id": inc, "resident_id": rid})
        from app.services.jobs import recover_contacting_job

        await recover_contacting_job({"incident_id": inc, "resident_id": rid, "attempt": attempt})
    finally:
        sessions.unregister(handle)
    return 1000


@ws_router.websocket("/ws/voice")
async def voice_ws(websocket: WebSocket, token: str = "") -> None:
    """WS /ws/voice?token=... (FR-15). One call per token."""
    if websocket.headers.get("origin") not in get_settings().allowed_origins:  # NFR-S9
        await websocket.close(code=WS_FORBIDDEN)
        return
    await websocket.accept()
    ch = StarletteChannel(websocket)
    code = await answer_call(token, ch)
    if code != 1000:
        await ch.close(code)
