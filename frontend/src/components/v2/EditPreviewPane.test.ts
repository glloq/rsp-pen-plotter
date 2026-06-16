// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createI18n } from 'vue-i18n'

import EditPreviewPane, { type SheetOutlineShape } from './EditPreviewPane.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'fr',
  fallbackLocale: 'fr',
  messages: {
    fr: {
      v2: {
        modal: {
          sheetCaptionLabel: 'Feuille',
          viewPlot: 'Résultat',
          viewOriginal: 'Original',
          viewCompare: 'Comparer',
          previewLoading: 'Mise à jour de l’aperçu…',
          previewError: 'Aperçu indisponible.',
          zoomIn: 'Zoom +',
          zoomOut: 'Zoom −',
          resetView: 'Recentrer',
        },
      },
    },
  },
})

// The pane sizes the sheet outline from a ResizeObserver on the preview
// pane; happy-dom doesn't implement one, so fake an observer that
// reports a fixed pane size synchronously on observe().
type ObserverCb = (entries: { contentRect: { width: number; height: number } }[]) => void
class FakeResizeObserver {
  private readonly cb: ObserverCb
  constructor(cb: ObserverCb) {
    this.cb = cb
  }
  observe(): void {
    this.cb([{ contentRect: { width: 800, height: 600 } }])
  }
  unobserve(): void {}
  disconnect(): void {}
}

const SVG = '<svg xmlns="http://www.w3.org/2000/svg"></svg>'

// Portrait A4 sheet.
const SHEET: SheetOutlineShape = {
  aspectRatio: 210 / 297,
  labelW: 210,
  labelH: 297,
  isPortrait: true,
  widthMm: 210,
  heightMm: 297,
}

function mountPane(props: Record<string, unknown> = {}) {
  return mount(EditPreviewPane, {
    props: {
      plotSvg: SVG,
      originalSvg: SVG,
      loading: false,
      error: false,
      sheet: SHEET,
      ...props,
    },
    global: { plugins: [i18n] },
  })
}

describe('EditPreviewPane (sheet / artwork geometry)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('ResizeObserver', FakeResizeObserver)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sizes the artwork box as artwork_mm / sheet_mm percentages', async () => {
    const wrapper = mountPane({ artworkWidthMm: 105, artworkHeightMm: 148.5 })
    await nextTick()
    const box = wrapper.find<HTMLElement>('[data-test="modal-v2-artwork-box"]')
    expect(box.exists()).toBe(true)
    expect(box.element.style.width).toBe('50%')
    expect(box.element.style.height).toBe('50%')
  })

  it('clamps an oversized artwork uniformly so its aspect ratio survives', async () => {
    // 420 × 297 artwork on a 210 × 297 sheet: width overflows 2×, height
    // fits exactly. A per-axis clamp would yield 100 % × 100 % (stretched);
    // the uniform clamp keeps the 2:√2 shape → 100 % × 50 %.
    const wrapper = mountPane({ artworkWidthMm: 420, artworkHeightMm: 297 })
    await nextTick()
    const box = wrapper.find<HTMLElement>('[data-test="modal-v2-artwork-box"]')
    expect(box.element.style.width).toBe('100%')
    expect(box.element.style.height).toBe('50%')
  })

  it('maps the compare-slider position from sheet space into artwork space', async () => {
    // Artwork covers the left 50 % of the sheet. The handle starts at
    // 50 % of the SHEET — i.e. exactly the artwork's right edge — so the
    // plot layer must be clipped at 100 % of the ARTWORK box, not 50 %.
    const wrapper = mountPane({ artworkWidthMm: 105, artworkHeightMm: 148.5 })
    await nextTick()
    await wrapper.find('[data-test="modal-v2-mode-split"]').trigger('click')
    const plot = wrapper.find<HTMLElement>('[data-test="modal-v2-preview-svg"]')
    expect(plot.element.style.clipPath).toBe('inset(0 0 0 100%)')
    const source = wrapper.find<HTMLElement>('[data-test="modal-v2-preview-source"]')
    expect(source.element.style.clipPath).toBe('inset(0 0% 0 0)')
  })

  it('keeps the 1:1 sheet↔artwork mapping when the artwork fills the sheet', async () => {
    const wrapper = mountPane({ artworkWidthMm: 210, artworkHeightMm: 297 })
    await nextTick()
    await wrapper.find('[data-test="modal-v2-mode-split"]').trigger('click')
    const plot = wrapper.find<HTMLElement>('[data-test="modal-v2-preview-svg"]')
    expect(plot.element.style.clipPath).toBe('inset(0 0 0 50%)')
  })

  it('collapses a hidden layer to opacity 0 in the preview SVG', async () => {
    // The ink-chip eye toggles job.visibility; the pane realises it by
    // setting opacity on the matching ``<g inkscape:label="...">`` group.
    const { useJobStore } = await import('../../stores/job')
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
          }
        : p,
    )
    const plotSvg =
      '<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">' +
      '<g inkscape:label="color-aabbcc"><path d="M0 0H10"/></g></svg>'
    const wrapper = mountPane({ plotSvg })
    await nextTick()
    await Promise.resolve()
    const group = () =>
      wrapper.find('[data-test="modal-v2-preview-svg"]').element.querySelector('g')
    // Visible: opacity unset ('') or explicitly 1 — both render fully opaque.
    expect(group()?.style.opacity).not.toBe('0')

    job.setVisibility('color-aabbcc', false)
    await nextTick()
    expect(group()?.style.opacity).toBe('0')

    // Re-showing restores full opacity.
    job.setVisibility('color-aabbcc', true)
    await nextTick()
    expect(group()?.style.opacity).toBe('1')
  })
})
