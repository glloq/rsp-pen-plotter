<script setup lang="ts">
// SheetPreview orchestrator (L10 #2 finalize).
//
// Post-split this component is a thin wiring layer:
//   - drives ``useSheetGeometry`` with the job store's profile +
//     placements + the UI store's preview sheet
//   - owns view-transform state (zoom / pan / snapMm) + container
//     pan-gesture handler + drag-and-drop + keyboard delete + the
//     generation button
//   - composes ``<SheetCanvas>`` (presentational SVG surface) and
//     ``<PlacementHandles>`` (interactive bounding boxes + resize
//     gestures) inside the workspace SVG
//
// Heavy lifting lives in the three siblings:
//   - ``useSheetGeometry``    — workspace, grid, renderedPlacements,
//                                tier helpers, pxPerMm,
//                                clientToSvgMm, snap
//   - ``<SheetCanvas>``       — workspace + grid + foreignObject
//                                preview tiers
//   - ``<PlacementHandles>``  — bounding box + resize handles +
//                                page/variant chip, with move/resize
//                                emit-only interactions

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'
import { useSheetGeometry } from '../composables/useSheetGeometry'
import SheetCanvas from './SheetCanvas.vue'
import PlacementHandles from './PlacementHandles.vue'

const { t } = useI18n()
const store = useJobStore()
const ui = useUiStore()

const container = ref<HTMLDivElement | null>(null)
const svgEl = ref<SVGSVGElement | null>(null)

// View transform (zoom/pan) is independent of placement scale.
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const snapMm = ref(0)
const snapOptions = [0, 1, 5, 10]
// Aspect-ratio lock for resize gestures. Defaults to locked because
// plotter sources (typography, vectors, raster bitmaps) almost always
// want to preserve proportions; the toolbar toggle lets the operator
// stretch a placement deliberately.
const aspectLock = ref(true)

// Reactive sources for the geometry composable. The composable
// recomputes when any of these change; the SheetCanvas + PlacementHandles
// receive the derived data as props.
const profileRef = computed(() => store.selectedProfile)
const placementsRef = computed(() => store.placements)
const previewSheetRef = computed(() => ui.previewSheet)

const {
  workspace,
  renderedPlacements,
  grid,
  previewSheetRect,
  anyExceeds,
  snap,
  pxPerMm,
  clientToSvgMm,
  showsPreviewImage,
  showsPlotterSvg,
  showsMimeBadge,
  onPreviewLoad,
  onPreviewError,
} = useSheetGeometry({
  profile: profileRef,
  placements: placementsRef,
  previewSheet: previewSheetRef,
  snapMm,
  container,
  svgEl,
})

function resetView(): void {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
}
function zoomIn(): void {
  zoom.value = Math.min(zoom.value * 1.25, 12)
}
function zoomOut(): void {
  zoom.value = Math.max(zoom.value / 1.25, 0.2)
}
watch(
  () => store.selectedProfileName,
  () => resetView(),
)

// Container-level pan: when the operator grabs background (not a
// placement), drag = pan-view, wheel = zoom.
type ContainerMode = 'idle' | 'pan-view'
const containerMode = ref<ContainerMode>('idle')

function onWheel(event: WheelEvent): void {
  event.preventDefault()
  const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15
  zoom.value = Math.max(0.2, Math.min(zoom.value * factor, 12))
}

// PlacementHandles stops propagation on its own pointerdown, so we
// only see background drags here. ``movementX``/``movementY`` on the
// move event gives us the per-frame delta — no need to track the
// start point.
function onContainerPointerDown(event: PointerEvent): void {
  if (event.button !== 0 && event.button !== 1) return
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  containerMode.value = 'pan-view'
}

function onContainerPointerMove(event: PointerEvent): void {
  if (containerMode.value !== 'pan-view') return
  panX.value += event.movementX
  panY.value += event.movementY
}

function onContainerPointerUp(event: PointerEvent): void {
  containerMode.value = 'idle'
  try {
    ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
  } catch {
    // Pointer capture may have lapsed when the operator dragged out
    // of the canvas; swallowing keeps the gesture cleanup idempotent.
  }
}

