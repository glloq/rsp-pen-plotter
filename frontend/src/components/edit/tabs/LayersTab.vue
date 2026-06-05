<script setup lang="ts">
import LayersSection from '../../LayersSection.vue'

// Thin wrapper around LayersSection so the tab API stays uniform with
// SourceTab / ColorsTab / RenderTab. Phase 3 (the LayerPassStack
// "stack-of-passes" refactor) lands inside LayersSection / LayerCard,
// not here.
</script>

<template>
  <LayersSection />
</template>
