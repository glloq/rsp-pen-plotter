// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest'
import { useProgressiveStream } from './useProgressiveStream'

class FakeEventSource {
  url: string
  listeners: Map<string, ((e: MessageEvent) => void)[]> = new Map()
  closed = false
  constructor(url: string) {
    this.url = url
  }
  addEventListener(type: string, fn: (e: MessageEvent) => void): void {
    const list = this.listeners.get(type) ?? []
    list.push(fn)
    this.listeners.set(type, list)
  }
  emit(type: string, payload: Record<string, unknown>): void {
    const list = this.listeners.get(type) ?? []
    const msg = { data: JSON.stringify(payload) } as MessageEvent
    for (const fn of list) fn(msg)
  }
  close(): void {
    this.closed = true
  }
}

describe('useProgressiveStream', () => {
  it('captures the start event and exposes its payload', () => {
    let stub: FakeEventSource | null = null
    const stream = useProgressiveStream((u) => {
      stub = new FakeEventSource(u)
      return stub as unknown as EventSource
    })
    stream.open('/preview/stream?layer_count=3')
    expect(stream.active.value).toBe(true)
    stub!.emit('start', { sequence: 0, elapsed_ms: 0, payload: { layer_count: 3 } })
    expect(stream.start.value?.payload.layer_count).toBe(3)
  })

  it('updates percent from progress events', () => {
    let stub: FakeEventSource | null = null
    const stream = useProgressiveStream((u) => {
      stub = new FakeEventSource(u)
      return stub as unknown as EventSource
    })
    stream.open('/preview/stream')
    stub!.emit('progress', {
      sequence: 1,
      elapsed_ms: 10,
      payload: { layer_index: 0, percent: 33 },
    })
    expect(stream.percent.value).toBe(33)
    stub!.emit('progress', {
      sequence: 2,
      elapsed_ms: 20,
      payload: { layer_index: 1, percent: 66 },
    })
    expect(stream.percent.value).toBe(66)
  })

  it('captures partial frames separately from progress', () => {
    let stub: FakeEventSource | null = null
    const stream = useProgressiveStream((u) => {
      stub = new FakeEventSource(u)
      return stub as unknown as EventSource
    })
    stream.open('/preview/stream')
    stub!.emit('partial', { sequence: 5, elapsed_ms: 50, payload: { svg: '<svg/>' } })
    expect(stream.lastPartial.value?.payload.svg).toBe('<svg/>')
  })

  it('closes on done and snaps percent to 100', () => {
    let stub: FakeEventSource | null = null
    const stream = useProgressiveStream((u) => {
      stub = new FakeEventSource(u)
      return stub as unknown as EventSource
    })
    stream.open('/preview/stream')
    stub!.emit('done', { sequence: 9, elapsed_ms: 100, payload: { layer_count: 3 } })
    expect(stream.done.value).not.toBeNull()
    expect(stream.percent.value).toBe(100)
    expect(stream.active.value).toBe(false)
    expect(stub!.closed).toBe(true)
  })

  it('records the error event', () => {
    let stub: FakeEventSource | null = null
    const stream = useProgressiveStream((u) => {
      stub = new FakeEventSource(u)
      return stub as unknown as EventSource
    })
    stream.open('/preview/stream')
    stub!.emit('error', {})
    expect(stream.error.value).toBe('connection error')
    expect(stream.active.value).toBe(false)
  })

  it('open() twice closes the previous stream', () => {
    const stubs: FakeEventSource[] = []
    const stream = useProgressiveStream((u) => {
      const s = new FakeEventSource(u)
      stubs.push(s)
      return s as unknown as EventSource
    })
    stream.open('/preview/stream?a=1')
    stream.open('/preview/stream?b=2')
    expect(stubs[0]!.closed).toBe(true)
    expect(stubs[1]!.closed).toBe(false)
  })
})
