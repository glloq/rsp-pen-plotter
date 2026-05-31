<script setup lang="ts">
// Compare Mode A/B (roadmap C.5 / audit #7 §4 + audit #1 §6).
//
// Side-by-side comparison of two preview candidates (typically the
// resolver recommendation versus an operator-tuned variant). Renders
// each candidate's SVG preview, the metrics card next to it, and a
// diff column highlighting which side wins on each axis.
//
// Overlays (pen-up travel heatmap, path density, bounds, curvature
// stress) are surfaced as a toggle row; the actual rendering of
// those overlays is deferred to a dedicated PR — this component
// owns the UX seam so the rest of the modal V2 can already opt into
// the compare workflow.

import { computed } from 'vue'
import type { PolicyDecision } from '../../domain/policy/schemas'

export interface CandidateMetrics {
  /** Estimated draw time in seconds. */
  est_time_s?: number
  /** Total ink length in millimetres. */
  draw_length_mm?: number
  /** Pen-up travel length in millimetres. */
  pen_up_length_mm?: number
  /** Number of operator swaps. */
  swap_count?: number
}

export interface Candidate {
  id: string
  label: string
  /** Raw SVG preview markup. Already sanitized by the caller. */
  svg: string
  decision: PolicyDecision | null
  metrics: CandidateMetrics
}

const props = defineProps<{
  a: Candidate
  b: Candidate
  overlays?: readonly OverlayKey[]
}>()

export type OverlayKey = 'penup_heatmap' | 'path_density' | 'bounds' | 'curvature'

const emit = defineEmits<{
  (e: 'pick-winner', candidateId: string): void
  (e: 'toggle-overlay', key: OverlayKey): void
}>()

// ``wired`` marks overlays the renderer can actually draw today. The
// others need geometry the resolver doesn't expose yet (G.1 follow-up);
// keep them in the row so operators discover the planned axes, but
// disable the checkbox so a click can't silently do nothing.
const overlayDefs: { key: OverlayKey; label: string; wired: boolean }[] = [
  { key: 'penup_heatmap', label: 'Pen-up heatmap', wired: false },
  { key: 'path_density', label: 'Densité de trait', wired: false },
  { key: 'bounds', label: 'Marges / bounds', wired: true },
  { key: 'curvature', label: 'Stress de courbure', wired: false },
]

const enabledOverlays = computed(() => new Set<OverlayKey>(props.overlays ?? []))

// Parse the ``viewBox`` attribute of a sanitized SVG string. Returns
// ``null`` when the attribute is missing or malformed; the overlay
// renderer falls back to "no overlay" rather than guessing dimensions.
function parseViewBox(svg: string): { x: number; y: number; w: number; h: number } | null {
  const m = svg.match(/viewBox\s*=\s*["']([^"']+)["']/)
  if (!m) return null
  const parts = m[1]!
    .trim()
    .split(/[\s,]+/)
    .map(Number)
  if (parts.length !== 4 || parts.some((n) => !Number.isFinite(n))) return null
  return { x: parts[0]!, y: parts[1]!, w: parts[2]!, h: parts[3]! }
}

function fmtMm(v?: number): string {
  if (v === undefined) return '—'
  if (v < 100) return `${v.toFixed(1)} mm`
  if (v < 10_000) return `${(v / 10).toFixed(0)} cm`
  return `${(v / 1_000).toFixed(1)} m`
}

function fmtTime(s?: number): string {
  if (s === undefined) return '—'
  if (s < 60) return `${s.toFixed(1)} s`
  const m = Math.floor(s / 60)
  const r = (s % 60).toFixed(0)
  return `${m} min ${r} s`
}

interface DiffRow {
  label: string
  a: string
  b: string
  winner: 'a' | 'b' | null
}

function diffNum(
  label: string,
  a: number | undefined,
  b: number | undefined,
  fmt: (n?: number) => string,
  lowerIsBetter = true,
): DiffRow {
  if (a === undefined || b === undefined) {
    return { label, a: fmt(a), b: fmt(b), winner: null }
  }
  let winner: 'a' | 'b' | null
  if (a === b) winner = null
  else if (lowerIsBetter) winner = a < b ? 'a' : 'b'
  else winner = a > b ? 'a' : 'b'
  return { label, a: fmt(a), b: fmt(b), winner }
}

const diff = computed<DiffRow[]>(() => [
  diffNum('Temps estimé', props.a.metrics.est_time_s, props.b.metrics.est_time_s, fmtTime),
  diffNum('Longueur tracé', props.a.metrics.draw_length_mm, props.b.metrics.draw_length_mm, fmtMm),
  diffNum(
    'Pen-up travel',
    props.a.metrics.pen_up_length_mm,
    props.b.metrics.pen_up_length_mm,
    fmtMm,
  ),
  diffNum('Changements stylo', props.a.metrics.swap_count, props.b.metrics.swap_count, (n) =>
    n === undefined ? '—' : String(n),
  ),
])
</script>

