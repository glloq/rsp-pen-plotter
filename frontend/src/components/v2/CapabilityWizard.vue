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

const state = reactive<MachineCapabilities>(defaultCapabilities('manual'))
const activeStep = ref<0 | 1 | 2>(0)

const modeOptions: { value: ToolingMode; label: string; help: string }[] = [
  {
    value: 'firmware',
    label: 'Firmware (M6/T<n>)',
    help: 'Le contrôleur gère le changement (carousel CNC, etc.).',
  },
  {
    value: 'host_macro',
    label: 'Macros host (rack)',
    help: 'Le Raspberry envoie une séquence G-code pour piloter le rack.',
  },
  {
    value: 'manual',
    label: 'Manuel guidé',
    help: 'La machine se positionne, l\'opérateur change le stylo, puis confirme.',
  },
  {
    value: 'single_pen',
    label: 'Mono-pen (aucun changement)',
    help: 'Un seul stylo pour tout le job.',
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
      return state.tool_change.host_macro.length > 0 &&
        state.tool_change.host_macro.every((s) => s.send.trim().length > 0)
    }
    if (state.tool_change.mode === 'manual') {
      return !!state.tool_change.manual_prompt?.body?.trim()
    }
  }
  return true
})

function next(): void {
  if (activeStep.value < 2) activeStep.value = ((activeStep.value + 1) as 0 | 1 | 2)
}
function previous(): void {
  if (activeStep.value > 0) activeStep.value = ((activeStep.value - 1) as 0 | 1 | 2)
}

function confirm(): void {
  emit('confirm', JSON.parse(JSON.stringify(state)) as MachineCapabilities)
}

const recoveryOptions: { value: RecoveryPolicy; label: string }[] = [
  { value: 'abort', label: 'Abandonner — le job est marqué en échec.' },
  {
    value: 'pause_and_prompt',
    label: 'Pause et demande à l\'opérateur (recommandé).',
  },
  {
    value: 'skip_layer',
    label: 'Sauter la couche et continuer (avancé).',
  },
]
</script>

<template>
  <div class="cap-wizard" data-test="capability-wizard">
    <header>
      <h3>Configurer la machine</h3>
      <span class="step-indicator">Étape {{ activeStep + 1 }} / 3</span>
    </header>

    <!-- Step 1: pick tool-change mode -->
    <section v-if="activeStep === 0" data-test="cap-step-mode">
      <p>Comment la machine change-t-elle de stylo&nbsp;?</p>
      <ul class="modes">
        <li
          v-for="opt in modeOptions"
          :key="opt.value"
          :class="{ active: state.tool_change.mode === opt.value }"
        >
          <button
            type="button"
            :data-test="`cap-mode-${opt.value}`"
            @click="setMode(opt.value)"
          >
            <strong>{{ opt.label }}</strong>
            <span>{{ opt.help }}</span>
          </button>
        </li>
      </ul>
    </section>

    <!-- Step 2: mode-specific knobs -->
    <section v-else-if="activeStep === 1" data-test="cap-step-details">
      <div v-if="state.tool_change.mode === 'manual'" data-test="cap-manual-knobs">
        <p>Personnalise la consigne affichée à l'opérateur&nbsp;:</p>
        <label>
          Titre
          <input
            v-model="state.tool_change.manual_prompt!.title"
            type="text"
            data-test="cap-manual-title"
          />
        </label>
        <label>
          Corps
          <textarea
            v-model="state.tool_change.manual_prompt!.body"
            rows="3"
            data-test="cap-manual-body"
          ></textarea>
        </label>
        <small>Variables supportées&nbsp;: <code>{color}</code>, <code>{slot}</code>, <code>{label}</code>.</small>
      </div>

      <div v-else-if="state.tool_change.mode === 'host_macro'" data-test="cap-macro-knobs">
        <p>Séquence de commandes envoyée à chaque changement&nbsp;:</p>
        <ol class="macro-steps">
          <li v-for="(step, i) in state.tool_change.host_macro" :key="i">
            <input
              v-model="step.send"
              type="text"
              placeholder="ex: M6 T{slot}"
              :data-test="`cap-macro-send-${i}`"
            />
            <input
              v-model.number="step.wait_ms"
              type="number"
              min="0"
              step="50"
              :data-test="`cap-macro-wait-${i}`"
            />
            <button
              type="button"
              :data-test="`cap-macro-remove-${i}`"
              @click="removeMacroStep(i)"
            >
              −
            </button>
          </li>
        </ol>
        <button type="button" data-test="cap-macro-add" @click="addMacroStep">+ Ligne</button>
      </div>

      <div v-else data-test="cap-no-knobs">
        Aucune configuration requise pour le mode
        « {{ state.tool_change.mode }} ».
      </div>
    </section>

    <!-- Step 3: recovery + magazine + confirm -->
    <section v-else data-test="cap-step-finalize">
      <p>Que faire en cas d'échec d'un changement&nbsp;?</p>
      <ul class="recovery">
        <li v-for="opt in recoveryOptions" :key="opt.value">
          <label>
            <input
              v-model="state.tool_change.recovery_policy"
              type="radio"
              :value="opt.value"
            />
            {{ opt.label }}
          </label>
        </li>
      </ul>
      <label class="magazine">
        Taille du magasin
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
      <button type="button" @click="emit('cancel')">Annuler</button>
      <button type="button" :disabled="activeStep === 0" @click="previous">Précédent</button>
      <button
        v-if="activeStep < 2"
        type="button"
        :disabled="!canAdvance"
        data-test="cap-next"
        @click="next"
      >
        Suivant
      </button>
      <button v-else type="button" data-test="cap-confirm" @click="confirm">
        Enregistrer
      </button>
    </footer>
  </div>
</template>

<style scoped>
.cap-wizard {
  font-family: system-ui, sans-serif;
  font-size: 0.9rem;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 1rem 1.25rem;
  background: white;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.75rem;
}
h3 {
  margin: 0;
  font-size: 1rem;
}
.step-indicator {
  color: #666;
  font-size: 0.85rem;
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
  padding: 0.75rem;
  border: 1px solid #d0d0d0;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  text-align: left;
  width: 100%;
}
.modes li.active button {
  border-color: #1f6feb;
  background: #eef4ff;
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
</style>
