<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getAlgoSpec, type AlgoOption } from '../../data/algorithmSchemas'
import { ALGO_PEN_FLOOR_KEYS, penMarkFloorMm } from '../../lib/penWidth'

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
  // Pen tip diameter (mm) of the colour(s) drawn with this algorithm.
  // Raises the lower bound of physical mark-size options (``dot_radius_mm``,
  // ``stroke_width``) to what the pen can actually draw. Omitted /
  // ``null`` (the per-layer expert form, where no single pen applies)
  // leaves the schema bounds untouched.
  minPenWidthMm?: number | null
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

// Pen-tip floor (mm) for a physical mark-size option, or ``null`` when
// the option isn't a mark or no pen width is known.
function penFloor(opt: AlgoOption): number | null {
  const kind = ALGO_PEN_FLOOR_KEYS[opt.key]
  return kind ? penMarkFloorMm(kind, props.minPenWidthMm) : null
}

// Lower bound shown on the input: the pen floor when it's higher than
// the schema min, else the schema min.
function optionMin(opt: AlgoOption): number | undefined {
  const floor = penFloor(opt)
  if (floor === null) return opt.min
  return opt.min === undefined ? floor : Math.max(opt.min, floor)
}

// Value shown, clamped up to the pen floor so a stored knob never
// displays a thinner mark than the pen can make.
function displayValue(opt: AlgoOption): unknown {
  const v = currentValue(opt)
  const floor = penFloor(opt)
  if (floor !== null && typeof v === 'number' && v < floor) return floor
  return v
}

// Persist the floor: when a stored mark-size option sits below the pen's
// mark, raise it so the rendered output matches the input. Number inputs
// don't reject sub-min typed values, so this also re-clamps after edits.
// Runs only when a pen width is supplied (master-style fallback) — the
// per-layer expert form passes none, so nothing is rewritten there.
watch(
  [spec, () => props.values, () => props.minPenWidthMm],
  () => {
    if (!(typeof props.minPenWidthMm === 'number') || !(props.minPenWidthMm > 0)) return
    for (const opt of spec.value?.schema ?? []) {
      const floor = penFloor(opt)
      if (floor === null) continue
      const v = currentValue(opt)
      if (typeof v === 'number' && v < floor) emit('update', opt.key, floor)
    }
  },
  { immediate: true, deep: true },
)

function onChange(opt: AlgoOption, ev: Event): void {
  const el = ev.target as HTMLInputElement | HTMLSelectElement
  let value: unknown
  if (opt.type === 'boolean') {
    value = (el as HTMLInputElement).checked
  } else if (opt.type === 'select') {
    value = (el as HTMLSelectElement).value
  } else if (opt.type === 'text') {
    value = (el as HTMLInputElement).value
  } else if (opt.type === 'integer') {
    // Round to keep the operator from sending non-integer values that
    // the backend would silently truncate (and that bypass the form's
    // step=1 constraint when typed in directly).
    value = Math.round(Number((el as HTMLInputElement).value))
  } else {
    value = Number((el as HTMLInputElement).value)
    // A typed number can dip below the input's ``min`` attribute, so
    // clamp mark-size options up to the pen floor explicitly.
    const floor = penFloor(opt)
    if (floor !== null && typeof value === 'number' && value < floor) value = floor
  }
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
        v-else-if="opt.type === 'select'"
        :class="
          compact
            ? 'flex items-center gap-1.5 text-[11px] text-slate-400'
            : 'block text-[11px] text-slate-400'
        "
      >
        <span :class="compact ? 'w-24 shrink-0 truncate' : ''">{{ t(opt.label) }}</span>
        <select
          :value="String(currentValue(opt) ?? '')"
          :class="
            compact
              ? 'min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-[11px] text-slate-100'
              : 'mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[11px] text-slate-100'
          "
          @change="(e) => onChange(opt, e)"
        >
          <option v-for="choice in opt.choices ?? []" :key="choice" :value="choice">
            {{ choice }}
          </option>
        </select>
      </label>
      <label
        v-else-if="opt.type === 'text'"
        :class="
          compact
            ? 'flex items-center gap-1.5 text-[11px] text-slate-400'
            : 'block text-[11px] text-slate-400'
        "
      >
        <span :class="compact ? 'w-24 shrink-0 truncate' : ''">{{ t(opt.label) }}</span>
        <input
          type="text"
          :value="String(currentValue(opt) ?? '')"
          :class="
            compact
              ? 'min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-[11px] text-slate-100'
              : 'mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[11px] text-slate-100'
          "
          @change="(e) => onChange(opt, e)"
        />
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
          :min="optionMin(opt)"
          :max="opt.max"
          :step="opt.type === 'integer' ? (opt.step ?? 1) : opt.step"
          :value="displayValue(opt)"
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
