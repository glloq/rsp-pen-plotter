<script setup lang="ts">
// SLO dashboard (roadmap D.3 + Block D wire).
//
// Lists the configured SLO budgets and exposes a one-click
// `evaluate` against the in-memory perf samples that the operator
// (or the app) has accumulated. The eval call posts those samples to
// the backend, which returns the verdict table.
//
// This is intentionally read-only — budget tuning lives in the
// backend config / domain/slo. The dashboard only surfaces the live
// state so the operator can spot regressions without leaving the UI.

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  evaluateSloBudgets,
  getSloBudgets,
  type SloBudget,
  type SloBudgetReport,
  type SloMetricSample,
} from '../api/client'
import { errorDetail } from '../api/error'
import { usePerfStore, type PerfKpi } from '../stores/perf'

const { t } = useI18n()
const perf = usePerfStore()
const budgets = ref<SloBudget[]>([])
const report = ref<SloBudgetReport | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

// Map the in-memory perf KPI ids to the backend metric names. The
// backend uses snake_case identifiers tied to the budget table;
// keep this mapping local so the perf store doesn't have to know
// about SLO metric names.
const KPI_TO_METRIC: Partial<Record<PerfKpi, string>> = {
  time_to_first_preview: 'preview_draft_ms',
  preview_refresh: 'preview_refresh_ms',
  slow_interaction: 'slow_interaction_ms',
}

const samples = computed<SloMetricSample[]>(() => {
  const out: SloMetricSample[] = []
  for (const sample of perf.samples) {
    const metric = KPI_TO_METRIC[sample.kpi]
    if (!metric) continue
    out.push({ metric, value_ms: sample.value })
  }
  return out
})

async function refreshBudgets(): Promise<void> {
  loading.value = true
  try {
    budgets.value = await getSloBudgets()
    error.value = null
  } catch (err) {
    error.value = errorDetail(err, t('slo.loadFailed'))
  } finally {
    loading.value = false
  }
}

async function runEvaluation(): Promise<void> {
  if (!samples.value.length) {
    report.value = null
    error.value = t('slo.noSamples')
    return
  }
  loading.value = true
  error.value = null
  try {
    report.value = await evaluateSloBudgets(samples.value)
  } catch (err) {
    error.value = errorDetail(err, t('slo.evaluateFailed'))
  } finally {
    loading.value = false
  }
}

function severityClass(severity: string): string {
  if (severity === 'breach') return 'badge badge-breach'
  if (severity === 'warning') return 'badge badge-warning'
  return 'badge badge-healthy'
}

function statusOf(metric: string) {
  return report.value?.statuses.find((s) => s.budget.metric === metric) ?? null
}

onMounted(refreshBudgets)
</script>

<template>
  <section class="space-y-4 text-sm text-slate-200" data-test="slo-panel">
    <header class="flex items-center justify-between">
      <h3 class="text-base font-semibold">{{ t('slo.title') }}</h3>
      <button
        type="button"
        class="rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700 disabled:opacity-40"
        :disabled="loading"
        data-test="slo-evaluate"
        @click="runEvaluation"
      >
        {{ t('slo.evaluateNow') }}
      </button>
    </header>

    <p class="text-xs text-slate-400">
      {{ t('slo.intro', { count: samples.length }) }}
    </p>

    <p v-if="error" class="text-xs text-red-400">{{ error }}</p>

    <table class="w-full border-collapse text-xs">
      <thead>
        <tr class="text-left text-slate-400">
          <th class="py-1">{{ t('slo.col.metric') }}</th>
          <th>{{ t('slo.col.p95Budget') }}</th>
          <th>{{ t('slo.col.observed') }}</th>
          <th>{{ t('slo.col.severity') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="b in budgets"
          :key="b.metric"
          class="border-t border-slate-800"
          :data-test="`slo-row-${b.metric}`"
        >
          <td class="py-1.5 pr-2">
            <div class="font-medium">{{ b.label }}</div>
            <div class="text-[10px] text-slate-500">{{ b.metric }}</div>
          </td>
          <td class="font-mono">{{ b.p95_ms.toFixed(0) }} ms</td>
          <td class="font-mono">
            {{ statusOf(b.metric)?.observed_p95_ms?.toFixed(0) ?? '—' }}
          </td>
          <td>
            <span :class="severityClass(statusOf(b.metric)?.severity ?? 'healthy')">
              {{ statusOf(b.metric)?.severity ?? '—' }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="report" class="text-xs text-slate-400" data-test="slo-overall">
      {{ t('slo.overall') }}:
      <span :class="severityClass(report.overall)">{{ report.overall }}</span>
    </div>
  </section>
</template>

<style scoped>
.badge {
  display: inline-block;
  padding: 0 0.4rem;
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.badge-healthy {
  background: #064e3b;
  color: #6ee7b7;
}
.badge-warning {
  background: #78350f;
  color: #fde68a;
}
.badge-breach {
  background: #7f1d1d;
  color: #fca5a5;
}
</style>
