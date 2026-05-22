<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { getAlgorithms, getFonts, type AlgorithmInfo } from '../api/client'
import { useJobStore } from '../stores/job'

const { t } = useI18n()
const store = useJobStore()
const { profiles, selectedProfileName, presets, selectedPresetName } = storeToRefs(store)
const fileInput = ref<HTMLInputElement | null>(null)

const selectedFile = ref<File | null>(null)
const algorithms = ref<AlgorithmInfo[]>([])
const fonts = ref<string[]>([])
const showOptions = ref(false)

const bitmap = ref({
  algorithm: 'direct',
  num_colors: 4,
  max_dimension_px: 800,
  drop_background: true,
  background_luminance: 0.92,
  cell_size_px: 6,
  density: 0.02,
  dot_radius_px: 0.6,
  seed: 0,
})
const typo = ref({
  font: 'futural',
  font_size_mm: 4.0,
  line_spacing: 1.5,
  alignment: 'left' as 'left' | 'center' | 'right',
  stroke_width_mm: 0.3,
  margin_mm: 15.0,
  page_width_mm: 210.0,
  page_height_mm: 297.0,
})

const IMAGE_EXT = ['png', 'jpg', 'jpeg', 'tiff', 'webp', 'heic']
const TEXT_EXT = ['txt', 'md', 'html', 'docx', 'odt', 'rtf']

const kind = computed<'bitmap' | 'typography' | 'none'>(() => {
  const ext = selectedFile.value?.name.split('.').pop()?.toLowerCase() ?? ''
  if (IMAGE_EXT.includes(ext)) return 'bitmap'
  if (TEXT_EXT.includes(ext)) return 'typography'
  return 'none'
})

onMounted(async () => {
  try {
    ;[algorithms.value, fonts.value] = await Promise.all([getAlgorithms(), getFonts()])
  } catch {
    // Options forms still work with their defaults if metadata fails to load.
  }
})

// When a bitmap preset is chosen, prefill the bitmap form from its options.
watch(selectedPresetName, (name) => {
  const preset = presets.value.find((p) => p.name === name)
  if (!preset) return
  const opts = preset.options as Record<string, unknown>
  const target = bitmap.value as Record<string, unknown>
  for (const key of Object.keys(target)) {
    if (key in opts) target[key] = opts[key]
  }
  const algoOpts = (opts.algorithm_options as Record<string, unknown>) ?? {}
  for (const key of ['cell_size_px', 'density', 'dot_radius_px', 'seed']) {
    if (key in algoOpts) target[key] = algoOpts[key]
  }
})

function onFileChange(event: Event): void {
  const target = event.target as HTMLInputElement
  selectedFile.value = target.files?.[0] ?? null
  target.value = ''
}

function buildOptions(): Record<string, unknown> | undefined {
  if (kind.value === 'bitmap') {
    const b = bitmap.value
    return {
      algorithm: b.algorithm,
      num_colors: b.num_colors,
      max_dimension_px: b.max_dimension_px,
      drop_background: b.drop_background,
      background_luminance: b.background_luminance,
      algorithm_options:
        b.algorithm === 'halftone'
          ? { cell_size_px: b.cell_size_px }
          : b.algorithm === 'stippling'
            ? { density: b.density, dot_radius_px: b.dot_radius_px, seed: b.seed }
            : {},
    }
  }
  if (kind.value === 'typography') {
    return { ...typo.value }
  }
  return undefined
}

