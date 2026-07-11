#!/usr/bin/env python3
"""Unified calibration-loop hook for Claude Code (time + tokens + burn rate).

This is the automatic half of the calibration loop (see ../calibration-loop.md). It
measures, per turn, BOTH wall-clock time and the tokens generated, and derives the
burn rate (output tokens / second) that ties the two together.

Modes (argv[1]):
  prompt  -> UserPromptSubmit: inject current wall-clock time + a unified prior
             (time band, output-token band, effective burn rate, gen-rate estimate)
             and record this turn's start epoch.
  stop    -> Stop: measure elapsed since start AND read the transcript to sum this
             turn's output / non-cache tokens, then append one row to the log.

Identity it trains:  time  ~=  output_tokens / burn_rate
  - gen_rate (pure generation) is ~constant per model; we estimate it as the high
    percentile of observed output/sec (turns with little tool-wait).
  - effective burn = output_tokens / wall_clock is diluted by tool-wait time, so it
    is lower on tool-heavy turns. Per-turn effective burn is what "how quick the
    burn is" actually means for a given kind of work.

Token measurement uses the transcript JSONL: each assistant message carries
message.usage {output_tokens, input_tokens, cache_*} and a timestamp. We sum
assistant messages whose timestamp >= the recorded turn start. Non-cache tokens =
input_tokens + output_tokens (same quantity the manual ccusage pass calibrates on).

State in ~/.claude/time-loop/:
  start-<session_id>  transient per-session start epoch (removed on Stop; stale ones reaped)
  pair-<session_id>   transient {pred,out,elapsed} consumed by the next prompt to score
  durations.log       tab-separated rows, schema v3:
                        <iso>\t<elapsed_s>\t<out_tok>\t<noncache_tok>\t<total_tok>\t<tag>
                      (older 2/5-field rows are still read; missing stats are skipped)

The <tag> is the task-type, parsed straight from this turn's PREDICT line against the
priors-table vocab (parse_task_type) — no manual tagging. Scored turns are also appended to
~/.claude/calibration/scorecard.jsonl, and backfill.py re-derives the whole priors table
from this log.

Fails silent: a broken hook must never block a turn.
"""
import sys, os, re, json, time, statistics, subprocess
from datetime import datetime

DIR = os.path.expanduser("~/.claude/time-loop")
LOG = os.path.join(DIR, "durations.log")
PRIORS = os.path.expanduser("~/.claude/calibration/token-priors.md")
SCORE = os.path.expanduser("~/.claude/calibration/scorecard.jsonl")
WINDOW = 20
MAX_PLAUSIBLE = 86400

# Fallback task-type vocab when the priors file can't be read (keep in sync with the
# priors table row labels — that file is the real source of truth for task-types).
DEFAULT_TYPES = ["read+answer", "single-file edit", "multi-file feature",
                 "codebase explore", "backtest/study run", "design/doc write", "debug loop"]


def read_stdin_json():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def session_id(data):
    s = str(data.get("session_id") or "default")
    return "".join(c for c in s if c.isalnum() or c in "-_") or "default"


def is_print_mode():
    """True when this hook fires inside a non-interactive `claude -p`/--print run
    (e.g. nested by `headroom learn`). Those children parse their own stdout as
    structured JSON, so the PREDICT instruction must not be injected into them."""
    try:
        pid = os.getppid()
        for _ in range(10):
            if pid <= 1:
                break
            try:
                args = subprocess.run(["ps", "-o", "args=", "-p", str(pid)],
                                      capture_output=True, text=True, timeout=2).stdout.strip()
                ppid = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)],
                                      capture_output=True, text=True, timeout=2).stdout.strip()
            except Exception:
                break
            low = args.lower()
            toks = args.split()
            if "headroom" in low:
                return True
            if "claude" in low and ("-p" in toks or "--print" in toks):
                return True
            try:
                pid = int(ppid)
            except (ValueError, TypeError):
                break
    except Exception:
        pass
    return False


def human_time(seconds):
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60}s"
    return f"{s // 3600}h{(s % 3600) // 60}m"


def human_tok(t):
    t = int(t)
    return f"{t/1000:.1f}k" if t >= 1000 else f"{t}"


