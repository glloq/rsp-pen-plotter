<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { useFileManager } from '../../../composables/useFileManager'
import { useJobStore } from '../../../stores/job'
import DetailPicker from '../shared/DetailPicker.vue'
import SegmentationMethodCard from '../svg/SegmentationMethodCard.vue'

// SVG tab — every technical knob that drives image → SVG conversion:
//   - Detail picker (max_dimension_px): the longer side of the
//     segmentation canvas; controls how much fine detail survives.
//   - Centerline / line-tracing mode: switches the vectorisation to
//     medial-skeleton tracing (single polylines along each stroke)
//     instead of region outlines. Ideal for schematics and line art.
//   - Douglas-Peucker simplification: a per-layer tolerance applied
//     by /optimize. Slider here writes through to every layer.
//   - Bezier fitting toggle: reserved for a future polyline→cubic-
//     Bezier pass on /optimize.
//   - Segmentation method picker + its primary parameter (kmeans /
//     luminance_bands / thresholds / fixed_palette).
//
// Post-processing (drop_background, min_region, merge_delta_e) lives
// on the Style tab — those filter the segmentation output rather than
// choose how to vectorise.

const { t } = useI18n()
const draft = useBitmapDraft()
const fm = useFileManager(t)
const store = useJobStore()

const bitmap = draft.bitmap
const curves = draft.curves

function onSimplifyChange(event: Event): void {
  const v = Number((event.target as HTMLInputElement).value)
  curves.value.simplify_tolerance_mm = v
  // Propagate to every layer of the active placement so the next
  // /optimize call uses the slider value as its default. The operator
  // can still override per-layer in LayerCard's advanced controls.
  for (const layer of store.layers) {
    store.updateLayer(layer.layer_id, { simplify_tolerance_mm: v })
  }
}
</script>

<template>
  <section v-if="fm.hasSource.value && fm.showsBitmapForm.value" class="space-y-3">
    <!-- Detail tier + path treatments -->
    <div class="card space-y-3 text-xs">
      <DetailPicker
        :model-value="bitmap.max_dimension_px"
        @update:model-value="(v) => (bitmap.max_dimension_px = v)"
      />

      <div class="border-t border-slate-700 pt-3 space-y-3">
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('svg.pathTitle') }}
        </p>

        <!-- Centerline / line-tracing mode -->
        <label class="flex items-start gap-2 text-slate-300">
          <input
            v-model="curves.centerline_mode"
            type="checkbox"
            class="mt-0.5 rounded border-slate-600 bg-slate-900"
          />
          <span class="flex-1">
            <span class="block font-medium">{{ t('svg.centerline') }}</span>
            <span class="block text-[10px] leading-snug text-slate-500">
              {{ t('svg.centerlineDesc') }}
            </span>
          </span>
        </label>

        <!-- Centerline fine-detail threshold (min branch length in px).
             Lower = preserve tick marks / dimension serifs / hatching ;
             higher = drop short spurs that are mostly skeletonisation
             noise. Only meaningful when centerline_mode is on. -->
        <div v-if="curves.centerline_mode" class="space-y-1 pl-6">
          <div class="flex items-center justify-between text-slate-300">
            <label for="svg-min-branch" class="font-medium">
              {{ t('svg.minBranch') }}
            </label>
            <span class="font-mono text-[10px] text-slate-400">
              {{ curves.centerline_min_branch_mm }} mm
            </span>
          </div>
          <input
            id="svg-min-branch"
            v-model.number="curves.centerline_min_branch_mm"
            type="range"
            min="0.2"
            max="3.7"
            step="0.1"
            class="w-full accent-emerald-500"
          />
          <p class="text-[10px] leading-snug text-slate-500">
            {{ t('svg.minBranchDesc') }}
          </p>
        </div>

        <!-- Douglas-Peucker simplification -->
        <div class="space-y-1">
          <div class="flex items-center justify-between text-slate-300">
            <label for="svg-simplify" class="font-medium">{{ t('svg.simplify') }}</label>
            <span class="font-mono text-[10px] text-slate-400">
              {{ curves.simplify_tolerance_mm.toFixed(2) }} mm
            </span>
          </div>
          <input
            id="svg-simplify"
            type="range"
            min="0.01"
            max="0.5"
            step="0.01"
            :value="curves.simplify_tolerance_mm"
            class="w-full accent-emerald-500"
            @input="onSimplifyChange"
          />
          <p class="text-[10px] leading-snug text-slate-500">
            {{ t('svg.simplifyDesc') }}
          </p>
        </div>

        <!-- Curve fitting (reserved) -->
        <label class="flex items-start gap-2 text-slate-500">
          <input
            v-model="curves.curve_fit"
            type="checkbox"
            disabled
            class="mt-0.5 rounded border-slate-700 bg-slate-900"
          />
          <span class="flex-1">
            <span class="block font-medium">
              {{ t('svg.curveFit') }}
              <span
                class="ml-1 rounded bg-slate-700 px-1 py-px font-mono text-[9px] text-slate-300"
              >
                {{ t('svg.curveFitTodo') }}
              </span>
            </span>
            <span class="block text-[10px] leading-snug">
              {{ t('svg.curveFitDesc') }}
            </span>
          </span>
        </label>
      </div>
    </div>

    <!-- Segmentation method (how the bitmap gets split into masks) -->
    <SegmentationMethodCard :bitmap="bitmap" :is-document="fm.kind.value === 'document'" />
  </section>

  <p v-else-if="!fm.hasSource.value" class="text-[11px] text-slate-500">
    {{ t('svg.noSource') }}
  </p>

  <p v-else class="text-[11px] text-slate-500">
    {{ t('svg.notApplicable') }}
  </p>
</template>
