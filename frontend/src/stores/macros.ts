import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  deleteMacro as apiDeleteMacro,
  getMacros,
  runMacro as apiRunMacro,
  saveMacro as apiSaveMacro,
  type Macro,
} from '../api/client'
import { errorDetail } from '../api/error'
import { i18n } from '../i18n'
import { useToastStore } from './toasts'

export const useMacroStore = defineStore('macros', () => {
  const macros = ref<Macro[]>([])
  const error = ref<string | null>(null)
  // Names of macros whose run is in flight. A macro fires hardware
  // commands, so a double-click must not dispatch the sequence twice —
  // the panel disables the Run button while the name is in this set, and
  // ``run`` itself early-returns as a belt-and-suspenders guard.
  const running = ref<ReadonlySet<string>>(new Set())

  const isRunning = (name: string): boolean => running.value.has(name)
  const anyRunning = computed(() => running.value.size > 0)

  function setRunning(name: string, value: boolean): void {
    const next = new Set(running.value)
    if (value) next.add(name)
    else next.delete(name)
    running.value = next
  }

  async function load(): Promise<void> {
    error.value = null
    try {
      macros.value = await getMacros()
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('macros.loadFailed'))
      error.value = message
      useToastStore().error(message)
    }
  }

  async function save(macro: Macro): Promise<void> {
    error.value = null
    try {
      await apiSaveMacro(macro)
      await load()
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('macros.saveFailed'))
      error.value = message
      useToastStore().error(message)
    }
  }

  async function remove(name: string): Promise<void> {
    error.value = null
    try {
      await apiDeleteMacro(name)
      await load()
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('macros.deleteFailed'))
      error.value = message
      useToastStore().error(message)
    }
  }

  async function run(name: string): Promise<void> {
    if (running.value.has(name)) return
    error.value = null
    setRunning(name, true)
    const toasts = useToastStore()
    const toastId = toasts.progress(i18n.global.t('toast.macroRunning', { name }))
    try {
      await apiRunMacro(name)
      toasts.update(toastId, 'success', i18n.global.t('toast.macroDone', { name }), 3000)
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('macros.runFailed'))
      error.value = message
      toasts.update(toastId, 'error', message, 6000)
    } finally {
      setRunning(name, false)
    }
  }

  return { macros, error, running, isRunning, anyRunning, load, save, remove, run }
})
