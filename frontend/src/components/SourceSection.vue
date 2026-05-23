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
  type SegmentationMethod,
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
const showSegmentation = ref(false)
const showRender = ref(false)
const dragOver = ref(false)

// Editable state for bitmap conversion. Grouped by concern so the
// template can show only the section the chosen segmentation method or
// algorithm needs.
const bitmap = ref({
  // -- Segmentation ("decoupage") --
  segmentation_method: 'kmeans' as SegmentationMethod,
  num_colors: 4,              // kmeans
  num_bands: 4,               // luminance_bands
  thresholds: [0.33, 0.66] as number[], // thresholds
  palette: ['#000000', '#ff0000', '#0000ff'] as string[], // fixed_palette
  // -- Post-processing --
  min_region_pixels: 0,
  merge_delta_e: 0,
  // -- Common input options --
  max_dimension_px: 800,
  drop_background: true,
  background_luminance: 0.92,
  // -- Render algorithm --
  algorithm: 'direct',
  // halftone
  cell_size_px: 6,
  // stippling + tsp
  density: 0.02,
  dot_radius_px: 0.6,
  seed: 0,
  // crosshatch
  crosshatch_angle_deg: 45,
  crosshatch_spacing_px: 4,
  crosshatch_crossed: false,
  // contours
  contours_spacing_px: 4,
  contours_max_rings: 20,
  // edges
  edges_stroke_width: 0.8,
  // spiral
  spiral_spacing_px: 4,
  spiral_samples_per_turn: 64,
  // scanlines
  scanlines_spacing_px: 4,
  scanlines_wave_amp_px: 0,
  scanlines_wave_period_px: 12,
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

// Local thumbnail for raster images: instant preview before paying the
// round-trip + vectorisation cost. ObjectURL is revoked on file change.
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

// (The per-algorithm card grid + ``algorithmsByKind`` helper that used to
//  live here moved into LayerCard when render became a per-layer choice.)

// Live preview: debounced /preview round-trip on parameter changes.
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
    if (controller.signal.aborted) return
    previewResult.value = result
  } catch (err) {
    if (controller.signal.aborted) return
    previewError.value = (err as Error).message || t('upload.failed')
  } finally {
    if (previewController === controller) {
      previewController = null
      previewLoading.value = false
    }
  }
}

watch(
  [
    selectedFile,
    () => bitmap.value.algorithm,
    () => bitmap.value.segmentation_method,
    () => bitmap.value.num_colors,
    () => bitmap.value.num_bands,
    () => bitmap.value.thresholds,
    () => bitmap.value.palette,
    () => bitmap.value.drop_background,
    () => bitmap.value.background_luminance,
    () => bitmap.value.min_region_pixels,
    () => bitmap.value.merge_delta_e,
    () => bitmap.value.cell_size_px,
    () => bitmap.value.density,
    () => bitmap.value.dot_radius_px,
    () => bitmap.value.seed,
    () => bitmap.value.crosshatch_angle_deg,
    () => bitmap.value.crosshatch_spacing_px,
    () => bitmap.value.crosshatch_crossed,
    () => bitmap.value.contours_spacing_px,
    () => bitmap.value.contours_max_rings,
    () => bitmap.value.edges_stroke_width,
    () => bitmap.value.spiral_spacing_px,
    () => bitmap.value.spiral_samples_per_turn,
    () => bitmap.value.scanlines_spacing_px,
    () => bitmap.value.scanlines_wave_amp_px,
    () => bitmap.value.scanlines_wave_period_px,
  ],
  () => {
    if (selectedFile.value && kind.value === 'bitmap') {
      schedulePreview()
    } else {
      previewResult.value = null
      previewError.value = null
    }
  },
  { deep: true },
)

onBeforeUnmount(() => {
  if (previewTimer) clearTimeout(previewTimer)
  if (previewController) previewController.abort()
})

