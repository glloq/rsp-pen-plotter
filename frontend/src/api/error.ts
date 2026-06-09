export function errorDetail(err: unknown, fallback: string): string {
  const response = (err as { response?: { data?: unknown } })?.response
  const detail = (response?.data as { detail?: unknown } | undefined)?.detail
  if (typeof detail === 'string' && detail.length > 0) return detail
  if (detail && typeof detail === 'object') {
    // FastAPI handlers sometimes raise HTTPException with a dict detail
    // (e.g. /system/update returns {message, log, returncode}). Surface the
    // log when present — it's the actionable bit — otherwise the message.
    const obj = detail as { message?: unknown; log?: unknown; returncode?: unknown }
    const message = typeof obj.message === 'string' ? obj.message : ''
    const rc = typeof obj.returncode === 'number' ? ` (exit ${obj.returncode})` : ''
    const log = typeof obj.log === 'string' ? obj.log.trim() : ''
    if (message || log) {
      const header = message ? `${message}${rc}` : ''
      return [header, log].filter(Boolean).join('\n\n') || fallback
    }
  }
  // Non-JSON error bodies: an unhandled backend exception yields Starlette's
  // bare-text "Internal Server Error", a proxy yields an HTML page. Surface
  // a trimmed snippet so the operator gets more than axios' generic
  // "Request failed with status code NNN".
  const raw = response?.data
  if (typeof raw === 'string' && raw.trim().length > 0) {
    const text = raw
      .replace(/<[^>]*>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
    if (text) return `${fallback} — ${text.length > 300 ? `${text.slice(0, 300)}…` : text}`
  }
  return fallback
}
