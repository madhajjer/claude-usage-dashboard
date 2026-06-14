# Calibration Loop — one loop, two probes (tokens · time · burn)

The umbrella over [`token-calibration-loop/`](token-calibration-loop/) and
[`time-calibration-loop/`](time-calibration-loop/). Same discipline (PREDICT before peek,
score the model not the work), one shared core, joined by **task-type**.

## The model

A turn costs **tokens** and takes **time**. They are linked by a rate:

```
time  ≈  output_tokens / burn_rate
```

- **gen_rate** (pure generation, output tok/s while the model is actually generating) is
  roughly **constant per model**. This is the kernel of truth in "Claude has a constant
  token/sec rate."
- **wall-clock** of a turn is `generation_time + tool_wait` (builds, network, file reads —
  zero tokens produced). So the **effective burn** you observe, `output_tokens /
  wall_clock`, is *diluted* by tool-wait and is **lower on tool-heavy turns**.
- Therefore effective burn is not one global constant — but it **is stable per task-type**
  (each task-type has a characteristic tool-wait profile). `codebase explore` and
  `backtest/study run` are tool-bound (low burn); `design/doc write` and `read+answer` are
  generation-bound (burn ≈ gen_rate). That per-task-type burn is exactly "how quick the
  burn is" for a kind of work.

Given any two of {tokens, time, burn} you predict the third. That is what merges the two
loops: predict tokens → derive time; or measure time → infer tokens; burn_rate is the join.

## The two probes

| Probe | Cadence | Instrument | Measures | Feeds |
|-------|---------|-----------|----------|-------|
| **tokens** | manual pass, output-heavy sessions | `ccusage` snapshots (delta) | non-cache `inputTokens+outputTokens` | `token-priors.md` `tokens (k)` |
| **time + burn** | **automatic, every turn** | `time-calibration-loop` hooks | wall-clock elapsed + transcript `output_tokens` | `token-priors.md` `time band` / `burn` + `durations.log` |

Both ultimately measure the **same per-turn token usage** — the manual pass reads it from
`ccusage` blocks, the automatic Stop hook reads it from the transcript's `message.usage`.
The transcript path makes per-turn token accounting automatic, so the time loop now logs
`elapsed_s · out_tok · noncache_tok` together and computes burn for free.

## The limit anchor (usagecal)

A third calibrated quantity: the **session limit cap**. Anthropic doesn't publish it and
the model can't poll `/usage`, but pasting `/usage` once lets `time-calibration-loop/
usagecal.py` back-compute it — `cap ≈ total_tokens / (session_pct/100)` — and store the
median over pastes. Basis is **total tokens** (incl cache), not non-cache: with ~97%
cache-hit the quota follows total/cost, and non-cache was measured to be near-flat against
`/usage`. Between pastes the `UserPromptSubmit` hook extrapolates the live % from the
per-turn total tokens `durations.log` already records (no ccusage call). So manual `/usage`
reads become a self-correcting limit prior, surfaced every turn as a labelled proxy.

## The shared core

`token-calibration-loop/token-priors.md` — one row per task-type, columns:
`tokens (k) · time band · burn (tok/s) · conf · n · note`. The `tokens` column is moved by
manual passes; `time band` / `burn` are moved by the automatic time-loop feed. Same
30%-toward-actual distill rule for every column.

## Each turn (automatic) and each pass (manual)

- **Turn:** the `UserPromptSubmit` hook injects `now` + the unified prior and asks for a
  one-line prediction (task-type, output tokens, wall-clock time — which must satisfy the
  identity). The `Stop` hook logs the actuals. No effort required; the prior sharpens.
- **Pass:** say "run a token-calibration pass" to do a scored `ccusage` token pass per
  `token-calibration-loop/RUN-A-PASS.md`, reconciling the `tokens (k)` band and reading
  recent `durations.log` to update the `time band` / `burn` columns.

## Install both

```bash
bash token-calibration-loop/install.sh   # SessionStart: inject priors + nudge
bash time-calibration-loop/install.sh    # UserPromptSubmit + Stop: time/token/burn per turn
# then open /hooks once (or restart)
```
