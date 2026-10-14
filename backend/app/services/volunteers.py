"""Volunteer selection and availability (PRD §15.3)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from google.cloud import firestore

from app.services import db
from app.services.geo import haversine_m

_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def rank_volunteers(
    resident: dict[str, Any], volunteers: list[dict[str, Any]], limit: int = 3
) -> list[dict[str, Any]]:
    """Return the best `limit` available volunteers for a resident (lower score is better)."""
    r_langs = set(resident.get("languages", [])) | {resident.get("preferred_language")}
    heavy = resident.get("mobility") in ("wheelchair", "bedridden")
    out = []
    for v in volunteers:
        if not v.get("available"):
            continue
        dist_m = haversine_m(resident["location"], v["location"])
        shares = bool(r_langs & set(v["languages"]))
        no_driver = heavy and "driver" not in v.get("skills", [])
        score = dist_m / 1000 + (0 if shares else 1.0) + (0.5 if no_driver else 0)
        why = [f"{dist_m:.0f} m away", "shares a language" if shares else "no shared language"]
        if heavy and not no_driver:
            why.append("driver")
        out.append(
            {
                "volunteer_id": v["volunteer_id"],
                "display_name": v["display_name"],
                "languages": v["languages"],
                "distance_m": round(dist_m),
                "score": round(score, 3),
                "why": ", ".join(why),
            }
        )
    out.sort(key=lambda x: (x["score"], x["volunteer_id"]))
    return out[:limit]


async def claim_volunteer(volunteer_id: str) -> bool:
    """Atomically mark a volunteer unavailable. Returns False if already taken."""
    ref = db.volunteer_ref(volunteer_id)
    tx = db.transaction()

    @firestore.async_transactional
    async def _run(t) -> bool:
        snap = await ref.get(transaction=t)
        if not snap.exists or not snap.to_dict().get("available"):
            return False
        t.update(ref, {"available": False})
        db.count_writes()
        return True

    # In-process lock avoids transaction contention on one instance [P1]; the
    # transaction still guarantees correctness across instances [P2].
    async with _locks[volunteer_id]:
        return await _run(tx)


async def release_volunteer(volunteer_id: str) -> None:
    """Make a volunteer available again (task DONE, CANNOT_LOCATE, REJECTED or CANCELLED)."""
    await db.update_doc(db.volunteer_ref(volunteer_id), {"available": True})