def pctl(sorted_vals, q):
    if not sorted_vals:
        return 0
    i = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[i]


# ---- transcript token accounting ------------------------------------------
def find_transcript(data):
    tp = data.get("transcript_path")
    if tp and os.path.exists(tp):
        return tp
    cwd = data.get("cwd") or os.getcwd()
    san = re.sub(r"[^A-Za-z0-9]", "-", cwd)
    pdir = os.path.expanduser(f"~/.claude/projects/{san}")
    try:
        js = [os.path.join(pdir, f) for f in os.listdir(pdir) if f.endswith(".jsonl")]
        return max(js, key=os.path.getmtime) if js else None
    except Exception:
        return None


def turn_tokens(transcript, start_epoch):
    """Sum (output, noncache, total) tokens over assistant messages in this turn.

    total = input + output + cache_read + cache_creation — the cache-inclusive volume
    the session quota actually tracks (the limit follows total/cost, not non-cache;
    cache-hit ~97% means non-cache is near-flat while the limit still burns).
    """
    out = nc = tot = 0
    found = False
    try:
        with open(transcript) as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("type") != "assistant":
                    continue
                ts = o.get("timestamp")
                if not ts:
                    continue
                try:
                    te = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except Exception:
                    continue
                if te < start_epoch - 2:
                    continue
                u = (o.get("message") or {}).get("usage") or {}
                ot = int(u.get("output_tokens") or 0)
                it = int(u.get("input_tokens") or 0)
                cr = int(u.get("cache_read_input_tokens") or 0)
                cc = int(u.get("cache_creation_input_tokens") or 0)
                out += ot
                nc += it + ot
                tot += it + ot + cr + cc
                found = True
    except Exception:
        return -1, -1, -1
    return (out, nc, tot) if found else (-1, -1, -1)


# ---- predict-vs-actual pairing --------------------------------------------
def extract_predict(transcript, start_epoch):
    """Return this turn's PREDICT line (assistant text) or None.

    Scans assistant messages with timestamp >= turn start, concatenates their text
    blocks, and returns the first line beginning with PREDICT (case-insensitive).
    This is the prediction half of the loop; the actual half is turn_tokens/elapsed.
    """
    try:
        with open(transcript) as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("type") != "assistant":
                    continue
                ts = o.get("timestamp")
                if not ts:
                    continue
                try:
                    te = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except Exception:
                    continue
                if te < start_epoch - 2:
                    continue
                content = (o.get("message") or {}).get("content") or []
                text = ""
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "text":
                            text += b.get("text") or ""
                for ln in text.splitlines():
                    if re.match(r"\s*PREDICT\b", ln, re.I):
                        return ln.strip()[:200]
    except Exception:
        return None
    return None


def parse_pred(pred):
    """Best-effort (out_tokens, seconds) from a PREDICT line; None where absent."""
    out = secs = None
    if not pred:
        return out, secs
    mt = re.search(r"(\d+(?:\.\d+)?)\s*k\b", pred, re.I)
    if mt:
        out = float(mt.group(1)) * 1000
    m2 = re.search(r"(\d+)\s*m\s*(\d+)?\s*s?\b", pred)
    if m2:
        secs = int(m2.group(1)) * 60 + (int(m2.group(2)) if m2.group(2) else 0)
    else:
        m3 = re.search(r"~?\s*(\d+)\s*s\b", pred)
        if m3:
            secs = int(m3.group(1))
    return out, secs


# ---- task-type tagging -----------------------------------------------------
def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def to_tag(label):
    return re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-") or "untagged"


def load_task_types(priors_path=PRIORS):
    """Task-type vocab = the first column of the priors markdown table.

    The priors file is the single source of truth for which task-types exist; falling
    back to DEFAULT_TYPES keeps tagging working if that file is missing/unreadable.
    """
    types = []
    try:
        with open(priors_path) as f:
            for line in f:
                s = line.strip()
                if not s.startswith("|") or "task-type" in s or set(s) <= set("|-: "):
                    continue
                label = s.strip("|").split("|")[0].strip()
                if label:
                    types.append(label)
    except Exception:
        pass
    return types or DEFAULT_TYPES


