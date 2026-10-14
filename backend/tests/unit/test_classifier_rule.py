"""FR-18: the cautious final status rule (PRD §14.3)."""

from app.models import CaseStatus as S
from app.models import Classification
from app.services.classifier import final_status


def cls(status, **kw):
    return Classification(status=status, confidence=kw.pop("confidence", 0.9), **kw)


def test_FR_18_no_speech_is_no_answer():
    assert final_status(cls(S.SAFE_IN_PLACE), S.SAFE_IN_PLACE, resident_spoke=False) == (
        S.NO_ANSWER,
        False,
    )


def test_FR_18_more_cautious_wins():
    assert final_status(cls(S.SAFE_IN_PLACE), S.NEEDS_EVACUATION, True)[0] == S.NEEDS_EVACUATION
    assert final_status(cls(S.MEDICAL), S.NEEDS_HELP, True)[0] == S.MEDICAL


def test_FR_18_medical_flag_forces_medical():
    assert final_status(cls(S.NEEDS_HELP, medical_flag=True), S.NEEDS_HELP, True)[0] == S.MEDICAL


def test_FR_18_household_with_medical_need_is_medical():
    c = cls(S.NEEDS_HELP, household_others_at_risk=True, needs=["medication"])
    assert final_status(c, S.NEEDS_HELP, True)[0] == S.MEDICAL


def test_FR_18_disagreement_sets_review():
    final, review = final_status(cls(S.SAFE_IN_PLACE), S.NEEDS_HELP, True)
    assert final == S.NEEDS_HELP and review is True


def test_FR_18_agreement_keeps_review_flag_off():
    assert final_status(cls(S.SAFE_IN_PLACE), S.SAFE_IN_PLACE, True) == (S.SAFE_IN_PLACE, False)
