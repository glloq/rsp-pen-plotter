/**
 * Thin client for /policy/resolve. Returns the parsed PolicyDecision
 * or rethrows the underlying error (the modal V2 catches it and falls
 * back to the static defaults). No cache here — the resolver is pure
 * and called only when the operator clicks Next on the Intent step.
 */
import { api } from '../../api/client'
import { PolicyDecisionSchema, type PolicyDecision, type PolicyInput } from './schemas'

export async function resolveAlgorithmPolicy(input: PolicyInput): Promise<PolicyDecision> {
  const response = await api.post('/policy/resolve', input)
  return PolicyDecisionSchema.parse(response.data)
}
