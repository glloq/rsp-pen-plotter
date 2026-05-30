<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore, type Placement } from '../stores/job'

const { t } = useI18n()
const store = useJobStore()

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs.toString().padStart(2, '0')}s`
}

// The footer describes the file the operator is working with on the
// plan: the selected placement when it's actually on the sheet,
// otherwise the first visible placement that carries a drawing.
const target = computed<Placement | null>(() => {
  const sel = store.selectedPlacement
  if (sel && !sel.is_library_draft && sel.layers.length) return sel
  return store.visiblePlacements.find((p) => p.layers.length) ?? null
})

// Size = the placement's actual footprint on the plan (what the
// operator dragged / resized), not a re-fit of the source bbox.
const drawingDims = computed(() => {
  const p = target.value
  if (!p) return null
  return `${p.width_mm.toFixed(0)}×${p.height_mm.toFixed(0)} mm`
})

// Scale = placed size relative to the source's natural rendered size
// (the union of the layer bboxes, in mm). A 90°/270° rotation swaps
// which source axis maps onto the placed width.
const scaleLabel = computed(() => {
  const p = target.value
  if (!p) return null
  const bw = p.source_bbox.x_max - p.source_bbox.x_min
  const bh = p.source_bbox.y_max - p.source_bbox.y_min
  const swap = Math.abs(Math.round(p.rotation / 90)) % 2 === 1
  const naturalW = swap ? bh : bw
  if (!(naturalW > 0)) return null
  const ratio = p.width_mm / naturalW
  if (!Number.isFinite(ratio) || ratio <= 0) return null
  return `${(ratio * 100).toFixed(0)}%`
})

// Time estimate is only trustworthy once the plan has been resolved into
// a toolpath: ``/preflight`` (and ``/generate``, which runs it) walk the
// real ordered G-code including pen-up travel and tool changes. The
// length÷speed sum we used before ignored travel and gave optimistic
// numbers, so we now surface the preflight figure and show a pending
// placeholder until that calculation has run. ``preflight`` is cleared
// whenever the plan changes, so a stale estimate never lingers.
const estimateSeconds = computed<number | null>(() => store.preflight?.estimated_seconds ?? null)

// Out-of-bounds flag for the target placement: does its footprint spill
// outside the machine workspace? Mirrors the geometry composable's
// ``exceeds`` test so the footer warning matches the red bbox on the
// sheet.
const exceeds = computed(() => {
  const p = target.value
  const profile = store.selectedProfile
  if (!p || !profile) return false
  const ws = profile.workspace
  const x_min = ws.x_min + p.x_mm
  const y_min = ws.y_min + p.y_mm
  const x_max = x_min + p.width_mm
  const y_max = y_min + p.height_mm
  return (
    x_min < ws.x_min - 0.01 ||
    y_min < ws.y_min - 0.01 ||
    x_max > ws.x_max + 0.01 ||
    y_max > ws.y_max + 0.01
  )
})
const missing = computed(() => store.missingPenSlots)
const hasJob = computed(() => target.value !== null)
</script>

<template>
  <footer
    v-if="hasJob"
    class="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-800 bg-slate-900/80 px-4 py-1.5 text-xs"
  >
    <div v-if="drawingDims" class="flex items-baseline gap-1.5">
      <span class="text-slate-500">{{ t('footer.size') }}</span>
      <span class="font-mono text-slate-200">{{ drawingDims }}</span>
    </div>

    <div v-if="scaleLabel" class="flex items-baseline gap-1.5">
      <span class="text-slate-500">{{ t('footer.scale') }}</span>
      <span class="font-mono text-slate-200">{{ scaleLabel }}</span>
    </div>

    <div class="flex items-baseline gap-1.5">
      <span class="text-slate-500">{{ t('footer.estimate') }}</span>
      <span v-if="estimateSeconds !== null" class="font-mono text-slate-200">{{
        formatDuration(estimateSeconds)
      }}</span>
      <span
        v-else
        class="font-mono text-slate-500"
        :title="t('footer.estimatePendingHint')"
        data-test="footer-estimate-pending"
      >
        {{ t('footer.estimatePending') }}
      </span>
    </div>

    <div v-if="store.preflight" class="flex items-baseline gap-1.5">
      <span class="text-slate-500">{{ t('footer.penChanges') }}</span>
      <span class="font-mono text-slate-200">{{ store.preflight.pen_changes }}</span>
    </div>

    <div class="ml-auto flex flex-wrap items-center gap-2">
      <span
        v-if="exceeds"
        class="rounded border border-red-700 bg-red-950/60 px-2 py-0.5 text-red-200"
      >
        ⚠ {{ t('sheet.outOfBounds') }}
      </span>
      <span
        v-if="missing.length"
        class="rounded border border-amber-700 bg-amber-950/60 px-2 py-0.5 text-amber-200"
      >
        ⚠ {{ t('preflight.missingPens', { slots: missing.join(', ') }) }}
      </span>
    </div>
  </footer>
</template>
