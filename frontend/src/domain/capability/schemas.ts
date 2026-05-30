/**
 * Capability Model wire types (mirrors pen_plotter.domain.capability).
 *
 * Frontend zod schemas for the v0.2 Capability Model introduced in
 * roadmap A.5 / B.2 and consumed by the C.4 wizard. Kept separate
 * from `domain/policy/schemas.ts` because the lifecycle is different:
 * the policy resolver returns a decision per job, the capability
 * model is a static description of the machine.
 */
import { z } from 'zod'

export const ToolingModeSchema = z.enum(['firmware', 'host_macro', 'manual', 'single_pen'])
export type ToolingMode = z.infer<typeof ToolingModeSchema>

export const CommandSourceSchema = z.enum(['machine', 'host', 'operator'])
export type CommandSource = z.infer<typeof CommandSourceSchema>

export const RecoveryPolicySchema = z.enum(['abort', 'pause_and_prompt', 'skip_layer'])
export type RecoveryPolicy = z.infer<typeof RecoveryPolicySchema>

export const ManualSwapPromptSchema = z.object({
  title: z.string().default('Change pen'),
  body: z.string().default('Insert pen {color} into the holder, then press Resume.'),
  timeout_s: z.number().int().positive().nullable().default(null),
})
export type ManualSwapPrompt = z.infer<typeof ManualSwapPromptSchema>

export const HostMacroStepSchema = z.object({
  send: z.string(),
  wait_ms: z.number().int().nonnegative().default(0),
})
export type HostMacroStep = z.infer<typeof HostMacroStepSchema>

export const ToolChangeStrategySchema = z.object({
  mode: ToolingModeSchema,
  command_source: CommandSourceSchema,
  recovery_policy: RecoveryPolicySchema,
  manual_prompt: ManualSwapPromptSchema.nullable().default(null),
  host_macro: z.array(HostMacroStepSchema).default([]),
})
export type ToolChangeStrategyValue = z.infer<typeof ToolChangeStrategySchema>

export const MachineCapabilitiesSchema = z.object({
  tool_change: ToolChangeStrategySchema,
  has_pen_sensor: z.boolean().default(false),
  has_sheet_loader: z.boolean().default(false),
  max_pens_in_magazine: z.number().int().positive().default(1),
})
export type MachineCapabilities = z.infer<typeof MachineCapabilitiesSchema>

export function defaultCapabilities(mode: ToolingMode = 'manual'): MachineCapabilities {
  const isManual = mode === 'manual'
  return {
    tool_change: {
      mode,
      command_source: mode === 'firmware' ? 'machine' : mode === 'host_macro' ? 'host' : 'operator',
      recovery_policy: 'pause_and_prompt',
      manual_prompt: isManual
        ? {
            title: 'Change pen',
            body: 'Insert pen {color} into the holder, then press Resume.',
            timeout_s: null,
          }
        : null,
      host_macro: [],
    },
    has_pen_sensor: false,
    has_sheet_loader: false,
    max_pens_in_magazine: 1,
  }
}
