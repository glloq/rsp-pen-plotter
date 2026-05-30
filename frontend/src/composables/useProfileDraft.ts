// Machine profile draft lifecycle for ProfileEditor (L10 #3).
//
// Wraps the bookkeeping that used to live inline at the top of
// ``ProfileEditor.vue``:
//   - clone the active store profile into a local editable draft
//   - keep an ``isUnsavedDraft`` flag so the in-memory "+ New"
//     profile isn't clobbered by store reloads before Save
//   - normalize the ``pens`` array against ``pen_slot_count`` on
//     every mutation
//   - save / duplicate / remove / download-yaml plumbing with
//     loading + error state
//
// Inputs are the store's reactive profile fields (passed by the
// caller via ``storeToRefs``); the composable owns the draft ref +
// the lifecycle calls back to the store via callbacks. This shape
// keeps the composable unit-testable without spinning up Pinia.

import { computed, ref, watch, type Ref } from 'vue'
import { exportProfileYaml, type EbbConfig, type MachineProfile, type PenSlot } from '../api/client'

export interface ProfileDraftCallbacks {
  /** POST the validated draft to the backend + reload the profile
   *  list. Resolves on success; throws with the server's detail
   *  message on failure (caught + surfaced via ``error``). */
  saveProfile: (profile: MachineProfile) => Promise<void>
  /** DELETE the named profile + reload the profile list. */
  deleteProfile: (name: string) => Promise<void>
}

export interface ProfileDraftInputs {
  /** The currently-selected store profile (null when no profile is
   *  selected, e.g. on first boot). */
  selectedProfile: Ref<MachineProfile | null>
  /** The full profile list — watched so a profile rename or list
   *  reload re-syncs the draft. */
  profiles: Ref<MachineProfile[]>
  /** Localised default name for the "+ New" blank profile. Passed
   *  in so the composable doesn't pull the i18n instance directly. */
  newProfileDefaultName: () => string
  /** Localised fallback messages for Save / Delete failures when the
   *  server doesn't return a ``detail`` field. */
  saveFailedMessage: () => string
  deleteFailedMessage: () => string
}

export function defaultEbb(): EbbConfig {
  return {
    steps_per_mm: 80,
    servo_up: 16000,
    servo_down: 12000,
    servo_rate: 400,
    serial_terminator: 'cr',
  }
}

export function defaultPen(index: number): PenSlot {
  return {
    index,
    name: `Pen ${index}`,
    color: '#000000',
    installed: true,
    position: null,
    pen_up_command: null,
    pen_down_command: null,
  }
}

// Deep, reactivity-free clone for the profile payload. Profiles are pure
// data (numbers / strings / booleans / null / nested objects), so a JSON
// round-trip is both correct and bulletproof: unlike ``structuredClone``
// it reads *through* Vue reactive proxies, so a proxy that leaked into a
// nested field (e.g. a retained pen slot) can never raise a
// ``DataCloneError`` at save time.
function plainClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export function normalizePens(profile: MachineProfile): void {
  const existing = profile.pens ?? []
  const count = Math.max(0, Math.floor(profile.pen_slot_count))
  profile.pens = Array.from({ length: count }, (_, i) => {
    const found = existing.find((p) => p.index === i)
    // Deep-plain copy of a retained slot: when this runs on a reactive
    // draft (the pen-count watcher), ``found`` is a reactive proxy, and
    // re-inserting it would poison the array so ``structuredClone`` later
    // throws. A plain copy keeps the draft serialisable.
    return found ? plainClone(found) : defaultPen(i)
  })
}

export function useProfileDraft(inputs: ProfileDraftInputs, callbacks: ProfileDraftCallbacks) {
  const draft = ref<MachineProfile | null>(null)
  const saving = ref(false)
  const error = ref<string | null>(null)
  // True when the active draft is an in-memory "+ New" profile that
  // has never been persisted. ``save()`` POSTs it; until then it's
  // not in ``profiles.value``, so we must not let ``syncDraft``
  // overwrite it on a profile-list reload.
  const isUnsavedDraft = ref(false)

  function newBlankProfile(): MachineProfile {
    // Sensible GRBL/A4-landscape defaults. The operator immediately
    // edits these, so the goal is "valid + visibly placeholder"
    // rather than "optimal".
    return {
      name: inputs.newProfileDefaultName(),
      units: 'mm',
      workspace: { x_min: 0, y_min: 0, x_max: 297, y_max: 210 },
      origin: 'top_left',
      gcode_dialect: 'grbl',
      pen_up_command: 'M5',
      pen_down_command: 'M3 S1000',
      tool_change_method: 'manual_pause',
      tool_change_command: 'M0',
      drawing_speed_mm_s: 50,
      travel_speed_mm_s: 100,
      acceleration_mm_s2: 1000,
      pen_slot_count: 1,
      supports_arcs: false,
      arc_tolerance_mm: 0.1,
      ebb: null,
      pens: null,
    }
  }

  function syncDraft(): void {
    if (isUnsavedDraft.value) return
    if (!inputs.selectedProfile.value) {
      draft.value = null
      return
    }
    const clone = plainClone(inputs.selectedProfile.value)
    normalizePens(clone)
    draft.value = clone
  }

  function startNewProfile(): void {
    const blank = newBlankProfile()
    normalizePens(blank)
    draft.value = blank
    isUnsavedDraft.value = true
  }

  watch(inputs.selectedProfile, syncDraft, { immediate: true })
  watch(inputs.profiles, syncDraft)

  const isEbb = computed(() => draft.value?.gcode_dialect === 'ebb')

  // Side-effect watchers — keep the EBB / pens substructures in
  // sync with their parent toggle / count so the v-model bindings
  // downstream never see ``null`` / undersized arrays.
  watch(
    () => draft.value?.gcode_dialect,
    (dialect) => {
      if (!draft.value) return
      if (dialect === 'ebb' && !draft.value.ebb) draft.value.ebb = defaultEbb()
    },
  )
  watch(
    () => draft.value?.pen_slot_count,
    () => {
      if (draft.value) normalizePens(draft.value)
    },
  )

  async function save(): Promise<void> {
    if (!draft.value) return
    saving.value = true
    error.value = null
    try {
      if (!isEbb.value) draft.value.ebb = null
      await callbacks.saveProfile(plainClone(draft.value))
      isUnsavedDraft.value = false
    } catch (err) {
      error.value =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        inputs.saveFailedMessage()
    } finally {
      saving.value = false
    }
  }

  function duplicate(): void {
    if (!draft.value) return
    const clone = plainClone(draft.value)
    draft.value = { ...clone, name: `${draft.value.name} copy` }
    isUnsavedDraft.value = true
  }

  async function remove(): Promise<void> {
    if (!draft.value) return
    error.value = null
    try {
      await callbacks.deleteProfile(draft.value.name)
    } catch (err) {
      error.value =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        inputs.deleteFailedMessage()
    }
  }

  async function downloadYaml(): Promise<void> {
    if (!draft.value) return
    const yaml = await exportProfileYaml(draft.value.name)
    const blob = new Blob([yaml], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${draft.value.name}.yaml`
    link.click()
    URL.revokeObjectURL(url)
  }

  return {
    draft,
    saving,
    error,
    isUnsavedDraft,
    isEbb,
    startNewProfile,
    save,
    duplicate,
    remove,
    downloadYaml,
  }
}
