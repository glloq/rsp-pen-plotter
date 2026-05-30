<script setup lang="ts">
// ProfileEditor orchestrator (L10 #3).
//
// Post-split this component wires:
//   - ``useProfileDraft`` for the draft lifecycle (sync from store,
//     save / duplicate / remove / downloadYaml, isUnsavedDraft flag,
//     normalize-pens watcher)
//   - ``<ProfilePenFields>`` for the biggest fieldset (~160 LOC of
//     pen / tool-change form + per-pen detail editor)
//
// The remaining fieldsets (Identity / Workspace / Motion / Advanced)
// stay inline because each is a self-contained ``<details>`` block
// that binds primitives directly against ``draft.*`` — extracting
// them would only add prop-pass-through boilerplate without any
// real benefit. ProfilePenFields is the one fieldset where the
// per-pen array UI gets noisy enough that its own home is worth it.

import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { confirmAction } from '../composables/confirm'
import { useJobStore } from '../stores/job'
import { useProfileDraft } from '../composables/useProfileDraft'
import ProfilePenFields from './ProfilePenFields.vue'

const { t } = useI18n()
const store = useJobStore()
const { profiles, selectedProfileName, presets, selectedPresetName, selectedProfile } =
  storeToRefs(store)

const {
  draft,
  saving,
  error,
  isUnsavedDraft,
  isEbb,
  startNewProfile,
  save,
  duplicate,
  remove: removeDraft,
  downloadYaml,
} = useProfileDraft(
  {
    selectedProfile,
    profiles,
    newProfileDefaultName: () => t('profile.newProfileDefault'),
    saveFailedMessage: () => t('profile.saveFailed'),
    deleteFailedMessage: () => t('profile.deleteFailed'),
  },
  {
    saveProfile: (profile) => store.saveProfile(profile),
    deleteProfile: (name) => store.deleteProfile(name),
  },
)

const workspaceSize = computed(() => {
  if (!draft.value) return { w: 0, h: 0 }
  const w = draft.value.workspace.x_max - draft.value.workspace.x_min
  const h = draft.value.workspace.y_max - draft.value.workspace.y_min
  return { w, h }
})

// A zero/negative span means the workspace rectangle is degenerate or
// inverted — generation would silently divide by a tiny epsilon, so we
// block the save and tell the operator which axis is wrong.
const workspaceInvalid = computed(() => workspaceSize.value.w <= 0 || workspaceSize.value.h <= 0)

// ``M204`` (acceleration) is only emitted for the firmwares that
// understand it. EBB / custom profiles ignore the field on the wire,
// though it still feeds the time estimate. Surface that so the operator
// isn't surprised the value "does nothing" on an AxiDraw.
const ACCEL_DIALECTS = ['grbl', 'marlin', 'klipper']
const accelOnWire = computed(() =>
  draft.value ? ACCEL_DIALECTS.includes(draft.value.gcode_dialect) : true,
)

async function remove(): Promise<void> {
  if (!draft.value) return
  const confirmed = await confirmAction({
    title: t('confirm.deleteProfileTitle'),
    message: t('confirm.deleteProfileMsg', { name: draft.value.name }),
    confirmLabel: t('profile.delete'),
    cancelLabel: t('confirm.cancel'),
    danger: true,
  })
  if (!confirmed) return
  await removeDraft()
}
</script>

