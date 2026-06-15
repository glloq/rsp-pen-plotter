<script setup lang="ts">
// The ONE place a preview SVG string is injected into the DOM.
//
// Every ``v-html`` of an SVG payload in the editor goes through this
// component instead of binding the raw string directly, so the trust
// boundary is explicit and impossible to bypass by accident: the markup is
// run through DOMPurify (``sanitizePreviewSvgCached``) before it ever
// reaches ``v-html``. A future preview source — a new recolour pass, a
// third-party importer, a cached blob — is sanitised the moment it's
// rendered here, without the caller having to remember to do it (audit P2,
// "la frontière de sécurité des SVG injectés n'est pas explicite").
//
// Attributes (class / style / data-test / ref-less bindings) fall through
// to the root <div> so call sites keep their layout and test hooks.
import { computed } from 'vue'
import { sanitizePreviewSvgCached } from '../../lib/sanitizeSvg'

const props = defineProps<{
  /** Raw SVG markup. ``null`` / empty renders nothing. */
  svg: string | null | undefined
}>()

const clean = computed<string>(() => (props.svg ? sanitizePreviewSvgCached(props.svg) : ''))
</script>

<template>
  <div class="safe-svg" v-html="clean" />
</template>
