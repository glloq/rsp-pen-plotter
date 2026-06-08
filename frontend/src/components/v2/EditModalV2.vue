<script setup lang="ts">
// Modal V2 — beginner editor (assisted mode).
//
// Single-screen, zero-mandatory-step flow (roadmap C.2 / audit #7 §3,
// simplified per operator feedback "encore plus simple, preview rapide
// adaptée, un minimum d'interactions"). Lives **in parallel** with the
// expert EditModal.vue and is gated by the assisted UX mode.
//
// The whole decision (source kind, palette, algorithm, layers) is
// resolved automatically from the placement + a single "intent" choice
// (Rapide / Équilibré / Qualité, défaut Équilibré). The operator sees a
// large LIVE preview of the real plotted result — re-rendered through
// the same ``/rerender`` endpoint "Generate" uses — and commits in one
// click. Power-user details (algorithme, couches, raisonnement) move to
// the full editor, reachable via "Ouvrir l'éditeur complet".

import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { libraryFilePreviewImageUrl, type LayerInfo } from '../../api/client'
import { useKeyboardShortcuts } from '../../composables/useKeyboardShortcuts'
import { resolveAlgorithmPolicy } from '../../domain/policy/client'
import type { Goal, PaletteMode, PolicyDecision, PolicyPass, SourceKind } from '../../domain/policy/schemas'
import { nearestPen, type PenSlotLike } from '../../lib/penMatching'
import { useAvailableColorsStore } from '../../stores/availableColors'
import { usePaletteSourceStore } from '../../stores/paletteSource'
import { useUiStore } from '../../stores/ui'
import { useUiModeStore } from '../../stores/uiMode'
import { useJobStore } from '../../stores/job'
import { usePlotterStore } from '../../stores/plotter'
import { useBitmapDraft } from '../../composables/useBitmapDraft'
import { useFileManager } from '../../composables/useFileManager'
import AssistantModeToggle from '../AssistantModeToggle.vue'
import LayersSection from '../LayersSection.vue'
import EditTabs, { type EditTabId } from '../edit/EditTabs.vue'
import ImageTab from '../edit/tabs/ImageTab.vue'
import SvgTab from '../edit/tabs/SvgTab.vue'
import StyleTab from '../edit/tabs/StyleTab.vue'
import TextTab from '../edit/tabs/TextTab.vue'
import PresetPanel from './PresetPanel.vue'
import SheetPicker from './SheetPicker.vue'
import { BEGINNER_STYLES, type CustomStyleSelection } from './beginnerStyles'
import StyleCustomizer from './StyleCustomizer.vue'
import EditPreviewPane from './EditPreviewPane.vue'

const ONBOARDING_KEY = 'omniplot.onboarding.editorV2.v1'
const PREAMBLE_KEY = 'omniplot.preamble.editorV2.v1'
const TOUR_STEPS = 3

const props = defineProps<{
  initialSourceKind?: SourceKind
  initialPaletteMode?: PaletteMode
  availableColorsCount?: number
  imageMegapixels?: number | null
  isMonoPenMachine?: boolean
  /** Layers from the currently-selected placement. Empty when the
   *  operator hasn't picked one yet. */
  layers?: readonly LayerInfo[]
  /** Source file name from the active placement — surfaced as a caption
   *  under the preview. */
  sourceName?: string
  /** Sanitized SVG preview from the active placement; shown immediately
   *  as the placeholder while the adapted render is computed. */
  previewSvg?: string
  /** Test/embed escape hatch: when true, the first-run welcome tour is
   *  never shown (regardless of localStorage state). Production code
   *  leaves this unset so the tour appears once per operator. */
  skipOnboarding?: boolean
}>()

const emit = defineEmits<{
  (e: 'cancel'): void
  (e: 'confirm', decision: PolicyDecision): void
}>()

const { t } = useI18n()
const ui = useUiStore()
const uiMode = useUiModeStore()
const job = useJobStore()
const paletteSource = usePaletteSourceStore()
const availableColors = useAvailableColorsStore()
const plotter = usePlotterStore()

const sourceKind = ref<SourceKind>(props.initialSourceKind ?? 'bitmap_photo')
// Initial palette mode: prop wins, else mirror the global palette source
// so the modal opens consistent with whatever the operator has already
// configured in the Plotter drawer (``pens`` → ``machine_only``, anything
// else → ``free``).
const paletteMode = ref<PaletteMode>(
  props.initialPaletteMode ?? (paletteSource.source === 'pens' ? 'machine_only' : 'free'),
)

// Équilibré is the sensible default for a beginner: one good-enough
// result with no questions asked. They can nudge faster/finer with a
// single click if they want.
const goal = ref<Goal>('balanced')

const decision = ref<PolicyDecision | null>(null)
const resolving = ref(false)
const resolveError = ref<string | null>(null)

// Live preview state. ``renderedSvg`` holds the adapted result; until
// it lands we fall back to the original placement SVG so the pane is
// never blank.
const renderedSvg = ref<string | null>(null)
const previewLoading = ref(false)
const previewError = ref(false)
let previewController: AbortController | null = null

const INTENTS: readonly Goal[] = ['fast', 'balanced', 'quality'] as const

// True when there's an active placement to apply the decision to.
const hasPlacement = computed(() => Boolean(props.previewSvg || props.sourceName))

// ============================ CUSTOM STYLE STACK =======================
// Optional escape hatch from the resolver's automatic algorithm pick:
// the StyleCustomizer subcomponent owns the picker UI, this parent
// owns the selection state + the PolicyPass projection that drives
// /rerender and Generate. Empty stack = resolver wins (default
// experience). Non-empty stack = the modal overrides decision.default_*.
const customStyles = ref<CustomStyleSelection[]>([])
const customStylesActive = computed<boolean>(() => customStyles.value.length > 0)

// Custom styles really only make sense for bitmap sources — vectors
// and PDFs route through dedicated pipelines (vector_passthrough,
// pdf_text_*) that ignore raster algorithms. We hide the panel
// outright for non-bitmap kinds so the affordance never misleads.
const canCustomizeStyles = computed<boolean>(
  () => sourceKind.value === 'bitmap_photo' || sourceKind.value === 'bitmap_illustration',
)

// Build the PolicyPass[] the user's stack expresses. The full algorithm
// option set keeps its registry defaults (see printRegistry.ts) and we
// only override the primary knob's key — that's the entire contract of
// the "1 simple knob per style" decision.
const customPasses = computed<PolicyPass[]>(() =>
  customStyles.value.map((sel) => {
    const style = BEGINNER_STYLES.find((s) => s.id === sel.id)!
    return {
      algorithm: sel.id,
      algorithm_options: { [style.primaryKnob.optionKey]: sel.knobValue },
    }
  }),
)

/**
 * Resolve the algorithm for the current intent, then render the real
 * result across every layer. Aborts any in-flight preview so rapid
 * intent toggles don't pile up stale renders. Errors degrade
 * gracefully — the original SVG keeps showing and Generate stays
 * usable as long as we have a decision.
 */
async function resolveAndPreview(): Promise<void> {
  if (!hasPlacement.value) return
  previewController?.abort()
  const controller = new AbortController()
  previewController = controller

  resolving.value = true
  resolveError.value = null
  previewError.value = false
  try {
    const d = await resolveAlgorithmPolicy({
      source_kind: sourceKind.value,
      goal: goal.value,
      palette_mode: paletteMode.value,
      available_colors_count: props.availableColorsCount ?? 1,
      image_megapixels: props.imageMegapixels ?? null,
      layer_count_estimate: props.layers?.length || 1,
      is_mono_pen_machine: Boolean(props.isMonoPenMachine),
    })
    if (controller.signal.aborted) return
    decision.value = d
  } catch (err) {
    resolveError.value = (err as Error).message
    resolving.value = false
    return
  }
  resolving.value = false

  // Now render the adapted result. Keep the previous render visible
  // until the new one lands to avoid a flash back to the original.
  await renderAdaptedPreview(controller)
}