// PlacementHandles emits ``move`` / ``resize`` with the post-snap
// rect; we forward to ``setDrawing`` which mutates the currently-
// selected placement. The handles component selects on pointerdown
// so the right placement is always the target.
function onPlacementSelect(id: string): void {
  store.selectPlacement(id)
}
function onPlacementMove(patch: {
  id: string
  x_mm: number
  y_mm: number
  width_mm: number
  height_mm: number
}): void {
  store.setDrawing({
    x_mm: patch.x_mm,
    y_mm: patch.y_mm,
    width_mm: patch.width_mm,
    height_mm: patch.height_mm,
  })
}
function onPlacementResize(patch: {
  id: string
  x_mm: number
  y_mm: number
  width_mm: number
  height_mm: number
}): void {
  store.setDrawing({
    x_mm: patch.x_mm,
    y_mm: patch.y_mm,
    width_mm: patch.width_mm,
    height_mm: patch.height_mm,
  })
}
function onPlacementDoubleClick(id: string): void {
  store.selectPlacement(id)
  ui.openEditModal()
}
async function onPlacementPageChange(payload: { id: string; page: number }): Promise<void> {
  if (!Number.isFinite(payload.page)) return
  // The chip belongs to the SELECTED placement, but ``changePage``
  // implicitly targets the currently selected one — bail if the
  // selection got out from under us between mousedown and change.
  if (store.selectedPlacementId !== payload.id) {
    store.selectPlacement(payload.id)
  }
  await store.changePage(payload.page)
}
function onPlacementVariantChange(payload: { id: string; variantId: string }): void {
  store.setPlacementActiveVariant(payload.id, payload.variantId)
}
function onPlacementRemove(id: string): void {
  store.removePlacement(id)
}

// Drag-and-drop from FilesPane: a drag carries either a library file
// id (``application/x-omniplot-library``) — which creates a new
// placement on the plan referencing that library entry — or a
// placement id (``application/x-omniplot-file``) for in-plan
// duplication / repositioning.
const dragOver = ref(false)
function hasDropPayload(types?: readonly string[]): boolean {
  if (!types) return false
  return (
    types.includes('application/x-omniplot-file') ||
    types.includes('application/x-omniplot-library')
  )
}
function onDragEnter(event: DragEvent): void {
  if (hasDropPayload(event.dataTransfer?.types)) {
    event.preventDefault()
    dragOver.value = true
  }
}
function onDragOver(event: DragEvent): void {
  if (hasDropPayload(event.dataTransfer?.types)) {
    event.preventDefault()
    dragOver.value = true
  }
}
function onDragLeave(event: DragEvent): void {
  if (event.currentTarget === event.target) dragOver.value = false
}

async function onDrop(event: DragEvent): Promise<void> {
  event.preventDefault()
  dragOver.value = false
  const w = workspace.value
  if (!w) return
  const local = clientToSvgMm(event.clientX, event.clientY)
  if (!local) return

  // Drop from the library: spawn a new placement bound to that file id.
  const libraryId = event.dataTransfer?.getData('application/x-omniplot-library')
  if (libraryId) {
    const newId = await store.createPlacementFromLibrary(libraryId, {
      x: local.x,
      y: local.y,
    })
    if (newId) store.selectPlacement(newId)
    return
  }

  const sourceId = event.dataTransfer?.getData('application/x-omniplot-file')
  if (!sourceId) return
  const src = store.placements.find((p) => p.id === sourceId)
  if (!src) return
  // If the source placement has no svg yet, the user is just
  // positioning the (empty) draft. Otherwise duplicate it at the
  // drop position.
  if (!src.svg || !src.layers.length) {
    const prev = store.selectedPlacementId
    store.selectPlacement(sourceId)
    store.setDrawing({
      x_mm: Math.max(0, local.x - src.width_mm / 2 - w.ws.x_min),
      y_mm: Math.max(0, local.y - src.height_mm / 2 - w.ws.y_min),
      width_mm: src.width_mm,
      height_mm: src.height_mm,
    })
    if (prev) store.selectPlacement(prev)
    return
  }
  // Duplicate at the drop point, centred on the cursor.
  const newId = store.duplicatePlacement(sourceId)
  if (!newId) return
  const prev = store.selectedPlacementId
  store.selectPlacement(newId)
  store.setDrawing({
    x_mm: Math.max(0, local.x - src.width_mm / 2 - w.ws.x_min),
    y_mm: Math.max(0, local.y - src.height_mm / 2 - w.ws.y_min),
    width_mm: src.width_mm,
    height_mm: src.height_mm,
  })
  if (prev) store.selectPlacement(prev)
}

const containerCursor = computed(() => {
  if (containerMode.value === 'pan-view') return 'grabbing'
  return 'grab'
})

const canGenerate = computed(() => {
  const ready = store.placements.some((p) => p.svg && p.layers.length)
  return ready && store.missingPenSlots.length === 0 && !store.generating
})

async function generateAndShow(): Promise<void> {
  await store.generate()
  if (store.gcode) {
    ui.canvasTab = store.selectedProfile?.gcode_dialect === 'ebb' ? 'gcode' : 'simulator'
  }
}

