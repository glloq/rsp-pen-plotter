import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  deleteGcodeFile,
  listGcodeFiles,
  printGcodeFile,
  renameGcodeFile,
  saveGcodeFile,
  type GcodeFileSummary,
} from '../api/client'
import { errorDetail } from '../api/error'
import { i18n } from '../i18n'
import { useToastStore } from './toasts'

// G-code file library: the saved programs the operator can re-print on
// demand. The list only changes on operator action (save / rename /
// delete / print), so — unlike the queue — there's no background poll;
// callers refresh after a mutation and on mount. Live "is this one
// printing?" state is read from the queue store, not duplicated here.
export const useGcodeFilesStore = defineStore('gcodeFiles', () => {
  const files = ref<GcodeFileSummary[]>([])
  const error = ref<string | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  // Ids with a rename / delete / print in flight, so rows can disable
  // their buttons and a double-click can't fire two round-trips.
  const busyIds = ref<ReadonlySet<string>>(new Set())
  const isBusy = (id: string): boolean => busyIds.value.has(id)
  const hasFiles = computed(() => files.value.length > 0)

  function setBusy(id: string, value: boolean): void {
    const next = new Set(busyIds.value)
    if (value) next.add(id)
    else next.delete(id)
    busyIds.value = next
  }

  async function refresh(): Promise<void> {
    loading.value = true
    try {
      files.value = await listGcodeFiles()
      error.value = null
    } catch (err) {
      error.value = errorDetail(err, i18n.global.t('gcodeFiles.loadFailed'))
    } finally {
      loading.value = false
    }
  }

  async function save(
    name: string,
    profileName: string,
    gcode: string,
    lengthMmByColor: Record<string, number> = {},
  ): Promise<GcodeFileSummary | null> {
    if (saving.value) return null
    saving.value = true
    try {
      const created = await saveGcodeFile(name, profileName, gcode, lengthMmByColor)
      await refresh()
      useToastStore().success(i18n.global.t('gcodeFiles.saved', { name: created.name }))
      return created
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('gcodeFiles.saveFailed'))
      error.value = message
      useToastStore().error(message)
      return null
    } finally {
      saving.value = false
    }
  }

  async function rename(id: string, name: string): Promise<void> {
    if (busyIds.value.has(id)) return
    setBusy(id, true)
    try {
      await renameGcodeFile(id, name)
      await refresh()
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('gcodeFiles.renameFailed'))
      error.value = message
      useToastStore().error(message)
    } finally {
      setBusy(id, false)
    }
  }

  async function remove(id: string): Promise<void> {
    if (busyIds.value.has(id)) return
    setBusy(id, true)
    try {
      await deleteGcodeFile(id)
      await refresh()
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('gcodeFiles.deleteFailed'))
      error.value = message
      useToastStore().error(message)
    } finally {
      setBusy(id, false)
    }
  }

  // Launch a saved program. The backend enqueues it as a run + wakes the
  // worker; the caller is expected to refresh the queue store so the row
  // flips to "printing".
  async function print(id: string): Promise<boolean> {
    if (busyIds.value.has(id)) return false
    setBusy(id, true)
    try {
      await printGcodeFile(id)
      return true
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('gcodeFiles.printFailed'))
      error.value = message
      useToastStore().error(message)
      return false
    } finally {
      setBusy(id, false)
    }
  }

  return {
    files,
    error,
    loading,
    saving,
    busyIds,
    isBusy,
    hasFiles,
    refresh,
    save,
    rename,
    remove,
    print,
  }
})
