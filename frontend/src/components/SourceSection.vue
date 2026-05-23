<script setup lang="ts">
import DOMPurify from 'dompurify'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import {
  getAlgorithms,
  getFonts,
  previewBitmap,
  type AlgorithmInfo,
  type PreviewResponse,
} from '../api/client'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'

const { t } = useI18n()
const store = useJobStore()
const ui = useUiStore()
const { presets, selectedPresetName } = storeToRefs(store)
const fileInput = ref<HTMLInputElement | null>(null)

const selectedFile = ref<File | null>(null)
const algorithms = ref<AlgorithmInfo[]>([])
const fonts = ref<string[]>([])
const showOptions = ref(false)
const dragOver = ref(false)

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
const TYPOGRAPHY_EXT = ['txt', 'md']
const DOCUMENT_EXT = ['pdf', 'svg', 'eps', 'ps', 'ai', 'docx', 'odt', 'rtf', 'html']
const ACCEPT = '.svg,.png,.jpg,.jpeg,.tiff,.webp,.heic,.pdf,.dxf,.eps,.ps,.ai,.txt,.md,.html,.docx,.odt,.rtf'

const kind = computed<'bitmap' | 'typography' | 'document' | 'none'>(() => {
  const ext = selectedFile.value?.name.split('.').pop()?.toLowerCase() ?? ''
  if (IMAGE_EXT.includes(ext)) return 'bitmap'
  if (TYPOGRAPHY_EXT.includes(ext)) return 'typography'
  if (DOCUMENT_EXT.includes(ext)) return 'document'
  return 'none'
})

const showsBitmapForm = computed(() => kind.value === 'bitmap' || kind.value === 'document')

// Local thumbnail for raster images: gives an instant preview before paying
// the round-trip + vectorization cost. ObjectURL is revoked on file change.
const previewUrl = ref<string | null>(null)
function refreshPreview(): void {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = null
  }
  if (selectedFile.value && kind.value === 'bitmap') {
    previewUrl.value = URL.createObjectURL(selectedFile.value)
  }
}
watch(selectedFile, refreshPreview)
onBeforeUnmount(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})

// Plain-text inline preview for txt / md so the user knows what they're about
// to convert. Capped at a few KB so large files don't hang the UI.
const textPreview = ref<string>('')
watch(selectedFile, async (file) => {
  textPreview.value = ''
  if (file && kind.value === 'typography') {
    try {
      const blob = file.slice(0, 4096)
      textPreview.value = await blob.text()
    } catch {
      textPreview.value = ''
    }
  }
})

const algoDescriptions: Record<string, { label: string; hint: string }> = {
  direct: { label: 'convert.algoDirect', hint: 'convert.algoDirectHint' },
  halftone: { label: 'convert.algoHalftone', hint: 'convert.algoHalftoneHint' },
  stippling: { label: 'convert.algoStippling', hint: 'convert.algoStipplingHint' },
}

// Fast preview: hit POST /preview when the user is tweaking params on an
// image, debounced + cancellable. The result is a tiny rasterised-to-vector
// SVG shown next to the original thumbnail.
const previewResult = ref<PreviewResponse | null>(null)
const previewLoading = ref(false)
const previewError = ref<string | null>(null)
let previewController: AbortController | null = null
let previewTimer: ReturnType<typeof setTimeout> | null = null

const previewSvg = computed(() => {
  if (!previewResult.value) return ''
  return DOMPurify.sanitize(previewResult.value.svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
  })
})

function schedulePreview(): void {
  if (!selectedFile.value || kind.value !== 'bitmap') return
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(runPreview, 500)
}

async function runPreview(): Promise<void> {
  if (!selectedFile.value || kind.value !== 'bitmap') return
  if (previewController) previewController.abort()
  const controller = new AbortController()
  previewController = controller
  previewLoading.value = true
  previewError.value = null
  try {
    const result = await previewBitmap(
      selectedFile.value,
      bitmap.value.algorithm,
      buildOptions(),
      controller.signal,
    )
    // Late response from a superseded request → discard.
    if (controller.signal.aborted) return
    previewResult.value = result
  } catch (err) {
    // Aborted requests come through as ``CanceledError`` from axios; the
    // signal check above also covers it, but axios may resolve the abort
    // path through the catch.
    if (controller.signal.aborted) return
    previewError.value = (err as Error).message || t('upload.failed')
  } finally {
    if (previewController === controller) {
      previewController = null
      previewLoading.value = false
    }
  }
}

