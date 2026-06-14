<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getFonts } from '../../../api/client'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { useFileManager } from '../../../composables/useFileManager'
import BlockMapCard from '../BlockMapCard.vue'
import TabEmptyState from '../shared/TabEmptyState.vue'
import TypographyCard from '../source/TypographyCard.vue'

// Text tab — dedicated home for every text-related control. For
// pure typography sources (.txt / .md) it carries the full layout
// form (font, size, alignment, page, margins). For mixed
// text + image documents (PDF / DOCX / HTML) it surfaces the
// Hershey re-render toggle, the font/stroke knobs and the
// BlockMapCard that lets the operator pick which text/image
// blocks survive the conversion. Bitmap-only sources hide this
// tab entirely (see EditTabs.vue).

const { t } = useI18n()
const draft = useBitmapDraft()
const fm = useFileManager(t)

const fonts = ref<string[]>([])
onMounted(async () => {
  try {
    fonts.value = await getFonts()
  } catch {
    /* keep [] */
  }
})
</script>

<template>
  <section v-if="fm.kind.value === 'typography'" class="space-y-3">
    <TypographyCard :typo="draft.typo.value" :fonts="fonts" mode="typography" />
  </section>

  <section v-else-if="fm.kind.value === 'document'" class="space-y-3">
    <TypographyCard :typo="draft.typo.value" :fonts="fonts" mode="document" />
    <BlockMapCard />
  </section>

  <TabEmptyState v-else :message="t('text.notApplicable')" />
</template>
