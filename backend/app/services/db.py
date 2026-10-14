"""Firestore client, document references and small typed helpers.

All writes go through the helpers here (or `count_writes` inside transactions) so
`STATS` can report Firestore writes per run (free-tier budget, docs/COSTS.md).
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterable
from functools import lru_cache
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.async_document import AsyncDocumentReference

from app.config import get_settings

STATS: Counter[str] = Counter()
TX_MAX_ATTEMPTS = 30


@lru_cache
def get_db() -> AsyncClient:
    """Return the process-wide async Firestore client (emulator-aware)."""
    s = get_settings()
    if s.FIRESTORE_EMULATOR_HOST:
        os.environ["FIRESTORE_EMULATOR_HOST"] = s.FIRESTORE_EMULATOR_HOST
    return firestore.AsyncClient(project=s.GCP_PROJECT_ID)


def transaction():
    """New transaction with a retry budget sized for hot documents (shelters, counters)."""
    return get_db().transaction(max_attempts=TX_MAX_ATTEMPTS)


def count_writes(n: int = 1) -> None:
    """Record `n` document writes (used inside transactions and batches)."""
    STATS["writes"] += n


# ------------------------------------------------------------------ references
def incident_ref(inc: str) -> AsyncDocumentReference:
    return get_db().collection("incidents").document(inc)


def case_ref(inc: str, rid: str) -> AsyncDocumentReference:
    return incident_ref(inc).collection("cases").document(rid)


def checkin_ref(inc: str, ck: str) -> AsyncDocumentReference:
    return incident_ref(inc).collection("checkins").document(ck)


def task_ref(inc: str, tid: str) -> AsyncDocumentReference:
    return incident_ref(inc).collection("tasks").document(tid)


def events_col(inc: str):
    return incident_ref(inc).collection("agent_events")


def resident_ref(rid: str) -> AsyncDocumentReference:
    return get_db().collection("residents").document(rid)


def shelter_ref(sid: str) -> AsyncDocumentReference:
    return get_db().collection("shelters").document(sid)


def volunteer_ref(vid: str) -> AsyncDocumentReference:
    return get_db().collection("volunteers").document(vid)


# ------------------------------------------------------------------ helpers
async def get_doc(ref: AsyncDocumentReference) -> dict[str, Any] | None:
    """Return the document as a dict, or None if it doesn't exist."""
    snap = await ref.get()
    STATS["reads"] += 1
    return snap.to_dict() if snap.exists else None


async def set_doc(ref: AsyncDocumentReference, data: dict[str, Any], merge: bool = False) -> None:
    await ref.set(data, merge=merge)
    count_writes()


async def update_doc(ref: AsyncDocumentReference, data: dict[str, Any]) -> None:
    await ref.update(data)
    count_writes()


async def list_docs(collection) -> list[dict[str, Any]]:
    """Return every document in a collection or query as dicts."""
    out = [d.to_dict() async for d in collection.stream()]
    STATS["reads"] += max(1, len(out))
    return out


async def list_residents() -> list[dict[str, Any]]:
    return await list_docs(get_db().collection("residents"))


async def list_shelters() -> list[dict[str, Any]]:
    return await list_docs(get_db().collection("shelters"))


async def list_volunteers() -> list[dict[str, Any]]:
    return await list_docs(get_db().collection("volunteers"))


async def list_cases(inc: str) -> list[dict[str, Any]]:
    return await list_docs(incident_ref(inc).collection("cases"))


async def batch_write(items: Iterable[tuple[AsyncDocumentReference, dict[str, Any]]]) -> None:
    """Set many documents in batches of 400 (Firestore limit is 500)."""
    db = get_db()
    batch, n = db.batch(), 0
    for ref, data in items:
        batch.set(ref, data)
        n += 1
        if n % 400 == 0:
            await batch.commit()
            batch = db.batch()
    if n % 400:
        await batch.commit()
    count_writes(n)


async def delete_collection(collection, page: int = 300) -> int:
    """Delete every document in a collection in batches. Returns the count."""
    db, total = get_db(), 0
    while True:
        docs = [d async for d in collection.limit(page).stream()]
        if not docs:
            return total
        batch = db.batch()
        for d in docs:
            batch.delete(d.reference)
        await batch.commit()
        total += len(docs)
        STATS["deletes"] += len(docs)
