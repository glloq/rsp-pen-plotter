/**
 * zod schemas for the AlgorithmPolicyResolver wire types (roadmap C.2 / B.1).
 *
 * Mirrors `pen_plotter.domain.policy.types` exactly. The modal V2 sends
 * a PolicyInput to /policy/resolve and renders the returned
 * PolicyDecision (default algorithm + reasoning + hard constraints +
 * fallback chain).
 */
import { z } from 'zod'

export const SourceKindSchema = z.enum([
  'bitmap_photo',
  'bitmap_illustration',
  'vector_svg',
  'pdf_doc',
  'text_typography',
])
export type SourceKind = z.infer<typeof SourceKindSchema>

export const GoalSchema = z.enum(['fast', 'balanced', 'quality'])
export type Goal = z.infer<typeof GoalSchema>

export const PaletteModeSchema = z.enum(['machine_only', 'union', 'free'])
export type PaletteMode = z.infer<typeof PaletteModeSchema>

export const QualityTierSchema = z.enum(['draft', 'standard', 'final'])
export type QualityTier = z.infer<typeof QualityTierSchema>

export const SegmentationMethodSchema = z.enum(['fixed_palette', 'kmeans', 'none'])
export type SegmentationMethod = z.infer<typeof SegmentationMethodSchema>

export const RuleHitSchema = z.object({
  rule: z.string(),
  description: z.string(),
})
export type RuleHit = z.infer<typeof RuleHitSchema>

export const ConstraintHitSchema = z.object({
  constraint: z.string(),
  description: z.string(),
  forbidden_algorithms: z.array(z.string()).default([]),
})
export type ConstraintHit = z.infer<typeof ConstraintHitSchema>

export const PolicyInputSchema = z.object({
  source_kind: SourceKindSchema,
  goal: GoalSchema.default('fast'),
  palette_mode: PaletteModeSchema.default('union'),
  available_colors_count: z.number().int().nonnegative().default(1),
  image_megapixels: z.number().nullable().optional(),
  layer_count_estimate: z.number().int().nonnegative().default(1),
  is_mono_pen_machine: z.boolean().default(false),
})
export type PolicyInput = z.infer<typeof PolicyInputSchema>

export const PolicyPassSchema = z.object({
  algorithm: z.string(),
  algorithm_options: z.record(z.string(), z.unknown()).default({}),
})
export type PolicyPass = z.infer<typeof PolicyPassSchema>

export const PolicyDecisionSchema = z.object({
  segmentation_method: SegmentationMethodSchema,
  default_algorithm: z.string(),
  default_options: z.record(z.string(), z.unknown()).default({}),
  // Optional ordered multi-pass stack (QUALITY tiers). When non-empty,
  // callers render/apply these passes per layer instead of the single
  // ``default_algorithm``; the first pass mirrors that field.
  default_passes: z.array(PolicyPassSchema).default([]),
  quality_tier: QualityTierSchema,
  fallback_chain: z.array(z.string()).default([]),
  reasoning: z.array(RuleHitSchema).default([]),
  hard_constraints_applied: z.array(ConstraintHitSchema).default([]),
})
export type PolicyDecision = z.infer<typeof PolicyDecisionSchema>
