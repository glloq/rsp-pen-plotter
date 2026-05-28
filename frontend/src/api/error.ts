export function errorDetail(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
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
  return fallback
}
