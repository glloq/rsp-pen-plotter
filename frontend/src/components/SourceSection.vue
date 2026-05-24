<script setup lang="ts">
import DOMPurify from 'dompurify'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import {
  downloadOriginalFile,
  getAlgorithms,
  getFonts,
  previewBitmap,
  type AlgorithmInfo,
  type PreviewResponse,
  type SegmentationMethod,
} from '../api/client'
import { useEditState } from '../composables/useEditState'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'
import FileSourceCard from './edit/source/FileSourceCard.vue'
import PrintModeCard from './edit/source/PrintModeCard.vue'
import PaletteCard from './edit/source/PaletteCard.vue'
import SegmentationCard from './edit/source/SegmentationCard.vue'
import MonochromeCard from './edit/source/MonochromeCard.vue'
import TypographyCard from './edit/source/TypographyCard.vue'
import { DEFAULT_MONO_MODE, getMonoMode } from '../data/monoModes'

const { t } = useI18n()
const store = useJobStore()
const ui = useUiStore()
const { presets, selectedPresetName } = storeToRefs(store)
const fileInput = ref<HTMLInputElement | null>(null)

const selectedFile = ref<File | null>(null)
const algorithms = ref<AlgorithmInfo[]>([])
const fonts = ref<string[]>([])
// SegmentationCard and TypographyCard own their own collapsed state
// now; we only keep the drag-over flag here because the parent owns
// the dropzone-vs-file-row layout decision (passed to FileSourceCard).
const dragOver = ref(false)

// Editable state for bitmap conversion. Grouped by concern so the
// template can show only the section the chosen segmentation method or
// algorithm needs. Factored into a default-builder so the
// placement-switch watcher (below) can reset the draft state cleanly.
type BitmapDraft = {
  segmentation_method: SegmentationMethod
  num_colors: number
  num_bands: number
  thresholds: number[]
  palette: string[]
  min_region_pixels: number
  merge_delta_e: number
  max_dimension_px: number
  drop_background: boolean
  background_luminance: number
  algorithm: string
  // Mono-mode preset writes directly into this dict (one place
  // instead of the scattered per-algo fields below). When non-empty
  // it takes precedence in buildAlgorithmOptions; left empty for
  // multi-colour mode so the legacy preset apply / rehydrate paths
  // keep working through the scattered fields.
  algorithm_options: Record<string, unknown>
  cell_size_px: number
  density: number
  dot_radius_px: number
  seed: number
  crosshatch_angle_deg: number
  crosshatch_spacing_px: number
  crosshatch_crossed: boolean
  contours_spacing_px: number
  contours_max_rings: number
  edges_stroke_width: number
  spiral_spacing_px: number
  spiral_samples_per_turn: number
  scanlines_spacing_px: number
  scanlines_wave_amp_px: number
  scanlines_wave_period_px: number
}

function defaultBitmap(): BitmapDraft {
  return {
    segmentation_method: 'kmeans',
    num_colors: 4,
    num_bands: 4,
    thresholds: [0.33, 0.66],
    // Specific colours the user pins via the top-level "Colours" block.
    // When non-empty, the segmentation switches to ``fixed_palette`` and
    // snaps the image to exactly these colours; when empty, kmeans picks
    // ``num_colors`` colours automatically.
    palette: [],
    min_region_pixels: 0,
    merge_delta_e: 0,
    max_dimension_px: 800,
    drop_background: true,
    background_luminance: 0.92,
    algorithm: 'direct',
    algorithm_options: {},
    cell_size_px: 6,
    density: 0.02,
    dot_radius_px: 0.6,
    seed: 0,
    crosshatch_angle_deg: 45,
    crosshatch_spacing_px: 4,
    crosshatch_crossed: false,
    contours_spacing_px: 4,
    contours_max_rings: 20,
    edges_stroke_width: 0.8,
    spiral_spacing_px: 4,
    spiral_samples_per_turn: 64,
    scanlines_spacing_px: 4,
    scanlines_wave_amp_px: 0,
    scanlines_wave_period_px: 12,
  }
}

const bitmap = ref<BitmapDraft>(defaultBitmap())

