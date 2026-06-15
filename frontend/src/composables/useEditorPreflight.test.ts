// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import type { LayerInfo } from '../api/client'
import { usePlotterStore } from '../stores/plotter'
import { useUiStore } from '../stores/ui'
import { formatDuration, formatLengthMeters, useEditorPreflight } from './useEditorPreflight'

function layer(over: Partial<LayerInfo> = {}): LayerInfo {
  return {
    layer_id: 'color-112233',
    source_color: '#112233',
    target_pen_slot: null,
    draw_order: 0,
    total_length_mm: 0,
    path_count: 1,
    bbox: { x_min: 0, y_min: 0, x_max: 1, y_max: 1 },
    optimize: true,
    simplify_tolerance_mm: 0,
    drawing_speed_mm_s: null,
    color_label: null,
    pause_before: 'auto',
    assigned_color_hex: null,
    color_assignment: 'auto',
    ...over,
  } as LayerInfo
}

const t = (key: string) => key

describe('useEditorPreflight', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('sums path length and derives draw time at the default speed', () => {
    const layers = ref<LayerInfo[]>([
      layer({ layer_id: 'a', source_color: '#111', total_length_mm: 600 }),
      layer({ layer_id: 'b', source_color: '#222', total_length_mm: 600 }),
    ])
    const pf = useEditorPreflight({ layers: () => layers.value, hasPlacement: ref(true), t })

    expect(pf.estimatedLengthMm.value).toBe(1200)
    // 1200 mm / 60 mm·s⁻¹ = 20 s.
    expect(pf.estimatedDurationSeconds.value).toBeCloseTo(20)
    expect(pf.hasEstimate.value).toBe(true)
  })

  it('counts distinct required pens by assigned hex then source colour', () => {
    const layers = ref<LayerInfo[]>([
      layer({ layer_id: 'a', source_color: '#ff0000' }),
      layer({ layer_id: 'b', source_color: '#ff0000' }), // dup → not counted twice
      layer({ layer_id: 'c', source_color: '#00ff00', assigned_color_hex: '#0000ff' }),
    ])
    const pf = useEditorPreflight({ layers: () => layers.value, hasPlacement: ref(true), t })
    // #ff0000 and #0000ff (assigned wins over source) → 2 distinct.
    expect(pf.requiredPenCount.value).toBe(2)
  })

  it('reports every required ink missing when no pens are installed', () => {
    const layers = ref<LayerInfo[]>([
      layer({ layer_id: 'a', source_color: '#ff0000' }),
      layer({ layer_id: 'b', source_color: '#00ff00' }),
    ])
    const pf = useEditorPreflight({ layers: () => layers.value, hasPlacement: ref(true), t })
    expect(pf.missingInkCount.value).toBe(2)
    expect(pf.inksReady.value).toBe(false)
  })

  it('builds the four-chip checklist from placement / machine / sheet / ink state', () => {
    const hasPlacement = ref(false)
    const layers = ref<LayerInfo[]>([])
    const plotter = usePlotterStore()
    const ui = useUiStore()
    const pf = useEditorPreflight({ layers: () => layers.value, hasPlacement, t })

    let items = pf.preflightItems.value
    expect(items.map((i) => i.id)).toEqual(['file', 'machine', 'sheet', 'inks'])
    expect(items.find((i) => i.id === 'file')!.ok).toBe(false)
    expect(items.find((i) => i.id === 'machine')!.ok).toBe(false)
    expect(items.find((i) => i.id === 'sheet')!.ok).toBe(false)
    // No required inks yet → inks chip is OK.
    expect(items.find((i) => i.id === 'inks')!.ok).toBe(true)

    hasPlacement.value = true
    plotter.status.connected = true
    ui.previewSheet = { width_mm: 210, height_mm: 297 } as never
    items = pf.preflightItems.value
    expect(items.find((i) => i.id === 'file')!.ok).toBe(true)
    expect(items.find((i) => i.id === 'machine')!.ok).toBe(true)
    expect(items.find((i) => i.id === 'sheet')!.ok).toBe(true)
  })

  it('wires onFix to the right plotter-settings tab', () => {
    const layers = ref<LayerInfo[]>([layer({ source_color: '#ff0000' })])
    const ui = useUiStore()
    const spy = vi.spyOn(ui, 'openPlotterSettings').mockImplementation(() => {})
    const pf = useEditorPreflight({ layers: () => layers.value, hasPlacement: ref(true), t })

    const machine = pf.preflightItems.value.find((i) => i.id === 'machine')!
    machine.onFix?.()
    expect(spy).toHaveBeenCalledWith('connection')

    // A required-but-missing ink wires the chip to the colours tab.
    const inks = pf.preflightItems.value.find((i) => i.id === 'inks')!
    inks.onFix?.()
    expect(spy).toHaveBeenCalledWith('colors')
  })
})

describe('preflight formatters', () => {
  it('formats durations across the second / minute / hour bands', () => {
    expect(formatDuration(0)).toBe('—')
    expect(formatDuration(45)).toBe('45 s')
    expect(formatDuration(150)).toBe('3 min')
    expect(formatDuration(3600)).toBe('1 h')
    expect(formatDuration(3900)).toBe('1 h 5')
  })

  it('formats lengths in metres', () => {
    expect(formatLengthMeters(0)).toBe('0')
    expect(formatLengthMeters(2500)).toBe('2.5')
    expect(formatLengthMeters(42000)).toBe('42')
  })
})
