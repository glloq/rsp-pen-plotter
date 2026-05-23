// Curated catalogue of "print styles" surfaced in PrintStylePicker.
// Each style is a named bundle of (algorithm, algorithm_options) that
// the operator can apply with a single click. The algorithm + options
// match the backend renderers exactly so a style click goes straight
// through to /rerender via store.applyLayerAlgorithm.
//
// Styles are scoped by the kind of source content they suit best
// (raster image vs. schematic line-art vs. text). The picker filters
// the visible thumbnails accordingly.

export type PrintStyleKind = 'image' | 'schematic' | 'text'

export interface PrintStyle {
  id: string
  labelKey: string
  descriptionKey?: string
  applicableTo: PrintStyleKind[]
  algorithm: string
  algorithm_options: Record<string, unknown>
}

export const PRINT_STYLES: PrintStyle[] = [
  {
    id: 'direct',
    labelKey: 'printStyles.direct',
    descriptionKey: 'printStyles.directDesc',
    applicableTo: ['image', 'schematic', 'text'],
    algorithm: 'direct',
    algorithm_options: {},
  },
  {
    id: 'halftone-fine',
    labelKey: 'printStyles.halftoneFine',
    descriptionKey: 'printStyles.halftoneFineDesc',
    applicableTo: ['image'],
    algorithm: 'halftone',
    algorithm_options: { cell_size_px: 4 },
  },
  {
    id: 'halftone-coarse',
    labelKey: 'printStyles.halftoneCoarse',
    descriptionKey: 'printStyles.halftoneCoarseDesc',
    applicableTo: ['image'],
    algorithm: 'halftone',
    algorithm_options: { cell_size_px: 10 },
  },
  {
    id: 'stippling-portrait',
    labelKey: 'printStyles.stippling',
    descriptionKey: 'printStyles.stipplingDesc',
    applicableTo: ['image'],
    algorithm: 'stippling',
    algorithm_options: { density: 0.03, dot_radius_px: 0.5, seed: 0 },
  },
  {
    id: 'crosshatch-tech',
    labelKey: 'printStyles.crosshatch',
    descriptionKey: 'printStyles.crosshatchDesc',
    applicableTo: ['image', 'schematic'],
    algorithm: 'crosshatch',
    algorithm_options: { angle_deg: 45, spacing_px: 4, crossed: true },
  },
  {
    id: 'contours',
    labelKey: 'printStyles.contours',
    descriptionKey: 'printStyles.contoursDesc',
    applicableTo: ['image', 'schematic'],
    algorithm: 'contours',
    algorithm_options: { spacing_px: 5, max_rings: 20 },
  },
  {
    id: 'edges',
    labelKey: 'printStyles.edges',
    descriptionKey: 'printStyles.edgesDesc',
    applicableTo: ['image', 'schematic'],
    algorithm: 'edges',
    algorithm_options: { stroke_width: 0.8 },
  },
  {
    id: 'spiral',
    labelKey: 'printStyles.spiral',
    descriptionKey: 'printStyles.spiralDesc',
    applicableTo: ['image'],
    algorithm: 'spiral',
    algorithm_options: { spacing_px: 4, samples_per_turn: 64 },
  },
  {
    id: 'scanlines',
    labelKey: 'printStyles.scanlines',
    descriptionKey: 'printStyles.scanlinesDesc',
    applicableTo: ['image'],
    algorithm: 'scanlines',
    algorithm_options: { spacing_px: 4, wave_amp_px: 0, wave_period_px: 12 },
  },
]

export function stylesFor(kind: PrintStyleKind): PrintStyle[] {
  return PRINT_STYLES.filter((style) => style.applicableTo.includes(kind))
}