type TypographyDraft = {
  font: string
  font_size_mm: number
  line_spacing: number
  alignment: 'left' | 'center' | 'right'
  stroke_width_mm: number
  margin_mm: number
  page_width_mm: number
  page_height_mm: number
}

function defaultTypography(): TypographyDraft {
  return {
    font: 'futural',
    font_size_mm: 4.0,
    line_spacing: 1.5,
    alignment: 'left',
    stroke_width_mm: 0.3,
    margin_mm: 15.0,
    page_width_mm: 210.0,
    page_height_mm: 297.0,
  }
}

const typo = ref<TypographyDraft>(defaultTypography())

// Restore the draft form to defaults, then overlay any options the
// placement was actually uploaded with so re-opening the modal on an
// already-converted file shows the parameters that produced it.
function rehydrateDraftFromPlacement(): void {
  bitmap.value = defaultBitmap()
  typo.value = defaultTypography()
  paletteFollowsPens.value = true
  const opts = store.selectedPlacement?.last_options
  if (!opts || typeof opts !== 'object') return
  const target = bitmap.value as Record<string, unknown>
  for (const key of Object.keys(target)) {
    if (key in opts) target[key] = (opts as Record<string, unknown>)[key]
  }
  const algoOpts = (opts as Record<string, unknown>).algorithm_options as
    | Record<string, unknown>
    | undefined
  if (algoOpts) {
    for (const key of ['cell_size_px', 'density', 'dot_radius_px', 'seed']) {
      if (key in algoOpts) target[key] = algoOpts[key]
    }
  }
  const segOpts = (opts as Record<string, unknown>).segmentation_options as
    | Record<string, unknown>
    | undefined
  if (segOpts && 'palette' in segOpts && Array.isArray(segOpts.palette)) {
    bitmap.value.palette = [...(segOpts.palette as string[])]
    // If the stored palette doesn't match the currently installed pens,
    // the upload used a manual palette — surface that as the editor mode.
    const installed = (store.selectedProfile?.pens ?? [])
      .filter((p) => p.installed && p.color)
      .map((p) => p.color)
    const sameAsPens
      = bitmap.value.palette.length === installed.length
      && bitmap.value.palette.every((c, i) => c === installed[i])
    paletteFollowsPens.value = sameAsPens
  }
  const typoTarget = typo.value as Record<string, unknown>
  for (const key of Object.keys(typoTarget)) {
    if (key in opts) typoTarget[key] = (opts as Record<string, unknown>)[key]
  }
}

const IMAGE_EXT = ['png', 'jpg', 'jpeg', 'tiff', 'webp', 'heic']
const TYPOGRAPHY_EXT = ['txt', 'md']
const DOCUMENT_EXT = ['pdf', 'svg', 'eps', 'ps', 'ai', 'docx', 'odt', 'rtf', 'html']
const ACCEPT = '.svg,.png,.jpg,.jpeg,.tiff,.webp,.heic,.pdf,.dxf,.eps,.ps,.ai,.txt,.md,.html,.docx,.odt,.rtf'

// File kind is derived from the selectedFile when present, otherwise
// from the placement's source_file metadata. Without this fallback,
// placements created via the library (createPlacementFromLibrary
// doesn't set last_file) would land on the modal with kind='none' and
// every conversion section hidden — the operator would only see the
// dropzone, even though a file is clearly attached.
const sourceName = computed<string>(() =>
  selectedFile.value?.name ?? store.selectedPlacement?.source_file ?? '',
)

const kind = computed<'bitmap' | 'typography' | 'document' | 'none'>(() => {
  const ext = sourceName.value.split('.').pop()?.toLowerCase() ?? ''
  if (IMAGE_EXT.includes(ext)) return 'bitmap'
  if (TYPOGRAPHY_EXT.includes(ext)) return 'typography'
  if (DOCUMENT_EXT.includes(ext)) return 'document'
  return 'none'
})

const showsBitmapForm = computed(() => kind.value === 'bitmap' || kind.value === 'document')

// Has a file attached either in memory (selectedFile) or via the
// placement's library entry. Drives whether the conversion settings
// are shown at all — without this, the modal would fall back to the
// dropzone for any placement that came from the library or survived
// a page refresh (File handles can't be persisted to localStorage).
const hasSource = computed<boolean>(
  () => Boolean(selectedFile.value || store.selectedPlacement?.source_file),
)