onMounted(async () => {
  try {
    ;[algorithms.value, fonts.value] = await Promise.all([getAlgorithms(), getFonts()])
  } catch {
    // Defaults still work if metadata fetch fails.
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

function buildSegmentationOptions(): Record<string, unknown> {
  const b = bitmap.value
  if (b.segmentation_method === 'luminance_bands') return { num_bands: b.num_bands }
  if (b.segmentation_method === 'thresholds') return { levels: b.thresholds }
  if (b.segmentation_method === 'fixed_palette') return { palette: b.palette }
  return {}
}

function buildAlgorithmOptions(): Record<string, unknown> {
  const b = bitmap.value
  switch (b.algorithm) {
    case 'halftone':
      return { cell_size_px: b.cell_size_px }
    case 'stippling':
      return { density: b.density, dot_radius_px: b.dot_radius_px, seed: b.seed }
    case 'crosshatch':
      return {
        angle_deg: b.crosshatch_angle_deg,
        spacing_px: b.crosshatch_spacing_px,
        crossed: b.crosshatch_crossed,
      }
    case 'contours':
      return { spacing_px: b.contours_spacing_px, max_rings: b.contours_max_rings }
    case 'edges':
      return { stroke_width: b.edges_stroke_width }
    case 'spiral':
      return { spacing_px: b.spiral_spacing_px, samples_per_turn: b.spiral_samples_per_turn }
    case 'scanlines':
      return {
        spacing_px: b.scanlines_spacing_px,
        wave_amp_px: b.scanlines_wave_amp_px,
        wave_period_px: b.scanlines_wave_period_px,
      }
    case 'tsp':
      return { density: b.density, seed: b.seed }
    default:
      return {}
  }
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
      segmentation_method: b.segmentation_method,
      segmentation_options: buildSegmentationOptions(),
      min_region_pixels: b.min_region_pixels,
      merge_delta_e: b.merge_delta_e,
      algorithm_options: buildAlgorithmOptions(),
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

// Threshold / palette editing helpers — the bitmap state's lists need
// add/remove + per-cell editing.
function addThreshold(): void {
  bitmap.value.thresholds = [...bitmap.value.thresholds, 0.5].sort((a, b) => a - b)
}
function removeThreshold(i: number): void {
  bitmap.value.thresholds = bitmap.value.thresholds.filter((_, idx) => idx !== i)
}
function updateThreshold(i: number, value: number): void {
  const clamped = Math.max(0, Math.min(1, value))
  const next = [...bitmap.value.thresholds]
  next[i] = clamped
  bitmap.value.thresholds = next.sort((a, b) => a - b)
}
function addPaletteColour(): void {
  bitmap.value.palette = [...bitmap.value.palette, '#888888']
}
function removePaletteColour(i: number): void {
  bitmap.value.palette = bitmap.value.palette.filter((_, idx) => idx !== i)
}
function updatePaletteColour(i: number, value: string): void {
  const next = [...bitmap.value.palette]
  next[i] = value
  bitmap.value.palette = next
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

    <!-- ============================== SEGMENTATION ============================== -->
    <div v-if="selectedFile && showsBitmapForm" class="rounded-lg border border-slate-700 bg-slate-800">
      <button
        type="button"
        class="flex w-full items-center justify-between px-3 py-2 text-xs uppercase tracking-wide text-slate-400 hover:text-slate-200"
        :aria-expanded="showSegmentation"
        @click="showSegmentation = !showSegmentation"
      >
        {{ t('convert.segmentation') }}
        <span class="text-slate-500">{{ showSegmentation ? '−' : '+' }}</span>
      </button>
      <div v-if="showSegmentation" class="space-y-2 border-t border-slate-700 p-3 text-xs">
        <p v-if="kind === 'document'" class="rounded border border-slate-700 bg-slate-900/50 px-2 py-1 text-[11px] leading-snug text-slate-400">
          {{ t('convert.embeddedImageHint') }}
        </p>

        <!-- Method picker -->
        <div class="space-y-1">
          <p class="text-slate-400">{{ t('convert.segmentationMethod') }}</p>
          <div class="grid grid-cols-2 gap-1">
            <button
              v-for="method in (['kmeans', 'luminance_bands', 'thresholds', 'fixed_palette'] as SegmentationMethod[])"
              :key="method"
              type="button"
              class="rounded border px-2 py-1.5 text-left text-[11px] transition"
              :class="bitmap.segmentation_method === method
                ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
                : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'"
              :title="t(`convert.seg_${method}_hint`)"
              @click="bitmap.segmentation_method = method"
            >
              <span class="block font-medium">{{ t(`convert.seg_${method}`) }}</span>
              <span class="block text-[9px] text-slate-500">{{ t(`convert.seg_${method}_hint`) }}</span>
            </button>
          </div>
        </div>

        <!-- Method-specific params -->
        <label v-if="bitmap.segmentation_method === 'kmeans'" class="block text-slate-400">
          {{ t('convert.numColors') }}
          <input v-model.number="bitmap.num_colors" type="number" min="1" max="32" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
        </label>

        <label v-else-if="bitmap.segmentation_method === 'luminance_bands'" class="block text-slate-400">
          {{ t('convert.numBands') }}
          <input v-model.number="bitmap.num_bands" type="number" min="2" max="16" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
        </label>

        <div v-else-if="bitmap.segmentation_method === 'thresholds'" class="space-y-1">
          <div class="flex items-center justify-between">
            <span class="text-slate-400">{{ t('convert.thresholds') }}</span>
            <button
              type="button"
              class="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-300 hover:border-slate-600"
              @click="addThreshold"
            >
              + {{ t('convert.addThreshold') }}
            </button>
          </div>
          <div v-for="(value, i) in bitmap.thresholds" :key="i" class="flex items-center gap-1">
            <input
              type="number"
              min="0"
              max="1"
              step="0.01"
              :value="value"
              class="flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              @change="(e) => updateThreshold(i, Number((e.target as HTMLInputElement).value))"
            />
            <button
              type="button"
              class="rounded bg-slate-700 px-2 py-1 text-[10px] text-slate-300 hover:bg-slate-600"
              @click="removeThreshold(i)"
            >
              ✕
            </button>
          </div>
          <p class="text-[10px] text-slate-500">{{ t('convert.thresholdsHint') }}</p>
        </div>

        <div v-else-if="bitmap.segmentation_method === 'fixed_palette'" class="space-y-1">
          <div class="flex items-center justify-between">
            <span class="text-slate-400">{{ t('convert.palette') }}</span>
            <button
              type="button"
              class="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-300 hover:border-slate-600"
              @click="addPaletteColour"
            >
              + {{ t('convert.addColour') }}
            </button>
          </div>
          <div v-for="(hex, i) in bitmap.palette" :key="i" class="flex items-center gap-1">
            <input
              type="color"
              :value="hex"
              class="h-7 w-12 cursor-pointer rounded border border-slate-700 bg-slate-900"
              @input="(e) => updatePaletteColour(i, (e.target as HTMLInputElement).value)"
            />
            <input
              type="text"
              :value="hex"
              class="flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100"
              @change="(e) => updatePaletteColour(i, (e.target as HTMLInputElement).value)"
            />
            <button
              type="button"
              class="rounded bg-slate-700 px-2 py-1 text-[10px] text-slate-300 hover:bg-slate-600"
              @click="removePaletteColour(i)"
            >
              ✕
            </button>
          </div>
        </div>

        <!-- Post-processing -->
        <div class="border-t border-slate-700 pt-2 space-y-2">
          <p class="text-[10px] uppercase tracking-wider text-slate-500">{{ t('convert.postProcess') }}</p>
          <div class="grid grid-cols-2 gap-2">
            <label class="block text-slate-400">
              {{ t('convert.minRegion') }}
              <input v-model.number="bitmap.min_region_pixels" type="number" min="0" max="1000" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            </label>
            <label class="block text-slate-400">
              {{ t('convert.mergeDeltaE') }}
              <input v-model.number="bitmap.merge_delta_e" type="number" min="0" max="50" step="0.5" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            </label>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <label class="flex items-center gap-2 self-end text-slate-400">
              <input v-model="bitmap.drop_background" type="checkbox" class="rounded border-slate-600 bg-slate-900" />
              {{ t('convert.dropBackground') }}
            </label>
            <label class="block text-slate-400">{{ t('convert.bgLuminance') }}
              <input v-model.number="bitmap.background_luminance" type="number" min="0" max="1" step="0.01" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
            </label>
          </div>
          <label class="block text-slate-400">{{ t('convert.maxDim') }}
            <input v-model.number="bitmap.max_dimension_px" type="number" min="16" max="4096" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
        </div>
      </div>
    </div>

    <!-- Render algorithm has moved into each LayerCard — operators pick a
         style per colour layer in the "Layers" panel rather than choosing
         one algorithm for the whole image here. -->

    <!-- ============================ TYPOGRAPHY (unchanged) ========================== -->
    <div v-if="selectedFile && kind === 'typography'" class="rounded-lg border border-slate-700 bg-slate-800">
      <button
        type="button"
        class="flex w-full items-center justify-between px-3 py-2 text-xs uppercase tracking-wide text-slate-400 hover:text-slate-200"
        :aria-expanded="showRender"
        @click="showRender = !showRender"
      >
        {{ t('convert.options') }}
        <span class="text-slate-500">{{ showRender ? '−' : '+' }}</span>
      </button>
      <div v-if="showRender" class="space-y-2 border-t border-slate-700 p-3 text-xs">
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
