<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  systemUpdate,
  systemVersion,
  type SystemUpdateResponse,
  type SystemVersionResponse,
} from '../api/client'
import { confirmAction } from '../composables/confirm'
import { useToastStore } from '../stores/toasts'

const { t } = useI18n()
const toasts = useToastStore()

const version = ref<SystemVersionResponse | null>(null)
const versionError = ref<string | null>(null)
const updating = ref(false)
const lastUpdate = ref<SystemUpdateResponse | null>(null)
const updateError = ref<string | null>(null)

async function loadVersion(): Promise<void> {
  try {
    version.value = await systemVersion()
    versionError.value = null
  } catch (err) {
    versionError.value = (err as Error).message || t('system.versionError')
  }
}

async function runUpdate(): Promise<void> {
  const confirmed = await confirmAction({
    title: t('system.updateConfirmTitle'),
    message: t('system.updateConfirmMsg'),
    confirmLabel: t('system.updateNow'),
    cancelLabel: t('confirm.cancel'),
  })
  if (!confirmed) return

  updating.value = true
  updateError.value = null
  lastUpdate.value = null
  try {
    const result = await systemUpdate()
    lastUpdate.value = result
    if (result.updated) {
      toasts.success(t('system.updateApplied'))
    } else {
      toasts.info(t('system.upToDate'))
    }
    await loadVersion()
  } catch (err) {
    updateError.value = (err as Error).message || t('system.updateFailed')
    toasts.error(updateError.value)
  } finally {
    updating.value = false
  }
}

onMounted(loadVersion)
</script>

<template>
  <section class="space-y-4">
    <header>
      <h2 class="text-base font-semibold text-slate-100">{{ t('system.title') }}</h2>
      <p class="mt-1 text-xs text-slate-400">{{ t('system.subtitle') }}</p>
    </header>

    <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 text-xs">
      <h3 class="mb-2 text-[11px] uppercase tracking-wider text-slate-500">{{ t('system.installed') }}</h3>
      <dl v-if="version" class="grid grid-cols-[6rem_1fr] gap-y-1 text-slate-300">
        <dt class="text-slate-500">{{ t('system.version') }}</dt>
        <dd class="font-mono">{{ version.version }}</dd>
        <template v-if="version.branch">
          <dt class="text-slate-500">{{ t('system.branch') }}</dt>
          <dd class="font-mono">{{ version.branch }}</dd>
        </template>
        <template v-if="version.commit">
          <dt class="text-slate-500">{{ t('system.commit') }}</dt>
          <dd class="font-mono break-all">{{ version.commit.slice(0, 12) }}</dd>
        </template>
        <template v-if="version.dirty">
          <dt class="text-slate-500">{{ t('system.workingTree') }}</dt>
          <dd class="text-amber-300">{{ t('system.dirty') }}</dd>
        </template>
      </dl>
      <p v-else-if="versionError" class="text-amber-300">{{ versionError }}</p>
      <p v-else class="text-slate-500">{{ t('system.loading') }}</p>
    </div>

    <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-3">
      <div>
        <h3 class="text-[11px] uppercase tracking-wider text-slate-500">{{ t('system.update') }}</h3>
        <p class="mt-1 text-xs text-slate-400">{{ t('system.updateHint') }}</p>
      </div>
      <button
        type="button"
        class="w-full rounded bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        :disabled="updating || (version?.dirty ?? false)"
        @click="runUpdate"
      >
        {{ updating ? t('system.updating') : t('system.updateNow') }}
      </button>
      <p v-if="version?.dirty" class="text-[11px] text-amber-300">{{ t('system.dirtyWarning') }}</p>

      <div v-if="lastUpdate" class="rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs">
        <p v-if="lastUpdate.updated" class="text-emerald-300">
          ✓ {{ t('system.updateApplied') }}
          <span v-if="lastUpdate.previous_commit && lastUpdate.new_commit" class="font-mono text-slate-400">
            {{ lastUpdate.previous_commit.slice(0, 7) }} → {{ lastUpdate.new_commit.slice(0, 7) }}
          </span>
        </p>
        <p v-else class="text-slate-300">✓ {{ t('system.upToDate') }}</p>
        <p v-if="lastUpdate.needs_restart" class="mt-1 text-amber-300">⚠ {{ t('system.needsRestart') }}</p>
        <details v-if="lastUpdate.log" class="mt-1">
          <summary class="cursor-pointer text-slate-500 hover:text-slate-300">{{ t('system.viewLog') }}</summary>
          <pre class="mt-1 max-h-48 overflow-auto rounded bg-slate-950 p-2 font-mono text-[10px] text-slate-300 whitespace-pre-wrap">{{ lastUpdate.log }}</pre>
        </details>
      </div>
      <p v-if="updateError" class="rounded border border-red-700 bg-red-950/40 px-2 py-1 text-xs text-red-300">
        {{ updateError }}
      </p>
    </div>
  </section>
</template>
