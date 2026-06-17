import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  deleteTimelapse,
  downloadTimelapseVideo,
  getTimelapseStatus,
  listTimelapses,
  startTimelapse,
  stopTimelapse,
  type TimelapseStatus,
  type TimelapseSummary,
} from '../api/client'
import { errorDetail } from '../api/error'
import { i18n } from '../i18n'
import { useToastStore } from './toasts'

// Camera timelapse store: drives the recorder (start / stop) and the
// saved-timelapse library (list / delete / download). The capture itself
// runs on the backend; this store mirrors its status and the file list.
const IDLE: TimelapseStatus = {
  recording: false,
  session_id: null,
  label: '',
  frame_count: 0,
  interval_seconds: 0,
  fps: 0,
  started_at: null,
  error: null,
}

export const useTimelapseStore = defineStore('timelapse', () => {
  const status = ref<TimelapseStatus>({ ...IDLE })
  const files = ref<TimelapseSummary[]>([])
  const busy = ref(false)
  const error = ref<string | null>(null)

  async function refreshStatus(): Promise<void> {
    try {
      status.value = await getTimelapseStatus()
    } catch {
      // Transient (e.g. offline) — keep the last known status.
    }
  }

  async function refreshList(): Promise<void> {
    try {
      files.value = await listTimelapses()
      error.value = null
    } catch (err) {
      error.value = errorDetail(err, i18n.global.t('timelapse.listFailed'))
    }
  }

  async function start(
    streamUrl: string,
    intervalSeconds: number,
    fps: number,
    label: string,
  ): Promise<boolean> {
    if (busy.value) return false
    busy.value = true
    try {
      status.value = await startTimelapse(streamUrl, intervalSeconds, fps, label)
      error.value = null
      return true
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('timelapse.startFailed'))
      error.value = message
      useToastStore().error(message)
      return false
    } finally {
      busy.value = false
    }
  }

  async function stop(): Promise<void> {
    if (busy.value) return
    busy.value = true
    try {
      const summary = await stopTimelapse()
      status.value = { ...IDLE }
      await refreshList()
      useToastStore().success(i18n.global.t('timelapse.saved', { count: summary.frame_count }))
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('timelapse.stopFailed'))
      error.value = message
      useToastStore().error(message)
    } finally {
      busy.value = false
    }
  }

  async function remove(id: string): Promise<void> {
    try {
      await deleteTimelapse(id)
      await refreshList()
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('timelapse.deleteFailed'))
      error.value = message
      useToastStore().error(message)
    }
  }

  async function download(file: TimelapseSummary): Promise<void> {
    try {
      const blob = await downloadTimelapseVideo(file.id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `timelapse-${file.label || file.id}.mp4`
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('timelapse.downloadFailed'))
      error.value = message
      useToastStore().error(message)
    }
  }

  return { status, files, busy, error, refreshStatus, refreshList, start, stop, remove, download }
})
