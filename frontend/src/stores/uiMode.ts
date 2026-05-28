// Operator UX mode store (roadmap C.1).
//
// Toggles between "assisted" (guided defaults, conservative palette,
// minimal knobs) and "expert" (full control, multi-pass, diagnostics).
// The choice is per-task by design (audit #7 decision frozen
// 2026-05-27) so the operator can ask for a fast assisted run on one
// job and an exhaustive expert session on the next without flipping
// a global toggle. The last value is remembered in localStorage so
// the next session opens on the operator's preferred mode.
//
// Feature flags live next to the mode for the same reason: they're
// usually toggled together (an experimental compare-mode is an expert
// feature) and they share the same storage / serialization concerns.

import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

export type AssistantMode = 'assisted' | 'expert'

const STORAGE_KEY = 'omniplot.uiMode.v1'

interface PersistedShape {
  mode: AssistantMode
  expertDisclosureLevel: 1 | 2
  flags: Record<string, boolean>
}

function readPersisted(): PersistedShape {
  const fallback: PersistedShape = {
    mode: 'assisted',
    expertDisclosureLevel: 1,
    flags: {},
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as Partial<PersistedShape>
    return {
      mode: parsed.mode === 'expert' ? 'expert' : 'assisted',
      expertDisclosureLevel: parsed.expertDisclosureLevel === 2 ? 2 : 1,
      flags:
        parsed.flags && typeof parsed.flags === 'object'
          ? Object.fromEntries(
              Object.entries(parsed.flags).filter(([, v]) => typeof v === 'boolean'),
            )
          : {},
    }
  } catch {
    return fallback
  }
}

function readUrlFlags(): Record<string, boolean> {
  // `?flag.compareMode=1&flag.perf=0` → { compareMode: true, perf: false }.
  // URL flags win over persisted ones so an operator can override per
  // session without touching localStorage. Only used in the browser; the
  // SSR fallback is an empty map.
  if (typeof window === 'undefined') return {}
  try {
    const params = new URLSearchParams(window.location.search)
    const out: Record<string, boolean> = {}
    for (const [key, value] of params.entries()) {
      if (!key.startsWith('flag.')) continue
      const name = key.slice('flag.'.length)
      if (!name) continue
      out[name] = value === '1' || value.toLowerCase() === 'true'
    }
    return out
  } catch {
    return {}
  }
}

export const useUiModeStore = defineStore('uiMode', () => {
  const persisted = readPersisted()
  const urlFlags = readUrlFlags()

  const mode = ref<AssistantMode>(persisted.mode)
  const expertDisclosureLevel = ref<1 | 2>(persisted.expertDisclosureLevel)
  const flags = ref<Record<string, boolean>>({ ...persisted.flags })

  const isAssisted = computed(() => mode.value === 'assisted')
  const isExpert = computed(() => mode.value === 'expert')

  function setMode(next: AssistantMode): void {
    mode.value = next
  }

  function toggleMode(): void {
    mode.value = mode.value === 'assisted' ? 'expert' : 'assisted'
  }

  function setExpertDisclosureLevel(level: 1 | 2): void {
    expertDisclosureLevel.value = level
  }

  function setFlag(name: string, value: boolean): void {
    flags.value = { ...flags.value, [name]: value }
  }

  // Default values for flags that ship enabled in v0.2. The
  // operator can still flip them off via the header toggle or
  // ``?flag.X=0`` — the persisted ``false`` wins next time.
  // ``modalV2`` defaults to ON so the new editor is the v0.2
  // experience by default; v1 remains reachable via the wizard's
  // "Open full editor" escape hatch.
  const FLAG_DEFAULTS: Record<string, boolean> = {
    modalV2: true,
  }

  function isFlagEnabled(name: string): boolean {
    // URL override wins, then explicit persisted flag, then
    // FLAG_DEFAULTS, then false.
    if (name in urlFlags) return urlFlags[name] === true
    if (name in flags.value) return Boolean(flags.value[name])
    return FLAG_DEFAULTS[name] ?? false
  }

  // Persist any mutation; throws are silent (private-mode / quota).
  watch(
    [mode, expertDisclosureLevel, flags],
    () => {
      try {
        const payload: PersistedShape = {
          mode: mode.value,
          expertDisclosureLevel: expertDisclosureLevel.value,
          flags: flags.value,
        }
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
      } catch {
        /* ignore */
      }
    },
    { deep: true },
  )

  return {
    mode,
    expertDisclosureLevel,
    flags,
    isAssisted,
    isExpert,
    setMode,
    toggleMode,
    setExpertDisclosureLevel,
    setFlag,
    isFlagEnabled,
  }
})
