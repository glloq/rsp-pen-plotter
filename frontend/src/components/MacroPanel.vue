<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Macro } from '../api/client'
import { useMacroStore } from '../stores/macros'
import { usePlotterStore } from '../stores/plotter'

const { t } = useI18n()
const store = useMacroStore()
const plotter = usePlotterStore()

const open = ref(false)
const editName = ref('')
const editDescription = ref('')
const editCommands = ref('')

const canRun = computed(
  () => plotter.status.connected && !['running', 'paused'].includes(plotter.status.state),
)

onMounted(() => {
  void store.load()
})

function edit(macro: Macro): void {
  editName.value = macro.name
  editDescription.value = macro.description
  editCommands.value = macro.commands.join('\n')
}

function reset(): void {
  editName.value = ''
  editDescription.value = ''
  editCommands.value = ''
}

async function save(): Promise<void> {
  const name = editName.value.trim()
  if (!name) return
  const commands = editCommands.value
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
  await store.save({ name, description: editDescription.value.trim(), commands })
  reset()
}
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800">
    <button
      type="button"
      class="flex w-full items-center justify-between px-4 py-3 text-sm uppercase tracking-wide text-slate-300"
      @click="open = !open"
    >
      {{ t('macros.title') }}
      <span class="text-slate-500">{{ open ? '−' : '+' }}</span>
    </button>

    <div v-if="open" class="space-y-3 border-t border-slate-700 p-4 text-sm">
      <p v-if="!store.macros.length" class="text-slate-500">{{ t('macros.empty') }}</p>

      <div
        v-for="macro in store.macros"
        :key="macro.name"
        class="rounded border border-slate-700 bg-slate-900/50 px-3 py-2"
      >
        <div class="flex items-center gap-2">
          <div class="min-w-0 flex-1">
            <p class="truncate font-medium text-slate-200">{{ macro.name }}</p>
            <p v-if="macro.description" class="truncate text-xs text-slate-500">
              {{ macro.description }}
            </p>
          </div>
          <button
            class="rounded bg-emerald-600 px-2 py-1 text-xs text-white hover:bg-emerald-500 disabled:opacity-40"
            :disabled="!canRun"
            :title="canRun ? '' : t('macros.runHint')"
            @click="store.run(macro.name)"
          >
            {{ t('macros.run') }}
          </button>
          <button
            class="rounded bg-slate-700 px-2 py-1 text-xs text-slate-100 hover:bg-slate-600"
            @click="edit(macro)"
          >
            {{ t('macros.edit') }}
          </button>
          <button
            class="rounded bg-red-900/70 px-2 py-1 text-xs text-red-200 hover:bg-red-800"
            @click="store.remove(macro.name)"
          >
            ×
          </button>
        </div>
      </div>

      <div class="space-y-2 border-t border-slate-700 pt-3">
        <input
          v-model="editName"
          type="text"
          :placeholder="t('macros.name')"
          class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        />
        <input
          v-model="editDescription"
          type="text"
          :placeholder="t('macros.description')"
          class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        />
        <textarea
          v-model="editCommands"
          rows="3"
          :placeholder="t('macros.commands')"
          class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100"
        />
        <div class="flex gap-2">
          <button
            class="flex-1 rounded bg-sky-600 px-3 py-2 font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            :disabled="!editName.trim()"
            @click="save"
          >
            {{ t('macros.save') }}
          </button>
          <button
            class="rounded bg-slate-700 px-3 py-2 text-slate-100 hover:bg-slate-600"
            @click="reset"
          >
            {{ t('macros.clear') }}
          </button>
        </div>
      </div>

      <p v-if="store.error" class="text-sm text-red-400">{{ store.error }}</p>
    </div>
  </div>
</template>