/**
 * Render-only path used both by ``resolveAndPreview`` (after the policy
 * lands) and by ``customStyles`` mutations (where the resolver result
 * hasn't changed but the operator's stack has). Picks between custom
 * passes, resolver multi-pass, and single-algorithm depending on what's
 * active. Errors leave the previous render in place.
 */
async function renderAdaptedPreview(controller: AbortController): Promise<void> {
  if (!decision.value) return
  previewLoading.value = true
  try {
    const passes: PolicyPass[] = customStylesActive.value
      ? customPasses.value
      : (decision.value.default_passes ?? [])
    const result = passes.length
      ? await job.previewPassesOnAllLayers(passes, controller.signal)
      : await job.previewAlgorithmOnAllLayers(
          decision.value.default_algorithm,
          (decision.value.default_options ?? {}) as Record<string, unknown>,
          controller.signal,
        )
    if (controller.signal.aborted) return
    // ``null`` means nothing renderable (e.g. vector source with no
    // layers) — fall back to the original SVG, not an error.
    if (result) renderedSvg.value = result.svg
  } catch {
    if (!controller.signal.aborted) previewError.value = true
  } finally {
    if (!controller.signal.aborted) previewLoading.value = false
  }
}

/** Re-render without re-resolving — used when only the custom-style
 *  stack changes (the resolver inputs are unchanged, so its answer
 *  would be identical). Aborts any in-flight render. */
async function rerenderOnly(): Promise<void> {
  if (!hasPlacement.value || !decision.value) return
  previewController?.abort()
  const controller = new AbortController()
  previewController = controller
  previewError.value = false
  await renderAdaptedPreview(controller)
}

// Operator mutated the custom-style stack (added, removed, or tweaked a
// slider). Re-render through the cheaper path that skips the policy
// resolver. The deep watch fires on knob drags too; the AbortController
// in ``rerenderOnly`` cancels stale renders so slider scrubbing stays
// responsive.
watch(customStyles, () => void rerenderOnly(), { deep: true })

function selectGoal(g: Goal): void {
  if (goal.value === g && decision.value) return
  goal.value = g
  void resolveAndPreview()
}

async function selectPalette(mode: PaletteMode): Promise<void> {
  if (paletteMode.value === mode && decision.value) return
  paletteMode.value = mode
  // Mirror to the global palette source so the job store's resnap
  // watcher refreshes each layer's ``assigned_color_hex`` against the
  // pool the operator just picked. The preview call below then sends
  // those fresh assigned hexes to ``/rerender`` (via
  // ``inkColorsFor``) so the SVG it returns uses the colours that
  // will actually be drawn.
  await paletteSource.update(mode === 'machine_only' ? 'pens' : 'union')
  await nextTick()
  void resolveAndPreview()
}

async function applyExpertDraft(): Promise<void> {
  // Commit the V1 draft mutations (image preprocess, segmentation
  // method, master style, typography) back to the placement by
  // re-running /upload with the freshly built options bundle. The
  // ``useFileManager.uploadSelected`` path is what the V1 modal's
  // "Apply" button drove; we reuse it verbatim so the existing
  // confirmation modal (overwrite warning, multi-pass reupload
  // warning) shows up in the same shape the operator already knows.
  // No-op when nothing is dirty so a stray click can't trigger a
  // pointless re-upload.
  if (!bitmapDraft.isDirty.value) return
  await fileManager.uploadSelected()
}

function confirm(): void {
  // In expert mode, an operator who tweaked the image / SVG / style
  // cards expects their changes to land in the final G-code. Commit
  // any pending draft mutations through the V1 ``uploadSelected``
  // path *before* the V2 confirm fires so the placement the parent
  // receives is the freshly-converted one. Fire-and-forget: the
  // upload schedules its own progress toast, and the parent's
  // confirm handler can run against the (already-rehydrated)
  // placement state once /upload returns.
  if (uiMode.isExpert) {
    void applyExpertDraft()
  }
  if (!hasPlacement.value || !decision.value) return
  if (customStylesActive.value) {
    // Override the resolver's algorithm pick with the operator's manual
    // stack while keeping every other field the resolver decided
    // (segmentation method, quality tier, fallback chain, …). First
    // pass mirrors ``default_algorithm`` / ``default_options`` per the
    // PolicyDecision contract (see schemas.ts ``default_passes`` doc).
    const passes = customPasses.value
    const first = passes[0]!
    emit('confirm', {
      ...decision.value,
      default_algorithm: first.algorithm,
      default_options: first.algorithm_options,
      default_passes: passes,
    })
    return
  }
  emit('confirm', decision.value)
}

// Compare needs two variants on the active placement to be useful.
const canCompare = computed(() => (job.selectedPlacement?.variants.length ?? 0) >= 2)

// Swatches shown under the preview: one per layer of the active
// placement, in draw order, showing the colour the layer will actually
// be drawn with (assigned ink hex from the magazine / inventory pool,
// or the segmentation centroid as a fallback). Used to make the
// "which inks will this print use" question answerable at a glance,
// independent of the preview SVG itself.
interface InkSwatch {
  layerId: string
  hex: string
  name: string
  // Human-readable label for the chip. Inventory name when known,
  // otherwise the hex itself.
  displayName: string
  // Secondary hex caption, shown next to ``displayName`` as a small
  // monospace aside. Empty when the name already *is* the hex (no
  // inventory match) to avoid duplicating the same six characters.
  displayHex: string
  isFallback: boolean
}
const inventoryNameByHex = computed(() => {
  const map = new Map<string, string>()
  for (const entry of availableColors.colors) {
    if (entry.name && entry.name.trim()) {
      map.set(entry.hex.toLowerCase(), entry.name)
    }
  }
  return map
})
const inkSwatches = computed<InkSwatch[]>(() => {
  // Prefer the LIVE /preview palette when the V1 cards have just
  // produced one (expert mode tweaks): it reflects what the
  // operator is actually about to commit on Apply. Falls back to
  // the placement's committed layers so assisted mode + fresh
  // sessions keep their chip strip. Without this the swatches
  // showed the previous /upload's colours even after the operator
  // changed k-means settings in the Style tab — exactly the "couleurs
  // pas à jour" the operator flagged.
  const livePalette = fileManager.previewResult?.value?.palette ?? null
  if (uiMode.isExpert && livePalette && livePalette.length > 0) {
    return livePalette.map((entry, idx) => {
      const hex = entry.color
      const namedMatch = inventoryNameByHex.value.get(hex.toLowerCase())
      const name = namedMatch ?? hex
      // Synthesise a stable layerId so the v-for keys stay stable
      // across renders. The /preview palette doesn't carry layer
      // ids; we tag them by index in cluster order.
      return {
        layerId: `preview-${idx}-${hex.replace('#', '')}`,
        hex,
        name,
        displayName: name,
        displayHex: namedMatch ? hex : '',
        isFallback: false,
      }
    })
  }
  const layers = job.selectedPlacement?.layers ?? []
  const ordered = [...layers].sort((a, b) => a.draw_order - b.draw_order)
  return ordered.map((layer) => {
    const assigned = layer.assigned_color_hex
    const hex = assigned ?? layer.source_color
    const namedMatch = inventoryNameByHex.value.get(hex.toLowerCase())
    const name = namedMatch ?? hex
    return {
      layerId: layer.layer_id,
      hex,
      name,
      displayName: name,
      displayHex: namedMatch ? hex : '',
      isFallback: !assigned,
    }
  })
})

