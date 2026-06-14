<script setup lang="ts">
// Centered empty / not-applicable state for the editor tabs. Replaces the
// bare slate-500 one-liners that previously rendered when a tab didn't
// apply to the current source (e.g. the Image tab on a vector file) or no
// source was attached — those read as "is this broken?". A muted icon +
// centered message makes the intent unmistakable while staying within the
// dark slate system.

withDefaults(
  defineProps<{
    message: string
    /** Glyph shown above the message (monospace, decorative). */
    icon?: string
  }>(),
  { icon: '—' },
)
</script>

<template>
  <div class="flex flex-col items-center gap-1 px-3 py-6 text-center text-slate-500">
    <span class="font-mono text-2xl leading-none text-slate-600" aria-hidden="true">{{
      icon
    }}</span>
    <p class="text-[11px] leading-snug">{{ message }}</p>
  </div>
</template>
