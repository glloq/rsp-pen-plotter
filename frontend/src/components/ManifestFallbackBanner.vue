<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ManifestSource } from '../domain/manifests/client'

/**
 * Non-blocking banner shown when the UI is serving algorithm metadata
 * from a cached or build-time snapshot instead of the live backend.
 * The fallback path still works, but the operator should know that a
 * brand-new algorithm or a tweaked default may not have reached this
 * session yet. Phase A.7 surface; integration with stores in Phase B.
 */
const props = defineProps<{
  source: ManifestSource
  error?: Error
}>()

const { t } = useI18n()
const visible = computed(() => props.source !== 'live')

const message = computed(() => {
  if (props.source === 'cache') return t('v2.manifest.fallbackCache')
  if (props.source === 'snapshot') return t('v2.manifest.fallbackSnapshot')
  return ''
})
</script>

<template>
  <div
    v-if="visible"
    role="status"
    aria-live="polite"
    class="manifest-fallback-banner"
    data-test="manifest-fallback-banner"
  >
    <span>{{ message }}</span>
    <span v-if="error" class="manifest-fallback-banner__detail">{{ error.message }}</span>
  </div>
</template>

<style scoped>
.manifest-fallback-banner {
  background: rgba(69, 26, 3, 0.4);
  border: 1px solid #b45309;
  color: #fde68a;
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  display: flex;
  gap: 0.75rem;
  align-items: center;
}
.manifest-fallback-banner__detail {
  opacity: 0.7;
  font-family: monospace;
}
</style>