// Recompute preview whenever the file or any algorithm-affecting option moves.
watch(
  [
    selectedFile,
    () => bitmap.value.algorithm,
    () => bitmap.value.num_colors,
    () => bitmap.value.drop_background,
    () => bitmap.value.background_luminance,
    () => bitmap.value.cell_size_px,
    () => bitmap.value.density,
    () => bitmap.value.dot_radius_px,
    () => bitmap.value.seed,
  ],
  () => {
    if (selectedFile.value && kind.value === 'bitmap') {
      schedulePreview()
    } else {
      previewResult.value = null
      previewError.value = null
    }
  },
)

onBeforeUnmount(() => {
  if (previewTimer) clearTimeout(previewTimer)
  if (previewController) previewController.abort()
})

onMounted(async () => {
  try {
    ;[algorithms.value, fonts.value] = await Promise.all([getAlgorithms(), getFonts()])
  } catch {
    // Options forms still work with their defaults if metadata fails to load.
  }
})

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

function onDrop(event: DragEvent): void {
  dragOver.value = false
  const file = event.dataTransfer?.files?.[0] ?? null
  if (file) selectedFile.value = file
}

function buildOptions(): Record<string, unknown> | undefined {
  if (showsBitmapForm.value) {
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
  if (store.layers.length) ui.canvasTab = 'sheet'
}

function clearAll(): void {
  selectedFile.value = null
  store.clearJob()
}

const pageCount = computed(() => Number(store.uploadMetadata.page_count ?? 0))
const currentPage = computed(() => Number(store.uploadMetadata.page ?? 0))

async function goToPage(page: number): Promise<void> {
  if (page < 0 || page >= pageCount.value || page === currentPage.value) return
  await store.changePage(page)
  if (store.layers.length) ui.canvasTab = 'sheet'
}

function openPicker(): void {
  fileInput.value?.click()
}
</script>

<template>
  <section class="space-y-2">
    <div class="flex items-baseline justify-between px-1">
      <h2 class="text-xs uppercase tracking-wider text-slate-500">{{ t('prepare.source') }}</h2>
      <button
        v-if="selectedFile || store.job"
        type="button"
        class="text-[10px] uppercase tracking-wider text-slate-500 hover:text-red-300"
        :title="t('upload.clear')"
        @click="clearAll"
      >
        ✕ {{ t('upload.clear') }}
      </button>
    </div>

    <input
      ref="fileInput"
      type="file"
      class="hidden"
      :accept="ACCEPT"
      @change="onFileChange"
    />

    <div
      class="rounded-lg border-2 border-dashed px-3 py-3 text-center transition"
      :class="dragOver ? 'border-emerald-500 bg-emerald-950/30' : 'border-slate-700 bg-slate-900/40'"
      @dragenter.prevent="dragOver = true"
      @dragover.prevent="dragOver = true"
      @dragleave.prevent="dragOver = false"
      @drop.prevent="onDrop"
    >
      <div v-if="selectedFile" class="space-y-2">
        <div v-if="previewUrl" class="grid grid-cols-2 gap-2">
          <div class="space-y-1">
            <p class="text-[10px] uppercase tracking-wider text-slate-500">{{ t('upload.original') }}</p>
            <img
              :src="previewUrl"
              :alt="selectedFile.name"
              class="mx-auto max-h-32 rounded border border-slate-700 bg-slate-800 object-contain"
            />
          </div>
          <div class="space-y-1">
            <p class="flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-500">
              <span>{{ t('upload.preview') }}</span>
              <span v-if="previewLoading" class="text-slate-400">{{ t('upload.previewing') }}</span>
              <span v-else-if="previewResult" class="text-slate-400">
                {{ previewResult.elapsed_ms }} ms{{ previewResult.cached ? ' · ' + t('upload.cached') : '' }}
              </span>
            </p>
            <div
              class="mx-auto flex h-32 items-center justify-center rounded border border-slate-700 bg-white"
            >
              <div
                v-if="previewSvg"
                class="h-full w-full p-1 [&_svg]:h-full [&_svg]:w-full"
                v-html="previewSvg"
              />
              <p v-else-if="previewError" class="px-2 text-center text-[10px] text-red-400">
                {{ previewError }}
              </p>
              <p v-else class="text-[10px] text-slate-400">
                {{ previewLoading ? t('upload.previewing') : t('upload.previewHint') }}
              </p>
            </div>
            <div v-if="previewResult?.palette.length" class="flex flex-wrap gap-1">
              <span
                v-for="entry in previewResult.palette"
                :key="entry.color"
                class="inline-block h-3 w-3 rounded border border-slate-700"
                :style="{ backgroundColor: entry.color }"
                :title="entry.color"
              />
            </div>
          </div>
        </div>
        <pre
          v-else-if="kind === 'typography' && textPreview"
          class="max-h-24 overflow-hidden rounded border border-slate-700 bg-slate-900 px-2 py-1 text-left text-[10px] leading-snug text-slate-300 whitespace-pre-wrap"
          >{{ textPreview }}</pre>
        <p class="truncate text-sm font-medium text-slate-100" :title="selectedFile.name">
          {{ selectedFile.name }}
        </p>
        <p class="text-[10px] text-slate-500">
          {{ (selectedFile.size / 1024).toFixed(1) }} KB · {{ kind }}
        </p>
        <button
          type="button"
          class="rounded bg-slate-700 px-3 py-1 text-xs text-slate-100 hover:bg-slate-600"
          @click="openPicker"
        >
          {{ t('upload.changeFile') }}
        </button>
      </div>
      <div v-else>
        <p class="text-sm text-slate-400">{{ t('upload.dropHere') }}</p>
        <button
          type="button"
          class="mt-2 rounded bg-slate-700 px-3 py-1 text-xs text-slate-100 hover:bg-slate-600"
          @click="openPicker"
        >
          {{ t('upload.pick') }}
        </button>
      </div>
    </div>

    <div v-if="selectedFile && kind !== 'none'" class="rounded-lg border border-slate-700 bg-slate-800">
      <button
        type="button"
        class="flex w-full items-center justify-between px-3 py-2 text-xs uppercase tracking-wide text-slate-400 hover:text-slate-200"
        :aria-expanded="showOptions"
        @click="showOptions = !showOptions"
      >
        {{ kind === 'document' ? t('convert.embeddedImageOptions') : t('convert.options') }}
        <span class="text-slate-500">{{ showOptions ? '−' : '+' }}</span>
      </button>

      <div v-if="showOptions" class="space-y-2 border-t border-slate-700 p-3 text-xs">
        <p v-if="kind === 'document'" class="rounded border border-slate-700 bg-slate-900/50 px-2 py-1 text-[11px] leading-snug text-slate-400">
          {{ t('convert.embeddedImageHint') }}
        </p>

        <template v-if="showsBitmapForm">
          <div class="space-y-1">
            <p class="text-slate-400">{{ t('convert.algorithm') }}</p>
            <div class="grid grid-cols-3 gap-1">
              <button
                v-for="algo in algorithms"
                :key="algo.name"
                type="button"
                class="rounded border px-2 py-1.5 text-left text-[11px] transition"
                :class="bitmap.algorithm === algo.name
                  ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
                  : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'"
                :title="t(algoDescriptions[algo.name]?.hint ?? '') || algo.description"
                @click="bitmap.algorithm = algo.name"
              >
                <span class="block font-medium">{{ t(algoDescriptions[algo.name]?.label ?? '') || algo.name }}</span>
                <span class="block text-[9px] text-slate-500">{{ t(algoDescriptions[algo.name]?.hint ?? '') || algo.description }}</span>
              </button>
            </div>
          </div>
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
      class="w-full rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
      :disabled="store.loading"
      @click="uploadSelected"
    >
      {{ store.loading ? t('upload.converting') : t('upload.choose') }}
    </button>

    <div
      v-if="pageCount > 1"
      class="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs"
    >
      <button
        type="button"
        class="rounded bg-slate-700 px-2 py-1 text-slate-100 hover:bg-slate-600 disabled:opacity-40"
        :disabled="currentPage <= 0 || store.loading"
        :aria-label="t('upload.prevPage')"
        @click="goToPage(currentPage - 1)"
      >
        ←
      </button>
      <span class="text-slate-300">
        {{ t('upload.pageOf', { current: currentPage + 1, total: pageCount }) }}
      </span>
      <button
        type="button"
        class="rounded bg-slate-700 px-2 py-1 text-slate-100 hover:bg-slate-600 disabled:opacity-40"
        :disabled="currentPage >= pageCount - 1 || store.loading"
        :aria-label="t('upload.nextPage')"
        @click="goToPage(currentPage + 1)"
      >
        →
      </button>
    </div>

    <p v-if="store.error && store.errorScope === 'upload'" class="rounded border border-red-700 bg-red-950/40 px-2 py-1 text-xs text-red-300">
      {{ store.error }}
    </p>
    <p v-else-if="store.job" class="px-1 text-xs text-slate-500">
      {{ t('upload.loaded') }}
      <span class="font-mono text-slate-300">{{ store.job.source_file }}</span>
      ({{ t('upload.layers', store.layers.length) }})
    </p>

    <ul
      v-if="store.uploadWarnings.length"
      class="rounded border border-amber-700 bg-amber-950/40 px-2 py-1.5 text-xs text-amber-200 space-y-0.5"
    >
      <li v-for="(warning, i) in store.uploadWarnings" :key="i">⚠ {{ warning }}</li>
    </ul>
  </section>
</template>
