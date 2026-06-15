<script setup lang="ts">
// Modal V2 — the editor (the only editor surface since the v0.2 migration).
//
// Single-screen, zero-mandatory-step flow (roadmap C.2 / audit #7 §3,
// simplified per operator feedback "encore plus simple, preview rapide
// adaptée, un minimum d'interactions"). Hosts BOTH modes directly,
// switched by the global UX mode (``uiMode``):
//   - ASSISTED: intent + palette + a small custom-style stack
//     (EditorAssistedPanel).
//   - EXPERT:   the Image / SVG / Style / Text / Layers tab strip
//     (EditorExpertPanel, lazy-loaded).
//
// In assisted mode the whole decision (source kind, palette, algorithm,
// layers) is resolved automatically from the placement + a single "intent"
// choice (Rapide / Équilibré / Qualité, défaut Équilibré). The operator
// sees a large LIVE preview of the real plotted result — re-rendered
// through the same ``/rerender`` endpoint "Generate" uses — and commits in
// one click. "Ouvrir l'éditeur complet" flips to expert mode in place.

import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { type LayerInfo } from '../../api/client'
import { useKeyboardShortcuts } from '../../composables/useKeyboardShortcuts'
import type { Goal, PaletteMode, PolicyDecision, SourceKind } from '../../domain/policy/schemas'
import { errorMessage } from '../../lib/errorMessage'
import { useAvailableColorsStore } from '../../stores/availableColors'
import { usePaletteSourceStore } from '../../stores/paletteSource'
import { useUiStore } from '../../stores/ui'
import { useUiModeStore } from '../../stores/uiMode'
import { useJobStore } from '../../stores/job'
import { useBitmapDraft } from '../../composables/useBitmapDraft'
import { useFileManager } from '../../composables/useFileManager'
import { useEditorPaletteSegmentation } from '../../composables/useEditorPaletteSegmentation'
import { useEditorInkSwatches } from '../../composables/useEditorInkSwatches'
import { useEditorExpertPreview } from '../../composables/useEditorExpertPreview'
import { useEditorPreviewPipeline } from '../../composables/useEditorPreviewPipeline'
import { useEditorConfirmation } from '../../composables/useEditorConfirmation'
import { useEditorCloseGuard } from '../../composables/useEditorCloseGuard'
import { useEditorPreflight } from '../../composables/useEditorPreflight'
import { useEditorOnboarding } from '../../composables/useEditorOnboarding'
import { useEditorDialogAccessibility } from '../../composables/useEditorDialogAccessibility'
import type { EditTabId } from '../edit/EditTabs.vue'
import { useEditorCustomStyles } from '../../composables/useEditorCustomStyles'
import EditorAssistedPanel from './EditorAssistedPanel.vue'
import EditorExpertPanel from './EditorExpertPanel.vue'
import EditorHeader from './EditorHeader.vue'
import EditorInkPanel from './EditorInkPanel.vue'
import EditorPageNav from './EditorPageNav.vue'
import EditPreviewPane from './EditPreviewPane.vue'

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

// The live preview state (``decision``, ``resolving``, ``resolveError``,
// ``renderedSvg``, ``previewLoading``, ``previewError``) plus the single
// preview scheduler are owned by ``useEditorPreviewPipeline`` — created
// once ``fileManager`` exists (it feeds the palette re-segmentation) and
// destructured below. ``renderedSvg`` holds the adapted result; until it
// lands the pane falls back to the original placement SVG so it's never
// blank.

// The expert-apply + confirm logic — ``applying``, ``applyError``,
// ``applyExpertDraft`` and ``confirm`` — lives in
// ``useEditorConfirmation``, wired up below once ``bitmapDraft`` and
// ``fileManager`` exist.

// True when there's an active placement to apply the decision to.
const hasPlacement = computed(() => Boolean(props.previewSvg || props.sourceName))

