<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useBlocks } from './composables/useBlocks'
import type { BlockView } from './types'
import StatsBar from './components/StatsBar.vue'
import BlockTimeline from './components/BlockTimeline.vue'
import BlockCard from './components/BlockCard.vue'
import { fmtHour, fmtTokens, fmtCost } from './format'
import CalibrationApp from './calibration/CalibrationApp.vue'

const view = ref<'blocks' | 'calibration'>('blocks')

const {
  metric,
  error,
  sourceLabel,
  hasData,
  loadFile,
  loadUrl,
  views,
  byHour,
  stats,
  ceiling,
  isInferred,
  setCeiling,
} = useBlocks()

const selectedId = ref<string | null>(null)
const selected = computed<BlockView | null>(
  () => views.value.find((v) => v.block.id === selectedId.value) ?? views.value[views.value.length - 1] ?? null,
)

function onSelect(v: BlockView) {
  selectedId.value = v.block.id
}

async function onFile(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) await loadFile(f)
}

// Hour-of-day planner: normalize bar heights against the busiest hour.
const maxHourValue = computed(() => Math.max(1, ...byHour.value.map((s) => s.value)))
const heaviestHour = computed(() => {
  const s = [...byHour.value].sort((a, b) => b.value - a.value)[0]
  return s && s.value > 0 ? s.hour : null
})

const ceilingLabel = computed(() =>
  metric.value === 'tokens' ? fmtTokens(ceiling.value) : fmtCost(ceiling.value),
)

onMounted(async () => {
  // Prefer a locally-served real export; fall back to the bundled demo so the
  // app always renders (and works as a static Pages demo). Upload overrides both.
  const real = await loadUrl(import.meta.env.BASE_URL + 'blocks.json', 'blocks.json')
  if (!real) await loadUrl(import.meta.env.BASE_URL + 'demo_blocks.json', 'demo data')
})
</script>

<template>
  <div class="app">
    <nav class="tabs">
      <button :class="{ on: view === 'blocks' }" @click="view = 'blocks'">Blocks</button>
      <button :class="{ on: view === 'calibration' }" @click="view = 'calibration'">Calibration</button>
    </nav>
    <CalibrationApp v-if="view === 'calibration'" />
    <template v-else>
    <header class="head">
      <div>
        <h1>Block Usage Dashboard</h1>
        <p class="sub">
          Historical 5-hour billing blocks — see how hard each window ran so you can
          plan heavy work and avoid hitting the limit mid-task.
        </p>
      </div>
      <div class="inputs">
        <label class="btn">
          Upload <code>ccusage blocks --json</code>
          <input type="file" accept="application/json,.json" @change="onFile" hidden />
        </label>
        <span v-if="sourceLabel" class="source">source: {{ sourceLabel }}</span>
      </div>
    </header>

    <p v-if="error" class="error">⚠ {{ error }}</p>

    <template v-if="hasData">
      <StatsBar
        :stats="stats"
        :metric="metric"
        :ceiling="ceiling"
        :is-inferred="isInferred"
        @update:metric="metric = $event"
        @set-ceiling="setCeiling"
      />

      <section class="panel-row">
        <div class="primary">
          <h2>Each block vs ceiling</h2>
          <BlockTimeline :views="views" :selected-id="selectedId" @select="onSelect" />
          <p class="legend">
            Bars = {{ metric === 'tokens' ? 'tokens' : 'cost' }} per block as a share of the
            <strong>{{ isInferred ? 'inferred' : 'manual' }}</strong> ceiling ({{ ceilingLabel }}).
            Red-edged bars ran ≥80%. Grouped by local day · hover a bar for detail.
          </p>
        </div>

        <aside class="detail" v-if="selected">
          <h2>Block detail</h2>
          <BlockCard :view="selected" :metric="metric" />
        </aside>
      </section>

      <section class="planner">
        <h2>When do your heavy blocks happen?</h2>
        <p class="insight">
          <template v-if="heaviestHour !== null">
            Busiest window starts around <strong>{{ fmtHour(heaviestHour) }}</strong> (local).
          </template>
          <strong>{{ stats.nearCeiling }}</strong> of {{ stats.count }} blocks ran ≥80% of the
          {{ isInferred ? 'inferred' : 'set' }} ceiling — start demanding work early in a fresh
          block so a mid-task limit doesn't catch you.
        </p>
        <div class="hours">
          <div v-for="s in byHour" :key="s.hour" class="hour">
            <div class="hbar-track">
              <div
                class="hbar"
                :style="{ height: (s.value / maxHourValue) * 100 + '%' }"
                :title="`${fmtHour(s.hour)}: ${s.count} block(s)`"
              />
            </div>
            <div class="hlabel" :class="{ tick: s.hour % 6 === 0 }">
              {{ s.hour % 6 === 0 ? fmtHour(s.hour) : '' }}
            </div>
          </div>
        </div>
      </section>
    </template>

    <section v-else class="empty">
      <h2>No block data loaded</h2>
      <p>Generate an export and upload it, or drop it next to the app as <code>blocks.json</code>:</p>
      <pre>npx ccusage blocks --json &gt; blocks.json</pre>
      <p class="muted">
        Gap rows (idle padding) are filtered automatically. This view is historical;
        live in-progress blocks are out of scope here.
      </p>
    </section>

    <footer class="foot">
      <span>Ceiling is <strong>inferred</strong> from your busiest observed block (ccusage convention) and is editable — it is not a verified plan cap.</span>
    </footer>
    </template>
  </div>