// Local thumbnail for raster images: instant preview before paying the
// round-trip + vectorisation cost. ObjectURL is revoked on file change.
const previewUrl = ref<string | null>(null)
function refreshPreview(): void {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = null
  }
  if (selectedFile.value && kind.value === 'bitmap') {
    previewUrl.value = URL.createObjectURL(selectedFile.value)
  }
}
watch(selectedFile, refreshPreview)
onBeforeUnmount(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})

// Plain-text inline preview for txt / md so the user knows what they're about
// to convert. Capped at a few KB so large files don't hang the UI.
const textPreview = ref<string>('')
watch(selectedFile, async (file) => {
  textPreview.value = ''
  if (file && kind.value === 'typography') {
    try {
      const blob = file.slice(0, 4096)
      textPreview.value = await blob.text()
    } catch {
      textPreview.value = ''
    }
  }
})

// (The per-algorithm card grid + ``algorithmsByKind`` helper that used to
//  live here moved into LayerCard when render became a per-layer choice.)

// Live preview: debounced /preview round-trip on parameter changes.
const previewResult = ref<PreviewResponse | null>(null)
const previewLoading = ref(false)
const previewError = ref<string | null>(null)
let previewController: AbortController | null = null
let previewTimer: ReturnType<typeof setTimeout> | null = null

const previewSvg = computed(() => {
  if (!previewResult.value) return ''
  return DOMPurify.sanitize(previewResult.value.svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
  })
})

// schedulePreview runs the live /preview on a debounce so dragging
// a slider doesn't fire N round-trips. ``immediate`` skips the
// debounce — used by the detail-tier picker since a tier click is
// already a discrete commitment by the operator (one click, not a
// stream), and the operator expects instant feedback.
function schedulePreview(immediate = false): void {
  if (!selectedFile.value || kind.value !== 'bitmap') return
  if (previewTimer) clearTimeout(previewTimer)
  if (immediate) {
    void runPreview()
  } else {
    previewTimer = setTimeout(runPreview, 500)
  }
}

async function runPreview(): Promise<void> {
  if (!selectedFile.value || kind.value !== 'bitmap') return
  if (previewController) previewController.abort()
  const controller = new AbortController()
  previewController = controller
  previewLoading.value = true
  previewError.value = null
  try {
    const result = await previewBitmap(
      selectedFile.value,
      bitmap.value.algorithm,
      buildOptions(),
      controller.signal,
    )
    if (controller.signal.aborted) return
    previewResult.value = result
  } catch (err) {
    if (controller.signal.aborted) return
    previewError.value = (err as Error).message || t('upload.failed')
  } finally {
    if (previewController === controller) {
      previewController = null
      previewLoading.value = false
    }
  }
}

// Cancellation + retry exposed to the preview pane (via useEditState).
// Cancel aborts the in-flight controller AND clears any pending debounce,
// so a long /preview round-trip doesn't keep eating CPU after the user
// gives up on it.
function cancelPreview(): void {
  if (previewTimer) {
    clearTimeout(previewTimer)
    previewTimer = null
  }
  if (previewController) {
    previewController.abort()
    previewController = null
  }
  previewLoading.value = false
}

function retryPreview(): void {
  previewError.value = null
  runPreview()
}

// Detail-tier changes get their own watcher with no debounce — the
// operator clicks a tier and expects immediate visual feedback (the
// preview pane footer's path-count diagnostic in particular). The
// debounced watcher below still handles the more granular slider /
// numeric inputs.
watch(
  () => bitmap.value.max_dimension_px,
  () => {
    if (selectedFile.value && kind.value === 'bitmap') schedulePreview(true)
  },
)

