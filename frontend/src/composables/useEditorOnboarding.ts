// First-run onboarding for the V2 editor modal: the three-step welcome
// tour and the one-sentence preamble card above the preview.
//
// Extracted from ``EditModalV2.vue`` (Phase 2 of the editor audit). Both
// surfaces persist a localStorage flag so they never reappear once seen /
// dismissed; ``skipOnboarding`` overrides for tests and embeds. Pure
// state + localStorage, so it's unit-testable without mounting the modal.
import { computed, ref, type ComputedRef, type Ref } from 'vue'

const ONBOARDING_KEY = 'omniplot.onboarding.editorV2.v1'
const PREAMBLE_KEY = 'omniplot.preamble.editorV2.v1'
const TOUR_STEPS = 3

interface OnboardingState {
  seen: boolean
}

function readOnboarding(): OnboardingState {
  try {
    const raw = window.localStorage.getItem(ONBOARDING_KEY)
    if (!raw) return { seen: false }
    const parsed = JSON.parse(raw) as Partial<OnboardingState>
    return { seen: parsed.seen === true }
  } catch {
    return { seen: false }
  }
}

function persistOnboardingSeen(): void {
  try {
    window.localStorage.setItem(ONBOARDING_KEY, JSON.stringify({ seen: true }))
  } catch {
    /* private mode / quota — accept that the tour may replay */
  }
}

function readPreambleDismissed(): boolean {
  try {
    const raw = window.localStorage.getItem(PREAMBLE_KEY)
    if (!raw) return false
    const parsed = JSON.parse(raw) as { dismissed?: boolean }
    return parsed.dismissed === true
  } catch {
    return false
  }
}

export interface EditorOnboardingDeps {
  /** ``props.skipOnboarding`` — never show onboarding when true. */
  skipOnboarding: boolean
  hasPlacement: Ref<boolean> | ComputedRef<boolean>
}

export function useEditorOnboarding(deps: EditorOnboardingDeps) {
  // ---- Welcome tour ----
  const tourStep = ref<number>(0) // 0 = inactive; 1..TOUR_STEPS = visible
  const tourActive = computed<boolean>(() => tourStep.value > 0)

  function startTourIfFirstRun(): void {
    if (deps.skipOnboarding) return
    if (!deps.hasPlacement.value) return
    if (readOnboarding().seen) return
    tourStep.value = 1
  }
  function nextTourStep(): void {
    if (tourStep.value >= TOUR_STEPS) {
      dismissTour()
      return
    }
    tourStep.value += 1
  }
  function dismissTour(): void {
    tourStep.value = 0
    persistOnboardingSeen()
  }

  // ---- Preamble card ----
  // One-sentence context card above the preview ("your machine will draw
  // this"). Persisted dismissal so it disappears once read.
  const preambleDismissed = ref<boolean>(deps.skipOnboarding ? true : readPreambleDismissed())
  const preambleVisible = computed<boolean>(
    () => !preambleDismissed.value && deps.hasPlacement.value,
  )
  function dismissPreamble(): void {
    preambleDismissed.value = true
    try {
      window.localStorage.setItem(PREAMBLE_KEY, JSON.stringify({ dismissed: true }))
    } catch {
      /* private mode / quota — accept that the preamble may replay */
    }
  }

  return {
    TOUR_STEPS,
    tourStep,
    tourActive,
    startTourIfFirstRun,
    nextTourStep,
    dismissTour,
    preambleVisible,
    dismissPreamble,
  }
}
