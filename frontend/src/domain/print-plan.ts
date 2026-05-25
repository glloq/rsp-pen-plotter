// Print-plan types — readable aliases over the OpenAPI-generated
// ``components.schemas``. The generated file is the source of truth;
// run ``npm run gen:types`` after touching the Pydantic models to
// refresh it. Importing types from this module (rather than
// ``api-types`` directly) keeps the call sites short.

import type { components } from './api-types'

export type LayerPlan = components['schemas']['LayerPlan']
export type PlacementPlan = components['schemas']['PlacementPlan']
export type PlanMetadata = components['schemas']['PlanMetadata']
export type PrintPlan = components['schemas']['PrintPlan']
export type ResolvedLayer = components['schemas']['ResolvedLayer']
export type ResolvedPlan = components['schemas']['ResolvedPlan']
export type TypographyPlan = components['schemas']['TypographyPlan']
export type PausePolicy = NonNullable<LayerPlan['pause_before']>
export type ScaleMode = NonNullable<PrintPlan['scale_mode']>
