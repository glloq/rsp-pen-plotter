<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../../stores/job'

// Persistent variants chip-bar mounted above EditTabs. Replaces the
// full-page VariantsCard now that variants are an always-visible
// state-switcher rather than a "step" in the workflow.
//
// Collapsible: chips by default, click ▾ to fold into a thin
// "{active} · N variants" summary so the bar doesn't eat vertical
// space when the operator isn't using it.

const props = defineProps<{ inline?: boolean }>()

const { t } = useI18n()
const store = useJobStore()

const variants = computed(() => store.selectedPlacement?.variants ?? [])
const activeId = computed(() => store.selectedPlacement?.active_variant_id ?? '')
const activeName = computed(
  () => variants.value.find((v) => v.id === activeId.value)?.name ?? '—',
)

// Persisted collapsed state — the operator who hides the bar once
// shouldn't see it pop back open every modal reopen. Keyed per
// placement so a placement the operator hid stays hidden, while a
// brand-new placement starts at the default (expanded). The legacy
// global key is kept as a fallback for placements that haven't been
// touched yet so we don't visually regress existing setups.
const LEGACY_COLLAPSED_KEY = 'omniplot.editModal.variantsBar.collapsed'
const collapsedKey = computed(
  () => `omniplot.editModal.variantsBar.collapsed.${store.selectedPlacementId ?? 'none'}`,
)
function readCollapsed(key: string): boolean {
  try {
    const v = localStorage.getItem(key)
    if (v === '1') return true
    if (v === '0') return false
  } catch { /* ignore */ }
  // Fall back to the legacy global value when this placement has no
  // entry yet; pre-migration users keep their previously-set state.
  try { return localStorage.getItem(LEGACY_COLLAPSED_KEY) === '1' } catch { return false }
}
const collapsed = ref<boolean>(readCollapsed(collapsedKey.value))
watch(collapsedKey, (key) => { collapsed.value = readCollapsed(key) })
function toggleCollapsed(): void {
  collapsed.value = !collapsed.value
  try { localStorage.setItem(collapsedKey.value, collapsed.value ? '1' : '0') } catch { /* ignore */ }
}

// Inline rename, same UX as the old card.
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

function onAdd(): void {
  const id = store.addVariant(t('variants.untitled'))
  if (id) beginRename(id, t('variants.untitled'))
}

function onRemove(id: string): void {
  store.removeVariant(id)
}
</script>

<template>
  <div
    v-if="store.selectedPlacement"
    class="flex items-center gap-1 px-2 py-1"
    :class="!props.inline ? 'border-b border-slate-700 bg-slate-900/80 backdrop-blur' : 'min-w-0 flex-1'"
  >
    <button
      type="button"
      class="rounded px-1 py-0.5 text-[11px] text-slate-400 hover:bg-slate-800 hover:text-slate-200"
      :title="collapsed ? t('variants.expand') : t('variants.collapse')"
      @click="toggleCollapsed"
    >
      {{ collapsed ? '▸' : '▾' }}
    </button>
    <span class="shrink-0 text-[10px] uppercase tracking-wider text-slate-500">
      {{ t('variants.title') }}
    </span>

    <template v-if="collapsed">
      <span class="ml-1 truncate text-[11px] text-slate-300">
        {{ activeName }}
        <span class="text-slate-500">· {{ variants.length }}</span>
      </span>
    </template>

    <template v-else>
      <div class="flex min-w-0 flex-1 flex-wrap items-center gap-1">
        <template
          v-for="variant in variants"
          :key="variant.id"
        >
          <span
            v-if="editingId === variant.id"
            class="inline-flex items-center gap-1 rounded border border-emerald-600 bg-emerald-950/40 px-1"
          >
            <input
              v-model="draftName"
              type="text"
              class="w-32 bg-transparent text-[11px] text-slate-100 focus:outline-none"
              autofocus
              @keydown.enter="commitRename"
              @keydown.esc="cancelRename"
              @blur="commitRename"
            />
          </span>
          <button
            v-else
            type="button"
            class="inline-flex max-w-[12rem] items-center gap-1 truncate rounded border px-1.5 py-0.5 text-[11px] transition"
            :class="variant.id === activeId
              ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
              : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'"
            @click="onSwitch(variant.id)"
            @dblclick="beginRename(variant.id, variant.name)"
            :title="t('variants.switchHint')"
          >
            <span aria-hidden="true">{{ variant.id === activeId ? '●' : '○' }}</span>
            <span class="truncate">{{ variant.name }}</span>
            <span
              v-if="variants.length > 1"
              class="ml-0.5 text-[10px] text-slate-500 hover:text-rose-400"
              :title="t('variants.remove')"
              @click.stop="onRemove(variant.id)"
            >✕</span>
          </button>
        </template>
        <button
          type="button"
          class="rounded border border-dashed border-slate-700 px-1.5 py-0.5 text-[11px] text-slate-300 hover:border-emerald-600 hover:text-emerald-200"
          :title="t('variants.add')"
          @click="onAdd"
        >+ {{ t('variants.add') }}</button>
        <button
          type="button"
          class="ml-auto rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[11px] text-slate-300 hover:border-slate-600"
          :title="t('variants.updateHint')"
          @click="store.updateActiveVariant"
        >{{ t('variants.update') }}</button>
      </div>
    </template>
  </div>
</template>
