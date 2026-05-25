<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { getAlgoSpec, type AlgoOption } from '../../data/algorithmSchemas'

// Schema-driven inline form for one algorithm's options. The same
// component renders inside LayerCard's "Advanced" drawer AND inside
// PassList's per-pass parameter panel, so the operator can tweak any
// algorithm's knobs (spacing, angle, seed…) from one place wherever
// it's surfaced. Schema lives in data/algorithmSchemas.ts — adding a
// new algorithm there propagates everywhere.

const props = defineProps<{
  algorithm: string
  values: Record<string, unknown>
  // ``compact`` switches the grid to a single column so the form fits
  // inside narrow contexts (pass rows are ~280px wide).
  compact?: boolean
}>()

const emit = defineEmits<{
  (e: 'update', key: string, value: unknown): void
}>()

const { t } = useI18n()

const spec = computed(() => getAlgoSpec(props.algorithm))

function currentValue(opt: AlgoOption): unknown {
  if (Object.prototype.hasOwnProperty.call(props.values, opt.key)) {
    return props.values[opt.key]
  }
  return spec.value?.defaults[opt.key]
}

function onChange(opt: AlgoOption, ev: Event): void {
  const el = ev.target as HTMLInputElement
  const value = opt.type === 'boolean' ? el.checked : Number(el.value)
  emit('update', opt.key, value)
}
</script>

<template>
  <div v-if="spec && spec.schema.length" :class="compact ? 'space-y-1' : 'grid grid-cols-2 gap-2'">
    <template v-for="opt in spec.schema" :key="opt.key">
      <label
        v-if="opt.type === 'boolean'"
        class="flex items-center gap-1.5 text-[11px] text-slate-400"
      >
        <input
          type="checkbox"
          :checked="Boolean(currentValue(opt))"
          class="h-3.5 w-3.5 accent-emerald-500"
          @change="(e) => onChange(opt, e)"
        />
        {{ t(opt.label) }}
      </label>
      <label
        v-else
        :class="
          compact
            ? 'flex items-center gap-1.5 text-[11px] text-slate-400'
            : 'block text-[11px] text-slate-400'
        "
      >
        <span :class="compact ? 'w-24 shrink-0 truncate' : ''">{{ t(opt.label) }}</span>
        <input
          type="number"
          :min="opt.min"
          :max="opt.max"
          :step="opt.step"
          :value="currentValue(opt)"
          :class="
            compact
              ? 'min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-[11px] text-slate-100'
              : 'mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[11px] text-slate-100'
          "
          @change="(e) => onChange(opt, e)"
        />
      </label>
    </template>
  </div>
</template>