watch(
  [
    selectedFile,
    () => bitmap.value.algorithm,
    () => bitmap.value.algorithm_options,
    () => bitmap.value.segmentation_method,
    () => bitmap.value.num_colors,
    () => bitmap.value.num_bands,
    () => bitmap.value.thresholds,
    () => bitmap.value.palette,
    () => bitmap.value.drop_background,
    () => bitmap.value.background_luminance,
    () => bitmap.value.min_region_pixels,
    () => bitmap.value.merge_delta_e,
    () => bitmap.value.cell_size_px,
    () => bitmap.value.density,
    () => bitmap.value.dot_radius_px,
    () => bitmap.value.seed,
    () => bitmap.value.crosshatch_angle_deg,
    () => bitmap.value.crosshatch_spacing_px,
    () => bitmap.value.crosshatch_crossed,
    () => bitmap.value.contours_spacing_px,
    () => bitmap.value.contours_max_rings,
    () => bitmap.value.edges_stroke_width,
    () => bitmap.value.spiral_spacing_px,
    () => bitmap.value.spiral_samples_per_turn,
    () => bitmap.value.scanlines_spacing_px,
    () => bitmap.value.scanlines_wave_amp_px,
    () => bitmap.value.scanlines_wave_period_px,
  ],
  () => {
    if (selectedFile.value && kind.value === 'bitmap') {
      schedulePreview()
    } else {
      previewResult.value = null
      previewError.value = null
    }
  },
  { deep: true },
)

onBeforeUnmount(() => {
  if (previewTimer) clearTimeout(previewTimer)
  if (previewController) previewController.abort()
})

// Try to restore the placement's source as a File object. Two paths:
//   1. ``store.lastFile`` is set when the placement was created via
//      drop-anywhere or the upload form (the bytes live in memory).
//   2. Library placements + post-refresh placements have no in-memory
//      file — but they hold a ``library_file_id`` pointing at the
//      backend's persistent store; ``/files/{id}/original`` streams the
//      bytes back so we can rehydrate the File on demand.
// Without this, the modal could only show the dropzone for any
// placement coming from the library or surviving a page refresh.
async function ensureSelectedFile(): Promise<void> {
  if (selectedFile.value) return
  if (store.lastFile) {
    selectedFile.value = store.lastFile
    return
  }
  const placement = store.selectedPlacement
  if (!placement?.library_file_id || !placement.source_file) return
  try {
    selectedFile.value = await downloadOriginalFile(
      placement.library_file_id,
      placement.source_file,
      placement.source_mime || 'application/octet-stream',
    )
  } catch {
    // Bytes evicted / network error — UI stays usable in read-only
    // mode (settings visible, /preview disabled until re-attach via
    // the header menu).
  }
}

onMounted(async () => {
  // Promise.all so the algos + fonts metadata fetch doesn't block the
  // (potentially much larger) original-file download — but both run.
  await Promise.all([
    ensureSelectedFile(),
    (async () => {
      try {
        ;[algorithms.value, fonts.value] = await Promise.all([getAlgorithms(), getFonts()])
      } catch {
        // Defaults still work if metadata fetch fails.
      }
    })(),
  ])
})

// Switching placements (via FilesPane) refreshes the local file ref AND
// the draft form so the modal mirrors the newly-selected placement's
// source. Without the rehydrate, the previous placement's bitmap /
// typography knobs would silently feed into the next /preview call and
// next upload — see audit findings #2 and #3.
watch(
  () => store.selectedPlacementId,
  async () => {
    // Clear the local File first so ensureSelectedFile() doesn't
    // surface the previous placement's bytes while the new one's
    // fetch is in flight.
    selectedFile.value = null
    rehydrateDraftFromPlacement()
    // EditModal calls resetEditState() on placement switch, which
    // wipes the goToPage / cancel / retry callbacks back to no-ops.
    // Re-register them so the preview pane's controls keep working
    // after the operator hops between placements without closing the
    // modal.
    edit.setGoToPage(goToPage)
    edit.setPreviewCallbacks({ cancel: cancelPreview, retry: retryPreview })
    await ensureSelectedFile()
  },
)

watch(selectedPresetName, (name) => {
  const preset = presets.value.find((p) => p.name === name)
  if (!preset) return
  const opts = preset.options as Record<string, unknown>
  const target = bitmap.value as Record<string, unknown>
  for (const key of Object.keys(target)) {
    if (key in opts) target[key] = opts[key]
  }
  const algoOpts = (opts.algorithm_options as Record<string, unknown>) ?? {}
  for (const key of ['cell_size_px', 'density', 'dot_radius_px', 'seed']) {
    if (key in algoOpts) target[key] = algoOpts[key]
  }
})

