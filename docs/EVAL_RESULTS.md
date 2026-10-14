# Evaluation results

Filled in at M6 by `tests/evals/run_evals.py` and `tests/evals/metrics.py` (PRD §18, §20).

## M2 baseline (emulator, fake GenAI, fallback policy only)

| Metric                                              | Value                                                |
| --------------------------------------------------- | ---------------------------------------------------- |
| SM-1 residents reaching CONFIRMED_SAFE or ESCALATED | 40 / 40 (100%)                                       |
| End state                                           | 36 CONFIRMED_SAFE, 4 ESCALATED (PRD expects ≈35 / 5) |
| AC-10 counters match recomputed counts              | yes                                                  |

## Classifier eval (SM-2, SM-3)

_Pending (M6)._

## Guardrail eval (SM-4)

_Pending (M6)._
