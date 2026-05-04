#!/usr/bin/env node
/**
 * Claude Usage Matrix — CLI
 *
 * Terminal-native matrix visualization of token usage.
 *
 * Usage:
 *   node cli.js                   # default reset-day=2 (Tue)
 *   node cli.js --reset-day 1     # Mon-start
 *   node cli.js --no-color        # plain ASCII, no ANSI
 *   node cli.js --weeks N         # show last N weeks
 */

const { execSync } = require('child_process')
const os = require('os')

// ── Parse CLI Args ────────────────────────────────────────────────────────
const args = process.argv.slice(2)
const RESET_DAY = (() => {
  const i = args.indexOf('--reset-day')
  return i !== -1 ? parseInt(args[i+1]) : 2 // default: Tuesday
})()
const NO_COLOR = args.includes('--no-color')
const WEEKS_LIMIT = (() => {
  const i = args.indexOf('--weeks')
  return i !== -1 ? parseInt(args[i+1]) : Infinity
})()

const SOURCE_NAME = process.env.MACHINE_NAME || os.hostname()
const DAY_NAMES = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
const COLS = Array.from({length:7}, (_,i) => (RESET_DAY + i) % 7)
const COL_NAMES = COLS.map(d => DAY_NAMES[d])

// ── ANSI Color Codes ──────────────────────────────────────────────────────
const RESET = '\x1b[0m'
const BOLD = '\x1b[1m'
const DIM = '\x1b[2m'
const YELLOW_BG = '\x1b[103m'
const YELLOW = '\x1b[33m'

const color = (str, code) => NO_COLOR ? str : code + str + RESET

// ── Fetch and Parse Data ──────────────────────────────────────────────────
let dailyData
try {
  const raw = execSync('npx ccusage daily --json', {
    encoding: 'utf-8',
    stdio: ['pipe', 'pipe', 'pipe']
  })
  const parsed = JSON.parse(raw)
  dailyData = parsed.daily || parsed
} catch (err) {
  console.error('\n✗ Could not run ccusage.')
  console.error('  Make sure Node.js is installed and you have Claude Code sessions.\n')
  console.error('  Error:', err.message)
  process.exit(1)
}

// ── Group into Weeks ──────────────────────────────────────────────────────
function getWeekStart(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  const day = d.getDay()
  const diff = (day - RESET_DAY + 7) % 7
  const start = new Date(d)
  start.setDate(d.getDate() - diff)
  return start.toISOString().slice(0, 10)
}

const byDate = {}
for (const e of dailyData) {
  byDate[e.date] = e
}

const weeks = {}
for (const [date, entry] of Object.entries(byDate)) {
  const ws = getWeekStart(date)
  if (!weeks[ws]) weeks[ws] = { entries: {}, total: 0 }
  weeks[ws].entries[date] = entry
  weeks[ws].total += entry.totalCost
}

// Apply weeks limit
const sortedWeeks = Object.keys(weeks).sort()
const displayWeeks = sortedWeeks.slice(-WEEKS_LIMIT)

// ── Render Matrix ─────────────────────────────────────────────────────────
// Header
const colWidths = 8 // width per day column
const weekColWidth = 18
const totalColWidth = 9

let header = color(
  String('Week').padEnd(weekColWidth),
  BOLD
)
for (let i = 0; i < COL_NAMES.length; i++) {
  const colName = COL_NAMES[i]
  const dayOfWeek = COLS[i]
  const isReset = dayOfWeek === RESET_DAY
  const colStr = color(String(colName).padEnd(colWidths), isReset ? YELLOW : '')
  header += colStr
}
header += color(String('Total').padEnd(totalColWidth), BOLD)
console.log(header)
console.log('─'.repeat(header.replace(/\x1b\[[0-9;]*m/g, '').length))

// Data rows
for (const weekKey of displayWeeks) {
  const week = weeks[weekKey]
  const wsDate = new Date(weekKey + 'T00:00:00')

  // Week label (MM-DD format)
  const monthDay = (d) => `${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
  const startStr = monthDay(wsDate)

  // Determine if week is partial
  const endDate = new Date(wsDate)
  endDate.setDate(endDate.getDate() + 6)
  const isFirstWeek = weekKey === sortedWeeks[0]
  const isLastWeek = weekKey === sortedWeeks[sortedWeeks.length - 1]
  const isPartial = isFirstWeek || isLastWeek

  let weekLabel
  if (isPartial) {
    weekLabel = startStr + ' (partial)'
  } else {
    const endStr = monthDay(endDate)
    weekLabel = startStr + '→' + endStr
  }

  let row = String(weekLabel).padEnd(weekColWidth)

  // Day columns
  const cells = []
  for (const dayOfWeek of COLS) {
    const offset = (dayOfWeek - wsDate.getDay() + 7) % 7
    const dateObj = new Date(wsDate)
    dateObj.setDate(wsDate.getDate() + offset)
    const dateStr = dateObj.toISOString().slice(0, 10)

    if (week.entries[dateStr]) {
      const entry = week.entries[dateStr]
      const pct = Math.round(entry.totalCost / week.total * 100)
      const cost = entry.totalCost.toFixed(2)
      cells.push({ pct, cost, dateStr })
    } else {
      cells.push(null)
    }
  }

  // Format cells on first line
  for (const cell of cells) {
    if (cell) {
      const pctStr = color(String(cell.pct + '%').padEnd(colWidths), BOLD)
      row += pctStr
    } else {
      row += '░░░'.padEnd(colWidths)
    }
  }

  // Total
  const totalStr = '$' + week.total.toFixed(2)
  row += String(totalStr).padEnd(totalColWidth)

  console.log(row)

  // Second line: costs and bars
  let row2 = ' '.repeat(weekColWidth)
  for (const cell of cells) {
    if (cell) {
      const costStr = '$' + cell.cost
      row2 += color(String(costStr).padEnd(colWidths), DIM)
    } else {
      row2 += ' '.repeat(colWidths)
    }
  }
  console.log(row2)
}

// ── Stats ─────────────────────────────────────────────────────────────────
console.log('─'.repeat(70))

const totalSpend = Object.values(weeks).reduce((sum, w) => sum + w.total, 0)
const peakWeek = Math.max(...Object.values(weeks).map(w => w.total))
const activeDays = Object.values(weeks).reduce((count, w) => count + Object.keys(w.entries).length, 0)
const avgPerDay = activeDays > 0 ? totalSpend / activeDays : 0

console.log(
  color(`Total: $${totalSpend.toFixed(2)}`, BOLD) +
  ` | Peak week: $${peakWeek.toFixed(2)} | Avg/day: $${avgPerDay.toFixed(2)} | Weeks: ${displayWeeks.length}`
)
