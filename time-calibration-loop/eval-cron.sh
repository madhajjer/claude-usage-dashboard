#!/bin/bash
# Weekly eval + reminder: compute the calibration report (eval.py -> eval-latest.md),
# then notify to run /calibration-eval, which interprets the report and acts on it.
# Run by LaunchAgent com.kozystay.calibration-eval (Mondays).
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$HOME/.claude/calibration/distill.log"

{
  echo "=== eval $(date '+%Y-%m-%d %H:%M:%S') ==="
  /usr/bin/python3 "$DIR/eval.py"
} >> "$LOG" 2>&1

/usr/bin/osascript -e 'display notification "Report ready: ~/.claude/calibration/eval-latest.md — run /calibration-eval in Claude Code to act on it" with title "Weekly calibration eval"' 2>> "$LOG"
