<script setup lang="ts">
// The ONE place a *dynamic* preview SVG string is injected into the DOM.
//
// Every ``v-html`` of a SVG payload whose markup originates outside the
// bundle — a /preview or /rerender render, a recolour pass, a third-party
// importer, a cached blob — goes through this component instead of binding
// the raw string directly, so the trust boundary is explicit and impossible
// to bypass by accident: the markup is run through DOMPurify
// (``sanitizePreviewSvgCached``) before it ever reaches ``v-html`` (audit P2,
// "la frontière de sécurité des SVG injectés n'est pas explicite").
//
// EXCEPTION — static, in-bundle SVG does NOT route through here. The beginner
// style thumbnails (``StyleCustomizer.vue`` ← ``beginnerStyles.ts``) are
// hardcoded ``const`` string literals shipped in the source, as trusted as
// the template markup itself, and are injected as the *inner* content of a
// sized ``<svg viewBox>`` (this component wraps in a ``<div>``). Sanitising a
// build-time constant on every render would be pure overhead with no trust
// boundary to enforce, so those sites are an intentional, documented
// exception rather than a leak in the invariant.
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
