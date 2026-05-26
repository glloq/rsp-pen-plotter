<script setup lang="ts">
// Magazine editor — moved out of the Profile tab so the operator can
// assign colours to pen slots from the same panel that manages the
// available-colour inventory ("Couleurs" drawer tab).
//
// The colour selector lists every entry from the available-colours
// store; picking one writes its hex onto the matching pen slot. The
// ColorPicker swatch is still available so the operator can override
// with a free hex when the colour isn't (yet) in the inventory.
//
// Edits hit the backend through the same ``saveProfile`` path the
// Profile tab uses — there's no draft state here, every mutation is
// persisted immediately. The Profile tab's draft is rebuilt from
// ``profiles`` on each store reload, so an unsaved profile rename
// won't be clobbered by a pen-colour save (the watcher in
// ``useProfileDraft`` short-circuits while ``isUnsavedDraft`` is true).

import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import type { MachineProfile, PenSlot } from '../api/client'
import { useAvailableColorsStore } from '../stores/availableColors'
import { useJobStore } from '../stores/job'
import { defaultPen, normalizePens } from '../composables/useProfileDraft'
import ColorPicker from './ColorPicker.vue'

const { t } = useI18n()
const job = useJobStore()
const { selectedProfile } = storeToRefs(job)
const availableColors = useAvailableColorsStore()

const saving = ref(false)
const error = ref<string | null>(null)

const profile = computed(() => selectedProfile.value)

const pens = computed<PenSlot[]>(() => {
  const p = profile.value
  if (!p) return []
  const existing = p.pens ?? []
  const count = Math.max(0, Math.floor(p.pen_slot_count))
  return Array.from({ length: count }, (_, i) => existing.find((s) => s.index === i) ?? defaultPen(i))
})

function canonicaliseHex(value: string): string {
  const trimmed = value.trim().replace(/^#/, '').toLowerCase()
  if (/^[0-9a-f]{3}$/.test(trimmed)) {
    return `#${trimmed.split('').map((c) => c + c).join('')}`
  }
  if (/^[0-9a-f]{6}$/.test(trimmed)) return `#${trimmed}`
  return value
}

function matchAvailable(hex: string): string {
  // Return the canonical hex if it lives in the inventory, otherwise
  // the empty string so the select shows the "custom" sentinel option.
  const canon = canonicaliseHex(hex)
  return availableColors.ordered.find((c) => c.hex === canon)?.hex ?? ''
}

async function patchPen(index: number, patch: Partial<PenSlot>): Promise<void> {
  if (!profile.value) return
  saving.value = true
  error.value = null
  try {
    const next: MachineProfile = structuredClone({ ...profile.value, pens: pens.value })
    normalizePens(next)
    const target = next.pens?.find((p) => p.index === index)
    if (target) Object.assign(target, patch)
    await job.saveProfile(next)
  } catch (err) {
    error.value =
      (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
      t('profile.saveFailed')
  } finally {
    saving.value = false
  }
}

async function setSlotCount(value: number): Promise<void> {
  if (!profile.value) return
  const count = Math.max(0, Math.floor(value))
  if (count === profile.value.pen_slot_count) return
  saving.value = true
  error.value = null
  try {
    const next: MachineProfile = structuredClone({ ...profile.value, pen_slot_count: count })
    normalizePens(next)
    await job.saveProfile(next)
  } catch (err) {
    error.value =
      (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
      t('profile.saveFailed')
  } finally {
    saving.value = false
  }
}

function onSelectColor(index: number, value: string): void {
  if (!value) return
  void patchPen(index, { color: value })
}

function onCustomColor(index: number, hex: string): void {
  void patchPen(index, { color: hex })
}

function onName(index: number, name: string): void {
  void patchPen(index, { name })
}

function onInstalled(index: number, installed: boolean): void {
  void patchPen(index, { installed })
}

function displayLabel(name: string, hex: string): string {
  return name.trim() ? `${name} · ${hex}` : hex
}
</script>

<template>
  <section class="space-y-2 rounded-lg border border-slate-700 bg-slate-800 p-3">
    <div class="flex items-baseline justify-between">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">
        {{ t('magazine.title') }}
      </p>
      <span v-if="profile" class="text-[10px] text-slate-500">
        {{ profile.name }}
      </span>
    </div>

    <p v-if="!profile" class="text-xs text-slate-500">{{ t('magazine.noProfile') }}</p>

    <template v-else>
      <p class="text-[11px] text-slate-500">{{ t('magazine.hint') }}</p>

      <label class="flex items-center gap-2 text-[11px] text-slate-400">
        {{ t('magazine.slotCount') }}
        <input
          type="number"
          min="0"
          :value="profile.pen_slot_count"
          class="w-16 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
          :disabled="saving"
          @change="(e) => setSlotCount(Number((e.target as HTMLInputElement).value))"
        />
      </label>

      <ul v-if="pens.length" class="space-y-1.5">
        <li
          v-for="pen in pens"
          :key="pen.index"
          class="flex items-center gap-2 rounded border border-slate-700 bg-slate-900/60 px-2 py-1.5"
        >
          <span class="w-6 shrink-0 text-center font-mono text-[11px] text-slate-500">
            #{{ pen.index }}
          </span>

          <ColorPicker
            :model-value="pen.color"
            :label="t('availableColors.pickColor')"
            swatch-class="h-7 w-9"
            :disabled="saving"
            @update:model-value="(hex) => onCustomColor(pen.index, hex)"
          />

          <select
            class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 disabled:opacity-60"
            :value="matchAvailable(pen.color)"
            :disabled="saving || !availableColors.ordered.length"
            @change="(e) => onSelectColor(pen.index, (e.target as HTMLSelectElement).value)"
          >
            <option value="" disabled>
              {{
                availableColors.ordered.length
                  ? t('magazine.customColor', { hex: pen.color })
                  : t('magazine.noAvailable')
              }}
            </option>
            <option
              v-for="opt in availableColors.ordered"
              :key="opt.color_id"
              :value="opt.hex"
            >
              {{ displayLabel(opt.name, opt.hex) }}
            </option>
          </select>

          <input
            type="text"
            :value="pen.name"
            :placeholder="`Pen ${pen.index}`"
            class="w-28 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
            :disabled="saving"
            @change="(e) => onName(pen.index, (e.target as HTMLInputElement).value)"
          />

          <label class="flex shrink-0 items-center gap-1 text-[11px] text-slate-400">
            <input
              type="checkbox"
              :checked="pen.installed"
              class="rounded border-slate-600 bg-slate-900"
              :disabled="saving"
              @change="(e) => onInstalled(pen.index, (e.target as HTMLInputElement).checked)"
            />
            {{ t('profile.installed') }}
          </label>
        </li>
      </ul>

      <p v-else class="text-xs text-slate-500">{{ t('magazine.empty') }}</p>

      <p v-if="error" class="text-[11px] text-red-400">{{ error }}</p>
    </template>
  </section>
</template>