// ============================ CUSTOM STYLE STACK =======================
// Optional escape hatch from the resolver's automatic algorithm pick:
// the StyleCustomizer subcomponent owns the picker UI; ``useEditorCustomStyles``
// owns the selection state, the bitmap-only gate, the one-shot seed from the
// committed ``layer_algorithms``, and the PolicyPass projection that drives
// /rerender and Generate. Empty stack = resolver wins (default experience);
// non-empty stack = the modal overrides decision.default_*. ``seed`` runs once
// on open (the modal remounts per session via its ``:key``).
const {
  customStyles,
  customStylesActive,
  canCustomizeStyles,
  customPasses,
  seedCustomStylesFromCommitted,
} = useEditorCustomStyles({ sourceKind: () => sourceKind.value })

function selectGoal(g: Goal): void {
  if (goal.value === g && decision.value) return
  goal.value = g
  // Direct operator action → resolve immediately for a responsive click.
  schedule('resolve-and-segment', { immediate: true })
}

// Surfaced when a palette switch fails to persist — keeps the toggle and
// the rendered preview honest by rolling the local mode back to whatever
// actually landed in the store.
const paletteError = ref<string | null>(null)
async function selectPalette(mode: PaletteMode): Promise<void> {
  if (paletteMode.value === mode && decision.value) return
  const previousMode = paletteMode.value
  paletteMode.value = mode
  paletteError.value = null
  // Mirror to the global palette source so the job store's resnap
  // watcher refreshes each layer's ``assigned_color_hex`` against the
  // pool the operator just picked. The preview call below then sends
  // those fresh assigned hexes to ``/rerender`` (via
  // ``inkColorsFor``) so the SVG it returns uses the colours that
  // will actually be drawn.
  //
  // "Palette libre" means the operator's available-colours INVENTORY,
  // not the pens∪inventory union: the union let the machine's mounted
  // pen colours leak into the segmentation pool, so the preview showed
  // colours outside the list the operator curated ("ça me donne des
  // couleurs en dehors des couleurs dispo"). Union stays the fallback
  // when the inventory is empty so the button is never a no-op.
  try {
    await paletteSource.update(
      mode === 'machine_only' ? 'pens' : availableColors.ordered.length > 0 ? 'available' : 'union',
    )
  } catch (err) {
    // The store didn't switch pools — restore the toggle so the UI doesn't
    // advertise a palette the segmentation isn't actually using, and tell
    // the operator why. No resolve is scheduled (nothing changed).
    paletteMode.value = previousMode
    paletteError.value = errorMessage(err)
    return
  }
  await nextTick()
  // Resolve immediately: the ``effectivePool`` watcher also fires from the
  // source change above, but ``schedule`` clears its pending debounce so
  // the two collapse into a single resolve instead of a double render.
  schedule('resolve-and-segment', { immediate: true })
}

// Ink-swatch strip + the expert-mode live-preview centroid→pool snap live
// in ``useEditorInkSwatches`` — wired up below once ``fileManager`` and
// ``effectivePool`` exist (it reads the live /preview palette and the
// operator's pool). ``previewInkSnap`` is shared with the expert preview
// recolour so the chips and the preview SVG agree on the inks drawn.

// ======================= PREFLIGHT + ESTIMATES ========================
// Drawing estimates (length / time / required pen count), ink
// compatibility and the four-chip "am I ready?" checklist — all derived
// state, owned by ``useEditorPreflight``. Only the bindings the template
// reads are destructured here. The live preview pane (zoom, pan, sheet
// outline) lives in EditPreviewPane.vue; this parent only forwards SVGs
// and flags.
// Only ``openMagazine`` is still consumed (the ink-fallback CTA). The
// preflight chips + cost estimates were dropped from the header to give
// the preview maximum room, so the rest of this read-model is no longer
// rendered.
const { openMagazine } = useEditorPreflight({
  layers: () => props.layers,
  hasPlacement,
  t,
})

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
  // No re-render needed: EditPreviewPane folds visibility into its
  // per-layer opacity overlay, so the hidden colour vanishes from the
  // displayed SVG instantly (the backend /rerender returns every layer
  // regardless, so a round-trip here would change nothing on screen).
  // The visibility flag is still persisted to the variant via
  // ``setVisibility`` so Generate honours it.
}

