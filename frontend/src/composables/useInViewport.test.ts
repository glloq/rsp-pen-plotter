// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import { useInViewport } from './useInViewport'

// Minimal IntersectionObserver stub: records observed elements and lets a
// test fire an intersection on demand (happy-dom's own IO never fires).
// Locally-typed (not the DOM IntersectionObserver* type names) to keep
// eslint's no-undef happy in the test file.
type IOEntry = { isIntersecting: boolean; target: Element }
type IOCallback = (entries: IOEntry[], observer: unknown) => void

class MockIO {
  static instances: MockIO[] = []
  cb: IOCallback
  options?: { rootMargin?: string }
  observed: Element[] = []
  disconnected = false
  constructor(cb: IOCallback, options?: { rootMargin?: string }) {
    this.cb = cb
    this.options = options
    MockIO.instances.push(this)
  }
  observe(el: Element): void {
    this.observed.push(el)
  }
  disconnect(): void {
    this.disconnected = true
  }
  unobserve(): void {}
  takeRecords(): IOEntry[] {
    return []
  }
  fire(isIntersecting: boolean): void {
    this.cb(
      this.observed.map((target) => ({ isIntersecting, target })),
      this,
    )
  }
}

afterEach(() => {
  MockIO.instances = []
  vi.unstubAllGlobals()
})

describe('useInViewport', () => {
  it('starts hidden and latches visible on first intersection, then disconnects', () => {
    vi.stubGlobal('IntersectionObserver', MockIO)
    const el = ref<HTMLElement | null>(document.createElement('div'))
    const scope = effectScope()
    let visible!: ReturnType<typeof useInViewport>
    scope.run(() => {
      visible = useInViewport(el, { rootMargin: '123px' })
    })
    expect(visible.value).toBe(false)
    const io = MockIO.instances[0]!
    expect(io.options?.rootMargin).toBe('123px')
    expect(io.observed).toHaveLength(1)
    io.fire(true)
    expect(visible.value).toBe(true)
    // ``once`` (default) disconnects after the first hit.
    expect(io.disconnected).toBe(true)
    scope.stop()
  })

  it('does not flip visible while the element stays off screen', () => {
    vi.stubGlobal('IntersectionObserver', MockIO)
    const el = ref<HTMLElement | null>(document.createElement('div'))
    const scope = effectScope()
    let visible!: ReturnType<typeof useInViewport>
    scope.run(() => {
      visible = useInViewport(el)
    })
    MockIO.instances[0]!.fire(false)
    expect(visible.value).toBe(false)
    scope.stop()
  })

  it('tracks visibility both ways when once is false', () => {
    vi.stubGlobal('IntersectionObserver', MockIO)
    const el = ref<HTMLElement | null>(document.createElement('div'))
    const scope = effectScope()
    let visible!: ReturnType<typeof useInViewport>
    scope.run(() => {
      visible = useInViewport(el, { once: false })
    })
    const io = MockIO.instances[0]!
    io.fire(true)
    expect(visible.value).toBe(true)
    expect(io.disconnected).toBe(false)
    io.fire(false)
    expect(visible.value).toBe(false)
    scope.stop()
  })

  it('degrades to eager (visible=true) when IntersectionObserver is unavailable', () => {
    vi.stubGlobal('IntersectionObserver', undefined)
    const el = ref<HTMLElement | null>(document.createElement('div'))
    const scope = effectScope()
    let visible!: ReturnType<typeof useInViewport>
    scope.run(() => {
      visible = useInViewport(el)
    })
    expect(visible.value).toBe(true)
    scope.stop()
  })

  it('disconnects the observer when the scope is disposed', () => {
    vi.stubGlobal('IntersectionObserver', MockIO)
    const el = ref<HTMLElement | null>(document.createElement('div'))
    const scope = effectScope()
    scope.run(() => {
      useInViewport(el)
    })
    const io = MockIO.instances[0]!
    expect(io.disconnected).toBe(false)
    scope.stop()
    expect(io.disconnected).toBe(true)
  })
})
