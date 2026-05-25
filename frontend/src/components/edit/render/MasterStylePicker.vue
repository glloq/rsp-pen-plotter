<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  masterStylesByMode,
  resolveMasterStyle,
  resolveMulticolorStyle,
  LEGACY_MASTER_ID_MAP,
  type PrintStyle,
  type PrintStyleMode,
} from '../../../data/printRegistry'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import StyleThumbnail from '../shared/StyleThumbnail.vue'

// Gallery of master styles (Pencil / Halftone / Stippling / Engraving
// / Contours-topo / Outline / TSP / Spiral). Renders each as a card
// with the style thumbnail + label + one-line description. The grid
// is 2 columns to match the density of the surrounding render tab;
// 3-4 columns would feel sparse for 8 entries.
//
// Selecting a style commits the registry id directly into the draft.
// LEGACY_MASTER_ID_MAP still resolves saved placements that were
// committed under the pre-merge ids (halftone / spiral / centerline)
// so historical SVGs rehydrate to the renamed registry entries.

const props = withDefaults(defineProps<{
  // Active style id — either the registry id (``pencil``,
  // ``halftone-shade``…) or a legacy mono-mode id (``halftone``…).
  modelValue: string
  // Master-style family to gallery. Defaults to ``monochrome`` so
  // existing call sites (which never passed the prop) keep showing the
  // mono masters.
  mode?: PrintStyleMode
}>(), { mode: 'monochrome' })

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const { t } = useI18n()
const draft = useBitmapDraft()

const styles = computed<PrintStyle[]>(() => masterStylesByMode(props.mode))

// Pick the right resolver for the active mode — falls back to the
// mono-family default when called from the legacy mono call sites that
// don't pass ``mode``.
function resolve(id: string | null | undefined): PrintStyle {
  return props.mode === 'multicolor'
    ? resolveMulticolorStyle(id)
    : resolveMasterStyle(id)
}

// "Custom" surfaces when the operator has touched segmentation or
// algorithm knobs (typically on the SvgTab) so the live bitmap state
// no longer matches the active preset's defaults. Without this pill
// the picker silently keeps the previously-selected tile highlighted
// even though the rendered output reflects a one-off configuration,
// which the UX audit flagged as a recurring source of confusion.
const activeStyleId = computed(() => resolve(props.modelValue).id)
const isCustomised = computed<boolean>(() => {
  const style = resolve(props.modelValue)
  const seg = style.segmentation
  const b = draft.bitmap.value
  if (!seg) return false
  if (b.segmentation_method !== seg.method) return true
  if (b.algorithm !== style.defaultAlgorithm) return true
  if (seg.method === 'luminance_bands') {
    const baseline = seg.default_num_bands ?? 4
    if (b.num_bands !== baseline) return true
  } else if (seg.method === 'thresholds') {
    const baseline = seg.default_threshold ?? 0.5
    const current = b.thresholds[0] ?? baseline
    if (b.thresholds.length !== 1 || Math.abs(current - baseline) > 1e-6) return true
  }
  return false
})

// Match either by registry id or by mapped legacy id so the active
// pill survives both old (``halftone``) and new (``halftone-shade``)
// values living in the draft. Legacy ids only exist for the mono
// family — multicolour masters are post-merge so there's no mapping
// table to consult.
function isActive(style: PrintStyle): boolean {
  if (style.id === props.modelValue) return true
  if (props.mode === 'monochrome') {
    const mapped = LEGACY_MASTER_ID_MAP[props.modelValue]
    return mapped === style.id
  }
  return false
}

function select(style: PrintStyle): void {
  // Emit the registry id; callers that still need the legacy id can
  // map back via ``LEGACY_MASTER_ID_MAP``. The draft setter
  // (``setPrintMode`` / direct write) goes through
  // ``resolveMasterStyle`` so either form is accepted.
  emit('update:modelValue', style.id)
}

// Resolve the active style for the descriptive footer at the bottom
// of the card. Falls back to the default master if the id is unknown.
const activeStyle = computed(() => resolve(props.modelValue))
</script>

<template>
  <div class="space-y-1">
    <div class="flex items-center justify-between">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">
        {{ t('render.masterStyle') }}
      </p>
      <span
        v-if="isCustomised"
        class="rounded border border-amber-700 bg-amber-950/40 px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-amber-200"
        :title="t('render.customisedHint')"
      >
        {{ t('render.customised') }}
      </span>
    </div>
    <p v-if="isCustomised" class="text-[10px] text-amber-400/80">
      {{ t('render.customisedExplain', { style: t(resolveMasterStyle(activeStyleId).labelKey) }) }}
    </p>
    <div class="grid grid-cols-2 gap-1">
      <button
        v-for="style in styles"
        :key="style.id"
        type="button"
        class="flex items-center gap-2 rounded border px-2 py-1.5 text-left transition"
        :class="isActive(style)
          ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
          : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'"
        :title="style.descriptionKey ? t(style.descriptionKey) : ''"
        @click="select(style)"
      >
        <StyleThumbnail :algorithm="style.defaultAlgorithm" size="md" />
        <span class="min-w-0 flex-1">
          <span class="block truncate text-[11px] font-medium">
            {{ t(style.labelKey) }}
          </span>
          <span
            v-if="style.descriptionKey"
            class="block truncate text-[9px] text-slate-500"
          >
            {{ t(style.descriptionKey) }}
          </span>
        </span>
      </button>
    </div>
    <p class="text-[10px] text-slate-500">
      {{ activeStyle.descriptionKey ? t(activeStyle.descriptionKey) : '' }}
    </p>
  </div>
</template>