// =========================================================================
// EXPERT MODE
// The assisted/expert switch lives in the header (AssistantModeToggle).
// The modal stays open across the switch and swaps its controls block to
// the expert tab strip (EditorExpertPanel) based on ``uiMode.isExpert`` —
// the preview pane stays mounted throughout.
// =========================================================================
// Expert mode tab state.
// Expert mode reveals the V1 source / SVG / style / text / layers tabs
// (restored after the operator audit). ``fileManager`` already knows
// the file kind, so we use it to gate the Text tab (only when the
// source carries typography) and to default the active tab to the
// most useful starting point for the current source.
// ``owner: true`` — the modal owns the preview lifecycle: closing the
// modal cancels any in-flight /preview. The tabs inside the modal call
// useFileManager() WITHOUT owner so a tab switch can't abort the
// shared previewer mid-flight.
const fileManager = useFileManager(t, { owner: true })

// ============================ PREVIEW PIPELINE =========================
// Palette-driven re-segmentation + the single preview scheduler. Created
// here (not at the top of setup) because the segmentation needs the
// owner ``fileManager`` to round-trip /upload. The pipeline owns all the
// live preview state the template reads; the four watchers below are the
// only places that ask for a preview, each via ``schedule(level)``.
const segmentation = useEditorPaletteSegmentation(fileManager)
const { effectivePool, ensureSegmentationMatchesDecision } = segmentation

// Ink chips + the shared expert centroid→pool snap (see the note up top).
const { previewInkSnap, inkSwatches } = useEditorInkSwatches({ fileManager, effectivePool })

const pipeline = useEditorPreviewPipeline({
  hasPlacement,
  sourceKind,
  goal,
  paletteMode,
  customStylesActive,
  customPasses,
  resolveInputs: () => ({
    available_colors_count: props.availableColorsCount ?? 1,
    image_megapixels: props.imageMegapixels ?? null,
    layer_count_estimate: props.layers?.length || 1,
    is_mono_pen_machine: Boolean(props.isMonoPenMachine),
  }),
  // In EXPERT mode the operator drives segmentation by hand via the SVG /
  // Style tabs (the singleton bitmap draft). The resolver's automatic
  // re-segmentation — which re-uploads the placement as kmeans_lab +
  // ink_pool to snap every cluster onto the pen pool — would silently
  // override that choice the moment the colour stores load on a tab
  // switch (changing the rendered colours and reverting an explicit
  // k-means pick). Skip it in expert mode so the draft stays authoritative;
  // assisted mode still gets the automatic pool-matching round-trip.
  ensureSegmentation: (decision, controller, onUploadStart) =>
    uiMode.isExpert
      ? Promise.resolve()
      : ensureSegmentationMatchesDecision(decision, controller, onUploadStart),
})
const {
  decision,
  resolveError,
  renderedSvg,
  previewLoading,
  previewError,
  previewErrorMessage,
  canGenerate,
  schedule,
} = pipeline

// Inventory edits / palette-source flips while the modal is open move the
// pool under the decision — re-resolve so the chips and the render keep
// matching what the operator just picked. Debounced (via ``schedule``):
// an inventory editing session mutates the pool once per swatch.
watch(
  () => effectivePool.value.join('|'),
  (next, prev) => {
    if (next === prev || !decision.value) return
    schedule('resolve-and-segment')
  },
)

// Per-layer ink assignment → preview coupling. The LayerCard picker
// writes ``assigned_color_hex`` through the job store; this modal shows
// its own adapted render, so re-render whenever any layer's assigned ink
// moves. Debounced so a quick run through several layers renders once.
watch(
  () =>
    (job.selectedPlacement?.layers ?? [])
      .map((l) => `${l.layer_id}:${l.assigned_color_hex ?? ''}`)
      .join('|'),
  (next, prev) => {
    if (next === prev || !decision.value) return
    schedule('render-only')
  },
)