async function uploadSelected(): Promise<void> {
  if (!selectedFile.value) return
  await store.upload(selectedFile.value, buildOptions())
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
      class="w-full rounded bg-slate-700 hover:bg-slate-600 px-4 py-2 font-medium text-slate-100"
      @click="openPicker"
    >
      {{ selectedFile ? selectedFile.name : t('upload.pick') }}
    </button>

    <div v-if="selectedFile && kind !== 'none'" class="rounded border border-slate-700">
      <button
        type="button"
        class="flex w-full items-center justify-between px-3 py-2 text-xs uppercase tracking-wide text-slate-400"
        @click="showOptions = !showOptions"
      >
        {{ t('convert.options') }}
        <span class="text-slate-500">{{ showOptions ? '−' : '+' }}</span>
      </button>

      <div v-if="showOptions" class="space-y-2 border-t border-slate-700 p-3 text-xs">
        <template v-if="kind === 'bitmap'">
          <label class="block text-slate-400">{{ t('convert.algorithm') }}
            <select v-model="bitmap.algorithm" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100">
              <option v-for="algo in algorithms" :key="algo.name" :value="algo.name">{{ algo.name }}</option>
            </select>
          </label>
          <div class="grid grid-cols-2 gap-2">
            <label class="block text-slate-400">{{ t('convert.numColors') }}
              <input v-model.number="bitmap.num_colors" type="number" min="1" max="32" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            </label>
            <label class="block text-slate-400">{{ t('convert.maxDim') }}
              <input v-model.number="bitmap.max_dimension_px" type="number" min="16" max="4096" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            </label>
            <label class="flex items-center gap-2 self-end text-slate-400">
              <input v-model="bitmap.drop_background" type="checkbox" class="rounded border-slate-600 bg-slate-900" />
              {{ t('convert.dropBackground') }}
            </label>
            <label class="block text-slate-400">{{ t('convert.bgLuminance') }}
              <input v-model.number="bitmap.background_luminance" type="number" min="0" max="1" step="0.01" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            </label>
          </div>
          <label v-if="bitmap.algorithm === 'halftone'" class="block text-slate-400">{{ t('convert.cellSize') }}
            <input v-model.number="bitmap.cell_size_px" type="number" min="2" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
          <div v-if="bitmap.algorithm === 'stippling'" class="grid grid-cols-3 gap-2">
            <label class="block text-slate-400">{{ t('convert.density') }}
              <input v-model.number="bitmap.density" type="number" step="0.001" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            </label>
            <label class="block text-slate-400">{{ t('convert.dotRadius') }}
              <input v-model.number="bitmap.dot_radius_px" type="number" step="0.1" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            </label>
            <label class="block text-slate-400">{{ t('convert.seed') }}
              <input v-model.number="bitmap.seed" type="number" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            </label>
          </div>
        </template>

        <template v-else-if="kind === 'typography'">
          <div class="grid grid-cols-2 gap-2">
            <label class="block text-slate-400">{{ t('convert.font') }}
              <select v-model="typo.font" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100">
                <option v-for="font in fonts" :key="font" :value="font">{{ font }}</option>
              </select>
            </label>
            <label class="block text-slate-400">{{ t('convert.alignment') }}
              <select v-model="typo.alignment" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100">
                <option value="left">left</option>
                <option value="center">center</option>
                <option value="right">right</option>
              </select>
            </label>
            <label class="block text-slate-400">{{ t('convert.fontSize') }}
              <input v-model.number="typo.font_size_mm" type="number" step="0.5" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            </label>
            <label class="block text-slate-400">{{ t('convert.lineSpacing') }}
              <input v-model.number="typo.line_spacing" type="number" step="0.1" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            </label>
            <label class="block text-slate-400">{{ t('convert.strokeWidth') }}
              <input v-model.number="typo.stroke_width_mm" type="number" step="0.1" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            </label>
            <label class="block text-slate-400">{{ t('convert.margin') }}
              <input v-model.number="typo.margin_mm" type="number" step="any" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            </label>
            <label class="block text-slate-400">{{ t('convert.pageWidth') }}
              <input v-model.number="typo.page_width_mm" type="number" step="any" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            </label>
            <label class="block text-slate-400">{{ t('convert.pageHeight') }}
              <input v-model.number="typo.page_height_mm" type="number" step="any" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            </label>
          </div>
        </template>
      </div>
    </div>

    <button
      v-if="selectedFile"
      type="button"
      class="w-full rounded bg-emerald-600 hover:bg-emerald-500 px-4 py-2 font-medium text-white disabled:opacity-50"
      :disabled="store.loading"
      @click="uploadSelected"
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
