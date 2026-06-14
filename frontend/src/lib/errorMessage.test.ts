import { describe, expect, it } from 'vitest'

import { errorMessage } from './errorMessage'

describe('errorMessage', () => {
  it('reads the message off an Error', () => {
    expect(errorMessage(new Error('boom'))).toBe('boom')
  })

  it('passes a thrown string through', () => {
    expect(errorMessage('plain failure')).toBe('plain failure')
  })

  it('reads a string ``message`` off a plain object (axios-like)', () => {
    expect(errorMessage({ message: 'request failed' })).toBe('request failed')
  })

  it('falls back to String() for objects without a string message', () => {
    expect(errorMessage({ code: 500 })).toBe('[object Object]')
  })

  it('handles null and undefined without throwing', () => {
    expect(errorMessage(null)).toBe('null')
    expect(errorMessage(undefined)).toBe('undefined')
  })
})
