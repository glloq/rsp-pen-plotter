<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'

const { t } = useI18n()
const store = useJobStore()
</script>

<template>
  <section v-if="store.layers.length" class="space-y-2">
    <h2 class="px-1 text-xs uppercase tracking-wider text-slate-500">{{ t('prepare.layout') }}</h2>
    <div class="grid grid-cols-2 gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm">
      <label class="block text-slate-400">
        {{ t('job.scaleMode') }}
        <select
          v-model="store.scaleMode"
          class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        >
          <option value="fit">{{ t('job.scaleFit') }}</option>
          <option value="actual">{{ t('job.scaleActual') }}</option>
        </select>
      </label>
      <label class="block text-slate-400" :class="{ 'opacity-40': store.scaleMode !== 'fit' }">
        {{ t('job.margin') }}
        <input
          v-model.number="store.marginMm"
          type="number"
          step="any"
          min="0"
          :disabled="store.scaleMode !== 'fit'"
          class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        />
      </label>
    </div>
  </section>
</template>
