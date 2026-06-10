// Extract a human-readable message from an API error response.
//
// The backend's global error handler (backend/pen_plotter/errors.py)
// renders EVERY error as the v0.2 envelope ``{code, message, details,
// path}`` — including legacy ``HTTPException`` raises, whose ``detail``
// payload is coerced into ``message`` + ``details``. The envelope is
// therefore the primary shape; the bare ``{detail: …}`` forms are kept
// as fallbacks for older backends / proxies that bypass the handler.

interface PydanticFieldError {
  loc?: unknown
  msg?: unknown
}

function formatValidationErrors(errors: unknown[]): string[] {
  const lines: string[] = []
  for (const entry of errors) {
    if (!entry || typeof entry !== 'object') continue
    const { loc, msg } = entry as PydanticFieldError
    const field = Array.isArray(loc)
      ? loc
          .filter((part) => part !== 'body')
          .map((part) => String(part))
          .join('.')
      : ''
    const message = typeof msg === 'string' ? msg : ''
    if (field && message) lines.push(`${field}: ${message}`)
    else if (message) lines.push(message)
  }
  return lines
}

export function errorDetail(err: unknown, fallback: string): string {
  const response = (err as { response?: { data?: unknown } })?.response
  const data = response?.data

  // ---- v0.2 envelope: {code, message, details, path} ----
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    const env = data as { code?: unknown; message?: unknown; details?: unknown }
    if (typeof env.message === 'string' && env.message.length > 0) {
      const details = (
        env.details && typeof env.details === 'object' ? env.details : {}
      ) as Record<string, unknown>
      // Pydantic input rejections: surface the field errors instead of
      // the generic "request validation failed" so the operator learns
      // WHICH field was rejected and why.
      if (env.code === 'validation_error' && Array.isArray(details.errors)) {
        const lines = formatValidationErrors(details.errors as unknown[])
        if (lines.length) {
          const shown = lines.slice(0, 5)
          const more = lines.length > shown.length ? ` (+${lines.length - shown.length} more)` : ''
          return `${env.message}: ${shown.join('; ')}${more}`
        }
      }
      // Legacy dict-detail raises (e.g. /system/update's {message, log,
      // returncode}) arrive coerced as message + the rest in details.
      // Surface the log when present — it's the actionable bit.
      const rc = typeof details.returncode === 'number' ? ` (exit ${details.returncode})` : ''
      const log = typeof details.log === 'string' ? details.log.trim() : ''
      return [`${env.message}${rc}`, log].filter(Boolean).join('\n\n')
    }
  }

  // ---- Legacy bare FastAPI shape: {detail: string | dict} ----
  const detail = (data as { detail?: unknown } | undefined)?.detail
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