// Operator mutated the custom-style stack (added, removed, or tweaked a
// slider). Re-render through the cheaper render-only path that skips the
// resolver. Debounced so slider scrubbing collapses to one render.
watch(customStyles, () => schedule('render-only'), { deep: true })

// Physical size → render coupling. Changing the sheet format refits the
// placement (SheetPicker → ``fitSelectedPlacementToSheet``), so the
// render must re-run at the new mm size (pen widths convert from it).
// Debounced so a quick A6→A5→A4 click run renders once.
watch(
  () => [job.selectedPlacement?.width_mm ?? 0, job.selectedPlacement?.height_mm ?? 0] as const,
  ([w, h], [prevW, prevH]) => {
    // Sub-0.01 mm deltas are float noise from centring math, not an
    // operator action — skip so the watcher can't ping-pong.
    if (Math.abs(w - prevW) < 0.01 && Math.abs(h - prevH) < 0.01) return
    if (!decision.value) return
    schedule('render-only')
  },
)

// Direct access to the V1 singleton draft so we can read ``isDirty``
// for the expert-mode "Appliquer" affordance. The cards inside the
// expert tabs already mutate this singleton via their own imports;
// reading it here is a no-op for the wiring.
const bitmapDraft = useBitmapDraft()

// Race-safe save: in expert mode the single "save the print style"
// button awaits the dirty-draft upload before emitting ``confirm`` so the
// parent never commits from the pre-apply SVG. ``applyExpertDraft`` is no
// longer a separate footer button — ``confirm`` runs it internally. Owns
// ``applying`` / ``applyError``.
const {
  applying,
  applyError,
  confirm,
  dispose: disposeConfirmation,
} = useEditorConfirmation({
  isExpert: computed(() => uiMode.isExpert),
  hasPlacement,
  decision,
  isDirty: bitmapDraft.isDirty,
  customStylesActive,
  customPasses,
  fileManager,
  onConfirm: (d) => emit('confirm', d),
})

// The single header "save the print style" button is locked until there's
// a decision to commit and nothing is in flight (resolve or expert apply).
// ``canGenerate`` already folds in the pipeline's busy state *and* the
// segmentation-error block + the debounce-pending window, so the operator
// can't commit from a placement that's out of sync with the displayed
// decision (audit P1). The decision / placement / applying checks stay
// explicit here.
const saveDisabled = computed(
  () => !decision.value || !hasPlacement.value || !canGenerate.value || applying.value,
)

// Single close gate (header ✕, backdrop, Escape all route
// here). Blocks closing while an expert apply is committing and confirms
// before discarding an unsaved expert draft. ``window.confirm`` is the same
// affordance the colours panel uses for destructive actions.
//
// Gated on EXPERT mode: the shared bitmap draft reads "dirty" by default
// until an upload pins its baseline (``markCommitted``), and the assisted
// wizard never edits that draft — so confirming on an assisted-mode close
// would nag the operator about changes they never made. Only the expert
// tabs surface the draft, so only an expert close can lose real work.
const hasUnsavedExpertDraft = computed(() => uiMode.isExpert && bitmapDraft.isDirty.value)
const { requestClose } = useEditorCloseGuard({
  applying,
  isDirty: hasUnsavedExpertDraft,
  // Defensive ``typeof`` guard: ``window.confirm`` is absent in some test
  // DOMs; treat "no dialog available" as "proceed" rather than throwing.
  confirmDiscard: () =>
    typeof window.confirm === 'function' ? window.confirm(t('v2.modal.discardConfirm')) : true,
  onClose: () => emit('cancel'),
})

