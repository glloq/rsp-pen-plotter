// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, expect, it, vi } from 'vitest'
import PlacementHandles from './PlacementHandles.vue'
import type { RenderedPlacement } from '../composables/useSheetGeometry'

// Regression cover for the post-L10-split pointer-capture bug. The
// placement rect lives inside the same DOM tree as the container that
// owns the pan-view gesture; without ``@pointerdown.stop`` on the
// rect the container's bubble handler steals pointer capture, the
// placement gesture never sees pointerup, and ``mode`` stays armed at
// ``'move-drawing'`` — making the placement track the cursor on the
// very next mousemove after the operator released the button.

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      sheet: { removePlacement: 'Remove' },
      upload: { pageOf: 'Page {current}/{total}' },
      variants: { title: 'Variants' },
    },
  },
})

function makeRendered(id: string): RenderedPlacement {
  return {
    placement: {
      id,
      x_mm: 10,
      y_mm: 10,
      width_mm: 50,
      height_mm: 50,
      rotation: 0,
      flip_h: false,
      flip_v: false,
      svg: '',
      layers: [],
      visibility: {},
      variants: [],
      active_variant_id: '',
      library_file_id: '',
      source_file: '',
      source_mime: '',
      source_bbox: { x_min: 0, y_min: 0, x_max: 0, y_max: 0 },
      job_id: '',
      rerenderable: false,
      upload_warnings: [],
      upload_metadata: {},
      layer_algorithms: {},
      // satisfy any extra Placement fields with defaults; the test
      // only reads the geometry slice.
    } as unknown as RenderedPlacement['placement'],
    footprint: { x_min: 10, y_min: 10, x_max: 60, y_max: 60 },
    exceeds: false,
    cleanSvg: '',
    previewUrl: '',
  }
}

function mountHandles(selectedId: string | null = null) {
  const rp = makeRendered('p1')
  return mount(PlacementHandles, {
    props: {
      renderedPlacements: [rp],
      selectedPlacementId: selectedId,
      pxToMm: () => 1,
      snap: (v: number) => v,
      snapActive: false,
      loading: false,
    },
    global: { plugins: [i18n] },
    // happy-dom doesn't render SVG inside a fragment by default; wrap.
    attachTo: document.body,
  })
}

describe('PlacementHandles pointerdown propagation', () => {
  it('placement rect pointerdown does not bubble to ancestor (parent pan-view never armed)', async () => {
    // Stand-in for the SheetPreview container that listens on
    // pointerdown to enter pan-view mode. If the bubble reaches it,
    // the parent steals pointer capture from PlacementHandles and the
    // gesture state leaks — exactly the post-refactor regression.
    const parentSpy = vi.fn()
    document.body.addEventListener('pointerdown', parentSpy)
    try {
      const wrapper = mountHandles()
      const rect = wrapper.find('rect')
      expect(rect.exists()).toBe(true)
      await rect.trigger('pointerdown', { button: 0, clientX: 100, clientY: 100 })
      expect(parentSpy).not.toHaveBeenCalled()
    } finally {
      document.body.removeEventListener('pointerdown', parentSpy)
    }
  })

  it('resize handle pointerdown does not bubble to ancestor', async () => {
    const parentSpy = vi.fn()
    document.body.addEventListener('pointerdown', parentSpy)
    try {
      // Selected placement renders the 8 resize circles.
      const wrapper = mountHandles('p1')
      const circle = wrapper.find('circle')
      expect(circle.exists()).toBe(true)
      await circle.trigger('pointerdown', { button: 0, clientX: 10, clientY: 10 })
      expect(parentSpy).not.toHaveBeenCalled()
    } finally {
      document.body.removeEventListener('pointerdown', parentSpy)
    }
  })
})
