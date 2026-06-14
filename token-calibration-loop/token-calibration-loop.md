# Token Calibration Loop

A learning loop for token spend, built on the same 7-move shape as the edge-loop
(`learn-the-loop.html`). The carried-forward **core** is `token-priors.md`: a table of
what we believe each task-type *costs* in tokens. The loop works when that table's
predictions get less wrong over time (MAPE / calibration shrinking), not when we merely
log usage. Logging usage is the treadmill; predicting-then-scoring is the loop.

## Why this and not just ccusage / the dashboard

`ccusage` and `claude-usage-dashboard` are **VERDICT instruments** — they report what was
actually spent. By themselves they are a script that runs and forgets: pretty totals, no
carried state, no belief that changes. This loop wraps them so each session writes a
prediction *before* the work and scores it *after*, turning passive telemetry into a
self-correcting cost model. `claude-token-efficient` is the **lever** we pull when a
task-type is chronically OVER its band.

## The core (state): `token-priors.md`

One row per task-type. Each row is a belief with a confidence. Every pass reads it
(RECALL) and every pass updates exactly one row (DISTILL). That one-line diff is the
proof the loop learned.

## One pass — seven moves

| # | Move | Plain words | Touches |
|---|------|-------------|---------|
| 0 | POP | Take the next task; tag it with a task-type. | `task-queue.jsonl` |
| 1 | RECALL | Read the predicted token band for that task-type. | `token-priors.md` |
| 2 | PREDICT | **Before doing the work**, write est. tokens + confidence. | `token-scorecard.jsonl` |
| 3 | RUN | Snapshot block total (`ccusage blocks --json`) at start, do the task, snapshot at end. | the session itself |
| 4 | VERDICT | actual = end − start delta. **ccusage is block-cumulative, never per-task — absolute totals are useless here; only the delta is the answer.** | ccusage |
| 5 | SCORE | Error = `|pred-actual|/actual`; bucket UNDER / ON / OVER. | `token-scorecard.jsonl` |
| 6 | DISTILL | Move the band toward the actual; tighten/loosen confidence. | `token-priors.md` |

Verdict buckets (analog of EDGE/MARGINAL/NO_EDGE):

- **ON_BUDGET** — actual within ±20% of predicted band. Belief confirmed.
- **DRIFT** — 20–60% off. Nudge the band, keep the row.
- **BLIND** — >60% off. The task-type is mis-modeled; split it or flag for the
  `token-efficient` skill.

## The two rules (same as edge-loop)

- **Rule A — Predict before you peek.** The PREDICT line is committed to
  `token-scorecard.jsonl` before RUN. If you read ccusage first and then "predict," the
  scorecard is a mirror and proves nothing.
- **Rule B — Score the prediction, not the task.** We are not grading whether the work
  was good; we are grading whether the *cost model* was right. That is the only thing
  that makes the band trustworthy enough to budget against (e.g. the 5-hr rolling limit).

## Proof of learning

Append-only `token-scorecard.jsonl`. Run `loopscore` analog over it: rolling MAPE per
task-type must trend down, and the share of ON_BUDGET passes must trend up. If MAPE is
flat across 5+ passes of a task-type, the loop is a treadmill for that type → split the
type or change the lever.

## Integration with the 5-hr rolling limit

RECALL also sums the predicted bands of all *queued* tasks. If that sum exceeds remaining
rolling budget, HALT and either (a) defer low-value tasks or (b) invoke `token-efficient`
to shrink the per-task band before running. This is the loop paying rent: it stops you
hitting 3% blind, the way the edge-loop's HALT stops a no-edge deploy.

## Bootstrap

```bash
# VERDICT source — actual tokens per session/block
ccusage --json            # or `ccusage blocks --json` for the rolling window
# seed core already at docs/loop/token-priors.md
# scorecard + queue are append-only jsonl, created on first pass
```
