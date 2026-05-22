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

export const useQueueStore = defineStore('queue', () => {
  const runs = ref<PrintRun[]>([])
  const error = ref<string | null>(null)
  let timer: ReturnType<typeof setInterval> | null = null

  const active = computed(() => runs.value.filter((r) => ACTIVE.includes(r.state)))

  async function load(): Promise<void> {
    try {
      runs.value = await listQueue()
      error.value = null
    } catch (err) {
      error.value = errorDetail(err, i18n.global.t('queue.loadFailed'))
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

  function startPolling(): void {
    if (timer === null) timer = setInterval(load, 2000)
    void load()
  }

  function stopPolling(): void {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  return { runs, active, error, load, enqueue, act, remove, startPolling, stopPolling }
})
