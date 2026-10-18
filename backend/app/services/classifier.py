"""Post-call classifier (PRD §14) and the deterministic final status rule (FR-18)."""

from __future__ import annotations

from typing import Any

from app.agent.prompts import load_prompt
from app.models import CaseStatus, Classification
from app.services import db, genai
from app.util.errors import UpstreamModelError
from app.util.logging import get_logger

log = get_logger(__name__)

SEVERITY = {
    CaseStatus.MEDICAL: 4,
    CaseStatus.NEEDS_EVACUATION: 3,
    CaseStatus.NEEDS_HELP: 2,
    CaseStatus.SAFE_IN_PLACE: 1,
}
MEDICAL_NEEDS = {"medication", "oxygen", "dialysis"}


def has_resident_speech(transcript: list[dict[str, Any]]) -> bool:
    """True if the resident said anything non-empty."""
    return any(t.get("role") == "resident" and t.get("text", "").strip() for t in transcript)


def render_transcript(transcript: list[dict[str, Any]]) -> str:
    lines = []
    for t in transcript:
        en = t.get("text_en")
        extra = f"  [EN: {en}]" if en and en != t.get("text") else ""
        lines.append(f"{t['role'].upper()}: {t['text']}{extra}")
    return "\n".join(lines)


async def classify(
    transcript: list[dict[str, Any]],
    live_status: CaseStatus | None,
    cached: dict[str, Any] | None = None,
    *,
    priority: bool = False,
) -> tuple[Classification, str]:
    """Run the classifier, retrying once.

    `cached` is the pre-computed classification for a simulated dialogue: it is the scripted
    output in fake mode, and the graceful fallback if the model is unavailable in real mode
    (labelled model="cached", D-025). Live calls pass None and use the §14.3 fallback.
    `priority` lets a live call's result skip the Gemini queue (D-047).
    """
    prompt = load_prompt("classifier_user.md").format(
        transcript=render_transcript(transcript), live_status=live_status or "none"
    )
    fake = cached if cached is not None else _fake_from_live(transcript, live_status)
    for _ in range(2):
        try:
            return await genai.generate_json(
                system=load_prompt("classifier.md"),
                prompt=prompt,
                schema=Classification,
                fake=fake,
                priority=priority,
            )
        except UpstreamModelError as exc:
            log.warning("classifier failed", extra={"error_code": exc.code})
    if cached is not None:
        db.STATS["classifier_cached"] += 1
        return Classification.model_validate(cached), "cached"
    status = live_status or CaseStatus.NEEDS_HELP
    return Classification(
        status=status,
        confidence=0.5,
        requires_human_review=True,
        review_reason="Classifier unavailable",
        summary_en="Classifier unavailable; needs review.",
    ), "fallback"


def _fake_from_live(
    transcript: list[dict[str, Any]], live_status: CaseStatus | None
) -> dict[str, Any] | None:
    """GENAI_MODE=fake only: agree with the live agent's record_status for live calls."""
    if live_status is None:
        return None
    said = " ".join(t["text"] for t in transcript if t.get("role") == "resident")
    return {
        "status": live_status.value,
        "confidence": 0.9,
        "medical_flag": live_status == CaseStatus.MEDICAL,
        "summary_en": f"Resident said: {said}"[:200],
    }


def final_status(
    cls: Classification, live_status: CaseStatus | None, resident_spoke: bool
) -> tuple[CaseStatus, bool]:
    """Apply the cautious final status rule (PRD §14.3). Returns (status, requires_review)."""
    if not resident_spoke:
        return CaseStatus.NO_ANSWER, False
    review = cls.requires_human_review
    candidates = [s for s in (cls.status, live_status) if s in SEVERITY]
    if not candidates:
        return CaseStatus.NO_ANSWER, review
    final = max(candidates, key=lambda s: SEVERITY[s])
    if cls.medical_flag or (cls.household_others_at_risk and MEDICAL_NEEDS & set(cls.needs)):
        final = CaseStatus.MEDICAL
    if live_status is not None and cls.status != live_status:
        review = True
    return final, review
