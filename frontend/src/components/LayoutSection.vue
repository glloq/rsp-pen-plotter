<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { useToastStore } from '../stores/toasts'

const { t } = useI18n()
const store = useJobStore()
const toasts = useToastStore()

const showSheet = ref(false)
const saving = ref(false)

// Editable copies of the workspace dimensions; only flushed back to the
// profile on Save so the user can tweak without saving partial edits.
const widthDraft = ref(0)
const heightDraft = ref(0)

const profileWidth = computed(() => {
  const ws = store.selectedProfile?.workspace
  return ws ? ws.x_max - ws.x_min : 0
})
const profileHeight = computed(() => {
  const ws = store.selectedProfile?.workspace
  return ws ? ws.y_max - ws.y_min : 0
})

watch(
  [profileWidth, profileHeight],
  ([w, h]) => {
    widthDraft.value = Number(w.toFixed(2))
    heightDraft.value = Number(h.toFixed(2))
  },
  { immediate: true },
)

interface SheetPreset {
  name: string
  w: number
  h: number
}
const presets: SheetPreset[] = [
  { name: 'A6', w: 105, h: 148 },
  { name: 'A5', w: 148, h: 210 },
  { name: 'A4', w: 210, h: 297 },
  { name: 'A3', w: 297, h: 420 },
  { name: 'A2', w: 420, h: 594 },
  { name: 'Letter', w: 216, h: 279 },
]

function applyPreset(p: SheetPreset, landscape: boolean): void {
  widthDraft.value = landscape ? p.h : p.w
  heightDraft.value = landscape ? p.w : p.h
}

function swap(): void {
  const w = widthDraft.value
  widthDraft.value = heightDraft.value
  heightDraft.value = w
}

async function saveSheet(): Promise<void> {
  const profile = store.selectedProfile
  if (!profile) return
  const w = Number(widthDraft.value)
  const h = Number(heightDraft.value)
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) {
    toasts.error(t('sheet.invalidSize'))
    return
  }
  saving.value = true
  try {
    // Anchor the new workspace at the existing origin so we don't move the
    // origin (which would invalidate jog positions and saved drawings).
    const next = {
      ...profile,
      workspace: {
        x_min: profile.workspace.x_min,
        y_min: profile.workspace.y_min,
        x_max: profile.workspace.x_min + w,
        y_max: profile.workspace.y_min + h,
      },
    }
    await store.saveProfile(next)
    toasts.success(t('sheet.saved'))
    showSheet.value = false
  } catch (err) {
    toasts.error((err as Error).message || t('profile.saveFailed'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section v-if="store.layers.length || store.selectedProfile" class="space-y-2">
    <div class="flex items-baseline justify-between px-1">
      <h2 class="text-xs uppercase tracking-wider text-slate-500">{{ t('prepare.layout') }}</h2>
      <button
        type="button"
        class="text-[10px] uppercase tracking-wider text-slate-500 hover:text-slate-300"
        @click="showSheet = !showSheet"
      >
        {{ showSheet ? '−' : '+' }} {{ t('sheet.sheet') }}
      </button>
    </div>

    <div v-if="showSheet" class="space-y-2 rounded-lg border border-slate-700 bg-slate-800 p-3">
      <div class="grid grid-cols-3 gap-1">
        <button
          v-for="p in presets"
          :key="p.name"
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-300 hover:border-slate-600"
          @click="applyPreset(p, false)"
        >
          {{ p.name }}
          <span class="block text-[9px] text-slate-500">{{ p.w }}×{{ p.h }}</span>
        </button>
      </div>
      <div class="grid grid-cols-[1fr_auto_1fr] gap-2 items-end">
        <label class="block text-xs text-slate-400">
          {{ t('sheet.width') }}
          <input
            v-model.number="widthDraft"
            type="number"
            min="1"
            step="any"
            class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
          />
        </label>
        <button
          type="button"
          class="self-end rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-300 hover:border-slate-600"
          :title="t('sheet.swap')"
          @click="swap"
        >
          ⇄
        </button>
        <label class="block text-xs text-slate-400">
          {{ t('sheet.height') }}
          <input
            v-model.number="heightDraft"
            type="number"
            min="1"
            step="any"
            class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
          />
        </label>
      </div>
      <button
        type="button"
        class="w-full rounded bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        :disabled="saving"
        @click="saveSheet"
      >
        {{ saving ? t('profile.saving') : t('sheet.applySize') }}
      </button>
      <p class="text-[10px] text-slate-500">{{ t('sheet.sizeHint') }}</p>
    </div>

    <div v-if="store.layers.length" class="grid grid-cols-2 gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm">
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
