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
import type { LayerInfo } from '../../api/client'
import { useKeyboardShortcuts } from '../../composables/useKeyboardShortcuts'
import { resolveAlgorithmPolicy } from '../../domain/policy/client'
import type { Goal, PaletteMode, PolicyDecision, SourceKind } from '../../domain/policy/schemas'
import { nearestPen, type PenSlotLike } from '../../lib/penMatching'
import { useAvailableColorsStore } from '../../stores/availableColors'
import { usePaletteSourceStore } from '../../stores/paletteSource'
import { useUiStore } from '../../stores/ui'
import { useUiModeStore } from '../../stores/uiMode'
import { useJobStore } from '../../stores/job'
import { usePlotterStore } from '../../stores/plotter'
import AssistantModeToggle from '../AssistantModeToggle.vue'

const ONBOARDING_KEY = 'omniplot.onboarding.editorV2.v1'
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
  // QUALITY recommendations carry a multi-pass stack — render that
  // exactly as "Generate" would; otherwise render the single algorithm.
  previewLoading.value = true
  try {
    const passes = decision.value.default_passes ?? []
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

// ============================== ZOOM & PAN ==============================
// Wheel zooms, drag pans, double-click / button resets. Same model as
// the expert EditPreviewPane so the gesture vocabulary is consistent.
// The view is intentionally *not* reset between intent changes so the
// operator can zoom into a detail and flip Rapide↔Qualité to compare it
// at the same magnification; switching files remounts the modal (App's
// ``:key``) which resets it naturally.
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const panning = ref(false)
let panStartX = 0
let panStartY = 0
let panInitX = 0
let panInitY = 0
const MIN_ZOOM = 0.2
const MAX_ZOOM = 16

const contentStyle = computed(() => ({
  transform: `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`,
  transformOrigin: 'center center',
  transition: panning.value ? 'none' : 'transform 0.08s ease-out',
}))

function clampZoom(value: number): number {
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, value))
}

function onWheel(event: WheelEvent): void {
  event.preventDefault()
  const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15
  zoom.value = clampZoom(zoom.value * factor)
}

