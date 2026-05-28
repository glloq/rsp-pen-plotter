<script setup lang="ts">
// Modal V2 — six-step decision flow (roadmap C.2 / audit #7 §3).
//
// Lives **in parallel** with the existing EditModal.vue and is gated
// by the `modalV2` feature flag (toggle in expert mode or via
// ``?flag.modalV2=1`` for QA). When the flag is off, callers route
// through the v0.1 modal as before. The two modals share no state
// today — the v0.2 modal stores its draft in local refs and only
// calls into the backend via /policy/resolve.
//
// Steps:
//   1. Source Prep      — confirm/override the detected source_kind
//   2. Intent           — fast / balanced / quality picker
//   3. Algorithm        — recommendation from /policy/resolve + reasoning
//   4. Colours / Pens   — palette source toggle (machine_only / free)
//   5. Layers / Passes  — passes and per-layer overrides placeholder
//   6. Preflight        — risk indicators + ETA + "Generate"

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { LayerInfo } from '../../api/client'
import { useKeyboardShortcuts } from '../../composables/useKeyboardShortcuts'
import { resolveAlgorithmPolicy } from '../../domain/policy/client'
import type {
  Goal,
  PaletteMode,
  PolicyDecision,
  SourceKind,
} from '../../domain/policy/schemas'
import { useUiModeStore } from '../../stores/uiMode'
import AssistantModeToggle from '../AssistantModeToggle.vue'
import LayerInspector from './LayerInspector.vue'
import PipelineInspector from './PipelineInspector.vue'
import StepperHeader from './StepperHeader.vue'

const props = defineProps<{
  initialSourceKind?: SourceKind
  initialPaletteMode?: PaletteMode
  availableColorsCount?: number
  imageMegapixels?: number | null
  isMonoPenMachine?: boolean
  /** Layers from the currently-selected placement. Empty when the
   *  operator hasn't picked one yet — the Couches step then falls
   *  back to an explanatory placeholder. */
  layers?: readonly LayerInfo[]
  /** Source file name from the active placement — surfaced in the
   *  context bar so the operator can see what they're editing. */
  sourceName?: string
  /** Sanitized SVG preview from the active placement; rendered as a
   *  small thumbnail in the context bar. */
  previewSvg?: string
}>()

const emit = defineEmits<{
  (e: 'cancel'): void
  (e: 'confirm', decision: PolicyDecision): void
  (e: 'open-v1'): void
}>()

const { t } = useI18n()

const STEPS = computed<{ id: string; label: string }[]>(() => [
  { id: 'source', label: t('v2.modal.stepSource') },
  { id: 'intent', label: t('v2.modal.stepIntent') },
  { id: 'algorithm', label: t('v2.modal.stepAlgorithm') },
  { id: 'colors', label: t('v2.modal.stepColors') },
  { id: 'layers', label: t('v2.modal.stepLayers') },
  { id: 'preflight', label: t('v2.modal.stepPreflight') },
])

const activeIndex = ref(0)

const sourceKind = ref<SourceKind>(props.initialSourceKind ?? 'bitmap_photo')
const goal = ref<Goal>('fast')
const paletteMode = ref<PaletteMode>(props.initialPaletteMode ?? 'machine_only')

const decision = ref<PolicyDecision | null>(null)
const resolving = ref(false)
const resolveError = ref<string | null>(null)

async function next(): Promise<void> {
  if (activeIndex.value === 1) {
    // Leaving Intent → ask the resolver for a recommendation.
    resolving.value = true
    resolveError.value = null
    try {
      decision.value = await resolveAlgorithmPolicy({
        source_kind: sourceKind.value,
        goal: goal.value,
        palette_mode: paletteMode.value,
        available_colors_count: props.availableColorsCount ?? 1,
        image_megapixels: props.imageMegapixels ?? null,
        layer_count_estimate: 1,
        is_mono_pen_machine: Boolean(props.isMonoPenMachine),
      })
    } catch (err) {
      resolveError.value = (err as Error).message
    } finally {
      resolving.value = false
    }
  }
  if (activeIndex.value < STEPS.value.length - 1) activeIndex.value += 1
}