</template>

<style scoped>
.tabs { display: flex; gap: 4px; margin-bottom: 4px; }
.tabs button { background: var(--track); border: 1px solid var(--border); color: var(--muted); padding: 6px 16px; border-radius: 9px; cursor: pointer; font-size: 13px; font-weight: 600; }
.tabs button.on { background: var(--accent); color: #0b1020; }
.app {
  max-width: 1180px;
  margin: 0 auto;
  padding: 28px 24px 60px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
  flex-wrap: wrap;
}
h1 {
  margin: 0;
  font-size: 24px;
}
.sub {
  margin: 6px 0 0;
  color: var(--muted);
  max-width: 560px;
  line-height: 1.45;
}
.inputs {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}
.btn {
  background: var(--accent);
  color: #0b1020;
  font-weight: 600;
  padding: 9px 14px;
  border-radius: 9px;
  cursor: pointer;
  font-size: 13px;
}
.btn code {
  background: rgba(0, 0, 0, 0.18);
  padding: 1px 5px;
  border-radius: 5px;
  font-size: 12px;
}
.source {
  font-size: 12px;
  color: var(--muted);
}
.error {
  background: rgba(248, 113, 113, 0.12);
  border: 1px solid rgba(248, 113, 113, 0.4);
  color: #fca5a5;
  padding: 10px 14px;
  border-radius: 9px;
  margin: 0;
}
h2 {
  font-size: 15px;
  margin: 0 0 10px;
  color: var(--text);
}
.panel-row {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 18px;
  align-items: start;
}
.legend {
  color: var(--muted);
  font-size: 12px;
  margin: 10px 2px 0;
  line-height: 1.5;
}
.planner {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px;
}
.insight {
  color: var(--muted);
  margin: 0 0 14px;
  line-height: 1.5;
  max-width: 760px;
}
.insight strong {
  color: var(--text);
}
.hours {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 90px;
}
.hour {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
}
.hbar-track {
  flex: 1;
  display: flex;
  align-items: flex-end;
}
.hbar {
  width: 100%;
  background: var(--accent);
  border-radius: 3px 3px 0 0;
  min-height: 0;
  opacity: 0.85;
}
.hlabel {
  height: 14px;
  font-size: 10px;
  color: var(--muted);
  text-align: left;
}
.empty {
  background: var(--panel);
  border: 1px dashed var(--border);
  border-radius: 12px;
  padding: 40px;
  text-align: center;
}
.empty pre {
  display: inline-block;
  background: var(--track);
  padding: 10px 16px;
  border-radius: 8px;
  margin: 8px 0;
}
.muted {
  color: var(--muted);
}
.foot {
  color: var(--muted);
  font-size: 12px;
  border-top: 1px solid var(--border);
  padding-top: 14px;
}
@media (max-width: 820px) {
  .panel-row {
    grid-template-columns: 1fr;
  }
}
</style>
