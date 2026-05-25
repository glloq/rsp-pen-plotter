<script setup lang="ts">
// Pure SVG renderer for the SheetPreview's workspace surface (L10 #2).
//
// Receives geometry-derived data via props and paints:
//   - workspace outline (white rect with slate border)
//   - 10mm minor / 50mm major grid + cm labels
//   - decorative sheet-format overlay (when LayoutSection picks one)
//   - per-placement content via the tier 1/2/3 fallback chain
//     (source preview ``<image>`` → sanitised plotter SVG → MIME
//     badge)
//
// Interaction lives in the sibling ``<PlacementHandles>`` component;
// this surface is presentational only so the canvas re-renders are
// purely declarative.

import { shortMime } from '../lib/labels'
import type { RenderedPlacement, SheetGrid, SheetWorkspace } from '../composables/useSheetGeometry'

const props = defineProps<{
  workspace: SheetWorkspace
  grid: SheetGrid | null
  previewSheetRect: { x: number; y: number; width: number; height: number } | null
  renderedPlacements: RenderedPlacement[]
  showsPreviewImage: (rp: RenderedPlacement) => boolean
  showsPlotterSvg: (rp: RenderedPlacement) => boolean
  showsMimeBadge: (rp: RenderedPlacement) => boolean
  onPreviewLoad: (fileId: string) => void
  onPreviewError: (fileId: string) => void
}>()

// CSS transform applied to the foreignObject content so the previewed
// drawing matches the placement's rotation / mirror state. The inner
// box's width / height are swapped for a quarter-turn so the SVG
// renders at its post-rotation aspect ratio inside the placement
// footprint; ``transform-origin: 50% 50%`` keeps the rotation
// centred.
function placementInnerStyle(rp: RenderedPlacement): Record<string, string> {
  const p = rp.placement
  const rotated = p.rotation % 180 !== 0
  const parts: string[] = ['translate(-50%, -50%)']
  if (p.rotation) parts.push(`rotate(${p.rotation}deg)`)
  if (p.flip_h) parts.push('scaleX(-1)')
  if (p.flip_v) parts.push('scaleY(-1)')
  const fpW = rp.footprint.x_max - rp.footprint.x_min
  const fpH = rp.footprint.y_max - rp.footprint.y_min
  const innerW = rotated ? fpH : fpW
  const innerH = rotated ? fpW : fpH
  return {
    position: 'absolute',
    left: '50%',
    top: '50%',
    width: `${innerW}px`,
    height: `${innerH}px`,
    transform: parts.join(' '),
    transformOrigin: '50% 50%',
  }
}

defineExpose({ placementInnerStyle })

// Computed label size in workspace mm so the cm tick text reads at a
// consistent visual scale regardless of profile. Mirrors the
// pre-split rule (workspace 1.5%).
function labelFontSize(): number {
  return Math.max(props.workspace.wsW, props.workspace.wsH) * 0.015
}
</script>

