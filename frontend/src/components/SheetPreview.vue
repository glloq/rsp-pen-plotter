<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import DOMPurify from 'dompurify'
import { libraryFileOriginalUrl } from '../api/client'
import { shortMime } from '../lib/labels'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'
import type { Placement } from '../stores/job'

const { t } = useI18n()
const store = useJobStore()
const ui = useUiStore()

// Workspace data — always available as long as a profile is selected so
// the plan stays visible even without any imported file.
const workspace = computed(() => {
  const profile = store.selectedProfile
  if (!profile) return null
  const ws = profile.workspace
  const wsW = ws.x_max - ws.x_min
  const wsH = ws.y_max - ws.y_min
  if (wsW <= 0 || wsH <= 0) return null
  const pad = Math.max(wsW, wsH) * 0.04
  return { profile, ws, wsW, wsH, pad }
})

// Each placement gets its own rendering rect on the plan. We project
// workspace-relative ``x/y/width/height`` onto absolute machine coords
// using the active profile's origin.
interface RenderedPlacement {
  placement: Placement
  footprint: { x_min: number; y_min: number; x_max: number; y_max: number }
  exceeds: boolean
  cleanSvg: string
  // URL to the original uploaded bytes, only when the file is an image
  // we can display directly in the browser (raster + SVG sources). Empty
  // for PDFs / typography / other formats — those fall back to the
  // plotter SVG (tier 2) immediately.
  previewUrl: string
}

// DOMPurify.sanitize is expensive on large SVGs; without memoization it
// runs for every placement on every pointer-move during drag, which
// chokes the tab. Cache by placement id + raw svg so unchanged SVGs are
// reused across recomputations. Entries are evicted for placements that
// disappear from the plan.
const sanitizedCache = new Map<string, { svg: string; clean: string }>()

// Per-library-file load status for the source-preview image. ``reactive``
// so onload / onerror on the SVG ``<image>`` re-trigger the template
// without recomputing the heavy ``renderedPlacements`` chain.
type PreviewStatus = 'loading' | 'loaded' | 'failed'
const previewStatus = reactive<Record<string, PreviewStatus>>({})

function isDisplayableMime(mime: string): boolean {
  // Anything the browser can paint into an SVG ``<image>`` without a
  // server-side render step. SVG counts here because we draw it through
  // the bytes endpoint, which serves it with the right content type.
  if (!mime) return false
  if (mime.startsWith('image/')) return true
  return false
}

function onPreviewLoad(fileId: string): void {
  previewStatus[fileId] = 'loaded'
}
function onPreviewError(fileId: string): void {
  previewStatus[fileId] = 'failed'
}

const renderedPlacements = computed<RenderedPlacement[]>(() => {
  const w = workspace.value
  if (!w) return []
  const seen = new Set<string>()
  const out = store.placements.map((p) => {
    seen.add(p.id)
    const x_min = w.ws.x_min + p.x_mm
    const y_min = w.ws.y_min + p.y_mm
    const x_max = x_min + p.width_mm
    const y_max = y_min + p.height_mm
    const exceeds
      = x_min < w.ws.x_min - 0.01
      || y_min < w.ws.y_min - 0.01
      || x_max > w.ws.x_max + 0.01
      || y_max > w.ws.y_max + 0.01
    let cleanSvg = ''
    if (p.svg) {
      const cached = sanitizedCache.get(p.id)
      if (cached && cached.svg === p.svg) {
        cleanSvg = cached.clean
      } else {
        cleanSvg = DOMPurify.sanitize(p.svg, { USE_PROFILES: { svg: true, svgFilters: true } })
        sanitizedCache.set(p.id, { svg: p.svg, clean: cleanSvg })
      }
    } else {
      sanitizedCache.delete(p.id)
    }
    // Tier 1 source preview is only attempted when (a) we have a library
    // entry to read bytes from, and (b) the MIME is one the browser can
    // paint without an extra server-side render step.
    const previewUrl
      = p.library_file_id && isDisplayableMime(p.source_mime)
        ? libraryFileOriginalUrl(p.library_file_id)
        : ''
    return {
      placement: p,
      footprint: { x_min, y_min, x_max, y_max },
      exceeds,
      cleanSvg,
      previewUrl,
    }
  })
  for (const id of sanitizedCache.keys()) {
    if (!seen.has(id)) sanitizedCache.delete(id)
  }
  return out
})

