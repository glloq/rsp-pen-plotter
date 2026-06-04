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
import { useAvailableColorsStore } from '../../stores/availableColors'
import { usePaletteSourceStore } from '../../stores/paletteSource'
import { useUiStore } from '../../stores/ui'
import { useJobStore } from '../../stores/job'
import AssistantModeToggle from '../AssistantModeToggle.vue'

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
}>()

const emit = defineEmits<{
  (e: 'cancel'): void
  (e: 'confirm', decision: PolicyDecision): void
}>()

const { t } = useI18n()
const ui = useUiStore()
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

// What the preview pane shows: the adapted render once available, else
// the original placement SVG as an immediate placeholder.
const shownSvg = computed(() => renderedSvg.value ?? props.previewSvg ?? null)

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
    return {
      layerId: layer.layer_id,
      hex,
      name: inventoryNameByHex.value.get(hex.toLowerCase()) ?? hex,
      isFallback: !assigned,
    }
  })
})

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
        <AssistantModeToggle />
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
          <div class="modal-v2__preview-viewport" :style="contentStyle">
            <!-- v-html: caller (App.vue) passes already-sanitized SVG,
                 and ``previewAlgorithmOnAllLayers`` returns backend-
                 rendered SVG from the same trusted pipeline. -->
            <!-- eslint-disable-next-line vue/no-v-html -->
            <div
              v-if="shownSvg"
              class="modal-v2__preview-svg"
              :class="{ 'is-stale': previewLoading }"
              data-test="modal-v2-preview-svg"
              v-html="shownSvg"
            />
          </div>

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

        <!-- File caption. -->
        <p v-if="props.sourceName" class="modal-v2__caption" data-test="modal-v2-context">
          <span class="modal-v2__filename">{{ props.sourceName }}</span>
          <span v-if="props.layers && props.layers.length" class="modal-v2__counts">
            · {{ t('v2.modal.layerCount', { count: props.layers.length }) }}
          </span>
        </p>

        <!-- Per-layer ink swatches: which colours from the
             magazine / inventory pool the preview is using, in draw
             order. A fallback badge flags layers that fell back to the
             segmentation centroid because nothing in the pool matched. -->
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
              class="modal-v2__ink"
              :class="{ 'is-fallback': ink.isFallback }"
              :title="ink.isFallback ? t('v2.modal.inkFallback', { hex: ink.hex }) : ink.name"
            >
              <span
                class="modal-v2__ink-swatch"
                :style="{ backgroundColor: ink.hex }"
                aria-hidden="true"
              />
              <span class="modal-v2__ink-name">{{ ink.name }}</span>
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
      </template>

      <footer class="modal-v2__footer">
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
      </footer>
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
</style>