// ============================ ESTIMATE =================================
// Time, length and pen count for the placement being edited. Computed
// straight from the ``layers`` prop (same data the job store uses for
// its plan-wide aggregates), so the operator sees what *this* placement
// will cost — not what the whole plan adds up to. Falls back to null
// when there's no placement; the template hides the row in that case.
const DEFAULT_SPEED_MM_S = 60
function effectiveSpeed(layer: LayerInfo): number {
  return (
    layer.drawing_speed_mm_s ??
    job.selectedProfile?.drawing_speed_mm_s ??
    DEFAULT_SPEED_MM_S
  )
}
const estimatedLengthMm = computed<number>(() => {
  const layers = props.layers ?? []
  return layers.reduce((sum, l) => sum + (l.total_length_mm ?? 0), 0)
})
const estimatedDurationSeconds = computed<number>(() => {
  const layers = props.layers ?? []
  return layers.reduce((sum, l) => {
    const speed = effectiveSpeed(l)
    return sum + (speed > 0 ? (l.total_length_mm ?? 0) / speed : 0)
  }, 0)
})
const requiredPenCount = computed<number>(() => {
  const layers = props.layers ?? []
  const hexes = new Set<string>()
  for (const layer of layers) {
    const hex = (layer.assigned_color_hex ?? layer.source_color ?? '').toLowerCase()
    if (hex) hexes.add(hex)
  }
  return hexes.size
})
const hasEstimate = computed<boolean>(() => estimatedLengthMm.value > 0)
function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return '—'
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))} s`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m === 0 ? `${h} h` : `${h} h ${m}`
}
function formatLengthMeters(mm: number): string {
  if (!Number.isFinite(mm) || mm <= 0) return '0'
  const meters = mm / 1000
  return meters < 10 ? meters.toFixed(1) : Math.round(meters).toString()
}

// ============================ COMPATIBILITY ============================
// Walk every layer's assigned colour, ask ``nearestPen`` for the best
// installed match, and surface a single green/orange badge with the
// count of unmatched inks. Clicking the badge opens the magazine
// editor on the Colors tab so the operator can load the missing pens
// without leaving the workflow.
interface PenSlotShape extends PenSlotLike {
  name?: string
}
const installedPens = computed<PenSlotShape[]>(() => {
  const slots = job.selectedProfile?.pens ?? []
  return slots
    .filter((p) => p.installed !== false)
    .map((p) => ({ index: p.index, color: p.color, installed: true, name: p.name }))
})
const missingInkCount = computed<number>(() => {
  const pens = installedPens.value
  if (pens.length === 0) return requiredPenCount.value
  const layers = props.layers ?? []
  const seen = new Set<string>()
  let missing = 0
  for (const layer of layers) {
    const hex = (layer.assigned_color_hex ?? layer.source_color ?? '').toLowerCase()
    if (!hex || seen.has(hex)) continue
    seen.add(hex)
    const match = nearestPen(hex, pens)
    // 'far' and 'wrong' both mean the operator will get a visibly
    // different ink — treat as missing so the warning is honest.
    if (match.severity === 'far' || match.severity === 'wrong' || match.severity === 'none') {
      missing += 1
    }
  }
  return missing
})
function openMagazine(): void {
  ui.openPlotterSettings('colors')
}
function openConnectionSettings(): void {
  ui.openPlotterSettings('connection')
}

// Note: the live preview pane (zoom, pan, original↔plot toggle,
// sheet outline, gesture hint) lives in EditPreviewPane.vue — the
// parent only forwards the source / rendered SVG and the loading /
// error flags.

// ============================ PREFLIGHT CHECKLIST ======================
// Four things have to be true before Generate can do anything useful:
// a file is selected, the machine is online, a sheet is picked, and
// every required ink is loaded. Surfacing them as a single line of
// green/orange chips means the operator can answer "am I ready?" in
// one glance instead of hunting four signals across the workspace.
const machineReady = computed<boolean>(() => plotter.status.connected === true)
const hasSheet = computed<boolean>(() => ui.previewSheet !== null)
const inksReady = computed<boolean>(
  () => requiredPenCount.value === 0 || missingInkCount.value === 0,
)
interface PreflightItem {
  id: 'file' | 'machine' | 'sheet' | 'inks'
  label: string
  ok: boolean
  // ``onFix`` jumps the operator straight to the panel that resolves
  // the warning. Null when the modal can't help (e.g. the missing
  // file has to come from the Files panel outside the modal).
  onFix: (() => void) | null
}
const preflightItems = computed<PreflightItem[]>(() => [
  {
    id: 'file',
    label: t('v2.modal.preflightFile'),
    ok: hasPlacement.value,
    onFix: null,
  },
  {
    id: 'machine',
    label: t('v2.modal.preflightMachine'),
    ok: machineReady.value,
    onFix: openConnectionSettings,
  },
  {
    id: 'sheet',
    label: t('v2.modal.preflightSheet'),
    ok: hasSheet.value,
    onFix: null,
  },
  {
    id: 'inks',
    label: t('v2.modal.preflightInks'),
    ok: inksReady.value,
    onFix: requiredPenCount.value > 0 ? openMagazine : null,
  },
])
// Header-chip variant doesn't aggregate — each chip carries its own
// colour. The previous "all-OK" highlight is dropped along with the
// body-level preflight block.

// ============================ SHEET OUTLINE ============================
// Translucent rectangle drawn behind the artwork at the active sheet's
// real aspect ratio so the operator can read paper shape (portrait vs
// landscape) and rough proportions without context-switching to the
// plan view. Sized to fit the preview pane with a margin; null when no
// sheet is selected so the template skips the overlay entirely.
interface SheetOutline {
  aspectRatio: number
  labelW: number
  labelH: number
  isPortrait: boolean
  // Real sheet width/height in mm — forwarded to EditPreviewPane so
  // the artwork inside the sheet is sized as ``artwork_mm / sheet_mm``.
  widthMm: number
  heightMm: number
}
const sheetOutline = computed<SheetOutline | null>(() => {
  const sheet = ui.previewSheet
  if (!sheet) return null
  const w = sheet.width_mm
  const h = sheet.height_mm
  if (!w || !h) return null
  return {
    widthMm: w,
    heightMm: h,
    aspectRatio: w / h,
    labelW: Math.round(w),
    labelH: Math.round(h),
    isPortrait: w / h < 1,
  }
})

// ============================ LAYER VISIBILITY =========================
// Each ink chip doubles as a one-click visibility toggle. Toggling
// triggers a fresh adapted render so the preview reflects exactly what
// Generate will produce. The job store already persists visibility to
// the active variant via ``setVisibility`` (autoSyncActiveVariant).
function isLayerVisible(layerId: string): boolean {
  return job.isVisible(layerId)
}
function toggleLayerVisibility(layerId: string): void {
  // Live /preview palette entries carry synthesised ids ("preview-N-…")
  // because the response doesn't enumerate layers. They aren't real
  // placement layers so the visibility map can't act on them — skip
  // the toggle rather than write a phantom key the rest of the store
  // would never read.
  if (layerId.startsWith('preview-')) return
  const next = !isLayerVisible(layerId)
  job.setVisibility(layerId, next)
  // The resolver inputs haven't changed; only the render needs a
  // refresh. ``resolveAndPreview`` is the cheapest reliable path —
  // policy resolution is fast and the result is identical, so the
  // re-render dominates and matches Generate's output.
  void resolveAndPreview()
}

// ============================ EXPERT MODE ==============================
// "Ouvrir l'éditeur complet" promise from the design notes (top of file).
// Switches the global UX mode to expert; the AssistantModeToggle in the
// header reflects the change immediately. The modal stays open so the
// operator doesn't lose their place — future iterations will swap the
// inner UI to the expert layout based on ``uiMode.isExpert``.
function openExpertEditor(): void {
  uiMode.setMode('expert')
}

// =========================================================================
// Expert mode tab state.
// Expert mode reveals the V1 source / SVG / style / text / layers tabs
// (restored after the operator audit). ``fileManager`` already knows
// the file kind, so we use it to gate the Text tab (only when the
// source carries typography) and to default the active tab to the
// most useful starting point for the current source.
const fileManager = useFileManager(t)
// Direct access to the V1 singleton draft so we can read ``isDirty``
// for the expert-mode "Appliquer" affordance. The cards inside the
// expert tabs already mutate this singleton via their own imports;
// reading it here is a no-op for the wiring.
const bitmapDraft = useBitmapDraft()
const showTextTab = computed<boolean>(() => fileManager.kind.value === 'typography')
const defaultExpertTab = computed<EditTabId>(() => {
  if (fileManager.kind.value === 'typography') return 'text'
  if (fileManager.showsBitmapForm.value) return 'image'
  return 'layers'
})
const activeExpertTab = ref<EditTabId>('layers')

// =========================================================================
// V1 expert-tab → preview wiring.
// The restored Image / SVG / Style / Text cards mutate a singleton
// ``useBitmapDraft`` whose deep watcher fires ``/preview`` via the
// ``useFileManager`` scheduler. That endpoint returns the freshly
// preprocessed + segmented + rendered SVG — which the assisted-mode
// ``previewAlgorithmOnAllLayers`` path *doesn't* hit. Without forwarding
// the scheduler's result, the operator would change brightness or
// segmentation method and see nothing happen on screen.
//
// We forward the scheduler's SVG to ``EditPreviewPane`` only when the
// operator is in expert mode AND the scheduler has actually produced a
// result for this session. Outside those conditions we fall back to the
// resolver-driven ``renderedSvg`` so the assisted wizard keeps its own
// preview pipeline untouched.
const expertPreviewSvg = computed<string | null>(() => {
  if (!uiMode.isExpert) return null
  const svg = fileManager.previewSvg.value
  return svg && svg.length > 0 ? svg : null
})
const expertPreviewLoading = computed<boolean>(() => {
  if (!uiMode.isExpert) return false
  return Boolean(fileManager.previewLoading.value)
})
const effectivePreviewSvg = computed<string | null>(
  () => expertPreviewSvg.value ?? renderedSvg.value,
)
const effectivePreviewLoading = computed<boolean>(
  () => expertPreviewLoading.value || previewLoading.value,
)

// =========================================================================
// Source image URL — fed to EditPreviewPane's "Original" and "Compare"
// modes so the operator sees the actual uploaded photo (PNG / JPG /
// PDF page raster) vs. the converted result, instead of two SVG
// derivatives of the same input. ``libraryFilePreviewImageUrl`` works
// for every supported source type (the backend rasterises vectors,
// documents, PDFs on demand), so this single URL covers all kinds.
// Null when the placement isn't backed by a library file yet — the
// pane falls back to ``originalSvg`` in that case.
const sourceImageUrl = computed<string | null>(() => {
  const id = job.selectedPlacement?.library_file_id
  if (!id) return null
  const page = Number(job.selectedPlacement?.upload_metadata?.page ?? 0)
  return libraryFilePreviewImageUrl(id, Number.isFinite(page) ? page : 0)
})
// Reset the tab whenever the source file kind changes so the operator
// doesn't land on an "Image" tab for a vector file. The :key in App.vue
// also remounts on placement switch; this watcher is the safety net
// for in-place file changes.
watch(
  defaultExpertTab,
  (next) => {
    activeExpertTab.value = next
  },
  { immediate: true },
)
// Ctrl/Cmd + digit shortcut: cycle through the visible tabs. Mirrors
// the V1 binding the EditTabs <kbd> badges advertise.
function selectExpertTab(id: EditTabId): void {
  activeExpertTab.value = id
}

// ============================ ONBOARDING TOUR ==========================
// Three-step welcome shown the first time the modal opens. Persists a
// "seen" flag in localStorage so it never reappears. ``skipOnboarding``
// (prop) overrides for tests and embedded scenarios.
interface OnboardingState {
  seen: boolean
}
function readOnboarding(): OnboardingState {
  try {
    const raw = window.localStorage.getItem(ONBOARDING_KEY)
    if (!raw) return { seen: false }
    const parsed = JSON.parse(raw) as Partial<OnboardingState>
    return { seen: parsed.seen === true }
  } catch {
    return { seen: false }
  }
}
function persistOnboardingSeen(): void {
  try {
    window.localStorage.setItem(ONBOARDING_KEY, JSON.stringify({ seen: true }))
  } catch {
    /* private mode / quota — accept that the tour may replay */
  }
}
const tourStep = ref<number>(0) // 0 = inactive; 1..TOUR_STEPS = visible
const tourActive = computed<boolean>(() => tourStep.value > 0)
function startTourIfFirstRun(): void {
  if (props.skipOnboarding) return
  if (!hasPlacement.value) return
  if (readOnboarding().seen) return
  tourStep.value = 1
}
function nextTourStep(): void {
  if (tourStep.value >= TOUR_STEPS) {
    dismissTour()
    return
  }
  tourStep.value += 1
}
function dismissTour(): void {
  tourStep.value = 0
  persistOnboardingSeen()
}

// ============================ PREAMBLE =================================
// One-sentence context card above the preview answering "what is this
// for?". Distinct from the welcome tour: the tour walks the operator
// through interactions, the preamble names the outcome ("your machine
// will draw this"). Persisted dismissal so it disappears once read.
function readPreambleDismissed(): boolean {
  try {
    const raw = window.localStorage.getItem(PREAMBLE_KEY)
    if (!raw) return false
    const parsed = JSON.parse(raw) as { dismissed?: boolean }
    return parsed.dismissed === true
  } catch {
    return false
  }
}
const preambleDismissed = ref<boolean>(props.skipOnboarding ? true : readPreambleDismissed())
const preambleVisible = computed<boolean>(
  () => !preambleDismissed.value && hasPlacement.value,
)
function dismissPreamble(): void {
  preambleDismissed.value = true
  try {
    window.localStorage.setItem(PREAMBLE_KEY, JSON.stringify({ dismissed: true }))
  } catch {
    /* private mode / quota — accept that the preamble may replay */
  }
}

// Ctrl/Cmd+Enter = Générer. No prev/next anymore — there's one screen.
useKeyboardShortcuts([
  {
    id: 'modal.next',
    handler: () => {
      if (!resolving.value && decision.value) confirm()
    },
  },
])

// Accessibility: Escape closes, focus moves into the dialog on mount,
// and Tab is trapped inside while open (matches v1 + native dialogs).
const dialogRoot = ref<HTMLElement | null>(null)

function onWindowKey(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('cancel')
    return
  }
  if (event.key !== 'Tab' || !dialogRoot.value) return
  const focusables = dialogRoot.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )
  if (focusables.length === 0) return
  const first = focusables[0]!
  const last = focusables[focusables.length - 1]!
  const active = document.activeElement as HTMLElement | null
  if (event.shiftKey && active === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}

onMounted(async () => {
  window.addEventListener('keydown', onWindowKey)
  // Belt-and-braces preview reset on every mount: the modal :key
  // remounts on placement change so this fires per editor session.
  // The placement-switch watcher in useFileManager *should* have
  // already cleared the singleton previewer, but if Vue reorders the
  // watcher flush vs. the modal re-render the operator can briefly
  // see the previous file's cached preview. Calling cancel + clear
  // here guarantees a clean slate the moment the modal appears, no
  // matter the order. Cheap when the previewer is already empty.
  fileManager.previewer.cancel()
  fileManager.previewer.clear()
  // Kick off the first preview immediately — zero clicks to a result.
  void resolveAndPreview()
  startTourIfFirstRun()
  await nextTick()
  if (!dialogRoot.value) return
  const first = dialogRoot.value.querySelector<HTMLElement>(
    'button:not([disabled]), select:not([disabled])',
  )
  first?.focus()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onWindowKey)
  previewController?.abort()
})

// If the source kind changes (parent swaps file without remount), redo
// the preview. The ``:key`` in App.vue normally remounts on placement
// change, but this keeps us correct if that ever stops being true.
watch(
  () => props.initialSourceKind,
  (next) => {
    if (next && next !== sourceKind.value) {
      sourceKind.value = next
      void resolveAndPreview()
    }
  },
)
</script>

<template>
  <!-- Backdrop: fixed full-screen, clicking outside the card cancels. -->
  <div
    class="modal-v2__backdrop"
    role="presentation"
    data-test="modal-v2-backdrop"
    @click.self="emit('cancel')"
  >
    <div
      ref="dialogRoot"
      class="modal-v2"
      role="dialog"
      aria-modal="true"
      :aria-label="t('v2.modal.title')"
    >
      <header class="modal-v2__header">
        <h2 class="modal-v2__title">{{ t('v2.modal.title') }}</h2>

        <!-- Preflight + cost chips live in the header so the operator
             can read "am I ready, what will it cost?" at a glance
             without scrolling. ``data-test`` ids match the previous
             chips so existing Playwright selectors keep working. -->
        <ul
          v-if="hasPlacement"
          class="modal-v2__header-chips"
          :aria-label="t('v2.modal.preflightLabel')"
        >
          <li v-for="item in preflightItems" :key="item.id">
            <button
              v-if="!item.ok && item.onFix"
              type="button"
              class="modal-v2__hchip is-warn is-actionable"
              :data-test="`modal-v2-preflight-${item.id}`"
              :title="t('v2.modal.preflightFix')"
              @click="item.onFix"
            >
              <span aria-hidden="true">⚠</span>
              <span>{{ item.label }}</span>
            </button>
            <span
              v-else
              class="modal-v2__hchip"
              :class="item.ok ? 'is-ok' : 'is-warn'"
              :data-test="`modal-v2-preflight-${item.id}`"
            >
              <span aria-hidden="true">{{ item.ok ? '✓' : '⚠' }}</span>
              <span>{{ item.label }}</span>
            </span>
          </li>
          <li v-if="hasEstimate">
            <span
              class="modal-v2__hchip is-info"
              data-test="modal-v2-estimate-time"
              :title="t('v2.modal.estimateLabel')"
            >
              <span aria-hidden="true">⏱</span>
              <span>{{ formatDuration(estimatedDurationSeconds) }}</span>
            </span>
          </li>
          <li v-if="hasEstimate">
            <span
              class="modal-v2__hchip is-info"
              data-test="modal-v2-estimate-length"
            >
              <span aria-hidden="true">📏</span>
              <span>{{ formatLengthMeters(estimatedLengthMm) }} m</span>
            </span>
          </li>
          <li v-if="requiredPenCount > 0">
            <span
              class="modal-v2__hchip is-info"
              data-test="modal-v2-estimate-pens"
            >
              <span aria-hidden="true">🖊</span>
              <span>{{ requiredPenCount }}</span>
            </span>
          </li>
        </ul>

        <AssistantModeToggle v-if="uiMode.isExpert" />
        <button
          type="button"
          class="ghost-btn"
          :disabled="!canCompare"
          :title="t('compare.open')"
          data-test="modal-v2-compare-open"
          @click="ui.openCompare()"
        >
          ⇄ {{ t('compare.open') }}
        </button>
        <button
          type="button"
          class="close"
          :aria-label="t('settings.close')"
          data-test="modal-v2-close"
          @click="emit('cancel')"
        >
          ×
        </button>
      </header>

      <!-- No placement: explain how to get one, lock Generate. -->
      <div
        v-if="!hasPlacement"
        class="modal-v2__noplacement"
        role="status"
        aria-live="polite"
        data-test="modal-v2-no-placement"
      >
        <span aria-hidden="true" class="modal-v2__noplacement-icon">⚠</span>
        <div class="modal-v2__noplacement-body">
          <strong>{{ t('v2.modal.noPlacementTitle') }}</strong>
          <p>{{ t('v2.modal.noPlacement') }}</p>
        </div>
      </div>

      <template v-else>
        <!-- Outcome preamble. The modal otherwise opens silent on the
             question every beginner asks first: "what is this for?".
             One short sentence + a dismiss-forever button. -->
        <div
          v-if="preambleVisible"
          class="modal-v2__preamble"
          role="note"
          data-test="modal-v2-preamble"
        >
          <p>{{ t('v2.modal.preamble') }}</p>
          <button
            type="button"
            class="modal-v2__preamble-dismiss"
            data-test="modal-v2-preamble-dismiss"
            @click="dismissPreamble"
          >
            {{ t('v2.modal.preambleDismiss') }}
          </button>
        </div>

        <!-- Single-column layout: preview dominates the top of the
             modal, everything else condenses underneath. The operator
             wanted maximum preview real estate; the tabs / sheet
             picker / inks / footer all sit beneath it in a compact
             stack. -->
        <div class="modal-v2__layout" data-test="modal-v2-layout">
          <!-- Preview block: preview pane + sheet picker. Sits at the
               top so the artwork is always the first thing on screen. -->
          <div class="modal-v2__preview-block">
        <!-- Live preview pane (zoom, pan, sheet outline, view toggle,
             gesture hint). Extracted to a subcomponent so this modal
             stays focused on decision-making. -->
        <EditPreviewPane
          :plot-svg="effectivePreviewSvg"
          :original-svg="props.previewSvg ?? null"
          :source-image-url="sourceImageUrl"
          :loading="effectivePreviewLoading"
          :error="previewError"
          :sheet="sheetOutline"
          :stream-file-id="job.selectedPlacement?.library_file_id ?? null"
          :artwork-width-mm="job.selectedPlacement?.width_mm ?? null"
          :artwork-height-mm="job.selectedPlacement?.height_mm ?? null"
        />

        <!-- Sheet picker: A6/A5/A4/A3/A2/Letter + portrait/landscape.
             Lives right under the preview so the operator can size the
             page-guide without leaving the modal. Mutations go through
             ``ui.setPreviewSheet`` so the plan view stays in sync. -->
        <SheetPicker />

        <!-- File caption. -->
        <p v-if="props.sourceName" class="modal-v2__caption" data-test="modal-v2-context">
          <span class="modal-v2__filename">{{ props.sourceName }}</span>
          <span v-if="props.layers && props.layers.length" class="modal-v2__counts">
            · {{ t('v2.modal.layerCount', { count: props.layers.length }) }}
          </span>
        </p>

        <!-- Estimate + magazine compatibility row. Time, length, pen
             count come from the placement's layers; the compatibility
             badge counts inks the resolver picked that aren't loaded in
             the magazine, with a one-click shortcut to fix it. -->
        <!-- Cost + preflight chips moved to the header. -->


        <!-- Per-layer ink swatches, in draw order. Each chip is a
             one-click visibility toggle (👁 / strike-through) so the
             beginner can mute a layer without leaving the modal. When
             the resolver fell back because nothing in the magazine
             matched, a secondary "Charger" button on the chip jumps
             straight to the magazine editor. -->
        <div
          v-if="inkSwatches.length"
          class="modal-v2__inks"
          data-test="modal-v2-inks"
          :aria-label="t('v2.modal.inksLabel')"
        >
          <span class="modal-v2__inks-label">{{ t('v2.modal.inksLabel') }}</span>
          <ul class="modal-v2__inks-list">
            <li
              v-for="ink in inkSwatches"
              :key="ink.layerId"
              class="modal-v2__ink-item"
            >
              <button
                type="button"
                class="modal-v2__ink"
                :class="{
                  'is-fallback': ink.isFallback,
                  'is-hidden': !isLayerVisible(ink.layerId),
                }"
                :aria-pressed="isLayerVisible(ink.layerId)"
                :title="
                  isLayerVisible(ink.layerId)
                    ? t('v2.modal.layerHide')
                    : t('v2.modal.layerShow')
                "
                :data-test="`modal-v2-ink-${ink.layerId}`"
                @click="toggleLayerVisibility(ink.layerId)"
              >
                <span
                  class="modal-v2__ink-eye"
                  aria-hidden="true"
                >{{ isLayerVisible(ink.layerId) ? '👁' : '⊘' }}</span>
                <span
                  class="modal-v2__ink-swatch"
                  :style="{ backgroundColor: ink.hex }"
                  aria-hidden="true"
                />
                <span class="modal-v2__ink-name">{{ ink.displayName }}</span>
              </button>
              <button
                v-if="ink.isFallback"
                type="button"
                class="modal-v2__ink-cta"
                :title="t('v2.modal.inkFallback', { hex: ink.hex })"
                :aria-label="t('v2.modal.inkFallbackCta')"
                :data-test="`modal-v2-ink-load-${ink.layerId}`"
                @click="openMagazine"
              >
                {{ t('v2.modal.inkFallbackCta') }}
              </button>
            </li>
          </ul>
        </div>

          </div>
          <!-- end preview block -->

          <!-- Controls block: condensed under the preview. In
               assisted mode this is the intent + palette + custom-
               style stack; in expert mode it's the V1 tab strip
               (Image / SVG / Style / Text / Layers + PresetPanel). -->
          <div class="modal-v2__controls-block">
        <!-- Expert surface: V1-style tab strip (Image / SVG / Style /
             Text / Layers) restored from the audit. Each tab carries
             the source-level cards (brightness/contrast, segmentation
             method, master style, typography) the V1→V2 migration
             dropped. The preview pane on the left stays mounted in
             both modes so the operator never loses sight of the
             result. -->
        <section v-if="uiMode.isExpert" class="modal-v2__expert" data-test="modal-v2-expert-panel">
          <EditTabs
            :model-value="activeExpertTab"
            :layer-count="props.layers?.length ?? 0"
            :variant-count="job.selectedPlacement?.variants?.length ?? 0"
            :show-text="showTextTab"
            @update:model-value="selectExpertTab"
          />
          <div class="modal-v2__expert-body">
            <ImageTab v-if="activeExpertTab === 'image'" />
            <SvgTab v-else-if="activeExpertTab === 'svg'" />
            <StyleTab v-else-if="activeExpertTab === 'style'" />
            <TextTab v-else-if="activeExpertTab === 'text'" />
            <LayersSection v-else-if="activeExpertTab === 'layers'" />
          </div>
          <PresetPanel />
        </section>

        <!-- Assisted surface: intent + palette + custom-style stack.
             Single-screen, three clicks max to a usable Generate. -->
        <fieldset v-else class="modal-v2__intent">
          <legend>{{ t('v2.modal.chooseIntent') }}</legend>
          <div class="intent-grid">
            <button
              v-for="opt in INTENTS"
              :key="opt"
              type="button"
              :class="{ active: goal === opt }"
              :aria-pressed="goal === opt"
              :data-test="`intent-${opt}`"
              @click="selectGoal(opt)"
            >
              <strong>{{ t(`v2.intent.${opt}`) }}</strong>
              <span class="intent-desc">{{ t(`v2.intent.${opt}Desc`) }}</span>
            </button>
          </div>
        </fieldset>

        <!-- Secondary control: where the colours come from. Machine
             magazine is the safe default (only pens actually loaded);
             "free" lets the resolver pick from the full palette for
             operators who'll swap pens by hand. -->
        <fieldset v-if="uiMode.isAssisted" class="modal-v2__palette">
          <legend>{{ t('v2.modal.paletteLabel') }}</legend>
          <div class="palette-toggle">
            <button
              type="button"
              :class="{ active: paletteMode === 'machine_only' }"
              :aria-pressed="paletteMode === 'machine_only'"
              data-test="palette-machine_only"
              @click="selectPalette('machine_only')"
            >
              {{ t('v2.modal.paletteMachine') }}
            </button>
            <button
              type="button"
              :class="{ active: paletteMode === 'free' }"
              :aria-pressed="paletteMode === 'free'"
              data-test="palette-free"
              @click="selectPalette('free')"
            >
              {{ t('v2.modal.paletteFree') }}
            </button>
          </div>
        </fieldset>

        <!-- Optional "stack your own styles" panel. Empty stack = the
             resolver wins (default experience); non-empty stack
             overrides the algorithm at preview + Generate time. The
             subcomponent owns the picker UI, the parent owns the
             selection state via v-model. Bitmap-only — vector and PDF
             pipelines bypass raster algorithms entirely. -->
        <StyleCustomizer
          v-if="uiMode.isAssisted && canCustomizeStyles"
          v-model="customStyles"
        />

        <p v-if="resolveError" class="error" data-test="modal-v2-resolve-error">
          {{ t('v2.modal.resolverError', { message: resolveError }) }}
        </p>
          </div>
          <!-- end controls block -->
        </div>
        <!-- end .modal-v2__layout -->
      </template>

      <footer class="modal-v2__footer">
        <button
          type="button"
          class="modal-v2__cancel"
          data-test="modal-v2-cancel"
          @click="emit('cancel')"
        >
          {{ t('v2.modal.cancel') }}
        </button>
        <div class="modal-v2__footer-actions">
          <button
            v-if="uiMode.isAssisted"
            type="button"
            class="modal-v2__expert-link"
            :title="t('v2.modal.openExpertHint')"
            data-test="modal-v2-open-expert"
            @click="openExpertEditor"
          >
            {{ t('v2.modal.openExpert') }}
          </button>
          <!-- Expert "Appliquer" button: commits the V1 draft mutations
               (image preprocess, segmentation, master style, typography)
               back to the placement via /upload. Disabled when the draft
               is clean so a stray click can't trigger a pointless
               re-conversion. The dirty hint after the label tells the
               operator the button is meaningful right now. -->
          <button
            v-if="uiMode.isExpert"
            type="button"
            class="modal-v2__apply-btn"
            :disabled="!bitmapDraft.isDirty || !hasPlacement"
            :title="
              bitmapDraft.isDirty
                ? t('v2.modal.applyExpertHint')
                : t('v2.modal.applyExpertClean')
            "
            data-test="modal-v2-apply-expert"
            @click="applyExpertDraft"
          >
            {{ t('v2.modal.applyExpert') }}
            <span v-if="bitmapDraft.isDirty" aria-hidden="true" class="dirty-dot">●</span>
          </button>
          <button
            type="button"
            class="generate-btn"
            :disabled="!decision || !hasPlacement || resolving"
            :title="!hasPlacement ? t('v2.modal.noPlacement') : undefined"
            data-test="confirm-button"
            @click="confirm"
          >
            {{ t('v2.modal.generate') }}
          </button>
        </div>
      </footer>

      <!-- First-run welcome tour. Three steps, no progress lost on
           skip. Renders above the modal body so the operator can still
           see what each step describes. -->
      <div
        v-if="tourActive"
        class="modal-v2__tour"
        role="dialog"
        aria-modal="false"
        :aria-label="t('v2.modal.tourTitle')"
        data-test="modal-v2-tour"
      >
        <div class="modal-v2__tour-card">
          <header class="modal-v2__tour-header">
            <h3>{{ t('v2.modal.tourTitle') }}</h3>
            <span class="modal-v2__tour-progress">{{
              t('v2.modal.tourProgress', { current: tourStep, total: TOUR_STEPS })
            }}</span>
          </header>
          <div v-if="tourStep === 1" class="modal-v2__tour-body" data-test="modal-v2-tour-step-1">
            <strong>{{ t('v2.modal.tourStep1Title') }}</strong>
            <p>{{ t('v2.modal.tourStep1Body') }}</p>
          </div>
          <div v-else-if="tourStep === 2" class="modal-v2__tour-body" data-test="modal-v2-tour-step-2">
            <strong>{{ t('v2.modal.tourStep2Title') }}</strong>
            <p>{{ t('v2.modal.tourStep2Body') }}</p>
          </div>
          <div v-else class="modal-v2__tour-body" data-test="modal-v2-tour-step-3">
            <strong>{{ t('v2.modal.tourStep3Title') }}</strong>
            <p>{{ t('v2.modal.tourStep3Body') }}</p>
          </div>
          <footer class="modal-v2__tour-footer">
            <button
              type="button"
              class="modal-v2__tour-skip"
              data-test="modal-v2-tour-skip"
              @click="dismissTour"
            >
              {{ t('v2.modal.tourSkip') }}
            </button>
            <button
              type="button"
              class="modal-v2__tour-next"
              data-test="modal-v2-tour-next"
              @click="nextTourStep"
            >
              {{ tourStep >= TOUR_STEPS ? t('v2.modal.tourDone') : t('v2.modal.tourNext') }}
            </button>
          </footer>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-v2__backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.7);
  padding: 1rem;
  overflow-y: auto;
}
.modal-v2 {
  background: white;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  padding: 1rem 1.5rem 1.25rem;
  /* Wide enough to fit the split layout — preview LEFT, controls
     RIGHT — without crowding either side. The grid responds to the
     viewport via min/max columns, so the modal isn't actually 1280
     px on a 1200-px-wide screen. */
  width: min(98vw, 1280px);
  max-height: 92vh;
  overflow-y: auto;
  font-family: system-ui, sans-serif;
  color: #1e293b;
}
/* Expert mode widens the modal so the side-by-side layout has room
   for both preview (left) and controls (right). The light shell
   keeps the preview visually dominant; LayersSection / PresetPanel
   carry their own dark surface inside the right column. */
/* Expert mode used to widen the modal here; the base ``.modal-v2``
   rule already maxes at 1280 px for both modes so the split has
   room either way. Kept the selector for future expert-only style
   overrides. */
.modal-v2:has(.modal-v2__expert) {
  width: min(98vw, 1280px);
}

/* Split layout: preview pinned on the LEFT (sticky), controls on
   the RIGHT. The preview block stays in view while the operator
   scrolls through tabs / cards / per-layer settings on the right.
   Falls back to a stacked single column on narrow viewports so the
   controls stay reachable on a tablet held in portrait. */
.modal-v2__layout {
  display: grid;
  grid-template-columns: minmax(340px, 1fr) minmax(360px, 1.2fr);
  gap: 1rem;
  align-items: start;
}
.modal-v2__preview-block {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  position: sticky;
  top: 0;
  /* Reserve space for the modal header + footer so the preview block
     never scrolls behind them. ``92vh`` matches the modal's own
     ``max-height``; subtract roughly the header (44 px) + footer
     (60 px) + paddings. */
  max-height: calc(92vh - 9rem);
  overflow-y: auto;
}
.modal-v2__controls-block {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  min-width: 0;
}

/* The expert-mode controls drawer inside the right column. */
.modal-v2__expert {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  padding: 0.65rem;
}

/* Narrow viewports (tablet portrait, phones): collapse to a single
   column so the operator can still reach every control. */
@media (max-width: 900px) {
  .modal-v2__layout {
    grid-template-columns: 1fr;
  }
  .modal-v2__preview-block {
    position: static;
    max-height: none;
  }
}
.modal-v2__header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid #e2e8f0;
}
.modal-v2__title {
  margin: 0;
  font-size: 1.05rem;
  flex-shrink: 0;
}
/* Preflight + estimate chip strip — lives in the header so the
   operator reads "am I ready, what will it cost?" at a glance
   without the body having to reserve real estate for them. */
.modal-v2__header-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  list-style: none;
  padding: 0;
  margin: 0;
  flex: 1;
  min-width: 0;
}
.modal-v2__hchip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.18rem 0.5rem;
  border-radius: 999px;
  font-size: 0.72rem;
  border: 1px solid transparent;
  background: white;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.modal-v2__hchip.is-ok {
  border-color: #10b981;
  color: #065f46;
  background: #ecfdf5;
}
.modal-v2__hchip.is-warn {
  border-color: #f59e0b;
  color: #92400e;
  background: #fff7ed;
}
.modal-v2__hchip.is-info {
  border-color: #cbd5e1;
  color: #334155;
  background: #f8fafc;
}
.modal-v2__hchip.is-actionable {
  cursor: pointer;
}
.modal-v2__hchip.is-actionable:hover {
  background: #ffedd5;
}
.modal-v2__hchip.is-actionable:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 2px;
}
.close {
  border: none;
  background: transparent;
  font-size: 1.5rem;
  cursor: pointer;
  color: #777;
  line-height: 1;
}
.ghost-btn {
  border: 1px solid #cbd5e1;
  background: #f8fafc;
  color: #1e293b;
  padding: 0.25rem 0.6rem;
  border-radius: 4px;
  font-size: 0.8rem;
  cursor: pointer;
}
.ghost-btn:hover:not(:disabled) {
  background: #e2e8f0;
}
.ghost-btn:disabled {
  cursor: not-allowed;
  opacity: 0.4;
}

/* Preview pane, zoom/pan, sheet outline, view toggle, gesture hint
   and spinner all live in EditPreviewPane.vue now. */

.modal-v2__caption {
  margin: 0.4rem 0 0.85rem;
  font-size: 0.8rem;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.modal-v2__filename {
  font-family: ui-monospace, Menlo, monospace;
  color: #334155;
}

.modal-v2__inks {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin: 0 0 0.6rem;
}
.modal-v2__inks-label {
  font-size: 0.72rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.modal-v2__inks-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  list-style: none;
  padding: 0;
  margin: 0;
}

.modal-v2__intent {
  border: none;
  padding: 0;
  margin: 0 0 0.5rem;
}
.modal-v2__intent legend {
  padding: 0;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
  font-weight: 600;
  color: #334155;
}
.intent-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.5rem;
}
.intent-grid button {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.2rem;
  padding: 0.65rem 0.75rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: white;
  transition:
    background 0.12s ease,
    border-color 0.12s ease,
    transform 0.08s ease;
  cursor: pointer;
  text-align: left;
}
.intent-grid button.active {
  border-color: #1f6feb;
  background: #eef4ff;
  box-shadow: inset 0 0 0 1px #1f6feb;
}
.intent-grid button:hover:not(.active) {
  background: #f8fafc;
  border-color: #94a3b8;
}
.intent-grid button:active {
  transform: scale(0.98);
}
.intent-grid button:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 2px;
}
.intent-desc {
  font-size: 0.72rem;
  color: #64748b;
  font-weight: 400;
}

.modal-v2__palette {
  border: none;
  padding: 0;
  margin: 0.75rem 0 0;
}
.modal-v2__palette legend {
  padding: 0;
  margin-bottom: 0.4rem;
  font-size: 0.9rem;
  font-weight: 600;
  color: #334155;
}
.palette-toggle {
  display: inline-flex;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  overflow: hidden;
}
.palette-toggle button {
  padding: 0.35rem 0.8rem;
  border: none;
  background: white;
  color: #475569;
  font-size: 0.82rem;
  cursor: pointer;
  transition: background 0.12s ease;
}
.palette-toggle button + button {
  border-left: 1px solid #cbd5e1;
}
.palette-toggle button.active {
  background: #eef4ff;
  color: #1f6feb;
  font-weight: 600;
}
.palette-toggle button:hover:not(.active) {
  background: #f8fafc;
}
.palette-toggle button:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 2px;
}

.error {
  color: #b71c1c;
  background: #fdecea;
  padding: 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
  margin: 0.5rem 0 0;
}
.modal-v2__noplacement {
  background: #fff4cc;
  border: 1px solid #d9b800;
  color: #5b4a00;
  padding: 0.65rem 0.85rem;
  border-radius: 6px;
  margin-bottom: 0.75rem;
  font-size: 0.85rem;
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
}
.modal-v2__noplacement-icon {
  font-size: 1.25rem;
  line-height: 1;
}
.modal-v2__noplacement-body strong {
  display: block;
  margin-bottom: 0.15rem;
}
.modal-v2__noplacement-body p {
  margin: 0;
  font-size: 0.8rem;
  opacity: 0.85;
}

/* Outcome preamble — single-sentence context card with a dismiss
   button. Light blue tint so it reads as informational, not warning. */
.modal-v2__preamble {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.55rem 0.75rem;
  background: #eef4ff;
  border: 1px solid #c7d8ff;
  border-radius: 6px;
  margin-bottom: 0.6rem;
  font-size: 0.82rem;
  color: #1e293b;
}
.modal-v2__preamble p {
  margin: 0;
  flex: 1;
  line-height: 1.35;
}
.modal-v2__preamble-dismiss {
  border: none;
  background: transparent;
  color: #1f6feb;
  font-size: 0.75rem;
  cursor: pointer;
  padding: 0.15rem 0.4rem;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
}
.modal-v2__preamble-dismiss:hover {
  background: white;
  text-decoration: underline;
}
.modal-v2__preamble-dismiss:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 2px;
}

/* Footer: Annuler on the left, expert link + Generate on the right. */
.modal-v2__footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
.generate-btn {
  padding: 0.55rem 1.4rem;
  border: 1px solid #1f6feb;
  background: #1f6feb;
  color: white;
  border-radius: 6px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition:
    background 0.12s ease,
    transform 0.08s ease;
}
.generate-btn:hover:not(:disabled) {
  background: #1959c7;
}
.generate-btn:active:not(:disabled) {
  transform: scale(0.97);
}
.generate-btn:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 2px;
}
.generate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Estimate + compatibility row. */
.modal-v2__estimate {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin: 0.5rem 0 0.6rem;
}
.modal-v2__estimate-label {
  font-size: 0.72rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.modal-v2__estimate-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  list-style: none;
  padding: 0;
  margin: 0;
  align-items: center;
}
.modal-v2__estimate-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.55rem;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #f8fafc;
  font-size: 0.78rem;
  color: #334155;
  font-variant-numeric: tabular-nums;
}
.modal-v2__estimate-icon {
  font-size: 0.85rem;
  line-height: 1;
}
/* Ink chips now act as visibility toggles. */
.modal-v2__ink-item {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
}
.modal-v2__ink {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.15rem 0.55rem 0.15rem 0.35rem;
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  background: white;
  font-size: 0.72rem;
  color: #334155;
  max-width: 14rem;
  cursor: pointer;
  transition:
    background 0.12s ease,
    opacity 0.15s ease;
}
.modal-v2__ink:hover {
  background: #f8fafc;
}
.modal-v2__ink:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 2px;
}
.modal-v2__ink.is-hidden {
  opacity: 0.5;
}
.modal-v2__ink.is-hidden .modal-v2__ink-name {
  text-decoration: line-through;
}
.modal-v2__ink.is-fallback {
  border-color: #f59e0b;
  background: #fffbeb;
  color: #92400e;
}
.modal-v2__ink-eye {
  font-size: 0.7rem;
  line-height: 1;
  opacity: 0.7;
}
.modal-v2__ink-swatch {
  display: inline-block;
  width: 0.85rem;
  height: 0.85rem;
  border-radius: 50%;
  border: 1px solid rgba(15, 23, 42, 0.25);
  flex-shrink: 0;
}
.modal-v2__ink-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.modal-v2__ink-cta {
  border: 1px solid #f59e0b;
  background: #fff7ed;
  color: #92400e;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.7rem;
  cursor: pointer;
  white-space: nowrap;
}
.modal-v2__ink-cta:hover {
  background: #ffedd5;
}
.modal-v2__ink-cta:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 2px;
}

.modal-v2__footer-actions {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}
.modal-v2__cancel {
  border: none;
  background: transparent;
  color: #64748b;
  font-size: 0.85rem;
  cursor: pointer;
  padding: 0.3rem 0.5rem;
  border-radius: 4px;
}
.modal-v2__cancel:hover {
  background: #f1f5f9;
  color: #1e293b;
}
.modal-v2__cancel:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 2px;
}
.modal-v2__apply-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.45rem 1rem;
  border: 1px solid #10b981;
  background: #ecfdf5;
  color: #065f46;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition:
    background 0.12s ease,
    opacity 0.12s ease;
}
.modal-v2__apply-btn:hover:not(:disabled) {
  background: #d1fae5;
}
.modal-v2__apply-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.modal-v2__apply-btn:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.modal-v2__apply-btn .dirty-dot {
  font-size: 0.7rem;
  color: #f59e0b;
}
.modal-v2__expert-link {
  border: none;
  background: transparent;
  color: #1f6feb;
  font-size: 0.85rem;
  cursor: pointer;
  padding: 0.3rem 0.4rem;
  border-radius: 4px;
}
.modal-v2__expert-link:hover {
  background: #eef4ff;
  text-decoration: underline;
}
.modal-v2__expert-link:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 2px;
}


/* Preflight checklist: one line of green / amber chips that
   aggregates the four "am I ready to plot" signals. */
.modal-v2__preflight {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin: 0.6rem 0 0;
  padding: 0.5rem 0.65rem;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  border-radius: 6px;
}
.modal-v2__preflight.is-all-ok {
  background: #ecfdf5;
  border-color: #10b981;
}
.modal-v2__preflight-label {
  font-size: 0.72rem;
  font-weight: 600;
  color: #334155;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.modal-v2__preflight-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  list-style: none;
  padding: 0;
  margin: 0;
}
.modal-v2__preflight-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  border: 1px solid transparent;
  background: white;
}
.modal-v2__preflight-chip.is-ok {
  border-color: #10b981;
  color: #065f46;
  background: #ecfdf5;
}
.modal-v2__preflight-chip.is-warn {
  border-color: #f59e0b;
  color: #92400e;
  background: #fff7ed;
}
.modal-v2__preflight-chip.is-actionable {
  cursor: pointer;
}
.modal-v2__preflight-chip.is-actionable:hover {
  background: #ffedd5;
}
.modal-v2__preflight-chip.is-actionable:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 2px;
}


/* Onboarding tour overlay. Anchored to the modal so the preview
   underneath stays partly visible. */
.modal-v2__tour {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 1rem;
  background: rgba(15, 23, 42, 0.35);
  border-radius: 8px;
  z-index: 5;
  pointer-events: auto;
}
.modal-v2 {
  position: relative;
}
.modal-v2__tour-card {
  background: white;
  border-radius: 8px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.25);
  padding: 0.85rem 1rem;
  max-width: 22rem;
  width: 100%;
}
.modal-v2__tour-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}
.modal-v2__tour-header h3 {
  margin: 0;
  font-size: 0.95rem;
  color: #1e293b;
}
.modal-v2__tour-progress {
  font-size: 0.7rem;
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}
.modal-v2__tour-body strong {
  display: block;
  margin-bottom: 0.25rem;
  font-size: 0.85rem;
  color: #1e293b;
}
.modal-v2__tour-body p {
  margin: 0;
  font-size: 0.8rem;
  color: #475569;
  line-height: 1.4;
}
.modal-v2__tour-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.75rem;
  gap: 0.5rem;
}
.modal-v2__tour-skip {
  border: none;
  background: transparent;
  color: #64748b;
  font-size: 0.78rem;
  cursor: pointer;
  padding: 0.25rem 0.4rem;
}
.modal-v2__tour-skip:hover {
  text-decoration: underline;
}
.modal-v2__tour-next {
  border: 1px solid #1f6feb;
  background: #1f6feb;
  color: white;
  padding: 0.35rem 0.9rem;
  border-radius: 6px;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
}
.modal-v2__tour-next:hover {
  background: #1959c7;
}
.modal-v2__tour-next:focus-visible,
.modal-v2__tour-skip:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 2px;
}
</style>
