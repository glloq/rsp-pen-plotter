<script setup lang="ts">
// Panel that lives under the Plotter drawer's "Couleurs" tab.
//
// Edits the global available-colours inventory: list every ink the
// operator owns (whether currently mounted or not), with add / rename /
// rehex / delete. The list feeds the editor's per-layer colour picker
// when the active palette source is ``available`` or ``union`` (added
// in L3+L4 of the palette-source rework).
//
// Pure presentational against the ``useAvailableColorsStore`` Pinia
// store — no API calls from this file; the store owns the network
// surface, error toasts, and the local cache mirror.

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAvailableColorsStore } from '../stores/availableColors'
import ColorPicker from './ColorPicker.vue'
import MagazineEditor from './MagazineEditor.vue'

function canonicaliseHex(value: string): string {
  // Match the backend's normalisation so the dedup check below treats
  // ``#ABC`` and ``#aabbcc`` as the same entry.
  const trimmed = value.trim().replace(/^#/, '').toLowerCase()
  if (/^[0-9a-f]{3}$/.test(trimmed)) {
    return `#${trimmed.split('').map((c) => c + c).join('')}`
  }
  if (/^[0-9a-f]{6}$/.test(trimmed)) return `#${trimmed}`
  return value
}

const { t } = useI18n()
const store = useAvailableColorsStore()

const newHex = ref('#000000')
const newName = ref('')
// Default to a common fineliner tip so a quick add lands on a sane width.
const newWidth = ref(0.5)
const submitting = ref(false)

const ordered = computed(() => store.ordered)

// True when the hex the operator is about to add already lives in the
// inventory — used to disable the Add button + show a heads-up so the
// idempotent backend POST doesn't silently mutate the existing row.
const duplicate = computed(() => {
  const canon = canonicaliseHex(newHex.value)
  return ordered.value.find((c) => c.hex === canon) ?? null
})

// Inline-edit state: ``color_id`` of the row currently being renamed,
// or ``null`` when none. Single-row at a time keeps the UI simple
// (no nested form complexity) and matches the macros-panel pattern.
const editingId = ref<string | null>(null)
const editName = ref('')
const editHex = ref('#000000')
const editWidth = ref(0.5)

onMounted(() => {
  if (!store.loaded) void store.refresh()
})

async function addColor(): Promise<void> {
  if (!newHex.value) return
  submitting.value = true
  try {
    const width = newWidth.value > 0 ? newWidth.value : undefined
    const created = await store.add(newHex.value, newName.value.trim(), width)
    if (created) {
      newHex.value = '#000000'
      newName.value = ''
      newWidth.value = 0.5
    }
  } finally {
    submitting.value = false
  }
}

function startEdit(colorId: string, hex: string, name: string, width: number): void {
  editingId.value = colorId
  editHex.value = hex
  editName.value = name
  editWidth.value = width
}

function cancelEdit(): void {
  editingId.value = null
}

async function saveEdit(colorId: string): Promise<void> {
  const w = Number.isFinite(editWidth.value) && editWidth.value > 0 ? editWidth.value : null
  const result = await store.rename(colorId, {
    hex: editHex.value,
    name: editName.value.trim(),
    ...(w !== null ? { stroke_width_mm: w } : {}),
  })
  if (result !== null) editingId.value = null
}

async function moveUp(colorId: string): Promise<void> {
  const list = ordered.value
  const idx = list.findIndex((c) => c.color_id === colorId)
  if (idx <= 0) return
  const me = list[idx]!
  const above = list[idx - 1]!
  // Swap their positions; persistence is one round-trip per row so a
  // concurrent edit can't leave them with the same position. The
  // backend tie-breaker on created_at keeps the ordering stable if
  // both updates land at the same logical timestamp.
  await store.rename(me.color_id, { position: above.position })
  await store.rename(above.color_id, { position: me.position })
}

async function moveDown(colorId: string): Promise<void> {
  const list = ordered.value
  const idx = list.findIndex((c) => c.color_id === colorId)
  if (idx < 0 || idx >= list.length - 1) return
  const me = list[idx]!
  const below = list[idx + 1]!
  await store.rename(me.color_id, { position: below.position })
  await store.rename(below.color_id, { position: me.position })
}

async function removeColor(colorId: string, label: string): Promise<void> {
  if (!window.confirm(t('availableColors.deleteConfirm', { name: label }))) return
  await store.remove(colorId)
}

function displayLabel(name: string, hex: string): string {
  return name.trim() ? name : hex
}
</script>

<template>
  <div class="space-y-3">
    <p class="text-xs text-slate-400">{{ t('availableColors.hint') }}</p>

    <!-- Magazine (pen slot ↔ colour assignment) -->
    <MagazineEditor />

    <!-- Add a colour -->
    <section class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-2">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">
        {{ t('availableColors.add') }}
      </p>
      <div class="flex items-center gap-2">
        <ColorPicker
          v-model="newHex"
          :label="t('availableColors.pickColor')"
          swatch-class="h-9 w-12"
        />
        <input
          v-model="newHex"
          type="text"
          class="w-28 rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-xs text-slate-100"
          :placeholder="t('availableColors.hex')"
          spellcheck="false"
        />
        <input
          v-model="newName"
          type="text"
          class="flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-100"
          :placeholder="t('availableColors.namePlaceholder')"
        />
        <label class="flex shrink-0 items-center gap-1 text-[11px] text-slate-400">
          <input
            v-model.number="newWidth"
            type="number"
            min="0.05"
            step="0.05"
            class="w-16 rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-100"
            :title="t('availableColors.strokeWidthTitle')"
          />
          {{ t('availableColors.mmUnit') }}
        </label>
        <button
          type="button"
          class="rounded bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          :disabled="submitting || !newHex || !!duplicate"
          @click="addColor"
        >
          {{ t('availableColors.addAction') }}
        </button>
      </div>
      <p v-if="duplicate" class="text-[11px] text-amber-300">
        ⚠ {{ t('availableColors.duplicate', { name: displayLabel(duplicate.name, duplicate.hex) }) }}
      </p>
    </section>

    <!-- Inventory -->
    <section class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-2">
      <div class="flex items-baseline justify-between">
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('availableColors.inventory') }}
        </p>
        <span class="text-[10px] text-slate-500">{{ ordered.length }}</span>
      </div>

      <p
        v-if="store.loading && !ordered.length"
        class="text-xs text-slate-500"
      >
        {{ t('availableColors.loading') }}
      </p>
      <p
        v-else-if="!ordered.length"
        class="text-xs text-slate-500"
      >
        {{ t('availableColors.empty') }}
      </p>

      <ul v-else class="space-y-1.5">
        <li
          v-for="(color, idx) in ordered"
          :key="color.color_id"
          class="flex items-center gap-2 rounded border border-slate-700 bg-slate-900/60 px-2 py-1.5"
        >
          <template v-if="editingId === color.color_id">
            <ColorPicker
              v-model="editHex"
              :label="t('availableColors.pickColor')"
              swatch-class="h-7 w-10"
            />
            <input
              v-model="editHex"
              type="text"
              class="w-24 rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-[11px] text-slate-100"
              spellcheck="false"
            />
            <input
              v-model="editName"
              type="text"
              class="flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
              :placeholder="t('availableColors.namePlaceholder')"
            />
            <label class="flex shrink-0 items-center gap-1 text-[11px] text-slate-400">
              <input
                v-model.number="editWidth"
                type="number"
                min="0.05"
                step="0.05"
                class="w-16 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                :title="t('availableColors.strokeWidthTitle')"
              />
              {{ t('availableColors.mmUnit') }}
            </label>
            <button
              type="button"
              class="rounded bg-emerald-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-emerald-500"
              @click="saveEdit(color.color_id)"
            >
              ✓
            </button>
            <button
              type="button"
              class="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
              @click="cancelEdit"
            >
              ✕
            </button>
          </template>

          <template v-else>
            <span
              class="inline-block h-5 w-5 shrink-0 rounded border border-slate-600"
              :style="{ backgroundColor: color.hex }"
              :aria-label="color.hex"
            />
            <span class="font-mono text-[11px] text-slate-400">{{ color.hex }}</span>
            <span class="min-w-0 flex-1 truncate text-xs text-slate-200">
              {{ displayLabel(color.name, color.hex) }}
            </span>

            <span
              class="shrink-0 rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300"
              :title="t('availableColors.strokeWidthTitle')"
            >
              Ø {{ color.stroke_width_mm }} {{ t('availableColors.mmUnit') }}
            </span>

            <span
              class="shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px]"
              :class="
                color.odometer_mm > 0
                  ? 'bg-emerald-950/60 text-emerald-300'
                  : 'text-slate-600'
              "
              :title="t('availableColors.odometerTitle')"
            >
              {{ t('availableColors.meters', { value: (color.odometer_mm / 1000).toFixed(3) }) }}
            </span>

            <button
              type="button"
              class="rounded p-1 text-slate-400 hover:bg-amber-900/40 hover:text-amber-300 disabled:opacity-30"
              :disabled="color.odometer_mm === 0"
              :title="t('availableColors.resetOdometer')"
              @click="store.resetOdometer(color.color_id)"
            >
              ↺
            </button>

            <button
              type="button"
              class="rounded p-1 text-slate-400 hover:bg-slate-700 hover:text-slate-200 disabled:opacity-30"
              :disabled="idx === 0"
              :title="t('availableColors.moveUp')"
              @click="moveUp(color.color_id)"
            >
              ↑
            </button>
            <button
              type="button"
              class="rounded p-1 text-slate-400 hover:bg-slate-700 hover:text-slate-200 disabled:opacity-30"
              :disabled="idx === ordered.length - 1"
              :title="t('availableColors.moveDown')"
              @click="moveDown(color.color_id)"
            >
              ↓
            </button>
            <button
              type="button"
              class="rounded p-1 text-slate-400 hover:bg-slate-700 hover:text-slate-200"
              :title="t('availableColors.edit')"
              @click="startEdit(color.color_id, color.hex, color.name, color.stroke_width_mm)"
            >
              ✎
            </button>
            <button
              type="button"
              class="rounded p-1 text-slate-400 hover:bg-red-900/40 hover:text-red-300"
              :title="t('availableColors.delete')"
              @click="removeColor(color.color_id, displayLabel(color.name, color.hex))"
            >
              🗑
            </button>
          </template>
        </li>
      </ul>
    </section>
  </div>
</template>
