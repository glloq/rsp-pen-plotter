<script setup lang="ts">
import { computed } from 'vue'
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

const visible = computed(() => props.source !== 'live')

const message = computed(() => {
  if (props.source === 'cache') {
    return 'Manifestes algorithmes servis depuis le cache local — connexion au backend indisponible.'
  }
  if (props.source === 'snapshot') {
    return "Manifestes algorithmes servis depuis le snapshot embarqué — la dernière liste à jour n'a pas pu être chargée."
  }
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
  background: #fff4cc;
  border: 1px solid #d9b800;
  color: #5b4a00;
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  display: flex;
  gap: 0.75rem;
  align-items: center;
}
.manifest-fallback-banner__detail {
  opacity: 0.6;
  font-family: monospace;
}
</style>