def load_budgets(priors_path=PRIORS):
    """{tag: budget_k} from the priors table's 'budget (k)' column (header-matched)."""
    budgets = {}
    try:
        with open(priors_path) as f:
            col = None
            for line in f:
                s = line.strip()
                if not s.startswith("|") or set(s) <= set("|-: "):
                    continue
                cells = [c.strip() for c in s.strip("|").split("|")]
                if col is None:
                    if "task-type" in s:
                        col = next((i for i, c in enumerate(cells)
                                    if c.lower().startswith("budget")), None)
                        if col is None:
                            return {}
                    continue
                if len(cells) > col:
                    try:
                        budgets[to_tag(cells[0])] = float(cells[col])
                    except ValueError:
                        pass
    except Exception:
        pass
    return budgets


def over_budget_lines(rows, min_n=3):
    """Warning lines for task-types whose rolling median non-cache spend exceeds budget."""
    budgets = load_budgets()
    if not budgets:
        return []
    agg = {}
    for r in rows:
        tg = r.get("tag")
        if tg in budgets and r.get("nc") is not None:
            agg.setdefault(tg, []).append(r["nc"])
    out = []
    for tg, ncs in agg.items():
        if len(ncs) < min_n:
            continue
        med = statistics.median(ncs)
        if med > budgets[tg] * 1000:
            out.append(f"  {tg}: rolling median {human_tok(med)} vs budget "
                       f"{budgets[tg]:g}k (n={len(ncs)})")
    return out


def parse_task_type(pred, vocab=None):
    """First known task-type *mentioned* in a PREDICT line (by position), else 'untagged'."""
    if vocab is None:
        vocab = load_task_types()
    p = _norm(pred)
    if not p or not vocab:
        return "untagged"
    best, best_pos = None, len(p) + 1
    for label in vocab:
        idx = p.find(_norm(label))
        if 0 <= idx < best_pos:
            best, best_pos = label, idx
    return to_tag(best) if best else "untagged"


def per_type_summary(rows, min_n=3, limit=5):
    """Compact 'tag (n): ~tok / ~time / burn' lines for tags with enough samples."""
    agg = {}
    for r in rows:
        tg = r.get("tag")
        if tg and tg != "untagged":
            agg.setdefault(tg, []).append(r)
    out = []
    for tg in sorted(agg, key=lambda k: -len(agg[k])):
        rs = agg[tg]
        if len(rs) < min_n:
            continue
        ts = [r["elapsed"] for r in rs]
        toks = [r["out"] for r in rs if r["out"] is not None]
        burns = [r["out"] / r["elapsed"] for r in rs
                 if r["out"] is not None and r["elapsed"] > 0]
        seg = f"  {tg} (n={len(rs)}): "
        seg += f"~{human_tok(statistics.median(toks))} tok / " if toks else ""
        seg += f"~{human_time(statistics.median(ts))}"
        if burns:
            seg += f" / {statistics.median(burns):.0f} tok/s"
        out.append(seg)
        if len(out) >= limit:
            break
    return out


