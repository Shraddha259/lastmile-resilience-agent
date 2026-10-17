"""Run metrics for one incident (PRD §18): SM-1, SM-5, SM-6 and operational numbers.

    make metrics                                  # latest incident in the local emulator
    cd backend && GCP_PROJECT_ID=lastmile-resilience-agent \
        uv run python tests/evals/metrics.py <incident_id> --write
(The second form reads the real project with your gcloud application-default login.)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from google.cloud import firestore  # noqa: E402

from app.services import db  # noqa: E402
from tests.evals import scoring  # noqa: E402

RESULTS = ROOT / "docs" / "EVAL_RESULTS.md"


async def latest_incident() -> str | None:
    q = (
        db.get_db()
        .collection("incidents")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(1)
    )
    docs = await db.list_docs(q)
    return docs[0]["incident_id"] if docs else None


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("incident_id", nargs="?")
    ap.add_argument("--latest", action="store_true", help="use the most recent incident")
    ap.add_argument("--write", action="store_true", help="append to docs/EVAL_RESULTS.md")
    args = ap.parse_args()
    inc = args.incident_id or (await latest_incident() if args.latest else None)
    if not inc:
        print("Give an incident ID or --latest.")
        return 2
    incident = await db.get_doc(db.incident_ref(inc))
    if not incident:
        print(f"Incident {inc} not found.")
        return 2
    base = db.incident_ref(inc)
    m = scoring.compute_metrics(
        incident,
        await db.list_cases(inc),
        await db.list_docs(base.collection("agent_events")),
        await db.list_docs(base.collection("checkins")),
    )
    print(json.dumps(m, indent=2, default=str))
    if args.write:
        scoring.update_section(RESULTS, f"run-{inc}", scoring.metrics_markdown(inc, m))
        print(f"Wrote {RESULTS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
