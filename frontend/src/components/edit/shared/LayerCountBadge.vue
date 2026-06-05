<script setup lang="ts">
import { useI18n } from 'vue-i18n'

// Small inline "→ N layers" badge surfaced next to the controls that
// drive the layer count (bands slider, num_colors, palette length).
// Lets the operator predict the cost of a tweak without committing
// and counting cards in the Layers tab. Uses the existing
// ``upload.layers`` plural key so layer / layers stays correct.

defineProps<{
  count: number
}>()

const { t } = useI18n()
</script>

<template>
  <span
    class="ml-1 inline-block rounded-sm bg-slate-800 px-1 py-px font-mono text-[10px] text-slate-400"
    :title="t('layers.expectedHint')"
    >→ {{ count }} {{ t('upload.layers', count) }}</span
  >
</template>
