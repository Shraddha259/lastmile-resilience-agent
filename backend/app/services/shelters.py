"""Shelter matching and transactional reservation (PRD §15.2)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from google.cloud import firestore

from app.services import db
from app.services.geo import haversine_m

_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

MEDICAL_NEEDS = {"oxygen", "dialysis", "medication"}


def rank_shelters(
    resident: dict[str, Any], needs: list[str], shelters: list[dict[str, Any]], limit: int = 3
) -> list[dict[str, Any]]:
    """Return up to `limit` candidate shelters for a resident, best first (pure function)."""
    needs_wc = resident.get("mobility") in ("wheelchair", "bedridden") or "wheelchair" in needs
    needs_med = bool(MEDICAL_NEEDS & set(needs))
    cands = []
    for s in shelters:
        if not s.get("open") or s["occupied"] >= s["capacity"]:
            continue
        if needs_wc and not s["wheelchair_accessible"]:
            continue
        dist = haversine_m(resident["location"], s["location"])
        med_key = (0 if s["medical_support"] else 1) if needs_med else 0
        why = []
        if s["wheelchair_accessible"]:
            why.append("wheelchair accessible")
        if s["medical_support"]:
            why.append("medical support")
        why.append(f"{dist:.0f} m away")
        cands.append(
            (
                (med_key, dist),
                {
                    "shelter_id": s["shelter_id"],
                    "name": s["name"],
                    "distance_m": round(dist),
                    "spaces_left": s["capacity"] - s["occupied"],
                    "wheelchair_accessible": s["wheelchair_accessible"],
                    "medical_support": s["medical_support"],
                    "fit_reasons": why,
                },
            )
        )
    cands.sort(key=lambda c: c[0])
    return [c[1] for c in cands[:limit]]


async def find_shelters(resident: dict[str, Any], needs: list[str]) -> list[dict[str, Any]]:
    """Load shelters and rank them for this resident."""
    return rank_shelters(resident, needs, await db.list_shelters())


async def reserve_shelter(shelter_id: str) -> bool:
    """Atomically take one place. Returns False if the shelter is full or closed."""
    ref = db.shelter_ref(shelter_id)
    tx = db.transaction()

    @firestore.async_transactional
    async def _run(t) -> bool:
        snap = await ref.get(transaction=t)
        s = snap.to_dict() if snap.exists else None
        if not s or not s.get("open") or s["occupied"] >= s["capacity"]:
            return False
        t.update(ref, {"occupied": s["occupied"] + 1})
        db.count_writes()
        return True

    # In-process lock avoids transaction contention on one instance [P1]; the
    # transaction still guarantees correctness across instances [P2].
    async with _locks[shelter_id]:
        return await _run(tx)


async def release_shelter(shelter_id: str) -> None:
    """Give a place back (used when a reservation is undone)."""
    await db.update_doc(db.shelter_ref(shelter_id), {"occupied": firestore.Increment(-1)})
