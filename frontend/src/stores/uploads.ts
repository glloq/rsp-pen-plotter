import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { validateUploadFile } from '../api/uploadValidation'
import { useLibraryStore } from './library'
import { useToastStore } from './toasts'

// Upload orchestration shared by every entry point (Files pane button,
// pane drop, window-level drop). Owns the batch lifecycle so the
// ``UploadProgressModal`` can render live per-file progress, and so files
// dropped from anywhere flow through the same concurrency + validation
// path instead of each caller re-implementing its own loop.

// How many files we push to the server at once. The backend off-loads each
// conversion to its own thread, so a small fan-out shortens wall-clock for
// multi-file imports without burying a Pi-class CPU. Sequential before; 3
// is a deliberate, conservative bump.
const MAX_CONCURRENT = 3

export type UploadItemStatus =
  | 'pending'
  | 'uploading'
  | 'converting'
  | 'done'
  | 'existing'
  | 'error'
  | 'cancelled'

export interface UploadItem {
  /** Stable id for keying the list and matching the abort controller. */
  id: string
  name: string
  size: number
  status: UploadItemStatus
  /** Network-transfer percent (0-100). Meaningful while ``uploading``. */
  percent: number
  /** Number of converter warnings, surfaced as a badge once ``done``. */
  warningCount: number
}

const TERMINAL: ReadonlySet<UploadItemStatus> = new Set(['done', 'existing', 'error', 'cancelled'])

export const useUploadsStore = defineStore('uploads', () => {
  const items = ref<UploadItem[]>([])
  // Modal visibility. Distinct from "is a batch running" so a finished
  // batch with warnings/errors can linger until the operator dismisses it.
  const visible = ref(false)

  // Side tables kept off the reactive graph: File blobs are large and the
  // abort controllers aren't render state.
  const files = new Map<string, File>()
  const controllers = new Map<string, AbortController>()
  // FIFO queue of pending item ids drained by the worker pool.
  const queue: string[] = []
  let runningWorkers = 0
  let seq = 0

  const active = computed(() => items.value.some((i) => !TERMINAL.has(i.status)))
  const total = computed(() => items.value.length)
  const doneCount = computed(() => items.value.filter((i) => TERMINAL.has(i.status)).length)
  const hasErrors = computed(() => items.value.some((i) => i.status === 'error'))
  const hasWarnings = computed(() => items.value.some((i) => i.warningCount > 0))

  function patch(id: string, change: Partial<UploadItem>): void {
    const idx = items.value.findIndex((i) => i.id === id)
    if (idx < 0) return
    items.value[idx] = { ...items.value[idx]!, ...change }
  }

  // Validate and enqueue a batch. Rejected files are added as ``error``
  // items (with a toast) so the modal explains why they were dropped,
  // rather than silently vanishing. Accepted files queue for the pool.
  // Safe to call while a batch is already running — new files just append.
  function start(input: File[] | FileList): void {
    const incoming = Array.from(input)
    if (incoming.length === 0) return
    // A fresh batch after the previous one finished clears the old results
    // so the modal doesn't accumulate stale rows across unrelated imports.
    if (!active.value) reset()
    visible.value = true
    const toasts = useToastStore()
    for (const file of incoming) {
      const id = `u${seq++}`
      const issue = validateUploadFile(file)
      if (issue) {
        items.value.push({
          id,
          name: file.name,
          size: file.size,
          status: 'error',
          percent: 0,
          warningCount: 0,
        })
        toasts.error(`${file.name}: ${issue.message}`)
        continue
      }
      files.set(id, file)
      items.value.push({
        id,
        name: file.name,
        size: file.size,
        status: 'pending',
        percent: 0,
        warningCount: 0,
      })
      queue.push(id)
    }
    ensureWorkers()
  }

  function ensureWorkers(): void {
    while (runningWorkers < MAX_CONCURRENT && queue.length > 0) {
      runningWorkers += 1
      void worker()
    }
  }

  async function worker(): Promise<void> {
    try {
      for (;;) {
        const id = queue.shift()
        if (id === undefined) break
        const item = items.value.find((i) => i.id === id)
        if (!item || item.status !== 'pending') continue
        await processItem(id)
      }
    } finally {
      runningWorkers -= 1
    }
  }

  async function processItem(id: string): Promise<void> {
    const file = files.get(id)
    if (!file) {
      patch(id, { status: 'error' })
      return
    }
    const library = useLibraryStore()
    const controller = new AbortController()
    controllers.set(id, controller)
    patch(id, { status: 'uploading', percent: 0 })
    try {
      // ``silent`` is left off: the library store already raises the right
      // toasts for warnings, dedup info and failures — the modal layers the
      // live per-file status on top rather than duplicating those messages.
      const result = await library.upload(file, {
        signal: controller.signal,
        onProgress: (percent: number) => {
          if (controller.signal.aborted) return
          // 100% means the bytes are fully sent; the server now converts
          // (untimed), which we surface as a distinct phase.
          patch(id, {
            percent,
            status: percent >= 100 ? 'converting' : 'uploading',
          })
        },
      })
      if (result) {
        patch(id, {
          status: result.existing ? 'existing' : 'done',
          percent: 100,
          warningCount: result.file.warnings?.length ?? 0,
        })
      } else if (controller.signal.aborted) {
        patch(id, { status: 'cancelled' })
      } else {
        patch(id, { status: 'error' })
      }
    } catch {
      patch(id, { status: controller.signal.aborted ? 'cancelled' : 'error' })
    } finally {
      controllers.delete(id)
      files.delete(id)
    }
  }

  // Abort one in-flight file. Pending (not-yet-started) items are dropped
  // from the queue and marked cancelled directly.
  function cancelItem(id: string): void {
    const item = items.value.find((i) => i.id === id)
    if (!item || TERMINAL.has(item.status)) return
    const controller = controllers.get(id)
    if (controller) {
      controller.abort()
    } else {
      const qi = queue.indexOf(id)
      if (qi >= 0) queue.splice(qi, 1)
      files.delete(id)
      patch(id, { status: 'cancelled' })
    }
  }

  function cancelAll(): void {
    queue.length = 0
    for (const item of items.value) {
      if (!TERMINAL.has(item.status)) cancelItem(item.id)
    }
  }

  function reset(): void {
    items.value = []
    files.clear()
    controllers.clear()
    queue.length = 0
  }

  // Dismiss the modal. Refuses while a batch is still running so the
  // operator can't lose sight of in-flight work — they cancel first.
  function close(): void {
    if (active.value) return
    visible.value = false
    reset()
  }

  return {
    items,
    visible,
    active,
    total,
    doneCount,
    hasErrors,
    hasWarnings,
    start,
    cancelItem,
    cancelAll,
    close,
  }
})