function onFileChange(event: Event): void {
  const target = event.target as HTMLInputElement
  selectedFile.value = target.files?.[0] ?? null
  target.value = ''
}

function buildSegmentationOptions(): Record<string, unknown> {
  const b = bitmap.value
  if (b.segmentation_method === 'luminance_bands') return { num_bands: b.num_bands }
  if (b.segmentation_method === 'thresholds') return { levels: b.thresholds }
  if (b.segmentation_method === 'fixed_palette') return { palette: b.palette }
  return {}
}

function buildAlgorithmOptions(): Record<string, unknown> {
  const b = bitmap.value
  // Mono modes write the full options dict into ``algorithm_options``
  // directly — prefer that when populated so the recipe survives
  // intact instead of being filtered through the per-algo scattered
  // fields (which the multicolor path still uses through presets).
  if (Object.keys(b.algorithm_options).length > 0) {
    return { ...b.algorithm_options }
  }
  switch (b.algorithm) {
    case 'halftone':
      return { cell_size_px: b.cell_size_px }
    case 'stippling':
      return { density: b.density, dot_radius_px: b.dot_radius_px, seed: b.seed }
    case 'crosshatch':
      return {
        angle_deg: b.crosshatch_angle_deg,
        spacing_px: b.crosshatch_spacing_px,
        crossed: b.crosshatch_crossed,
      }
    case 'contours':
      return { spacing_px: b.contours_spacing_px, max_rings: b.contours_max_rings }
    case 'edges':
      return { stroke_width: b.edges_stroke_width }
    case 'spiral':
      return { spacing_px: b.spiral_spacing_px, samples_per_turn: b.spiral_samples_per_turn }
    case 'scanlines':
      return {
        spacing_px: b.scanlines_spacing_px,
        wave_amp_px: b.scanlines_wave_amp_px,
        wave_period_px: b.scanlines_wave_period_px,
      }
    case 'tsp':
      return { density: b.density, seed: b.seed }
    default:
      return {}
  }
}

function buildOptions(): Record<string, unknown> | undefined {
  if (showsBitmapForm.value) {
    const b = bitmap.value
    return {
      algorithm: b.algorithm,
      num_colors: b.num_colors,
      max_dimension_px: b.max_dimension_px,
      drop_background: b.drop_background,
      background_luminance: b.background_luminance,
      segmentation_method: b.segmentation_method,
      segmentation_options: buildSegmentationOptions(),
      min_region_pixels: b.min_region_pixels,
      merge_delta_e: b.merge_delta_e,
      algorithm_options: buildAlgorithmOptions(),
    }
  }
  if (kind.value === 'typography') {
    return { ...typo.value }
  }
  return undefined
}

// Count layers in the active placement that carry a multi-pass stack
// — re-uploading the file would discard those configurations along
// with the layer ids, so we surface a banner + confirmation before the
// operator loses work they spent time tuning.
const multiPassLayerCount = computed(() =>
  Object.values(store.layerAlgorithms).filter(
    (spec) => Array.isArray((spec as { passes?: unknown[] }).passes) && (spec as { passes: unknown[] }).passes.length > 0,
  ).length,
)

