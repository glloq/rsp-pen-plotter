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
const builtinPresets = computed<Preset[]>(() =>
  presets.value.filter((p) => p.kind !== 'user'),
)

// "Save as preset" only makes sense once the operator has actually
// configured something — last_options is the snapshot of the converter
// bundle that drove the latest upload / generate call. Empty / null
// means there's nothing meaningful to capture.
const currentOptions = computed<Record<string, unknown> | null>(() => {
  const opts = job.selectedPlacement?.last_options
  if (!opts || typeof opts !== 'object') return null
  return Object.keys(opts).length === 0 ? null : (opts as Record<string, unknown>)
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

function onApply(preset: Preset): void {
  job.selectedPresetName = preset.name
  toasts.success(t('presets.appliedToast', { name: preset.name }))
}
</script>

<template>
  <section class="preset-panel" data-test="preset-panel">
    <header class="preset-panel__header">
      <h3>{{ t('presets.title') }}</h3>
      <span class="preset-panel__hint">{{ t('presets.hint') }}</span>
    </header>

    <!-- Save form. Hidden when there's no current converter snapshot to
         capture (fresh session, no upload yet). -->
    <form
      v-if="currentOptions"
      class="preset-panel__save"
      data-test="preset-panel-save"
      @submit.prevent="onSave"
    >
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
  outline: 2px solid #1f6feb;
  outline-offset: 1px;
}
.preset-panel__save-btn {
  border: 1px solid #10b981;
  background: #065f46;
  color: white;
  border-radius: 4px;
  padding: 0.3rem 0.7rem;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
}
.preset-panel__save-btn:hover:not(:disabled) {
  background: #047857;
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
  border-color: #1f6feb;
  background: #1e3a8a;
  color: white;
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
</style>
