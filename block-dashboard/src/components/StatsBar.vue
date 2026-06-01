<script setup lang="ts">
import { computed } from 'vue'
import type { Metric } from '../types'
import { fmtTokens, fmtCost } from '../format'

const props = defineProps<{
  stats: {
    count: number
    totalTokens: number
    totalCost: number
    avgTokens: number
    avgCost: number
    nearCeiling: number
    nearThresholdPct: number
  }
  metric: Metric
  ceiling: number
  isInferred: boolean
}>()

const emit = defineEmits<{
  (e: 'update:metric', m: Metric): void
  (e: 'set-ceiling', v: number | null): void
}>()

const unit = computed(() => (props.metric === 'tokens' ? 'M tokens' : '$'))

// Ceiling shown in friendly units: millions for tokens, dollars for cost.
const ceilingDisplay = computed({
  get: () =>
    props.metric === 'tokens'
      ? (props.ceiling / 1_000_000).toFixed(2)
      : props.ceiling.toFixed(2),
  set: (raw: string) => {
    const n = parseFloat(raw)
    if (!isFinite(n) || n <= 0) {
      emit('set-ceiling', null) // empty/invalid => back to inferred
      return
    }
    emit('set-ceiling', props.metric === 'tokens' ? n * 1_000_000 : n)
  },
})
</script>

<template>
  <div class="statsbar">
    <div class="stat">
      <div class="label">Blocks</div>
      <div class="value">{{ stats.count }}</div>
    </div>
    <div class="stat">
      <div class="label">Total tokens</div>
      <div class="value">{{ fmtTokens(stats.totalTokens) }}</div>
    </div>
    <div class="stat">
      <div class="label">Total cost</div>
      <div class="value">{{ fmtCost(stats.totalCost) }}</div>
    </div>
    <div class="stat">
      <div class="label">Avg / block</div>
      <div class="value">
        {{ metric === 'tokens' ? fmtTokens(stats.avgTokens) : fmtCost(stats.avgCost) }}
      </div>
    </div>
    <div class="stat hot-stat">
      <div class="label">Near ceiling (≥{{ (stats.nearThresholdPct * 100).toFixed(0) }}%)</div>
      <div class="value" :class="{ warn: stats.nearCeiling > 0 }">{{ stats.nearCeiling }}</div>
    </div>

    <div class="spacer" />

    <div class="control">
      <div class="label">Metric</div>
      <div class="toggle">
        <button :class="{ on: metric === 'tokens' }" @click="emit('update:metric', 'tokens')">Tokens</button>
        <button :class="{ on: metric === 'cost' }" @click="emit('update:metric', 'cost')">Cost</button>
      </div>
    </div>

    <div class="control">
      <div class="label">
        Block ceiling
        <span class="badge" :class="isInferred ? 'inferred' : 'manual'">
          {{ isInferred ? 'inferred' : 'manual' }}
        </span>
      </div>
      <div class="ceiling-input">
        <input
          type="number"
          step="0.01"
          min="0"
          v-model="ceilingDisplay"
          :placeholder="isInferred ? 'auto' : ''"
        />
        <span class="unit">{{ unit }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.statsbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 22px;
  padding: 16px 18px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
}
.stat .label,
.control .label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
  margin-bottom: 4px;
}
.stat .value {
  font-size: 22px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}
.value.warn {
  color: #fbbf24;
}
.spacer {
  flex: 1;
}
.toggle {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
.toggle button {
  background: transparent;
  color: var(--muted);
  border: none;
  padding: 6px 14px;
  cursor: pointer;
  font-size: 13px;
}
.toggle button.on {
  background: var(--accent);
  color: #0b1020;
  font-weight: 600;
}
.badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 999px;
  margin-left: 4px;
  vertical-align: middle;
}
.badge.inferred {
  background: rgba(96, 165, 250, 0.18);
  color: #93c5fd;
}
.badge.manual {
  background: rgba(192, 132, 252, 0.18);
  color: #d8b4fe;
}
.ceiling-input {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ceiling-input input {
  width: 90px;
  background: var(--track);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 8px;
  padding: 6px 8px;
  font-variant-numeric: tabular-nums;
}
.ceiling-input .unit {
  color: var(--muted);
  font-size: 12px;
}
</style>
