<script setup lang="ts">
import { computed, ref, toRaw, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { exportProfileYaml, type EbbConfig, type MachineProfile, type PenSlot } from '../api/client'
import { confirmAction } from '../composables/confirm'
import { useJobStore } from '../stores/job'

const { t } = useI18n()
const store = useJobStore()
const { profiles, selectedProfileName, presets, selectedPresetName } = storeToRefs(store)

const draft = ref<MachineProfile | null>(null)
const saving = ref(false)
const error = ref<string | null>(null)
// True when the active draft is an in-memory "+ New" profile that has never
// been persisted. Save POSTs it; until then it's not in ``store.profiles``,
// so we must not let ``syncDraft`` overwrite it on a profile-list reload.
const isUnsavedDraft = ref(false)

function defaultEbb(): EbbConfig {
  return { steps_per_mm: 80, servo_up: 16000, servo_down: 12000, servo_rate: 400, serial_terminator: 'cr' }
}

function defaultPen(index: number): PenSlot {
  return {
    index,
    name: `Pen ${index}`,
    color: '#000000',
    installed: true,
    position: null,
    pen_up_command: null,
    pen_down_command: null,
  }
}

function normalizePens(profile: MachineProfile): void {
  const existing = profile.pens ?? []
  const count = Math.max(0, Math.floor(profile.pen_slot_count))
  profile.pens = Array.from(
    { length: count },
    (_, i) => existing.find((p) => p.index === i) ?? defaultPen(i),
  )
}

function newBlankProfile(): MachineProfile {
  // Sensible GRBL/A4-landscape defaults. The operator immediately edits these,
  // so the goal is "valid + visibly placeholder" rather than "optimal".
  return {
    name: t('profile.newProfileDefault'),
    units: 'mm',
    workspace: { x_min: 0, y_min: 0, x_max: 297, y_max: 210 },
    origin: 'top_left',
    gcode_dialect: 'grbl',
    pen_up_command: 'M5',
    pen_down_command: 'M3 S1000',
    tool_change_method: 'manual_pause',
    tool_change_command: 'M0',
    drawing_speed_mm_s: 50,
    travel_speed_mm_s: 100,
    acceleration_mm_s2: 1000,
    pen_slot_count: 1,
    supports_arcs: false,
    arc_tolerance_mm: 0.1,
    ebb: null,
    pens: null,
  }
}

function syncDraft(): void {
  // While an unsaved draft is in flight, the profile-list watch shouldn't
  // wipe it just because /profiles re-loaded.
  if (isUnsavedDraft.value) return
  if (!store.selectedProfile) {
    draft.value = null
    return
  }
  // ``toRaw`` peels off Pinia's reactive Proxy; otherwise ``structuredClone``
  // raises DataCloneError on Chromium for any reactive object, which used to
  // leave ``draft`` null and silently hide the EBB fieldset on profile switch.
  const clone = structuredClone(toRaw(store.selectedProfile))
  normalizePens(clone)
  draft.value = clone
}

function startNewProfile(): void {
  const blank = newBlankProfile()
  normalizePens(blank)
  draft.value = blank
  isUnsavedDraft.value = true
}

watch(() => store.selectedProfileName, syncDraft, { immediate: true })
watch(() => store.profiles, syncDraft)

const isEbb = computed(() => draft.value?.gcode_dialect === 'ebb')

watch(
  () => draft.value?.gcode_dialect,
  (dialect) => {
    if (!draft.value) return
    if (dialect === 'ebb' && !draft.value.ebb) draft.value.ebb = defaultEbb()
  },
)

watch(
  () => draft.value?.pen_slot_count,
  () => {
    if (draft.value) normalizePens(draft.value)
  },
)

async function save(): Promise<void> {
  if (!draft.value) return
  saving.value = true
  error.value = null
  try {
    if (!isEbb.value) draft.value.ebb = null
    await store.saveProfile(structuredClone(toRaw(draft.value)))
    // Successful POST → the new profile is now in the store. Drop the
    // "unsaved" guard so subsequent profile-list updates can re-sync the
    // draft from the canonical version.
    isUnsavedDraft.value = false
  } catch (err) {
    error.value = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? t('profile.saveFailed')
  } finally {
    saving.value = false
  }
}

function duplicate(): void {
  if (!draft.value) return
  const clone = structuredClone(toRaw(draft.value))
  draft.value = { ...clone, name: `${draft.value.name} copy` }
  isUnsavedDraft.value = true
}

async function remove(): Promise<void> {
  if (!draft.value) return
  const confirmed = await confirmAction({
    title: t('confirm.deleteProfileTitle'),
    message: t('confirm.deleteProfileMsg', { name: draft.value.name }),
    confirmLabel: t('profile.delete'),
    cancelLabel: t('confirm.cancel'),
    danger: true,
  })
  if (!confirmed) return
  error.value = null
  try {
    await store.deleteProfile(draft.value.name)
  } catch (err) {
    error.value = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? t('profile.deleteFailed')
  }
}

async function downloadYaml(): Promise<void> {
  if (!draft.value) return
  const yaml = await exportProfileYaml(draft.value.name)
  const blob = new Blob([yaml], { type: 'text/yaml' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${draft.value.name}.yaml`
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="space-y-4 text-sm">
    <!-- Profile + preset pickers (moved here from the AppHeader) -->
    <div class="space-y-2 rounded-lg border border-slate-700 bg-slate-800/60 p-3">
      <label class="block text-xs text-slate-400">
        {{ t('profile.select') }}
        <div class="mt-1 flex gap-2">
          <select
            v-model="selectedProfileName"
            class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
          >
            <option v-for="profile in profiles" :key="profile.name" :value="profile.name">
              {{ profile.name }} ({{ profile.pen_slot_count }})
            </option>
          </select>
          <button
            type="button"
            class="rounded bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-500"
            :title="t('profile.newProfile')"
            @click="startNewProfile"
          >
            + {{ t('profile.newProfile') }}
          </button>
        </div>
      </label>
      <label class="block text-xs text-slate-400">
        {{ t('profile.preset') }}
        <select
          v-model="selectedPresetName"
          class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
        >
          <option value="">{{ t('upload.presetNone') }}</option>
          <option v-for="preset in presets" :key="preset.name" :value="preset.name">
            {{ preset.name }}
          </option>
        </select>
      </label>
      <p v-if="isUnsavedDraft" class="text-[11px] text-amber-300">
        ⚠ {{ t('profile.unsavedDraft') }}
      </p>
    </div>

    <div v-if="draft" class="space-y-4">
      <label class="block text-slate-400">
        {{ t('profile.name') }}
        <input v-model="draft.name" type="text" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
      </label>

      <fieldset class="space-y-2">
        <legend class="text-xs uppercase tracking-wide text-slate-500">{{ t('profile.sheet') }}</legend>
        <div class="grid grid-cols-2 gap-2">
          <label class="block text-slate-400">{{ t('profile.units') }}
            <select v-model="draft.units" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100">
              <option value="mm">mm</option>
              <option value="inch">inch</option>
            </select>
          </label>
          <label class="block text-slate-400">{{ t('profile.origin') }}
            <select v-model="draft.origin" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100">
              <option value="top_left">top_left</option>
              <option value="bottom_left">bottom_left</option>
              <option value="center">center</option>
            </select>
          </label>
          <label class="block text-slate-400">X min
            <input v-model.number="draft.workspace.x_min" type="number" step="any" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
          <label class="block text-slate-400">Y min
            <input v-model.number="draft.workspace.y_min" type="number" step="any" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
          <label class="block text-slate-400">X max
            <input v-model.number="draft.workspace.x_max" type="number" step="any" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
          <label class="block text-slate-400">Y max
            <input v-model.number="draft.workspace.y_max" type="number" step="any" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
        </div>
      </fieldset>

      <fieldset class="space-y-2">
        <legend class="text-xs uppercase tracking-wide text-slate-500">{{ t('profile.motion') }}</legend>
        <div class="grid grid-cols-2 gap-2">
          <label class="block text-slate-400">{{ t('profile.drawingSpeed') }}
            <input v-model.number="draft.drawing_speed_mm_s" type="number" step="any" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
          <label class="block text-slate-400">{{ t('profile.travelSpeed') }}
            <input v-model.number="draft.travel_speed_mm_s" type="number" step="any" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
          <label class="col-span-2 block text-slate-400">{{ t('profile.acceleration') }}
            <input v-model.number="draft.acceleration_mm_s2" type="number" step="any" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
        </div>
      </fieldset>

      <fieldset class="space-y-2">
        <legend class="text-xs uppercase tracking-wide text-slate-500">{{ t('profile.pen') }}</legend>
        <div class="grid grid-cols-2 gap-2">
          <label class="block text-slate-400">{{ t('profile.penUp') }}
            <input v-model="draft.pen_up_command" type="text" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100" />
          </label>
          <label class="block text-slate-400">{{ t('profile.penDown') }}
            <input v-model="draft.pen_down_command" type="text" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100" />
          </label>
          <label class="block text-slate-400">{{ t('profile.toolChangeMethod') }}
            <select v-model="draft.tool_change_method" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100">
              <option value="manual_pause">manual_pause</option>
              <option value="carousel">carousel</option>
              <option value="rack">rack</option>
              <option value="none">none</option>
            </select>
          </label>
          <label class="block text-slate-400">{{ t('profile.toolChangeCommand') }}
            <input v-model="draft.tool_change_command" type="text" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100" />
          </label>
          <label class="block text-slate-400">{{ t('profile.penSlots') }}
            <input v-model.number="draft.pen_slot_count" type="number" min="1" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
        </div>
      </fieldset>

      <fieldset v-if="draft.pens" class="space-y-2">
        <legend class="text-xs uppercase tracking-wide text-slate-500">{{ t('profile.magazine') }}</legend>
        <div
          v-for="pen in draft.pens"
          :key="pen.index"
          class="rounded border border-slate-700 bg-slate-900/50 p-2"
        >
          <div class="flex items-center gap-2">
            <span class="w-6 shrink-0 text-center font-mono text-slate-500">{{ pen.index }}</span>
            <input v-model="pen.color" type="color" class="h-7 w-9 shrink-0 rounded border border-slate-700 bg-slate-900" />
            <input
              v-model="pen.name"
              type="text"
              :placeholder="`Pen ${pen.index}`"
              class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
            />
            <label class="flex shrink-0 items-center gap-1 text-xs text-slate-400">
              <input v-model="pen.installed" type="checkbox" class="rounded border-slate-600 bg-slate-900" />
              {{ t('profile.installed') }}
            </label>
          </div>
          <label class="mt-1 flex items-center gap-2 text-xs text-slate-400">
            <input
              type="checkbox"
              :checked="pen.position !== null"
              class="rounded border-slate-600 bg-slate-900"
              @change="(e) => (pen.position = (e.target as HTMLInputElement).checked ? { x: 0, y: 0 } : null)"
            />
            {{ t('profile.pickupPosition') }}
          </label>
          <div v-if="pen.position" class="mt-1 grid grid-cols-2 gap-2">
            <input v-model.number="pen.position.x" type="number" step="any" placeholder="X" class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            <input v-model.number="pen.position.y" type="number" step="any" placeholder="Y" class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </div>
          <div class="mt-1 grid grid-cols-2 gap-2">
            <label class="block text-slate-500">{{ t('profile.penUpOverride') }}
              <input v-model="pen.pen_up_command" type="text" :placeholder="draft.pen_up_command" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100" />
            </label>
            <label class="block text-slate-500">{{ t('profile.penDownOverride') }}
              <input v-model="pen.pen_down_command" type="text" :placeholder="draft.pen_down_command" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100" />
            </label>
          </div>
        </div>
      </fieldset>

      <fieldset class="space-y-2">
        <legend class="text-xs uppercase tracking-wide text-slate-500">{{ t('profile.advanced') }}</legend>
        <div class="grid grid-cols-2 gap-2">
          <label class="block text-slate-400">{{ t('profile.dialect') }}
            <select v-model="draft.gcode_dialect" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100">
              <option value="grbl">grbl</option>
              <option value="marlin">marlin</option>
              <option value="klipper">klipper</option>
              <option value="ebb">ebb</option>
              <option value="custom">custom</option>
            </select>
          </label>
          <label class="flex items-center gap-2 self-end text-slate-400">
            <input v-model="draft.supports_arcs" type="checkbox" class="rounded border-slate-600 bg-slate-900" />
            {{ t('profile.supportsArcs') }}
          </label>
          <label v-if="draft.supports_arcs" class="block text-slate-400">{{ t('profile.arcTolerance') }}
            <input v-model.number="draft.arc_tolerance_mm" type="number" step="any" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
        </div>

        <div v-if="isEbb && draft.ebb" class="mt-2 grid grid-cols-2 gap-2 rounded border border-slate-700 bg-slate-900/50 p-2">
          <label class="block text-slate-400">steps/mm
            <input v-model.number="draft.ebb.steps_per_mm" type="number" step="any" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
          <label class="block text-slate-400">servo rate
            <input v-model.number="draft.ebb.servo_rate" type="number" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
          <label class="block text-slate-400">servo up
            <input v-model.number="draft.ebb.servo_up" type="number" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
          <label class="block text-slate-400">servo down
            <input v-model.number="draft.ebb.servo_down" type="number" class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
          <label class="block text-slate-400">{{ t('profile.serialTerminator') }}
            <select
              v-model="draft.ebb.serial_terminator"
              class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
            >
              <option value="cr">CR</option>
              <option value="lf">LF</option>
              <option value="crlf">CRLF</option>
            </select>
          </label>
        </div>
      </fieldset>

      <p v-if="error" class="text-sm text-red-400">{{ error }}</p>

      <div class="flex flex-wrap gap-2">
        <button type="button" class="flex-1 rounded bg-emerald-600 px-3 py-2 font-medium text-white hover:bg-emerald-500 disabled:opacity-50" :disabled="saving" @click="save">
          {{ saving ? t('profile.saving') : t('profile.save') }}
        </button>
        <button type="button" class="rounded bg-slate-700 px-3 py-2 text-slate-100 hover:bg-slate-600" @click="duplicate">
          {{ t('profile.duplicate') }}
        </button>
        <button type="button" class="rounded bg-slate-700 px-3 py-2 text-slate-100 hover:bg-slate-600" @click="downloadYaml">
          {{ t('profile.export') }}
        </button>
        <button type="button" class="rounded bg-red-900/70 px-3 py-2 text-red-200 hover:bg-red-800" @click="remove">
          {{ t('profile.delete') }}
        </button>
      </div>
    </div>
  </div>
</template>