// Should tier 1 (source preview <image>) actually be shown for this
// placement? True when we have a URL and the load hasn't failed.
function showsPreviewImage(rp: RenderedPlacement): boolean {
  if (!rp.previewUrl) return false
  const status = previewStatus[rp.placement.library_file_id ?? '']
  return status !== 'failed'
}

// Should tier 2 (inline plotter SVG) be shown? Hide it when tier 1 has
// fully loaded, so we don't double-paint the same drawing. Show it as
// the fallback whenever tier 1 isn't usable.
function showsPlotterSvg(rp: RenderedPlacement): boolean {
  if (!rp.cleanSvg) return false
  if (!rp.previewUrl) return true
  const status = previewStatus[rp.placement.library_file_id ?? '']
  return status !== 'loaded'
}

// Tier 3: nothing else worked — render a small MIME badge so the
// placement footprint isn't visually empty.
function showsMimeBadge(rp: RenderedPlacement): boolean {
  if (rp.cleanSvg) return false
  if (showsPreviewImage(rp)) return false
  return true
}

const anyExceeds = computed(() => renderedPlacements.value.some((r) => r.exceeds))

// Sheet overlay shown when the user picked a sheet format in LayoutSection.
// Anchored at the workspace top-left, clipped to the workspace bounds, and
// purely decorative — no impact on placement logic.
const previewSheetRect = computed(() => {
  const w = workspace.value
  const sheet = ui.previewSheet
  if (!w || !sheet) return null
  const width = Math.max(0, Math.min(sheet.width_mm, w.wsW))
  const height = Math.max(0, Math.min(sheet.height_mm, w.wsH))
  if (width <= 0 || height <= 0) return null
  return { x: w.ws.x_min, y: w.ws.y_min, width, height }
})

// Grid: minor lines every 10 mm (1 cm), major every 50 mm (5 cm).
const grid = computed(() => {
  const w = workspace.value
  if (!w) return null
  const xs: number[] = []
  const ys: number[] = []
  const majorXs: number[] = []
  const majorYs: number[] = []
  const labelsX: { x: number; cm: number }[] = []
  const labelsY: { y: number; cm: number }[] = []
  for (let x = Math.ceil(w.ws.x_min / 10) * 10; x <= w.ws.x_max + 0.0001; x += 10) {
    xs.push(x)
    if (Math.round(x) % 50 === 0) {
      majorXs.push(x)
      labelsX.push({ x, cm: Math.round(x / 10) })
    }
  }
  for (let y = Math.ceil(w.ws.y_min / 10) * 10; y <= w.ws.y_max + 0.0001; y += 10) {
    ys.push(y)
    if (Math.round(y) % 50 === 0) {
      majorYs.push(y)
      labelsY.push({ y, cm: Math.round(y / 10) })
    }
  }
  return { xs, ys, majorXs, majorYs, labelsX, labelsY }
})

// View transform (zoom/pan) is independent of placement scale.
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
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
watch(() => store.selectedProfileName, () => resetView())

// Snap-to-grid: 0 = off, otherwise grid step in mm.
const snapMm = ref(0)
const snapOptions = [0, 1, 5, 10]
function snap(value: number): number {
  if (snapMm.value <= 0) return value
  return Math.round(value / snapMm.value) * snapMm.value
}

// Pointer interaction state. The active gesture is bound to whichever
// placement the user grabbed (recorded in ``activePlacementId``).
type Mode = 'idle' | 'pan-view' | 'move-drawing' | 'resize'
const mode = ref<Mode>('idle')
const handle = ref<'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | null>(null)
const activePlacementId = ref<string | null>(null)
const container = ref<HTMLDivElement | null>(null)
const svgEl = ref<SVGSVGElement | null>(null)
let startPxX = 0
let startPxY = 0
let startRegion: { x_mm: number; y_mm: number; width_mm: number; height_mm: number } | null = null

