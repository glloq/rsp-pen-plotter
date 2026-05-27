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
import { resolveAlgorithmPolicy } from '../../domain/policy/client'
import type {
  Goal,
  PaletteMode,
  PolicyDecision,
  SourceKind,
} from '../../domain/policy/schemas'
import AssistantModeToggle from '../AssistantModeToggle.vue'
import StepperHeader from './StepperHeader.vue'

const props = defineProps<{
  initialSourceKind?: SourceKind
  initialPaletteMode?: PaletteMode
  availableColorsCount?: number
  imageMegapixels?: number | null
  isMonoPenMachine?: boolean
}>()

const emit = defineEmits<{
  (e: 'cancel'): void
  (e: 'confirm', decision: PolicyDecision): void
}>()

const STEPS: { id: string; label: string }[] = [
  { id: 'source', label: 'Source' },
  { id: 'intent', label: 'Intent' },
  { id: 'algorithm', label: 'Algorithme' },
  { id: 'colors', label: 'Couleurs' },
  { id: 'layers', label: 'Couches' },
  { id: 'preflight', label: 'Préflight' },
]

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
  if (activeIndex.value < STEPS.length - 1) activeIndex.value += 1
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

function confirm(): void {
  if (decision.value) emit('confirm', decision.value)
}
</script>

<template>
  <div class="modal-v2" role="dialog" aria-modal="true" aria-label="Préparer l'impression">
    <header class="modal-v2__header">
      <h2>Préparer l'impression</h2>
      <AssistantModeToggle />
      <button type="button" class="close" aria-label="Fermer" @click="emit('cancel')">×</button>
    </header>

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
            <strong>{{ opt === 'fast' ? 'Rapide' : opt === 'balanced' ? 'Équilibré' : 'Qualité' }}</strong>
            <span>
              {{ opt === 'fast' ? 'preview brouillon, algos économes' :
                 opt === 'balanced' ? 'compromis temps / rendu' :
                 'preview final, algos plus chers' }}
            </span>
          </button>
        </div>
      </div>

      <!-- 3. Algorithm recommendation -->
      <div v-else-if="activeIndex === 2" data-test="step-algorithm">
        <div v-if="resolving">Calcul de la recommandation…</div>
        <div v-else-if="resolveError" class="error">
          Erreur resolver : {{ resolveError }}. Les défauts statiques seront utilisés.
        </div>
        <div v-else-if="decision">
          <p>
            Algo recommandé&nbsp;: <strong data-test="recommended-algo">{{ decision.default_algorithm }}</strong>
            (<span>{{ decision.quality_tier }}</span>)
          </p>
          <details open>
            <summary>Pourquoi ce choix&nbsp;?</summary>
            <ul>
              <li v-for="r in decision.reasoning" :key="r.rule">
                <code>{{ r.rule }}</code> — {{ r.description }}
              </li>
            </ul>
          </details>
          <p v-if="decision.fallback_chain.length">
            Fallbacks&nbsp;: {{ decision.fallback_chain.join(' → ') }}
          </p>
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
        <p>Les couches seront générées par l'algorithme recommandé.</p>
        <p>
          La gestion fine des passes par couche est exposée dans
          <strong>Layer Inspector</strong> (étape C.3).
        </p>
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
      <button type="button" :disabled="activeIndex === 0" @click="previous">Précédent</button>
      <button
        v-if="activeIndex < STEPS.length - 1"
        type="button"
        :disabled="resolving"
        @click="next"
      >
        Suivant
      </button>
      <button
        v-else
        type="button"
        :disabled="!decision"
        data-test="confirm-button"
        @click="confirm"
      >
        Générer
      </button>
    </footer>
  </div>
</template>

<style scoped>
.modal-v2 {
  background: white;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  padding: 1rem 1.5rem;
  max-width: 720px;
  font-family: system-ui, sans-serif;
}
.modal-v2__header {
  display: flex;
  align-items: center;
  gap: 1rem;
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
</style>
