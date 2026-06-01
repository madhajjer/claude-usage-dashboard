// Shared formatters + model palette. Kept framework-free so any component can import.

// Palette echoes the root dashboard's model colors for cross-app consistency.
const MODEL_COLORS: Record<string, string> = {
  opus: '#c084fc', // purple
  sonnet: '#60a5fa', // blue
  haiku: '#34d399', // green
}
const FALLBACK_COLOR = '#94a3b8'

export function shortModel(name: string | undefined): string {
  if (!name) return 'unknown'
  const m = name.toLowerCase()
  if (m.includes('opus')) return 'opus'
  if (m.includes('sonnet')) return 'sonnet'
  if (m.includes('haiku')) return 'haiku'
  return name
}

// Color by the block's dominant (first-listed) model.
export function modelColor(models: string[]): string {
  const key = shortModel(models[0])
  return MODEL_COLORS[key] ?? FALLBACK_COLOR
}

export function fmtTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(n >= 10_000_000 ? 1 : 2) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(0) + 'K'
  return String(n)
}

export function fmtCost(n: number): string {
  return '$' + n.toFixed(2)
}

const DAY_FMT = new Intl.DateTimeFormat(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
const TIME_FMT = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' })

export function fmtLocalDay(iso: string): string {
  return DAY_FMT.format(new Date(iso))
}

export function fmtLocalTime(iso: string): string {
  return TIME_FMT.format(new Date(iso))
}

// Local YYYY-MM-DD (NOT iso.slice(0,10), which is UTC). Groups by the user's own day.
export function localDayKey(iso: string): string {
  const d = new Date(iso)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function localHour(iso: string): number {
  return new Date(iso).getHours()
}

// "2pm", "12am" — compact hour label for the time-of-day planner.
export function fmtHour(h: number): string {
  const period = h < 12 ? 'am' : 'pm'
  const h12 = h % 12 === 0 ? 12 : h % 12
  return `${h12}${period}`
}