function pxPerMm(): number {
  const w = workspace.value
  if (!w || !container.value) return 1
  return container.value.clientWidth / (w.wsW + 2 * w.pad)
}

function onWheel(event: WheelEvent): void {
  event.preventDefault()
  const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15
  zoom.value = Math.max(0.2, Math.min(zoom.value * factor, 12))
}

function onPointerDown(event: PointerEvent): void {
  if (event.button !== 0 && event.button !== 1) return
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  startPxX = event.clientX
  startPxY = event.clientY
  if (mode.value === 'idle') mode.value = 'pan-view'
  else {
    // A placement gesture was pre-armed by its handler — record its
    // current position so the move/resize can compute deltas from it.
    const p = store.placements.find((pl) => pl.id === activePlacementId.value)
    if (p) startRegion = { x_mm: p.x_mm, y_mm: p.y_mm, width_mm: p.width_mm, height_mm: p.height_mm }
  }
}

function onPointerMove(event: PointerEvent): void {
  if (mode.value === 'idle') return
  const dxPx = event.clientX - startPxX
  const dyPx = event.clientY - startPxY
  if (mode.value === 'pan-view') {
    panX.value += event.movementX
    panY.value += event.movementY
    return
  }
  if (!startRegion || !activePlacementId.value) return
  const k = zoom.value * pxPerMm()
  const dxMm = dxPx / k
  const dyMm = dyPx / k
  if (mode.value === 'move-drawing') {
    updatePlacementRect(activePlacementId.value, {
      x_mm: snap(startRegion.x_mm + dxMm),
      y_mm: snap(startRegion.y_mm + dyMm),
      width_mm: startRegion.width_mm,
      height_mm: startRegion.height_mm,
    })
    return
  }
  if (mode.value === 'resize' && handle.value) {
    const minSize = 5
    let x = startRegion.x_mm
    let y = startRegion.y_mm
    let w = startRegion.width_mm
    let h = startRegion.height_mm
    if (handle.value.includes('w')) {
      const newW = Math.max(minSize, startRegion.width_mm - dxMm)
      x = startRegion.x_mm + (startRegion.width_mm - newW)
      w = newW
    } else if (handle.value.includes('e')) {
      w = Math.max(minSize, startRegion.width_mm + dxMm)
    }
    if (handle.value.includes('n')) {
      const newH = Math.max(minSize, startRegion.height_mm - dyMm)
      y = startRegion.y_mm + (startRegion.height_mm - newH)
      h = newH
    } else if (handle.value.includes('s')) {
      h = Math.max(minSize, startRegion.height_mm + dyMm)
    }
    updatePlacementRect(activePlacementId.value, {
      x_mm: snap(x),
      y_mm: snap(y),
      width_mm: snapMm.value > 0 ? Math.max(minSize, snap(w)) : w,
      height_mm: snapMm.value > 0 ? Math.max(minSize, snap(h)) : h,
    })
  }
}

function onPointerUp(event: PointerEvent): void {
  mode.value = 'idle'
  handle.value = null
  activePlacementId.value = null
  startRegion = null
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
}

function updatePlacementRect(
  _id: string,
  patch: { x_mm: number; y_mm: number; width_mm: number; height_mm: number },
): void {
  // ``setDrawing`` always edits the selected placement — startMove /
  // startResize already selected the right one on pointer-down.
  store.setDrawing(patch)
}

function startMoveDrawing(event: PointerEvent, id: string): void {
  if (event.button !== 0) return
  mode.value = 'move-drawing'
  activePlacementId.value = id
  store.selectPlacement(id)
}

function onPlacementDblClick(event: MouseEvent, id: string): void {
  event.stopPropagation()
  store.selectPlacement(id)
  ui.openEditModal()
}

function onVariantChange(event: Event, placementId: string): void {
  const select = event.target as HTMLSelectElement
  store.setPlacementActiveVariant(placementId, select.value)
}