<template>
  <div class="space-y-4 text-sm">
    <!-- Active profile picker — pinned at the top -->
    <div class="space-y-2 rounded-lg border border-slate-700 bg-slate-800/60 p-3">
      <label class="block text-xs text-slate-400">
        {{ t('profile.select') }}
        <div class="mt-1 flex gap-2">
          <select
            v-model="selectedProfileName"
            class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
          >
            <option v-for="profile in profiles" :key="profile.name" :value="profile.name">
              {{ profile.name }} ({{ profile.pen_slot_count }})
            </option>
          </select>
          <button
            type="button"
            class="rounded bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-500"
            :title="t('profile.newProfile')"
            @click="startNewProfile"
          >
            + {{ t('profile.newProfile') }}
          </button>
        </div>
      </label>
      <label class="block text-xs text-slate-400">
        {{ t('profile.preset') }}
        <select
          v-model="selectedPresetName"
          class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
        >
          <option value="">{{ t('upload.presetNone') }}</option>
          <option v-for="preset in presets" :key="preset.name" :value="preset.name">
            {{ preset.name }}
          </option>
        </select>
      </label>
      <p v-if="isUnsavedDraft" class="text-[11px] text-amber-300">
        ⚠ {{ t('profile.unsavedDraft') }}
      </p>
    </div>

    <div v-if="draft" class="space-y-3">
      <!-- IDENTITY -->
      <details open class="group rounded-lg border border-slate-700 bg-slate-800/40">
        <summary
          class="flex cursor-pointer items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200"
        >
          <span>① {{ t('profile.sectionIdentity') }}</span>
          <span class="text-[10px] text-slate-500 group-open:hidden">{{ draft.name }}</span>
        </summary>
        <div class="space-y-3 border-t border-slate-700 p-3">
          <label class="block text-slate-400">
            {{ t('profile.name') }}
            <input
              v-model="draft.name"
              type="text"
              class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
            />
            <span class="mt-0.5 block text-[11px] text-slate-500">{{ t('profile.nameHint') }}</span>
          </label>
          <label class="block text-slate-400">
            {{ t('profile.dialect') }}
            <select
              v-model="draft.gcode_dialect"
              class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
            >
              <option value="grbl">GRBL</option>
              <option value="marlin">Marlin</option>
              <option value="klipper">Klipper</option>
              <option value="ebb">EBB (EiBotBoard / AxiDraw)</option>
              <option value="custom">{{ t('profile.dialectCustom') }}</option>
            </select>
            <span class="mt-0.5 block text-[11px] text-slate-500">{{
              t('profile.dialectHint')
            }}</span>
          </label>
        </div>
      </details>

      <!-- WORKSPACE -->
      <details open class="group rounded-lg border border-slate-700 bg-slate-800/40">
        <summary
          class="flex cursor-pointer items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200"
        >
          <span>② {{ t('profile.sectionWorkspace') }}</span>
          <span class="text-[10px] text-slate-500 group-open:hidden">
            {{ Math.round(workspaceSize.w) }} × {{ Math.round(workspaceSize.h) }} {{ draft.units }}
          </span>
        </summary>
        <div class="space-y-3 border-t border-slate-700 p-3">
          <p class="text-[11px] text-slate-500">{{ t('profile.workspaceHint') }}</p>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-[1fr_180px]">
            <div class="space-y-2">
              <div class="grid grid-cols-2 gap-2">
                <label class="block text-slate-400"
                  >{{ t('profile.units') }}
                  <select
                    v-model="draft.units"
                    class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                  >
                    <option value="mm">mm</option>
                    <option value="inch">inch</option>
                  </select>
                  <span class="mt-0.5 block text-[11px] text-slate-500">{{
                    t('profile.unitsNoConvertHint')
                  }}</span>
                </label>
                <label class="block text-slate-400"
                  >{{ t('profile.origin') }}
                  <select
                    v-model="draft.origin"
                    class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                  >
                    <option value="top_left">{{ t('profile.originTopLeft') }}</option>
                    <option value="bottom_left">{{ t('profile.originBottomLeft') }}</option>
                  </select>
                </label>
                <label class="block text-slate-400"
                  >X min ({{ draft.units }})
                  <input
                    v-model.number="draft.workspace.x_min"
                    type="number"
                    step="any"
                    class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                  />
                </label>
                <label class="block text-slate-400"
                  >Y min ({{ draft.units }})
                  <input
                    v-model.number="draft.workspace.y_min"
                    type="number"
                    step="any"
                    class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                  />
                </label>
                <label class="block text-slate-400"
                  >X max ({{ draft.units }})
                  <input
                    v-model.number="draft.workspace.x_max"
                    type="number"
                    step="any"
                    class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                  />
                </label>
                <label class="block text-slate-400"
                  >Y max ({{ draft.units }})
                  <input
                    v-model.number="draft.workspace.y_max"
                    type="number"
                    step="any"
                    class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                  />
                </label>
              </div>
              <p class="text-[11px] text-slate-500">{{ t('profile.originHint') }}</p>
              <p
                v-if="workspaceInvalid"
                class="text-[11px] text-red-400"
                data-test="workspace-invalid"
              >
                ⚠ {{ t('profile.workspaceInvalid') }}
              </p>
            </div>

            <!-- Workspace preview -->
            <div
              class="flex items-start justify-center rounded border border-slate-700 bg-slate-900/60 p-2"
            >
              <svg
                viewBox="0 0 100 80"
                class="h-32 w-full"
                preserveAspectRatio="xMidYMid meet"
                aria-hidden="true"
              >
                <rect
                  x="10"
                  y="10"
                  width="80"
                  height="60"
                  fill="none"
                  stroke="#475569"
                  stroke-width="0.8"
                  stroke-dasharray="2 2"
                />
                <text
                  x="50"
                  y="42"
                  text-anchor="middle"
                  fill="#94a3b8"
                  font-size="6"
                  font-family="ui-monospace, monospace"
                >
                  {{ Math.round(workspaceSize.w) }} × {{ Math.round(workspaceSize.h) }}
                </text>
                <!-- Origin marker -->
                <g v-if="draft.origin === 'top_left'">
                  <circle cx="10" cy="10" r="2" fill="#10b981" />
                  <text x="14" y="9" fill="#10b981" font-size="5">0,0</text>
                </g>
                <g v-else>
                  <circle cx="10" cy="70" r="2" fill="#10b981" />
                  <text x="14" y="73" fill="#10b981" font-size="5">0,0</text>
                </g>
              </svg>
            </div>
          </div>
        </div>
      </details>

      <!-- MOTION -->
      <details open class="group rounded-lg border border-slate-700 bg-slate-800/40">
        <summary
          class="flex cursor-pointer items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200"
        >
          <span>③ {{ t('profile.motion') }}</span>
          <span class="text-[10px] text-slate-500 group-open:hidden">
            {{ draft.drawing_speed_mm_s }} / {{ draft.travel_speed_mm_s }} mm/s
          </span>
        </summary>
        <div class="space-y-3 border-t border-slate-700 p-3">
          <div class="grid grid-cols-2 gap-2">
            <label class="block text-slate-400"
              >{{ t('profile.drawingSpeed') }}
              <input
                v-model.number="draft.drawing_speed_mm_s"
                type="number"
                step="any"
                class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              />
              <span class="mt-0.5 block text-[11px] text-slate-500">{{
                t('profile.drawingSpeedHint')
              }}</span>
            </label>
            <label class="block text-slate-400"
              >{{ t('profile.travelSpeed') }}
              <input
                v-model.number="draft.travel_speed_mm_s"
                type="number"
                step="any"
                class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              />
              <span class="mt-0.5 block text-[11px] text-slate-500">{{
                t('profile.travelSpeedHint')
              }}</span>
            </label>
            <label class="col-span-2 block text-slate-400"
              >{{ t('profile.acceleration') }}
              <input
                v-model.number="draft.acceleration_mm_s2"
                type="number"
                step="any"
                class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              />
              <span class="mt-0.5 block text-[11px] text-slate-500">{{
                t('profile.accelerationHint')
              }}</span>
              <span
                v-if="!accelOnWire"
                class="mt-0.5 block text-[11px] text-amber-300"
                data-test="accel-not-on-wire"
                >⚠ {{ t('profile.accelerationNotOnWire') }}</span
              >
            </label>
          </div>

          <!-- Mechanical pen commands — machine motion config (the raw
               G-code that raises / lowers the pen). Lives here next to
               speed / acceleration rather than under colour management,
               because it's the same "how does the head move?" concern.
               Per-pen overrides live in the magazine editor. -->
          <div class="space-y-2 border-t border-slate-700 pt-3">
            <p class="text-[11px] uppercase tracking-wider text-slate-500">
              {{ t('profile.penCommands') }}
            </p>
            <div class="grid grid-cols-2 gap-2">
              <label class="block text-slate-400"
                >{{ t('profile.penUp') }}
                <input
                  v-model="draft.pen_up_command"
                  type="text"
                  class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100"
                />
                <span class="mt-0.5 block text-[11px] text-slate-500">{{
                  t('profile.penUpHint')
                }}</span>
              </label>
              <label class="block text-slate-400"
                >{{ t('profile.penDown') }}
                <input
                  v-model="draft.pen_down_command"
                  type="text"
                  class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100"
                />
                <span class="mt-0.5 block text-[11px] text-slate-500">{{
                  t('profile.penDownHint')
                }}</span>
              </label>
            </div>
          </div>
        </div>
      </details>

      <!-- PENS & TOOL -->
      <ProfilePenFields :draft="draft" />

      <!-- ADVANCED -->
      <details class="group rounded-lg border border-slate-700 bg-slate-800/40">
        <summary
          class="flex cursor-pointer items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200"
        >
          <span>⑤ {{ t('profile.advanced') }}</span>
          <span class="text-[10px] text-slate-500">{{ t('profile.advancedHint') }}</span>
        </summary>
        <div class="space-y-3 border-t border-slate-700 p-3">
          <label class="flex items-center gap-2 text-slate-400">
            <input
              v-model="draft.supports_arcs"
              type="checkbox"
              class="rounded border-slate-600 bg-slate-900"
            />
            {{ t('profile.supportsArcs') }}
          </label>
          <label v-if="draft.supports_arcs" class="block text-slate-400"
            >{{ t('profile.arcTolerance') }}
            <input
              v-model.number="draft.arc_tolerance_mm"
              type="number"
              step="any"
              class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
            />
            <span class="mt-0.5 block text-[11px] text-slate-500">{{
              t('profile.arcToleranceHint')
            }}</span>
          </label>

          <div
            v-if="isEbb && draft.ebb"
            class="space-y-2 rounded border border-slate-700 bg-slate-900/50 p-3"
          >
            <h4 class="text-[11px] uppercase tracking-wider text-slate-500">
              {{ t('profile.ebbSection') }}
            </h4>
            <p class="text-[11px] text-slate-500">{{ t('profile.ebbHint') }}</p>
            <div class="grid grid-cols-2 gap-2">
              <label class="block text-slate-400"
                >steps/mm
                <input
                  v-model.number="draft.ebb.steps_per_mm"
                  type="number"
                  step="any"
                  class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                />
                <span class="mt-0.5 block text-[11px] text-slate-500">{{
                  t('profile.stepsPerMmHint')
                }}</span>
              </label>
              <label class="block text-slate-400"
                >servo rate
                <input
                  v-model.number="draft.ebb.servo_rate"
                  type="number"
                  class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                />
                <span class="mt-0.5 block text-[11px] text-slate-500">{{
                  t('profile.servoRateHint')
                }}</span>
              </label>
              <label class="block text-slate-400"
                >servo up
                <input
                  v-model.number="draft.ebb.servo_up"
                  type="number"
                  class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                />
                <span class="mt-0.5 block text-[11px] text-slate-500">{{
                  t('profile.servoUpHint')
                }}</span>
              </label>
              <label class="block text-slate-400"
                >servo down
                <input
                  v-model.number="draft.ebb.servo_down"
                  type="number"
                  class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                />
                <span class="mt-0.5 block text-[11px] text-slate-500">{{
                  t('profile.servoDownHint')
                }}</span>
              </label>
              <label class="col-span-2 block text-slate-400"
                >{{ t('profile.serialTerminator') }}
                <select
                  v-model="draft.ebb.serial_terminator"
                  class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                >
                  <option value="cr">CR (\r) — EBB default</option>
                  <option value="lf">LF (\n)</option>
                  <option value="crlf">CRLF (\r\n)</option>
                </select>
                <span class="mt-0.5 block text-[11px] text-slate-500">{{
                  t('profile.serialTerminatorHint')
                }}</span>
              </label>
            </div>
          </div>
        </div>
      </details>

      <p v-if="error" class="text-sm text-red-400">{{ error }}</p>

      <div
        class="sticky bottom-0 -mx-4 -mb-4 flex flex-wrap gap-2 border-t border-slate-700 bg-slate-900/95 px-4 py-3 backdrop-blur"
      >
        <button
          type="button"
          class="flex-1 rounded bg-emerald-600 px-3 py-2 font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          :disabled="saving || workspaceInvalid"
          @click="save"
        >
          {{ saving ? t('profile.saving') : t('profile.save') }}
        </button>
        <button
          type="button"
          class="rounded bg-slate-700 px-3 py-2 text-slate-100 hover:bg-slate-600"
          @click="duplicate"
        >
          {{ t('profile.duplicate') }}
        </button>
        <button
          type="button"
          class="rounded bg-slate-700 px-3 py-2 text-slate-100 hover:bg-slate-600"
          @click="downloadYaml"
        >
          {{ t('profile.export') }}
        </button>
        <button
          type="button"
          class="rounded bg-red-900/70 px-3 py-2 text-red-200 hover:bg-red-800"
          @click="remove"
        >
          {{ t('profile.delete') }}
        </button>
      </div>
    </div>
  </div>
</template>
