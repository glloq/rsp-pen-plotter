import { defineStore } from 'pinia'
import { ref } from 'vue'

export type CanvasTab = 'sheet' | 'simulator' | 'gcode'
export type SettingsTab = 'profile' | 'macros' | 'history' | 'audit' | 'system'

export const useUiStore = defineStore('ui', () => {
  const canvasTab = ref<CanvasTab>('sheet')
  const settingsOpen = ref(false)
  const settingsTab = ref<SettingsTab>('profile')
  const plotterDrawerOpen = ref(false)
  const editModalOpen = ref(false)

  function openSettings(tab?: SettingsTab): void {
    if (tab) settingsTab.value = tab
    settingsOpen.value = true
  }

  function closeSettings(): void {
    settingsOpen.value = false
  }

  function openPlotterDrawer(): void {
    plotterDrawerOpen.value = true
  }

  function closePlotterDrawer(): void {
    plotterDrawerOpen.value = false
  }

  function openEditModal(): void {
    editModalOpen.value = true
  }

  function closeEditModal(): void {
    editModalOpen.value = false
  }

  return {
    canvasTab,
    settingsOpen,
    settingsTab,
    plotterDrawerOpen,
    editModalOpen,
    openSettings,
    closeSettings,
    openPlotterDrawer,
    closePlotterDrawer,
    openEditModal,
    closeEditModal,
  }
})
