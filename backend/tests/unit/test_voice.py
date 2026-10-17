"""Voice prompt (PRD §13.3), live tools (§13.4) and the scripted text caller."""

from app.models import CaseStatus
from app.voice import live_tools
from app.voice.live_bridge import fake_text_turn
from app.voice.live_tools import CallState
from app.voice.prompt import render_voice_prompt

INCIDENT = {"official_facts": ["Water may rise 1 m by 18:00.", "Shelters S-1 and S-3 are open."]}


def _res(**over):
    return {
        "resident_id": "R-001",
        "display_name": "Mdm Tan Ah Lian",
        "age": 82,
        "preferred_language": "zh",
        "dialect_hint": "Hokkien",
        "address_label": "Blk 12",
        "medical_flags": [],
        **over,
    }


def test_NFR_S10_prompt_discloses_automation_and_uses_language_and_facts():
    p = render_voice_prompt(_res(), INCIDENT, text_mode=False)
    assert "You are an automated assistant; say so in your first sentence." in p
    assert "Speak ONLY in Mandarin (they may also speak Hokkien" in p
    assert "- Water may rise 1 m by 18:00." in p and "Mdm Tan Ah Lian, age 82" in p
    assert "typed chat" not in p


def test_prompt_hearing_and_text_clauses():
    p = render_voice_prompt(
        _res(medical_flags=["hearing_impaired"], dialect_hint=None), INCIDENT, text_mode=True
    )
    assert "hearing difficulty" in p and "typed chat" in p and "Hokkien" not in p


def test_record_status_validates_and_filters_needs():
    st = CallState("inc", "R-001", 1)
    res = live_tools.apply_record_status(
        st,
        {
            "status": "NEEDS_EVACUATION",
            "needs": ["walking_aid", "unicorn"],
            "summary_en": "x" * 300,
            "needs_human": False,
        },
    )
    assert res["ok"] and st.live_status == CaseStatus.NEEDS_EVACUATION
    assert st.needs == ["walking_aid"] and len(st.summary_en) == 200
    bad = live_tools.apply_record_status(st, {"status": "CONFIRMED_SAFE"})
    assert not bad["ok"] and st.live_status == CaseStatus.NEEDS_EVACUATION


def test_fake_caller_maps_answers_to_statuses():
    st, r = CallState("inc", "R-001", 1), _res()
    assert "automated assistant" in fake_text_turn(st, r, None)["say"]
    cases = {
        "my chest hurts": "MEDICAL",
        "water is coming in": "NEEDS_EVACUATION",
        "please help me carry rice upstairs": "NEEDS_HELP",
        "I'm fine upstairs": "SAFE_IN_PLACE",
    }
    for text, want in cases.items():
        assert fake_text_turn(st, r, text)["record_status"]["status"] == want, text
