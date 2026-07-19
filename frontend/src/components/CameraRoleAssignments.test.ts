// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import CameraRoleAssignments from './CameraRoleAssignments.vue'
import { useJobStore } from '../stores/job'
import { useTimelapseStore } from '../stores/timelapse'
import { useUiStore } from '../stores/ui'
import type { MachineProfile } from '../api/client'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      cameraRoles: {
        title: 'Camera roles',
        hint: 'Assign each use.',
        timelapse: 'Timelapse',
        offset: 'Offset measurement',
        noCameras: 'No camera configured',
        needsProfile: 'Select a machine profile',
        customUrl: 'Custom URL',
        customUrlHint: 'Hand-typed URL in use.',
        unassigned: 'no role',
      },
      system: { cameraN: 'Camera {n}' },
      profile: { saveFailed: 'Save failed' },
    },
  },
})

function makeProfile(over: Partial<MachineProfile> = {}): MachineProfile {
  return {
    name: 'Cam Test A3',
    units: 'mm',
    workspace: { x_min: 0, y_min: 0, x_max: 297, y_max: 420 },
    origin: 'bottom_left',
    gcode_dialect: 'grbl',
    pen_up_command: 'M3 S0',
    pen_down_command: 'M3 S1000',
    tool_change_method: 'manual_pause',
    tool_change_command: 'M0',
    drawing_speed_mm_s: 30,
    travel_speed_mm_s: 80,
    acceleration_mm_s2: 500,
    pen_lift_time_ms: 0,
    pen_slot_count: 1,
    supports_arcs: false,
    arc_tolerance_mm: 0.1,
    ebb: null,
    pens: null,
    ...over,
  } as MachineProfile
}

function seedCameras(): void {
  const ui = useUiStore()
  ui.cameras[0]!.enabled = true
  ui.cameras[0]!.url = 'http://cam-a/stream'
  ui.cameras[0]!.label = 'Atelier'
  ui.cameras[1]!.enabled = true
  ui.cameras[1]!.url = 'http://cam-b/stream'
  ui.cameras[1]!.label = 'Station'
}

function seedProfile(over: Partial<MachineProfile> = {}): void {
  const job = useJobStore()
  const { profiles, selectedProfileName } = storeToRefs(job)
  const profile = makeProfile(over)
  profiles.value = [profile]
  selectedProfileName.value = profile.name
}

function mountPanel() {
  return mount(CameraRoleAssignments, { global: { plugins: [i18n] } })
}

describe('CameraRoleAssignments', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('shows the empty hint when no camera is configured', () => {
    const wrapper = mountPanel()
    expect(wrapper.find('[data-test="camera-roles-empty"]').exists()).toBe(true)
  })

  it('assigning the timelapse role writes the timelapse store slot', async () => {
    seedCameras()
    const timelapse = useTimelapseStore()
    const wrapper = mountPanel()
    await wrapper.find('[data-test="camera-role-timelapse"]').setValue('1')
    expect(timelapse.cameraSlot).toBe(1)
  })

  it('assigning the offset role saves the camera URL onto the profile', async () => {
    seedCameras()
    seedProfile({ tip_calibration: null })
    const job = useJobStore()
    const save = vi.spyOn(job, 'saveProfile').mockResolvedValue(undefined as never)
    const wrapper = mountPanel()
    await wrapper.find('[data-test="camera-role-offset"]').setValue('1')
    await nextTick()
    expect(save).toHaveBeenCalledTimes(1)
    const saved = save.mock.calls[0]?.[0] as MachineProfile
    expect(saved.tip_calibration?.camera_url).toBe('http://cam-b/stream')
    // Creating the block from scratch ships the full default config.
    expect(saved.tip_calibration?.detector).toBe('dark_blob')
  })

  it('one camera can hold both roles (single-USB setup)', async () => {
    const ui = useUiStore()
    ui.cameras[0]!.enabled = true
    ui.cameras[0]!.url = 'http://only/stream'
    seedProfile({
      tip_calibration: {
        camera_url: 'http://only/stream',
        reference_slot: 0,
        mm_per_pixel: 0.1,
        detector: 'dark_blob',
        samples: 1,
      } as MachineProfile['tip_calibration'],
    })
    const timelapse = useTimelapseStore()
    timelapse.cameraSlot = 0
    const wrapper = mountPanel()
    const summary = wrapper.find('[data-test="camera-roles-summary"]')
    expect(summary.text()).toContain('Timelapse')
    expect(summary.text()).toContain('Offset measurement')
  })

  it('flags a hand-typed offset URL instead of rewriting it', () => {
    seedCameras()
    seedProfile({
      tip_calibration: {
        camera_url: 'http://typed-by-hand/other',
        reference_slot: 0,
        mm_per_pixel: 0.1,
        detector: 'dark_blob',
        samples: 1,
      } as MachineProfile['tip_calibration'],
    })
    const wrapper = mountPanel()
    const select = wrapper.find('[data-test="camera-role-offset"]')
    expect((select.element as HTMLSelectElement).value).toBe('custom')
    expect(wrapper.find('[data-test="camera-role-offset-custom"]').exists()).toBe(true)
  })
})
