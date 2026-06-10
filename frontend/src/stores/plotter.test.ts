// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PlotterStatus } from '../api/client'

const plotterConnect = vi.fn()
const plotterDisconnect = vi.fn()
const plotterCommand = vi.fn()

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    websocketUrl: () => 'ws://test/ws/plotter',
    plotterConnect: (...args: unknown[]) => plotterConnect(...args),
    plotterDisconnect: (...args: unknown[]) => plotterDisconnect(...args),
    plotterCommand: (...args: unknown[]) => plotterCommand(...args),
  }
})

import { usePlotterStore } from './plotter'

function makeStatus(over: Partial<PlotterStatus> = {}): PlotterStatus {
  return {
    connected: true,
    total: 100,
    sent: 0,
    acked: 0,
    state: 'running',
    message: null,
    ...over,
  } as PlotterStatus
}

// Minimal WebSocket stand-in: records instances so the test can flip
// readyState / push frames / observe close().
class FakeWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  static instances: FakeWebSocket[] = []
  url: string
  readyState = FakeWebSocket.CONNECTING
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  closed = false
  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }
  close(): void {
    this.closed = true
    this.readyState = FakeWebSocket.CLOSED
  }
}

describe('plotter store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    plotterConnect.mockReset()
    plotterDisconnect.mockReset()
    plotterCommand.mockReset()
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
  })

  it('REST responses update status when no live socket exists', async () => {
    const store = usePlotterStore()
    plotterCommand.mockResolvedValue(makeStatus({ acked: 10 }))
    await store.pause()
    expect(store.status.acked).toBe(10)
  })

  it('REST responses do not clobber WS-driven status while the socket is open', async () => {
    const store = usePlotterStore()
    plotterConnect.mockResolvedValue(makeStatus({ acked: 0 }))
    await store.connect()
    const ws = FakeWebSocket.instances[0]!
    ws.readyState = FakeWebSocket.OPEN

    // Live frame: 50 lines acked.
    ws.onmessage!({ data: JSON.stringify(makeStatus({ acked: 50 })) })
    expect(store.status.acked).toBe(50)

    // A slow REST snapshot from before the frame must NOT roll back.
    plotterCommand.mockResolvedValue(makeStatus({ acked: 12 }))
    await store.pause()
    expect(store.status.acked).toBe(50)
  })

  it('disconnect() closes the websocket and applies the REST status', async () => {
    const store = usePlotterStore()
    plotterConnect.mockResolvedValue(makeStatus())
    await store.connect()
    const ws = FakeWebSocket.instances[0]!
    ws.readyState = FakeWebSocket.OPEN

    plotterDisconnect.mockResolvedValue(makeStatus({ connected: false, state: 'idle' }))
    await store.disconnect()

    expect(ws.closed).toBe(true)
    // Socket was closed first, so the REST snapshot lands.
    expect(store.status.connected).toBe(false)
    // No reconnect: a new socket must not have been opened.
    expect(FakeWebSocket.instances).toHaveLength(1)
  })
})
