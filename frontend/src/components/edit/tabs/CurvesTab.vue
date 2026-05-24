<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { useFileManager } from '../../../composables/useFileManager'
import { useJobStore } from '../../../stores/job'

// Curves tab — sits between Image and Colors. Owns the path-level
// treatments that apply between the source raster (Image tab) and the
// colour/segmentation pipeline (Colors / Render):
//   - centerline_mode: switches vectorisation to medial-skeleton
//     tracing (the new ``centerline`` algorithm) so schematics and
//     line art produce single-stroke polylines instead of potrace's
//     double-outlines around every stroke.
//   - simplify_tolerance_mm: Douglas-Peucker tolerance the /optimize
//     endpoint applies per layer. Writing here updates all current
//     layers so the slider is the global default.
//   - curve_fit: reserved for a future polyline→Bezier pass on
//     /optimize. Toggle ships disabled with a "coming soon" hint.

const { t } = useI18n()
const draft = useBitmapDraft()
const fm = useFileManager(t)
const store = useJobStore()

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
    <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-3 text-xs">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">
        {{ t('curves.title') }}
      </p>

      <!-- Centerline / line-tracing mode -->
      <label class="flex items-start gap-2 text-slate-300">
        <input
          v-model="curves.centerline_mode"
          type="checkbox"
          class="mt-0.5 rounded border-slate-600 bg-slate-900"
        />
        <span class="flex-1">
          <span class="block font-medium">{{ t('curves.centerline') }}</span>
          <span class="block text-[10px] leading-snug text-slate-500">
            {{ t('curves.centerlineDesc') }}
          </span>
        </span>
      </label>

      <!-- Douglas-Peucker simplification tolerance -->
      <div class="space-y-1">
        <div class="flex items-center justify-between text-slate-300">
          <label for="curves-simplify" class="font-medium">{{ t('curves.simplify') }}</label>
          <span class="font-mono text-[10px] text-slate-400">
            {{ curves.simplify_tolerance_mm.toFixed(2) }} mm
          </span>
        </div>
        <input
          id="curves-simplify"
          type="range"
          min="0.01"
          max="0.5"
          step="0.01"
          :value="curves.simplify_tolerance_mm"
          class="w-full accent-emerald-500"
          @input="onSimplifyChange"
        />
        <p class="text-[10px] leading-snug text-slate-500">
          {{ t('curves.simplifyDesc') }}
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
            {{ t('curves.curveFit') }}
            <span class="ml-1 rounded bg-slate-700 px-1 py-px font-mono text-[9px] text-slate-300">
              {{ t('curves.curveFitTodo') }}
            </span>
          </span>
          <span class="block text-[10px] leading-snug">
            {{ t('curves.curveFitDesc') }}
          </span>
        </span>
      </label>
    </div>
  </section>

  <p v-else-if="!fm.hasSource.value" class="text-[11px] text-slate-500">
    {{ t('curves.noSource') }}
  </p>

  <p v-else class="text-[11px] text-slate-500">
    {{ t('curves.notApplicable') }}
  </p>
</template>
