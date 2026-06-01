<script setup lang="ts">
import type { BlockView, Metric } from '../types'
import { fmtTokens, fmtCost, fmtLocalDay, fmtLocalTime, shortModel } from '../format'

const props = defineProps<{ view: BlockView; metric: Metric }>()

const tc = () => props.view.block.tokenCounts
</script>

<template>
  <div class="card">
    <div class="card-head">
      <span class="dot" :style="{ background: view.color }" />
      <strong>{{ fmtLocalDay(view.block.startTime) }}</strong>
      <span class="muted">{{ fmtLocalTime(view.block.startTime) }}–{{ fmtLocalTime(view.block.endTime) }}</span>
    </div>

    <div class="pct-row">
      <div class="bar-track">
        <div
          class="bar-fill"
          :style="{ width: Math.min(100, view.pct * 100) + '%', background: view.color }"
        />
      </div>
      <span class="pct" :class="{ hot: view.pct >= 0.8 }">{{ (view.pct * 100).toFixed(0) }}%</span>
    </div>
    <div class="muted small">of {{ metric === 'tokens' ? 'token' : 'cost' }} ceiling</div>

    <dl class="kv">
      <div><dt>Tokens</dt><dd>{{ fmtTokens(view.block.totalTokens) }}</dd></div>
      <div><dt>Cost</dt><dd>{{ fmtCost(view.block.costUSD) }}</dd></div>
      <div><dt>Messages</dt><dd>{{ view.block.entries }}</dd></div>
      <div><dt>Models</dt><dd>{{ view.block.models.map(shortModel).join(', ') || '—' }}</dd></div>
    </dl>

    <details class="breakdown">
      <summary>Token breakdown</summary>
      <dl class="kv">
        <div><dt>Input</dt><dd>{{ fmtTokens(tc().inputTokens) }}</dd></div>
        <div><dt>Output</dt><dd>{{ fmtTokens(tc().outputTokens) }}</dd></div>
        <div><dt>Cache write</dt><dd>{{ fmtTokens(tc().cacheCreationInputTokens) }}</dd></div>
        <div><dt>Cache read</dt><dd>{{ fmtTokens(tc().cacheReadInputTokens) }}</dd></div>
      </dl>
    </details>
  </div>
</template>

<style scoped>
.card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  min-width: 240px;
}
.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex: none;
}
.muted {
  color: var(--muted);
}
.small {
  font-size: 11px;
}
.pct-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.bar-track {
  flex: 1;
  height: 8px;
  background: var(--track);
  border-radius: 4px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  border-radius: 4px;
}
.pct {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  min-width: 38px;
  text-align: right;
}
.pct.hot {
  color: #f87171;
}
.kv {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 16px;
  margin: 10px 0 0;
}
.kv > div {
  display: flex;
  justify-content: space-between;
}
.kv dt {
  color: var(--muted);
  margin: 0;
}
.kv dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}
.breakdown {
  margin-top: 10px;
  font-size: 12px;
}
.breakdown summary {
  cursor: pointer;
  color: var(--muted);
}
</style>
