#!/usr/bin/env python3
"""usagecal — calibrate the (unpublished) Claude Code session limit from /usage pastes.

The authoritative limit % lives only in the interactive `/usage` panel, which the model
cannot poll. But when the user pastes `/usage`, we pair its "session X% used" with the
concurrent **total** token count from `ccusage` to back out the real cap:

    cap_total  ≈  total_tokens / (session_pct / 100)

Basis = TOTAL tokens (input+output+cache_read+cache_creation), NOT non-cache. Measured
finding (2026-06-14): across two /usage reads (12%→18%) non-cache barely moved (+11k)
while total grew +2.5M and cost +$2.35 — cache-hit ~97%, so the quota tracks total/cost.
Non-cache as a basis under-tracked badly; total had the best cross-anchor agreement (82%).

Each paste is one (pct, total) pair; the stored cap is the median implied cap over all
pairs, so it self-corrects. Between pastes the time loop's per-turn total log
(durations.log col 5) lets the prompt hook EXTRAPOLATE the current % with no ccusage call.

Caveat: still a proxy (/usage is cost-weighted; total is raw cache-inclusive tokens), and
there is a fixed offset two points can't fully resolve — each fresh paste re-anchors and
removes drift.

Commands:
  record <session_pct> [--week <pct>] [--reset "<text>"] [--total <n>]
      Anchor: read ccusage total now (or use --total to backfill a historical pair),
      log the pair, recompute the cap, write usage-state.json.
  status
      Print the calibrated cap + current % (authoritative ccusage read).

State (in ~/.claude/time-loop/):
  usage-cal.log    <iso>\t<session_pct>\t<total_tokens>\t<implied_cap>
  usage-state.json {ts, session_pct, total_tokens, cap, week_pct, session_reset}
"""
import sys, os, json, subprocess, statistics
from datetime import datetime

DIR = os.path.expanduser("~/.claude/time-loop")
CAL_LOG = os.path.join(DIR, "usage-cal.log")
STATE = os.path.join(DIR, "usage-state.json")


def ccusage_total():
    """Active-block total tokens (incl cache), or None."""
    try:
        out = subprocess.run(["ccusage", "blocks", "--active", "--json"],
                             capture_output=True, text=True, timeout=60).stdout
        d = json.loads(out)
        blocks = [b for b in d.get("blocks", []) if b.get("isActive")]
        b = blocks[0] if blocks else (d["blocks"][-1] if d.get("blocks") else None)
        return int(b["totalTokens"]) if b else None
    except Exception:
        return None


def load_pairs():
    pairs = []
    if not os.path.exists(CAL_LOG):
        return pairs
    try:
        with open(CAL_LOG) as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) >= 4:
                    try:
                        pairs.append((float(p[1]), int(p[2]), float(p[3])))
                    except ValueError:
                        pass
    except Exception:
        pass
    return pairs


def cmd_record(argv):
    if not argv:
        print("usage: usagecal record <session_pct> [--week <pct>] [--reset \"<text>\"] [--total <n>]")
        return 2
    try:
        pct = float(str(argv[0]).rstrip("%"))
    except ValueError:
        print("session_pct must be a number, e.g. 18")
        return 2
    week = reset = total_override = None
    i = 1
    while i < len(argv):
        if argv[i] == "--week" and i + 1 < len(argv):
            try:
                week = float(str(argv[i + 1]).rstrip("%"))
            except ValueError:
                pass
            i += 2
        elif argv[i] == "--reset" and i + 1 < len(argv):
            reset = argv[i + 1]
            i += 2
        elif argv[i] == "--total" and i + 1 < len(argv):
            try:
                total_override = int(argv[i + 1])
            except ValueError:
                pass
            i += 2
        else:
            i += 1

    if pct <= 0:
        print("session_pct must be > 0 to imply a cap (got %s%%)" % pct)
        return 2
    total = total_override if total_override is not None else ccusage_total()
    if total is None:
        print("ERROR: could not read ccusage active block (is ccusage installed?)")
        return 1
    implied = total / (pct / 100.0)

    os.makedirs(DIR, exist_ok=True)
    with open(CAL_LOG, "a") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')}\t{pct}\t{total}\t{implied:.0f}\n")

    pairs = load_pairs()
    cap = statistics.median(p[2] for p in pairs) if pairs else implied
    state = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "session_pct": pct,
        "total_tokens": total,
        "cap": cap,
        "week_pct": week,
        "session_reset": reset,
    }
    with open(STATE, "w") as f:
        json.dump(state, f, indent=2)

    print(f"anchored: session {pct}% ↔ {total:,} total tokens  →  implied cap {implied:,.0f}")
    print(f"stored cap (median of {len(pairs)} pair(s)): {cap:,.0f} total tokens (~{cap/1e6:.0f}M)")
    if week is not None:
        print(f"week: {week}% used")
    if reset:
        print(f"session resets: {reset}")
    return 0


def cmd_status():
    if not os.path.exists(STATE):
        print("no calibration yet. Paste /usage, then: usagecal record <session_pct>")
        return 0
    st = json.load(open(STATE))
    cap = st.get("cap")
    print(f"calibrated cap: {cap:,.0f} total tokens (~{cap/1e6:.0f}M) "
          f"(from anchor {st.get('session_pct')}% at {st.get('ts')})")
    now = ccusage_total()
    if now is not None and cap:
        print(f"current ccusage total: {now:,}  →  session ~{now / cap * 100:.0f}% used "
              f"(proxy; authoritative figure is /usage)")
    if st.get("week_pct") is not None:
        print(f"last week reading: {st['week_pct']}% used")
    if st.get("session_reset"):
        print(f"session resets: {st['session_reset']}")
    return 0


def main():
    if len(sys.argv) < 2:
        print("usage: usagecal {record|status} ...")
        return 2
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "record":
        return cmd_record(rest)
    if cmd == "status":
        return cmd_status()
    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
