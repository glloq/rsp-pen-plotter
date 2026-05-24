<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { resetEditState } from '../composables/useEditState'
import { resetFileManager, useFileManager } from '../composables/useFileManager'
import { useBitmapDraft } from '../composables/useBitmapDraft'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'
import EditPreviewPane from './edit/EditPreviewPane.vue'
import EditTabs, { type EditTabId } from './edit/EditTabs.vue'
import VariantsBar from './edit/VariantsBar.vue'
import UploadFooter from './edit/UploadFooter.vue'
import EmptyPlacementDropzone from './edit/EmptyPlacementDropzone.vue'
import ColorsTab from './edit/tabs/ColorsTab.vue'
import RenderTab from './edit/tabs/RenderTab.vue'
import LayersTab from './edit/tabs/LayersTab.vue'

const { t } = useI18n()
const ui = useUiStore()
const store = useJobStore()
const draft = useBitmapDraft()
const fm = useFileManager(t)
const { editModalOpen } = storeToRefs(ui)

// Guard close: if the operator changed knobs since the last Apply,
// confirm before discarding. Wraps both the keyboard Escape path and
// the click-on-overlay path; the explicit "Done" button has its own
// handler so we can warn from there too.
function closeWithConfirm(): void {
  if (draft.isDirty.value) {
    const ok = window.confirm(t('editModal.unsavedWarning'))
    if (!ok) return
  }
  ui.closeEditModal()
}

const headerTitle = computed(() => {
  const name = store.lastFile?.name ?? store.job?.source_file ?? null
  return name ? `${t('editModal.title')} — ${name}` : t('editModal.title')
})

// ============================== TABS ==============================
// Right pane is split into Source / Layers / Variants tabs so the long
// scroll is broken into focused contexts. Tab choice persists across
// reopens via localStorage. Auto-jumps to "layers" once a placement
// actually has layers so the operator lands on the per-colour controls
// instead of the (often blank) Source tab.
const TAB_KEY = 'omniplot.editModal.activeTab'
const activeTab = ref<EditTabId>(loadInitialTab())

function loadInitialTab(): EditTabId {
  try {
    const stored = localStorage.getItem(TAB_KEY)
    if (
      stored === 'colors'
      || stored === 'render'
      || stored === 'layers'
    ) return stored
    // Legacy ids ('source' and 'variants') from earlier iterations
    // fall back to 'colors' — the first step of the new workflow.
  } catch {
    // localStorage unavailable
  }
  return 'colors'
}

watch(activeTab, (tab) => {
  try { localStorage.setItem(TAB_KEY, tab) } catch { /* ignore */ }
})

const layerCount = computed(() => store.layers.length)
const variantCount = computed(() => store.selectedPlacement?.variants.length ?? 0)

// Number keys 1-3 jump to tabs; Escape closes (handled below). Avoid
// hijacking the shortcuts while the user is typing into an input.
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable
}

function onKey(event: KeyboardEvent): void {
  if (!editModalOpen.value) return
  if (event.key === 'Escape') {
    closeWithConfirm()
    return
  }
  if (isTypingTarget(event.target)) return
  if (event.key === '1') { activeTab.value = 'colors'; event.preventDefault() }
  else if (event.key === '2') { activeTab.value = 'render'; event.preventDefault() }
  else if (event.key === '3') { activeTab.value = 'layers'; event.preventDefault() }
}

// ============================== RESIZABLE SPLIT ==============================
// Draggable divider between the preview (left) and settings (right).
// Width is stored in localStorage so the user's choice survives reopens.
const PREVIEW_WIDTH_KEY = 'omniplot.editModal.previewWidthPx'
const PREVIEW_MIN_PX = 280
const SETTINGS_MIN_PX = 360
const HANDLE_PX = 6

function initialPreviewWidth(): number {
  try {
    const stored = localStorage.getItem(PREVIEW_WIDTH_KEY)
    if (stored) {
      const value = Number(stored)
      if (Number.isFinite(value) && value > 0) return value
    }
  } catch {
    // localStorage may be unavailable; fall through to default.
  }
  // Default: ~58% of viewport width on first open.
  return Math.max(PREVIEW_MIN_PX, Math.floor(window.innerWidth * 0.58))
}

const splitRef = ref<HTMLElement | null>(null)
const previewWidthPx = ref<number>(initialPreviewWidth())
const resizing = ref(false)

