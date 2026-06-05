// Per-layer derived state + store mutators for LayerCard (L10 #4).
//
// Wraps the ~250 LOC of script setup that used to live at the top of
// ``LayerCard.vue``: algorithm metadata, multi-pass detection,
// pen-match logic, visibility / settings updaters, print-style
// helpers, and the collapse/advanced toggles. The component template
// keeps reading these via the returned bag — no behavioural change.
//
// Takes the layer as a Ref so the composable stays usable from any
// caller that exposes a reactive ``LayerInfo``; the existing
// component passes ``computed(() => props.layer)``.

import { computed, inject, onMounted, ref, watch, type ComputedRef, type Ref } from 'vue'
import { type LayerInfo, type PausePolicy } from '../api/client'
import { formatLayerLabel } from '../lib/labels'
import { nearestPen } from '../lib/penMatching'
import { useAlgorithmsStore } from '../stores/algorithms'
import { useJobStore, type LayerPass } from '../stores/job'
import { defaultsFor, getAlgoSpec } from '../data/algorithmSchemas'
import type { PrintStyle, PrintStyleKind } from '../data/printRegistry'
import { LayerSelectionKey } from './useLayerSelection'

export function useLayerCardState(layer: Ref<LayerInfo>) {
  const store = useJobStore()

  // Bulk selection (provided by LayersSection). May be null when this
  // card is rendered outside the layers section (currently doesn't
  // happen, but the inject default keeps the file forgiving).
  const selection = inject(LayerSelectionKey, null)
  const isSelected: ComputedRef<boolean> = computed(() =>
    Boolean(selection?.isSelected(layer.value.layer_id)),
  )

  function onHeaderClick(event: MouseEvent): void {
    // Only intercept click for selection if a modifier is held — plain
    // clicks on the header would otherwise eat collapse-toggle / drag
    // affordances. Shift / Ctrl / Cmd are the canonical list-box
    // modifiers, identical to Finder / Explorer / Slack channel lists.
    if (!selection) return
    if (!event.shiftKey && !event.ctrlKey && !event.metaKey) return
    const allIds = store.layers.map((l) => l.layer_id)
    selection.handleClick(layer.value.layer_id, event, allIds)
  }

  // Algorithm catalog comes from the manifest-backed store (B.4) so
  // backend-side algorithm registrations propagate without UI patches.
  const algorithmsStore = useAlgorithmsStore()
  const algorithms = computed(() => algorithmsStore.list)
  onMounted(() => {
    if (!algorithmsStore.loaded) void algorithmsStore.refresh()
  })

  // Only bitmap-derived layers (label like ``color-XXXXXX``) can be
  // re-rendered with a different algorithm — that's what the /rerender
  // cache holds. SVG / DXF / text / document layers come straight
  // from the converter as vector groups and have nothing to re-render.
  // We also require the placement's ``rerenderable`` flag to be true:
  // a bitmap uploaded before the cache-rehydration feature shipped
  // won't have its segmentation options on disk, so /rerender would
  // silently 404 even though the layer label looks like a colour
  // cluster.
  const isBitmapLayer = computed(() => {
    if (!/^color-/.test(layer.value.layer_id)) return false
    return store.selectedPlacement?.rerenderable !== false
  })

  const currentAlgorithm = computed(
    () => store.layerAlgorithms[layer.value.layer_id]?.algorithm ?? '',
  )
  const currentAlgoOptions = computed(
    () => store.layerAlgorithms[layer.value.layer_id]?.algorithm_options ?? {},
  )
  const currentPasses = computed<LayerPass[]>(
    () => store.layerAlgorithms[layer.value.layer_id]?.passes ?? [],
  )
  const isMultiPass = computed(() => currentPasses.value.length > 0)

  function onUpdatePasses(passes: LayerPass[]): void {
    store.applyLayerPasses(layer.value.layer_id, passes)
  }

  // Promote the currently-selected single style to a one-pass stack
  // so the operator can start adding more passes without losing the
  // choice.
  function enableMultiPass(): void {
    const algo = currentAlgorithm.value || 'crosshatch'
    const opts = { ...currentAlgoOptions.value }
    store.applyLayerPasses(layer.value.layer_id, [{ algorithm: algo, algorithm_options: opts }])
  }

  const currentAlgoSpec = computed(() => getAlgoSpec(currentAlgorithm.value))

  async function onAlgorithm(event: Event): Promise<void> {
    const value = (event.target as HTMLSelectElement).value
    if (!value) {
      // "default" — drop the override so the layer rerenders with
      // the initial algorithm baked in at upload time.
      await store.clearLayerAlgorithm(layer.value.layer_id)
      return
    }
    // Seed the option payload with the schema defaults so the very
    // first ``/rerender`` call already exercises the algorithm with
    // sensible knobs.
    await store.applyLayerAlgorithm(layer.value.layer_id, value, defaultsFor(value))
  }

  async function onAlgoOption(key: string, value: unknown): Promise<void> {
    if (!currentAlgorithm.value) return
    const merged = { ...currentAlgoOptions.value, [key]: value }
    await store.applyLayerAlgorithm(layer.value.layer_id, currentAlgorithm.value, merged)
  }

  const visible = computed({
    get: () => store.isVisible(layer.value.layer_id),
    set: (value: boolean) => store.setVisibility(layer.value.layer_id, value),
  })

  const label = computed(() => formatLayerLabel(layer.value.layer_id))
  const swatchColor = computed(() => label.value.color ?? layer.value.source_color)

  const penSlotCount = computed(() => store.selectedProfile?.pen_slot_count ?? 0)

  const penSlots = computed(() => {
    const profile = store.selectedProfile
    const pens = profile?.pens ?? []
    return Array.from({ length: penSlotCount.value }, (_, i) => {
      const pen = pens.find((p) => p.index === i)
      return { index: i, name: pen?.name || `${i}`, color: pen?.color ?? '#94a3b8' }
    })
  })

  const selectedPen = computed(() =>
    layer.value.target_pen_slot === null
      ? null
      : (penSlots.value.find((p) => p.index === layer.value.target_pen_slot) ?? null),
  )

  // Nearest installed pen to this layer's source colour. Only
  // meaningful for bitmap-derived multicolour layers (mono layers
  // always plot in the single ink slot the operator picked, so a
  // pen-match warning would just be noise).
  const installedPenList = computed(() => {
    const pens = store.selectedProfile?.pens ?? []
    return pens
      .filter((p) => (p.installed ?? false) && typeof p.color === 'string')
      .map((p) => ({ index: p.index, color: p.color, installed: true }))
  })

  const penMatch = computed(() => {
    if (!isBitmapLayer.value) return null
    if (!store.isMultiColor) return null
    return nearestPen(swatchColor.value, installedPenList.value)
  })

  // True when the operator hasn't already assigned a slot manually
  // AND the nearest pen is far enough that the operator probably
  // wants to see the warning. Once they pick a slot we stop nagging
  // — the override is intentional.
  const showPenWarning = computed(() => {
    if (layer.value.target_pen_slot !== null) return false
    const m = penMatch.value
    if (!m) return false
    return m.severity === 'far' || m.severity === 'wrong' || m.severity === 'none'
  })

  function applyNearestPen(): void {
    const m = penMatch.value
    if (!m || !m.pen) return
    store.updateLayer(layer.value.layer_id, { target_pen_slot: m.pen.index })
  }

  function onPenSlot(event: Event): void {
    const value = (event.target as HTMLSelectElement).value
    store.updateLayer(layer.value.layer_id, {
      target_pen_slot: value === '' ? null : Number(value),
    })
  }

  function onSpeed(event: Event): void {
    const value = (event.target as HTMLInputElement).value
    store.updateLayer(layer.value.layer_id, {
      drawing_speed_mm_s: value === '' ? null : Number(value),
    })
  }

  function onSimplify(event: Event): void {
    store.updateLayer(layer.value.layer_id, {
      simplify_tolerance_mm: Number((event.target as HTMLInputElement).value),
    })
  }

  function onOptimize(event: Event): void {
    store.updateLayer(layer.value.layer_id, {
      optimize: (event.target as HTMLInputElement).checked,
    })
  }

  function onOpacity(event: Event): void {
    const raw = Number((event.target as HTMLInputElement).value)
    const clamped = Math.max(0, Math.min(100, Math.round(raw)))
    store.updateLayer(layer.value.layer_id, { opacity_percent: clamped })
  }

  function onColorLabel(event: Event): void {
    const raw = (event.target as HTMLInputElement).value.trim()
    store.updateLayer(layer.value.layer_id, { color_label: raw || null })
  }

  function setPause(policy: PausePolicy): void {
    store.updateLayer(layer.value.layer_id, { pause_before: policy })
  }

  const pauseChoices: Array<{ value: PausePolicy; icon: string; key: string }> = [
    { value: 'auto', icon: '⏸', key: 'layers.pauseAuto' },
    { value: 'always', icon: '✋', key: 'layers.pauseAlways' },
    { value: 'never', icon: '▶', key: 'layers.pauseNever' },
  ]

  // Print-style picker drives the algorithm + options in one click.
  // The "kind" classifies the layer for the picker's thumbnail
  // filter; we don't have a schematic detector yet so colour-derived
  // layers are treated as image-content while text layers are
  // explicit.
  const styleKind = computed<PrintStyleKind>(() => (label.value.kind === 'text' ? 'text' : 'image'))

  function onPickStyle(style: PrintStyle): void {
    store.applyLayerAlgorithm(layer.value.layer_id, style.defaultAlgorithm, {
      ...style.defaultAlgorithmOptions,
    })
  }

  function onResetStyle(): void {
    store.clearLayerAlgorithm(layer.value.layer_id)
  }

  // Toggle to expose the schema-driven advanced form behind the picker.
  const showAdvanced = ref(false)
  // Collapse the whole card body so a many-layer placement (e.g.
  // 8-colour segmentation) is scannable. The header — visibility
  // checkbox, swatch, label, path stats — stays visible so the
  // layer can still be reordered and toggled on/off while collapsed.
  const collapsed = ref(false)

  // LayersSection broadcasts an "expand all" / "collapse all" signal
  // via provide; honour it whenever it flips so the bulk toggle
  // takes effect without overriding the per-card toggle the rest of
  // the time.
  const sectionCollapseAll = inject<Ref<boolean | null>>(
    'layersCollapseAll',
    ref<boolean | null>(null),
  )
  watch(sectionCollapseAll, (value) => {
    if (value === null) return
    collapsed.value = value
  })

  function formatDuration(seconds: number): string {
    const mins = Math.floor(seconds / 60)
    const secs = Math.round(seconds % 60)
    return `${mins}m ${secs.toString().padStart(2, '0')}s`
  }

  const duration = computed(() => formatDuration(store.layerDurationSeconds(layer.value)))

  return {
    // refs the template binds against
    visible,
    showAdvanced,
    collapsed,
    algorithms,
    // computed views
    isSelected,
    isBitmapLayer,
    currentAlgorithm,
    currentAlgoOptions,
    currentPasses,
    isMultiPass,
    currentAlgoSpec,
    label,
    swatchColor,
    penSlots,
    selectedPen,
    penMatch,
    showPenWarning,
    styleKind,
    duration,
    pauseChoices,
    // event handlers
    onHeaderClick,
    onUpdatePasses,
    enableMultiPass,
    onAlgorithm,
    onAlgoOption,
    applyNearestPen,
    onPenSlot,
    onSpeed,
    onSimplify,
    onOptimize,
    onOpacity,
    onColorLabel,
    setPause,
    onPickStyle,
    onResetStyle,
  }
}
