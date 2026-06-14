// Normalise an unknown thrown value to a human-readable string without
// assuming it is an ``Error`` instance. A rejected ``fetch`` body, a
// thrown string, or ``null`` would all crash the common
// ``(err as Error).message`` cast; this never does.
export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  if (typeof error === 'string') return error
  if (error == null) return String(error)
  // Objects that carry a string ``message`` (axios-like errors, plain
  // ``{ message }`` payloads) read better than ``[object Object]``.
  if (typeof error === 'object' && 'message' in error) {
    const message = (error as { message: unknown }).message
    if (typeof message === 'string') return message
  }
  return String(error)
}
