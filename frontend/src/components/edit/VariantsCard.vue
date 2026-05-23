<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../../stores/job'

const { t } = useI18n()
const store = useJobStore()

const variants = computed(() => store.selectedPlacement?.variants ?? [])
const activeId = computed(() => store.selectedPlacement?.active_variant_id ?? '')

// Inline rename: track which variant id has its name being edited.
const editingId = ref<string | null>(null)
const draftName = ref('')

function beginRename(id: string, current: string): void {
  editingId.value = id
  draftName.value = current
}

function commitRename(): void {
  if (!editingId.value) return
  store.renameVariant(editingId.value, draftName.value)
  editingId.value = null
}

function cancelRename(): void {
  editingId.value = null
}

function onSwitch(id: string): void {
  if (id === activeId.value) return
  store.setActiveVariant(id)
}

function onAddVariant(): void {
  const id = store.addVariant(t('variants.untitled'))
  if (id) beginRename(id, t('variants.untitled'))
}

function onRemove(id: string): void {
  store.removeVariant(id)
}
</script>

<template>
  <section
    v-if="store.selectedPlacement"
    class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-2"
  >
    <div class="flex items-baseline justify-between">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">
        {{ t('variants.title') }}
      </p>
      <div class="flex gap-1">
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-300 hover:border-slate-600"
          :title="t('variants.updateHint')"
          @click="store.updateActiveVariant"
        >
          {{ t('variants.update') }}
        </button>
        <button
          type="button"
          class="rounded bg-emerald-700 px-2 py-0.5 text-[10px] text-white hover:bg-emerald-600"
          @click="onAddVariant"
        >
          + {{ t('variants.add') }}
        </button>
      </div>
    </div>

    <ul class="space-y-1">
      <li
        v-for="variant in variants"
        :key="variant.id"
        class="flex items-center gap-1 rounded border px-2 py-1 text-xs"
        :class="variant.id === activeId
          ? 'border-emerald-600 bg-emerald-950/30'
          : 'border-slate-700 bg-slate-900'"
      >
        <button
          v-if="editingId !== variant.id"
          type="button"
          class="min-w-0 flex-1 truncate text-left"
          :class="variant.id === activeId ? 'text-emerald-200' : 'text-slate-200 hover:text-white'"
          @click="onSwitch(variant.id)"
        >
          <span v-if="variant.id === activeId" aria-hidden="true">●</span>
          <span v-else aria-hidden="true">○</span>
          {{ variant.name }}
        </button>
        <input
          v-else
          v-model="draftName"
          type="text"
          class="flex-1 rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-xs text-slate-100"
          autofocus
          @keydown.enter="commitRename"
          @keydown.esc="cancelRename"
          @blur="commitRename"
        />
        <button
          v-if="editingId !== variant.id"
          type="button"
          class="rounded bg-slate-700 px-1.5 py-0.5 text-[10px] text-slate-200 hover:bg-slate-600"
          :title="t('variants.rename')"
          @click="beginRename(variant.id, variant.name)"
        >
          ✎
        </button>
        <button
          type="button"
          class="rounded bg-slate-700 px-1.5 py-0.5 text-[10px] text-slate-300 hover:bg-red-600 hover:text-white disabled:cursor-not-allowed disabled:opacity-30"
          :disabled="variants.length <= 1"
          :title="t('variants.remove')"
          @click="onRemove(variant.id)"
        >
          ✕
        </button>
      </li>
    </ul>

    <p class="text-[10px] text-slate-500">{{ t('variants.hint') }}</p>
  </section>
</template>