// PDF page navigation from the in-canvas placement chip. The select
// shows up next to the variant picker whenever the source document
// has more than one page (PDF / DOCX / HTML go through the converter
// that reports ``page_count`` in upload metadata). Changing the
// selection re-converts the source for the new page and refits the
// placement to that page's native millimetre dimensions — see
// ``changePage`` in the job store.
function placementPageCount(p: { upload_metadata: Record<string, unknown> }): number {
  return Number(p.upload_metadata?.page_count ?? 0)
}
function placementCurrentPage(p: { upload_metadata: Record<string, unknown> }): number {
  return Number(p.upload_metadata?.page ?? 0)
}
async function onPageChange(event: Event, placementId: string): Promise<void> {
  const select = event.target as HTMLSelectElement
  const value = Number(select.value)
  if (!Number.isFinite(value)) return
  // The chip belongs to the SELECTED placement, but ``changePage``
  // implicitly targets the currently selected one — bail if the
  // selection got out from under us between mousedown and change.
  if (store.selectedPlacementId !== placementId) {
    store.selectPlacement(placementId)
  }
  await store.changePage(value)
}

function startResize(h: typeof handle.value, event: PointerEvent, id: string): void {
  if (event.button !== 0) return
  mode.value = 'resize'
  handle.value = h
  activePlacementId.value = id
  store.selectPlacement(id)
}

// Drag-and-drop from FilesPane: a drag carries either a library file id
// (``application/x-omniplot-library``) — which creates a new placement
// on the plan referencing that library entry — or a placement id
// (``application/x-omniplot-file``) for in-plan duplication / repositioning.
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

