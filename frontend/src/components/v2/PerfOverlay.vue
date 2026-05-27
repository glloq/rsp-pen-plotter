<script setup lang="ts">
// Perf overlay (roadmap C.8).
//
// Floating chip in the bottom-right corner showing live KPIs from
// the perf store. Visible only when the `perf` feature flag is on
// (toggle via `?flag.perf=1` or the persisted store from C.1).
//
// Production-safe by design: zero overhead when hidden, no
// reporting to the backend yet (the D.4 SLO work picks that up).

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFeatureFlag } from '../../composables/useFeatureFlag'
import { usePerfStore } from '../../stores/perf'

const { t } = useI18n()
const enabled = useFeatureFlag('perf')
const store = usePerfStore()

const rows = computed(() =>
  (['time_to_first_preview', 'preview_refresh', 'slow_interaction'] as const).map((kpi) => ({
    kpi,
    ...store.summary(kpi),
  })),
)

const errorCount = computed(() => store.errors)

function fmtMs(v: number): string {
  if (v < 10) return v.toFixed(1) + ' ms'
  if (v < 1_000) return v.toFixed(0) + ' ms'
  return (v / 1_000).toFixed(2) + ' s'
}

function labelFor(kpi: string): string {
  return t(`v2.perf.kpi.${kpi}`)
}
</script>

<template>
  <aside
    v-if="enabled"
    class="perf-overlay"
    data-test="perf-overlay"
    role="complementary"
    aria-label="Performance overlay"
  >
    <header>
      <span>{{ t('v2.perf.title') }}</span>
      <button
        type="button"
        data-test="perf-clear"
        :title="t('v2.perf.clear')"
        @click="store.clear"
      >
        ×
      </button>
    </header>
    <table>
      <thead>
        <tr>
          <th>KPI</th>
          <th>n</th>
          <th>p50</th>
          <th>p95</th>
          <th>last</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.kpi" :data-test="`perf-row-${row.kpi}`">
          <th>{{ labelFor(row.kpi) }}</th>
          <td>{{ row.count }}</td>
          <td>{{ fmtMs(row.p50) }}</td>
          <td>{{ fmtMs(row.p95) }}</td>
          <td>{{ fmtMs(row.last) }}</td>
        </tr>
        <tr>
          <th>{{ t('v2.perf.kpi.errors') }}</th>
          <td colspan="4" data-test="perf-errors">{{ errorCount }}</td>
        </tr>
      </tbody>
    </table>
  </aside>
</template>

<style scoped>
.perf-overlay {
  position: fixed;
  bottom: 12px;
  right: 12px;
  background: rgba(20, 20, 20, 0.92);
  color: #f0f0f0;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.75rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  min-width: 16rem;
  z-index: 9999;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.25rem;
  font-weight: 600;
}
header button {
  background: transparent;
  border: none;
  color: #f0f0f0;
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th,
td {
  text-align: right;
  padding: 0.1rem 0.3rem;
}
th:first-child {
  text-align: left;
  color: #ddd;
}
tbody th {
  font-weight: 400;
}
</style>
