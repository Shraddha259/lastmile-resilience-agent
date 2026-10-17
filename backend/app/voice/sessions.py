"""Voice session tokens (PRD §11.2 API-8, §11.3) and the registry of open calls (FR-30)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import timedelta
from typing import Any

from google.cloud import firestore

from app.models import CaseStatus, IncidentStatus
from app.services import db, scenario
from app.util.errors import AppError, IncidentNotActive, NotFound
from app.util.ids import voice_token
from app.util.time import utcnow

TOKEN_TTL = timedelta(minutes=10)


class NotRinging(AppError):
    status_code, code = 409, "NOT_RINGING"


def _ref(token: str):
    return db.get_db().collection("voice_sessions").document(token)


async def create_session(incident_id: str, resident_id: str) -> dict[str, Any]:
    """API-8: one-time token for a live resident whose case is RINGING."""
    incident = await db.get_doc(db.incident_ref(incident_id))
    resident = await db.get_doc(db.resident_ref(resident_id))
    case = await db.get_doc(db.case_ref(incident_id, resident_id))
    if not incident or not resident or not case:
        raise NotFound("Incident or resident not found")
    if incident.get("status") != IncidentStatus.ACTIVE:
        raise IncidentNotActive("Incident is not active")
    if not resident.get("is_live_demo"):
        raise NotRinging(f"{resident_id} is not a live demo resident")
    if case["status"] != CaseStatus.RINGING:
        raise NotRinging(f"{resident_id} is not ringing (status {case['status']})")
    token, expires = voice_token(), utcnow() + TOKEN_TTL
    await db.set_doc(
        _ref(token),
        {
            "incident_id": incident_id,
            "resident_id": resident_id,
            "attempt": case["attempts"],
            "expires_at": expires,
            "used": False,
        },
    )
    return {"token": token, "expires_at": expires}


async def claim_token(token: str) -> dict[str, Any] | None:
    """Mark a token used exactly once. Returns its data, or None if invalid/used/expired."""
    ref = _ref(token)
    tx = db.transaction()

    @firestore.async_transactional
    async def _run(t) -> dict[str, Any] | None:
        snap = await ref.get(transaction=t)
        data = snap.to_dict() if snap.exists else None
        if not data or data.get("used") or data["expires_at"] < utcnow():
            return None
        t.update(ref, {"used": True, "used_at": utcnow()})
        db.count_writes()
        return data

    return await _run(tx)


# ------------------------------------------------------------------ open calls
class CallHandle:
    """Lets the kill switch end a running call from outside its task."""

    def __init__(self, incident_id: str) -> None:
        self.incident_id = incident_id
        self.stop_reason: str | None = None
        self.stopped = asyncio.Event()

    def stop(self, reason: str) -> None:
        self.stop_reason = reason
        self.stopped.set()


_open: dict[str, set[CallHandle]] = defaultdict(set)


def register(handle: CallHandle) -> None:
    _open[handle.incident_id].add(handle)


def unregister(handle: CallHandle) -> None:
    _open[handle.incident_id].discard(handle)


def open_calls(incident_id: str) -> int:
    return len(_open.get(incident_id, ()))


async def stop_incident_calls(incident_id: str) -> None:
    """Kill-switch hook (AC-5): signal every open call for the incident to end now."""
    for handle in list(_open.get(incident_id, ())):
        handle.stop("kill_switch")


# Kill switch closes live calls (FR-30, AC-5). Registered here so it is active wherever
# calls can exist, not only when the FastAPI app module is imported.
scenario.on_stop(stop_incident_calls)
