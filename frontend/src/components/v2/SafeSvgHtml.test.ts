// @vitest-environment jsdom
// jsdom (not happy-dom): DOMPurify >= 3.4.11 mis-detects happy-dom nodes via its
// cross-realm instanceof hardening and mangles SVG output there; jsdom matches
// real-Chromium sanitizer behaviour.
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SafeSvgHtml from './SafeSvgHtml.vue'

function render(svg: string | null) {
  return mount(SafeSvgHtml, { props: { svg } })
}

describe('SafeSvgHtml', () => {
  it('renders nothing for null / empty input', () => {
    expect(render(null).html()).not.toContain('<svg')
    expect(render('').html()).not.toContain('<svg')
  })

  it('keeps benign SVG geometry intact', () => {
    const wrapper = render(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M0 0 L10 10" stroke="#f00"/></svg>',
    )
    const svg = wrapper.element.querySelector('svg')
    expect(svg).not.toBeNull()
    expect(svg!.getAttribute('viewBox')).toBe('0 0 10 10')
    expect(wrapper.element.querySelector('path')?.getAttribute('stroke')).toBe('#f00')
  })

  it('preserves inkscape:label so the per-layer opacity overlay still works', () => {
    const wrapper = render(
      '<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"><g inkscape:label="color-ff0000"><path d="M0 0"/></g></svg>',
    )
    const g = wrapper.element.querySelector('g')
    expect(g?.getAttribute('inkscape:label')).toBe('color-ff0000')
  })

  it('strips <script> elements', () => {
    const wrapper = render(
      '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><path d="M0 0"/></svg>',
    )
    expect(wrapper.element.querySelector('script')).toBeNull()
    expect(wrapper.html().toLowerCase()).not.toContain('alert')
  })

  it('strips inline event handlers (onload / onclick)', () => {
    const wrapper = render(
      '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><rect width="5" height="5" onclick="alert(2)"/></svg>',
    )
    const html = wrapper.html().toLowerCase()
    expect(html).not.toContain('onload')
    expect(html).not.toContain('onclick')
    expect(html).not.toContain('alert')
  })

  it('neutralises javascript: URLs on links', () => {
    const wrapper = render(
      '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><a xlink:href="javascript:alert(1)"><text>x</text></a></svg>',
    )
    expect(wrapper.html().toLowerCase()).not.toContain('javascript:')
  })

  it('drops embedded foreignObject HTML script vectors', () => {
    const wrapper = render(
      '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject><img src="x" onerror="alert(1)"></foreignObject></svg>',
    )
    const html = wrapper.html().toLowerCase()
    expect(html).not.toContain('onerror')
    expect(html).not.toContain('alert')
  })

  it('re-sanitises and re-renders when the svg prop changes', async () => {
    const wrapper = render(
      '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0" stroke="#f00"/></svg>',
    )
    expect(wrapper.element.querySelector('path')?.getAttribute('stroke')).toBe('#f00')
    // Swap in a different (clean) render — the new content must replace the old.
    await wrapper.setProps({
      svg: '<svg xmlns="http://www.w3.org/2000/svg"><path d="M1 1" stroke="#0f0"/></svg>',
    })
    expect(wrapper.element.querySelector('path')?.getAttribute('stroke')).toBe('#0f0')
  })
})
