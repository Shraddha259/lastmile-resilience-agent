"""Voice check-in system instruction (PRD §13.3)."""

from __future__ import annotations

from typing import Any

from app.agent.prompts import load_prompt
from app.config import get_settings

LANGUAGE_NAMES = {
    "zh": "Mandarin",
    "ms": "Malay",
    "ta": "Tamil",
    "en": "English",
    "yue": "Cantonese",
}
# BCP-47 hints for the Live API speech config (§13.1).
BCP47 = {"zh": "zh-CN", "ms": "ms-MY", "ta": "ta-IN", "en": "en-US", "yue": "yue-HK"}

TEXT_MODE = (
    "This is a typed chat, not a phone call: reply in short written sentences and "
    "use the record_status and end_call fields of your JSON reply as the tools."
)


def render_voice_prompt(resident: dict[str, Any], incident: dict[str, Any], text_mode: bool) -> str:
    """Fill the §13.3 template from the resident, the incident and config."""
    s = get_settings()
    lang = resident.get("preferred_language", "en")
    dialect = resident.get("dialect_hint")
    hearing = "hearing_impaired" in (resident.get("medical_flags") or [])
    return load_prompt("voice_checkin.md").format(
        org_name=s.ORG_NAME,
        language_name=LANGUAGE_NAMES.get(lang, "English"),
        dialect_clause=f" (they may also speak {dialect}; understand it if you can)"
        if dialect
        else "",
        hearing_clause=(
            "They have hearing difficulty: speak extra slowly and repeat key points."
            if hearing
            else ""
        ),
        display_name=resident["display_name"],
        age=resident["age"],
        address_label=resident.get("address_label", "unknown"),
        official_facts_bulleted="\n".join(f"- {f}" for f in incident.get("official_facts", [])),
        emergency_number=s.EMERGENCY_NUMBER,
        mode_clause=TEXT_MODE if text_mode else "",
    )