function previous(): void {
  if (activeIndex.value > 0) activeIndex.value -= 1
}

function jump(i: number): void {
  if (i <= activeIndex.value) activeIndex.value = i
}

const risks = computed<string[]>(() => {
  const out: string[] = []
  if (decision.value?.hard_constraints_applied.length) {
    for (const c of decision.value.hard_constraints_applied) out.push(c.description)
  }
  return out
})

// True when there's an active placement to apply the decision to.
// We use ``previewSvg`` rather than ``layers`` because vector
// sources may have zero LayerInfo entries (the algorithm wizard
// still makes sense for them). The Generate button is locked when
// this is false so the operator doesn't get a silent no-op.
const hasPlacement = computed(() => Boolean(props.previewSvg || props.sourceName))

function confirm(): void {
  if (!hasPlacement.value || !decision.value) return
  emit('confirm', decision.value)
}

// Progressive disclosure (roadmap C.1 + C.2). In expert mode the
// operator can flip into "advanced details" (level 2) which reveals
// the reasoning chain, fallback list, PipelineInspector, and the raw
// default-options JSON. Assisted mode stays at level 1 to keep the
// step body minimal.
const uiMode = useUiModeStore()
const showAdvanced = computed(
  () => uiMode.isExpert && uiMode.expertDisclosureLevel === 2,
)
function toggleAdvanced(): void {
  uiMode.setExpertDisclosureLevel(uiMode.expertDisclosureLevel === 2 ? 1 : 2)
}

// Global modal shortcuts (Ctrl/Cmd+Enter = Suivant, Ctrl/Cmd+Backspace
// = Précédent). The composable ignores keystrokes targeting inputs so
// the select / radios on each step continue to work normally.
useKeyboardShortcuts([
  {
    id: 'modal.next',
    handler: () => {
      if (resolving.value) return
      if (activeIndex.value < STEPS.value.length - 1) void next()
      else if (decision.value) confirm()
    },
  },
  { id: 'modal.previous', handler: previous },
])
</script>

