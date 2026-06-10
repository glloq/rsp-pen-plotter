<script setup lang="ts">
// Capability Wizard (roadmap C.4).
//
// Guides a non-technical operator through configuring a plotter's
// tool-change behaviour. Emits a complete MachineCapabilities object
// at the end. UI conditionnal sur le mode sélectionné (les knobs
// pertinents pour `manual` et `host_macro` n'apparaissent que là).
//
// Steps:
//   1. Pick a tool-change mode (firmware / host_macro / manual / single_pen).
//   2. Configure the mode-specific knobs (manual prompt, host macro lines).
//   3. Pick a recovery policy + magazine size + confirm.

import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  defaultCapabilities,
  type MachineCapabilities,
  type ToolingMode,
  type RecoveryPolicy,
  type CommandSource,
} from '../../domain/capability/schemas'

const emit = defineEmits<{
  (e: 'cancel'): void
  (e: 'confirm', capabilities: MachineCapabilities): void
}>()

const { t } = useI18n()

const state = reactive<MachineCapabilities>(defaultCapabilities('manual'))
const activeStep = ref<0 | 1 | 2>(0)

const modeOptions: { value: ToolingMode; labelKey: string; helpKey: string }[] = [
  {
    value: 'firmware',
    labelKey: 'v2.capability.modeFirmwareLabel',
    helpKey: 'v2.capability.modeFirmwareHelp',
  },
  {
    value: 'host_macro',
    labelKey: 'v2.capability.modeHostMacroLabel',
    helpKey: 'v2.capability.modeHostMacroHelp',
  },
  {
    value: 'manual',
    labelKey: 'v2.capability.modeManualLabel',
    helpKey: 'v2.capability.modeManualHelp',
  },
  {
    value: 'single_pen',
    labelKey: 'v2.capability.modeSinglePenLabel',
    helpKey: 'v2.capability.modeSinglePenHelp',
  },
]

function setMode(mode: ToolingMode): void {
  const source: CommandSource =
    mode === 'firmware' ? 'machine' : mode === 'host_macro' ? 'host' : 'operator'
  state.tool_change.mode = mode
  state.tool_change.command_source = source
  if (mode === 'manual' && state.tool_change.manual_prompt === null) {
    state.tool_change.manual_prompt = {
      title: 'Change pen',
      body: 'Insert pen {color}, then press Resume.',
      timeout_s: null,
    }
  } else if (mode !== 'manual') {
    state.tool_change.manual_prompt = null
  }
  if (mode === 'single_pen') {
    state.max_pens_in_magazine = 1
  }
}

function addMacroStep(): void {
  state.tool_change.host_macro.push({ send: '', wait_ms: 0 })
}

function removeMacroStep(i: number): void {
  state.tool_change.host_macro.splice(i, 1)
}

const canAdvance = computed<boolean>(() => {
  if (activeStep.value === 1) {
    if (state.tool_change.mode === 'host_macro') {
      return (
        state.tool_change.host_macro.length > 0 &&
        state.tool_change.host_macro.every((s) => s.send.trim().length > 0)
      )
    }
    if (state.tool_change.mode === 'manual') {
      return !!state.tool_change.manual_prompt?.body?.trim()
    }
  }
  return true
})

function next(): void {
  if (activeStep.value < 2) activeStep.value = (activeStep.value + 1) as 0 | 1 | 2
}
function previous(): void {
  if (activeStep.value > 0) activeStep.value = (activeStep.value - 1) as 0 | 1 | 2
}

function confirm(): void {
  emit('confirm', JSON.parse(JSON.stringify(state)) as MachineCapabilities)
}

const recoveryOptions: { value: RecoveryPolicy; labelKey: string }[] = [
  { value: 'abort', labelKey: 'v2.capability.recoveryAbort' },
  { value: 'pause_and_prompt', labelKey: 'v2.capability.recoveryPausePrompt' },
  { value: 'skip_layer', labelKey: 'v2.capability.recoverySkipLayer' },
]
</script>

