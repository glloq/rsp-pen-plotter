<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { layerStyles, type PrintStyle, type PrintStyleKind } from '../../data/printRegistry'

const props = defineProps<{
  kind: PrintStyleKind
  // Currently-selected algorithm name. We don't try to match the full
  // algorithm_options here — the picker is for "presets"; once the user
  // tweaks the advanced knobs, no style is highlighted any more.
  currentAlgorithm: string
}>()

const emit = defineEmits<{
  (e: 'select', style: PrintStyle): void
  (e: 'reset'): void
}>()

const { t } = useI18n()

// Curated short-list shown by default. The full registry exposes ~24
// per-layer styles, which is overwhelming as a flat grid — the operator
// only reaches for the long tail occasionally. We surface a handful of
// general-purpose ones up front and tuck the rest behind a "show all"
// toggle. Ids that aren't applicable to the current ``kind`` are
// filtered out by ``layerStyles`` so a missing featured id is simply
// skipped (no empty tile).
const FEATURED_LAYER_STYLE_IDS = [
  'direct',
  'halftone-fine',
  'stippling-portrait',
  'crosshatch-tech',
  'contours',
  'edges',
  'spiral',
] as const

const visible = computed(() => layerStyles(props.kind))
const featuredSet = new Set<string>(FEATURED_LAYER_STYLE_IDS)
const featured = computed(() => visible.value.filter((s) => featuredSet.has(s.id)))
const rest = computed(() => visible.value.filter((s) => !featuredSet.has(s.id)))

function isSelected(style: PrintStyle): boolean {
  return style.defaultAlgorithm === props.currentAlgorithm
}

// "Default" tile clears any per-layer override so the layer renders
// with whatever algorithm the converter baked in at upload time.
const defaultSelected = computed(() => !props.currentAlgorithm)

// Expand the long tail automatically when the active selection lives in
// it — otherwise the operator's current choice would be invisible while
// collapsed. Stays expanded once opened so toggling styles in the tail
// doesn't keep snapping it shut.
const selectedInRest = computed(() => rest.value.some((s) => isSelected(s)))
const showAll = ref(selectedInRest.value)
watch(selectedInRest, (inRest) => {
  if (inRest) showAll.value = true
})

// The grid the template iterates: featured-only when collapsed, the full
// list when expanded.
const shown = computed(() => (showAll.value ? visible.value : featured.value))
</script>

<template>
  <div class="space-y-1.5">
    <div class="grid grid-cols-3 gap-1.5">
      <button
        type="button"
        class="flex flex-col gap-0.5 rounded border px-2 py-1.5 text-left text-[11px] transition"
        :class="
          defaultSelected
            ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
            : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'
        "
        @click="emit('reset')"
      >
        <span class="font-medium">{{ t('printStyles.default') }}</span>
        <span class="text-[9px] text-slate-500">{{ t('printStyles.defaultDesc') }}</span>
      </button>
      <button
        v-for="style in shown"
        :key="style.id"
        type="button"
        class="flex flex-col gap-0.5 rounded border px-2 py-1.5 text-left text-[11px] transition"
        :class="
          isSelected(style)
            ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
            : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'
        "
        :title="style.descriptionKey ? t(style.descriptionKey) : ''"
        @click="emit('select', style)"
      >
        <span class="font-medium">{{ t(style.labelKey) }}</span>
        <span v-if="style.descriptionKey" class="text-[9px] text-slate-500">
          {{ t(style.descriptionKey) }}
        </span>
      </button>
    </div>

    <!-- Show-all / show-fewer toggle. Hidden when the long tail is empty
         for this ``kind`` (e.g. a text layer with few applicable styles). -->
    <button
      v-if="rest.length"
      type="button"
      class="w-full rounded border border-slate-800 bg-slate-900/60 px-2 py-1 text-[10px] text-slate-400 transition hover:border-slate-600 hover:text-slate-200"
      @click="showAll = !showAll"
    >
      {{ showAll ? t('printStyles.showFewer') : t('printStyles.showAll', { count: rest.length }) }}
    </button>
  </div>
</template>
