import { describe, expect, it } from 'vitest'
import { errorDetail } from './error'

function axiosErr(data: unknown): unknown {
  return { response: { data } }
}

describe('errorDetail', () => {
  it('reads message from the v0.2 error envelope', () => {
    const err = axiosErr({
      code: 'not_found',
      message: 'job cache entry expired',
      details: {},
      path: '/rerender',
    })
    expect(errorDetail(err, 'fallback')).toBe('job cache entry expired')
  })

  it('surfaces field errors for validation_error envelopes', () => {
    const err = axiosErr({
      code: 'validation_error',
      message: 'request validation failed',
      details: {
        errors: [
          { loc: ['body', 'font_size_mm'], msg: 'value is not a valid float', type: 'float' },
          { loc: ['body', 'margin_mm'], msg: 'value must be positive', type: 'value_error' },
        ],
      },
      path: '/generate',
    })
    const out = errorDetail(err, 'fallback')
    expect(out).toContain('request validation failed')
    expect(out).toContain('font_size_mm: value is not a valid float')
    expect(out).toContain('margin_mm: value must be positive')
  })

  it('keeps the envelope message when validation details are unusable', () => {
    const err = axiosErr({
      code: 'validation_error',
      message: 'request validation failed',
      details: { errors: 'not-a-list' },
    })
    expect(errorDetail(err, 'fallback')).toBe('request validation failed')
  })

  it('appends log + returncode from coerced dict-detail envelopes', () => {
    const err = axiosErr({
      code: 'internal_server_error',
      message: 'update failed',
      details: { log: 'git pull: conflict', returncode: 1 },
      path: '/system/update',
    })
    expect(errorDetail(err, 'fallback')).toBe('update failed (exit 1)\n\ngit pull: conflict')
  })

  it('still reads the legacy {detail: string} shape', () => {
    expect(errorDetail(axiosErr({ detail: 'old style message' }), 'fallback')).toBe(
      'old style message',
    )
  })

  it('still reads the legacy {detail: {message, log, returncode}} shape', () => {
    const err = axiosErr({
      detail: { message: 'update failed', log: 'stderr here', returncode: 2 },
    })
    expect(errorDetail(err, 'fallback')).toBe('update failed (exit 2)\n\nstderr here')
  })

  it('summarises non-JSON string bodies', () => {
    const out = errorDetail(axiosErr('<html><body>Bad Gateway</body></html>'), 'fallback')
    expect(out).toContain('fallback')
    expect(out).toContain('Bad Gateway')
  })

  it('returns the fallback for network errors with no response', () => {
    expect(errorDetail(new Error('Network Error'), 'fallback')).toBe('fallback')
    expect(errorDetail(undefined, 'fallback')).toBe('fallback')
  })

  it('returns the fallback for empty bodies', () => {
    expect(errorDetail(axiosErr(''), 'fallback')).toBe('fallback')
    expect(errorDetail(axiosErr(null), 'fallback')).toBe('fallback')
  })
})
