// Progressive preview SSE client (roadmap C.7).
//
// Wraps EventSource around the /preview/stream endpoint. Exposes
// reactive progress + last partial frame, plus start/stop/cleanup
// so a Vue component can use it as `const stream = useProgressiveStream()`
// and bind directly into the template.

import { onUnmounted, ref } from 'vue'

export type ProgressKind = 'start' | 'progress' | 'partial' | 'done' | 'error'

export interface ProgressEvent {
  kind: ProgressKind
  sequence: number
  elapsed_ms: number
  payload: Record<string, unknown>
}

export interface StreamHandle {
  // Latest payload received, by kind. Useful to bind individual chips.
  start: Readonly<ReturnType<typeof ref<ProgressEvent | null>>>
  lastProgress: Readonly<ReturnType<typeof ref<ProgressEvent | null>>>
  lastPartial: Readonly<ReturnType<typeof ref<ProgressEvent | null>>>
  done: Readonly<ReturnType<typeof ref<ProgressEvent | null>>>
  error: Readonly<ReturnType<typeof ref<string | null>>>
  // True between open() and either done/error.
  active: Readonly<ReturnType<typeof ref<boolean>>>
  // Convenience: percent from the most recent progress event (0-100).
  percent: Readonly<ReturnType<typeof ref<number>>>
  open: (url: string) => void
  close: () => void
}

/**
 * `eventSourceFactory` lets tests inject a stub. In the browser the
 * default global EventSource is used.
 */
export function useProgressiveStream(
  eventSourceFactory: (url: string) => EventSource = (u) => new EventSource(u),
): StreamHandle {
  const start = ref<ProgressEvent | null>(null)
  const lastProgress = ref<ProgressEvent | null>(null)
  const lastPartial = ref<ProgressEvent | null>(null)
  const done = ref<ProgressEvent | null>(null)
  const errorMsg = ref<string | null>(null)
  const active = ref<boolean>(false)
  const percent = ref<number>(0)

  let source: EventSource | null = null

  function close(): void {
    if (source) {
      source.close()
      source = null
    }
    active.value = false
  }

  function parse(event: MessageEvent, kind: ProgressKind): ProgressEvent | null {
    try {
      const data = JSON.parse(event.data) as ProgressEvent
      data.kind = kind
      return data
    } catch {
      return null
    }
  }

  function open(url: string): void {
    close()
    errorMsg.value = null
    start.value = null
    lastProgress.value = null
    lastPartial.value = null
    done.value = null
    percent.value = 0
    active.value = true
    source = eventSourceFactory(url)

    source.addEventListener('start', (e) => {
      const parsed = parse(e as MessageEvent, 'start')
      if (parsed) start.value = parsed
    })
    source.addEventListener('progress', (e) => {
      const parsed = parse(e as MessageEvent, 'progress')
      if (!parsed) return
      lastProgress.value = parsed
      const p = parsed.payload.percent
      if (typeof p === 'number') percent.value = p
    })
    source.addEventListener('partial', (e) => {
      const parsed = parse(e as MessageEvent, 'partial')
      if (parsed) lastPartial.value = parsed
    })
    source.addEventListener('done', (e) => {
      const parsed = parse(e as MessageEvent, 'done')
      if (parsed) done.value = parsed
      percent.value = 100
      close()
    })
    source.addEventListener('error', () => {
      errorMsg.value = errorMsg.value ?? 'connection error'
      close()
    })
  }

  onUnmounted(close)

  return { start, lastProgress, lastPartial, done, error: errorMsg, active, percent, open, close }
}