function onPanStart(event: PointerEvent): void {
  if (event.button !== 0 && event.button !== 1) return
  panning.value = true
  panStartX = event.clientX
  panStartY = event.clientY
  panInitX = panX.value
  panInitY = panY.value
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function onPanMove(event: PointerEvent): void {
  if (!panning.value) return
  panX.value = panInitX + (event.clientX - panStartX)
  panY.value = panInitY + (event.clientY - panStartY)
}

function onPanEnd(event: PointerEvent): void {
  if (!panning.value) return
  panning.value = false
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
}

function zoomIn(): void {
  zoom.value = clampZoom(zoom.value * 1.25)
}

function zoomOut(): void {
  zoom.value = clampZoom(zoom.value / 1.25)
}

function resetView(): void {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
}

function confirm(): void {
  if (!hasPlacement.value || !decision.value) return
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

// ============================ VIEW MODE (ORIGINAL ↔ PLOT) ==============
// Beginners need to verify "is my drawing recognisable after the pen
// plotter has its way with it?". A one-click toggle between the source
// SVG and the adapted render answers that without leaving the modal.
// Only meaningful once the adapted render has landed — until then there
// is nothing to compare against, so the button is hidden.
const viewMode = ref<'plot' | 'original'>('plot')
const canCompareOriginal = computed<boolean>(
  () => Boolean(props.previewSvg) && Boolean(renderedSvg.value),
)
const displayedSvg = computed<string | null>(() => {
  if (viewMode.value === 'original') return props.previewSvg ?? renderedSvg.value ?? null
  return renderedSvg.value ?? props.previewSvg ?? null
})
function toggleViewMode(): void {
  viewMode.value = viewMode.value === 'plot' ? 'original' : 'plot'
}

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
const allPreflightOk = computed<boolean>(() => preflightItems.value.every((i) => i.ok))

// ============================ SHEET OUTLINE ============================
// Translucent rectangle drawn behind the artwork at the active sheet's
// real aspect ratio so the operator can read paper shape (portrait vs
// landscape) and rough proportions without context-switching to the
// plan view. Sized to fit the preview pane with a margin; null when no
// sheet is selected so the template skips the overlay entirely.
interface SheetOutline {
  widthPct: number
  heightPct: number
  labelW: number
  labelH: number
  isPortrait: boolean
}
const sheetOutline = computed<SheetOutline | null>(() => {
  const sheet = ui.previewSheet
  if (!sheet) return null
  const w = sheet.width_mm
  const h = sheet.height_mm
  if (!w || !h) return null
  // Fit the larger dimension to 90% of the pane, the smaller scales
  // proportionally — gives portrait/landscape orientations a visibly
  // different footprint.
  const ratio = w / h
  let widthPct: number
  let heightPct: number
  if (ratio >= 1) {
    widthPct = 90
    heightPct = 90 / ratio
  } else {
    heightPct = 90
    widthPct = 90 * ratio
  }
  return {
    widthPct,
    heightPct,
    labelW: Math.round(w),
    labelH: Math.round(h),
    isPortrait: ratio < 1,
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
        <h2>{{ t('v2.modal.title') }}</h2>
        <!-- Mode toggle is only an *exit* affordance, useful once the
             operator has actually crossed into expert. In assisted mode
             the footer "Ouvrir l'éditeur complet →" link is enough; a
             second redundant toggle just adds noise for beginners. -->
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
        <!-- Large live preview of the real adapted result. The whole
             surface captures pointer events for pan; the inner viewport
             carries the zoom/pan transform. -->
        <div
          class="modal-v2__preview"
          data-test="modal-v2-preview"
          :style="{ cursor: panning ? 'grabbing' : 'grab', touchAction: 'none' }"
          @wheel="onWheel"
          @pointerdown="onPanStart"
          @pointermove="onPanMove"
          @pointerup="onPanEnd"
          @pointercancel="onPanEnd"
          @dblclick="resetView"
        >
          <!-- Active sheet outline. Drawn behind the artwork as a
               translucent dashed rectangle in the sheet's real aspect
               ratio so the operator perceives portrait/landscape and
               rough proportions at a glance. -->
          <div
            v-if="sheetOutline"
            class="modal-v2__sheet-outline"
            :style="{
              width: `${sheetOutline.widthPct}%`,
              height: `${sheetOutline.heightPct}%`,
            }"
            aria-hidden="true"
            data-test="modal-v2-sheet-outline"
          >
            <span class="modal-v2__sheet-caption">
              {{ sheetOutline.labelW }} × {{ sheetOutline.labelH }} mm
            </span>
          </div>
          <div class="modal-v2__preview-viewport" :style="contentStyle">
            <!-- v-html: caller (App.vue) passes already-sanitized SVG,
                 and ``previewAlgorithmOnAllLayers`` returns backend-
                 rendered SVG from the same trusted pipeline. -->
            <!-- eslint-disable-next-line vue/no-v-html -->
            <div
              v-if="displayedSvg"
              class="modal-v2__preview-svg"
              :class="{ 'is-stale': previewLoading }"
              data-test="modal-v2-preview-svg"
              v-html="displayedSvg"
            />
          </div>

          <!-- Original ↔ Plot toggle. Helps the beginner verify the
               drawing is still recognisable after segmentation /
               algorithm. Anchored bottom-left so it doesn't fight the
               zoom controls for space. -->
          <button
            v-if="canCompareOriginal"
            type="button"
            class="modal-v2__view-toggle"
            :class="{ 'is-original': viewMode === 'original' }"
            :aria-pressed="viewMode === 'original'"
            data-test="modal-v2-view-toggle"
            @pointerdown.stop
            @wheel.stop
            @dblclick.stop
            @click="toggleViewMode"
          >
            {{ viewMode === 'plot' ? t('v2.modal.viewOriginal') : t('v2.modal.viewPlot') }}
          </button>

          <!-- Floating zoom controls; opt out of the pan capture. -->
          <div
            class="modal-v2__zoom"
            data-test="modal-v2-zoom"
            @pointerdown.stop
            @wheel.stop
            @dblclick.stop
          >
            <button
              type="button"
              :title="t('v2.modal.zoomIn')"
              :aria-label="t('v2.modal.zoomIn')"
              data-test="modal-v2-zoom-in"
              @click="zoomIn"
            >
              +
            </button>
            <button
              type="button"
              :title="t('v2.modal.zoomOut')"
              :aria-label="t('v2.modal.zoomOut')"
              data-test="modal-v2-zoom-out"
              @click="zoomOut"
            >
              −
            </button>
            <button
              type="button"
              class="modal-v2__zoom-reset"
              :title="t('v2.modal.resetView')"
              :aria-label="t('v2.modal.resetView')"
              data-test="modal-v2-zoom-reset"
              @click="resetView"
            >
              {{ Math.round(zoom * 100) }}%
            </button>
          </div>

          <div
            v-if="previewLoading"
            class="modal-v2__preview-overlay"
            role="status"
            aria-live="polite"
            data-test="modal-v2-preview-loading"
          >
            <span class="spinner" aria-hidden="true" />
            {{ t('v2.modal.previewLoading') }}
          </div>
          <p v-if="previewError" class="modal-v2__preview-error" data-test="modal-v2-preview-error">
            {{ t('v2.modal.previewError') }}
          </p>
        </div>

        <!-- Gesture hint: makes wheel/drag/double-click discoverable
             without a tour overlay. Tiny, single-line, always visible. -->
        <p class="modal-v2__gesture-hint" data-test="modal-v2-gesture-hint">
          {{ t('v2.modal.gestureHint') }}
        </p>

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
        <div
          v-if="hasEstimate || requiredPenCount > 0"
          class="modal-v2__estimate"
          data-test="modal-v2-estimate"
          :aria-label="t('v2.modal.estimateLabel')"
        >
          <span class="modal-v2__estimate-label">{{ t('v2.modal.estimateLabel') }}</span>
          <ul class="modal-v2__estimate-chips">
            <li
              v-if="hasEstimate"
              class="modal-v2__estimate-chip"
              data-test="modal-v2-estimate-time"
            >
              <span aria-hidden="true" class="modal-v2__estimate-icon">⏱</span>
              <span>{{
                t('v2.modal.estimateTime', { value: formatDuration(estimatedDurationSeconds) })
              }}</span>
            </li>
            <li
              v-if="hasEstimate"
              class="modal-v2__estimate-chip"
              data-test="modal-v2-estimate-length"
            >
              <span aria-hidden="true" class="modal-v2__estimate-icon">📏</span>
              <span>{{
                t('v2.modal.estimateLength', { meters: formatLengthMeters(estimatedLengthMm) })
              }}</span>
            </li>
            <li
              v-if="requiredPenCount > 0"
              class="modal-v2__estimate-chip"
              data-test="modal-v2-estimate-pens"
            >
              <span aria-hidden="true" class="modal-v2__estimate-icon">🖊</span>
              <span>{{ t('v2.modal.estimatePens', { count: requiredPenCount }) }}</span>
            </li>
          </ul>
        </div>

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

        <!-- The single decision: intent. Équilibré pre-selected. -->
        <fieldset class="modal-v2__intent">
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
        <fieldset class="modal-v2__palette">
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

        <p v-if="resolveError" class="error" data-test="modal-v2-resolve-error">
          {{ t('v2.modal.resolverError', { message: resolveError }) }}
        </p>

        <!-- Plain-language "ready to plot?" checklist. Aggregates the
             four signals an operator otherwise has to hunt for (file,
             machine, sheet, inks) into a single line of green ticks
             and amber warnings. Warnings whose fix lives inside a
             panel are clickable shortcuts. -->
        <div
          class="modal-v2__preflight"
          :class="{ 'is-all-ok': allPreflightOk }"
          data-test="modal-v2-preflight"
          :aria-label="t('v2.modal.preflightLabel')"
        >
          <span class="modal-v2__preflight-label">{{ t('v2.modal.preflightLabel') }}</span>
          <ul class="modal-v2__preflight-list">
            <li v-for="item in preflightItems" :key="item.id">
              <button
                v-if="!item.ok && item.onFix"
                type="button"
                class="modal-v2__preflight-chip is-warn is-actionable"
                :data-test="`modal-v2-preflight-${item.id}`"
                :title="t('v2.modal.preflightFix')"
                @click="item.onFix"
              >
                <span aria-hidden="true">⚠</span>
                <span>{{ item.label }}</span>
              </button>
              <span
                v-else
                class="modal-v2__preflight-chip"
                :class="item.ok ? 'is-ok' : 'is-warn'"
                :data-test="`modal-v2-preflight-${item.id}`"
              >
                <span aria-hidden="true">{{ item.ok ? '✓' : '⚠' }}</span>
                <span>{{ item.label }}</span>
              </span>
            </li>
          </ul>
        </div>
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
  width: min(96vw, 640px);
  max-height: 92vh;
  overflow-y: auto;
  font-family: system-ui, sans-serif;
  color: #1e293b;
}
.modal-v2__header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}
.modal-v2__header h2 {
  margin: 0;
  flex: 1;
  font-size: 1.1rem;
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

/* Live preview — the star of the screen. */
.modal-v2__preview {
  position: relative;
  height: clamp(220px, 42vh, 360px);
  background: repeating-conic-gradient(#f1f5f9 0% 25%, white 0% 50%) 0 / 20px 20px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.modal-v2__preview-viewport {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  will-change: transform;
}
.modal-v2__preview-svg {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0.5rem;
  transition: opacity 0.15s ease;
}
.modal-v2__preview-svg.is-stale {
  opacity: 0.45;
}
.modal-v2__preview-svg :deep(svg) {
  max-width: 100%;
  max-height: 100%;
  height: auto;
  width: auto;
}
.modal-v2__preview-overlay {
  position: absolute;
  inset: auto 0 0 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.4rem;
  background: rgba(255, 255, 255, 0.85);
  font-size: 0.8rem;
  color: #475569;
}
.modal-v2__preview-error {
  position: absolute;
  inset: auto 0.5rem 0.5rem;
  margin: 0;
  text-align: center;
  font-size: 0.8rem;
  color: #b71c1c;
  background: #fdecea;
  padding: 0.35rem;
  border-radius: 4px;
}
.modal-v2__zoom {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.modal-v2__zoom button {
  width: 1.9rem;
  height: 1.9rem;
  border: 1px solid #cbd5e1;
  background: rgba(255, 255, 255, 0.92);
  color: #1e293b;
  border-radius: 4px;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal-v2__zoom button:hover {
  background: #e2e8f0;
}
.modal-v2__zoom button:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 1px;
}
.modal-v2__zoom-reset {
  font-size: 0.6rem !important;
  font-variant-numeric: tabular-nums;
}
.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid #cbd5e1;
  border-top-color: #1f6feb;
  border-radius: 50%;
  animation: modal-v2-spin 0.7s linear infinite;
}
@keyframes modal-v2-spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
  }
}

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
.modal-v2__ink {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.15rem 0.45rem 0.15rem 0.25rem;
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  background: white;
  font-size: 0.72rem;
  color: #334155;
  max-width: 12rem;
}
.modal-v2__ink.is-fallback {
  border-color: #f59e0b;
  background: #fffbeb;
  color: #92400e;
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
  font-family: ui-monospace, Menlo, monospace;
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
  border: 1px solid #d0d0d0;
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
  outline-offset: -2px;
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

.modal-v2__footer {
  display: flex;
  justify-content: flex-end;
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

/* Gesture hint under the preview. */
.modal-v2__gesture-hint {
  margin: 0.35rem 0 0;
  font-size: 0.7rem;
  color: #94a3b8;
  text-align: center;
  font-style: italic;
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
  outline-offset: 1px;
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
  outline-offset: 1px;
}

/* Footer: Annuler on the left, expert link + Generate on the right. */
.modal-v2__footer {
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
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
  outline-offset: 1px;
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
  outline-offset: 1px;
}

/* Sheet outline: translucent dashed rectangle drawn behind the
   artwork, scaled to the active sheet's aspect ratio. */
.modal-v2__sheet-outline {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border: 1px dashed #94a3b8;
  background: rgba(255, 255, 255, 0.4);
  border-radius: 2px;
  pointer-events: none;
  z-index: 0;
}
.modal-v2__sheet-caption {
  position: absolute;
  top: 2px;
  left: 4px;
  font-size: 0.6rem;
  color: #64748b;
  background: rgba(255, 255, 255, 0.7);
  padding: 0 3px;
  border-radius: 2px;
  font-variant-numeric: tabular-nums;
}

/* "View original ↔ View plot" toggle. Bottom-left of the preview pane,
   opposite the zoom column so it doesn't compete for space. */
.modal-v2__view-toggle {
  position: absolute;
  bottom: 0.5rem;
  left: 0.5rem;
  padding: 0.25rem 0.65rem;
  border: 1px solid #cbd5e1;
  background: rgba(255, 255, 255, 0.92);
  color: #1e293b;
  border-radius: 999px;
  font-size: 0.72rem;
  cursor: pointer;
  z-index: 2;
}
.modal-v2__view-toggle:hover {
  background: white;
}
.modal-v2__view-toggle.is-original {
  background: #eef4ff;
  border-color: #1f6feb;
  color: #1f6feb;
}
.modal-v2__view-toggle:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 1px;
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
  outline-offset: 1px;
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
  outline-offset: 1px;
}
</style>
