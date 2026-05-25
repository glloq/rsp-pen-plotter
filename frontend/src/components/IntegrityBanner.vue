<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLibraryStore } from '../stores/library'

// Surfaces the backend's ``GET /files/integrity`` report (lot L4) as a
// non-blocking banner. Each flagged file lost the state needed to
// re-render (missing original bytes, corrupt bitmap_options, etc.); the
// operator should re-upload them. The banner is dismissable for the
// session — refreshing the page or restarting the backend re-runs the
// scan, so a dismissed banner can come back legitimately.

const { t } = useI18n()
const library = useLibraryStore()
const dismissed = ref(false)

const visible = computed(() => !dismissed.value && library.integrityIssues.length > 0)

// Group by reason so a magazine-wide problem (e.g. someone wiped the
// data dir) reads as one line per cause, not one line per file.
const issuesByReason = computed(() => {
  const map = new Map<string, string[]>()
  for (const issue of library.integrityIssues) {
    const list = map.get(issue.reason) ?? []
    list.push(issue.source_file)
    map.set(issue.reason, list)
  }
  return [...map.entries()].map(([reason, files]) => ({ reason, files }))
})

function reasonLabel(reason: string): string {
  // Localized prose for the known REHYDRATE_* codes; unknown reasons
  // fall back to the raw code so a future server-side reason still
  // surfaces something readable.
  const key = `integrity.reason.${reason}`
  const localized = t(key)
  return localized === key ? reason : localized
}
</script>

<template>
  <div
    v-if="visible"
    class="border-b border-amber-700/60 bg-amber-950/60 px-4 py-2 text-xs text-amber-200"
    role="status"
  >
    <div class="flex flex-wrap items-start gap-2">
      <span aria-hidden="true">⚠</span>
      <div class="flex-1">
        <p class="font-semibold text-amber-100">
          {{ t('integrity.title', { count: library.integrityIssues.length }) }}
        </p>
        <ul class="mt-1 space-y-0.5">
          <li v-for="group in issuesByReason" :key="group.reason">
            <span class="font-medium">{{ reasonLabel(group.reason) }}</span>
            —
            <span class="text-amber-300/80">{{ group.files.slice(0, 3).join(', ') }}</span>
            <span v-if="group.files.length > 3" class="text-amber-300/60">
              {{ t('integrity.andMore', { count: group.files.length - 3 }) }}
            </span>
          </li>
        </ul>
      </div>
      <button
        type="button"
        class="rounded px-2 py-0.5 text-amber-300 hover:bg-amber-900/60 hover:text-amber-100"
        :aria-label="t('integrity.dismiss')"
        @click="dismissed = true"
      >
        ✕
      </button>
    </div>
  </div>
</template>
