<script setup lang="ts">
// Preset save/load panel — surfaced in the expert editor.
//
// Wraps the ``GET /presets`` list (built-in + operator-saved) the
// store already mirrors, plus the new ``POST /presets`` save flow.
// "Save as preset" snapshots the active placement's ``last_options``
// (the converter options bundle that drove the last upload / generate)
// so a future upload of a different file can be initialised from the
// same algorithm + tunings without retyping them.
//
// Built-in presets are read-only — the trash button only appears on
// rows tagged ``kind: 'user'`` and the server enforces the rule too
// (POST with a built-in name → 409, DELETE on a built-in → 404).

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { saveUserPreset, deleteUserPreset, type Preset } from '../../api/client'
import { useJobStore } from '../../stores/job'
import { useToastStore } from '../../stores/toasts'

const { t } = useI18n()
const job = useJobStore()
const toasts = useToastStore()

const newName = ref('')
const newDescription = ref('')
const saving = ref(false)
const saveError = ref<string | null>(null)

const presets = computed<Preset[]>(() => job.presets)
const userPresets = computed<Preset[]>(() => presets.value.filter((p) => p.kind === 'user'))
const builtinPresets = computed<Preset[]>(() => presets.value.filter((p) => p.kind !== 'user'))

// What we capture when the operator clicks "Save". We prefer
// ``last_options`` (the converter bundle that drove the latest /upload
// or /generate) — it's the canonical snapshot. When that's empty (the
// operator opened the editor without re-uploading and only tweaked
// per-layer settings) we fall back to synthesising one from
// ``layer_algorithms``: pick the most common algorithm across bitmap
// layers and use its options. The synthesised shape matches /upload's
// ``options`` body so a future upload using the saved preset replays
// the same look.
const currentOptions = computed<Record<string, unknown> | null>(() => {
  const placement = job.selectedPlacement
  if (!placement) return null
  const last = placement.last_options
  if (last && typeof last === 'object' && Object.keys(last).length > 0) {
    return last as Record<string, unknown>
  }
  // Fallback: synthesise from the placement's per-layer algorithm
  // overrides. ``layer_algorithms`` is keyed by layer_id; we tally the
  // algorithm choices and take the modal pick. Empty stack means
  // nothing meaningful to save — return null so the form stays hidden.
  const algorithms = placement.layer_algorithms ?? {}
  const tally = new Map<string, number>()
  let chosenOptions: Record<string, unknown> = {}
  for (const layerId of Object.keys(algorithms)) {
    const entry = algorithms[layerId]
    if (!entry || !entry.algorithm) continue
    const count = (tally.get(entry.algorithm) ?? 0) + 1
    tally.set(entry.algorithm, count)
    chosenOptions = entry.algorithm_options ?? {}
  }
  if (tally.size === 0) return null
  const [bestAlgorithm] = [...tally.entries()].sort((a, b) => b[1] - a[1])[0]!
  return {
    algorithm: bestAlgorithm,
    algorithm_options: chosenOptions,
    num_colors: placement.layers.length || 1,
  }
})

const canSave = computed<boolean>(
  () => newName.value.trim().length > 0 && currentOptions.value !== null && !saving.value,
)

async function onSave(): Promise<void> {
  if (!canSave.value || !currentOptions.value) return
  saving.value = true
  saveError.value = null
  try {
    await saveUserPreset(newName.value.trim(), newDescription.value.trim(), currentOptions.value)
    await job.loadPresets()
    newName.value = ''
    newDescription.value = ''
    toasts.success(t('presets.savedToast'))
  } catch (err: unknown) {
    // axios error → { response: { data: { detail: string } } }; fall back
    // to the plain Error message otherwise.
    const detail =
      err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined
    saveError.value = detail ?? (err instanceof Error ? err.message : String(err))
  } finally {
    saving.value = false
  }
}

async function onDelete(name: string): Promise<void> {
  // No confirm dialog here — the panel is already gated behind expert
  // mode, and presets are cheap to recreate. The toast on failure is
  // the safety net.
  try {
    await deleteUserPreset(name)
    await job.loadPresets()
    toasts.success(t('presets.deletedToast', { name }))
  } catch (err) {
    toasts.error(err instanceof Error ? err.message : String(err))
  }
}

async function onApply(preset: Preset): Promise<void> {
  // Two effects: (1) mark the preset as selected so the next /upload
  // picks it up; (2) when there's a live placement, apply the preset's
  // algorithm + options to every bitmap layer in that placement and
  // trigger a rerender, so the operator sees the new look immediately
  // instead of having to re-upload. The same code path the V2 modal's
  // "Generate" uses for policy decisions.
  job.selectedPresetName = preset.name
  const algorithm = preset.options.algorithm
  const algorithmOptions = preset.options.algorithm_options
  if (
    typeof algorithm === 'string' &&
    algorithm.length > 0 &&
    job.selectedPlacement &&
    job.selectedPlacement.layers.length > 0
  ) {
    const opts =
      algorithmOptions && typeof algorithmOptions === 'object'
        ? (algorithmOptions as Record<string, unknown>)
        : {}
    await job.applyAlgorithmToAllLayers(algorithm, opts)
  }
  toasts.success(t('presets.appliedToast', { name: preset.name }))
}
</script>

