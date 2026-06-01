# Block Usage Dashboard

Visualizes **historical 5-hour billing blocks** from Claude Code usage data so you can
see how hard each block ran, spot when you tend to run hot, and plan demanding work to
avoid hitting the per-block limit mid-task.

Each block is one rolling 5h window Claude tracks for billing. This app shows the
*already-closed* blocks (the live in-progress block is intentionally out of scope —
see `../HANDOFF_active_block_monitoring.md` for that separate idea).

Built as a standalone **Vue 3 + TypeScript + Vite** SPA, independent of the root
`dashboard.html`.

## Quick start

```bash
cd block-dashboard
npm install
npm run dev        # http://localhost:5173
```

On load the app tries `blocks.json` (your real local export, git-ignored), then falls
back to the bundled `demo_blocks.json` so it always renders something.

### Use your own data

```bash
npx ccusage blocks --json > public/blocks.json   # served automatically in dev
# — or — open the app and use the "Upload" button to load any blocks JSON
```

`public/blocks.json` is git-ignored (it holds your real token/cost numbers). The
committed `public/demo_blocks.json` is synthetic sample data for the public demo.

### Build / deploy

```bash
npm run build      # type-checks with vue-tsc, then builds to dist/
npm run preview    # serve the production build locally
```

`vite.config.ts` sets `base: './'`, so `dist/` deploys to any static host or GitHub
Pages sub-path. Upload still works there; `blocks.json` autoload only applies if you
place that file alongside the deployed app.

## How to read it

- **Stats bar** — total blocks, total tokens, total cost, average per block, and how
  many blocks ran **near the ceiling** (≥80%). Toggle the metric between **Tokens** and
  **Cost** (cache reads inflate token totals, so cost is often the truer "weight").
- **Each block vs ceiling** — one bar per block, chronological, grouped by **local**
  day. Bar height = that block's share of the ceiling. Bars ≥80% are red-edged; a ▲
  marks a block over a manually-lowered ceiling. Hover/click a bar for full detail.
- **When do your heavy blocks happen?** — a local hour-of-day histogram. The cluster of
  tall bars is your real planning signal: start heavy work early in a fresh block during
  those windows so a mid-task limit doesn't catch you.
- **Block detail** — tokens, cost, message count, models, and the input/output/cache
  breakdown for the selected block.

### The ceiling

The ceiling defaults to your **busiest observed block** (ccusage's own convention for
inferring a cap) and is labeled **inferred**. It is **not** a verified plan cap — Pro vs
Max limits aren't derivable from this data. Edit the **Block ceiling** field to set your
own (it switches to **manual**); clear it to return to inferred. Because the inferred
ceiling equals the busiest block, that one block always reads 100% — read the *cluster*
of near-ceiling blocks, not the single max, as "how often I run hot."

## Data notes

- **Gap rows** (`isGap: true`, idle padding, 0 tokens) are filtered out on load.
- **Local-day grouping** — blocks are bucketed by your local calendar day (not UTC), to
  match "when do *I* work."
- `burnRate` / `projection` may be `null` or populated on closed blocks; this historical
  view doesn't render forecasts.

## Project layout

```
block-dashboard/
├── index.html
├── vite.config.ts            # base: './'
├── public/
│   ├── demo_blocks.json      # committed synthetic sample (demo / Pages)
│   └── blocks.json           # your real export (git-ignored)
└── src/
    ├── main.ts
    ├── App.vue               # layout + data input + hour-of-day planner
    ├── types.ts              # ccusage block shapes + BlockView
    ├── format.ts             # formatters + model palette + local-day helpers
    ├── composables/
    │   └── useBlocks.ts       # load → filter gaps → sort → stats → ceiling/pct
    └── components/
        ├── StatsBar.vue       # totals, metric toggle, ceiling control
        ├── BlockTimeline.vue  # bars vs ceiling, grouped by local day
        └── BlockCard.vue      # single-block detail
```

## Requirements

- Node.js (tested on 25.x; Node 18+ recommended)
- `ccusage` for exports: `npx ccusage blocks --json`
