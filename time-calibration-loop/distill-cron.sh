#!/bin/bash
# Daily DISTILL: re-tag durations.log from transcript PREDICT lines and re-derive the
# priors bands. Run by LaunchAgent com.kozystay.calibration-distill (see install.sh).
# The budget (k) column is deliberately untouched by backfill.py — bands describe,
# budgets prescribe.
LOG="$HOME/.claude/calibration/distill.log"
DIR="$(cd "$(dirname "$0")" && pwd)"

# keep the log from growing unbounded
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 2000 ]; then
  tail -500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

{
  echo "=== distill $(date '+%Y-%m-%d %H:%M:%S') ==="
  /usr/bin/python3 "$DIR/backfill.py"
} >> "$LOG" 2>&1
