<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../../../stores/job'

// Pen slot grid factored out of the two places it lived (the mono
// card's "Pen" row and LayerCard's per-layer slot picker) so colour
// swatches, hover affordances, "not installed" badge and labels stay
// in lock-step. Consumers control the selection via v-model and
// optionally show the section label.

defineProps<{
  modelValue: number
  // When false, the section heading is hidden — handy when the picker
  // is embedded in a denser layer-card row where the surrounding
  // context already implies "pen".
  showLabel?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: number): void
}>()

const { t } = useI18n()
const store = useJobStore()

const penSlots = computed(() => {
  const profile = store.selectedProfile
  const pens = profile?.pens ?? []
  return Array.from({ length: profile?.pen_slot_count ?? 1 }, (_, i) => {
    const pen = pens.find((p) => p.index === i)
    return {
      index: i,
      name: pen?.name || `${i}`,
      color: pen?.color ?? '#94a3b8',
      installed: pen?.installed ?? false,
    }
  })
})

function setSlot(index: number): void {
  emit('update:modelValue', index)
}
</script>

<template>
  <div class="space-y-1">
    <p v-if="showLabel !== false" class="text-[10px] uppercase tracking-wider text-slate-400">
      {{ t('mono.pen') }}
    </p>
    <div class="flex flex-wrap gap-1">
      <button
        v-for="slot in penSlots"
        :key="slot.index"
        type="button"
        class="flex items-center gap-1.5 rounded border px-2 py-1 text-[11px] transition"
        :class="
          modelValue === slot.index
            ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
            : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'
        "
        :title="slot.installed ? slot.name : t('mono.penNotInstalled')"
        @click="setSlot(slot.index)"
      >
        <span
          class="inline-block h-3 w-3 rounded-full border border-slate-600"
          :style="{ backgroundColor: slot.color }"
        />
        <span class="font-mono text-[10px] text-slate-500">#{{ slot.index }}</span>
        <span class="truncate">{{ slot.name }}</span>
        <span v-if="!slot.installed" class="text-[9px] text-amber-400">·</span>
      </button>
    </div>
    <p v-if="showLabel !== false" class="text-[10px] leading-snug text-slate-500">
      {{ t('mono.penHint') }}
    </p>
  </div>
</template>
