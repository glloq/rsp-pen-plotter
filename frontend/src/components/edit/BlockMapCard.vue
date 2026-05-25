<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { analyzeDocument, type DocumentAnalysis } from '../../api/client'
import { useEditState } from '../../composables/useEditState'

const { t } = useI18n()
const edit = useEditState()

// We only run analysis for PDF uploads — other documents (DOCX, EPS, …)
// don't have a block model we can extract. The card stays hidden until
// the backend returns at least one block.
const isPdf = computed(() => {
  const file = edit.selectedFile.value
  if (!file) return false
  return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
})

const analysis = ref<DocumentAnalysis | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
// Track the in-flight request so a fast file switch cancels the
// pending analysis — otherwise PDF A's response can land after PDF B's
// and overwrite the displayed blocks.
let analyzeController: AbortController | null = null

// Auto-run analysis when the selected file changes to a PDF.
watch(
  () => edit.selectedFile.value,
  async (file) => {
    if (analyzeController) analyzeController.abort()
    analysis.value = null
    error.value = null
    if (!file || !isPdf.value) return
    const controller = new AbortController()
    analyzeController = controller
    loading.value = true
    try {
      const result = await analyzeDocument(file, controller.signal)
      if (controller.signal.aborted) return
      analysis.value = result
    } catch (err) {
      if (controller.signal.aborted) return
      error.value = (err as Error).message || t('blockMap.failed')
    } finally {
      if (analyzeController === controller) {
        analyzeController = null
        loading.value = false
      }
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (analyzeController) analyzeController.abort()
})

// Single-page view: PDF uploads land on one page at a time via the
// existing pageCount / currentPage navigation, so we only show the
// blocks for the currently visible page.
const currentBlocks = computed(() => {
  if (!analysis.value) return []
  const idx = edit.currentPage.value
  const page = analysis.value.pages.find((p) => p.page_index === idx)
  return page?.blocks ?? []
})

const textCount = computed(() => currentBlocks.value.filter((b) => b.kind === 'text').length)
const imageCount = computed(() => currentBlocks.value.filter((b) => b.kind === 'image').length)
</script>

<template>
  <section
    v-if="isPdf && (loading || analysis || error)"
    class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-2"
  >
    <div class="flex items-baseline justify-between">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">
        {{ t('blockMap.title') }}
      </p>
      <span v-if="loading" class="text-[10px] text-slate-500">{{ t('blockMap.loading') }}</span>
      <span v-else-if="analysis" class="text-[10px] text-slate-500">
        {{ t('blockMap.summary', { text: textCount, image: imageCount }) }}
      </span>
    </div>

    <p
      v-if="error"
      class="rounded border border-red-700 bg-red-950/40 px-2 py-1 text-[11px] text-red-300"
    >
      {{ error }}
    </p>

    <ul v-else-if="!loading && currentBlocks.length" class="space-y-1">
      <li
        v-for="block in currentBlocks"
        :key="block.id"
        class="flex items-center gap-2 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs"
      >
        <span
          class="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded border border-slate-600 text-[10px]"
          :class="block.kind === 'text' ? 'bg-slate-800 font-serif text-slate-300' : 'bg-slate-800'"
          aria-hidden="true"
          >{{ block.kind === 'text' ? 'Aa' : '🖼' }}</span
        >
        <div class="min-w-0 flex-1">
          <p class="truncate text-slate-200">
            <span v-if="block.text_sample">{{ block.text_sample }}</span>
            <span v-else class="text-slate-500">{{ t('blockMap.imageBlock') }}</span>
          </p>
          <p class="font-mono text-[10px] text-slate-500">
            {{ block.bbox[0].toFixed(0) }}, {{ block.bbox[1].toFixed(0) }} →
            {{ block.bbox[2].toFixed(0) }}, {{ block.bbox[3].toFixed(0) }} mm
            <template v-if="block.char_count">
              · {{ block.char_count }} {{ t('blockMap.chars') }}</template
            >
          </p>
        </div>
      </li>
    </ul>

    <p v-else-if="!loading && analysis && !currentBlocks.length" class="text-[11px] text-slate-500">
      {{ t('blockMap.empty') }}
    </p>

    <p class="text-[10px] text-slate-500">{{ t('blockMap.hint') }}</p>
  </section>
</template>
