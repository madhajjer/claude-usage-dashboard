# Token Calibration Loop

A self-improving loop that learns how many tokens your task-types actually cost, so you
can budget against the 5-hr rolling limit instead of hitting it blind. Built on the same
7-move shape as the edge-loop (`learn-the-loop`): a single carried-forward **core**
(`token-priors.md`), predict-before-peek, and scoring the prediction — not just logging
usage.

Logging usage (what `ccusage` / the dashboard do alone) is a treadmill. This loop wraps
those instruments so each session predicts cost *before* the work and scores it *after*,
turning passive telemetry into a self-correcting cost model.

## Files

| File | Role |
|------|------|
| `token-calibration-loop.md` | Full design — the 7 moves, verdict buckets, the two rules |
| `token-priors.md` | **The core (state).** Per-task-type cost bands in non-cache k-tokens |
| `RUN-A-PASS.md` | Self-contained runbook — what to do each pass |
| `token-scorecard.example.jsonl` | Example append-only scorecard (predictions + verdicts) |
| `install.sh` | Installs the Claude Code SessionStart reminder hook |

## Install

```bash
# 1. ccusage is the VERDICT instrument (token snapshots)
npm i -g ccusage

# 2. Install the SessionStart hook (idempotent; merges into ~/.claude/settings.json)
bash install.sh
# custom settings path: CLAUDE_SETTINGS=/path/to/settings.json bash install.sh

# 3. Reload: open /hooks in Claude Code once, or restart
```

The hook injects the current priors + a reminder at every session start. It never blocks
(`2>/dev/null || true`, 10s timeout) and is safe to re-run — it replaces its own prior
entry rather than stacking.

## Use

Say **"run a token-calibration pass"** (or just follow the SessionStart nudge). One pass:

```
0 POP      pick task-type from token-priors.md
1 RECALL   read that row's band
2 PREDICT  append {phase:PREDICT, pred_k, conf} to scorecard  <-- BEFORE work
3 RUN      START snapshot -> do the task -> END snapshot
4 VERDICT  actual_k = (END - START) / 1000   (delta of NON-cache tokens only)
5 SCORE    err = |pred-actual|/actual -> ON_BUDGET / DRIFT / BLIND
6 DISTILL  move that one row's band ~30% toward actual; n+1; update confidence
```

Snapshot command (non-cache = inputTokens + outputTokens; totalTokens is 80-95% cache
overhead and must NOT be used to calibrate):

```bash
ccusage blocks --json | python3 -c "import sys,json;d=json.load(sys.stdin);b=[x for x in d['blocks'] if x.get('isActive')];c=(b[0] if b else d['blocks'][-1])['tokenCounts'];print(c['inputTokens']+c['outputTokens'])"
```

## The two rules (don't skip)

- **Predict before you peek.** The PREDICT line lands in the scorecard before the START
  snapshot, or the scorecard is just a mirror and proves nothing.
- **Score the model, not the work.** You're grading whether the cost band was right, not
  whether the task was good. Only that makes the band trustworthy for budgeting.

## Proof it's learning

After 5+ passes of a task-type, rolling MAPE must trend down and ON_BUDGET share up. Flat
MAPE = treadmill → split the task-type or shrink the per-task cost (e.g. the
`token-efficient` skill). HALT before any pass whose predicted band would blow the
remaining rolling budget.
