#!/usr/bin/env python3
"""Weekly calibration eval — is the loop paying rent or just a treadmill?

Reads durations.log + scorecard.jsonl + token-priors.md and answers four questions:

  1. SPEND    is actual median non-cache spend per task-type falling week-over-week?
              (the only number the whole system is ultimately for)
  2. BUDGET   which task-types are over their budget (k) target from token-priors.md?
  3. ACCURACY is prediction quality improving? (MAPE down, ON_BUDGET share up)
  4. HYGIENE  untagged rate — how much of the feed never enters the scoring path?

Writes a markdown report to ~/.claude/calibration/eval-latest.md (and prints it).
The /calibration-eval skill interprets the report and acts on it (FLAG/split rows,
ratchet budgets). This script only measures — it never edits priors.
"""
import os, json, statistics, importlib.util
from datetime import datetime, timedelta

_spec = importlib.util.spec_from_file_location(
    "time_loop", os.path.join(os.path.dirname(os.path.abspath(__file__)), "time-loop.py"))
tl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tl)

REPORT = os.path.expanduser("~/.claude/calibration/eval-latest.md")
WEEKS = 4  # how many weekly buckets to show


def week_start(dt):
    d = dt.date() - timedelta(days=dt.weekday())
    return d.isoformat()


def load_durations():
    rows = []
    try:
        with open(tl.LOG) as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) < 6 or not p[1].isdigit():
                    continue
                try:
                    dt = datetime.fromisoformat(p[0])
                except ValueError:
                    continue
                nc = int(p[3]) if p[3].lstrip("-").isdigit() and int(p[3]) >= 0 else None
                rows.append({"week": week_start(dt), "nc": nc, "tag": p[5].strip()})
    except OSError:
        pass
    return rows


def load_scorecard():
    recs = []
    try:
        with open(tl.SCORE) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                try:
                    r["week"] = week_start(datetime.fromisoformat(r["ts"]))
                except (KeyError, ValueError):
                    continue
                recs.append(r)
    except OSError:
        pass
    return recs


def med_k(vals):
    return f"{statistics.median(vals)/1000:.1f}" if vals else "—"


def main():
    rows = load_durations()
    recs = load_scorecard()
    budgets = tl.load_budgets()
    weeks = sorted({r["week"] for r in rows})[-WEEKS:]
    out = [f"# Calibration eval — {datetime.now().date()}", ""]

    # 1. SPEND: median nc per task-type per week
    tags = sorted({r["tag"] for r in rows if r["tag"] != "untagged"})
    out += ["## 1. Spend trend (median non-cache k/turn, by week — must trend DOWN)", "",
            "| task-type | " + " | ".join(weeks) + " | budget | verdict |",
            "|---|" + "---|" * (len(weeks) + 2)]
    over = []
    for tg in tags:
        cells, last = [], None
        for w in weeks:
            vals = [r["nc"] for r in rows if r["tag"] == tg and r["week"] == w and r["nc"]]
            cells.append(med_k(vals) + (f" (n={len(vals)})" if vals else ""))
            if vals:
                last = statistics.median(vals) / 1000
        b = budgets.get(tg)
        verdict = "—"
        if last is not None and b is not None:
            verdict = "OVER" if last > b else "ok"
            if last > b:
                over.append(f"{tg} ({last:.1f}k vs {b:g}k)")
        btxt = f"{b:g}k" if b is not None else "—"
        out.append(f"| {tg} | " + " | ".join(cells) + f" | {btxt} | {verdict} |")
    out.append("")
    if over:
        out.append("**Over budget:** " + "; ".join(over))
        out.append("")

    # 2. ACCURACY: MAPE + ON_BUDGET share per week (scored rows only)
    out += ["## 2. Prediction accuracy (MAPE down, ON_BUDGET share up = learning)", "",
            "| week | scored | MAPE | ON_BUDGET | DRIFT | BLIND |", "|---|---|---|---|---|---|"]
    for w in weeks:
        wr = [r for r in recs if r["week"] == w and r.get("pred_tok") and r.get("actual_tok")]
        if not wr:
            out.append(f"| {w} | 0 | — | — | — | — |")
            continue
        errs = [abs(r["actual_tok"] - r["pred_tok"]) / r["actual_tok"] for r in wr]
        n = len(wr)
        share = lambda v: f"{sum(1 for r in wr if r.get('verdict') == v)/n:.0%}"
        out.append(f"| {w} | {n} | {statistics.median(errs):.0%} | "
                   f"{share('ON_BUDGET')} | {share('DRIFT')} | {share('BLIND')} |")
    out.append("")

    # worst rows by BLIND count (recent) — split/FLAG candidates
    recent = [r for r in recs if r.get("verdict") == "BLIND"][-60:]
    if recent:
        cnt = {}
        for r in recent:
            cnt[r["task_type"]] = cnt.get(r["task_type"], 0) + 1
        worst = sorted(cnt.items(), key=lambda kv: -kv[1])[:3]
        out.append("**FLAG/split candidates (most recent BLINDs):** "
                   + ", ".join(f"{t} ({c})" for t, c in worst))
        out.append("")

    # 3. HYGIENE: untagged rate per week
    out += ["## 3. Hygiene (untagged rate — data that never enters the loop)", ""]
    for w in weeks:
        wr = [r for r in rows if r["week"] == w]
        u = sum(1 for r in wr if r["tag"] == "untagged")
        out.append(f"- {w}: {u}/{len(wr)} untagged ({u/len(wr):.0%})" if wr else f"- {w}: no rows")
    out += ["", "## Verdict checklist (for /calibration-eval)", "",
            "- [ ] Spend medians flat/down vs last week? If a type is OVER 2 weeks running,",
            "      tighten its workflow (token-efficient) — do NOT raise the budget silently.",
            "- [ ] MAPE trending down / ON_BUDGET share up? Flat after 5+ passes → split the row.",
            "- [ ] Any type consistently under budget → ratchet its budget down ~10%.",
            "- [ ] Untagged rate falling? If not, the PREDICT discipline is slipping.", ""]

    report = "\n".join(out)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        f.write(report + "\n")
    print(report)


if __name__ == "__main__":
    main()
