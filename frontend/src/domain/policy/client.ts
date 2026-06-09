/**
 * Thin client for /policy/resolve. Returns the parsed PolicyDecision
 * or rethrows the underlying error (the modal V2 catches it and falls
 * back to the static defaults).
 *
 * In-flight + LRU cache: the resolver is a pure function of its inputs
 * (source kind, goal, palette mode, colour count, …) so the answer
 * never changes within a session for the same key. Repeated editor
 * opens — and intent toggles back to a previously-selected option —
 * would otherwise re-pay the network round-trip on every click. The
 * cache also collapses concurrent identical requests (e.g. a quick
 * goal toggle that fires Resolve twice) onto a single response so the
 * second call piggybacks on the first instead of racing it.
 */
import { api } from '../../api/client'
import { PolicyDecisionSchema, type PolicyDecision, type PolicyInput } from './schemas'

// Compact stable key for the cache. Field order is fixed, primitives
// only — no JSON.stringify allocations on the hot path.
function cacheKey(input: PolicyInput): string {
  return [
    input.source_kind,
    input.goal,
    input.palette_mode,
    input.available_colors_count | 0,
    input.image_megapixels ?? '',
    input.layer_count_estimate | 0,
    input.is_mono_pen_machine ? 1 : 0,
  ].join('|')
}

// Cap is generous: each entry is a tiny object, and the input space
// per session is bounded by the operator's intent / palette toggles
// across whatever placements they edit.
const POLICY_CACHE_MAX = 64
const decisionCache = new Map<string, PolicyDecision>()
const inflight = new Map<string, Promise<PolicyDecision>>()

export async function resolveAlgorithmPolicy(input: PolicyInput): Promise<PolicyDecision> {
  const key = cacheKey(input)
  const cached = decisionCache.get(key)
  if (cached) {
    // Refresh LRU recency so frequently-toggled keys survive eviction.
    decisionCache.delete(key)
    decisionCache.set(key, cached)
    return cached
  }
  const pending = inflight.get(key)
  if (pending) return pending
  const promise = (async () => {
    try {
      const response = await api.post('/policy/resolve', input)
      const decision = PolicyDecisionSchema.parse(response.data)
      if (decisionCache.size >= POLICY_CACHE_MAX) {
        const oldest = decisionCache.keys().next().value
        if (oldest !== undefined) decisionCache.delete(oldest)
      }
      decisionCache.set(key, decision)
      return decision
    } finally {
      inflight.delete(key)
    }
  })()
  inflight.set(key, promise)
  return promise
}

/**
 * Drop every cached resolver answer. Tests use this to keep cases
 * independent; production code has no reason to call it (the cache is
 * pure-function safe for the lifetime of the page).
 */
export function clearAlgorithmPolicyCache(): void {
  decisionCache.clear()
  inflight.clear()
}
