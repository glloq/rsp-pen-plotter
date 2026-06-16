// Client for the off-main-thread G-code parser (audit B2).
//
// ``parseGcodeMaybeAsync`` offloads ``parseGcode`` to a Web Worker in the
// browser and falls back to a synchronous main-thread parse anywhere a
// Worker isn't available (SSR, unit tests under happy-dom, very old
// browsers, or after a worker load failure). The return type is
// deliberately ``SimResult | Promise<SimResult>`` rather than always a
// Promise: a *synchronous* return keeps the playback ``reparse`` path
// synchronous so existing callers/tests that read ``sim`` right after
// still observe the result, while the worker path resolves later.

import { parseGcode, type ParseOptions, type SimResult } from './gcode'

interface PendingResolver {
  resolve: (result: SimResult) => void
  reject: (err: Error) => void
}

interface WorkerResponse {
  id: number
  ok: boolean
  result?: SimResult
  error?: string
}

let worker: Worker | null = null
// Latches true the first time a worker fails to construct or run, so we
// stop retrying and parse on the main thread for the rest of the session.
let workerUnavailable = false
let seq = 0
const pending = new Map<number, PendingResolver>()

function failAllPending(message: string): void {
  for (const p of pending.values()) p.reject(new Error(message))
  pending.clear()
}

function getWorker(): Worker | null {
  if (workerUnavailable) return null
  if (typeof Worker === 'undefined') return null
  if (worker) return worker
  try {
    worker = new Worker(new URL('./gcodeParser.worker.ts', import.meta.url), { type: 'module' })
    worker.onmessage = (e: MessageEvent<WorkerResponse>) => {
      const { id, ok, result, error } = e.data
      const p = pending.get(id)
      if (!p) return
      pending.delete(id)
      if (ok && result) p.resolve(result)
      else p.reject(new Error(error ?? 'gcode parse failed'))
    }
    worker.onerror = () => {
      // The worker module failed to load/run — give up on it for good and
      // reject in-flight requests so the caller can fall back / retry.
      workerUnavailable = true
      failAllPending('gcode worker error')
      worker?.terminate()
      worker = null
    }
    return worker
  } catch {
    workerUnavailable = true
    return null
  }
}

/**
 * Parse G-code, off the main thread when possible. Returns the result
 * synchronously when no Worker is available (so the value is observable
 * on the same tick), or a Promise resolving to it when the worker handles
 * the parse.
 */
export function parseGcodeMaybeAsync(
  code: string,
  opts: ParseOptions,
): SimResult | Promise<SimResult> {
  const w = getWorker()
  if (!w) {
    // No worker: parse on the main thread, synchronously, so the caller's
    // ``instanceof Promise`` check takes the sync branch.
    return parseGcode(code, opts)
  }
  const id = ++seq
  return new Promise<SimResult>((resolve, reject) => {
    pending.set(id, { resolve, reject })
    try {
      w.postMessage({ id, code, opts })
    } catch (err) {
      // Posting failed (e.g. an un-cloneable option slipped in) — drop the
      // worker and fall back to a main-thread parse so playback still works.
      pending.delete(id)
      workerUnavailable = true
      worker?.terminate()
      worker = null
      try {
        resolve(parseGcode(code, opts))
      } catch (parseErr) {
        reject(parseErr instanceof Error ? parseErr : new Error(String(parseErr)))
      }
      void err
    }
  })
}

/** Tear down the shared worker (idempotent). Optional — the worker is a
 *  cheap idle singleton, so callers needn't dispose on unmount. */
export function disposeGcodeWorker(): void {
  failAllPending('gcode worker disposed')
  if (worker) {
    worker.terminate()
    worker = null
  }
}
