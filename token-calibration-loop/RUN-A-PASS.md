# Run a pass

Trigger: say **"run a token-calibration pass"**. Full design: `token-calibration-loop.md`.

## The seven moves

```
0 POP      pick task-type from token-priors.md (or tag a new one)
1 RECALL   read that row's band + confidence in token-priors.md
2 PREDICT  append {phase:PREDICT, pred_k, conf} to token-scorecard.jsonl  <-- BEFORE work
3 RUN      START snapshot -> do the task -> END snapshot
4 VERDICT  actual_k = (END - START) / 1000     (delta only; absolute is useless)
5 SCORE    err = |pred-actual|/actual -> ON_BUDGET(<=.2) / DRIFT(.2-.6) / BLIND(>.6)
6 DISTILL  move that one row's band ~30% toward actual; n+1; reset confidence by ON_BUDGET share
```

## Snapshot command (START and END)

Measure **non-cache** tokens (inputTokens+outputTokens). totalTokens is 80-95% cache
read/create = fixed per-turn context overhead, NOT task work (lesson from pass 2).

```bash
ccusage blocks --json | python3 -c "import sys,json;d=json.load(sys.stdin);b=[x for x in d['blocks'] if x.get('isActive')];c=(b[0] if b else d['blocks'][-1])['tokenCounts'];print(c['inputTokens']+c['outputTokens'])"
```

Save START to `/tmp/passN_start.txt`, run END the same way after the task, subtract.
Track cache overhead separately if you care about wall-clock budget (it still counts
against the 5-hr rolling limit), but calibrate task bands on the non-cache delta.

## Two non-negotiables

- **Rule A — predict before peek.** PREDICT line lands in the scorecard before the START
  snapshot. Otherwise the scorecard is a mirror.
- **Rule B — score the model, not the work.** Grade whether the band was right, not
  whether the task was good. Block-cumulative totals are noise; only the delta is signal
  (the lesson pass 1 paid for with a BLIND).

## Proof it's learning, not a treadmill

After 5+ passes of a type: rolling MAPE must trend down and ON_BUDGET share up. Flat MAPE
-> split the task-type or pull the `token-efficient` lever. HALT before any pass whose
predicted band would blow the remaining 5-hr rolling budget.
