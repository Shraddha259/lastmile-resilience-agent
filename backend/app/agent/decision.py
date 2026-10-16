"""[P1] Structured-output decision engine (PRD §12.0, FR-14).

One Gemini call per event returns up to 3 tool calls as JSON. Code validates each one
(agent/validator.py) and runs it through the same tools the fallback policy uses. Any
failure stops the plan; the dispatcher then lets the deterministic fallback finish the case.
In GENAI_MODE=fake a scripted planner stands in for the model (tests, keyless dev).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from app.agent import tools, validator
from app.agent.prompts import load_prompt
from app.config import get_settings
from app.models import Actor, CaseStatus
from app.services import db, genai, shelters, volunteers
from app.util.logging import get_logger
from app.util.time import utcnow

log = get_logger(__name__)
MAX_ACTIONS = 3

ToolName = Literal[
    "confirm_safe",
    "schedule_retry",
    "contact_next_of_kin",
    "reserve_shelter",
    "dispatch_volunteer",
    "escalate_to_human",
    "add_note",
]


class ActionArgs(BaseModel):
    """Union of all tool arguments; each tool uses only the ones it needs."""

    resident_id: str
    reason: str | None = None
    shelter_id: str | None = None
    volunteer_id: str | None = None
    task_type: Literal["ESCORT_TO_SHELTER", "ASSIST_IN_PLACE", "WELFARE_CHECK"] | None = None
    urgency: Literal["NORMAL", "HIGH", "CRITICAL"] | None = None
    briefing_en: str | None = None
    message_en: str | None = None
    note: str | None = None


class ProposedAction(BaseModel):
    tool: ToolName
    args: ActionArgs


class Decision(BaseModel):
    """Response schema for the orchestrator call (PRD §12.0)."""

    actions: list[ProposedAction] = []
    overall_reason: str = ""


@dataclass
class DecisionOutcome:
    model: str
    proposed: int
    executed: int
    rejected: int
    latency_ms: int


# ------------------------------------------------------------------ context
_PROFILE_KEYS = (
    "resident_id",
    "display_name",
    "age",
    "languages",
    "dialect_hint",
    "preferred_language",
    "address_label",
    "floor",
    "lives_alone",
    "mobility",
    "medical_flags",
)
_CASE_KEYS = (
    "status",
    "attempts",
    "priority",
    "risk_score",
    "risk_reasons",
    "needs",
    "human_review",
    "last_summary_en",
    "assigned_shelter_id",
)


async def build_context(
    inc: str, case: dict[str, Any], resident: dict[str, Any], tool_names: list[str]
) -> dict[str, Any]:
    """Compact, read-only CONTEXT for one decision (PRD §12.6 step 6)."""
    incident = await db.get_doc(db.incident_ref(inc)) or {}
    cls = await tools.latest_classification(inc, case)
    ctx: dict[str, Any] = {
        "resident": {k: resident.get(k) for k in _PROFILE_KEYS},
        "next_of_kin_relation": (resident.get("next_of_kin") or {}).get("relation"),
        "case": {k: case.get(k) for k in _CASE_KEYS},
        "classification": cls,
        "max_attempts": get_settings().MAX_ATTEMPTS,
        "auto_approve_dispatch": bool(incident.get("auto_approve_dispatch")),
        "candidate_shelters": [],
        "available_volunteers": [],
    }
    if "reserve_shelter" in tool_names:
        ctx["candidate_shelters"] = await shelters.find_shelters(resident, case.get("needs", []))
    if case.get("assigned_shelter_id"):
        sh = await db.get_doc(db.shelter_ref(case["assigned_shelter_id"])) or {}
        ctx["assigned_shelter"] = {"shelter_id": sh.get("shelter_id"), "name": sh.get("name")}
    if "dispatch_volunteer" in tool_names:
        ctx["available_volunteers"] = volunteers.rank_volunteers(
            resident, await db.list_volunteers()
        )
    return ctx


def render_user_message(event: dict[str, Any], ctx: dict[str, Any], tool_names: list[str]) -> str:
    """The §12.2 user template."""
    details = {k: v for k, v in event.items() if k != "type"}
    return load_prompt("orchestrator_user.md").format(
        event_type=event["type"],
        event_json=json.dumps(details, default=str),
        context_json=json.dumps(ctx, default=str, ensure_ascii=False),
        allowed_tool_names=", ".join(tool_names),
    )


# ------------------------------------------------------------------ fake planner
def fake_decision(ctx: dict[str, Any]) -> dict[str, Any]:
    """Deterministic stand-in for the model in GENAI_MODE=fake (mirrors §12.2 rule 2)."""
    s = get_settings()
    case, res = ctx["case"], ctx["resident"]
    rid, status = res["resident_id"], CaseStatus(case["status"])
    cls = ctx.get("classification") or {}
    vid = None  # let dispatch_volunteer auto-pick from the ranked list (§15.3)
    langs = "/".join(res.get("languages") or [])

    def act(tool: str, **args: Any) -> dict[str, Any]:
        return {"tool": tool, "args": {"resident_id": rid, **args}}

    def brief(task: str, where: str) -> str:
        who = f"{res['display_name']}, {res['age']}, {res['mobility']}, speaks {langs}."
        return f"{who} {task} {where}."

    actions: list[dict[str, Any]] = []
    if status == CaseStatus.SAFE_IN_PLACE:
        confident = (
            cls.get("confidence", 0) >= s.SAFE_CONFIDENCE_MIN
            and not cls.get("requires_human_review")
            and not case.get("human_review")
        )
        actions = (
            [act("confirm_safe", reason="Resident clearly confirmed they are safe.")]
            if confident
            else [
                act(
                    "escalate_to_human",
                    urgency="HIGH",
                    reason="Safe-in-place answer is uncertain; a person should check.",
                )
            ]
        )
    elif status == CaseStatus.NO_ANSWER:
        if case.get("attempts", 0) < ctx["max_attempts"]:
            actions = [act("schedule_retry", reason="No answer yet; try again shortly.")]
        else:
            actions = [
                act(
                    "contact_next_of_kin",
                    reason="All call attempts failed.",
                    message_en=f"We could not reach {res['display_name']} about the flood "
                    "warning. Please check on them if you can.",
                ),
                act(
                    "dispatch_volunteer",
                    task_type="WELFARE_CHECK",
                    urgency="HIGH",
                    volunteer_id=vid,
                    reason="Nobody has reached the resident; send a welfare check.",
                    briefing_en=brief("Welfare check at", res.get("address_label", "home")),
                ),
            ]
    elif status == CaseStatus.NEEDS_EVACUATION:
        cands = ctx.get("candidate_shelters") or []
        if not cands:
            actions = [
                act(
                    "escalate_to_human",
                    urgency="CRITICAL",
                    reason="Needs evacuation but no suitable shelter has space.",
                )
            ]
        else:
            sh = cands[0]
            actions = [
                act(
                    "reserve_shelter",
                    shelter_id=sh["shelter_id"],
                    reason=f"{sh['name']} fits: {', '.join(sh['fit_reasons'])}.",
                ),
                act(
                    "dispatch_volunteer",
                    task_type="ESCORT_TO_SHELTER",
                    urgency="HIGH",
                    volunteer_id=vid,
                    reason="Resident needs an escort to the shelter.",
                    briefing_en=brief("Escort to", sh["name"]),
                ),
            ]
    elif status in (
        CaseStatus.SHELTER_RESERVED,
        CaseStatus.NEEDS_HELP,
        CaseStatus.NEXT_OF_KIN_CONTACTED,
    ):
        ttype = {
            CaseStatus.SHELTER_RESERVED: "ESCORT_TO_SHELTER",
            CaseStatus.NEEDS_HELP: "ASSIST_IN_PLACE",
            CaseStatus.NEXT_OF_KIN_CONTACTED: "WELFARE_CHECK",
        }[status]
        where = (ctx.get("assigned_shelter") or {}).get("name") or res.get("address_label", "home")
        actions = [
            act(
                "dispatch_volunteer",
                task_type=ttype,
                urgency="NORMAL" if ttype == "ASSIST_IN_PLACE" else "HIGH",
                volunteer_id=vid,
                reason="Send the closest volunteer who shares a language.",
                briefing_en=brief(ttype.replace("_", " ").capitalize() + ":", where),
            )
        ]
    return {"actions": actions, "overall_reason": f"Scripted plan for {status.value}."}


# ------------------------------------------------------------------ engine
async def _audit(
    inc: str,
    rid: str,
    *,
    result: str,
    reason: str,
    summary: str,
    model: str,
    latency_ms: int,
    tool: str | None = None,
) -> None:
    await db.set_doc(
        db.events_col(inc).document(),
        {
            "ts": utcnow(),
            "actor": Actor.agent.value,
            "event_type": "AGENT_DECISION",
            "resident_id": rid,
            "tool": tool,
            "args_summary": summary[:300],
            "result": result,
            "reason": reason[:300],
            "model": model,
            "latency_ms": latency_ms,
            "fallback_used": False,
        },
    )


async def run_decision(
    inc: str, event: dict[str, Any], case: dict[str, Any]
) -> DecisionOutcome | None:
    """Ask the model for a plan, validate and execute it. Never raises tool errors.

    Raises UpstreamModelError if the model is unavailable (the dispatcher falls back).
    """
    rid = case["resident_id"]
    resident = await db.get_doc(db.resident_ref(rid))
    status = CaseStatus(case["status"])
    tool_names = validator.planning_tools(status, case.get("attempts", 0))
    if not resident or not tool_names:
        return None
    ctx = await build_context(inc, case, resident, tool_names)

    started = time.monotonic()
    decision, model = await genai.generate_json(
        system=load_prompt("orchestrator.md"),
        prompt=render_user_message(event, ctx, tool_names),
        schema=Decision,
        fake=fake_decision(ctx),
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    db.STATS["decisions"] += 1

    proposed = decision.actions[:MAX_ACTIONS]
    executed = rejected = 0
    for action in proposed:
        current = await db.get_doc(db.case_ref(inc, rid))
        if not current:
            break
        shelter_ids = {c["shelter_id"] for c in ctx["candidate_shelters"]}
        volunteer_ids = {v["volunteer_id"] for v in ctx["available_volunteers"]}
        check = validator.validate(
            action.tool,
            action.args.model_dump(),
            event_resident_id=rid,
            case=current,
            candidate_shelter_ids=shelter_ids,
            top_volunteer_ids=volunteer_ids,
        )
        if not check.ok:
            rejected += 1
            await _audit(
                inc,
                rid,
                result="rejected",
                tool=action.tool,
                model=model,
                latency_ms=latency_ms,
                reason=check.message,
                summary=f"Validator blocked {action.tool}: {check.error}",
            )
            break
        res = await tools.TOOLS[action.tool](
            **check.args, actor=Actor.agent, model=model, latency_ms=latency_ms
        )
        if not res.get("ok"):
            rejected += 1
            await _audit(
                inc,
                rid,
                result="failed",
                tool=action.tool,
                model=model,
                latency_ms=latency_ms,
                reason=res.get("message", ""),
                summary=f"{action.tool} failed: {res.get('error')}",
            )
            break
        executed += 1

    names = ", ".join(a.tool for a in proposed) or "no action"
    await _audit(
        inc,
        rid,
        result="ok" if not rejected else "partial",
        model=model,
        latency_ms=latency_ms,
        reason=decision.overall_reason or "(no reason given)",
        summary=f"Plan: {names} ({executed}/{len(proposed)} executed)",
    )
    return DecisionOutcome(model, len(proposed), executed, rejected, latency_ms)
