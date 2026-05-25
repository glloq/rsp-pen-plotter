<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAccordionPersistence } from '../../../composables/useAccordionPersistence'
import type { PreprocessDraft } from '../../../composables/useBitmapDraft'

// Geometry: rotate (in 90° steps), flip H/V, and a numeric crop.
// Crop is expressed as four percentages so the operator can dial it
// in without depending on a drag-on-canvas tool (that comes later).
// The four inputs round-trip through ``setCrop`` which clamps the
// values into [0, 1] and refuses to write a zero-size rectangle —
// otherwise the backend's validator would reject the payload.

const props = defineProps<{ preprocess: PreprocessDraft }>()

const { t } = useI18n()
const expanded = useAccordionPersistence('preprocess.transform', false)

const ROTATIONS: Array<0 | 90 | 180 | 270> = [0, 90, 180, 270]

const cropEnabled = computed<boolean>({
  get: () => props.preprocess.crop !== null,
  set: (value: boolean) => {
    props.preprocess.crop = value ? [0, 0, 1, 1] : null
  },
})

type CropTuple = [number, number, number, number]
const FULL_CROP: CropTuple = [0, 0, 1, 1]
const crop = computed<CropTuple>(() => props.preprocess.crop ?? FULL_CROP)

function setCropField(index: 0 | 1 | 2 | 3, value: number): void {
  const c = crop.value
  const next: CropTuple = [c[0], c[1], c[2], c[3]]
  next[index] = Math.max(0, Math.min(1, value))
  // Force width and height to stay > 0 and inside the unit square so
  // the backend's validator never rejects the payload.
  if (next[2] <= 0) next[2] = 0.01
  if (next[3] <= 0) next[3] = 0.01
  if (next[0] + next[2] > 1) next[2] = Math.max(0.01, 1 - next[0])
  if (next[1] + next[3] > 1) next[3] = Math.max(0.01, 1 - next[1])
  props.preprocess.crop = next
}

function percent(value: number): number {
  return Math.round(value * 100)
}
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800">
    <button
      type="button"
      class="flex w-full items-center justify-between px-3 py-2 text-xs uppercase tracking-wide text-slate-400 hover:text-slate-200"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      {{ t('preprocess.transform.title') }}
      <span class="text-slate-500">{{ expanded ? '−' : '+' }}</span>
    </button>
    <div v-if="expanded" class="space-y-3 border-t border-slate-700 p-3 text-xs">
      <div class="space-y-1">
        <p class="text-slate-400">{{ t('preprocess.transform.rotate') }}</p>
        <div class="grid grid-cols-4 gap-1">
          <button
            v-for="deg in ROTATIONS"
            :key="deg"
            type="button"
            class="rounded border px-2 py-1.5 text-[11px] transition"
            :class="
              preprocess.rotate_deg === deg
                ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
                : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'
            "
            @click="preprocess.rotate_deg = deg"
          >
            {{ deg }}°
          </button>
        </div>
      </div>

      <div class="flex gap-4">
        <label class="flex items-center gap-2 text-slate-300">
          <input v-model="preprocess.flip_h" type="checkbox" class="accent-emerald-500" />
          <span>{{ t('preprocess.transform.flipH') }}</span>
        </label>
        <label class="flex items-center gap-2 text-slate-300">
          <input v-model="preprocess.flip_v" type="checkbox" class="accent-emerald-500" />
          <span>{{ t('preprocess.transform.flipV') }}</span>
        </label>
      </div>

      <div class="space-y-2 rounded border border-slate-700 bg-slate-900/40 p-2">
        <label class="flex items-center gap-2 text-slate-300">
          <input v-model="cropEnabled" type="checkbox" class="accent-emerald-500" />
          <span>{{ t('preprocess.transform.cropEnable') }}</span>
        </label>
        <div v-if="cropEnabled" class="grid grid-cols-2 gap-2">
          <label class="block text-slate-400">
            <span>{{ t('preprocess.transform.cropX') }} (%)</span>
            <input
              :value="percent(crop[0])"
              type="number"
              min="0"
              max="99"
              class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              @input="
                setCropField(0, (($event.target as HTMLInputElement).valueAsNumber || 0) / 100)
              "
            />
          </label>
          <label class="block text-slate-400">
            <span>{{ t('preprocess.transform.cropY') }} (%)</span>
            <input
              :value="percent(crop[1])"
              type="number"
              min="0"
              max="99"
              class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              @input="
                setCropField(1, (($event.target as HTMLInputElement).valueAsNumber || 0) / 100)
              "
            />
          </label>
          <label class="block text-slate-400">
            <span>{{ t('preprocess.transform.cropW') }} (%)</span>
            <input
              :value="percent(crop[2])"
              type="number"
              min="1"
              max="100"
              class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              @input="
                setCropField(2, (($event.target as HTMLInputElement).valueAsNumber || 0) / 100)
              "
            />
          </label>
          <label class="block text-slate-400">
            <span>{{ t('preprocess.transform.cropH') }} (%)</span>
            <input
              :value="percent(crop[3])"
              type="number"
              min="1"
              max="100"
              class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              @input="
                setCropField(3, (($event.target as HTMLInputElement).valueAsNumber || 0) / 100)
              "
            />
          </label>
        </div>
      </div>
    </div>
  </div>
</template>
