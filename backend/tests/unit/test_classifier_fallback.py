"""Classifier degradation when the model is unavailable (PRD §14.3, D-025)."""

from app.config import get_settings
from app.models import CaseStatus
from app.services import classifier, genai
from app.util.errors import UpstreamModelError

TRANSCRIPT = [{"role": "agent", "text": "Are you safe?"}, {"role": "resident", "text": "Yes."}]
CACHED = {"status": "SAFE_IN_PLACE", "confidence": 0.92, "summary_en": "Safe at home."}


async def _unavailable(**_):
    raise UpstreamModelError("quota")


async def test_cached_classification_used_when_model_unavailable(monkeypatch):
    monkeypatch.setattr(get_settings(), "GENAI_MODE", "real")
    monkeypatch.setattr(genai, "generate_json", _unavailable)
    cls, model = await classifier.classify(TRANSCRIPT, CaseStatus.SAFE_IN_PLACE, cached=CACHED)
    assert model == "cached" and cls.status == CaseStatus.SAFE_IN_PLACE and cls.confidence == 0.92


async def test_live_call_without_cache_needs_review(monkeypatch):
    monkeypatch.setattr(get_settings(), "GENAI_MODE", "real")
    monkeypatch.setattr(genai, "generate_json", _unavailable)
    cls, model = await classifier.classify(TRANSCRIPT, CaseStatus.SAFE_IN_PLACE, cached=None)
    assert model == "fallback" and cls.requires_human_review and cls.confidence == 0.5


async def test_fake_mode_live_call_agrees_with_recorded_status():
    cls, model = await classifier.classify(TRANSCRIPT, CaseStatus.SAFE_IN_PLACE, cached=None)
    assert model == "fake" and cls.status == CaseStatus.SAFE_IN_PLACE and cls.confidence == 0.9
