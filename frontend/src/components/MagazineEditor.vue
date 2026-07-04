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
//
// Per-pen XY tip offsets and the offset camera live in their own panel
// (Settings → Cameras → Offset camera); this editor owns colour, magazine
// position and per-slot pen-up/down depth only.

import { computed, onUnmounted, ref, toRaw } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import type { MachineProfile, PenSlot, Point } from '../api/client'
import { useAvailableColorsStore } from '../stores/availableColors'
import { canonicalHex } from '../lib/penWidth'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'
import { defaultPen, normalizePens } from '../composables/useProfileDraft'
import ColorPicker from './ColorPicker.vue'

const { t } = useI18n()
const job = useJobStore()
const ui = useUiStore()
const { selectedProfile } = storeToRefs(job)
const availableColors = useAvailableColorsStore()

const saving = ref(false)
const error = ref<string | null>(null)
// Transient "saved" acknowledgement: every edit persists immediately, so
// a brief badge confirms the write landed without a Save button.
const justSaved = ref(false)
let savedTimer: ReturnType<typeof setTimeout> | undefined

const profile = computed(() => selectedProfile.value)

// Mirror ProfilePenFields' ceiling so a stray ``pen_slot_count`` can't
// render thousands of rows and freeze the panel.
const MAX_PEN_SLOTS = 64

const pens = computed<PenSlot[]>(() => {
  const p = profile.value
  if (!p) return []
  const existing = p.pens ?? []
  const count = Math.min(MAX_PEN_SLOTS, Math.max(0, Math.floor(p.pen_slot_count)))
  return Array.from(
    { length: count },
    (_, i) => existing.find((s) => s.index === i) ?? defaultPen(i),
  )
})

// Resolve the tool-change mode the same way ProfilePenFields does
// (capability model first, legacy field as fallback) to decide what this
// tab should show.
const colorMode = computed<'mono' | 'manual' | 'firmware' | 'host'>(() => {
  const tooling = profile.value?.capabilities?.tool_change.mode
  if (tooling === 'single_pen') return 'mono'
  if (tooling === 'manual') return 'manual'
  if (tooling === 'firmware') return 'firmware'
  if (tooling === 'host_macro') return 'host'
  switch (profile.value?.tool_change_method) {
    case 'none':
      return 'mono'
    case 'carousel':
      return 'firmware'
    case 'rack':
      return 'host'
    default:
      return 'manual'
  }
})

// The Colours tab adapts its framing to the mode: mono shows a single pen
// colour, manual a colour list (no positions — there's no physical
// magazine), firmware / host the full magazine. Only the title / hint
// differ here; the per-slot calibration is gated separately below.
const sectionTitle = computed(() => {
  if (colorMode.value === 'mono') return t('magazine.titleMono')
  if (colorMode.value === 'manual') return t('magazine.titleManual')
  return t('magazine.title')
})

const listHint = computed(() =>
  colorMode.value === 'manual' ? t('magazine.hintManual') : t('magazine.hint'),
)

// Carousel / rack profiles physically fetch the pen from a fixed slot
// position, so the calibration editor (position + per-pen up/down
// overrides) is only meaningful for those. Mono / manual hide it.
const showsCalibration = computed(
  () =>
    profile.value?.tool_change_method === 'carousel' ||
    profile.value?.tool_change_method === 'rack',
)

function matchAvailable(hex: string): string {
  // Return the canonical hex if it lives in the inventory, otherwise
  // the empty string so the select shows the "custom" sentinel option.
  const canon = canonicalHex(hex)
  return availableColors.ordered.find((c) => c.hex === canon)?.hex ?? ''
}

// Persist a mutation against a plain clone of the active profile. Every
// edit in this panel saves immediately (there's no Save button).
async function commit(mutate: (next: MachineProfile) => void): Promise<void> {
  if (!profile.value) return
  saving.value = true
  error.value = null
  try {
    // ``toRaw`` first: ``profile.value`` is a reactive proxy and
    // ``structuredClone`` throws ``DataCloneError`` on proxies, so a
    // shallow spread (which keeps the reactive ``pens`` elements) would
    // fail before the save ever ran — leaving the slot stuck on its
    // default black. Cloning the raw object yields plain data that
    // ``normalizePens`` can pad against ``pen_slot_count``.
    const next: MachineProfile = structuredClone(toRaw(profile.value))
    normalizePens(next)
    mutate(next)
    await job.saveProfile(next)
    justSaved.value = true
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (justSaved.value = false), 1500)
  } catch (err) {
    error.value =
      (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
      t('profile.saveFailed')
  } finally {
    saving.value = false
  }
}