function clientToSvgMm(clientX: number, clientY: number): { x: number; y: number } | null {
  const svg = svgEl.value
  if (!svg) return null
  const pt = svg.createSVGPoint()
  pt.x = clientX
  pt.y = clientY
  const ctm = svg.getScreenCTM()
  if (!ctm) return null
  const local = pt.matrixTransform(ctm.inverse())
  return { x: local.x, y: local.y }
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
  // If the source placement has no svg yet, the user is just positioning
  // the (empty) draft. Otherwise duplicate it at the drop position.
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
  if (mode.value === 'pan-view') return 'grabbing'
  if (mode.value === 'move-drawing') return 'grabbing'
  if (mode.value === 'resize') return 'crosshair'
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

// Image editing tools act on the currently-selected placement. Buttons
// are disabled when nothing is selected so the header buttons can't fire
// store mutations against ``null``.
const hasSelection = computed(() => store.selectedPlacementId !== null)

function rotateSelected(deltaDeg: number): void {
  const id = store.selectedPlacementId
  if (id) store.rotatePlacement(id, deltaDeg)
}
function flipSelected(axis: 'h' | 'v'): void {
  const id = store.selectedPlacementId
  if (id) store.flipPlacement(id, axis)
}

// CSS transform applied to the foreignObject content so the previewed
// drawing matches the placement's rotation / mirror state. The inner
// box's width / height are swapped for a quarter-turn so the SVG renders
// at its post-rotation aspect ratio inside the placement footprint;
// ``transform-origin: 50% 50%`` keeps the rotation centred.
function placementInnerStyle(rp: RenderedPlacement): Record<string, string> {
  const p = rp.placement
  const rotated = p.rotation % 180 !== 0
  const parts: string[] = ['translate(-50%, -50%)']
  if (p.rotation) parts.push(`rotate(${p.rotation}deg)`)
  if (p.flip_h) parts.push('scaleX(-1)')
  if (p.flip_v) parts.push('scaleY(-1)')
  // When rotated 90°/270° the inner box is sized to the footprint's
  // (height, width) so a CSS rotate brings it to the footprint extent.
  const fpW = rp.footprint.x_max - rp.footprint.x_min
  const fpH = rp.footprint.y_max - rp.footprint.y_min
  const innerW = rotated ? fpH : fpW
  const innerH = rotated ? fpW : fpH
  return {
    position: 'absolute',
    left: '50%',
    top: '50%',
    width: `${innerW}px`,
    height: `${innerH}px`,
    transform: parts.join(' '),
    transformOrigin: '50% 50%',
  }
}

// Delete / Backspace removes the currently selected placement from the
// plan when the canvas has focus. We ignore the shortcut while the user
// is typing in a field or has a modal/drawer open, since those own their
// own keyboard handling.
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
  resetView()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
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
        >−</button>
        <span class="w-12 text-center font-mono text-slate-300">{{ Math.round(zoom * 100) }}%</span>
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200 hover:bg-slate-800"
          :title="t('sheet.zoomIn')"
          @click="zoomIn"
        >+</button>
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
          <svg viewBox="0 0 16 16" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
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
          <svg viewBox="0 0 16 16" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
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
          <svg viewBox="0 0 16 16" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
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
          <svg viewBox="0 0 16 16" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <line x1="2" y1="8" x2="14" y2="8" stroke-dasharray="1.5 1.5" />
            <polygon points="4 3 8 6.5 12 3" fill="currentColor" />
            <polygon points="4 13 8 9.5 12 13" fill="currentColor" />
          </svg>
        </button>
      </div>

      <div class="h-5 w-px bg-slate-700 mx-1" />

      <label class="flex items-center gap-1" :title="t('sheet.snap')">
        <svg viewBox="0 0 16 16" class="h-4 w-4 text-slate-400" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
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
          :title="store.missingPenSlots.length ? t('preflight.missingPens', { slots: store.missingPenSlots.join(', ') }) : ''"
          @click="generateAndShow"
        >
          {{ store.generating ? t('layers.generating') : t('layers.generate') }}
        </button>
      </div>
    </header>

    <div
      ref="container"
      class="relative min-h-0 flex-1 overflow-hidden rounded border select-none"
      :class="dragOver ? 'border-emerald-400 bg-emerald-950/30' : 'border-slate-700 bg-slate-900/40'"
      :style="{ touchAction: 'none', cursor: containerCursor }"
      @wheel="onWheel"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @dragenter="onDragEnter"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
    >
      <div
        class="absolute inset-0"
        :style="{ transform: `translate(${panX}px, ${panY}px) scale(${zoom})`, transformOrigin: '50% 50%' }"
      >
        <svg
          ref="svgEl"
          :viewBox="`${workspace.ws.x_min - workspace.pad} ${workspace.ws.y_min - workspace.pad} ${workspace.wsW + 2 * workspace.pad} ${workspace.wsH + 2 * workspace.pad}`"
          class="h-full w-full"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          :aria-label="t('sheet.title')"
        >
          <rect
            :x="workspace.ws.x_min"
            :y="workspace.ws.y_min"
            :width="workspace.wsW"
            :height="workspace.wsH"
            fill="#ffffff"
            stroke="#475569"
            stroke-width="1.5"
            vector-effect="non-scaling-stroke"
          />
          <g v-if="grid" pointer-events="none">
            <line
              v-for="x in grid.xs"
              :key="`gx-${x}`"
              :x1="x"
              :x2="x"
              :y1="workspace.ws.y_min"
              :y2="workspace.ws.y_max"
              :stroke="grid.majorXs.includes(x) ? '#cbd5e1' : '#e2e8f0'"
              :stroke-width="grid.majorXs.includes(x) ? 0.8 : 0.5"
              vector-effect="non-scaling-stroke"
            />
            <line
              v-for="y in grid.ys"
              :key="`gy-${y}`"
              :x1="workspace.ws.x_min"
              :x2="workspace.ws.x_max"
              :y1="y"
              :y2="y"
              :stroke="grid.majorYs.includes(y) ? '#cbd5e1' : '#e2e8f0'"
              :stroke-width="grid.majorYs.includes(y) ? 0.8 : 0.5"
              vector-effect="non-scaling-stroke"
            />
            <text
              v-for="label in grid.labelsX"
              :key="`lx-${label.x}`"
              :x="label.x"
              :y="workspace.ws.y_min - 1"
              text-anchor="middle"
              fill="#64748b"
              :font-size="Math.max(workspace.wsW, workspace.wsH) * 0.015"
              font-family="ui-sans-serif, system-ui, sans-serif"
            >
              {{ label.cm }}
            </text>
            <text
              v-for="label in grid.labelsY"
              :key="`ly-${label.y}`"
              :x="workspace.ws.x_min - 1"
              :y="label.y"
              text-anchor="end"
              dominant-baseline="central"
              fill="#64748b"
              :font-size="Math.max(workspace.wsW, workspace.wsH) * 0.015"
              font-family="ui-sans-serif, system-ui, sans-serif"
            >
              {{ label.cm }}
            </text>
          </g>

          <!-- Sheet overlay: transparent rectangle at workspace top-left
               representing the format chosen in LayoutSection. Decorative. -->
          <rect
            v-if="previewSheetRect"
            :x="previewSheetRect.x"
            :y="previewSheetRect.y"
            :width="previewSheetRect.width"
            :height="previewSheetRect.height"
            fill="#38bdf8"
            fill-opacity="0.12"
            stroke="#0ea5e9"
            stroke-width="1.2"
            stroke-dasharray="6 4"
            vector-effect="non-scaling-stroke"
            pointer-events="none"
          />

          <!-- Each placement: drawing content + interactive bbox + handles.
               Display fallback chain — tier 1 source preview (raster /
               SVG bytes as uploaded), tier 2 plotter SVG, tier 3 MIME
               badge placeholder. Tiers 1 and 2 share ``placementInnerStyle``
               so rotation / flip handling stays in one place. -->
          <template v-for="rp in renderedPlacements" :key="rp.placement.id">
            <foreignObject
              v-if="showsPreviewImage(rp)"
              :x="rp.footprint.x_min"
              :y="rp.footprint.y_min"
              :width="Math.max(rp.footprint.x_max - rp.footprint.x_min, 0.01)"
              :height="Math.max(rp.footprint.y_max - rp.footprint.y_min, 0.01)"
            >
              <div
                xmlns="http://www.w3.org/1999/xhtml"
                class="pointer-events-none overflow-hidden"
                :style="placementInnerStyle(rp)"
              >
                <img
                  :src="rp.previewUrl"
                  alt=""
                  draggable="false"
                  class="h-full w-full select-none object-fill"
                  @load="onPreviewLoad(rp.placement.library_file_id ?? '')"
                  @error="onPreviewError(rp.placement.library_file_id ?? '')"
                />
              </div>
            </foreignObject>
            <foreignObject
              v-if="showsPlotterSvg(rp)"
              :x="rp.footprint.x_min"
              :y="rp.footprint.y_min"
              :width="Math.max(rp.footprint.x_max - rp.footprint.x_min, 0.01)"
              :height="Math.max(rp.footprint.y_max - rp.footprint.y_min, 0.01)"
            >
              <div
                xmlns="http://www.w3.org/1999/xhtml"
                class="pointer-events-none overflow-hidden"
                :style="placementInnerStyle(rp)"
                v-html="rp.cleanSvg"
              />
            </foreignObject>
            <foreignObject
              v-if="showsMimeBadge(rp)"
              :x="rp.footprint.x_min"
              :y="rp.footprint.y_min"
              :width="Math.max(rp.footprint.x_max - rp.footprint.x_min, 0.01)"
              :height="Math.max(rp.footprint.y_max - rp.footprint.y_min, 0.01)"
            >
              <div
                xmlns="http://www.w3.org/1999/xhtml"
                class="pointer-events-none flex h-full w-full items-center justify-center bg-slate-100/50 font-mono text-[10px] uppercase tracking-wider text-slate-500"
              >
                {{ shortMime(rp.placement.source_mime || 'application/octet-stream') }}
              </div>
            </foreignObject>
            <rect
              :x="rp.footprint.x_min"
              :y="rp.footprint.y_min"
              :width="rp.footprint.x_max - rp.footprint.x_min"
              :height="rp.footprint.y_max - rp.footprint.y_min"
              fill="transparent"
              :stroke="rp.exceeds ? '#dc2626' : store.selectedPlacementId === rp.placement.id ? '#10b981' : '#475569'"
              :stroke-width="store.selectedPlacementId === rp.placement.id ? 2 : 1"
              :stroke-dasharray="store.selectedPlacementId === rp.placement.id ? undefined : '4 3'"
              vector-effect="non-scaling-stroke"
              style="cursor: grab;"
              @pointerdown="(e) => startMoveDrawing(e, rp.placement.id)"
              @dblclick="(e) => onPlacementDblClick(e, rp.placement.id)"
            />
            <g
              v-if="store.selectedPlacementId === rp.placement.id"
              :stroke="rp.exceeds ? '#dc2626' : '#10b981'"
              fill="#0f172a"
              stroke-width="1.5"
            >
              <template v-for="h in (['nw','n','ne','e','se','s','sw','w'] as const)" :key="h">
                <circle
                  :cx="h.includes('w') ? rp.footprint.x_min : h.includes('e') ? rp.footprint.x_max : (rp.footprint.x_min + rp.footprint.x_max) / 2"
                  :cy="h.includes('n') ? rp.footprint.y_min : h.includes('s') ? rp.footprint.y_max : (rp.footprint.y_min + rp.footprint.y_max) / 2"
                  r="5"
                  vector-effect="non-scaling-stroke"
                  :style="{ cursor: (h === 'n' || h === 's') ? 'ns-resize' : (h === 'e' || h === 'w') ? 'ew-resize' : (h === 'nw' || h === 'se') ? 'nwse-resize' : 'nesw-resize' }"
                  @pointerdown="(e) => startResize(h, e, rp.placement.id)"
                />
              </template>
            </g>
            <foreignObject
              v-if="store.selectedPlacementId === rp.placement.id"
              :x="rp.footprint.x_max - 240"
              :y="rp.footprint.y_min - 26"
              width="240"
              height="22"
            >
              <div
                xmlns="http://www.w3.org/1999/xhtml"
                class="flex items-center justify-end gap-1"
              >
                <select
                  v-if="placementPageCount(rp.placement) > 1"
                  class="max-w-[100px] truncate rounded border border-sky-600 bg-sky-950 px-1 py-0.5 text-[11px] text-sky-100 shadow focus:outline-none focus:ring-1 focus:ring-sky-400"
                  :value="placementCurrentPage(rp.placement)"
                  :title="t('upload.pageOf', {
                    current: placementCurrentPage(rp.placement) + 1,
                    total: placementPageCount(rp.placement),
                  })"
                  :disabled="store.loading"
                  @change="(e) => onPageChange(e, rp.placement.id)"
                  @pointerdown.stop
                  @click.stop
                  @dblclick.stop
                >
                  <option
                    v-for="n in placementPageCount(rp.placement)"
                    :key="n - 1"
                    :value="n - 1"
                  >
                    {{ t('upload.pageOf', { current: n, total: placementPageCount(rp.placement) }) }}
                  </option>
                </select>
                <select
                  v-if="rp.placement.variants.length > 1"
                  class="max-w-[120px] truncate rounded border border-slate-600 bg-slate-800 px-1 py-0.5 text-[11px] text-slate-100 shadow focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  :value="rp.placement.active_variant_id"
                  :title="t('variants.title')"
                  @change="(e) => onVariantChange(e, rp.placement.id)"
                  @pointerdown.stop
                  @click.stop
                  @dblclick.stop
                >
                  <option
                    v-for="variant in rp.placement.variants"
                    :key="variant.id"
                    :value="variant.id"
                  >
                    {{ variant.name }}
                  </option>
                </select>
                <button
                  type="button"
                  class="flex h-5 w-5 items-center justify-center rounded bg-red-600 text-[11px] font-bold text-white shadow hover:bg-red-500"
                  :title="t('sheet.removePlacement')"
                  @click.stop="store.removePlacement(rp.placement.id)"
                  @pointerdown.stop
                >
                  ✕
                </button>
              </div>
            </foreignObject>
          </template>
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

<style scoped>
:deep(foreignObject > div > svg) {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
