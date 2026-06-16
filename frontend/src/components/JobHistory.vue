<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getJobs, type JobRecord } from '../api/client'
import { useJobStore } from '../stores/job'

const { t } = useI18n()
const store = useJobStore()
const jobs = ref<JobRecord[]>([])
// Distinct from an *empty* history: a fetch failure used to blank the list
// silently, reading as "no jobs yet". Track it so the panel shows a real
// error line instead. No toast — the panel re-fetches on every job load
// (watch below), so a toast would spam on a transient blip.
const loadError = ref(false)

async function refresh(): Promise<void> {
  try {
    jobs.value = await getJobs()
    loadError.value = false
  } catch {
    jobs.value = []
    loadError.value = true
  }
}

onMounted(refresh)
// Refresh history whenever a new job is loaded.
watch(
  () => store.job?.job_id,
  () => refresh(),
)
</script>

<template>
  <div class="space-y-2">
    <p v-if="loadError" class="text-sm text-red-400">{{ t('history.loadFailed') }}</p>
    <p v-else-if="!jobs.length" class="text-sm text-slate-500">{{ t('history.empty') }}</p>
    <ul v-else class="space-y-1 max-h-[60vh] overflow-auto">
      <li
        v-for="job in jobs"
        :key="job.job_id"
        class="flex items-center justify-between rounded bg-slate-800 px-2 py-1 text-xs"
      >
        <span class="truncate font-mono text-slate-200">{{ job.source_file }}</span>
        <span class="text-slate-500">{{ job.layer_count }}</span>
      </li>
    </ul>
  </div>
</template>
