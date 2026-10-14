"""Deterministic risk scoring (PRD §10, FR-5). The LLM never computes the score."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models import Priority
from app.services.geo import LocalProjection

AT_RISK_BUFFER_M = 200


@dataclass
class RiskResult:
    resident_id: str
    risk_score: int
    priority: Priority
    risk_reasons: list[str]
    extra_needs: list[str] = field(default_factory=list)
    age: int = 0
    at_risk: bool = True


def score_resident(resident: dict[str, Any], river_dist_m: float) -> RiskResult:
    """Score one resident. Returns score, priority and plain-English reasons."""
    pts, reasons, needs = 0, [], []

    def add(n: int, why: str) -> None:
        nonlocal pts
        pts += n
        reasons.append(f"{why} (+{n})")

    age = resident["age"]
    if age >= 85:
        add(25, f"Age {age}")
    elif age >= 75:
        add(18, f"Age {age}")
    elif age >= 65:
        add(10, f"Age {age}")
    if resident.get("lives_alone"):
        add(15, "Lives alone")
    mob = resident.get("mobility")
    if mob == "bedridden":
        add(25, "Bedridden")
    elif mob == "wheelchair":
        add(20, "Uses wheelchair")
    elif mob == "walker":
        add(10, "Uses walker")
    flags = resident.get("medical_flags", [])
    if "dialysis" in flags or "oxygen" in flags:
        add(15, "Dialysis" if "dialysis" in flags else "Oxygen")
    other = [f for f in flags if f not in ("dialysis", "oxygen", "hearing_impaired")]
    other_pts = 0
    for f in other:
        if other_pts >= 10:
            break
        add(5, f.replace("_", " ").capitalize())
        other_pts += 5
    floor = resident.get("floor", 0)
    if floor == 0:
        add(15, "Ground floor")
    elif floor == 1:
        add(8, "First floor")
    if river_dist_m < 150:
        add(10, f"{river_dist_m:.0f} m from river")
    elif river_dist_m <= 400:
        add(5, f"{river_dist_m:.0f} m from river")
    if "hearing_impaired" in flags:
        needs.append("slow_clear_speech")
        reasons.append("Hearing impaired (+0, needs slow clear speech)")

    score = min(100, pts)
    prio = Priority.P1 if score >= 60 else Priority.P2 if score >= 35 else Priority.P3
    return RiskResult(resident["resident_id"], score, prio, reasons, needs, age)


def rank_residents(
    residents: list[dict[str, Any]], polygon: dict[str, Any], river: dict[str, Any]
) -> list[RiskResult]:
    """Return at-risk residents (inside the polygon or within 200 m of it), ranked.

    Order: risk score desc, then age desc, then resident_id.
    """
    ref_lat = polygon["points"][0]["lat"]
    proj = LocalProjection(ref_lat)
    zone = proj.geom(polygon).buffer(AT_RISK_BUFFER_M)
    river_line = proj.geom(river)
    out = []
    for r in residents:
        p = proj.point(r["location"])
        if not zone.covers(p):
            continue
        out.append(score_resident(r, p.distance(river_line)))
    out.sort(key=lambda x: (-x.risk_score, -x.age, x.resident_id))
    return out