<template>
  <g>
    <rect
      :x="workspace.ws.x_min"
      :y="workspace.ws.y_min"
      :width="workspace.wsW"
      :height="workspace.wsH"
      fill="#ffffff"
      stroke="#475569"
      stroke-width="1.5"
      vector-effect="non-scaling-stroke"
    />
    <g v-if="grid" pointer-events="none">
      <line
        v-for="x in grid.xs"
        :key="`gx-${x}`"
        :x1="x"
        :x2="x"
        :y1="workspace.ws.y_min"
        :y2="workspace.ws.y_max"
        :stroke="grid.majorXs.includes(x) ? '#cbd5e1' : '#e2e8f0'"
        :stroke-width="grid.majorXs.includes(x) ? 0.8 : 0.5"
        vector-effect="non-scaling-stroke"
      />
      <line
        v-for="y in grid.ys"
        :key="`gy-${y}`"
        :x1="workspace.ws.x_min"
        :x2="workspace.ws.x_max"
        :y1="y"
        :y2="y"
        :stroke="grid.majorYs.includes(y) ? '#cbd5e1' : '#e2e8f0'"
        :stroke-width="grid.majorYs.includes(y) ? 0.8 : 0.5"
        vector-effect="non-scaling-stroke"
      />
      <text
        v-for="label in grid.labelsX"
        :key="`lx-${label.x}`"
        :x="label.x"
        :y="workspace.ws.y_min - 1"
        text-anchor="middle"
        fill="#64748b"
        :font-size="labelFontSize()"
        font-family="ui-sans-serif, system-ui, sans-serif"
      >
        {{ label.cm }}
      </text>
      <text
        v-for="label in grid.labelsY"
        :key="`ly-${label.y}`"
        :x="workspace.ws.x_min - 1"
        :y="label.y"
        text-anchor="end"
        dominant-baseline="central"
        fill="#64748b"
        :font-size="labelFontSize()"
        font-family="ui-sans-serif, system-ui, sans-serif"
      >
        {{ label.cm }}
      </text>
    </g>

    <!-- Sheet overlay: transparent rectangle at workspace top-left
         representing the format chosen in LayoutSection. Decorative. -->
    <rect
      v-if="previewSheetRect"
      :x="previewSheetRect.x"
      :y="previewSheetRect.y"
      :width="previewSheetRect.width"
      :height="previewSheetRect.height"
      fill="#38bdf8"
      fill-opacity="0.12"
      stroke="#0ea5e9"
      stroke-width="1.2"
      stroke-dasharray="6 4"
      vector-effect="non-scaling-stroke"
      pointer-events="none"
    />

    <!-- Each placement: drawing content via the tier 1/2/3 fallback
         chain. Bounding rect + handles live in PlacementHandles so
         this surface stays purely declarative. -->
    <template v-for="rp in renderedPlacements" :key="rp.placement.id">
      <foreignObject
        v-if="showsPreviewImage(rp)"
        :x="rp.footprint.x_min"
        :y="rp.footprint.y_min"
        :width="Math.max(rp.footprint.x_max - rp.footprint.x_min, 0.01)"
        :height="Math.max(rp.footprint.y_max - rp.footprint.y_min, 0.01)"
      >
        <div
          xmlns="http://www.w3.org/1999/xhtml"
          class="pointer-events-none overflow-hidden"
          :style="placementInnerStyle(rp)"
        >
          <img
            :src="rp.previewUrl"
            alt=""
            draggable="false"
            class="h-full w-full select-none object-fill"
            @load="onPreviewLoad(rp.placement.library_file_id ?? '')"
            @error="onPreviewError(rp.placement.library_file_id ?? '')"
          />
        </div>
      </foreignObject>
      <foreignObject
        v-if="showsPlotterSvg(rp)"
        :x="rp.footprint.x_min"
        :y="rp.footprint.y_min"
        :width="Math.max(rp.footprint.x_max - rp.footprint.x_min, 0.01)"
        :height="Math.max(rp.footprint.y_max - rp.footprint.y_min, 0.01)"
      >
        <div
          xmlns="http://www.w3.org/1999/xhtml"
          class="pointer-events-none overflow-hidden"
          :style="placementInnerStyle(rp)"
          v-html="rp.cleanSvg"
        />
      </foreignObject>
      <foreignObject
        v-if="showsMimeBadge(rp)"
        :x="rp.footprint.x_min"
        :y="rp.footprint.y_min"
        :width="Math.max(rp.footprint.x_max - rp.footprint.x_min, 0.01)"
        :height="Math.max(rp.footprint.y_max - rp.footprint.y_min, 0.01)"
      >
        <div
          xmlns="http://www.w3.org/1999/xhtml"
          class="pointer-events-none flex h-full w-full items-center justify-center bg-slate-100/50 font-mono text-[10px] uppercase tracking-wider text-slate-500"
        >
          {{ shortMime(rp.placement.source_mime || 'application/octet-stream') }}
        </div>
      </foreignObject>
    </template>
  </g>
</template>

<style scoped>
:deep(foreignObject > div > svg) {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
