// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from 'vitest'
import { ref } from 'vue'

import { useEditorOnboarding } from './useEditorOnboarding'

const ONBOARDING_KEY = 'omniplot.onboarding.editorV2.v1'
const PREAMBLE_KEY = 'omniplot.preamble.editorV2.v1'

describe('useEditorOnboarding — tour', () => {
  beforeEach(() => window.localStorage.clear())

  it('starts on first run when a placement is attached', () => {
    const ob = useEditorOnboarding({ skipOnboarding: false, hasPlacement: ref(true) })
    expect(ob.tourActive.value).toBe(false)
    ob.startTourIfFirstRun()
    expect(ob.tourStep.value).toBe(1)
    expect(ob.tourActive.value).toBe(true)
  })

  it('does not start when skipped, when there is no placement, or when already seen', () => {
    expect(run(() => useEditorOnboarding({ skipOnboarding: true, hasPlacement: ref(true) }))).toBe(
      0,
    )
    expect(
      run(() => useEditorOnboarding({ skipOnboarding: false, hasPlacement: ref(false) })),
    ).toBe(0)
    window.localStorage.setItem(ONBOARDING_KEY, JSON.stringify({ seen: true }))
    expect(run(() => useEditorOnboarding({ skipOnboarding: false, hasPlacement: ref(true) }))).toBe(
      0,
    )

    function run(make: () => ReturnType<typeof useEditorOnboarding>): number {
      const ob = make()
      ob.startTourIfFirstRun()
      return ob.tourStep.value
    }
  })

  it('advances through the steps and dismisses (persisting seen) at the end', () => {
    const ob = useEditorOnboarding({ skipOnboarding: false, hasPlacement: ref(true) })
    ob.startTourIfFirstRun()
    ob.nextTourStep()
    expect(ob.tourStep.value).toBe(2)
    ob.nextTourStep()
    expect(ob.tourStep.value).toBe(3)
    ob.nextTourStep() // past TOUR_STEPS → dismiss
    expect(ob.tourStep.value).toBe(0)
    expect(ob.tourActive.value).toBe(false)
    expect(window.localStorage.getItem(ONBOARDING_KEY)).toContain('"seen":true')
  })

  it('once dismissed, a fresh instance never re-opens the tour', () => {
    useEditorOnboarding({ skipOnboarding: false, hasPlacement: ref(true) }).dismissTour()
    const next = useEditorOnboarding({ skipOnboarding: false, hasPlacement: ref(true) })
    next.startTourIfFirstRun()
    expect(next.tourStep.value).toBe(0)
  })
})

describe('useEditorOnboarding — preamble', () => {
  beforeEach(() => window.localStorage.clear())

  it('is visible with a placement and hides once dismissed (persisted)', () => {
    const ob = useEditorOnboarding({ skipOnboarding: false, hasPlacement: ref(true) })
    expect(ob.preambleVisible.value).toBe(true)
    ob.dismissPreamble()
    expect(ob.preambleVisible.value).toBe(false)
    expect(window.localStorage.getItem(PREAMBLE_KEY)).toContain('"dismissed":true')
  })

  it('is hidden when there is no placement', () => {
    const hasPlacement = ref(false)
    const ob = useEditorOnboarding({ skipOnboarding: false, hasPlacement })
    expect(ob.preambleVisible.value).toBe(false)
    hasPlacement.value = true
    expect(ob.preambleVisible.value).toBe(true)
  })

  it('starts dismissed when skipOnboarding is set', () => {
    const ob = useEditorOnboarding({ skipOnboarding: true, hasPlacement: ref(true) })
    expect(ob.preambleVisible.value).toBe(false)
  })

  it('respects a previously persisted dismissal', () => {
    window.localStorage.setItem(PREAMBLE_KEY, JSON.stringify({ dismissed: true }))
    const ob = useEditorOnboarding({ skipOnboarding: false, hasPlacement: ref(true) })
    expect(ob.preambleVisible.value).toBe(false)
  })
})
