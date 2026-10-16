"""Real-Gemini smoke tests (PRD §20.2 `@pytest.mark.live`). Skipped unless RUN_LIVE=1.

    cd backend && RUN_LIVE=1 GEMINI_API_KEY=... uv run pytest tests/live -m live -s
Uses ~2 requests. Checks that Gemini accepts our response schemas and returns sane output.
"""

import os

import pytest

from app.agent.decision import Decision
from app.agent.prompts import load_prompt
from app.config import get_settings
from app.models import CaseStatus, Classification
from app.services import genai

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to call Gemini"),
]


@pytest.fixture(autouse=True)
def real_mode(monkeypatch):
    monkeypatch.setattr(get_settings(), "GENAI_MODE", "real")


async def test_live_classifier_schema_and_medical_case():
    transcript = (
        "AGENT: Hello, I am an automated assistant. Are you safe?\n"
        "RESIDENT: I'm okay but my husband fell in the kitchen and cannot get up."
    )
    cls, model = await genai.generate_json(
        system=load_prompt("classifier.md"),
        prompt=load_prompt("classifier_user.md").format(transcript=transcript, live_status="none"),
        schema=Classification,
    )
    print(f"\n{model}: {cls.status} {cls.confidence:.2f} {cls.summary_en}")
    assert cls.status == CaseStatus.MEDICAL or cls.medical_flag


async def test_live_decision_schema():
    prompt = load_prompt("orchestrator_user.md").format(
        event_type="CHECKIN_COMPLETED",
        event_json="{}",
        context_json='{"resident": {"resident_id": "R-010", "display_name": "Test", "age": 80},'
        ' "case": {"status": "SAFE_IN_PLACE", "attempts": 1},'
        ' "classification": {"status": "SAFE_IN_PLACE", "confidence": 0.95,'
        ' "requires_human_review": false}}',
        allowed_tool_names="confirm_safe, escalate_to_human, add_note",
    )
    dec, model = await genai.generate_json(
        system=load_prompt("orchestrator.md"), prompt=prompt, schema=Decision
    )
    print(f"\n{model}: {[a.tool for a in dec.actions]} — {dec.overall_reason}")
    assert dec.actions and dec.actions[0].tool in ("confirm_safe", "escalate_to_human")
    assert dec.actions[0].args.resident_id == "R-010"
