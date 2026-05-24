<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getFonts } from '../../../api/client'
import { useFileManager, FILE_ACCEPT } from '../../../composables/useFileManager'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { useJobStore } from '../../../stores/job'
import FileSourceCard from '../source/FileSourceCard.vue'
import TypographyCard from '../source/TypographyCard.vue'
import BlockMapCard from '../BlockMapCard.vue'

// Source tab — the file itself (drop / pick / clear), the typography
// knobs when the source is plain text, and the PDF block analysis
// card. Everything that's about "what the input IS" lives here; the
// Colors / Render / Layers tabs are about "what we render FROM it".
//
// Also hosts the file <input> + dropzone wiring so the hidden picker
// can be opened from the modal header's "Change file" action.

const { t } = useI18n()
const fm = useFileManager(t)
const draft = useBitmapDraft()
const store = useJobStore()

const fileInput = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)

// Hershey font catalogue, fetched once on first mount. Drives the
// font dropdown in TypographyCard — without this fetch the dropdown
// would render empty (the old SourceSection's onMounted did the same
// fetch alongside the algorithms one; only the algorithms half was
// preserved when SourceSection was dissolved into tabs, leaving the
// fonts dropdown silently empty until this restored it).
const fonts = ref<string[]>([])
onMounted(async () => {
  try { fonts.value = await getFonts() } catch { /* keep [] — TypographyCard handles empty list */ }
})

function openPicker(): void {
  fileInput.value?.click()
}

function onFileChange(event: Event): void {
  const target = event.target as HTMLInputElement
  fm.setFile(target.files?.[0] ?? null)
  target.value = ''
}

defineExpose({ openPicker, clearAll: fm.clearAll })
</script>

<template>
  <section class="space-y-3">
    <input
      ref="fileInput"
      type="file"
      class="hidden"
      :accept="FILE_ACCEPT"
      @change="onFileChange"
    />

    <!-- Edge case: truly empty placement. Show the dropzone so the
         operator has somewhere to drop a file. Library / persisted
         placements take a no-op branch here; ensureSelectedFile() in
         the file manager rehydrates their File handle in the
         background. -->
    <FileSourceCard
      v-if="!fm.hasSource.value"
      :selected-file="null"
      :kind="fm.kind.value"
      :has-job="Boolean(store.job)"
      v-model:drag-over="dragOver"
      @pick="openPicker"
      @clear="fm.clearAll"
      @drop="(file) => fm.setFile(file)"
    />

    <TypographyCard
      v-if="fm.hasSource.value && fm.kind.value === 'typography'"
      :typo="draft.typo.value"
      :fonts="fonts"
    />

    <BlockMapCard v-if="fm.hasSource.value && fm.kind.value === 'document'" />
  </section>
</template>
