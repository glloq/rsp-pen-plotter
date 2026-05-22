import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  deleteMacro as apiDeleteMacro,
  getMacros,
  runMacro as apiRunMacro,
  saveMacro as apiSaveMacro,
  type Macro,
} from '../api/client'

export const useMacroStore = defineStore('macros', () => {
  const macros = ref<Macro[]>([])
  const error = ref<string | null>(null)

  function detail(err: unknown, fallback: string): string {
    return (
      (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback
    )
  }

  async function load(): Promise<void> {
    macros.value = await getMacros()
  }

  async function save(macro: Macro): Promise<void> {
    error.value = null
    try {
      await apiSaveMacro(macro)
      await load()
    } catch (err) {
      error.value = detail(err, 'Could not save macro.')
    }
  }

  async function remove(name: string): Promise<void> {
    error.value = null
    try {
      await apiDeleteMacro(name)
      await load()
    } catch (err) {
      error.value = detail(err, 'Could not delete macro.')
    }
  }

  async function run(name: string): Promise<void> {
    error.value = null
    try {
      await apiRunMacro(name)
    } catch (err) {
      error.value = detail(err, 'Could not run macro.')
    }
  }

  return { macros, error, load, save, remove, run }
})