<template>
  <section class="preset-panel" data-test="preset-panel">
    <header class="preset-panel__header">
      <h3>{{ t('presets.title') }}</h3>
      <span class="preset-panel__hint">{{ t('presets.hint') }}</span>
    </header>

    <!-- Save form. Hidden when there's nothing capturable yet (no
         placement, or a placement with no algorithm overrides) — we
         surface an explanatory hint in that case rather than vanish
         the affordance silently. -->
    <p v-if="!currentOptions" class="preset-panel__noop" data-test="preset-panel-noop">
      {{ t('presets.nothingToSave') }}
    </p>
    <form v-else class="preset-panel__save" data-test="preset-panel-save" @submit.prevent="onSave">
      <input
        v-model="newName"
        type="text"
        :placeholder="t('presets.namePlaceholder')"
        maxlength="64"
        class="preset-panel__name"
        data-test="preset-panel-name"
      />
      <input
        v-model="newDescription"
        type="text"
        :placeholder="t('presets.descPlaceholder')"
        maxlength="256"
        class="preset-panel__desc"
        data-test="preset-panel-desc"
      />
      <button
        type="submit"
        class="preset-panel__save-btn"
        :disabled="!canSave"
        data-test="preset-panel-save-btn"
      >
        {{ saving ? t('presets.saving') : t('presets.save') }}
      </button>
    </form>
    <p v-if="saveError" class="preset-panel__error" data-test="preset-panel-error">
      {{ saveError }}
    </p>

    <!-- Built-in presets row. -->
    <div v-if="builtinPresets.length" class="preset-panel__group">
      <span class="preset-panel__group-label">{{ t('presets.builtin') }}</span>
      <ul class="preset-panel__list">
        <li v-for="p in builtinPresets" :key="p.name">
          <button
            type="button"
            class="preset-panel__chip"
            :class="{ active: job.selectedPresetName === p.name }"
            :title="p.description"
            :data-test="`preset-chip-${p.name}`"
            @click="onApply(p)"
          >
            {{ p.name }}
          </button>
        </li>
      </ul>
    </div>

    <!-- User-saved presets row, with delete buttons. -->
    <div v-if="userPresets.length" class="preset-panel__group">
      <span class="preset-panel__group-label">{{ t('presets.user') }}</span>
      <ul class="preset-panel__list">
        <li v-for="p in userPresets" :key="p.name" class="preset-panel__user-item">
          <button
            type="button"
            class="preset-panel__chip"
            :class="{ active: job.selectedPresetName === p.name }"
            :title="p.description"
            :data-test="`preset-chip-${p.name}`"
            @click="onApply(p)"
          >
            {{ p.name }}
          </button>
          <button
            type="button"
            class="preset-panel__delete"
            :title="t('presets.delete')"
            :aria-label="t('presets.deleteFor', { name: p.name })"
            :data-test="`preset-delete-${p.name}`"
            @click="onDelete(p.name)"
          >
            ×
          </button>
        </li>
      </ul>
    </div>

    <p v-if="!presets.length" class="preset-panel__empty">{{ t('presets.empty') }}</p>
  </section>
</template>

<style scoped>
.preset-panel {
  border: 1px solid #334155;
  background: #1e293b;
  border-radius: 6px;
  padding: 0.7rem 0.85rem;
  color: #e2e8f0;
  font-size: 0.82rem;
}
.preset-panel__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}
.preset-panel__header h3 {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #cbd5e1;
}
.preset-panel__hint {
  font-size: 0.7rem;
  color: #94a3b8;
}
.preset-panel__save {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 0.35rem;
  margin-bottom: 0.5rem;
}
.preset-panel__name,
.preset-panel__desc {
  border: 1px solid #475569;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 4px;
  padding: 0.3rem 0.5rem;
  font-size: 0.78rem;
}
.preset-panel__name:focus,
.preset-panel__desc:focus {
  outline: 2px solid #10b981;
  outline-offset: 1px;
}
.preset-panel__save-btn {
  border: 1px solid #059669;
  background: #059669;
  color: white;
  border-radius: 4px;
  padding: 0.3rem 0.7rem;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
}
.preset-panel__save-btn:hover:not(:disabled) {
  background: #10b981;
}
.preset-panel__save-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.preset-panel__error {
  color: #fca5a5;
  background: rgba(127, 29, 29, 0.4);
  border: 1px solid #7f1d1d;
  padding: 0.3rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  margin: 0 0 0.5rem;
}
.preset-panel__group {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin-bottom: 0.4rem;
}
.preset-panel__group-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #64748b;
}
.preset-panel__list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  list-style: none;
  padding: 0;
  margin: 0;
}
.preset-panel__user-item {
  display: inline-flex;
  align-items: center;
  gap: 0.15rem;
}
.preset-panel__chip {
  border: 1px solid #475569;
  background: #0f172a;
  color: #cbd5e1;
  border-radius: 999px;
  padding: 0.2rem 0.6rem;
  font-size: 0.75rem;
  cursor: pointer;
}
.preset-panel__chip:hover {
  background: #1e293b;
  color: white;
}
.preset-panel__chip.active {
  border-color: #059669;
  background: rgba(2, 44, 34, 0.6);
  color: #6ee7b7;
}
.preset-panel__delete {
  border: 1px solid #7f1d1d;
  background: transparent;
  color: #fca5a5;
  border-radius: 999px;
  width: 1.2rem;
  height: 1.2rem;
  font-size: 0.85rem;
  line-height: 1;
  cursor: pointer;
  padding: 0;
}
.preset-panel__delete:hover {
  background: #7f1d1d;
  color: white;
}
.preset-panel__empty {
  color: #94a3b8;
  font-size: 0.75rem;
  margin: 0.3rem 0 0;
}
.preset-panel__noop {
  color: #94a3b8;
  font-size: 0.75rem;
  margin: 0 0 0.5rem;
  padding: 0.4rem 0.55rem;
  border: 1px dashed #475569;
  border-radius: 4px;
  background: rgba(15, 23, 42, 0.4);
}
</style>
