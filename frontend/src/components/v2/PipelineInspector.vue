<script setup lang="ts">
// Pipeline Inspector (roadmap C.3 / audit #7 §4).
//
// Renders the chain of decisions the resolver made to turn a source
// into a printable program: source kind, segmentation method, algorithm,
// quality tier, fallback chain, hard constraints.
//
// Pure / props-driven; designed to sit next to LayerInspector either in
// a side panel or inline inside the modal V2 Algorithm step.

import type { PolicyDecision } from '../../domain/policy/schemas'

defineProps<{
  decision: PolicyDecision | null
  sourceKind?: string
}>()
</script>

<template>
  <section class="pipeline-inspector" data-test="pipeline-inspector">
    <header>
      <h3>Inspecteur de pipeline</h3>
    </header>
    <div v-if="!decision" class="empty" data-test="pipeline-empty">
      Aucune décision résolue pour l'instant. Termine l'étape « Intent ».
    </div>
    <ol v-else class="chain">
      <li>
        <strong>Source</strong>
        <span>{{ sourceKind ?? 'inconnu' }}</span>
      </li>
      <li>
        <strong>Segmentation</strong>
        <span data-test="pipeline-segmentation">{{ decision.segmentation_method }}</span>
      </li>
      <li>
        <strong>Algorithme</strong>
        <span data-test="pipeline-algorithm">{{ decision.default_algorithm }}</span>
        <span class="tier">{{ decision.quality_tier }}</span>
      </li>
      <li v-if="decision.fallback_chain.length">
        <strong>Fallbacks</strong>
        <span>{{ decision.fallback_chain.join(' → ') }}</span>
      </li>
      <li v-if="decision.hard_constraints_applied.length" class="constraints">
        <strong>Contraintes appliquées</strong>
        <ul>
          <li
            v-for="c in decision.hard_constraints_applied"
            :key="c.constraint"
            :data-test="`pipeline-constraint-${c.constraint}`"
          >
            <code>{{ c.constraint }}</code> — {{ c.description }}
          </li>
        </ul>
      </li>
    </ol>
    <details v-if="decision" class="options">
      <summary>Paramètres par défaut</summary>
      <pre><code>{{ JSON.stringify(decision.default_options, null, 2) }}</code></pre>
    </details>
  </section>
</template>

<style scoped>
.pipeline-inspector {
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 0.75rem 1rem;
  font-family: system-ui, sans-serif;
  font-size: 0.875rem;
}
header {
  margin-bottom: 0.5rem;
}
h3 {
  margin: 0;
  font-size: 1rem;
}
.empty {
  color: #777;
  font-style: italic;
  padding: 0.75rem 0;
}
.chain {
  list-style: none;
  padding: 0;
  margin: 0;
}
.chain li {
  display: grid;
  grid-template-columns: 9rem 1fr auto;
  align-items: baseline;
  padding: 0.25rem 0;
  gap: 0.5rem;
}
.chain li.constraints {
  grid-template-columns: 9rem 1fr;
}
.chain li ul {
  margin: 0;
  padding-left: 1rem;
}
.tier {
  background: #eef4ff;
  color: #1f6feb;
  padding: 0 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
}
.options {
  margin-top: 0.5rem;
}
.options summary {
  cursor: pointer;
  color: #555;
}
pre {
  background: #fafafa;
  border: 1px solid #eee;
  padding: 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  overflow-x: auto;
}
code {
  font-family: ui-monospace, Menlo, monospace;
}
</style>
