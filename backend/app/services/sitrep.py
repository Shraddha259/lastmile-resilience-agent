"""Grounded situation report (PRD §15.5, FR-25). [P1] generated on demand (API-7).

The model sees only a JSON snapshot of real system data. Code then checks that every
resident / shelter / volunteer ID it mentions is in the snapshot; if not (or if the model
is unavailable) a deterministic template report is stored instead.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from pydantic import BaseModel

from app.agent.prompts import load_prompt
from app.models import OPEN_TASK_STATUSES, CaseStatus, TaskStatus
from app.services import db, genai, worker
from app.util.errors import UpstreamModelError
from app.util.logging import get_logger
from app.util.time import utcnow

log = get_logger(__name__)
_IDS = re.compile(r"\b(?:R-\d{3}|S-\d+|V-\d+)\b")
MAX_CHARS = 1200


class Sitrep(BaseModel):
    summary_en: str


async def build_snapshot(inc: str) -> dict[str, Any]:
    """Counters, escalations, open tasks and resources: the only facts the report may use."""
    incident = await db.get_doc(db.incident_ref(inc)) or {}
    cases = await db.list_cases(inc)
    tasks = await db.list_docs(db.incident_ref(inc).collection("tasks"))
    shelters = await db.list_shelters()
    vols = await db.list_volunteers()
    escalated = [
        {
            "resident_id": c["resident_id"],
            "priority": c.get("priority"),
            "summary": c.get("last_summary_en") or "",
        }
        for c in cases
        if c["status"] == CaseStatus.ESCALATED
    ]
    open_tasks = [
        {
            "task_id": t["task_id"],
            "type": t["type"],
            "resident_id": t["resident_id"],
            "urgency": t["urgency"],
            "status": t["status"],
            "volunteer_id": t.get("volunteer_id"),
            "reason": t.get("briefing_en", "")[:120],
        }
        for t in tasks
        if TaskStatus(t["status"]) in OPEN_TASK_STATUSES
    ]
    return {
        "counters": incident.get("counters", {}),
        "by_status": dict(Counter(c["status"] for c in cases)),
        "escalated": sorted(escalated, key=lambda e: e["resident_id"]),
        "open_tasks": sorted(open_tasks, key=lambda t: (t["urgency"] != "CRITICAL", t["task_id"])),
        "shelters": [
            {
                "shelter_id": s["shelter_id"],
                "name": s["name"],
                "occupied": s["occupied"],
                "capacity": s["capacity"],
            }
            for s in shelters
        ],
        "volunteers": {
            "available": sum(1 for v in vols if v.get("available")),
            "busy": sum(1 for v in vols if not v.get("available")),
        },
        "grounded_on_version": sum(c.get("version", 0) for c in cases),
    }


def template_report(snap: dict[str, Any]) -> str:
    """Rule-based report used in fake mode and whenever the model output can't be trusted."""
    c = snap["counters"]
    urgent = [e["resident_id"] for e in snap["escalated"]]
    reviews = [t for t in snap["open_tasks"] if t["type"] == "HUMAN_REVIEW"]
    approvals = [
        t
        for t in snap["open_tasks"]
        if t["status"] == "PENDING_APPROVAL" and t["type"] != "HUMAN_REVIEW"
    ]
    shelters = ", ".join(
        f"{s['shelter_id']} {s['occupied']}/{s['capacity']}" for s in snap["shelters"]
    )
    v = snap["volunteers"]
    focus = []
    if reviews:
        focus.append(f"review {len(reviews)} escalation(s)")
    if approvals:
        focus.append(f"approve or reject {len(approvals)} dispatch(es)")
    if c.get("in_progress"):
        focus.append(f"watch {c['in_progress']} case(s) still in progress")
    return (
        f"Status: {c.get('confirmed_safe', 0)}/{c.get('total', 0)} confirmed safe, "
        f"{c.get('escalated', 0)} escalated, {c.get('in_progress', 0)} in progress. "
        f"Urgent: {', '.join(urgent) if urgent else 'none'}. "
        f"Resources: shelters {shelters}; {v['available']} volunteers available, {v['busy']} busy. "
        f"Next 10 minutes: {'; '.join(focus) if focus else 'no action needed'}."
    )


def grounded(text: str, snap: dict[str, Any]) -> bool:
    """True if every ID the report mentions appears in the snapshot (SM-4: no invented facts)."""
    known = set(_IDS.findall(json.dumps(snap)))
    return set(_IDS.findall(text)) <= known


async def generate(inc: str) -> dict[str, Any]:
    """Build a snapshot, ask the model, verify grounding, store the report."""
    snap = await build_snapshot(inc)
    fallback = template_report(snap)
    model = "template"
    try:
        out, model = await genai.generate_json(
            system=load_prompt("sitrep.md"),
            prompt=json.dumps(snap, ensure_ascii=False),
            schema=Sitrep,
            fake={"summary_en": fallback},
        )
        text = out.summary_en.strip()[:MAX_CHARS]
        if not text or not grounded(text, snap):
            log.warning("sitrep not grounded; using template", extra={"incident_id": inc})
            text, model = fallback, "template"
    except UpstreamModelError:
        text = fallback
    doc = {
        "ts": utcnow(),
        "summary_en": text,
        "counts": snap["counters"],
        "model": model,
        "grounded_on_version": snap["grounded_on_version"],
    }
    await db.set_doc(db.incident_ref(inc).collection("sitreps").document(), doc)
    return doc


@worker.job("sitrep")
async def sitrep_job(payload: dict[str, Any]) -> None:
    """API-7 runs this in the background so the request returns 202 at once."""
    await generate(payload["incident_id"])


def request(inc: str) -> bool:
    """Queue a report; at most one per incident every 10 s (cost guard)."""
    bucket = int(utcnow().timestamp() // 10)
    return worker.enqueue("sitrep", {"incident_id": inc}, dedupe_key=f"sitrep-{inc}-{bucket}")