<template>
  <!-- Backdrop: fixed full-screen, semi-transparent, clicking outside
       the card emits cancel just like the v1 modal does. -->
  <div
    class="modal-v2__backdrop"
    role="presentation"
    data-test="modal-v2-backdrop"
    @click.self="emit('cancel')"
  >
    <div
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
          class="open-v1"
          :title="t('v2.modal.openV1')"
          data-test="modal-v2-open-v1"
          @click="emit('open-v1')"
        >
          {{ t('v2.modal.openV1') }}
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

      <!-- Context bar — file name + tiny preview so the wizard isn't
           floating in the void. Hidden when no placement is selected
           (operator opened the modal pre-upload). -->
      <div
        v-if="props.sourceName || props.previewSvg"
        class="modal-v2__context"
        data-test="modal-v2-context"
      >
        <div
          v-if="props.previewSvg"
          class="modal-v2__thumb"
          aria-hidden="true"
        >
          <!-- v-html: caller (App.vue) passes ``placement.svg`` which
               was already sanitized by the upload pipeline. -->
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div v-html="props.previewSvg" />
        </div>
        <div class="modal-v2__context-meta">
          <p v-if="props.sourceName" class="modal-v2__filename">
            {{ props.sourceName }}
          </p>
          <p v-if="props.layers && props.layers.length" class="modal-v2__counts">
            {{ t('v2.modal.layerCount', { count: props.layers.length }) }}
          </p>
        </div>
      </div>
      <div
        v-else
        class="modal-v2__noplacement"
        data-test="modal-v2-no-placement"
      >
        {{ t('v2.modal.noPlacement') }}
      </div>

      <StepperHeader :steps="STEPS" :active-index="activeIndex" @jump="jump" />

      <section class="modal-v2__body">
      <!-- 1. Source Prep -->
      <div v-if="activeIndex === 0" data-test="step-source">
        <p>Détection du type de source. L'algorithme par défaut s'adaptera.</p>
        <label>
          Type
          <select v-model="sourceKind" data-test="source-kind-select">
            <option value="bitmap_photo">Bitmap — photo</option>
            <option value="bitmap_illustration">Bitmap — illustration</option>
            <option value="vector_svg">Vecteur — SVG</option>
            <option value="pdf_doc">Document PDF</option>
            <option value="text_typography">Texte / typographie</option>
          </select>
        </label>
      </div>

      <!-- 2. Intent -->
      <div v-else-if="activeIndex === 1" data-test="step-intent">
        <p>Quel est ton objectif&nbsp;?</p>
        <div class="intent-grid">
          <button
            v-for="opt in (['fast', 'balanced', 'quality'] as const)"
            :key="opt"
            type="button"
            :class="{ active: goal === opt }"
            :data-test="`intent-${opt}`"
            @click="goal = opt"
          >
            <strong>{{ t(`v2.intent.${opt}`) }}</strong>
          </button>
        </div>
      </div>

      <!-- 3. Algorithm recommendation -->
      <div v-else-if="activeIndex === 2" data-test="step-algorithm">
        <div v-if="resolving">{{ t('v2.modal.resolving') }}</div>
        <div v-else-if="resolveError" class="error">
          {{ t('v2.modal.resolverError', { message: resolveError }) }}
        </div>
        <div v-else-if="decision">
          <p>
            Algo recommandé&nbsp;: <strong data-test="recommended-algo">{{ decision.default_algorithm }}</strong>
            (<span>{{ decision.quality_tier }}</span>)
          </p>
          <button
            v-if="uiMode.isExpert"
            type="button"
            class="disclosure-toggle"
            data-test="disclosure-toggle"
            :aria-pressed="showAdvanced"
            @click="toggleAdvanced"
          >
            {{ showAdvanced ? 'Masquer les détails avancés' : 'Afficher les détails avancés' }}
          </button>
          <template v-if="showAdvanced">
            <details open>
              <summary>{{ t('v2.modal.why') }}</summary>
              <ul>
                <li v-for="r in decision.reasoning" :key="r.rule">
                  <code>{{ r.rule }}</code> — {{ r.description }}
                </li>
              </ul>
            </details>
            <p v-if="decision.fallback_chain.length">
              Fallbacks&nbsp;: {{ decision.fallback_chain.join(' → ') }}
            </p>
            <PipelineInspector :decision="decision" :source-kind="sourceKind" />
          </template>
          <details v-else>
            <summary data-test="why-summary-collapsed">{{ t('v2.modal.why') }}</summary>
            <ul>
              <li v-for="r in decision.reasoning.slice(0, 1)" :key="r.rule">
                {{ r.description }}
              </li>
            </ul>
          </details>
        </div>
      </div>

      <!-- 4. Colours -->
      <div v-else-if="activeIndex === 3" data-test="step-colors">
        <p>Source de palette&nbsp;:</p>
        <label>
          <input v-model="paletteMode" type="radio" value="machine_only" />
          Magazine machine uniquement (recommandé)
        </label>
        <label>
          <input v-model="paletteMode" type="radio" value="free" />
          Palette libre (mode expert)
        </label>
      </div>

      <!-- 5. Layers -->
      <div v-else-if="activeIndex === 4" data-test="step-layers">
        <LayerInspector v-if="props.layers && props.layers.length" :layers="props.layers" />
        <div v-else class="layers-empty">
          <p>Les couches seront générées par l'algorithme recommandé.</p>
          <p class="muted">
            L'inspecteur de couches s'affichera ici dès qu'un placement actif aura été
            sélectionné.
          </p>
        </div>
      </div>

      <!-- 6. Preflight -->
      <div v-else-if="activeIndex === 5" data-test="step-preflight">
        <h3>Récapitulatif</h3>
        <ul>
          <li>Source&nbsp;: {{ sourceKind }}</li>
          <li>Intent&nbsp;: {{ goal }}</li>
          <li>Algo&nbsp;: <strong>{{ decision?.default_algorithm }}</strong></li>
          <li>Quality tier&nbsp;: {{ decision?.quality_tier }}</li>
          <li>Palette&nbsp;: {{ paletteMode }}</li>
        </ul>
        <div v-if="risks.length" class="risk-list" data-test="risk-list">
          <strong>Points d'attention&nbsp;:</strong>
          <ul>
            <li v-for="r in risks" :key="r">{{ r }}</li>
          </ul>
        </div>
      </div>
    </section>

    <footer class="modal-v2__footer">
      <button type="button" :disabled="activeIndex === 0" @click="previous">
        {{ t('v2.modal.previous') }}
      </button>
      <button
        v-if="activeIndex < STEPS.length - 1"
        type="button"
        :disabled="resolving"
        @click="next"
      >
        {{ t('v2.modal.next') }}
      </button>
      <button
        v-else
        type="button"
        :disabled="!decision || !hasPlacement"
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
/* Modal V2 chrome — matches the v1 EditModal pattern: full-screen
 * fixed backdrop with a centered card. Without this the component
 * would render inline in App.vue's flex flow and end up at the
 * bottom of the page (operator-reported bug).
 */
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
  padding: 1rem 1.5rem;
  width: min(96vw, 760px);
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
.open-v1 {
  border: 1px solid #cbd5e1;
  background: #f8fafc;
  color: #1e293b;
  padding: 0.25rem 0.6rem;
  border-radius: 4px;
  font-size: 0.8rem;
  cursor: pointer;
}
.open-v1:hover {
  background: #e2e8f0;
}
.modal-v2__context {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  margin-bottom: 0.75rem;
}
.modal-v2__thumb {
  width: 80px;
  height: 60px;
  overflow: hidden;
  background: white;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal-v2__thumb :deep(svg) {
  max-width: 100%;
  max-height: 100%;
}
.modal-v2__context-meta {
  flex: 1;
  min-width: 0;
}
.modal-v2__filename {
  margin: 0;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.85rem;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.modal-v2__counts {
  margin: 0.15rem 0 0;
  font-size: 0.75rem;
  color: #64748b;
}
.modal-v2__noplacement {
  background: #fff4cc;
  border: 1px solid #d9b800;
  color: #5b4a00;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  margin-bottom: 0.75rem;
  font-size: 0.85rem;
}
.modal-v2__body {
  min-height: 12rem;
  margin-bottom: 1rem;
}
.modal-v2__footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
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
  padding: 0.75rem;
  border: 1px solid #d0d0d0;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  text-align: left;
}
.intent-grid button.active {
  border-color: #1f6feb;
  background: #eef4ff;
}
.error {
  color: #b71c1c;
  background: #fdecea;
  padding: 0.5rem;
  border-radius: 4px;
}
.risk-list {
  background: #fff4cc;
  border: 1px solid #d9b800;
  color: #5b4a00;
  padding: 0.5rem 0.75rem;
  border-radius: 4px;
  margin-top: 0.5rem;
}
.layers-empty .muted {
  color: #777;
  font-size: 0.85rem;
}
.disclosure-toggle {
  margin: 0.25rem 0 0.5rem;
  padding: 0.2rem 0.6rem;
  border: 1px solid #d0d0d0;
  border-radius: 4px;
  background: #fafafa;
  font-size: 0.8rem;
  cursor: pointer;
}
.disclosure-toggle[aria-pressed='true'] {
  background: #eef4ff;
  border-color: #1f6feb;
}
</style>
