// ccusage `blocks --json` shapes. A "block" = one rolling 5h billing window.
// Closed (historical) blocks may carry burnRate/projection as null OR populated,
// so both are nullable rather than absent. Gap rows (isGap:true) are idle padding.

export interface TokenCounts {
  inputTokens: number
  outputTokens: number
  cacheCreationInputTokens: number
  cacheReadInputTokens: number
}

export interface BurnRate {
  tokensPerMinute: number
  tokensPerMinuteForIndicator?: number
  costPerHour: number
}

export interface Projection {
  totalTokens: number
  totalCost: number
  remainingMinutes: number
}

export interface UsageBlock {
  id: string
  startTime: string
  endTime: string
  actualEndTime?: string | null
  isActive: boolean
  isGap: boolean
  entries: number
  tokenCounts: TokenCounts
  totalTokens: number
  costUSD: number
  models: string[]
  burnRate?: BurnRate | null
  projection?: Projection | null
}

export interface BlocksResponse {
  blocks: UsageBlock[]
}

export type Metric = 'tokens' | 'cost'

// Pre-computed presentation model for one block (built once, consumed by components).
export interface BlockView {
  block: UsageBlock
  day: string // local YYYY-MM-DD
  startMs: number
  value: number // tokens or cost, per active metric
  pct: number // value / ceiling, 0..1+ (may exceed 1 if ceiling overridden low)
  color: string // dominant-model color
  model: string // dominant (first) model, shortened
}