function startResize(event: PointerEvent): void {
  if (event.button !== 0) return
  event.preventDefault()
  resizing.value = true
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function onResizeMove(event: PointerEvent): void {
  if (!resizing.value) return
  const container = splitRef.value
  if (!container) return
  const rect = container.getBoundingClientRect()
  const proposed = event.clientX - rect.left
  const maxWidth = rect.width - SETTINGS_MIN_PX - HANDLE_PX
  previewWidthPx.value = Math.max(PREVIEW_MIN_PX, Math.min(maxWidth, proposed))
}

function onResizeEnd(event: PointerEvent): void {
  if (!resizing.value) return
  resizing.value = false
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
  try {
    localStorage.setItem(PREVIEW_WIDTH_KEY, String(Math.round(previewWidthPx.value)))
  } catch {
    // localStorage may be unavailable; not persisting is acceptable.
  }
}

function resetSplit(): void {
  previewWidthPx.value = Math.max(PREVIEW_MIN_PX, Math.floor(window.innerWidth * 0.58))
  try {
    localStorage.removeItem(PREVIEW_WIDTH_KEY)
  } catch {
    // ignore
  }
}

// Wipe the singleton edit-state + file-manager composables whenever
// the modal closes or its selected placement changes, so the preview
// pane never renders the previous session's stale file / SVG /
// palette before the new tab mounts get a chance to write fresh
// values.
watch(editModalOpen, (open) => {
  if (!open) {
    resetEditState()
    resetFileManager()
  }
})
watch(
  () => store.selectedPlacementId,
  () => {
    if (editModalOpen.value) resetEditState()
  },
)

// Auto-jump after upload: when the placement first acquires layers
// (i.e. the operator just hit Apply), land them on the Layers tab so
// they see the per-layer controls instead of staying on whatever tab
// they applied from. Skip when the user is on Variants since that's a
// deliberate side-trip.
watch(
  () => store.layers.length,
  (count, prev) => {
    if (!editModalOpen.value) return
    if (count > 0 && (prev ?? 0) === 0) {
      activeTab.value = 'layers'
    }
  },
)

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div
    v-if="editModalOpen"
    class="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-4"
    @click.self="closeWithConfirm"
  >
    <div
      role="dialog"
      aria-modal="true"
      class="flex h-full max-h-[95vh] w-full max-w-[1600px] flex-col rounded-lg border border-slate-700 bg-slate-900 shadow-2xl"
      :style="{ width: '95vw' }"
    >
      <header class="flex items-center justify-between gap-3 border-b border-slate-700 px-4 py-3">
        <h2 class="min-w-0 truncate text-base font-semibold text-slate-100" :title="headerTitle">
          {{ headerTitle }}
        </h2>
        <div class="flex shrink-0 items-center gap-1">
          <button
            type="button"
            class="rounded bg-slate-800 px-3 py-1 text-xs text-slate-200 hover:bg-slate-700"
            @click="closeWithConfirm"
          >
            {{ t('editModal.done') }}
          </button>
        </div>
      </header>

      <!-- Split-pane: preview on the left, scrollable settings on the
           right, with a draggable divider so the user can dedicate more
           space to either side. The two panes communicate via the
           module-level useEditState singleton (see
           composables/useEditState.ts) which SourceSection mirrors its
           local state into. -->
      <main
        ref="splitRef"
        class="flex min-h-0 flex-1 overflow-hidden"
        :class="resizing ? 'cursor-col-resize select-none' : ''"
      >
        <div
          class="min-h-0 overflow-hidden border-r border-slate-700 bg-slate-950/60"
          :style="{ flexBasis: previewWidthPx + 'px', flexShrink: 1, flexGrow: 0, minWidth: PREVIEW_MIN_PX + 'px' }"
        >
          <EditPreviewPane />
        </div>
        <div
          class="group flex shrink-0 cursor-col-resize items-center justify-center bg-slate-800 transition hover:bg-emerald-600"
          :class="resizing ? 'bg-emerald-500' : ''"
          :style="{ width: HANDLE_PX + 'px' }"
          :title="t('editModal.resizeHandle')"
          @pointerdown="startResize"
          @pointermove="onResizeMove"
          @pointerup="onResizeEnd"
          @pointercancel="onResizeEnd"
          @dblclick="resetSplit"
        >
          <span class="text-[10px] leading-none text-slate-500 group-hover:text-white">⋮</span>
        </div>
        <div
          class="flex min-h-0 flex-1 flex-col"
          :style="{ minWidth: SETTINGS_MIN_PX + 'px' }"
        >
          <!-- Empty-placement edge case: show the dropzone instead of
               the tabs so the operator can attach the first file
               without leaving the modal. Tabs reappear automatically
               once a file is set. -->
          <template v-if="!fm.hasSource.value">
            <EmptyPlacementDropzone />
          </template>
          <template v-else>
            <VariantsBar />
            <EditTabs
              v-model="activeTab"
              :layer-count="layerCount"
              :variant-count="variantCount"
            />
            <div class="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
              <!-- v-show keeps each tab's component mounted so internal
                   state (drafts, scroll, dropdown open/closed) isn't
                   lost when the operator hops between tabs. -->
              <div v-show="activeTab === 'colors'" class="space-y-3">
                <ColorsTab />
              </div>
              <div v-show="activeTab === 'render'" class="space-y-3">
                <RenderTab />
              </div>
              <div v-show="activeTab === 'layers'" class="space-y-3">
                <LayersTab />
              </div>
            </div>
            <!-- Sticky upload footer so Apply is reachable from any tab.
                 Mounted once at the modal level (not per-tab) so the
                 apply button is uniform across tabs. -->
            <UploadFooter />
          </template>
        </div>
      </main>
    </div>
  </div>
</template>