// The Text tab is offered for every source that carries text — pure
// typography (.txt / .md) AND mixed text+image documents (PDF / DOCX /
// ODT / RTF / HTML). The tab content (TextTab.vue) already branches on
// the document vs. typography kind; only this gate was still
// typography-only, which is why a DOCX opened without it.
const showTextTab = computed<boolean>(() => fileManager.carriesText.value)
const defaultExpertTab = computed<EditTabId>(() => {
  // Text-bearing sources open on the Text tab so the operator lands on
  // the controls that actually shape the result (font, Hershey, page),
  // not the bitmap tabs a document can't be re-rendered through.
  if (fileManager.carriesText.value) return 'text'
  if (fileManager.showsBitmapForm.value) return 'image'
  return 'layers'
})

// Multi-page documents (PDF / DOCX / …) report ``page_count`` in the
// upload metadata. The page navigator lets the operator switch the
// edited page without leaving the modal; ``goToPage`` re-runs the
// conversion for the chosen page through the job store.
const pageCount = computed<number>(() => fileManager.pageCount.value)
const currentPage = computed<number>(() => fileManager.currentPage.value)
const hasPages = computed<boolean>(() => pageCount.value > 1)
function goToPage(page: number): void {
  void fileManager.goToPage(page)
}
const activeExpertTab = ref<EditTabId>('layers')