const placementCount = computed(() => store.placements.filter((p) => p.svg).length)

// Image editing tools act on the currently-selected placement.
// Buttons are disabled when nothing is selected so the header
// buttons can't fire store mutations against ``null``.
const hasSelection = computed(() => store.selectedPlacementId !== null)

function rotateSelected(deltaDeg: number): void {
  const id = store.selectedPlacementId
  if (id) store.rotatePlacement(id, deltaDeg)
}
function flipSelected(axis: 'h' | 'v'): void {
  const id = store.selectedPlacementId
  if (id) store.flipPlacement(id, axis)
}

// Delete / Backspace removes the currently selected placement from
// the plan when the canvas has focus. We ignore the shortcut while
// the user is typing in a field or has a modal/drawer open, since
// those own their own keyboard handling.
function onKey(event: KeyboardEvent): void {
  if (event.key !== 'Delete' && event.key !== 'Backspace') return
  const target = event.target as HTMLElement | null
  if (
    target &&
    (target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.tagName === 'SELECT' ||
      target.isContentEditable)
  ) {
    return
  }
  if (ui.editModalOpen || ui.settingsOpen || ui.plotterDrawerOpen) return
  const id = store.selectedPlacementId
  if (!id) return
  event.preventDefault()
  store.removePlacement(id)
}

onMounted(() => {
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
})

// Composite multiplier turning client-pixel deltas into mm, used by
// PlacementHandles' gesture math.
function pxToMm(): number {
  return zoom.value * pxPerMm()
}
</script>