<template>
  <section class="compare" data-test="compare-view">
    <header>
      <h3>Comparer A / B</h3>
      <fieldset class="overlay-row" data-test="compare-overlay-row">
        <legend>Overlays</legend>
        <label
          v-for="opt in overlayDefs"
          :key="opt.key"
          :data-test="`overlay-${opt.key}`"
          :class="{ 'overlay-pending': !opt.wired }"
          :title="opt.wired ? undefined : 'Pas encore implémenté'"
        >
          <input
            type="checkbox"
            :checked="enabledOverlays.has(opt.key)"
            :disabled="!opt.wired"
            @change="emit('toggle-overlay', opt.key)"
          />
          {{ opt.label }}{{ opt.wired ? '' : ' (bientôt)' }}
        </label>
      </fieldset>
    </header>

    <div class="grid">
      <article
        v-for="cand in [a, b]"
        :key="cand.id"
        class="candidate"
        :data-test="`candidate-${cand.id}`"
      >
        <h4>
          {{ cand.label }}
          <small v-if="cand.decision">— {{ cand.decision.default_algorithm }}</small>
        </h4>
        <div class="preview-frame" :data-overlays="props.overlays?.join(' ') ?? ''">
          <!-- v-html is acceptable here because the caller is required
               to sanitize the SVG before passing it in (the modal V2
               already DOMPurify's preview output). -->
          <!-- eslint-disable vue/no-v-html -->
          <div class="preview" v-html="cand.svg" />
          <!-- eslint-enable vue/no-v-html -->

          <!-- Bounds overlay (G.1 wire). The other three overlays
               (penup_heatmap / path_density / curvature) need
               geometry the resolver doesn't expose yet — they remain
               UX-only chips. Bounds is computable from the SVG
               viewBox alone so it ships now. -->
          <svg
            v-if="enabledOverlays.has('bounds') && parseViewBox(cand.svg)"
            class="overlay overlay-bounds"
            :viewBox="`${parseViewBox(cand.svg)!.x} ${parseViewBox(cand.svg)!.y} ${parseViewBox(cand.svg)!.w} ${parseViewBox(cand.svg)!.h}`"
            preserveAspectRatio="xMidYMid meet"
            :data-test="`overlay-bounds-${cand.id}`"
          >
            <rect
              :x="parseViewBox(cand.svg)!.x"
              :y="parseViewBox(cand.svg)!.y"
              :width="parseViewBox(cand.svg)!.w"
              :height="parseViewBox(cand.svg)!.h"
              fill="none"
              stroke="#1f6feb"
              stroke-width="2"
              stroke-dasharray="6 4"
              vector-effect="non-scaling-stroke"
            />
          </svg>

          <ul v-if="enabledOverlays.size" class="overlay-stub">
            <li v-for="k in overlays" :key="k" :class="{ wired: k === 'bounds' }">
              {{ k }}{{ k === 'bounds' ? '' : ' (stub)' }}
            </li>
          </ul>
        </div>
        <button type="button" :data-test="`pick-${cand.id}`" @click="emit('pick-winner', cand.id)">
          Choisir
        </button>
      </article>
    </div>

    <table class="metrics" data-test="metrics-table">
      <thead>
        <tr>
          <th>Métrique</th>
          <th>{{ a.label }}</th>
          <th>{{ b.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in diff" :key="row.label">
          <th scope="row">{{ row.label }}</th>
          <td :class="{ winner: row.winner === 'a' }">{{ row.a }}</td>
          <td :class="{ winner: row.winner === 'b' }">{{ row.b }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.compare {
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 0.75rem 1rem;
  background: white;
  font-family: system-ui, sans-serif;
}
.preview-frame {
  position: relative;
}
.preview-frame .overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.overlay-stub li.wired {
  color: #1f6feb;
}
header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.5rem;
}
h3 {
  margin: 0;
  font-size: 1rem;
}
.overlay-row {
  border: none;
  padding: 0;
  margin: 0;
  display: flex;
  gap: 0.75rem;
  font-size: 0.85rem;
  flex-wrap: wrap;
}
.overlay-row legend {
  font-weight: 600;
  margin-right: 0.5rem;
}
.overlay-row label.overlay-pending {
  color: #888;
  cursor: not-allowed;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}
.candidate {
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  padding: 0.5rem;
}
.candidate h4 {
  margin: 0 0 0.25rem 0;
  font-size: 0.9rem;
}
.candidate h4 small {
  color: #555;
  font-weight: normal;
}
.preview-frame {
  position: relative;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  padding: 0.25rem;
  border-radius: 3px;
  min-height: 8rem;
}
.preview :deep(svg) {
  width: 100%;
  height: auto;
  display: block;
}
.overlay-stub {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  list-style: none;
  padding: 0.25rem 0.5rem;
  margin: 0;
  background: rgba(31, 111, 235, 0.85);
  color: white;
  font-size: 0.7rem;
  border-radius: 3px;
}
.metrics {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
  margin-top: 0.75rem;
}
.metrics th,
.metrics td {
  text-align: left;
  padding: 0.25rem 0.5rem;
  border-bottom: 1px solid #f0f0f0;
}
.metrics td.winner {
  background: #e6f4ea;
  color: #1b5e20;
  font-weight: 600;
}
</style>
