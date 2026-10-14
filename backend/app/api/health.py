"""API-1 health check."""

import asyncio

from fastapi import APIRouter

from app.config import get_settings
from app.services import db

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Report status, version, configured model IDs and Firestore reachability."""
    s = get_settings()
    try:
        await asyncio.wait_for(db.get_db().collection("scenarios").limit(1).get(), timeout=3)
        firestore_ok = True
    except Exception:  # noqa: BLE001 - health must not raise
        firestore_ok = False
    return {
        "status": "ok",
        "version": s.VERSION,
        "phase": s.PHASE,
        "genai_mode": s.GENAI_MODE,
        "models": {
            "agent": s.GEMINI_AGENT_MODEL,
            "fallback": s.GEMINI_FALLBACK_MODEL,
            "live": s.GEMINI_LIVE_MODEL,
            "tts": s.GEMINI_TTS_MODEL,
        },
        "firestore": firestore_ok,
    }
