<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import EditTabs, { type EditTabId } from '../edit/EditTabs.vue'

// Expert surface for the editor modal: the V1-style tab strip (Image /
// SVG / Style / Text / Layers) restored from the audit, where each tab
// carries the source-level cards (brightness/contrast, segmentation
// method, master style, typography) the V1→V2 migration dropped.
//
// The tab CONTENT is async-loaded — those cards are heavy and an
// assisted-mode operator never opens them, so they fetch the first time
// the operator lands on the matching tab. The strip itself is light and
// imported eagerly so switching to expert mounts instantly. Pure
// presentation: the active tab arrives via prop and selection is emitted.
const ImageTab = defineAsyncComponent(() => import('../edit/tabs/ImageTab.vue'))
const SvgTab = defineAsyncComponent(() => import('../edit/tabs/SvgTab.vue'))
const StyleTab = defineAsyncComponent(() => import('../edit/tabs/StyleTab.vue'))
const TextTab = defineAsyncComponent(() => import('../edit/tabs/TextTab.vue'))
const LayersSection = defineAsyncComponent(() => import('../LayersSection.vue'))

defineProps<{
  activeTab: EditTabId
  layerCount: number
  showText: boolean
}>()

const emit = defineEmits<{ (e: 'update:active-tab', id: EditTabId): void }>()
</script>

<template>
  <section class="modal-v2__expert" data-test="modal-v2-expert-panel">
    <EditTabs
      :model-value="activeTab"
      :layer-count="layerCount"
      :show-text="showText"
      @update:model-value="(id: EditTabId) => emit('update:active-tab', id)"
    />
    <div class="modal-v2__expert-body">
      <ImageTab v-if="activeTab === 'image'" />
      <SvgTab v-else-if="activeTab === 'svg'" />
      <StyleTab v-else-if="activeTab === 'style'" />
      <TextTab v-else-if="activeTab === 'text'" />
      <LayersSection v-else-if="activeTab === 'layers'" />
    </div>
  </section>
</template>

<style scoped>
.modal-v2__expert {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
</style>
