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
  start-<session_id>  transient per-session start epoch (removed on Stop)
  durations.log       tab-separated rows, schema v2:
                        <iso>\t<elapsed_s>\t<out_tok>\t<noncache_tok>\t<tag>
                      (older 2-field rows are still read; their token stats skipped)

Fails silent: a broken hook must never block a turn.
"""
import sys, os, re, json, time, statistics
from datetime import datetime

DIR = os.path.expanduser("~/.claude/time-loop")
LOG = os.path.join(DIR, "durations.log")
WINDOW = 20
MAX_PLAUSIBLE = 86400


def read_stdin_json():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def session_id(data):
    s = str(data.get("session_id") or "default")
    return "".join(c for c in s if c.isalnum() or c in "-_") or "default"


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
                r = {"elapsed": int(p[1]), "out": None, "nc": None, "total": None}
                if len(p) >= 3 and p[2].lstrip("-").isdigit() and int(p[2]) >= 0:
                    r["out"] = int(p[2])
                if len(p) >= 4 and p[3].lstrip("-").isdigit() and int(p[3]) >= 0:
                    r["nc"] = int(p[3])
                if len(p) >= 6 and p[4].lstrip("-").isdigit() and int(p[4]) >= 0:
                    r["total"] = int(p[4])  # v3 rows only (6 fields); v2 p[4] is the tag
                rows.append(r)
    except Exception:
        pass
    return rows


def read_tag(sid):
    tag_file = os.path.join(DIR, f"tag-{sid}")
    try:
        with open(tag_file) as f:
            t = f.read().strip().replace("\t", " ")[:40]
        os.remove(tag_file)
        return t or "untagged"
    except Exception:
        return "untagged"


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
            tag = read_tag(sid)
            with open(LOG, "a") as f:
                f.write(f"{datetime.now().isoformat(timespec='seconds')}\t"
                        f"{int(elapsed)}\t{out}\t{nc}\t{tot}\t{tag}\n")
        except Exception:
            pass
        finally:
            try:
                os.remove(start_file)
            except OSError:
                pass
        return

    # ---- prompt mode -------------------------------------------------------
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
        prior = (f"Calibration prior (last {len(recent)} turns): "
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
