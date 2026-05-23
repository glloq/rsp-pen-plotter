<script setup lang="ts">
import SourceSection from './SourceSection.vue'
import LayoutSection from './LayoutSection.vue'
import LayersSection from './LayersSection.vue'
import GenerateSection from './GenerateSection.vue'
</script>

<template>
  <aside class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-slate-700 bg-slate-900/40">
    <div class="flex-1 space-y-4 overflow-y-auto p-3">
      <SourceSection />
      <LayoutSection />
      <LayersSection />
      <GenerateSection />
    </div>
  </aside>
</template>
