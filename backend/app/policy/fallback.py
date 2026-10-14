"""Deterministic fallback policy (PRD §12.5, FR-13). Completes any case with no LLM."""

from __future__ import annotations

from typing import Any

from app.agent import tools
from app.config import get_settings
from app.models import Actor, CaseStatus, TaskType
from app.services import db

P = Actor.policy
LANG_NAMES = {"zh": "Mandarin", "ms": "Malay", "ta": "Tamil", "en": "English", "yue": "Cantonese"}


def template_briefing(
    resident: dict[str, Any], task_type: TaskType, shelter_name: str | None = None
) -> str:
    """`{name}, {age}, {mobility}, speaks {languages}. Task: {task_type} to {where}.`"""
    langs = "/".join(LANG_NAMES.get(lang, lang) for lang in resident.get("languages", []))
    if resident.get("dialect_hint"):
        langs += f" ({resident['dialect_hint']})"
    where = shelter_name or resident.get("address_label", "home")
    task = task_type.value.replace("_", " ").lower()
    return (
        f"{resident['display_name']}, {resident['age']}, {resident['mobility']}, "
        f"speaks {langs}. Task: {task} to {where}."
    )


async def _dispatch_or_escalate(
    rid: str, resident: dict, ttype: TaskType, urgency: str, shelter_name: str | None = None
) -> dict:
    res = await tools.dispatch_volunteer(
        rid,
        ttype.value,
        urgency,
        template_briefing(resident, ttype, shelter_name),
        f"Policy: {ttype.value.replace('_', ' ').lower()} needed",
        actor=P,
    )
    if not res["ok"] and res.get("error") == "NO_VOLUNTEER":
        return await tools.escalate_to_human(rid, "HIGH", "No volunteer available", actor=P)
    return res


async def apply_step(inc: str, rid: str) -> dict:
    """Apply one fallback action for the case's current status. Returns the tool result."""
    case = await db.get_doc(db.case_ref(inc, rid))
    resident = await db.get_doc(db.resident_ref(rid))
    status = CaseStatus(case["status"])
    s = get_settings()

    if status == CaseStatus.SAFE_IN_PLACE:
        cls = await tools.latest_classification(inc, case) or {}
        ok = (
            cls.get("confidence", 0) >= s.SAFE_CONFIDENCE_MIN
            and not cls.get("requires_human_review")
            and not case.get("human_review")
        )
        if ok:
            return await tools.confirm_safe(rid, "Policy: confident safe-in-place answer", actor=P)
        why = cls.get("review_reason") or "Low confidence or review flagged"
        return await tools.escalate_to_human(rid, "HIGH", f"Policy: {why}", actor=P)

    if status == CaseStatus.MEDICAL:
        return await tools.escalate_to_human(rid, "CRITICAL", "Policy: medical concern", actor=P)

    if status == CaseStatus.NEEDS_EVACUATION:
        found = await tools.find_shelters(rid, actor=P)
        for cand in found.get("candidates", []):
            res = await tools.reserve_shelter(
                rid,
                cand["shelter_id"],
                f"Policy: best fit ({', '.join(cand['fit_reasons'])})",
                actor=P,
            )
            if res["ok"] or res.get("error") != "SHELTER_FULL":
                return res
        return await tools.escalate_to_human(
            rid, "CRITICAL", "Policy: no suitable shelter", actor=P
        )

    if status == CaseStatus.SHELTER_RESERVED:
        shelter = await db.get_doc(db.shelter_ref(case["assigned_shelter_id"])) or {}
        return await _dispatch_or_escalate(
            rid, resident, TaskType.ESCORT_TO_SHELTER, "HIGH", shelter.get("name")
        )

    if status == CaseStatus.NEEDS_HELP:
        return await _dispatch_or_escalate(rid, resident, TaskType.ASSIST_IN_PLACE, "NORMAL")

    if status == CaseStatus.NO_ANSWER:
        if case.get("attempts", 0) < s.MAX_ATTEMPTS:
            return await tools.schedule_retry(rid, "Policy: no answer, retrying", actor=P)
        msg = (
            f"We could not reach {resident['display_name']} about the flood warning. "
            "Please check on them if you can."
        )
        return await tools.contact_next_of_kin(rid, msg, "Policy: all attempts failed", actor=P)

    if status == CaseStatus.NEXT_OF_KIN_CONTACTED:
        return await _dispatch_or_escalate(rid, resident, TaskType.WELFARE_CHECK, "HIGH")

    return {"ok": True, "noop": True}