function patchPen(index: number, patch: Partial<PenSlot>): Promise<void> {
  return commit((next) => {
    const target = next.pens?.find((p) => p.index === index)
    if (target) Object.assign(target, patch)
  })
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

function onPenCommand(
  index: number,
  key: 'pen_up_command' | 'pen_down_command',
  raw: string,
): void {
  // Empty string clears the override so the slot falls back to the
  // profile-level command (the backend treats null as "use default").
  const value = raw.trim() ? raw : null
  void patchPen(index, { [key]: value } as Partial<PenSlot>)
}

function onPosition(pen: PenSlot, axis: 'x' | 'y', raw: string): void {
  const thisVal = raw.trim() === '' ? null : Number(raw)
  const otherVal = axis === 'x' ? (pen.position?.y ?? null) : (pen.position?.x ?? null)
  // Both axes blank → uncalibrated (null), falls back to no routing.
  if (thisVal === null && otherVal === null) {
    void patchPen(pen.index, { position: null })
    return
  }
  const next: Point = {
    x: axis === 'x' ? (thisVal ?? 0) : (pen.position?.x ?? 0),
    y: axis === 'y' ? (thisVal ?? 0) : (pen.position?.y ?? 0),
  }
  void patchPen(pen.index, { position: next })
}

function displayLabel(name: string, hex: string): string {
  return name.trim() ? `${name} · ${hex}` : hex
}

// Per-pen XY tip offsets (colour-overlay registration) live in their own
// panel — Settings → Cameras → Offset camera. That's a different modal
// from the Plotter drawer this editor sits in, so the shortcut closes
// this one before opening the settings modal on the Cameras tab.
const showOffsetLink = computed(() => colorMode.value !== 'mono' && pens.value.length > 1)
function openOffsetCamera(): void {
  ui.closePlotterSettings()
  ui.openSettings('cameras')
}

// True when the operator has no saved inventory yet: the slot <select>
// then has nothing to offer, so point them at the swatch / add section.
const inventoryEmpty = computed(() => availableColors.ordered.length === 0)

onUnmounted(() => clearTimeout(savedTimer))
</script>

<template>
  <section class="space-y-2 rounded-lg border border-slate-700 bg-slate-800 p-3">
    <div class="flex items-baseline justify-between">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">
        {{ sectionTitle }}
      </p>
      <span class="flex items-center gap-2">
        <span v-if="justSaved" class="text-[10px] text-emerald-400" data-test="magazine-saved"
          >✓ {{ t('magazine.saved') }}</span
        >
        <span v-if="profile" class="text-[10px] text-slate-500">
          {{ profile.name }}
        </span>
      </span>
    </div>

    <p v-if="!profile" class="text-xs text-slate-500">{{ t('magazine.noProfile') }}</p>

    <template v-else>
      <!-- Mono: a single pen → just its colour, no slots / magazine. -->
      <div v-if="colorMode === 'mono'" class="space-y-1.5" data-test="magazine-mono">
        <p class="text-[11px] text-slate-500">{{ t('magazine.monoHint') }}</p>
        <div
          class="flex items-center gap-2 rounded border border-slate-700 bg-slate-900/60 px-2 py-1.5"
        >
          <ColorPicker
            :model-value="pens[0]?.color ?? '#000000'"
            :label="t('availableColors.pickColor')"
            swatch-class="h-7 w-9"
            :disabled="saving"
            @update:model-value="(hex) => onCustomColor(0, hex)"
          />
          <select
            class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 disabled:opacity-60"
            :value="matchAvailable(pens[0]?.color ?? '')"
            :disabled="saving || !availableColors.ordered.length"
            @change="(e) => onSelectColor(0, (e.target as HTMLSelectElement).value)"
          >
            <option value="" disabled>
              {{
                availableColors.ordered.length
                  ? t('magazine.customColor', { hex: pens[0]?.color ?? '#000000' })
                  : t('magazine.noAvailable')
              }}
            </option>
            <option v-for="opt in availableColors.ordered" :key="opt.color_id" :value="opt.hex">
              {{ displayLabel(opt.name, opt.hex) }}
            </option>
          </select>
        </div>
      </div>

      <!-- Manual / firmware / host: per-slot list. Manual is a colour list
           (no positions — no physical magazine); firmware / host add the
           per-slot calibration block (gated by ``showsCalibration``). -->
      <template v-else>
        <p class="text-[11px] text-slate-500">{{ listHint }}</p>

        <!-- Shortcut to the per-pen XY offset calibration (colour-overlay
             registration) which lives in a separate settings panel. -->
        <button
          v-if="showOffsetLink"
          type="button"
          class="inline-flex items-center gap-1 rounded border border-sky-800 bg-sky-950/30 px-2 py-1 text-[11px] text-sky-200 hover:bg-sky-900/40"
          data-test="magazine-offset-link"
          @click="openOffsetCamera"
        >
          🎯 {{ t('magazine.calibrateOffsets') }}
        </button>

        <ul v-if="pens.length" class="space-y-1.5">
          <li
            v-for="pen in pens"
            :key="pen.index"
            class="rounded border border-slate-700 bg-slate-900/60 px-2 py-1.5"
          >
            <div class="flex items-center gap-2">
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
                <option v-for="opt in availableColors.ordered" :key="opt.color_id" :value="opt.hex">
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
            </div>

            <!-- Per-slot calibration: magazine position + pen-up/down
               overrides. Only carousel / rack machines fetch pens from a
               fixed position, so the block is hidden for mono / manual. -->
            <details
              v-if="showsCalibration"
              class="mt-1.5 rounded border border-slate-800 bg-slate-950/40"
              :data-test="`pen-calibration-${pen.index}`"
            >
              <summary
                class="cursor-pointer px-2 py-1 text-[10px] uppercase tracking-wider text-slate-500 hover:text-slate-300"
              >
                {{ t('magazine.calibration') }}
              </summary>
              <div class="grid grid-cols-2 gap-2 border-t border-slate-800 p-2">
                <label class="block text-[11px] text-slate-400"
                  >{{ t('magazine.posX') }}
                  <input
                    type="number"
                    step="any"
                    :value="pen.position?.x ?? ''"
                    :disabled="saving"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                    @change="(e) => onPosition(pen, 'x', (e.target as HTMLInputElement).value)"
                  />
                </label>
                <label class="block text-[11px] text-slate-400"
                  >{{ t('magazine.posY') }}
                  <input
                    type="number"
                    step="any"
                    :value="pen.position?.y ?? ''"
                    :disabled="saving"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                    @change="(e) => onPosition(pen, 'y', (e.target as HTMLInputElement).value)"
                  />
                </label>
                <label class="block text-[11px] text-slate-400"
                  >{{ t('magazine.penUpOverride') }}
                  <input
                    type="text"
                    :value="pen.pen_up_command ?? ''"
                    :placeholder="t('magazine.useProfileDefault')"
                    :disabled="saving"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-xs text-slate-100"
                    @change="
                      (e) =>
                        onPenCommand(
                          pen.index,
                          'pen_up_command',
                          (e.target as HTMLInputElement).value,
                        )
                    "
                  />
                </label>
                <label class="block text-[11px] text-slate-400"
                  >{{ t('magazine.penDownOverride') }}
                  <input
                    type="text"
                    :value="pen.pen_down_command ?? ''"
                    :placeholder="t('magazine.useProfileDefault')"
                    :disabled="saving"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-xs text-slate-100"
                    @change="
                      (e) =>
                        onPenCommand(
                          pen.index,
                          'pen_down_command',
                          (e.target as HTMLInputElement).value,
                        )
                    "
                  />
                </label>
              </div>
            </details>
          </li>
        </ul>

        <p v-else class="text-xs text-slate-500">{{ t('magazine.empty') }}</p>
      </template>

      <p
        v-if="inventoryEmpty"
        class="text-[11px] text-slate-500"
        data-test="magazine-empty-inventory-hint"
      >
        {{ t('magazine.emptyInventoryHint') }}
      </p>

      <p v-if="error" class="text-[11px] text-red-400">{{ error }}</p>
    </template>
  </section>
</template>
