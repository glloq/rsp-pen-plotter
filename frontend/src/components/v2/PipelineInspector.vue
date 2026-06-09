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
  border: 1px solid #334155;
  background: #1e293b;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  font-size: 0.875rem;
  color: #f1f5f9;
}
header {
  margin-bottom: 0.5rem;
}
h3 {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
}
.empty {
  color: #94a3b8;
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
  background: rgba(2, 44, 34, 0.6);
  color: #6ee7b7;
  padding: 0 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
}
.options {
  margin-top: 0.5rem;
}
.options summary {
  cursor: pointer;
  color: #94a3b8;
}
pre {
  background: #0f172a;
  border: 1px solid #334155;
  padding: 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  overflow-x: auto;
}
code {
  font-family: ui-monospace, Menlo, monospace;
}
</style>
