<script setup lang="ts">
// Pen + tool-change fieldset for ProfileEditor (L10 #3 extract).
//
// Receives the draft profile via v-model so the parent stays the
// single owner of the editable state. The fieldset binds nested
// fields (pens[], pen_up_command, tool_change_method, etc.) via
// two-way bindings against the draft slice — Vue allows mutating
// nested object/array contents through a prop without tripping
// ``vue/no-mutating-props``, which is what the parent expects.
//
// Why this fieldset specifically lives in its own component:
// it's the biggest section in ProfileEditor (~160 LOC of template)
// AND ships per-pen detail editing (color picker + pickup position +
// per-pen up/down command overrides) that has no overlap with the
// other sections. Splitting it makes ProfileEditor easier to read
// and gives the per-pen UI a focused home for future tweaks.

import { useI18n } from 'vue-i18n'
import type { MachineProfile } from '../api/client'

const { t } = useI18n()

defineProps<{
  draft: MachineProfile
}>()
</script>

<template>
  <details open class="group rounded-lg border border-slate-700 bg-slate-800/40">
    <summary
      class="flex cursor-pointer items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200"
    >
      <span>④ {{ t('profile.pen') }}</span>
      <span class="text-[10px] text-slate-500 group-open:hidden"
        >{{ draft.pen_slot_count }} slot(s)</span
      >
    </summary>
    <div class="space-y-3 border-t border-slate-700 p-3">
      <div class="grid grid-cols-2 gap-2">
        <label class="block text-slate-400"
          >{{ t('profile.penUp') }}
          <input
            v-model="draft.pen_up_command"
            type="text"
            class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100"
          />
          <span class="mt-0.5 block text-[11px] text-slate-500">{{ t('profile.penUpHint') }}</span>
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
        <label class="block text-slate-400"
          >{{ t('profile.toolChangeMethod') }}
          <select
            v-model="draft.tool_change_method"
            class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          >
            <option value="manual_pause">{{ t('profile.tcManualPause') }}</option>
            <option value="carousel">{{ t('profile.tcCarousel') }}</option>
            <option value="rack">{{ t('profile.tcRack') }}</option>
            <option value="none">{{ t('profile.tcNone') }}</option>
          </select>
          <span class="mt-0.5 block text-[11px] text-slate-500">{{
            t('profile.toolChangeMethodHint')
          }}</span>
        </label>
        <label class="block text-slate-400"
          >{{ t('profile.toolChangeCommand') }}
          <input
            v-model="draft.tool_change_command"
            type="text"
            class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100"
          />
        </label>
        <label class="col-span-2 block text-slate-400"
          >{{ t('profile.penSlots') }}
          <input
            v-model.number="draft.pen_slot_count"
            type="number"
            min="1"
            class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          />
          <span class="mt-0.5 block text-[11px] text-slate-500">{{
            t('profile.penSlotsHint')
          }}</span>
        </label>
      </div>

      <div v-if="draft.pens && draft.pens.length" class="space-y-2 border-t border-slate-700 pt-3">
        <div class="flex items-baseline justify-between">
          <h4 class="text-[11px] uppercase tracking-wider text-slate-500">
            {{ t('profile.magazine') }}
          </h4>
          <span class="text-[10px] text-slate-500">{{ t('profile.magazineMovedHint') }}</span>
        </div>
        <div
          v-for="pen in draft.pens"
          :key="pen.index"
          class="rounded border border-slate-700 bg-slate-900/50 p-2"
        >
          <div class="flex items-center gap-2">
            <span class="w-6 shrink-0 text-center font-mono text-slate-500">{{ pen.index }}</span>
            <span
              class="h-7 w-9 shrink-0 rounded border border-slate-700"
              :style="{ backgroundColor: pen.color }"
              :title="pen.color"
              :aria-label="pen.color"
            />
            <input
              v-model="pen.name"
              type="text"
              :placeholder="`Pen ${pen.index}`"
              class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
            />
            <label class="flex shrink-0 items-center gap-1 text-xs text-slate-400">
              <input
                v-model="pen.installed"
                type="checkbox"
                class="rounded border-slate-600 bg-slate-900"
              />
              {{ t('profile.installed') }}
            </label>
          </div>
          <label class="mt-1 flex items-center gap-2 text-xs text-slate-400">
            <input
              type="checkbox"
              :checked="pen.position !== null"
              class="rounded border-slate-600 bg-slate-900"
              @change="
                (e) =>
                  (pen.position = (e.target as HTMLInputElement).checked ? { x: 0, y: 0 } : null)
              "
            />
            {{ t('profile.pickupPosition') }}
          </label>
          <div v-if="pen.position" class="mt-1 grid grid-cols-2 gap-2">
            <input
              v-model.number="pen.position.x"
              type="number"
              step="any"
              placeholder="X"
              class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
            />
            <input
              v-model.number="pen.position.y"
              type="number"
              step="any"
              placeholder="Y"
              class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
            />
          </div>
          <div class="mt-1 grid grid-cols-2 gap-2">
            <label class="block text-slate-500"
              >{{ t('profile.penUpOverride') }}
              <input
                v-model="pen.pen_up_command"
                type="text"
                :placeholder="draft.pen_up_command"
                class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100"
              />
            </label>
            <label class="block text-slate-500"
              >{{ t('profile.penDownOverride') }}
              <input
                v-model="pen.pen_down_command"
                type="text"
                :placeholder="draft.pen_down_command"
                class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100"
              />
            </label>
          </div>
        </div>
      </div>
    </div>
  </details>
</template>