async function uploadSelected(): Promise<void> {
  if (!selectedFile.value) return
  if (multiPassLayerCount.value > 0) {
    const ok = window.confirm(
      t('passes.reuploadWarning', { count: multiPassLayerCount.value }),
    )
    if (!ok) return
  }
  const wasMono = printMode.value === 'monochrome'
  await store.upload(selectedFile.value, buildOptions())
  // Drop the stale draft preview now that the placement carries its own
  // committed SVG. Otherwise the live preview would shadow the
  // committed SVG in EditPreviewPane.
  previewResult.value = null
  previewError.value = null
  // Mono mode: every produced band-layer plots with the same pen, so
  // pre-assign them to the slot the operator picked in MonochromeCard
  // (saves a "All to one pen" click + spares the manual swap warning).
  // Per-band algorithm overrides from the active mono mode are also
  // installed here — store.applyLayerAlgorithm debounces a single
  // /rerender once all calls are queued, so we don't fan out N
  // round-trips for an N-band image.
  if (wasMono && store.layers.length) {
    const mode = getMonoMode(monoModeId.value)
    const total = store.layers.length
    for (let i = 0; i < total; i++) {
      const layer = store.layers[i]!
      if (layer.target_pen_slot !== monoPenSlot.value) {
        store.updateLayer(layer.layer_id, { target_pen_slot: monoPenSlot.value })
      }
      const override = mode?.algoForBand(i, total)
      if (override) {
        await store.applyLayerAlgorithm(
          layer.layer_id,
          override.algorithm,
          override.algorithm_options,
        )
      }
    }
  }
  if (store.layers.length) ui.canvasTab = 'sheet'
}

function clearAll(): void {
  selectedFile.value = null
  store.clearJob()
}

// Threshold and palette editing helpers used to live here; they're now
// in the sub-components (SegmentationCard / PaletteCard) that own the
// matching UI, so SourceSection stays as the orchestrator.

const pageCount = computed(() => Number(store.uploadMetadata.page_count ?? 0))
const currentPage = computed(() => Number(store.uploadMetadata.page ?? 0))

async function goToPage(page: number): Promise<void> {
  if (page < 0 || page >= pageCount.value || page === currentPage.value) return
  await store.changePage(page)
  if (store.layers.length) ui.canvasTab = 'sheet'
}

function openPicker(): void {
  fileInput.value?.click()
}

// ============================== PRINT MODE (SVG OUTPUT) ==============================
// "Single colour" mode rewrites the SVG output to a single layer drawn
// Mono splits the image into either luminance bands (shaded modes)
// OR a single binarisation threshold (line-drawing / TSP / spiral
// modes). Multi-colour uses kmeans or a manual palette. The mono
// modes are tagged by an explicit ref so we can tell the two
// "thresholds"-using paths apart (mono binary modes vs. a multicolor
// thresholds segmentation, which is rare but possible).
const printMode = computed<'multicolor' | 'monochrome'>(() => {
  // Any of the registered mono mode segmentation methods → mono
  if (bitmap.value.segmentation_method === 'luminance_bands') return 'monochrome'
  // Binary mono modes use ``thresholds`` with a single split. We
  // detect "this came from a mono mode" by checking the monoModeId
  // ref — switching the print mode toggle is the only way it gets set.
  const mode = getMonoMode(monoModeId.value)
  if (
    mode
    && mode.segmentation_method === 'thresholds'
    && bitmap.value.segmentation_method === 'thresholds'
    && bitmap.value.thresholds.length === 1
  ) {
    return 'monochrome'
  }
  return 'multicolor'
})

// Mono ink slot — which pen the operator wants to use for the
// monochrome plot. Defaults to slot 0; the post-upload step assigns
// every produced layer to this slot so the entire drawing prints in
// one ink without manual reassignment.
const monoPenSlot = ref(0)
function setMonoPenSlot(value: number): void {
  monoPenSlot.value = value
}

// Active monochrome mode (Pencil / Halftone / Stippling / Engraving /
// Contours / Outline / TSP / Spiral). The mode owns the segmentation
// + algorithm recipe; per-band overrides are applied via /rerender
// once the upload has produced layers. See data/monoModes.ts.
const monoModeId = ref<string>(DEFAULT_MONO_MODE)
function setMonoModeId(value: string): void {
  monoModeId.value = value
}

