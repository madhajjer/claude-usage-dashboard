---
name: usage-matrix
description: Display Claude token usage matrix directly in the terminal without opening a browser. Shows weekly breakdown of token spend with colors and stats.
repo: https://github.com/ahmadmuhajir/claude-usage-dashboard
requires: Node.js 16+, npx, Claude Code
---

# Usage Matrix

Quick terminal view of your Claude Code token usage across days of the week.

## Quick Install

```bash
# 1. Clone the repo
git clone https://github.com/ahmadmuhajir/claude-usage-dashboard.git
cd claude-usage-dashboard

# 2. Create skill directory
mkdir -p ~/.agents/skills/usage-matrix

# 3. Create run.sh script (copy this entire block)
cat > ~/.agents/skills/usage-matrix/run.sh << 'EOF'
#!/bin/bash
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo $(pwd))"
node cli.js "$@"
EOF
chmod +x ~/.agents/skills/usage-matrix/run.sh

# 4. Copy skill metadata
cp SKILL.md ~/.agents/skills/usage-matrix/

# 5. Create symlink
ln -s ../../.agents/skills/usage-matrix ~/.claude/skills/usage-matrix

# Done! The skill is now available as /usage-matrix
```

## When to Use This Skill

Use this skill when you want to:
- Check your token spend for the current/past weeks
- See a quick usage breakdown without opening a browser
- Run during active development sessions
- Pipe output to logs or other tools
- Filter to specific weeks or reset the week start day

## Installation Details

**What gets installed:**
- **Location:** `~/.agents/skills/usage-matrix/` (skill definition) + symlink at `~/.claude/skills/usage-matrix`
- **Files:** `run.sh` (executable) and `SKILL.md` (metadata)
- **Working directory:** Automatically detects the cloned repo directory

**Requirements before installing:**
- Node.js 16+ with `npm` or `npx`
- Claude Code with agent/skill support
- Existing Claude Code sessions in `~/.claude/projects/`

**Troubleshooting:**
- If `/usage-matrix` doesn't appear after installing, restart Claude Code
- If `run.sh` fails, ensure it's executable: `chmod +x ~/.agents/skills/usage-matrix/run.sh`
- If `node cli.js` can't find dependencies, run `npm install` in the cloned repository

## How to Use

```
/usage-matrix                    # Show all weeks, Wed-start (default)
/usage-matrix --weeks 2          # Show last 2 weeks only
/usage-matrix --reset-day 0      # Change week start (0=Sun, 1=Mon, etc.)
/usage-matrix --no-color         # Plain ASCII (no ANSI colors, good for logs)
```

## Examples

**Quick check (last 2 weeks):**
```
/usage-matrix --weeks 2
```

**Monday-based weeks:**
```
/usage-matrix --reset-day 1
```

**For log files (no colors):**
```
/usage-matrix --no-color
```

## Output

Matrix showing:
- **Week column**: date range (MM-DD format)
- **Day columns**: percentage and cost per day
- **Total column**: weekly spend
- **Stats line**: total spend, peak week, avg per active day, week count

Active days are bold; empty days are dimmed (`░░░`). The reset-day column is highlighted in yellow.

## Implementation

The skill runs `node cli.js` from the project root with your arguments.

Data is fetched fresh from Claude Code sessions via `ccusage` each time you run it.
