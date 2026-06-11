<script setup lang="ts">
import { computed } from 'vue'

// Placeholder visual for a style or algorithm — a colour-keyed swatch
// with a glyph that hints at the algorithm's drawing style. Phase 5
// adds the script that pre-renders 17 PNG thumbnails from a reference
// image at build time; this component picks them up via the optional
// ``imageUrl`` prop. While there's no PNG, the swatch + glyph keeps
// the picker UI consistent and readable.

const props = defineProps<{
  algorithm: string
  // Optional PNG / SVG URL, used when the build script has generated a
  // thumbnail for this style (Phase 5).
  imageUrl?: string
  size?: 'sm' | 'md'
}>()

// Pinned colour + glyph table per algorithm. The colour is purely
// decorative — chosen to be visually distinct so the operator can
// recognise a style at a glance in a dense PassList row.
const STYLE_GLYPHS: Record<string, { color: string; glyph: string }> = {
  direct: { color: '#475569', glyph: '/' },
  halftone: { color: '#0ea5e9', glyph: '⠿' },
  stippling: { color: '#a855f7', glyph: '∴' },
  crosshatch: { color: '#f59e0b', glyph: '╳' },
  contours: { color: '#10b981', glyph: '◎' },
  edges: { color: '#ef4444', glyph: '⌒' },
  spiral: { color: '#06b6d4', glyph: '@' },
  scanlines: { color: '#eab308', glyph: '☰' },
  tsp: { color: '#ec4899', glyph: '∽' },
  flowfield: { color: '#14b8a6', glyph: '≈' },
  voronoi_stipple: { color: '#a855f7', glyph: '⁘' },
  eulerian_hatch: { color: '#f59e0b', glyph: '#' },
  squiggle: { color: '#84cc16', glyph: '∿' },
  hilbert: { color: '#6366f1', glyph: '⌗' },
  gosper: { color: '#0ea5e9', glyph: '✿' },
  concentric_offset: { color: '#10b981', glyph: '◉' },
  tsp_opt: { color: '#ec4899', glyph: '⟿' },
  lowpoly: { color: '#f43f5e', glyph: '◭' },
  scribble: { color: '#facc15', glyph: '⌇' },
  grid: { color: '#64748b', glyph: '▦' },
  brick: { color: '#c2613f', glyph: '⊞' },
  dashes: { color: '#f59e0b', glyph: '┊' },
  truchet: { color: '#8b5cf6', glyph: '◫' },
  rings: { color: '#10b981', glyph: '◎' },
  sunburst: { color: '#f97316', glyph: '✸' },
  circle_pack: { color: '#06b6d4', glyph: '⊙' },
  ridge_lines: { color: '#0ea5e9', glyph: '〰' },
  hitomezashi: { color: '#a855f7', glyph: '╋' },
  cubic_disarray: { color: '#f43f5e', glyph: '▱' },
  quadtree: { color: '#64748b', glyph: '◰' },
  maze: { color: '#10b981', glyph: '◳' },
  phyllotaxis: { color: '#f59e0b', glyph: '❁' },
  voronoi_mosaic: { color: '#8b5cf6', glyph: '▩' },
  curve_stitching: { color: '#06b6d4', glyph: '△' },
  string_art: { color: '#ec4899', glyph: '✶' },
  space_colonization: { color: '#22c55e', glyph: 'ψ' },
  penrose: { color: '#6366f1', glyph: '◇' },
  dither: { color: '#475569', glyph: '▒' },
  etch: { color: '#b45309', glyph: 'ϟ' },
  noise_contours: { color: '#14b8a6', glyph: '≋' },
  reaction_diffusion: { color: '#f97316', glyph: 'ᘎ' },
  superpixel_hatch: { color: '#eab308', glyph: '▤' },
  moire: { color: '#84cc16', glyph: '◍' },
  weave: { color: '#c2613f', glyph: '✦' },
  honeycomb: { color: '#fbbf24', glyph: '⬡' },
  harmonograph: { color: '#06b6d4', glyph: '∞' },
  attractor: { color: '#a855f7', glyph: '☄' },
  text_fill: { color: '#475569', glyph: 'A' },
  lsystem: { color: '#22c55e', glyph: 'ϡ' },
  chladni: { color: '#0ea5e9', glyph: '✣' },
  sine_halftone: { color: '#f472b6', glyph: '∾' },
}

const meta = computed(() => STYLE_GLYPHS[props.algorithm] ?? { color: '#475569', glyph: '?' })

const sizeClass = computed(() =>
  (props.size ?? 'md') === 'sm' ? 'h-4 w-4 text-[8px]' : 'h-6 w-6 text-[10px]',
)
</script>

<template>
  <span
    class="inline-flex items-center justify-center rounded border border-slate-700 font-mono leading-none"
    :class="sizeClass"
    :style="{ backgroundColor: meta.color + '33', color: meta.color }"
    :title="algorithm"
  >
    <img
      v-if="imageUrl"
      :src="imageUrl"
      :alt="algorithm"
      class="h-full w-full rounded object-cover"
    />
    <span v-else>{{ meta.glyph }}</span>
  </span>
</template>
