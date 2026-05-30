<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import {
  systemUpdate,
  systemVersion,
  type SystemUpdateResponse,
  type SystemVersionResponse,
} from '../api/client'
import { errorDetail } from '../api/error'
import { confirmAction } from '../composables/confirm'
import { useUiStore } from '../stores/ui'

const { t, locale } = useI18n()
const ui = useUiStore()
const { updateNotificationsEnabled, planPreviewMode } = storeToRefs(ui)

// Plan-tab rendering choices surfaced in System settings. 'auto' keeps
// the WYSIWYG vector unless it's heavy enough to risk laggy scrolling.
const PLAN_PREVIEW_MODES = [
  { id: 'auto', label: 'system.planPreviewAuto', hint: 'system.planPreviewAutoHint' },
  { id: 'svg', label: 'system.planPreviewSvg', hint: 'system.planPreviewSvgHint' },
  { id: 'image', label: 'system.planPreviewImage', hint: 'system.planPreviewImageHint' },
] as const

function setLocale(value: 'en' | 'fr'): void {
  locale.value = value
}

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

async function runUpdate(force = false): Promise<void> {
  const confirmed = await confirmAction({
    title: force ? t('system.forceUpdateConfirmTitle') : t('system.updateConfirmTitle'),
    message: force ? t('system.forceUpdateConfirmMsg') : t('system.updateConfirmMsg'),
    confirmLabel: force ? t('system.forceUpdate') : t('system.updateNow'),
    cancelLabel: t('confirm.cancel'),
    danger: force,
  })
  if (!confirmed) return

  updating.value = true
  updateError.value = null
  lastUpdate.value = null
  // Drive the global blocking modal — operator can't interact with the rest
  // of the UI while update.sh is running.
  ui.startUpdate(t('updateModal.statusPulling'))
  try {
    const result = await systemUpdate(force)
    lastUpdate.value = result
    if (result.updated) {
      ui.finishUpdate('success', {
        message: t('updateModal.successMessage'),
        forced: result.forced,
        newCommitApplied: true,
      })
    } else {
      ui.finishUpdate('noop', { message: t('updateModal.noopMessage') })
    }
    await loadVersion()
  } catch (err) {
    updateError.value = errorDetail(err, (err as Error).message || t('system.updateFailed'))
    ui.finishUpdate('error', {
      message: t('updateModal.errorMessage'),
      error: updateError.value,
    })
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
      <h3 class="mb-2 text-[11px] uppercase tracking-wider text-slate-500">
        {{ t('system.language') }}
      </h3>
      <div class="flex overflow-hidden rounded border border-slate-700 text-xs">
        <button
          type="button"
          class="flex-1 px-3 py-1.5"
          :class="
            locale === 'en'
              ? 'bg-slate-700 text-white'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
          "
          @click="setLocale('en')"
        >
          {{ t('system.languageEn') }}
        </button>
        <button
          type="button"
          class="flex-1 px-3 py-1.5"
          :class="
            locale === 'fr'
              ? 'bg-slate-700 text-white'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
          "
          @click="setLocale('fr')"
        >
          {{ t('system.languageFr') }}
        </button>
      </div>
    </div>

    <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 text-xs">
      <h3 class="mb-2 text-[11px] uppercase tracking-wider text-slate-500">
        {{ t('system.installed') }}
      </h3>
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

    <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-2 text-xs">
      <h3 class="text-[11px] uppercase tracking-wider text-slate-500">
        {{ t('system.planPreview') }}
      </h3>
      <p class="text-[11px] text-slate-500">{{ t('system.planPreviewHint') }}</p>
      <div class="space-y-1.5">
        <label
          v-for="mode in PLAN_PREVIEW_MODES"
          :key="mode.id"
          class="flex items-start gap-2 text-slate-300"
        >
          <input
            v-model="planPreviewMode"
            type="radio"
            name="plan-preview-mode"
            :value="mode.id"
            class="mt-0.5 h-3.5 w-3.5 shrink-0 accent-emerald-500"
          />
          <span class="leading-snug">
            {{ t(mode.label) }}
            <span class="mt-0.5 block text-[11px] text-slate-500">{{ t(mode.hint) }}</span>
          </span>
        </label>
      </div>
    </div>

    <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-2 text-xs">
      <h3 class="text-[11px] uppercase tracking-wider text-slate-500">
        {{ t('system.notifications') }}
      </h3>
      <label class="flex items-start gap-2 text-slate-300">
        <input
          v-model="updateNotificationsEnabled"
          type="checkbox"
          class="mt-0.5 h-3.5 w-3.5 shrink-0 accent-emerald-500"
        />
        <span class="leading-snug">
          {{ t('system.notifyOnStartup') }}
          <span class="mt-0.5 block text-[11px] text-slate-500">{{
            t('system.notifyOnStartupHint')
          }}</span>
        </span>
      </label>
    </div>

    <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-3">
      <div>
        <h3 class="text-[11px] uppercase tracking-wider text-slate-500">
          {{ t('system.update') }}
        </h3>
        <p class="mt-1 text-xs text-slate-400">{{ t('system.updateHint') }}</p>
      </div>
      <button
        type="button"
        class="w-full rounded bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        :disabled="updating || (version?.dirty ?? false)"
        @click="runUpdate(false)"
      >
        {{ updating ? t('system.updating') : t('system.updateNow') }}
      </button>

      <div
        v-if="version?.dirty"
        class="space-y-2 rounded border border-amber-700 bg-amber-950/30 px-2 py-1.5 text-[11px]"
      >
        <p class="text-amber-200">⚠ {{ t('system.dirtyWarning') }}</p>
        <details v-if="version.dirty_files.length" class="text-amber-100/80">
          <summary class="cursor-pointer hover:text-amber-100">
            {{ t('system.dirtyFilesCount', { count: version.dirty_files.length }) }}
          </summary>
          <ul
            class="mt-1 max-h-32 overflow-auto rounded bg-slate-900/60 p-1.5 font-mono text-[10px] leading-snug"
          >
            <li v-for="(line, i) in version.dirty_files" :key="i">{{ line }}</li>
          </ul>
        </details>
        <button
          type="button"
          class="w-full rounded bg-amber-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-50"
          :disabled="updating"
          @click="runUpdate(true)"
        >
          {{ updating ? t('system.updating') : '⚠ ' + t('system.forceUpdate') }}
        </button>
        <p class="text-[10px] text-amber-100/70">{{ t('system.forceUpdateHint') }}</p>
      </div>

      <div
        v-if="lastUpdate"
        class="rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs"
      >
        <p v-if="lastUpdate.updated" class="text-emerald-300">
          ✓ {{ t('system.updateApplied') }}
          <span
            v-if="lastUpdate.previous_commit && lastUpdate.new_commit"
            class="font-mono text-slate-400"
          >
            {{ lastUpdate.previous_commit.slice(0, 7) }} → {{ lastUpdate.new_commit.slice(0, 7) }}
          </span>
        </p>
        <p v-else class="text-slate-300">✓ {{ t('system.upToDate') }}</p>
        <p v-if="lastUpdate.forced" class="mt-1 text-amber-200">⚠ {{ t('system.forcedNotice') }}</p>
        <p v-if="lastUpdate.needs_restart" class="mt-1 text-amber-300">
          ⚠ {{ t('system.needsRestart') }}
        </p>
        <details v-if="lastUpdate.log" class="mt-1">
          <summary class="cursor-pointer text-slate-500 hover:text-slate-300">
            {{ t('system.viewLog') }}
          </summary>
          <pre
            class="mt-1 max-h-48 overflow-auto rounded bg-slate-950 p-2 font-mono text-[10px] text-slate-300 whitespace-pre-wrap"
            >{{ lastUpdate.log }}</pre
          >
        </details>
      </div>
      <p
        v-if="updateError"
        class="rounded border border-red-700 bg-red-950/40 px-2 py-1 text-xs text-red-300"
      >
        {{ updateError }}
      </p>
    </div>
  </section>
</template>
