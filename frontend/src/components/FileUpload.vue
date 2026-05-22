<script setup lang="ts">
import { ref } from 'vue'
import { useJobStore } from '../stores/job'

const store = useJobStore()
const profileName = ref('Custom CoreXY A3')
const fileInput = ref<HTMLInputElement | null>(null)

async function onFileChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    await store.upload(file, profileName.value)
  }
}

function openPicker(): void {
  fileInput.value?.click()
}
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800 p-4 space-y-3">
    <label class="block text-sm text-slate-400">
      Machine profile
      <input
        v-model="profileName"
        class="mt-1 w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-slate-100"
      />
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
      {{ store.loading ? 'Converting…' : 'Choose a file to plot' }}
    </button>

    <p v-if="store.error" class="text-sm text-red-400">{{ store.error }}</p>
    <p v-else-if="store.job" class="text-sm text-slate-400">
      Loaded <span class="font-mono text-slate-200">{{ store.job.source_file }}</span>
      ({{ store.layers.length }} layer{{ store.layers.length === 1 ? '' : 's' }})
    </p>
  </div>
</template>
