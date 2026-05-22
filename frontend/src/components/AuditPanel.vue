<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getAudit, type AuditEntry } from '../api/client'

const { t } = useI18n()
const open = ref(false)
const entries = ref<AuditEntry[]>([])
let timer: ReturnType<typeof setInterval> | null = null

async function refresh(): Promise<void> {
  try {
    entries.value = await getAudit()
  } catch {
    entries.value = []
  }
}

function formatTime(ts: string): string {
  const date = new Date(ts)
  return Number.isNaN(date.getTime()) ? ts : date.toLocaleTimeString()
}

onMounted(() => {
  void refresh()
  timer = setInterval(refresh, 5000)
})
onBeforeUnmount(() => {
  if (timer !== null) clearInterval(timer)
})
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800">
    <button
      type="button"
      class="flex w-full items-center justify-between px-4 py-3 text-sm uppercase tracking-wide text-slate-300"
      :aria-expanded="open"
      @click="open = !open"
    >
      {{ t('audit.title') }}
      <span class="text-slate-500">{{ open ? '−' : '+' }}</span>
    </button>

    <div v-if="open" class="space-y-1 border-t border-slate-700 p-4 text-xs">
      <p v-if="!entries.length" class="text-slate-500">{{ t('audit.empty') }}</p>
      <ul v-else class="max-h-48 space-y-1 overflow-auto">
        <li
          v-for="entry in entries"
          :key="entry.id"
          class="flex items-center gap-2 rounded bg-slate-900 px-2 py-1"
        >
          <span class="shrink-0 text-slate-500">{{ formatTime(entry.timestamp) }}</span>
          <span class="shrink-0 font-mono text-slate-300">{{ entry.action }}</span>
          <span class="truncate text-slate-500">{{ entry.detail }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>