// Expert-tab → preview wiring (forward the /preview render in expert mode,
// fall back to the resolver render otherwise), the source-image URL for
// Original/Compare, and the per-run latency estimate — all owned by
// ``useEditorExpertPreview``.
const { effectivePreviewSvg, effectivePreviewLoading, previewEstimateMs, sourceImageUrl } =
  useEditorExpertPreview({
    fileManager,
    previewInkSnap,
    renderedSvg,
    pipelineLoading: previewLoading,
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

// ======================= ONBOARDING TOUR + PREAMBLE ====================
// First-run welcome tour (three steps) and the one-sentence preamble card
// above the preview — both localStorage-backed so they never replay once
// seen / dismissed. ``skipOnboarding`` (prop) overrides for tests/embeds.
const {
  TOUR_STEPS,
  tourStep,
  tourActive,
  startTourIfFirstRun,
  nextTourStep,
  dismissTour,
  preambleVisible,
  dismissPreamble,
} = useEditorOnboarding({
  skipOnboarding: Boolean(props.skipOnboarding),
  hasPlacement,
})

// Ctrl/Cmd+Enter = Générer. No prev/next anymore — there's one screen.
useKeyboardShortcuts([
  {
    id: 'modal.next',
    handler: () => {
      // Mirror the footer's Generate guard: never fire mid-pipeline, during
      // the debounce window, after a segmentation error, or mid-apply — only
      // when there's a decision to generate from.
      if (canGenerate.value && !applying.value && decision.value) confirm()
    },
  },
])

// Accessibility: Escape closes, focus moves into the dialog on mount and
// returns to the opener on close, and Tab is trapped inside while open
// (matches native <dialog>). Owned by useEditorDialogAccessibility.
const dialogRoot = ref<HTMLElement | null>(null)
const a11y = useEditorDialogAccessibility({
  dialogRoot,
  // While the welcome tour is open it owns the foreground: Escape dismisses
  // the tour (and unblocks the modal) rather than closing the whole editor
  // out from under the operator mid-tour.
  onEscape: () => {
    if (tourActive.value) {
      dismissTour()
      return
    }
    requestClose()
  },
})

// When the tour dismisses, its buttons unmount and the modal body stops
// being inert — pull focus back into the modal so it doesn't fall to
// <body> (the trap would then yank it back on the next Tab, but landing it
// cleanly is better for screen-reader users).
watch(tourActive, (active, was) => {
  if (was && !active) {
    void nextTick().then(() => a11y.focusInitial())
  }
})

onMounted(async () => {
  // Capture the opener + start the keyboard trap before any focus moves.
  a11y.activate()
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
  // Reflect the committed style in the beginner stack BEFORE the first
  // resolve/preview so the operator sees (and Generate commits) the
  // style already saved on the placement rather than a fresh resolver
  // pick. The pipeline's render reads ``customStylesActive`` so a seeded
  // stack renders straight away.
  seedCustomStylesFromCommitted()
  // Kick off the first preview immediately — zero clicks to a result.
  schedule('resolve-and-segment', { immediate: true })
  startTourIfFirstRun()
  await nextTick()
  // Move focus into the dialog once its content has rendered.
  a11y.focusInitial()
})

onBeforeUnmount(() => {
  // Stop the keyboard trap + return focus to the opener.
  a11y.deactivate()
  // Tears down the single preview timer + aborts any in-flight request.
  pipeline.dispose()
  // Mark the confirmation disposed so an expert upload that's still in
  // flight can't emit ``confirm`` from this now-unmounted modal.
  disposeConfirmation()
})

// If the source kind changes (parent swaps file without remount), redo
// the preview. The ``:key`` in App.vue normally remounts on placement
// change, but this keeps us correct if that ever stops being true.
watch(
  () => props.initialSourceKind,
  (next) => {
    if (next && next !== sourceKind.value) {
      sourceKind.value = next
      schedule('resolve-and-segment', { immediate: true })
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
    @click.self="requestClose"
  >
    <div
      ref="dialogRoot"
      class="modal-v2"
      :class="{ 'is-expert': uiMode.isExpert }"
      role="dialog"
      aria-modal="true"
      :aria-label="t('v2.modal.title')"
    >
      <EditorHeader
        :inert="tourActive"
        :has-placement="hasPlacement"
        :save-disabled="saveDisabled"
        :applying="applying"
        @close="requestClose"
        @save="confirm"
      />

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
          :inert="tourActive"
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
        <div class="modal-v2__layout" :inert="tourActive" data-test="modal-v2-layout">
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
              :error-message="previewErrorMessage"
              :sheet="sheetOutline"
              :estimate-ms="previewEstimateMs"
              :stream-file-id="job.selectedPlacement?.library_file_id ?? null"
              :artwork-width-mm="job.selectedPlacement?.width_mm ?? null"
              :artwork-height-mm="job.selectedPlacement?.height_mm ?? null"
            />

            <!-- Sheet picker moved to the header (above the preview); the
                 filename caption was removed so only the used colours sit
                 under the preview, maximising preview real estate. -->

            <!-- Page navigator: multi-page documents (PDF / DOCX / …)
                 convert one page at a time. Extracted to EditorPageNav.vue. -->
            <EditorPageNav
              v-if="hasPages"
              :current-page="currentPage"
              :page-count="pageCount"
              @go="goToPage"
            />

            <!-- Estimate + magazine compatibility row. Time, length, pen
             count come from the placement's layers; the compatibility
             badge counts inks the resolver picked that aren't loaded in
             the magazine, with a one-click shortcut to fix it. -->
            <!-- Cost + preflight chips moved to the header. -->

            <!-- Per-layer ink swatches + one-click visibility toggles.
                 Extracted to EditorInkPanel.vue. -->
            <EditorInkPanel
              :swatches="inkSwatches"
              :is-visible="isLayerVisible"
              @toggle="toggleLayerVisibility"
              @load-ink="openMagazine"
            />
          </div>
          <!-- end preview block -->

          <!-- Controls block: condensed under the preview. In
               assisted mode this is the intent + palette + custom-
               style stack; in expert mode it's the V1 tab strip
               (Image / SVG / Style / Text / Layers). -->
          <div class="modal-v2__controls-block">
            <!-- Expert surface: V1-style tab strip (Image / SVG / Style /
             Text / Layers) restored from the audit. Each tab carries
             the source-level cards (brightness/contrast, segmentation
             method, master style, typography) the V1→V2 migration
             dropped. The preview pane on the left stays mounted in
             both modes so the operator never loses sight of the
             result. -->
            <EditorExpertPanel
              v-if="uiMode.isExpert"
              :active-tab="activeExpertTab"
              :layer-count="props.layers?.length ?? 0"
              :show-text="showTextTab"
              @update:active-tab="selectExpertTab"
            />

            <!-- Assisted surface: intent + palette + custom-style stack.
             Single-screen, three clicks max to a usable Generate. -->
            <EditorAssistedPanel
              v-else
              v-model:custom-styles="customStyles"
              :goal="goal"
              :palette-mode="paletteMode"
              :can-customize-styles="canCustomizeStyles"
              @select-goal="selectGoal"
              @select-palette="selectPalette"
            />

            <!-- Resolver error sits outside the panels: a failed resolve
             can happen in either mode (it runs on open regardless). -->
            <p v-if="resolveError" class="error" data-test="modal-v2-resolve-error">
              {{ t('v2.modal.resolverError', { message: resolveError }) }}
            </p>
            <!-- Palette switch failed to persist — the toggle has rolled
             back to the pool actually in use; tell the operator why. -->
            <p v-if="paletteError" class="error" data-test="modal-v2-palette-error">
              {{ t('v2.modal.paletteError', { message: paletteError }) }}
            </p>
            <!-- Save failed to commit the expert draft (the header Save
             button runs the apply internally) — surface why so the
             operator can retry rather than silently losing the work. -->
            <p v-if="applyError" class="error" role="alert" data-test="modal-v2-apply-error">
              {{ t('v2.modal.applyError', { message: applyError }) }}
            </p>
          </div>
          <!-- end controls block -->
        </div>
        <!-- end .modal-v2__layout -->
      </template>

      <!-- First-run welcome tour. Three steps, no progress lost on
           skip. Renders above the modal body so the operator can still
           see what each step describes. -->
      <!-- Welcome tour. While open it owns the foreground: the modal body
           (header / controls / footer) is rendered ``inert`` above, so this
           is genuinely the active dialog — hence ``aria-modal="true"`` and
           the focus trap collapsing to the tour. Escape dismisses the tour,
           not the modal. -->
      <div
        v-if="tourActive"
        class="modal-v2__tour"
        role="dialog"
        aria-modal="true"
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
          <div
            v-else-if="tourStep === 2"
            class="modal-v2__tour-body"
            data-test="modal-v2-tour-step-2"
          >
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
  background: rgba(0, 0, 0, 0.6);
  padding: 1rem;
  overflow-y: auto;
}
.modal-v2 {
  /* Same surface as the app's other modals: slate-900 card with a
     slate-700 border (see PlotterSettingsModal). */
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 12px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6);
  padding: 1rem 1.5rem 1.25rem;
  /* Wide enough to fit the split layout — preview LEFT, controls
     RIGHT — without crowding either side. The grid responds to the
     viewport via min/max columns, so the modal isn't actually 1280
     px on a 1200-px-wide screen. */
  width: min(98vw, 1280px);
  max-height: 92vh;
  overflow-y: auto;
  font-family: system-ui, sans-serif;
  color: #f1f5f9;
}
/* Expert mode used to widen the modal here; the base ``.modal-v2``
   rule already maxes at 1280 px for both modes so the split has room
   either way. Kept the hook (now a plain ``is-expert`` class rather than
   ``:has(.modal-v2__expert)``, since the expert panel moved into its own
   scoped component) for future expert-only style overrides. */
.modal-v2.is-expert {
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
  /* Fixed height (header band + paddings subtracted from the modal's
     92vh ceiling; the footer is gone so the preview reclaims that space):
     the preview pane flexes inside it and gives up height to the ink
     chips below, so the colours stay readable without scrolling this
     column — notably in expert mode where the right column gets long. */
  height: calc(92vh - 7rem);
  overflow-y: auto;
}
/* The preview pane (child component root) absorbs the column's spare
   height; the sheet picker / caption / inks keep their natural size. */
.modal-v2__preview-block > .preview-pane {
  flex: 1 1 auto;
  min-height: 0;
}
.modal-v2__controls-block {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  min-width: 0;
}

/* The expert-mode controls drawer inside the right column. No own
   surface: the tabs and cards inside carry their slate-800 panels
   directly on the modal's slate-900 background, like the main view. */
/* Expert surface (tab strip + tab content) lives in EditorExpertPanel.vue. */

/* Narrow viewports (tablet portrait, phones): collapse to a single
   column so the operator can still reach every control. */
@media (max-width: 900px) {
  .modal-v2__layout {
    grid-template-columns: 1fr;
  }
  .modal-v2__preview-block {
    position: static;
    height: auto;
  }
}
/* Header (preflight/cost chips, mode toggle, close) lives in
   EditorHeader.vue. */

/* Preview pane, zoom/pan, sheet outline, view toggle, gesture hint
   and spinner all live in EditPreviewPane.vue now. */

/* Page navigator for multi-page documents. */
/* Page navigator (.modal-v2__pages) lives in EditorPageNav.vue; the ink
   swatch panel (.modal-v2__inks / .modal-v2__ink*) lives in
   EditorInkPanel.vue; assisted controls (intent grid + palette toggle +
   style stack) live in EditorAssistedPanel.vue. */

.error {
  color: #fca5a5;
  background: rgba(69, 10, 10, 0.4);
  border: 1px solid #b91c1c;
  padding: 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  margin: 0.5rem 0 0;
}
.modal-v2__noplacement {
  background: rgba(69, 26, 3, 0.4);
  border: 1px solid #b45309;
  color: #fde68a;
  padding: 0.65rem 0.85rem;
  border-radius: 8px;
  margin-bottom: 0.75rem;
  font-size: 0.875rem;
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
  font-size: 0.75rem;
  opacity: 0.85;
}

/* Outcome preamble — single-sentence context card with a dismiss
   button. Sky tint so it reads as informational, not warning. */
.modal-v2__preamble {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.55rem 0.75rem;
  background: rgba(8, 47, 73, 0.35);
  border: 1px solid #0369a1;
  border-radius: 8px;
  margin-bottom: 0.6rem;
  font-size: 0.75rem;
  color: #bae6fd;
}
.modal-v2__preamble p {
  margin: 0;
  flex: 1;
  line-height: 1.35;
}
.modal-v2__preamble-dismiss {
  border: none;
  background: transparent;
  color: #7dd3fc;
  font-size: 0.75rem;
  cursor: pointer;
  padding: 0.15rem 0.4rem;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
}
.modal-v2__preamble-dismiss:hover {
  background: rgba(8, 47, 73, 0.7);
  text-decoration: underline;
}
.modal-v2__preamble-dismiss:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}

/* The footer was removed: the single "save the print style" button and
   the close button live in EditorHeader.vue (right zone), alongside the
   sheet-format picker (left) and the assisted/expert toggle (center). */

/* Ink chips now act as visibility toggles. */
/* Onboarding tour overlay. Anchored to the modal so the preview
   underneath stays partly visible. */
.modal-v2__tour {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 1rem;
  background: rgba(2, 6, 23, 0.6);
  border-radius: 12px;
  z-index: 5;
  pointer-events: auto;
}
.modal-v2 {
  position: relative;
}
.modal-v2__tour-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 8px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
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
  font-size: 0.875rem;
  color: #f1f5f9;
}
.modal-v2__tour-progress {
  font-size: 0.6875rem;
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}
.modal-v2__tour-body strong {
  display: block;
  margin-bottom: 0.25rem;
  font-size: 0.875rem;
  color: #e2e8f0;
}
.modal-v2__tour-body p {
  margin: 0;
  font-size: 0.75rem;
  color: #cbd5e1;
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
  color: #94a3b8;
  font-size: 0.75rem;
  cursor: pointer;
  padding: 0.25rem 0.4rem;
}
.modal-v2__tour-skip:hover {
  text-decoration: underline;
}
.modal-v2__tour-next {
  border: 1px solid #059669;
  background: #059669;
  color: white;
  padding: 0.35rem 0.9rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
}
.modal-v2__tour-next:hover {
  background: #10b981;
}
.modal-v2__tour-next:focus-visible,
.modal-v2__tour-skip:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
</style>
