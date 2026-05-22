<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getJobs, type JobRecord } from '../api/client'
import { useJobStore } from '../stores/job'

const { t } = useI18n()
const store = useJobStore()
const jobs = ref<JobRecord[]>([])

async function refresh(): Promise<void> {
  try {
    jobs.value = await getJobs()
  } catch {
    jobs.value = []
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
    <p v-if="!jobs.length" class="text-sm text-slate-500">{{ t('history.empty') }}</p>
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
