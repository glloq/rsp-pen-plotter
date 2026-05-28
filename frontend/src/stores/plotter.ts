import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { errorDetail } from '../api/error'
import { i18n } from '../i18n'
import { useToastStore } from './toasts'
import {
  plotterCommand,
  plotterConnect,
  plotterDisconnect,
  plotterGoto,
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
    message: null,
  })
  const port = ref('/dev/ttyUSB0')
  const baudrate = ref(115200)
  const terminator = ref<'cr' | 'lf' | 'crlf'>('lf')
  const error = ref<string | null>(null)
  let socket: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  const progress = computed(() =>
    status.value.total > 0 ? status.value.acked / status.value.total : 0,
  )

  function openSocket(): void {
    if (socket) return
    socket = new WebSocket(websocketUrl('/ws/plotter'))
    socket.onmessage = (event) => {
      try {
        status.value = JSON.parse(event.data) as PlotterStatus
      } catch {
        // Ignore malformed frames; keep the last known status.
      }
    }
    socket.onclose = () => {
      socket = null
      // Reconnect while we believe we're still connected to a device.
      if (status.value.connected && reconnectTimer === null) {
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null
          openSocket()
        }, 2000)
      }
    }
  }

  async function withErrors(
    fn: () => Promise<PlotterStatus>,
    progressMessage?: string,
    successMessage?: string,
  ): Promise<void> {
    error.value = null
    const toasts = useToastStore()
    const toastId = progressMessage ? toasts.progress(progressMessage) : null
    try {
      status.value = await fn()
      if (toastId !== null && successMessage) {
        toasts.update(toastId, 'success', successMessage, 3000)
      } else if (toastId !== null) {
        toasts.dismiss(toastId)
      }
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('plotter.commandFailed'))
      error.value = message
      if (toastId !== null) {
        toasts.update(toastId, 'error', message, 6000)
      } else {
        toasts.error(message)
      }
    }
  }

  async function connect(): Promise<void> {
    await withErrors(
      () => plotterConnect(port.value, baudrate.value, terminator.value),
      i18n.global.t('toast.plotterConnecting'),
      i18n.global.t('toast.plotterConnected'),
    )
    if (status.value.connected) openSocket()
  }

  const disconnect = (): Promise<void> => withErrors(() => plotterDisconnect())
  const jog = (dx: number, dy: number, profileName: string): Promise<void> =>
    withErrors(() => plotterJog(dx, dy, profileName))
  const goto = (x: number, y: number, profileName: string): Promise<void> =>
    withErrors(() => plotterGoto(x, y, profileName))
  const home = (profileName: string): Promise<void> => withErrors(() => plotterHome(profileName))
  const run = (gcode: string): Promise<void> =>
    withErrors(
      () => plotterRun(gcode),
      i18n.global.t('toast.plotterSending'),
      i18n.global.t('toast.plotterSent'),
    )
  const pause = (): Promise<void> => withErrors(() => plotterCommand('pause'))
  const resume = (): Promise<void> => withErrors(() => plotterCommand('resume'))
  const abort = (): Promise<void> => withErrors(() => plotterCommand('abort'))

  // Mid-run device disconnect is operator-blocking: the job halts,
  // the head position becomes unreliable, and silent recovery would
  // leave the operator confused. Detect the transition (connected →
  // disconnected) while a run is in progress and push a persistent
  // critical toast so the alert can't vanish behind other notifs.
  // Array-form ``watch`` so Vue compares each scalar source by
  // reference; an object-literal getter would re-trigger on every
  // WebSocket frame even when the relevant fields didn't move.
  watch(
    [
      () => status.value.connected,
      () => status.value.state,
    ],
    ([nextConnected, _nextState], [prevConnected, prevState]) => {
      const wasRunning = prevState === 'running' || prevState === 'paused'
      if (prevConnected && !nextConnected && wasRunning) {
        useToastStore().critical(i18n.global.t('plotter.deviceLost'))
      }
    },
  )

  return {
    status,
    port,
    baudrate,
    terminator,
    error,
    progress,
    connect,
    disconnect,
    jog,
    goto,
    home,
    run,
    pause,
    resume,
    abort,
  }
})