function setPrintMode(mode: 'multicolor' | 'monochrome'): void {
  if (mode === 'monochrome') {
    // Delegate to the active mono mode's recipe. The default mode
    // (Pencil) ships sensible bands + algorithm + drop_background
    // settings; switching modes within the card re-applies via
    // MonochromeCard.selectMode.
    const target = getMonoMode(monoModeId.value)
    if (target) {
      bitmap.value.segmentation_method = target.segmentation_method
      bitmap.value.drop_background = target.drop_background
      bitmap.value.background_luminance = target.background_luminance
      bitmap.value.algorithm = target.default_algorithm
      bitmap.value.algorithm_options = { ...target.default_algorithm_options }
      if (target.segmentation_method === 'luminance_bands') {
        if (bitmap.value.num_bands < 2 || bitmap.value.num_bands > 6) {
          bitmap.value.num_bands = target.default_bands
        }
      } else {
        bitmap.value.thresholds = [target.default_threshold]
      }
    }
    paletteFollowsPens.value = false
  } else {
    // Back to multi-colour: restore the default kmeans / 4-colour
    // segmentation. If the user had pen-following enabled before
    // monochrome, the palette watch will repopulate from installed pens.
    bitmap.value.segmentation_method = 'kmeans'
    bitmap.value.num_colors = 4
    bitmap.value.background_luminance = 0.92
    // Clear the mono mode's algorithm_options dict so the multicolor
    // path falls back to the per-algo scattered fields and respects
    // any preset that gets applied afterwards.
    bitmap.value.algorithm_options = {}
    if (
      bitmap.value.algorithm !== 'direct'
      && bitmap.value.algorithm !== 'halftone'
      && bitmap.value.algorithm !== 'stippling'
    ) {
      bitmap.value.algorithm = 'direct'
    }
    paletteFollowsPens.value = true
  }
}

// ============================== PEN-DRIVEN PALETTE ==============================
// When the active machine profile has installed pens with hex colours,
// the editor follows them by default: palette = installed pen colours,
// segmentation_method = fixed_palette. Toggling "manual" frees the
// palette and the method picker. The manual-swap badge counts colours
// beyond the available pen slots (those will trigger pause-for-swap).
const paletteFollowsPens = ref(true)

const installedPenColors = computed<string[]>(() => {
  const pens = store.selectedProfile?.pens ?? []
  return pens.filter((p) => p.installed && p.color).map((p) => p.color)
})

const penSlotCount = computed(() => store.selectedProfile?.pen_slot_count ?? 0)

watch(
  [paletteFollowsPens, installedPenColors],
  ([follows, colors]) => {
    if (follows && colors.length) {
      bitmap.value.palette = [...colors]
      bitmap.value.segmentation_method = 'fixed_palette'
    }
  },
  { immediate: true },
)

const manualSwapCount = computed(() =>
  Math.max(0, bitmap.value.palette.length - penSlotCount.value),
)

// PaletteCard owns the "switch to manual + seed from pens" logic now;
// the parent only needs to mirror the boolean back into local state.
function setPaletteFollowsPens(value: boolean): void {
  paletteFollowsPens.value = value
}

// Mirror the preview-related local state into the shared edit-state
// composable so EditPreviewPane (rendered as a sibling on the left side
// of the modal) sees the same values. The composable holds its own refs
// — we sync into them with watchEffect rather than rewiring SourceSection
// to read/write the composable refs directly.
const edit = useEditState()
watch(selectedFile, (v) => { edit.selectedFile.value = v }, { immediate: true })
watch(previewUrl, (v) => { edit.previewUrl.value = v }, { immediate: true })
watch(textPreview, (v) => { edit.textPreview.value = v }, { immediate: true })
watch(previewSvg, (v) => { edit.previewSvg.value = v }, { immediate: true })
watch(previewLoading, (v) => { edit.previewLoading.value = v }, { immediate: true })
watch(previewError, (v) => { edit.previewError.value = v }, { immediate: true })
watch(previewResult, (v) => { edit.previewResult.value = v }, { immediate: true })
watch(kind, (v) => { edit.kind.value = v }, { immediate: true })
watch(() => Number(store.uploadMetadata.page_count ?? 0), (v) => { edit.pageCount.value = v }, { immediate: true })
watch(() => Number(store.uploadMetadata.page ?? 0), (v) => { edit.currentPage.value = v }, { immediate: true })
edit.setGoToPage(goToPage)
edit.setPreviewCallbacks({ cancel: cancelPreview, retry: retryPreview })

// Surfaced to EditModal so the header's file-action dropdown can
// trigger the hidden <input type=file> and the clear flow without
// reaching into SourceSection internals.
defineExpose({ openPicker, clearAll })
</script>