def _append_scorecard(pred, out, el, po, ps):
    """Persist one scored turn to scorecard.jsonl (the MAPE / ON_BUDGET-trend substrate)."""
    try:
        verdict = None
        if po and out:
            e = abs(out - po) / out
            verdict = "ON_BUDGET" if e <= 0.2 else "DRIFT" if e <= 0.6 else "BLIND"
        rec = {"ts": datetime.now().isoformat(timespec="seconds"),
               "task_type": parse_task_type(pred),
               "pred_tok": po, "actual_tok": out,
               "pred_s": ps, "actual_s": el,
               "tok_err": round(out / po, 3) if po else None,
               "time_err": round(el / ps, 3) if ps and el > 0 else None,
               "verdict": verdict}
        os.makedirs(os.path.dirname(SCORE), exist_ok=True)
        with open(SCORE, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def format_pair(pair_path):
    """Read+consume the stored pair file, return a 'predicted -> actual [err]' line."""
    try:
        with open(pair_path) as f:
            p = json.load(f)
        os.remove(pair_path)
    except Exception:
        return None
    out, el, pred = p.get("out"), p.get("elapsed"), p.get("pred")
    if out is None or out < 0 or el is None:
        return None
    po, ps = parse_pred(pred)
    _append_scorecard(pred, out, el, po, ps)
    seg = f"actual {human_tok(out)}/{human_time(el)}"
    if el > 0:
        seg += f" ({out/el:.0f} tok/s)"
    errs = []
    if po:
        errs.append(f"tok {out/po:.2f}x")
    if ps and el > 0:
        errs.append(f"time {el/ps:.2f}x")
    pred_s = pred if pred else "(no PREDICT line found)"
    line = f'Last turn scored, predicted: "{pred_s}" -> {seg}'
    if errs:
        line += " [err " + ", ".join(errs) + "]"
    return line


# ---- log ------------------------------------------------------------------
def load_rows():
    """Return list of dicts: {elapsed, out, nc} (out/nc None when unavailable)."""
    rows = []
    if not os.path.exists(LOG):
        return rows
    try:
        with open(LOG) as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) < 2 or not p[1].isdigit():
                    continue
                r = {"elapsed": int(p[1]), "out": None, "nc": None, "total": None, "tag": None}
                if len(p) >= 3 and p[2].lstrip("-").isdigit() and int(p[2]) >= 0:
                    r["out"] = int(p[2])
                if len(p) >= 4 and p[3].lstrip("-").isdigit() and int(p[3]) >= 0:
                    r["nc"] = int(p[3])
                if len(p) >= 6:
                    if p[4].lstrip("-").isdigit() and int(p[4]) >= 0:
                        r["total"] = int(p[4])  # v3 rows (6 fields): total then tag
                    r["tag"] = p[5].strip() or None
                elif len(p) == 5:
                    r["tag"] = p[4].strip() or None  # v2 rows: tag is field 5
                rows.append(r)
    except Exception:
        pass
    return rows


def reap_orphans(max_age_h=12):
    """Delete stale per-session start-/pair- files (sessions that never cleanly stopped)."""
    cutoff = time.time() - max_age_h * 3600
    try:
        for name in os.listdir(DIR):
            if name.startswith(("start-", "pair-")):
                fp = os.path.join(DIR, name)
                try:
                    if os.path.getmtime(fp) < cutoff:
                        os.remove(fp)
                except OSError:
                    pass
    except Exception:
        pass


