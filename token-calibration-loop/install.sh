#!/usr/bin/env bash
# Token Calibration Loop installer.
# Installs a Claude Code SessionStart hook that reminds you to run a calibration
# pass each session and injects the current priors as context.
set -euo pipefail

LOOP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"

echo "Loop package: $LOOP_DIR"
echo "Claude settings: $SETTINGS"

# 1. Dependency check
command -v python3 >/dev/null || { echo "ERROR: python3 required"; exit 1; }
if ! command -v ccusage >/dev/null; then
  echo "WARN: ccusage not found. Install it: npm i -g ccusage"
  echo "      (needed for the RUN step token snapshots)"
fi

# 2. Merge the SessionStart hook into settings.json (idempotent)
python3 - "$SETTINGS" "$LOOP_DIR" <<'PY'
import json, os, sys
settings_path, loop_dir = sys.argv[1], sys.argv[2]
priors = os.path.join(loop_dir, "token-priors.md")
cmd = (
    f"python3 -c \"import json,os;f='{priors}';"
    "p=open(f).read() if os.path.exists(f) else '(priors missing)';"
    "print(json.dumps({'hookSpecificOutput':{'hookEventName':'SessionStart',"
    "'additionalContext':'TOKEN-CALIBRATION LOOP active. On output-heavy sessions, "
    f"run a pass per {loop_dir}/RUN-A-PASS.md (Rule A: PREDICT before peek; "
    "calibrate on non-cache tokens). Current priors below.\\n\\n'+p}}))\" "
    "2>/dev/null || true"
)
os.makedirs(os.path.dirname(settings_path), exist_ok=True)
s = {}
if os.path.exists(settings_path):
    with open(settings_path) as fh:
        s = json.load(fh)
hooks = s.setdefault("hooks", {})
ss = hooks.setdefault("SessionStart", [])
# drop any prior token-calibration hook, then add fresh
for grp in ss:
    grp["hooks"] = [h for h in grp.get("hooks", [])
                    if "TOKEN-CALIBRATION LOOP" not in h.get("command", "")]
ss = [g for g in ss if g.get("hooks")]
ss.append({"hooks": [{"type": "command", "command": cmd, "timeout": 10}]})
hooks["SessionStart"] = ss
with open(settings_path, "w") as fh:
    json.dump(s, fh, indent=2)
print("SessionStart hook installed.")
PY

echo "Done. Open /hooks in Claude Code once (or restart) to load it."
