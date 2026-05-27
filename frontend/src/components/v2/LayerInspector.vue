<script setup lang="ts">
// Layer Inspector (roadmap C.3 / audit #7 §4).
//
// Renders one row per layer in execution order with the cost the
// operator cares about: ink length, slot assignment, pause policy.
// Pure / props-driven so it can be embedded in the modal V2 or
// dropped as a side panel without state coupling. Phase B/C will
// hook the IR-derived metrics (PathPlanIR.total_draw_length_mm,
// pen_up_length_mm) once the resolver feeds them through; for now
// we surface the existing total_length_mm from the v0.1 LayerInfo
// shape so the panel is useful immediately.

import { computed } from 'vue'
import type { LayerInfo } from '../../api/client'

const props = defineProps<{
  layers: readonly LayerInfo[]
  totalDrawLengthMm?: number
  totalPenUpLengthMm?: number
}>()

const ordered = computed(() =>
  [...props.layers].sort((a, b) => a.draw_order - b.draw_order),
)

const totalDraw = computed(() =>
  props.totalDrawLengthMm ??
  ordered.value.reduce((acc, l) => acc + (l.total_length_mm ?? 0), 0),
)

// Number of swaps the operator is going to perform: every transition
// to a layer whose slot differs from the previous one, **modulated**
// by the layer's pause_before policy. ``never`` suppresses the swap
// even if the slot changed; ``always`` forces one regardless.
const swapCount = computed(() => {
  let prevSlot: number | null = null
  let count = 0
  for (const layer of ordered.value) {
    if (layer.pause_before === 'never') {
      prevSlot = layer.target_pen_slot
      continue
    }
    if (layer.pause_before === 'always') {
      count += 1
    } else if (prevSlot !== null && layer.target_pen_slot !== prevSlot) {
      count += 1
    }
    prevSlot = layer.target_pen_slot
  }
  return count
})

function fmtMm(value: number): string {
  if (value < 100) return `${value.toFixed(1)} mm`
  if (value < 10_000) return `${(value / 10).toFixed(0)} cm`
  return `${(value / 1_000).toFixed(1)} m`
}
</script>

<template>
  <section class="layer-inspector" data-test="layer-inspector">
    <header>
      <h3>Inspecteur de couches</h3>
      <span class="summary">
        {{ ordered.length }} couches · {{ fmtMm(totalDraw) }} de tracé ·
        {{ swapCount }} changement(s) stylo
      </span>
    </header>
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Couche</th>
          <th>Slot</th>
          <th>Pause</th>
          <th>Longueur</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(layer, i) in ordered" :key="layer.layer_id" :data-test="`layer-row-${layer.layer_id}`">
          <td>{{ i + 1 }}</td>
          <td>
            <span class="dot" :style="{ background: layer.assigned_color_hex ?? layer.source_color }" />
            {{ layer.color_label ?? layer.source_color }}
          </td>
          <td>
            <span v-if="layer.target_pen_slot !== null">#{{ layer.target_pen_slot }}</span>
            <span v-else class="muted">—</span>
          </td>
          <td>
            <span :class="`pause pause-${layer.pause_before}`">{{ layer.pause_before }}</span>
          </td>
          <td>{{ fmtMm(layer.total_length_mm ?? 0) }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.layer-inspector {
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 0.75rem 1rem;
  font-family: system-ui, sans-serif;
  font-size: 0.875rem;
}
header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}
h3 {
  margin: 0;
  font-size: 1rem;
}
.summary {
  color: #555;
  font-size: 0.85rem;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th,
td {
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid #f0f0f0;
  text-align: left;
}
th {
  font-weight: 600;
  color: #444;
}
.dot {
  display: inline-block;
  width: 0.75rem;
  height: 0.75rem;
  border-radius: 50%;
  margin-right: 0.35rem;
  vertical-align: middle;
  border: 1px solid rgba(0, 0, 0, 0.1);
}
.muted {
  color: #999;
}
.pause {
  font-size: 0.75rem;
  padding: 0 0.4rem;
  border-radius: 999px;
  border: 1px solid currentColor;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.pause-auto {
  color: #555;
}
.pause-always {
  color: #b71c1c;
}
.pause-never {
  color: #2e7d32;
}
</style>
