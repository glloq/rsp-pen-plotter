<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'

const { t } = useI18n()
const store = useJobStore()
const { profiles, selectedProfileName, presets, selectedPresetName } = storeToRefs(store)
const fileInput = ref<HTMLInputElement | null>(null)

async function onFileChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    await store.upload(file)
  }
  target.value = ''
}

function openPicker(): void {
  fileInput.value?.click()
}
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800 p-4 space-y-3">
    <label class="block text-sm text-slate-400">
      {{ t('upload.profile') }}
      <select
        v-model="selectedProfileName"
        class="mt-1 w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-slate-100"
      >
        <option v-for="profile in profiles" :key="profile.name" :value="profile.name">
          {{ profile.name }} ({{ profile.pen_slot_count }})
        </option>
      </select>
    </label>

    <label class="block text-sm text-slate-400">
      {{ t('upload.preset') }}
      <select
        v-model="selectedPresetName"
        class="mt-1 w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-slate-100"
      >
        <option value="">{{ t('upload.presetNone') }}</option>
        <option v-for="preset in presets" :key="preset.name" :value="preset.name">
          {{ preset.name }}
        </option>
      </select>
    </label>

    <input
      ref="fileInput"
      type="file"
      class="hidden"
      accept=".svg,.png,.jpg,.jpeg,.tiff,.webp,.heic,.pdf,.dxf,.eps,.ps,.ai,.txt,.md,.html,.docx,.odt,.rtf"
      @change="onFileChange"
    />
    <button
      type="button"
      class="w-full rounded bg-emerald-600 hover:bg-emerald-500 px-4 py-2 font-medium text-white disabled:opacity-50"
      :disabled="store.loading"
      @click="openPicker"
    >
      {{ store.loading ? t('upload.converting') : t('upload.choose') }}
    </button>

    <p v-if="store.error" class="text-sm text-red-400">{{ t('upload.failed') }}</p>
    <p v-else-if="store.job" class="text-sm text-slate-400">
      {{ t('upload.loaded') }}
      <span class="font-mono text-slate-200">{{ store.job.source_file }}</span>
      ({{ t('upload.layers', store.layers.length) }})
    </p>
  </div>
</template>
