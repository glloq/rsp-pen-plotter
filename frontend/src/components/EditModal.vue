<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { resetEditState, useEditState } from '../composables/useEditState'
import { resetFileManager, useFileManager } from '../composables/useFileManager'
import { useBitmapDraft } from '../composables/useBitmapDraft'
import { confirmAction } from '../composables/confirm'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'
import EditPreviewPane from './edit/EditPreviewPane.vue'
import EditTabs, { type EditTabId } from './edit/EditTabs.vue'
import VariantsBar from './edit/VariantsBar.vue'
import UploadFooter from './edit/UploadFooter.vue'
import EmptyPlacementDropzone from './edit/EmptyPlacementDropzone.vue'
import ImageTab from './edit/tabs/ImageTab.vue'
import SvgTab from './edit/tabs/SvgTab.vue'
import StyleTab from './edit/tabs/StyleTab.vue'
import LayersTab from './edit/tabs/LayersTab.vue'

const { t } = useI18n()
const ui = useUiStore()
const store = useJobStore()
const draft = useBitmapDraft()
const fm = useFileManager(t)
const edit = useEditState()
const { editModalOpen } = storeToRefs(ui)

// Guard close: if the operator changed knobs since the last Apply,
// confirm before discarding. Wraps both the keyboard Escape path and
// the click-on-overlay path; the explicit close button has its own
// handler so we can warn from there too.
async function closeWithConfirm(): Promise<void> {
  if (draft.isDirty.value) {
    const ok = await confirmAction({
      title: t('editModal.unsavedTitle'),
      message: t('editModal.unsavedWarning'),
      confirmLabel: t('editModal.unsavedDiscard'),
      cancelLabel: t('confirm.cancel'),
      danger: true,
    })
    if (!ok) return
  }
  ui.closeEditModal()
}

const sourceName = computed(() => fm.sourceName.value)

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
    if (stored === 'image' || stored === 'svg' || stored === 'style' || stored === 'layers') {
      return stored
    }
    // Legacy ids from earlier iterations migrate forward: the SVG tab
    // absorbed the Curves tab; the Style tab absorbed Colors + Render.
    if (stored === 'curves') return 'svg'
    if (stored === 'colors' || stored === 'render') return 'style'
    // Legacy 'source' / 'variants' fall back to 'image'.
  } catch {
    // localStorage unavailable
  }
  return 'image'
}

watch(activeTab, (tab) => {
  try { localStorage.setItem(TAB_KEY, tab) } catch { /* ignore */ }
})

// Tell the preview pane to show the raw source raster (with the
// operator's preprocess adjustments overlaid) while they're on the
// Image tab — they're tuning the source pixels, the SVG renderer would
// only obscure what they're trying to see. Other tabs fall back to
// the live SVG / committed SVG / raster fallback chain.
//
// Reapplied on modal-open and on placement-switch as well as tab change:
// addEmptyPlacement + selectedPlacementId flips would otherwise land us
// here with the previous session's mode (or 'auto', the singleton's
// initial value) instead of the tab's intended default, leaving the
// operator's photo adjustments invisible on multicolour images.
function applyTabPreviewMode(): void {
  edit.previewMode.value = activeTab.value === 'image' ? 'source' : 'auto'
}
watch(activeTab, applyTabPreviewMode, { immediate: true })

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
  if (event.key === '1') { activeTab.value = 'image'; event.preventDefault() }
  else if (event.key === '2') { activeTab.value = 'svg'; event.preventDefault() }
  else if (event.key === '3') { activeTab.value = 'style'; event.preventDefault() }
  else if (event.key === '4') { activeTab.value = 'layers'; event.preventDefault() }
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

// Typography sources only have meaningful controls under the Style and
// Layers tabs — the Image (photo adjustments) and SVG (vectorisation
// knobs) tabs render a "not applicable" message. Force the operator
// onto Style when they open the modal on a .txt / .md file so the
// font / size / bold / italic controls are actually visible. Without
// this, the operator's last-used tab (typically Image, since that's
// the default for bitmaps) silently hides every typography knob and
// the modal looks like it has no font settings at all.
function ensureTabAppliesToSource(): void {
  if (fm.kind.value !== 'typography') return
  if (activeTab.value === 'image' || activeTab.value === 'svg') {
    activeTab.value = 'style'
  }
}

// Wipe the singleton edit-state + file-manager composables whenever
// the modal closes or its selected placement changes, so the preview
// pane never renders the previous session's stale file / SVG /
// palette before the new tab mounts get a chance to write fresh
// values.
watch(editModalOpen, (open) => {
  if (open) {
    // Re-derive preview mode from the active tab on every modal open.
    // The opener flow (addEmptyPlacement → selectedPlacementId watch →
    // resetEditState) runs before this watch, so without re-applying
    // here the Image tab would land on 'auto' on first open instead of
    // its intended 'source' default.
    ensureTabAppliesToSource()
    applyTabPreviewMode()
  } else {
    resetEditState()
    resetFileManager()
  }
})
watch(
  () => store.selectedPlacementId,
  () => {
    if (editModalOpen.value) {
      resetEditState()
      // Re-apply tab→mode after the reset so a placement switch within
      // the modal doesn't drop us out of the Image tab's source mode.
      ensureTabAppliesToSource()
      applyTabPreviewMode()
    }
  },
)
// Source kind changes (rare — usually the operator drags a different
// file onto an existing placement) also need the auto-jump so they
// don't end up staring at the wrong tab for the new file type.
watch(() => fm.kind.value, ensureTabAppliesToSource)

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
      <header class="flex items-center gap-3 border-b border-slate-700 px-3 py-2">
        <!-- Filename chip -->
        <div
          class="flex shrink-0 items-center gap-1.5 rounded border border-slate-600 bg-slate-800/80 px-2 py-1 text-xs"
          :title="sourceName || t('editModal.title')"
        >
          <svg class="h-3 w-3 shrink-0 text-slate-400" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <path d="M4 1h5.586L13 4.414V15H3V1h1zm0-1H3a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V4.414a1 1 0 0 0-.293-.707L9.293.293A1 1 0 0 0 8.586 0H4z"/>
            <path d="M9 4V1l3.5 3.5H9.5A.5.5 0 0 1 9 4z"/>
          </svg>
          <span class="max-w-[200px] truncate font-mono text-slate-200">
            {{ sourceName || t('editModal.title') }}
          </span>
        </div>
        <!-- Variants bar inline -->
        <div class="min-w-0 flex-1">
          <VariantsBar v-if="fm.hasSource.value" :inline="true" />
        </div>
        <!-- Close button (red × ) -->
        <button
          type="button"
          class="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-red-700 text-sm font-bold text-white hover:bg-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
          :title="t('editModal.close')"
          @click="closeWithConfirm"
        >
          ✕
        </button>
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
            <EditTabs
              v-model="activeTab"
              :layer-count="layerCount"
              :variant-count="variantCount"
            />
            <div class="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
              <!-- v-show keeps each tab's component mounted so internal
                   state (drafts, scroll, dropdown open/closed) isn't
                   lost when the operator hops between tabs. -->
              <div v-show="activeTab === 'image'" class="space-y-3">
                <ImageTab />
              </div>
              <div v-show="activeTab === 'svg'" class="space-y-3">
                <SvgTab />
              </div>
              <div v-show="activeTab === 'style'" class="space-y-3">
                <StyleTab />
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