<template>
  <div class="cap-wizard" data-test="capability-wizard">
    <header>
      <h3>{{ t('v2.capability.title') }}</h3>
      <span class="step-indicator">{{
        t('v2.capability.stepIndicator', { current: activeStep + 1, total: 3 })
      }}</span>
    </header>

    <!-- Step 1: pick tool-change mode -->
    <section v-if="activeStep === 0" data-test="cap-step-mode">
      <p>{{ t('v2.capability.modeQuestion') }}</p>
      <ul class="modes">
        <li
          v-for="opt in modeOptions"
          :key="opt.value"
          :class="{ active: state.tool_change.mode === opt.value }"
        >
          <button type="button" :data-test="`cap-mode-${opt.value}`" @click="setMode(opt.value)">
            <strong>{{ t(opt.labelKey) }}</strong>
            <span>{{ t(opt.helpKey) }}</span>
          </button>
        </li>
      </ul>
    </section>

    <!-- Step 2: mode-specific knobs -->
    <section v-else-if="activeStep === 1" data-test="cap-step-details">
      <div v-if="state.tool_change.mode === 'manual'" data-test="cap-manual-knobs">
        <p>{{ t('v2.capability.manualIntro') }}</p>
        <label>
          {{ t('v2.capability.manualTitle') }}
          <input
            v-model="state.tool_change.manual_prompt!.title"
            type="text"
            data-test="cap-manual-title"
          />
        </label>
        <label>
          {{ t('v2.capability.manualBody') }}
          <textarea
            v-model="state.tool_change.manual_prompt!.body"
            rows="3"
            data-test="cap-manual-body"
          ></textarea>
        </label>
        <small
          >{{ t('v2.capability.variablesSupported') }} <code>{{ '{color}' }}</code
          >, <code>{{ '{slot}' }}</code
          >, <code>{{ '{label}' }}</code
          >.</small
        >
      </div>

      <div v-else-if="state.tool_change.mode === 'host_macro'" data-test="cap-macro-knobs">
        <p>{{ t('v2.capability.macroIntro') }}</p>
        <ol class="macro-steps">
          <li v-for="(step, i) in state.tool_change.host_macro" :key="i">
            <input
              v-model="step.send"
              type="text"
              :placeholder="t('v2.capability.macroPlaceholder', { slot: '{slot}' })"
              :data-test="`cap-macro-send-${i}`"
            />
            <input
              v-model.number="step.wait_ms"
              type="number"
              min="0"
              step="50"
              :data-test="`cap-macro-wait-${i}`"
            />
            <button type="button" :data-test="`cap-macro-remove-${i}`" @click="removeMacroStep(i)">
              −
            </button>
          </li>
        </ol>
        <button type="button" data-test="cap-macro-add" @click="addMacroStep">
          {{ t('v2.capability.addLine') }}
        </button>
      </div>

      <div v-else data-test="cap-no-knobs">
        {{ t('v2.capability.noKnobs', { mode: state.tool_change.mode }) }}
      </div>
    </section>

    <!-- Step 3: recovery + magazine + confirm -->
    <section v-else data-test="cap-step-finalize">
      <p>{{ t('v2.capability.recoveryQuestion') }}</p>
      <ul class="recovery">
        <li v-for="opt in recoveryOptions" :key="opt.value">
          <label>
            <input v-model="state.tool_change.recovery_policy" type="radio" :value="opt.value" />
            {{ t(opt.labelKey) }}
          </label>
        </li>
      </ul>
      <label class="magazine">
        {{ t('v2.capability.magazineSize') }}
        <input
          v-model.number="state.max_pens_in_magazine"
          type="number"
          min="1"
          max="32"
          data-test="cap-magazine-size"
        />
      </label>
    </section>

    <footer>
      <button type="button" @click="emit('cancel')">{{ t('v2.capability.cancel') }}</button>
      <button type="button" :disabled="activeStep === 0" @click="previous">
        {{ t('v2.capability.previous') }}
      </button>
      <button
        v-if="activeStep < 2"
        type="button"
        :disabled="!canAdvance"
        data-test="cap-next"
        @click="next"
      >
        {{ t('v2.capability.next') }}
      </button>
      <button v-else type="button" data-test="cap-confirm" @click="confirm">
        {{ t('v2.capability.save') }}
      </button>
    </footer>
  </div>
</template>

<style scoped>
.cap-wizard {
  font-size: 0.875rem;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  background: #1e293b;
  color: #f1f5f9;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.75rem;
}
h3 {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
}
.step-indicator {
  color: #94a3b8;
  font-size: 0.75rem;
}
.modes {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.5rem;
}
.modes li button {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.2rem;
  padding: 0.75rem;
  border: 1px solid #334155;
  border-radius: 8px;
  background: #0f172a;
  color: inherit;
  cursor: pointer;
  text-align: left;
  width: 100%;
}
.modes li button span {
  font-size: 0.75rem;
  color: #94a3b8;
}
.modes li button:hover {
  background: #1e293b;
  border-color: #475569;
}
.modes li.active button {
  border-color: #059669;
  background: rgba(2, 44, 34, 0.45);
  box-shadow: inset 0 0 0 1px #059669;
}
input[type='text'],
input[type='number'],
textarea {
  border: 1px solid #334155;
  background: #0f172a;
  color: #f1f5f9;
  border-radius: 4px;
  padding: 0.3rem 0.5rem;
  font-size: 0.875rem;
}
input:focus-visible,
textarea:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 1px;
}
section > div > label {
  display: block;
  margin-bottom: 0.5rem;
}
small {
  color: #94a3b8;
}
.macro-steps {
  list-style: none;
  padding: 0;
  margin: 0.5rem 0;
}
.macro-steps li {
  display: grid;
  grid-template-columns: 1fr 6rem 2rem;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}
.recovery {
  list-style: none;
  padding: 0;
  margin: 0;
}
.magazine {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
.magazine input {
  width: 5rem;
}
footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1rem;
}
footer button,
.macro-steps button,
button[data-test='cap-macro-add'] {
  padding: 0.4rem 0.75rem;
  border: 1px solid #334155;
  background: #1e293b;
  color: #e2e8f0;
  border-radius: 4px;
  cursor: pointer;
}
footer button:hover:not(:disabled),
.macro-steps button:hover,
button[data-test='cap-macro-add']:hover {
  background: #334155;
}
footer button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
footer button[data-test='cap-confirm'] {
  border-color: #059669;
  background: #059669;
  color: white;
}
footer button[data-test='cap-confirm']:hover {
  background: #10b981;
}
</style>
