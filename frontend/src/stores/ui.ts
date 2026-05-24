import { defineStore } from 'pinia'
import { ref } from 'vue'

export type CanvasTab = 'sheet' | 'simulator' | 'gcode'
export type SettingsTab = 'profile' | 'macros' | 'history' | 'audit' | 'system'

export interface PreviewSheet {
  width_mm: number
  height_mm: number
}

export const useUiStore = defineStore('ui', () => {
  const canvasTab = ref<CanvasTab>('sheet')
  const settingsOpen = ref(false)
  const settingsTab = ref<SettingsTab>('profile')
  const plotterDrawerOpen = ref(false)
  const editModalOpen = ref(false)
  // Display-only sheet overlay shown on the workspace plan, positioned at
  // the top-left. Set when the user picks a sheet format in LayoutSection.
  const previewSheet = ref<PreviewSheet | null>(null)

  function setPreviewSheet(sheet: PreviewSheet | null): void {
    previewSheet.value = sheet
  }

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
    previewSheet,
    setPreviewSheet,
    openSettings,
    closeSettings,
    openPlotterDrawer,
    closePlotterDrawer,
    openEditModal,
    closeEditModal,
  }
})
