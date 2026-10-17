"""M6 evals (PRD §20.3-20.4): classifier accuracy (SM-2/SM-3) and voice-agent guardrails (SM-4).

Needs a real Gemini key; each full run uses ~12 classifier calls + ~10 caller turns.
    cd backend && GENAI_MODE=real uv run python tests/evals/run_evals.py --write
    cd backend && uv run python tests/evals/run_evals.py --dry-run     # validate data only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.services import classifier, genai  # noqa: E402
from app.voice import live_tools  # noqa: E402
from app.voice.live_bridge import CONNECTED, TextTurn, _chat_prompt  # noqa: E402
from app.voice.live_tools import CallState  # noqa: E402
from app.voice.prompt import render_voice_prompt  # noqa: E402
from tests.evals import scoring  # noqa: E402

RESULTS = ROOT / "docs" / "EVAL_RESULTS.md"


async def run_classifier() -> tuple[list[scoring.ClassifierResult], str]:
    results, model = [], ""
    for case in scoring.load_jsonl("classifier_eval.jsonl"):
        cls, model_used = await classifier.classify(case["transcript"], None, cached=None)
        model = model or model_used
        spoke = classifier.has_resident_speech(case["transcript"])
        final, review = classifier.final_status(cls, None, resident_spoke=spoke)
        results.append(
            scoring.ClassifierResult(
                case["id"],
                case["language"],
                case.get("expected_status"),
                final.value,
                case.get("expected_review"),
                review,
                case.get("expected_medical", False),
                cls.confidence,
                model_used,
                cls.summary_en,
            )
        )
        print(
            f"  {case['id']}: expected {case.get('expected_status')}, got {final.value} "
            f"(review {review}, model {model_used})"
        )
    return results, model


def _scenario() -> tuple[dict, dict]:
    seed = ROOT / "seed"
    residents = json.loads((seed / "residents.json").read_text(encoding="utf-8"))
    resident = next(r for r in residents if r["resident_id"] == "R-002")  # English live resident
    incident = json.loads((seed / "scenario_flood_demo.json").read_text(encoding="utf-8"))
    return resident, incident


async def run_guardrails() -> tuple[list[scoring.GuardrailResult], str]:
    resident, incident = _scenario()
    system = render_voice_prompt(resident, incident, text_mode=True)
    results, model = [], ""
    for case in scoring.load_jsonl("guardrail_eval.jsonl"):
        if case.get("classify_only"):
            cls, model_used = await classifier.classify(case["transcript"], None, cached=None)
            spoke = classifier.has_resident_speech(case["transcript"])
            final, _ = classifier.final_status(cls, None, resident_spoke=spoke)
            res = scoring.check_guardrail(case, [], None, final.value)
        else:
            state = CallState("eval", resident["resident_id"], 1)
            agent_lines: list[str] = []
            for user_text in [None, *case["resident_lines"]]:
                if user_text is not None:
                    state.transcript.append({"role": "resident", "text": user_text})
                turn, model_used = await genai.generate_json(
                    system=system, prompt=_chat_prompt(state), schema=TextTurn
                )
                state.transcript.append({"role": "agent", "text": turn.say})
                agent_lines.append(turn.say)
                if turn.record_status:
                    live_tools.apply_record_status(state, turn.record_status.model_dump())
                if turn.end_call:
                    break
            recorded = state.live_status.value if state.live_status else None
            res = scoring.check_guardrail(case, agent_lines, recorded)
        model = model or model_used
        print(
            f"  {case['id']} {case['title']}: "
            f"{'pass' if res.passed else 'FAIL ' + str(res.failures)}"
        )
        results.append(res)
    return results, model


def dry_run() -> int:
    cls = scoring.load_jsonl("classifier_eval.jsonl")
    grd = scoring.load_jsonl("guardrail_eval.jsonl")
    print(f"classifier cases: {len(cls)}, guardrail cases: {len(grd)}")
    print(f"first prompt line: {CONNECTED}")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suite", choices=["classifier", "guardrail", "all"], default="all")
    ap.add_argument("--write", action="store_true", help="update docs/EVAL_RESULTS.md")
    ap.add_argument(
        "--dry-run", action="store_true", help="validate the eval files, no model calls"
    )
    args = ap.parse_args()
    if args.dry_run:
        return dry_run()
    if get_settings().GENAI_MODE != "real":
        print("Evals need real Gemini: set GENAI_MODE=real and GEMINI_API_KEY (backend/.env).")
        return 2

    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    ok = True
    if args.suite in ("classifier", "all"):
        print("Classifier eval (SM-2, SM-3):")
        results, model = await run_classifier()
        summary = scoring.summarize_classifier(results)
        ok &= summary["accuracy"] >= 0.9 and summary["missed_medical"] == 0
        if args.write:
            scoring.update_section(
                RESULTS,
                "classifier",
                f"_Run {stamp}_\n\n" + scoring.classifier_markdown(summary, results, model),
            )
        print(f"  accuracy {summary['accuracy']:.0%}, missed MEDICAL {summary['missed_medical']}")
    if args.suite in ("guardrail", "all"):
        print("Guardrail eval (SM-4):")
        results, model = await run_guardrails()
        ok &= all(r.passed for r in results)
        if args.write:
            scoring.update_section(
                RESULTS,
                "guardrail",
                f"_Run {stamp}_\n\n" + scoring.guardrail_markdown(results, model),
            )
    if args.write:
        print(f"Wrote {RESULTS.relative_to(ROOT)}")
    print(f"llm calls: {genai.db.STATS['llm_calls']}, errors: {genai.db.STATS['llm_errors']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
