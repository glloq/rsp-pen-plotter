<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getAudit, type AuditEntry } from '../api/client'

const { t } = useI18n()
const entries = ref<AuditEntry[]>([])
let timer: ReturnType<typeof setInterval> | null = null
let onVisible: (() => void) | null = null

async function refresh(): Promise<void> {
  // Skip the round-trip while the tab is backgrounded — nobody's reading
  // the log, so a 5 s poll against a Pi is pure waste. The visibility
  // listener fires an immediate refresh on return.
  if (typeof document !== 'undefined' && document.hidden) return
  try {
    entries.value = await getAudit()
  } catch {
    // Keep the last good list on a transient blip rather than blanking it
    // (which read as "no actions recorded yet").
  }
}

function formatTime(ts: string): string {
  const date = new Date(ts)
  return Number.isNaN(date.getTime()) ? ts : date.toLocaleTimeString()
}

onMounted(() => {
  void refresh()
  timer = setInterval(refresh, 5000)
  if (typeof document !== 'undefined') {
    onVisible = () => {
      if (!document.hidden) void refresh()
    }
    document.addEventListener('visibilitychange', onVisible)
  }
})
onBeforeUnmount(() => {
  if (timer !== null) clearInterval(timer)
  if (onVisible !== null && typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', onVisible)
    onVisible = null
  }
})
</script>

<template>
  <div class="space-y-1 text-xs">
    <p v-if="!entries.length" class="text-slate-500">{{ t('audit.empty') }}</p>
    <ul v-else class="max-h-[60vh] space-y-1 overflow-auto">
      <li
        v-for="entry in entries"
        :key="entry.id"
        class="flex items-center gap-2 rounded bg-slate-800 px-2 py-1"
      >
        <span class="shrink-0 text-slate-500">{{ formatTime(entry.timestamp) }}</span>
        <span class="shrink-0 font-mono text-slate-300">{{ entry.action }}</span>
        <span class="truncate text-slate-500">{{ entry.detail }}</span>
      </li>
    </ul>
  </div>
</template>
