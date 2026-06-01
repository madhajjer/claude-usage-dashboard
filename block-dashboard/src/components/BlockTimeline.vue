<script setup lang="ts">
import { computed } from 'vue'
import type { BlockView } from '../types'
import { fmtLocalDay, fmtLocalTime, fmtTokens, fmtCost } from '../format'

const props = defineProps<{
  views: BlockView[]
  selectedId: string | null
}>()

const emit = defineEmits<{ (e: 'select', v: BlockView): void }>()

// Group consecutive blocks by local day so the axis reads as day columns.
const groups = computed(() => {
  const out: { day: string; label: string; items: BlockView[] }[] = []
  for (const v of props.views) {
    let g = out[out.length - 1]
    if (!g || g.day !== v.day) {
      g = { day: v.day, label: fmtLocalDay(v.block.startTime), items: [] }
      out.push(g)
    }
    g.items.push(v)
  }
  return out
})

function tip(v: BlockView): string {
  return `${fmtLocalTime(v.block.startTime)} · ${fmtTokens(v.block.totalTokens)} · ${fmtCost(
    v.block.costUSD,
  )} · ${(v.pct * 100).toFixed(0)}% of ceiling`
}
</script>

<template>
  <div class="timeline">
    <!-- y-axis ceiling guide -->
    <div class="chart">
      <div class="ceiling-line"><span class="ceiling-tag">ceiling 100%</span></div>
      <div class="grid-line" style="bottom: 80%"></div>
      <div class="grid-line" style="bottom: 50%"></div>

      <div class="groups">
        <div v-for="g in groups" :key="g.day" class="day-group">
          <div class="bars">
            <button
              v-for="v in g.items"
              :key="v.block.id"
              class="bar-wrap"
              :class="{ selected: v.block.id === selectedId }"
              :title="tip(v)"
              @mouseenter="emit('select', v)"
              @focus="emit('select', v)"
              @click="emit('select', v)"
            >
              <span v-if="v.pct > 1" class="over">▲</span>
              <span
                class="bar"
                :class="{ hot: v.pct >= 0.8 }"
                :style="{
                  height: Math.max(2, Math.min(100, v.pct * 100)) + '%',
                  background: v.color,
                }"
              />
            </button>
          </div>
          <div class="day-label">{{ g.label }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.timeline {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 18px 8px;
}
.chart {
  position: relative;
  height: 260px;
  overflow-x: auto;
  overflow-y: hidden;
}
.ceiling-line {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  border-top: 2px dashed rgba(248, 113, 113, 0.55);
  z-index: 2;
  pointer-events: none;
}
.ceiling-tag {
  position: absolute;
  right: 0;
  top: -9px;
  font-size: 10px;
  color: #f87171;
  background: var(--panel);
  padding: 0 4px;
}
.grid-line {
  position: absolute;
  left: 0;
  right: 0;
  border-top: 1px solid var(--border);
  opacity: 0.5;
  pointer-events: none;
}
.groups {
  display: flex;
  align-items: flex-end;
  gap: 18px;
  height: 100%;
  min-width: min-content;
  padding-bottom: 22px; /* room for day labels */
}
.day-group {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  height: 100%;
}
.bars {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 100%;
  border-left: 1px solid var(--border);
  padding: 0 6px;
}
.bar-wrap {
  position: relative;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  width: 18px;
  height: 100%;
  padding: 0;
  background: none;
  border: none;
  cursor: pointer;
}
.bar {
  display: block;
  width: 100%;
  border-radius: 3px 3px 0 0;
  transition: filter 0.1s;
}
.bar.hot {
  box-shadow: 0 0 0 1px rgba(248, 113, 113, 0.6) inset;
}
.bar-wrap:hover .bar,
.bar-wrap.selected .bar {
  filter: brightness(1.25);
}
.bar-wrap.selected {
  outline: 1px solid var(--accent);
  outline-offset: 2px;
  border-radius: 4px;
}
.over {
  position: absolute;
  top: -2px;
  font-size: 9px;
  color: #f87171;
}
.day-label {
  font-size: 10px;
  color: var(--muted);
  text-align: center;
  margin-top: 6px;
  white-space: nowrap;
}
</style>
