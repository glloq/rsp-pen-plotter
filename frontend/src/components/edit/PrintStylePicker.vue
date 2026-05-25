<script setup lang="ts">
import { computed } from 'vue'
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

const visible = computed(() => layerStyles(props.kind))

function isSelected(style: PrintStyle): boolean {
  return style.defaultAlgorithm === props.currentAlgorithm
}

// "Default" tile clears any per-layer override so the layer renders
// with whatever algorithm the converter baked in at upload time.
const defaultSelected = computed(() => !props.currentAlgorithm)
</script>

<template>
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
      v-for="style in visible"
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
</template>
