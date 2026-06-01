import { ref, computed } from 'vue'
import type { BlocksResponse, UsageBlock, Metric, BlockView } from '../types'
import { localDayKey, localHour, modelColor, shortModel } from '../format'

// Blocks near the ceiling are the planning signal — "how often do I run hot".
const NEAR_THRESHOLD = 0.8

export function useBlocks() {
  const raw = ref<UsageBlock[]>([])
  const metric = ref<Metric>('tokens')
  // Per-metric ceiling override; null => use the inferred (max observed) ceiling.
  const overrideTokens = ref<number | null>(null)
  const overrideCost = ref<number | null>(null)
  const error = ref<string | null>(null)
  const sourceLabel = ref<string>('')

  function ingest(json: unknown, label: string) {
    try {
      const blocks = (json as BlocksResponse)?.blocks
      if (!Array.isArray(blocks)) throw new Error('JSON has no "blocks" array — is this `ccusage blocks --json` output?')
      raw.value = blocks.filter((b) => !b.isGap) // drop idle gap padding
      sourceLabel.value = label
      error.value = null
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      raw.value = []
    }
  }

  async function loadFile(file: File) {
    try {
      ingest(JSON.parse(await file.text()), file.name)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  async function loadUrl(url: string, label: string): Promise<boolean> {
    try {
      const res = await fetch(url)
      if (!res.ok) return false
      ingest(await res.json(), label)
      return raw.value.length > 0
    } catch {
      return false
    }
  }

  const valueOf = (b: UsageBlock): number => (metric.value === 'tokens' ? b.totalTokens : b.costUSD)

  const blocks = computed(() =>
    [...raw.value].sort((a, b) => a.startTime.localeCompare(b.startTime)),
  )

  const inferredCeiling = computed(() => {
    if (!blocks.value.length) return 0
    return Math.max(...blocks.value.map(valueOf))
  })

  // Active ceiling: explicit override (current metric) or the inferred max.
  const ceiling = computed(() => {
    const ov = metric.value === 'tokens' ? overrideTokens.value : overrideCost.value
    return ov && ov > 0 ? ov : inferredCeiling.value
  })

  const isInferred = computed(() => {
    const ov = metric.value === 'tokens' ? overrideTokens.value : overrideCost.value
    return !(ov && ov > 0)
  })

  function setCeiling(v: number | null) {
    if (metric.value === 'tokens') overrideTokens.value = v
    else overrideCost.value = v
  }

  const pctOf = (b: UsageBlock): number => (ceiling.value > 0 ? valueOf(b) / ceiling.value : 0)

  // Presentation models — built once per metric/ceiling change, consumed by components.
  const views = computed<BlockView[]>(() =>
    blocks.value.map((b) => ({
      block: b,
      day: localDayKey(b.startTime),
      startMs: new Date(b.startTime).getTime(),
      value: valueOf(b),
      pct: pctOf(b),
      color: modelColor(b.models),
      model: shortModel(b.models[0]),
    })),
  )

  const byDay = computed(() => {
    const m = new Map<string, BlockView[]>()
    for (const v of views.value) {
      const arr = m.get(v.day) ?? []
      arr.push(v)
      m.set(v.day, arr)
    }
    return m
  })

  // 24-slot local hour-of-day histogram: when do blocks start, how heavy are they.
  // Drives the planner — lets the user see which windows run hottest.
  const byHour = computed(() => {
    const slots = Array.from({ length: 24 }, (_, h) => ({ hour: h, count: 0, value: 0 }))
    for (const b of blocks.value) {
      const h = localHour(b.startTime)
      slots[h].count += 1
      slots[h].value += valueOf(b)
    }
    return slots
  })

  const stats = computed(() => {
    const list = blocks.value
    const n = list.length
    const totalTokens = list.reduce((s, b) => s + b.totalTokens, 0)
    const totalCost = list.reduce((s, b) => s + b.costUSD, 0)
    const busiest = list.reduce<UsageBlock | null>(
      (max, b) => (!max || valueOf(b) > valueOf(max) ? b : max),
      null,
    )
    const nearCeiling = list.filter((b) => pctOf(b) >= NEAR_THRESHOLD).length
    return {
      count: n,
      totalTokens,
      totalCost,
      avgTokens: n ? totalTokens / n : 0,
      avgCost: n ? totalCost / n : 0,
      busiest,
      nearCeiling,
      nearThresholdPct: NEAR_THRESHOLD,
    }
  })

  const hasData = computed(() => blocks.value.length > 0)

  return {
    // state
    metric,
    error,
    sourceLabel,
    hasData,
    // loaders
    loadFile,
    loadUrl,
    // data
    blocks,
    views,
    byDay,
    byHour,
    stats,
    // ceiling / planning
    valueOf,
    pctOf,
    ceiling,
    inferredCeiling,
    isInferred,
    setCeiling,
  }
}
