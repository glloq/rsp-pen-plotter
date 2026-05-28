import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  deleteQueuedRun,
  enqueuePrint,
  listQueue,
  queueRunAction,
  type PrintRun,
} from '../api/client'
import { errorDetail } from '../api/error'
import { i18n } from '../i18n'

const ACTIVE: PrintRun['state'][] = ['queued', 'running', 'paused']

// Adaptive polling cadences. When at least one run is active we
// need fresh state to drive the cockpit; when idle we can afford
// to slow down so we don't hammer the backend or starve the event
// loop on a Pi. The transition is one-way per tick: a poll that
// returns an active run upgrades the interval immediately, an idle
// poll downgrades to the slow cadence.
const FAST_INTERVAL_MS = 2_000
const SLOW_INTERVAL_MS = 30_000

export const useQueueStore = defineStore('queue', () => {
  const runs = ref<PrintRun[]>([])
  const error = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null
  let inflight: Promise<void> | null = null

  const active = computed(() => runs.value.filter((r) => ACTIVE.includes(r.state)))

  async function load(): Promise<void> {
    // Single-flight: avoid stacking parallel /queue requests when
    // a tick fires while the previous one is still pending (slow
    // backend, network blip). The next tick reuses the in-flight
    // promise instead of opening a second connection.
    if (inflight) return inflight
    const promise = (async () => {
      try {
        runs.value = await listQueue()
        error.value = null
      } catch (err) {
        error.value = errorDetail(err, i18n.global.t('queue.loadFailed'))
      }
    })()
    inflight = promise
    try {
      await promise
    } finally {
      inflight = null
    }
  }

  async function enqueue(name: string, profileName: string, gcode: string): Promise<void> {
    try {
      await enqueuePrint(name, profileName, gcode)
      await load()
    } catch (err) {
      error.value = errorDetail(err, i18n.global.t('queue.enqueueFailed'))
    }
  }

  async function act(id: string, action: 'pause' | 'resume' | 'cancel'): Promise<void> {
    try {
      await queueRunAction(id, action)
    } catch (err) {
      error.value = errorDetail(err, i18n.global.t('queue.actionFailed'))
    }
    await load()
  }

  async function remove(id: string): Promise<void> {
    try {
      await deleteQueuedRun(id)
    } catch (err) {
      error.value = errorDetail(err, i18n.global.t('queue.actionFailed'))
    }
    await load()
  }

  function _schedule(): void {
    if (timer !== null) clearTimeout(timer)
    // Fast cadence while a run is active (timeline cockpit needs
    // smooth progress), slow cadence when the queue is empty —
    // operators idle most of the time and don't need 2 s polling
    // for an empty queue.
    const interval = active.value.length > 0 ? FAST_INTERVAL_MS : SLOW_INTERVAL_MS
    timer = setTimeout(async () => {
      await load()
      if (timer !== null) _schedule()
    }, interval)
  }

  function startPolling(): void {
    if (timer !== null) return // idempotent
    void load().then(() => {
      if (timer === null) _schedule()
    })
    // Defensive bootstrap: schedule even before the first load
    // resolves so we don't lose ticks when the initial request
    // takes > the interval.
    if (timer === null) _schedule()
  }

  function stopPolling(): void {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  return { runs, active, error, load, enqueue, act, remove, startPolling, stopPolling }
})
