"""Simulated check-ins (PRD §15.1, FR-21).

`SIM_DIALOGUE_MODE=cached` (default, free tier) replays a pre-generated dialogue stored in
Firestore `dialogues/{rid}` (seeded from seed/dialogues.json). `single_call` and `turns`
generate the dialogue with Gemini (planned for M3; they fall back to cached for now).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.models import CaseStatus, CheckinState, EndReason
from app.services import db, worker
from app.util.ids import checkin_id
from app.util.logging import get_logger
from app.util.time import scaled, utcnow

log = get_logger(__name__)
NO_ANSWER_RING_S = 8
LINE_GAP_S = 1.5
FLUSH_EVERY = 3


@dataclass
class SimResult:
    answered: bool
    transcript: list[dict[str, Any]]
    live_status: CaseStatus | None
    fake_classification: dict[str, Any] | None
    stopped: bool = False


def answers(persona: dict[str, Any] | None, attempt: int) -> bool:
    """True if the persona picks up on this attempt."""
    first = (persona or {}).get("answers_on_attempt", 1)
    return first is not None and attempt >= first


async def run_simulated_call(
    inc: str, resident: dict[str, Any], attempt: int, scale: float
) -> SimResult:
    """Produce the transcript for one simulated attempt, writing lines as it goes."""
    rid = resident["resident_id"]
    ref = db.checkin_ref(inc, checkin_id(rid, attempt))
    if not answers(resident.get("persona"), attempt):
        await asyncio.sleep(scaled(NO_ANSWER_RING_S, scale))
        return SimResult(False, [], None, None)

    mode = get_settings().SIM_DIALOGUE_MODE
    if mode != "cached":
        log.warning(
            "SIM_DIALOGUE_MODE not implemented yet; using cached", extra={"resident_id": rid}
        )
    dialogue = await db.get_doc(db.get_db().collection("dialogues").document(rid))
    if not dialogue:
        log.warning("no cached dialogue", extra={"resident_id": rid})
        return SimResult(False, [], None, None)

    transcript: list[dict[str, Any]] = []
    started = utcnow()
    for i, line in enumerate(dialogue["lines"]):
        await asyncio.sleep(scaled(LINE_GAP_S, scale))
        if worker.is_stopped(inc):
            return SimResult(False, transcript, None, None, stopped=True)
        transcript.append({**line, "t": round((utcnow() - started).total_seconds(), 1)})
        if (i + 1) % FLUSH_EVERY == 0:
            await db.update_doc(ref, {"transcript": transcript})
    live = dialogue.get("live_status")
    return SimResult(
        True, transcript, CaseStatus(live) if live else None, dialogue.get("classification")
    )


async def write_checkin_start(
    inc: str, resident: dict[str, Any], attempt: int, channel: str, state: CheckinState
) -> None:
    """Create the check-in document for this attempt."""
    rid = resident["resident_id"]
    await db.set_doc(
        db.checkin_ref(inc, checkin_id(rid, attempt)),
        {
            "checkin_id": checkin_id(rid, attempt),
            "resident_id": rid,
            "attempt": attempt,
            "channel": channel,
            "language": resident["preferred_language"],
            "state": state.value,
            "started_at": utcnow(),
            "ended_at": None,
            "duration_s": None,
            "transcript": [],
            "live_status": None,
            "classification": None,
            "end_reason": None,
        },
    )


async def write_checkin_end(
    inc: str,
    rid: str,
    attempt: int,
    state: CheckinState,
    end_reason: EndReason | None,
    **fields: Any,
) -> None:
    """Finish the check-in document."""
    ref = db.checkin_ref(inc, checkin_id(rid, attempt))
    doc = await db.get_doc(ref) or {}
    now = utcnow()
    started = doc.get("started_at") or now
    await db.update_doc(
        ref,
        {
            "state": state.value,
            "ended_at": now,
            "duration_s": round((now - started).total_seconds(), 1),
            "end_reason": end_reason.value if end_reason else None,
            **fields,
        },
    )