<template>
  <div v-if="workspace" class="flex h-full w-full min-h-0 flex-col gap-2">
    <header
      class="flex flex-wrap items-center gap-1 rounded border border-slate-700 bg-slate-900/40 px-2 py-1.5 text-xs"
    >
      <div class="flex items-center gap-1">
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200 hover:bg-slate-800"
          :title="t('sheet.zoomOut')"
          @click="zoomOut"
        >
          −
        </button>
        <span class="w-12 text-center font-mono text-slate-300">{{ Math.round(zoom * 100) }}%</span>
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200 hover:bg-slate-800"
          :title="t('sheet.zoomIn')"
          @click="zoomIn"
        >
          +
        </button>
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-300 hover:bg-slate-800"
          @click="resetView"
        >
          {{ t('sheet.resetView') }}
        </button>
      </div>

      <div class="h-5 w-px bg-slate-700 mx-1" />

      <div class="flex items-center gap-1">
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!hasSelection"
          :title="t('sheet.rotateLeft')"
          :aria-label="t('sheet.rotateLeft')"
          @click="rotateSelected(-90)"
        >
          <svg
            viewBox="0 0 16 16"
            class="h-4 w-4"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M3 8a5 5 0 1 0 5-5" />
            <polyline points="3 3 3 7 7 7" />
          </svg>
        </button>
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!hasSelection"
          :title="t('sheet.rotateRight')"
          :aria-label="t('sheet.rotateRight')"
          @click="rotateSelected(90)"
        >
          <svg
            viewBox="0 0 16 16"
            class="h-4 w-4"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M13 8a5 5 0 1 1-5-5" />
            <polyline points="13 3 13 7 9 7" />
          </svg>
        </button>
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!hasSelection"
          :title="t('sheet.flipH')"
          :aria-label="t('sheet.flipH')"
          @click="flipSelected('h')"
        >
          <svg
            viewBox="0 0 16 16"
            class="h-4 w-4"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <line x1="8" y1="2" x2="8" y2="14" stroke-dasharray="1.5 1.5" />
            <polygon points="3 4 6.5 8 3 12" fill="currentColor" />
            <polygon points="13 4 9.5 8 13 12" fill="currentColor" />
          </svg>
        </button>
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!hasSelection"
          :title="t('sheet.flipV')"
          :aria-label="t('sheet.flipV')"
          @click="flipSelected('v')"
        >
          <svg
            viewBox="0 0 16 16"
            class="h-4 w-4"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <line x1="2" y1="8" x2="14" y2="8" stroke-dasharray="1.5 1.5" />
            <polygon points="4 3 8 6.5 12 3" fill="currentColor" />
            <polygon points="4 13 8 9.5 12 13" fill="currentColor" />
          </svg>
        </button>
      </div>

      <div class="h-5 w-px bg-slate-700 mx-1" />

      <button
        type="button"
        class="rounded border px-2 py-1 hover:bg-slate-800"
        :class="
          aspectLock
            ? 'border-emerald-500 bg-emerald-950/40 text-emerald-200'
            : 'border-slate-700 bg-slate-900 text-slate-300'
        "
        :title="aspectLock ? t('sheet.aspectLockOn') : t('sheet.aspectLockOff')"
        :aria-label="aspectLock ? t('sheet.aspectLockOn') : t('sheet.aspectLockOff')"
        :aria-pressed="aspectLock"
        @click="aspectLock = !aspectLock"
      >
        <svg
          v-if="aspectLock"
          viewBox="0 0 16 16"
          class="h-4 w-4"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <rect x="3.5" y="7" width="9" height="6" rx="1" />
          <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
        </svg>
        <svg
          v-else
          viewBox="0 0 16 16"
          class="h-4 w-4"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <rect x="3.5" y="7" width="9" height="6" rx="1" />
          <path d="M5.5 7V5a2.5 2.5 0 0 1 4.6-1" />
        </svg>
      </button>

      <div class="h-5 w-px bg-slate-700 mx-1" />

      <label class="flex items-center gap-1" :title="t('sheet.snap')">
        <svg
          viewBox="0 0 16 16"
          class="h-4 w-4 text-slate-400"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="M2 4h12M2 8h12M2 12h12M4 2v12M8 2v12M12 2v12" />
        </svg>
        <select
          v-model.number="snapMm"
          class="rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-slate-200 focus:outline-none focus:ring-1 focus:ring-slate-500"
          :aria-label="t('sheet.snap')"
        >
          <option v-for="opt in snapOptions" :key="opt" :value="opt">
            {{ opt === 0 ? t('sheet.snapOff') : `${opt} mm` }}
          </option>
        </select>
      </label>

      <div class="ml-auto flex items-center gap-2">
        <span v-if="placementCount" class="font-mono text-slate-400">
          {{ t('sheet.placements', { count: placementCount }) }}
        </span>
        <button
          type="button"
          class="rounded bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="!canGenerate"
          :title="
            store.missingPenSlots.length
              ? t('preflight.missingPens', { slots: store.missingPenSlots.join(', ') })
              : ''
          "
          @click="generateAndShow"
        >
          {{ store.generating ? t('layers.generating') : t('layers.generate') }}
        </button>
      </div>
    </header>

    <div
      ref="container"
      class="relative min-h-0 flex-1 overflow-hidden rounded border select-none"
      :class="
        dragOver ? 'border-emerald-400 bg-emerald-950/30' : 'border-slate-700 bg-slate-900/40'
      "
      :style="{ touchAction: 'none', cursor: containerCursor }"
      @wheel="onWheel"
      @pointerdown="onContainerPointerDown"
      @pointermove="onContainerPointerMove"
      @pointerup="onContainerPointerUp"
      @pointercancel="onContainerPointerUp"
      @dragenter="onDragEnter"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
    >
      <div
        class="absolute inset-0"
        :style="{
          transform: `translate(${panX}px, ${panY}px) scale(${zoom})`,
          transformOrigin: '50% 50%',
        }"
      >
        <svg
          ref="svgEl"
          :viewBox="`${workspace.ws.x_min - workspace.pad} ${workspace.ws.y_min - workspace.pad} ${workspace.wsW + 2 * workspace.pad} ${workspace.wsH + 2 * workspace.pad}`"
          class="h-full w-full"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          :aria-label="t('sheet.title')"
        >
          <SheetCanvas
            :workspace="workspace"
            :grid="grid"
            :preview-sheet-rect="previewSheetRect"
            :rendered-placements="renderedPlacements"
            :shows-preview-image="showsPreviewImage"
            :shows-plotter-svg="showsPlotterSvg"
            :shows-mime-badge="showsMimeBadge"
            :on-preview-load="onPreviewLoad"
            :on-preview-error="onPreviewError"
          />
          <PlacementHandles
            :rendered-placements="renderedPlacements"
            :selected-placement-id="store.selectedPlacementId"
            :px-to-mm="pxToMm"
            :snap="snap"
            :snap-active="snapMm > 0"
            :aspect-lock="aspectLock"
            :loading="store.loading"
            @select="onPlacementSelect"
            @move="onPlacementMove"
            @resize="onPlacementResize"
            @double-click="onPlacementDoubleClick"
            @page-change="onPlacementPageChange"
            @variant-change="onPlacementVariantChange"
            @remove="onPlacementRemove"
          />
        </svg>
      </div>

      <p class="pointer-events-none absolute bottom-1 right-2 text-[10px] text-slate-500">
        {{ t('sheet.viewHint') }}
      </p>
    </div>

    <p v-if="anyExceeds" class="text-xs text-red-400">
      {{ t('sheet.outOfBounds') }}
    </p>
  </div>
</template>
