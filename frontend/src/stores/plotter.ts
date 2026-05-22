import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  plotterCommand,
  plotterConnect,
  plotterDisconnect,
  plotterHome,
  plotterJog,
  plotterRun,
  websocketUrl,
  type PlotterStatus,
} from '../api/client'

export const usePlotterStore = defineStore('plotter', () => {
  const status = ref<PlotterStatus>({
    connected: false,
    total: 0,
    sent: 0,
    acked: 0,
    state: 'idle',
  })
  const port = ref('/dev/ttyUSB0')
  const baudrate = ref(115200)
  const error = ref<string | null>(null)
  let socket: WebSocket | null = null

  const progress = computed(() =>
    status.value.total > 0 ? status.value.acked / status.value.total : 0,
  )

  function openSocket(): void {
    if (socket) return
    socket = new WebSocket(websocketUrl('/ws/plotter'))
    socket.onmessage = (event) => {
      status.value = JSON.parse(event.data) as PlotterStatus
    }
    socket.onclose = () => {
      socket = null
    }
  }

  async function withErrors(fn: () => Promise<PlotterStatus>): Promise<void> {
    error.value = null
    try {
      status.value = await fn()
    } catch {
      error.value = 'Plotter command failed (is a device connected?).'
    }
  }

  async function connect(): Promise<void> {
    await withErrors(() => plotterConnect(port.value, baudrate.value))
    if (status.value.connected) openSocket()
  }

  const disconnect = (): Promise<void> => withErrors(() => plotterDisconnect())
  const jog = (dx: number, dy: number, profileName: string): Promise<void> =>
    withErrors(() => plotterJog(dx, dy, profileName))
  const home = (profileName: string): Promise<void> =>
    withErrors(() => plotterHome(profileName))
  const run = (gcode: string): Promise<void> => withErrors(() => plotterRun(gcode))
  const pause = (): Promise<void> => withErrors(() => plotterCommand('pause'))
  const resume = (): Promise<void> => withErrors(() => plotterCommand('resume'))
  const abort = (): Promise<void> => withErrors(() => plotterCommand('abort'))

  return {
    status,
    port,
    baudrate,
    error,
    progress,
    connect,
    disconnect,
    jog,
    home,
    run,
    pause,
    resume,
    abort,
  }
})
