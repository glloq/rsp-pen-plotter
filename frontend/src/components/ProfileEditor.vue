<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { exportProfileYaml, type EbbConfig, type MachineProfile, type PenSlot } from '../api/client'
import { confirmAction } from '../composables/confirm'
import { useJobStore } from '../stores/job'

const { t } = useI18n()
const store = useJobStore()

const open = ref(false)
const draft = ref<MachineProfile | null>(null)
const saving = ref(false)
const error = ref<string | null>(null)

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

function syncDraft(): void {
  if (!store.selectedProfile) {
    draft.value = null
    return
  }
  const clone = structuredClone(store.selectedProfile)
  normalizePens(clone)
  draft.value = clone
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
    await store.saveProfile(structuredClone(draft.value))
  } catch (err) {
    error.value = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? t('profile.saveFailed')
  } finally {
    saving.value = false
  }
}

function duplicate(): void {
  if (!draft.value) return
  draft.value = { ...structuredClone(draft.value), name: `${draft.value.name} copy` }
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
  <div class="rounded-lg border border-slate-700 bg-slate-800">
    <button
      type="button"
      class="flex w-full items-center justify-between px-4 py-3 text-sm uppercase tracking-wide text-slate-300"
      :aria-expanded="open"
      @click="open = !open"
    >
      {{ t('profile.title') }}
      <span class="text-slate-500">{{ open ? '−' : '+' }}</span>
    </button>

    <div v-if="open && draft" class="space-y-4 border-t border-slate-700 p-4 text-sm">
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
