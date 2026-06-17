// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useInkOdometer } from './useInkOdometer'
import { useJobStore, type Placement } from '../stores/job'
import { useAvailableColorsStore } from '../stores/availableColors'
import type { LayerInfo } from '../api/client'

function makeLayer(over: Partial<LayerInfo> = {}): LayerInfo {
  return {
    layer_id: 'layer-1',
    color_label: 'c',
    source_color: '#000000',
    assigned_color_hex: null,
    color_assignment: 'auto',
    target_pen_slot: 0,
    draw_order: 0,
    total_length_mm: 10,
    bbox: { x_min: 0, y_min: 0, x_max: 1, y_max: 1 },
    ...over,
  } as LayerInfo
}

function makePlacement(over: Partial<Placement> = {}): Placement {
  return {
    id: `p${Math.random().toString(36).slice(2)}`,
    library_file_id: null,
    source_file: 'x.png',
    source_mime: 'image/png',
    job_id: null,
    rerenderable: false,
    svg: '<svg/>',
    layers: [makeLayer()],
    source_bbox: { x_min: 0, y_min: 0, x_max: 1, y_max: 1 },
    layer_algorithms: {},
    upload_warnings: [],
    upload_metadata: {},
    last_file: null,
    last_options: undefined,
    visibility: {},
    rotation: 0,
    flip_h: false,
    flip_v: false,
    x_mm: 0,
    y_mm: 0,
    width_mm: 10,
    height_mm: 10,
    ...over,
  } as Placement
}

describe('useInkOdometer', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('advances each ink odometer by the current job length per colour', () => {
    const job = useJobStore()
    job.placements = [
      makePlacement({
        layers: [
          makeLayer({ layer_id: 'a', source_color: '#ff0000', total_length_mm: 100 }),
          makeLayer({ layer_id: 'b', source_color: '#ff0000', total_length_mm: 50 }),
          makeLayer({ layer_id: 'c', source_color: '#0000ff', total_length_mm: 30 }),
        ],
      }),
    ]
    const colors = useAvailableColorsStore()
    const odo = vi.spyOn(colors, 'addToOdometer').mockResolvedValue()

    useInkOdometer().commitCurrentJob()

    // Same-colour layers aggregate; keys are canonical (#rrggbb).
    expect(odo).toHaveBeenCalledWith('#ff0000', 150)
    expect(odo).toHaveBeenCalledWith('#0000ff', 30)
    expect(odo).toHaveBeenCalledTimes(2)
  })

  it('does nothing when there is no job loaded', () => {
    const colors = useAvailableColorsStore()
    const odo = vi.spyOn(colors, 'addToOdometer').mockResolvedValue()

    useInkOdometer().commitCurrentJob()

    expect(odo).not.toHaveBeenCalled()
  })
})
