"""Idempotent loader: upserts the committed seed JSON into Firestore (PRD §19).

Usage (emulator):
    FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GCP_PROJECT_ID=demo-lastmile \
        uv run --project backend python seed/seed_firestore.py

Without FIRESTORE_EMULATOR_HOST it writes to the real project in GCP_PROJECT_ID, so
it asks for confirmation first unless --yes is passed.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from google.cloud import firestore

SEED = Path(__file__).parent


def _load(name: str):
    return json.loads((SEED / name).read_text(encoding="utf-8"))


def main() -> None:
    project = os.environ.get("GCP_PROJECT_ID", "demo-lastmile")
    emulator = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if not emulator and "--yes" not in sys.argv:
        answer = input(f"No emulator set. Seed the REAL project '{project}'? [y/N] ")
        if answer.strip().lower() != "y":
            print("aborted")
            return
    db = firestore.Client(project=project)
    batch, n = db.batch(), 0

    def put(col: str, doc_id: str, data: dict) -> None:
        nonlocal batch, n
        batch.set(db.collection(col).document(doc_id), data)
        n += 1
        if n % 400 == 0:
            batch.commit()
            batch = db.batch()

    scenario = _load("scenario_flood_demo.json")
    put("scenarios", scenario["scenario_id"], scenario)
    for r in _load("residents.json"):
        put("residents", r["resident_id"], r)
    for s in _load("shelters.json"):
        put("shelters", s["shelter_id"], s)
    for v in _load("volunteers.json"):
        put("volunteers", v["volunteer_id"], v)
    for rid, d in _load("dialogues.json").items():
        put("dialogues", rid, d)
    batch.commit()
    target = f"emulator {emulator}" if emulator else f"project {project}"
    print(f"seeded {n} documents into {target}")


if __name__ == "__main__":
    main()