<template>
  <!-- Orchestrator. State (drafts, watchers, /preview cancel/retry,
       upload guard) lives in script setup; the visual sections are
       implemented in dedicated cards under ./edit/source/. The file
       row used to live here too but the modal opens with a file
       already attached 100% of the time (Edit button on a library
       entry), so it was screen-real-estate for nothing. File actions
       (change / clear) live in the modal header now — see
       EditFileActions.vue. The dropzone below is only rendered for
       the rare edge case of an empty placement awaiting a first
       file. -->
  <section class="space-y-3">
    <input
      ref="fileInput"
      type="file"
      class="hidden"
      :accept="ACCEPT"
      @change="onFileChange"
    />

    <!-- Edge case: truly empty placement (no file + no library entry).
         Show the dropzone so the operator has somewhere to drop a
         file. Library/persisted placements take the settings branch
         below; ensureSelectedFile() rehydrates their File handle in
         the background. -->
    <FileSourceCard
      v-if="!hasSource"
      :selected-file="null"
      :kind="kind"
      :has-job="Boolean(store.job)"
      v-model:drag-over="dragOver"
      @pick="openPicker"
      @clear="clearAll"
      @drop="(file) => (selectedFile = file)"
    />

    <!-- Bitmap / document conversion settings: print mode first (it
         drives whether palette + segmentation render at all), then
         colours, then segmentation details. Per-layer algorithm
         choice lives in the Layers tab — surface a hint so the
         operator knows where to go. -->
    <template v-if="hasSource && showsBitmapForm">
      <PrintModeCard :mode="printMode" @update:mode="setPrintMode" />

      <template v-if="printMode === 'multicolor'">
        <PaletteCard
          :bitmap="bitmap"
          :palette-follows-pens="paletteFollowsPens"
          :installed-pen-colors="installedPenColors"
          :pen-slot-count="penSlotCount"
          :manual-swap-count="manualSwapCount"
          @update:palette-follows-pens="setPaletteFollowsPens"
        />
        <SegmentationCard :bitmap="bitmap" :is-document="kind === 'document'" />
      </template>

      <MonochromeCard
        v-else
        :bitmap="bitmap"
        :mono-pen-slot="monoPenSlot"
        :mono-mode-id="monoModeId"
        @update:mono-pen-slot="setMonoPenSlot"
        @update:mono-mode-id="setMonoModeId"
      />

      <p
        v-if="store.layers.length"
        class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1.5 text-[11px] text-slate-400"
      >
        {{ t('source.perLayerHint') }}
      </p>
    </template>

    <TypographyCard
      v-if="hasSource && kind === 'typography'"
      :typo="typo"
      :fonts="fonts"
    />

    <p
      v-if="hasSource && previewError"
      class="rounded border border-red-700 bg-red-950/40 px-2 py-1 text-[11px] text-red-300"
    >
      {{ previewError }}
    </p>

    <p
      v-if="hasSource && multiPassLayerCount > 0 && store.job"
      class="rounded border border-amber-700 bg-amber-950/40 px-2 py-1.5 text-[11px] text-amber-200"
    >
      ⚠ {{ t('passes.reuploadHint', { count: multiPassLayerCount }) }}
    </p>

    <button
      v-if="hasSource"
      type="button"
      class="w-full rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
      :disabled="store.loading || !selectedFile"
      :title="!selectedFile ? t('source.waitingForFile') : ''"
      @click="uploadSelected"
    >
      {{ !selectedFile
        ? t('source.waitingForFile')
        : store.loading
          ? t('upload.converting')
          : store.job
            ? t('source.applyChanges')
            : t('upload.choose') }}
    </button>

    <p v-if="store.error && store.errorScope === 'upload'" class="rounded border border-red-700 bg-red-950/40 px-2 py-1 text-xs text-red-300">
      {{ store.error }}
    </p>

    <ul
      v-if="store.uploadWarnings.length"
      class="rounded border border-amber-700 bg-amber-950/40 px-2 py-1.5 text-xs text-amber-200 space-y-0.5"
    >
      <li v-for="(warning, i) in store.uploadWarnings" :key="i">⚠ {{ warning }}</li>
    </ul>
  </section>
</template>
