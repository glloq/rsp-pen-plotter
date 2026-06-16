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
import { useToastStore } from './toasts'

const ACTIVE: PrintRun['state'][] = ['queued', 'running', 'paused']

// Adaptive polling cadences. When at least one run is active we
// need fresh state to drive the cockpit; when idle we can afford
// to slow down so we don't hammer the backend or starve the event
// loop on a Pi. The transition is one-way per tick: a poll that
// returns an active run upgrades the interval immediately, an idle
// poll downgrades to the slow cadence.
const FAST_INTERVAL_MS = 3_000
const SLOW_INTERVAL_MS = 30_000
// Exponential backoff cap when /queue keeps failing — protects the Pi from
// reconnect storms during a flaky network or a backend restart.
const MAX_BACKOFF_FACTOR = 4

export const useQueueStore = defineStore('queue', () => {
  const runs = ref<PrintRun[]>([])
  const error = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null
  let inflight: Promise<void> | null = null
  let consecutiveErrors = 0
  // Run ids with an action (pause/resume/cancel/delete) in flight. The
  // cockpit binds button ``:disabled`` to ``isBusy(id)`` and the actions
  // early-return while busy, so a double-click can't fire a second
  // round-trip before the first reloads the queue. ``enqueuing`` is the
  // same guard for the id-less enqueue path.
  const busyIds = ref<ReadonlySet<string>>(new Set())
  const enqueuing = ref(false)
  const isBusy = (id: string): boolean => busyIds.value.has(id)
  function setBusy(id: string, value: boolean): void {
    const next = new Set(busyIds.value)
    if (value) next.add(id)
    else next.delete(id)
    busyIds.value = next
  }

  const active = computed(() => runs.value.filter((r) => ACTIVE.includes(r.state)))

  // Last-seen skip count per run id. Used to detect *new* skips
  // between polls so we only fire one critical toast per skip event,
  // not on every subsequent poll that still reports the same list.
  // Primed silently on the first load so historical skips from a
  // previous session don't pop a stale toast at boot.
  const lastSeenSkips = new Map<string, number>()
  let primedSkips = false

  async function load(): Promise<void> {
    // Single-flight: avoid stacking parallel /queue requests when
    // a tick fires while the previous one is still pending (slow
    // backend, network blip). The next tick reuses the in-flight
    // promise instead of opening a second connection.
    if (inflight) return inflight
    const promise = (async () => {
      try {
        const next = await listQueue()
        // Detect newly-skipped layers between polls and surface them
        // as a critical (persistent) toast so the operator can't
        // miss that the recovery policy fired. ``skipped_layers`` is
        // append-only on the backend, so size delta == new skips.
        const toasts = useToastStore()
        for (const run of next) {
          const prev = lastSeenSkips.get(run.id) ?? 0
          const current = (run.skipped_layers ?? []).length
          if (primedSkips && current > prev) {
            const newOnes = (run.skipped_layers ?? []).slice(prev)
            toasts.critical(
              i18n.global.t('queue.skipNotice', {
                name: run.name,
                layers: newOnes.join(', '),
              }),
            )
          }
          lastSeenSkips.set(run.id, current)
        }
        // Drop bookkeeping for runs that have left the queue (completed,
        // cancelled, deleted) so the Map can't grow unbounded across a
        // long-lived session — one entry would otherwise linger forever
        // per run id ever seen.
        if (lastSeenSkips.size > next.length) {
          const live = new Set(next.map((r) => r.id))
          for (const id of lastSeenSkips.keys()) {
            if (!live.has(id)) lastSeenSkips.delete(id)
          }
        }
        primedSkips = true
        runs.value = next
        error.value = null
        consecutiveErrors = 0
      } catch (err) {
        consecutiveErrors = Math.min(consecutiveErrors + 1, MAX_BACKOFF_FACTOR)
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
    if (enqueuing.value) return
    enqueuing.value = true
    try {
      await enqueuePrint(name, profileName, gcode)
      await load()
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('queue.enqueueFailed'))
      error.value = message
      useToastStore().error(message)
    } finally {
      enqueuing.value = false
    }
  }

  async function act(id: string, action: 'pause' | 'resume' | 'cancel'): Promise<void> {
    if (busyIds.value.has(id)) return
    setBusy(id, true)
    try {
      await queueRunAction(id, action)
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('queue.actionFailed'))
      error.value = message
      useToastStore().error(message)
    } finally {
      await load()
      setBusy(id, false)
    }
  }

  async function remove(id: string): Promise<void> {
    if (busyIds.value.has(id)) return
    setBusy(id, true)
    try {
      await deleteQueuedRun(id)
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('queue.actionFailed'))
      error.value = message
      useToastStore().error(message)
    } finally {
      await load()
      setBusy(id, false)
    }
  }

  const isHidden = (): boolean => typeof document !== 'undefined' && document.hidden

  function _schedule(): void {
    if (timer !== null) clearTimeout(timer)
    // Fast cadence while a run is active (timeline cockpit needs
    // smooth progress), slow cadence when the queue is empty —
    // operators idle most of the time and don't need 2 s polling
    // for an empty queue. A backgrounded tab also drops to the slow
    // cadence even with an active run: nobody's watching the cockpit,
    // so 3 s polling just burns the Pi's event loop. The visibility
    // listener snaps back to fast + refreshes immediately on return.
    const base = !isHidden() && active.value.length > 0 ? FAST_INTERVAL_MS : SLOW_INTERVAL_MS
    // Exponential backoff on repeated failures so a dropped backend doesn't
    // pin the Pi's event loop with reconnect attempts every 3 s.
    const interval = base * Math.pow(2, consecutiveErrors)
    timer = setTimeout(async () => {
      await load()
      if (timer !== null) _schedule()
    }, interval)
  }

  let visibilityHandler: (() => void) | null = null

  function startPolling(): void {
    if (timer !== null) return // idempotent
    if (visibilityHandler === null && typeof document !== 'undefined') {
      visibilityHandler = () => {
        // On return to the foreground, refresh immediately (the slow-cadence
        // tick may be far off) and reschedule at the now-appropriate cadence.
        if (!document.hidden) void load()
        _schedule()
      }
      document.addEventListener('visibilitychange', visibilityHandler)
    }
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
    if (visibilityHandler !== null && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', visibilityHandler)
      visibilityHandler = null
    }
  }

  return {
    runs,
    active,
    error,
    enqueuing,
    isBusy,
    load,
    enqueue,
    act,
    remove,
    startPolling,
    stopPolling,
  }
})
