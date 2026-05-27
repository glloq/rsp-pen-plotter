// Workspaces store (roadmap D.3 / audit #7 bonus).
//
// A workspace is a named layout — which panels are visible, in
// which slot. The audit's "Beginner: Source → Style → Preview →
// Plot" and "Pro: Layer Inspector + Pipeline Inspector + Queue +
// Machine Telemetry" map to two built-in presets; operators can save
// their own customisations under a name and restore them later.
//
// Decision frozen 2026-05-27: local-first (localStorage), server
// sync deferred to V2. This store is the local-first half.

import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

export type PanelId =
  | 'source'
  | 'style'
  | 'preview'
  | 'plot'
  | 'layer_inspector'
  | 'pipeline_inspector'
  | 'queue'
  | 'machine_telemetry'
  | 'compare'
  | 'magazine'

export interface Workspace {
  id: string
  name: string
  /** Panels in display order, left-to-right / top-to-bottom. */
  panels: PanelId[]
  /** Optional built-in marker — built-ins can't be deleted. */
  builtin?: boolean
}

const STORAGE_KEY = 'omniplot.workspaces.v1'

const BUILTIN_BEGINNER: Workspace = {
  id: 'builtin.beginner',
  name: 'Débutant',
  panels: ['source', 'style', 'preview', 'plot'],
  builtin: true,
}

const BUILTIN_PRO: Workspace = {
  id: 'builtin.pro',
  name: 'Pro',
  panels: [
    'layer_inspector',
    'pipeline_inspector',
    'queue',
    'machine_telemetry',
  ],
  builtin: true,
}

const BUILTINS: readonly Workspace[] = [BUILTIN_BEGINNER, BUILTIN_PRO]

interface PersistedShape {
  activeId: string
  custom: Workspace[]
}

function readPersisted(): PersistedShape {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return { activeId: BUILTIN_BEGINNER.id, custom: [] }
    const parsed = JSON.parse(raw) as Partial<PersistedShape>
    return {
      activeId: typeof parsed.activeId === 'string' ? parsed.activeId : BUILTIN_BEGINNER.id,
      custom: Array.isArray(parsed.custom)
        ? parsed.custom.filter((w): w is Workspace => isWorkspace(w))
        : [],
    }
  } catch {
    return { activeId: BUILTIN_BEGINNER.id, custom: [] }
  }
}

function isWorkspace(value: unknown): value is Workspace {
  if (!value || typeof value !== 'object') return false
  const w = value as Workspace
  return typeof w.id === 'string' && typeof w.name === 'string' && Array.isArray(w.panels)
}

export const useWorkspacesStore = defineStore('workspaces', () => {
  const persisted = readPersisted()
  const custom = ref<Workspace[]>(persisted.custom)
  const activeId = ref<string>(persisted.activeId)

  const all = computed<Workspace[]>(() => [...BUILTINS, ...custom.value])
  const active = computed<Workspace>(() => {
    return all.value.find((w) => w.id === activeId.value) ?? BUILTIN_BEGINNER
  })

  function setActive(id: string): void {
    if (all.value.some((w) => w.id === id)) activeId.value = id
  }

  /** Save the active workspace under a new name (clones + adds to custom). */
  function saveAs(name: string, panels: PanelId[]): Workspace {
    const trimmed = name.trim()
    if (!trimmed) throw new Error('workspace name is required')
    const id = `custom.${Date.now().toString(36)}.${Math.random().toString(36).slice(2, 6)}`
    const next: Workspace = { id, name: trimmed, panels: [...panels] }
    custom.value = [...custom.value, next]
    activeId.value = id
    return next
  }

  function rename(id: string, name: string): void {
    const trimmed = name.trim()
    if (!trimmed) return
    custom.value = custom.value.map((w) => (w.id === id ? { ...w, name: trimmed } : w))
  }

  function remove(id: string): boolean {
    const target = custom.value.find((w) => w.id === id)
    if (!target) return false
    custom.value = custom.value.filter((w) => w.id !== id)
    if (activeId.value === id) activeId.value = BUILTIN_BEGINNER.id
    return true
  }

  watch(
    [activeId, custom],
    () => {
      try {
        const payload: PersistedShape = {
          activeId: activeId.value,
          custom: custom.value,
        }
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
      } catch {
        /* ignore */
      }
    },
    { deep: true },
  )

  return {
    custom,
    activeId,
    all,
    active,
    setActive,
    saveAs,
    rename,
    remove,
  }
})

export const _BUILTINS_FOR_TESTS = BUILTINS