def usage_line():
    """Extrapolated limit % from the last /usage anchor (see usagecal.py).

    Cheap: reads only usage-state.json + durations.log, never calls ccusage, so it
    adds no latency to the prompt hook. current% ~= anchor% + (non-cache tokens logged
    since the anchor) / cap. Returns None if no anchor has been recorded yet.
    """
    try:
        with open(os.path.join(DIR, "usage-state.json")) as f:
            st = json.load(f)
    except Exception:
        return None
    cap = st.get("cap")
    pct = st.get("session_pct")
    ts = st.get("ts")
    if not cap or pct is None:
        return None
    try:
        anchor = datetime.fromisoformat(ts).timestamp()
    except Exception:
        anchor = None
    delta = 0
    if anchor is not None and os.path.exists(LOG):
        try:
            with open(LOG) as f:
                for line in f:
                    p = line.rstrip("\n").split("\t")
                    if len(p) >= 6 and p[4].lstrip("-").isdigit() and int(p[4]) >= 0:
                        try:
                            rt = datetime.fromisoformat(p[0]).timestamp()
                        except Exception:
                            continue
                        if rt >= anchor:
                            delta += int(p[4])  # total tokens this turn
        except Exception:
            pass
    est = pct + (delta / cap * 100.0)
    age = ""
    if anchor is not None:
        age = f", last /usage {int((time.time() - anchor) / 60)}m ago"
    tail = ""
    if st.get("week_pct") is not None:
        tail += f"; week {st['week_pct']:.0f}% used"
    if st.get("session_reset"):
        tail += f"; resets {st['session_reset']}"
    return (f"Limit (proxy{age}): session ~{est:.0f}% used "
            f"(anchor {pct:.0f}% + {delta/1e6:.1f}M total since; "
            f"cap ~{cap/1e6:.0f}M total){tail}.")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "prompt"
    data = read_stdin_json()
    os.makedirs(DIR, exist_ok=True)
    sid = session_id(data)
    start_file = os.path.join(DIR, f"start-{sid}")
    now = time.time()

    if mode == "stop":
        try:
            with open(start_file) as f:
                start = float(f.read().strip())
        except Exception:
            return
        try:
            elapsed = now - start
            if not (0 <= elapsed < MAX_PLAUSIBLE):
                return
            out = nc = tot = -1
            tr = find_transcript(data)
            if tr:
                out, nc, tot = turn_tokens(tr, start)
            # task-type comes straight from this turn's PREDICT line (was an unused tag file)
            pred = extract_predict(tr, start) if tr else None
            tag = parse_task_type(pred)
            with open(LOG, "a") as f:
                f.write(f"{datetime.now().isoformat(timespec='seconds')}\t"
                        f"{int(elapsed)}\t{out}\t{nc}\t{tot}\t{tag}\n")
            # stash this turn's PREDICT + actuals so the next prompt can score it
            try:
                with open(os.path.join(DIR, f"pair-{sid}.json"), "w") as pf:
                    json.dump({"pred": pred, "out": out, "elapsed": int(elapsed)}, pf)
            except Exception:
                pass
        except Exception:
            pass
        finally:
            try:
                os.remove(start_file)
            except OSError:
                pass
            reap_orphans()
        return

    # ---- prompt mode -------------------------------------------------------
    # Skip nested non-interactive runs (e.g. `headroom learn`'s `claude -p`):
    # injecting the PREDICT instruction pollutes their structured JSON stdout.
    if is_print_mode():
        return

    try:
        with open(start_file, "w") as f:
            f.write(str(now))
    except Exception:
        pass

    lines = [f"Wall-clock now: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z (%a)')}"]
    rows = load_rows()

    if rows:
        recent = rows[-WINDOW:]
        times = [r["elapsed"] for r in recent]
        toks = [r["out"] for r in recent if r["out"] is not None]
        burns = sorted(r["out"] / r["elapsed"] for r in recent
                       if r["out"] is not None and r["elapsed"] > 0)
        t_med = human_time(statistics.median(times))
        t_lo, t_hi = human_time(min(times)), human_time(max(times))
        type_lines = per_type_summary(rows[-80:])
        if type_lines:
            lines.append("Per task-type (recent — RECALL your row before predicting):")
            lines.extend(type_lines)
        ob = over_budget_lines(rows[-80:])
        if ob:
            lines.append("OVER BUDGET (rolling median > target in token-priors.md — spend "
                         "lean this turn: fewest reads that answer, no re-reads, terse "
                         "output, per the token-efficient skill):")
            lines.extend(ob)
        prior = (f"Calibration prior (last {len(recent)} turns, all task-types blended): "
                 f"time median {t_med} (range {t_lo}-{t_hi})")
        if toks:
            prior += (f" | output median {human_tok(statistics.median(toks))} "
                      f"(range {human_tok(min(toks))}-{human_tok(max(toks))})")
        if burns:
            eff = statistics.median(burns)
            gen = pctl(burns, 0.9)
            prior += f" | burn median {eff:.0f} tok/s, gen-rate ~{gen:.0f} tok/s (p90)"
        lines.append(prior + ".")
        last = rows[-1]
        bit = f"time {human_time(last['elapsed'])}"
        if last["out"] is not None:
            bit += f", {human_tok(last['out'])} tok"
            if last["elapsed"] > 0:
                bit += f", {last['out']/last['elapsed']:.0f} tok/s"
        lines.append("Most recent turn: " + bit + ".")
        pair = format_pair(os.path.join(DIR, f"pair-{sid}.json"))
        if pair:
            lines.append(pair)
        lines.append(
            "PREDICT before working, one line: task-type (from token-priors.md), output "
            "tokens, wall-clock time. They should satisfy time ~= output_tokens / burn_rate "
            "(tool-heavy turns burn slower). Actual tokens + time are auto-logged at turn end."
        )
    else:
        lines.append(
            "Calibration prior: no samples yet. PREDICT this turn's output tokens and "
            "wall-clock time in one short line (they imply a burn rate, tok/s). Both are "
            "auto-measured at turn end from the transcript to seed the prior."
        )

    ul = usage_line()
    if ul:
        lines.append(ul)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(lines),
        }
    }))


if __name__ == "__main__":
    main()
