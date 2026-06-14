<script setup lang="ts">
import { useAccordionPersistence } from '../../../composables/useAccordionPersistence'

// Single card primitive for the editor's right-hand panel: a slate card
// with a collapsible header whose open/closed state is persisted per
// ``cardKey`` (via useAccordionPersistence). It replaces the accordion
// markup that was pasted verbatim across the image/segmentation cards and
// gives the previously-flat cards (post-process, typography layout/page)
// the same fold affordance, so the operator can hide advanced sections
// and the whole panel reads as one consistent system.
//
// An optional reset button sits in the header (``resettable``) — emits
// ``reset`` and is disabled when ``canReset`` is false (already at
// defaults), giving every section the per-section rollback that only the
// Image intro card used to offer.

const props = withDefaults(
  defineProps<{
    cardKey: string
    title: string
    defaultExpanded?: boolean
    resettable?: boolean
    canReset?: boolean
    resetLabel?: string
  }>(),
  {
    defaultExpanded: false,
    resettable: false,
    canReset: true,
    // Empty → the header shows the ``↺`` glyph and no tooltip; callers
    // pass a localised label when they want one.
    resetLabel: '',
  },
)

const emit = defineEmits<{ reset: [] }>()
const expanded = useAccordionPersistence(props.cardKey, props.defaultExpanded)

function toggle(): void {
  expanded.value = !expanded.value
}
function onReset(): void {
  emit('reset')
}
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800">
    <div class="flex items-center gap-2 px-3 py-2">
      <button
        type="button"
        class="flex-1 text-left text-xs uppercase tracking-wide text-slate-400 hover:text-slate-200"
        :aria-expanded="expanded"
        @click="toggle"
      >
        {{ title }}
      </button>
      <button
        v-if="resettable"
        type="button"
        :disabled="!canReset"
        :title="resetLabel"
        class="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-300 transition hover:border-emerald-700 hover:text-emerald-200 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-slate-700 disabled:hover:text-slate-300"
        @click="onReset"
      >
        {{ resetLabel || '↺' }}
      </button>
      <button
        type="button"
        class="text-slate-500 hover:text-slate-200"
        :aria-label="title"
        @click="toggle"
      >
        {{ expanded ? '−' : '+' }}
      </button>
    </div>
    <div v-if="expanded" class="space-y-3 border-t border-slate-700 p-3 text-xs">
      <slot />
    </div>
  </div>
</template>
