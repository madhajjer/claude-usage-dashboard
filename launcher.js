#!/usr/bin/env node
/**
 * Claude Usage Matrix — Launcher
 *
 * Usage:
 *   node launcher.js              # runs ccusage on this machine, opens browser
 *   node launcher.js --port 4000  # custom port
 *   node launcher.js --no-open    # skip auto-opening browser
 */

const { execSync, exec } = require('child_process')
const http = require('http')
const fs = require('fs')
const path = require('path')
const url = require('url')

const args = process.argv.slice(2)
const PORT = (() => {
  const i = args.indexOf('--port')
  return i !== -1 ? parseInt(args[i+1]) : 3131
})()
const NO_OPEN = args.includes('--no-open')
const RESET_DAY = (() => {
  const i = args.indexOf('--reset-day')
  return i !== -1 ? parseInt(args[i+1]) : 2 // default: Tuesday
})()

const DIST_DIR = __dirname

// ── Step 1: Run ccusage ───────────────────────────────────────────────────────
console.log('\n  Claude Usage Matrix\n  ────────────────────')
console.log('  → Running ccusage to collect session data...')

let dailyData
try {
  const raw = execSync('npx ccusage daily --json', {
    encoding: 'utf-8',
    stdio: ['pipe', 'pipe', 'pipe']
  })
  const parsed = JSON.parse(raw)
  dailyData = parsed.daily || parsed
  console.log(`  ✓ Found ${dailyData.length} days of session data`)
} catch (err) {
  console.error('\n  ✗ Could not run ccusage.')
  console.error('    Make sure Node.js is installed and you have Claude Code sessions.\n')
  console.error('    Error:', err.message)
  process.exit(1)
}

// ── Step 2: Process data ──────────────────────────────────────────────────────
const DAY_NAMES = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
const COLS = Array.from({length:7}, (_,i) => (RESET_DAY + i) % 7)
const COL_NAMES = COLS.map(d => DAY_NAMES[d])
const SOURCE_NAME = process.env.MACHINE_NAME || require('os').hostname()

// Merge by date (single machine here, but structure supports multi-machine)
const byDate = {}
for (const e of dailyData) {
  byDate[e.date] = { ...e, _devices: [SOURCE_NAME] }
}

// Group into weeks
function fmtLocal(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const da = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${da}`
}
function getWeekStart(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  const day = d.getDay()
  const diff = (day - RESET_DAY + 7) % 7
  const start = new Date(d)
  start.setDate(d.getDate() - diff)
  return fmtLocal(start)
}

const weeks = {}
for (const [date, entry] of Object.entries(byDate)) {
  const ws = getWeekStart(date)
  if (!weeks[ws]) weeks[ws] = { entries: {}, total: 0 }
  weeks[ws].entries[date] = entry
  weeks[ws].total += entry.totalCost
}

const payload = {
  sources: [SOURCE_NAME],
  weeks,
  cols: COLS,
  colNames: COL_NAMES,
  resetDay: RESET_DAY,
  generatedAt: new Date().toISOString()
}

// Write to usage_data.json (served by the local server)
const dataPath = path.join(DIST_DIR, 'usage_data.json')
fs.writeFileSync(dataPath, JSON.stringify(payload, null, 2))
console.log(`  ✓ Processed ${Object.keys(weeks).length} weeks`)

// ── Step 3: Serve dashboard ───────────────────────────────────────────────────
const MIME = {
  '.html': 'text/html',
  '.json': 'application/json',
  '.css':  'text/css',
  '.js':   'text/javascript',
}

const server = http.createServer((req, res) => {
  let pathname = url.parse(req.url).pathname
  if (pathname === '/' || pathname === '') pathname = '/dashboard.html'

  const filePath = path.join(DIST_DIR, pathname)

  if (!filePath.startsWith(DIST_DIR)) {
    res.writeHead(403); res.end(); return
  }

  if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
    const ext = path.extname(filePath)
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'text/plain' })
    res.end(fs.readFileSync(filePath))
  } else {
    res.writeHead(404); res.end('Not found')
  }
})

server.listen(PORT, '127.0.0.1', () => {
  const dashURL = `http://localhost:${PORT}/?autoload`
  console.log(`\n  ✓ Dashboard ready at ${dashURL}`)

  if (!NO_OPEN) {
    console.log('  → Opening browser...\n')
    // Cross-platform browser open
    const platform = process.platform
    const openCmd = platform === 'darwin' ? `open "${dashURL}"`
                  : platform === 'win32'  ? `start "" "${dashURL}"`
                  : `xdg-open "${dashURL}"`
    exec(openCmd, err => {
      if (err) console.log(`  Could not open browser automatically. Visit: ${dashURL}`)
    })
  }

  console.log('  Press Ctrl+C to stop.\n')
})

server.on('error', err => {
  if (err.code === 'EADDRINUSE') {
    console.error(`\n  ✗ Port ${PORT} already in use. Try: node launcher.js --port 4000\n`)
  } else {
    console.error('\n  ✗ Server error:', err.message)
  }
  process.exit(1)
})
