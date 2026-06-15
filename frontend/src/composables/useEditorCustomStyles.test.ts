import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { ref } from 'vue'

import { useEditorCustomStyles } from './useEditorCustomStyles'
import { getBeginnerStyle } from '../components/v2/beginnerStyles'
import type { SourceKind } from '../domain/policy/schemas'
import { useJobStore } from '../stores/job'

const CROSSHATCH = getBeginnerStyle('crosshatch')!

// Drop a single-layer placement whose committed ``layer_algorithms`` carries a
// crosshatch spec, so ``seedCustomStylesFromCommitted`` has something to read.
function seedPlacementWithCrosshatch(knobValue: number) {
  const job = useJobStore()
  const id = job.addEmptyPlacement()
  job.placements = job.placements.map((p) =>
    p.id === id
      ? {
          ...p,
          layers: [
            {
              layer_id: 'color-aabbcc',
              source_color: '#aabbcc',
              target_pen_slot: null,
              draw_order: 0,
              total_length_mm: 10,
              path_count: 1,
              bbox: { x_min: 0, y_min: 0, x_max: 10, y_max: 10 },
              optimize: true,
              simplify_tolerance_mm: 0,
              drawing_speed_mm_s: null,
              color_label: null,
              pause_before: 'auto',
              assigned_color_hex: null,
              color_assignment: 'auto',
            },
          ],
          layer_algorithms: {
            'color-aabbcc': {
              algorithm: 'crosshatch',
              algorithm_options: { [CROSSHATCH.primaryKnob.optionKey]: knobValue },
            },
          },
        }
      : p,
  )
}

describe('useEditorCustomStyles', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('starts with an empty, inactive stack', () => {
    const styles = useEditorCustomStyles({ sourceKind: () => 'bitmap_photo' })
    expect(styles.customStyles.value).toEqual([])
    expect(styles.customStylesActive.value).toBe(false)
    expect(styles.customPasses.value).toEqual([])
  })

  it('gates the panel to bitmap sources only', () => {
    const kind = ref<SourceKind>('bitmap_photo')
    const styles = useEditorCustomStyles({ sourceKind: () => kind.value })
    expect(styles.canCustomizeStyles.value).toBe(true)
    kind.value = 'bitmap_illustration'
    expect(styles.canCustomizeStyles.value).toBe(true)
    kind.value = 'vector_svg'
    expect(styles.canCustomizeStyles.value).toBe(false)
    kind.value = 'pdf_doc'
    expect(styles.canCustomizeStyles.value).toBe(false)
  })

  it('seeds the stack from the committed layer_algorithms of the first layer', () => {
    seedPlacementWithCrosshatch(2.4)
    const styles = useEditorCustomStyles({ sourceKind: () => 'bitmap_photo' })
    styles.seedCustomStylesFromCommitted()
    expect(styles.customStyles.value).toEqual([{ id: 'crosshatch', knobValue: 2.4 }])
    expect(styles.customStylesActive.value).toBe(true)
  })

  it('is a no-op seed for non-bitmap sources', () => {
    seedPlacementWithCrosshatch(2.4)
    const styles = useEditorCustomStyles({ sourceKind: () => 'vector_svg' })
    styles.seedCustomStylesFromCommitted()
    expect(styles.customStyles.value).toEqual([])
  })

  it('projects the stack into PolicyPass[] overriding only the primary knob', () => {
    const styles = useEditorCustomStyles({ sourceKind: () => 'bitmap_photo' })
    styles.customStyles.value = [{ id: 'crosshatch', knobValue: 3.1 }]
    expect(styles.customPasses.value).toEqual([
      {
        algorithm: 'crosshatch',
        algorithm_options: { [CROSSHATCH.primaryKnob.optionKey]: 3.1 },
      },
    ])
  })
})
