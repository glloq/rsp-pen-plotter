// Preflight checklist + drawing estimates for the V2 editor modal.
//
// Extracted from ``EditModalV2.vue`` (Phase 2 of the editor audit). Pure
// derived state over the job / plotter / ui stores plus the placement's
// layers — no template, so it's unit-testable without mounting the modal.
//
// Owns three related read-models:
//   - estimates : total path length + draw time + required pen count.
//   - compatibility : how many required inks aren't loaded (nearestPen).
//   - checklist : the four green/orange "am I ready?" chips.
import { computed, type ComputedRef, type Ref } from 'vue'
import type { LayerInfo } from '../api/client'
import { nearestPen, type PenSlotLike } from '../lib/penMatching'
import { usePlotterStore } from '../stores/plotter'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'

const DEFAULT_SPEED_MM_S = 60

export interface PreflightItem {
  id: 'file' | 'machine' | 'sheet' | 'inks'
  label: string
  ok: boolean
  // ``onFix`` jumps the operator straight to the panel that resolves the
  // warning. Null when the modal can't help (e.g. the missing file has to
  // come from the Files panel outside the modal).
  onFix: (() => void) | null
}

interface PenSlotShape extends PenSlotLike {
  name?: string
}

export interface EditorPreflightDeps {
  /** Layers from the active placement (the modal's ``props.layers``). */
  layers: () => readonly LayerInfo[] | undefined
  hasPlacement: Ref<boolean> | ComputedRef<boolean>
  /** i18n translate fn — kept reactive so labels follow locale changes. */
  t: (key: string) => string
}

export function useEditorPreflight(deps: EditorPreflightDeps) {
  const job = useJobStore()
  const plotter = usePlotterStore()
  const ui = useUiStore()

  const layers = computed<readonly LayerInfo[]>(() => deps.layers() ?? [])

  function effectiveSpeed(layer: LayerInfo): number {
    return layer.drawing_speed_mm_s ?? job.selectedProfile?.drawing_speed_mm_s ?? DEFAULT_SPEED_MM_S
  }

  // ---- Estimates ----
  const estimatedLengthMm = computed<number>(() =>
    layers.value.reduce((sum, l) => sum + (l.total_length_mm ?? 0), 0),
  )
  const estimatedDurationSeconds = computed<number>(() =>
    layers.value.reduce((sum, l) => {
      const speed = effectiveSpeed(l)
      return sum + (speed > 0 ? (l.total_length_mm ?? 0) / speed : 0)
    }, 0),
  )
  const requiredPenCount = computed<number>(() => {
    const hexes = new Set<string>()
    for (const layer of layers.value) {
      const hex = (layer.assigned_color_hex ?? layer.source_color ?? '').toLowerCase()
      if (hex) hexes.add(hex)
    }
    return hexes.size
  })
  const hasEstimate = computed<boolean>(() => estimatedLengthMm.value > 0)

  // ---- Ink compatibility ----
  // Walk every layer's assigned colour, ask ``nearestPen`` for the best
  // installed match, and count the inks that have no acceptable match.
  const installedPens = computed<PenSlotShape[]>(() => {
    const slots = job.selectedProfile?.pens ?? []
    return slots
      .filter((p) => p.installed !== false)
      .map((p) => ({ index: p.index, color: p.color, installed: true, name: p.name }))
  })
  const missingInkCount = computed<number>(() => {
    const pens = installedPens.value
    if (pens.length === 0) return requiredPenCount.value
    const seen = new Set<string>()
    let missing = 0
    for (const layer of layers.value) {
      const hex = (layer.assigned_color_hex ?? layer.source_color ?? '').toLowerCase()
      if (!hex || seen.has(hex)) continue
      seen.add(hex)
      const match = nearestPen(hex, pens)
      // 'far' and 'wrong' both mean the operator will get a visibly
      // different ink — treat as missing so the warning is honest.
      if (match.severity === 'far' || match.severity === 'wrong' || match.severity === 'none') {
        missing += 1
      }
    }
    return missing
  })

  function openMagazine(): void {
    ui.openPlotterSettings('colors')
  }
  function openConnectionSettings(): void {
    ui.openPlotterSettings('connection')
  }

  // ---- Checklist ----
  // Four things have to be true before Generate can do anything useful:
  // a file is selected, the machine is online, a sheet is picked, and
  // every required ink is loaded.
  const machineReady = computed<boolean>(() => plotter.status.connected === true)
  const hasSheet = computed<boolean>(() => ui.previewSheet !== null)
  const inksReady = computed<boolean>(
    () => requiredPenCount.value === 0 || missingInkCount.value === 0,
  )
  const preflightItems = computed<PreflightItem[]>(() => [
    {
      id: 'file',
      label: deps.t('v2.modal.preflightFile'),
      ok: deps.hasPlacement.value,
      onFix: null,
    },
    {
      id: 'machine',
      label: deps.t('v2.modal.preflightMachine'),
      ok: machineReady.value,
      onFix: openConnectionSettings,
    },
    {
      id: 'sheet',
      label: deps.t('v2.modal.preflightSheet'),
      ok: hasSheet.value,
      onFix: null,
    },
    {
      id: 'inks',
      label: deps.t('v2.modal.preflightInks'),
      ok: inksReady.value,
      onFix: requiredPenCount.value > 0 ? openMagazine : null,
    },
  ])

  return {
    estimatedLengthMm,
    estimatedDurationSeconds,
    requiredPenCount,
    hasEstimate,
    missingInkCount,
    machineReady,
    hasSheet,
    inksReady,
    preflightItems,
    openMagazine,
  }
}

// Display helpers for the estimate rows — pure, so they live next to the
// read-model that produces the numbers they format.
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return '—'
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))} s`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m === 0 ? `${h} h` : `${h} h ${m}`
}

export function formatLengthMeters(mm: number): string {
  if (!Number.isFinite(mm) || mm <= 0) return '0'
  const meters = mm / 1000
  return meters < 10 ? meters.toFixed(1) : Math.round(meters).toString()
}
