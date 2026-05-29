// Singleton owner of the edit modal's file lifecycle:
//
//   - the in-memory File handle (selectedFile)
//   - the derived ``kind`` (bitmap / typography / document / none)
//   - the inline bitmap thumbnail + plain-text preview
//   - the /preview scheduler (debounce + abort + retry)
//   - the /upload action with the multi-pass reupload guard + the
//     post-upload mono style propagation
//
// Hoisted out of SourceSection.vue so the SourceTab / ColorsTab /
// RenderTab / LayersTab can all consume the same draft + same upload
// action without prop-drilling through EditModal. The modal mounts at
// most one instance at a time so a module-level singleton is simpler
// than provide/inject across tab siblings.

import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { downloadOriginalFile } from '../api/client'
import { confirmAction } from './confirm'
import { useEditState } from './useEditState'
import { useBitmapDraft } from './useBitmapDraft'
import { usePreviewScheduler } from './usePreviewScheduler'
import { usePreviewCostEstimator } from './usePreviewCostEstimator'
import { applyMasterStyleToLayers } from './useStylePropagation'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'

const IMAGE_EXT = ['png', 'jpg', 'jpeg', 'tiff', 'webp', 'heic']
const TYPOGRAPHY_EXT = ['txt', 'md']
const DOCUMENT_EXT = ['pdf', 'svg', 'eps', 'ps', 'ai', 'docx', 'odt', 'rtf', 'html', 'dxf']
export const FILE_ACCEPT =
  '.svg,.png,.jpg,.jpeg,.tiff,.webp,.heic,.pdf,.dxf,.eps,.ps,.ai,.txt,.md,.html,.docx,.odt,.rtf'

export type FileKind = 'bitmap' | 'typography' | 'document' | 'none'

// ---- Singleton state ----
const _selectedFile = ref<File | null>(null)
const _previewUrl = ref<string | null>(null)
const _textPreview = ref<string>('')
const _initialised = ref(false)
let _disposers: Array<() => void> = []

// Tagged shape for the optional i18n translator. Mirrors vue-i18n's
// ``t`` overloads enough for our two callsites (no-arg and
// args-object) without pulling vue-i18n's type tree into this file.
export type Translator = (key: string, args?: Record<string, unknown>) => string

// ---- Public composable ----
export function useFileManager(t?: Translator) {
  const store = useJobStore()
  const ui = useUiStore()
  const draft = useBitmapDraft()
  const edit = useEditState()
  const costEstimator = usePreviewCostEstimator()

  const sourceName = computed<string>(
    () => _selectedFile.value?.name ?? store.selectedPlacement?.source_file ?? '',
  )

  const kind = computed<FileKind>(() => {
    const ext = sourceName.value.split('.').pop()?.toLowerCase() ?? ''
    if (IMAGE_EXT.includes(ext)) return 'bitmap'
    if (TYPOGRAPHY_EXT.includes(ext)) return 'typography'
    if (DOCUMENT_EXT.includes(ext)) return 'document'
    return 'none'
  })

  const showsBitmapForm = computed(() => kind.value === 'bitmap' || kind.value === 'document')

  const hasSource = computed<boolean>(() =>
    Boolean(_selectedFile.value || store.selectedPlacement?.source_file),
  )

  function buildOptions(): Record<string, unknown> | undefined {
    let opts: Record<string, unknown> | undefined
    if (showsBitmapForm.value) opts = draft.buildBitmapOptions()
    else if (kind.value === 'typography') opts = draft.buildTypographyOptions()
    else return undefined
    // Multi-page sources (PDF, DOCX): preserve the page currently shown
    // in the preview when re-uploading. Without this the Apply button
    // re-runs the conversion against the default (first) page and the
    // operator has to navigate back from page 1 every single time they
    // tweak a setting.
    if (opts) {
      const placement = store.selectedPlacement
      const pageCount = Number(placement?.upload_metadata?.page_count ?? 0)
      const currentPage = Number(placement?.upload_metadata?.page ?? 0)
      if (pageCount > 1 && currentPage > 0) {
        opts.page = currentPage
      }
    }
    return opts
  }

  // ---- Preview scheduler ----
  const previewer = usePreviewScheduler({
    fileGetter: () => _selectedFile.value,
    algorithmGetter: () => draft.bitmap.value.algorithm,
    optionsBuilder: () => buildOptions(),
    // Typography sources (.txt / .md) now get a live Hershey preview
    // too, served by ``/preview-text``. Document sources still fall
    // through to ``/upload`` (the bitmap-form preview only makes sense
    // when there's a raster to segment).
    shouldRun: () => kind.value === 'bitmap' || kind.value === 'typography',
    modeGetter: () => (kind.value === 'typography' ? 'text' : 'bitmap'),
    qualityGetter: () => edit.previewQuality.value,
    failedMessage: t?.('upload.failed') ?? 'preview failed',
    timeoutMessage:
      t?.('upload.previewTimeout') ??
      'Preview too slow — lower the detail tier or hit Apply to render anyway.',
    // Long-render progress toast wiring. Toast appears after 800ms
    // (so quick renders never surface one), ticks every second so the
    // operator sees the elapsed time, and exposes a cancel button
    // that aborts the in-flight /preview round-trip.
    progressMessage: (seconds: number) =>
      t?.('upload.previewProgress', { seconds }) ?? `Rendering preview… (${seconds}s)`,
    cancelLabel: t?.('upload.previewCancel') ?? 'Cancel',
  })

  // ---- File handling ----
  function refreshThumbnail(): void {
    if (_previewUrl.value) {
      URL.revokeObjectURL(_previewUrl.value)
      _previewUrl.value = null
    }
    if (_selectedFile.value && kind.value === 'bitmap') {
      _previewUrl.value = URL.createObjectURL(_selectedFile.value)
    }
  }

  // Restore the placement's source as a File object. Two paths:
  //   1. ``store.lastFile`` is the bytes from the most recent
  //      drop-anywhere / upload-form action — still in memory.
  //   2. Library placements + post-refresh placements have no
  //      in-memory file, only a ``library_file_id`` pointing at the
  //      backend's persistent store; ``/files/{id}/original`` streams
  //      the bytes back on demand.
  async function ensureSelectedFile(): Promise<void> {
    if (_selectedFile.value) return
    if (store.lastFile) {
      _selectedFile.value = store.lastFile
      return
    }
    const placement = store.selectedPlacement
    if (!placement?.library_file_id || !placement.source_file) return
    try {
      _selectedFile.value = await downloadOriginalFile(
        placement.library_file_id,
        placement.source_file,
        placement.source_mime || 'application/octet-stream',
      )
    } catch {
      // Bytes evicted / network error — UI stays usable in read-only
      // mode (settings visible, /preview disabled until re-attach via
      // the header menu). Surface it on the preview pane so a blank
      // canvas reads as "couldn't reload the source" instead of a
      // mystery: without the File the live /preview can't run, so the
      // SVG would otherwise silently never update on a settings change.
      edit.previewError.value = t?.('upload.sourceReloadFailed') ?? 'Could not reload the source file'
    }
  }

  function setFile(file: File | null): void {
    _selectedFile.value = file
  }

  // ---- Upload ----
  const multiPassLayerCount = computed(
    () =>
      Object.values(store.layerAlgorithms).filter(
        (spec) =>
          Array.isArray((spec as { passes?: unknown[] }).passes) &&
          (spec as { passes: unknown[] }).passes.length > 0,
      ).length,
  )

  async function uploadSelected(): Promise<void> {
    if (!_selectedFile.value) return

    // Ask for overwrite confirmation when a conversion already exists.
    if (store.job) {
      const ok = await confirmAction({
        title: t?.('editModal.overwriteTitle') ?? 'Re-convert file',
        message:
          t?.('editModal.overwriteMessage') ??
          'This file already has a conversion. Overwrite the existing result?',
        confirmLabel: t?.('editModal.overwriteConfirm') ?? 'Re-convert',
        cancelLabel: t?.('confirm.cancel') ?? 'Cancel',
        danger: false,
      })
      if (!ok) return
    }

    if (multiPassLayerCount.value > 0) {
      const ok = await confirmAction({
        title: t?.('passes.reuploadTitle') ?? 'Multi-pass layers',
        message:
          t?.('passes.reuploadWarning', { count: multiPassLayerCount.value }) ??
          `${multiPassLayerCount.value} layer(s) have multi-pass overrides that will be lost. Continue?`,
        confirmLabel: t?.('confirm.ok') ?? 'Continue',
        cancelLabel: t?.('confirm.cancel') ?? 'Cancel',
        danger: true,
      })
      if (!ok) return
    }
    const wasMono = draft.printMode.value === 'monochrome'
    await store.upload(_selectedFile.value, buildOptions())
    previewer.clear()
    // Push the master style's per-cluster recipe onto the freshly
    // produced layers in BOTH print modes. Monochrome's ``bandRecipe``
    // and multicolour's ``colorRecipe`` are how a style like Pencil
    // shaded / Halftone-CMYK / Crosshatch-colour expresses "draw
    // cluster N differently from cluster N-1" — without this call the
    // uniform default algorithm baked in at /upload time wins and the
    // operator's style choice is invisible past the first cluster.
    if (wasMono) {
      await applyMasterStyleToLayers(store, {
        styleId: draft.monoMasterStyleId.value,
        penSlot: draft.monoPenSlot.value,
      })
    } else {
      // Multicolour styles don't pin every layer to one slot — each
      // cluster already carries its segmentation-derived ``target_pen_slot``
      // (or stays null pending pen matching). Pass ``penSlot: null`` so
      // the propagation only touches the algorithm overrides.
      await applyMasterStyleToLayers(store, {
        styleId: draft.multicolorMasterStyleId.value,
        penSlot: null,
      })
    }
    // Refresh the live preview so the canvas reflects the per-band /
    // per-cluster recipes that ``applyMasterStyleToLayers`` just
    // installed via /rerender. Without this, the pane would either
    // stay blank (previewer.clear() above) until the placement SVG
    // arrives, or keep the pre-Apply uniform-algo preview visible —
    // confusing the operator who expected to see the result of their
    // changes.
    previewer.schedule({ immediate: true })
    // Pin the new baseline so the dirty tracker flips back to false
    // — Apply button greys out, close-modal warning won't fire.
    draft.markCommitted()
    if (store.layers.length) ui.canvasTab = 'sheet'
  }

  function clearAll(): void {
    _selectedFile.value = null
    store.clearJob()
  }

  // ---- Page navigation (PDF) ----
  const pageCount = computed(() => Number(store.uploadMetadata.page_count ?? 0))
  const currentPage = computed(() => Number(store.uploadMetadata.page ?? 0))

  async function goToPage(page: number): Promise<void> {
    if (page < 0 || page >= pageCount.value || page === currentPage.value) return
    await store.changePage(page)
    if (store.layers.length) ui.canvasTab = 'sheet'
  }

  // ---- Wiring (idempotent) ----
  // Watchers / mirrors are installed once across the whole app
  // lifetime — the singleton survives modal close. We track disposers
  // so a future ``disposeFileManager`` (called when the modal closes
  // for good) can tear them down cleanly.
  function ensureWired(): void {
    if (_initialised.value) return
    _initialised.value = true

    // Bitmap thumbnail + plain-text preview rebuild on file change.
    _disposers.push(
      watch(_selectedFile, refreshThumbnail),
      watch(_selectedFile, async (file) => {
        _textPreview.value = ''
        if (file && kind.value === 'typography') {
          try {
            const blob = file.slice(0, 4096)
            _textPreview.value = await blob.text()
          } catch {
            _textPreview.value = ''
          }
        }
      }),
      // Detail-tier picker: immediate /preview (no debounce) so the
      // operator gets instant visual feedback on a discrete click.
      watch(
        () => draft.bitmap.value.max_dimension_px,
        () => {
          if (_selectedFile.value && kind.value === 'bitmap') {
            previewer.schedule({ immediate: true })
          }
        },
      ),
      // Everything else: debounced /preview. One deep watch on the
      // bitmap object replaces the 25-field watcher SourceSection used
      // to maintain by hand — adding a new algorithm option no longer
      // requires touching the watcher list.
      watch(
        // Deep-watch the full draft surface that feeds /preview: the
        // bitmap options, the mono ink colour + per-style knobs + per-
        // band overrides, the multicolour per-style knobs, both master-
        // style ids, the curves toggles. A single getter that returns
        // every reactive bag is simpler — and less bug-prone — than
        // maintaining one ``watch()`` per slice; missing one (as we did
        // with ``draft.mono`` and later ``draft.multicolor``) silently
        // breaks the live preview for the knob the operator just moved.
        () => [
          draft.bitmap.value,
          draft.mono.value,
          draft.multicolor.value,
          draft.curves.value,
          draft.monoMasterStyleId.value,
          draft.multicolorMasterStyleId.value,
        ],
        () => {
          if (_selectedFile.value && kind.value === 'bitmap') {
            previewer.schedule()
          } else if (kind.value !== 'typography') {
            previewer.clear()
          }
        },
        { deep: true },
      ),
      // Typography draft has its own deep watcher: every font / size /
      // alignment / margin tweak schedules a debounced ``/preview-text``
      // round-trip so the editor pane mirrors the chosen Hershey face
      // without the operator having to hit Apply.
      watch(
        () => draft.typo.value,
        () => {
          if (_selectedFile.value && kind.value === 'typography') {
            previewer.schedule()
          }
        },
        { deep: true },
      ),
      watch(_selectedFile, () => {
        if (!_selectedFile.value) return
        if (kind.value === 'bitmap' || kind.value === 'typography') {
          previewer.schedule({ immediate: true })
        }
      }),
      // Quality tier change: immediate /preview so the operator sees
      // the tier they just picked. Standard ↔ Final affects k-means
      // restarts; Draft additionally caps the sample resolution. Each
      // tier owns its own slot in the backend LRU so toggling between
      // tiers stays cheap once each has been warmed.
      watch(
        () => edit.previewQuality.value,
        () => {
          if (_selectedFile.value && kind.value === 'bitmap') {
            previewer.schedule({ immediate: true })
          }
        },
      ),

      // Switching placements (via FilesPane) drops the in-memory File
      // and rehydrates the draft so the modal mirrors the newly
      // selected placement's source — see the original audit findings
      // #2/#3 about previous-placement knobs silently feeding the next
      // /preview call.
      watch(
        () => store.selectedPlacementId,
        async () => {
          _selectedFile.value = null
          const installed = (store.selectedProfile?.pens ?? [])
            .filter((p) => p.installed && p.color)
            .map((p) => p.color)
          draft.rehydrateDraft({
            placement: store.selectedPlacement ?? null,
            installedPenColors: installed,
          })
          edit.setGoToPage(goToPage)
          edit.setPreviewCallbacks({ cancel: previewer.cancel, retry: previewer.retry })
          await ensureSelectedFile()
        },
      ),

      // Mirror the preview state into useEditState so EditPreviewPane
      // (rendered as a sibling of the tabs) reads the same values.
      watch(
        _selectedFile,
        (v) => {
          edit.selectedFile.value = v
        },
        { immediate: true },
      ),
      watch(
        _previewUrl,
        (v) => {
          edit.previewUrl.value = v
        },
        { immediate: true },
      ),
      watch(
        _textPreview,
        (v) => {
          edit.textPreview.value = v
        },
        { immediate: true },
      ),
      watch(
        previewer.previewSvg,
        (v) => {
          edit.previewSvg.value = v
        },
        { immediate: true },
      ),
      watch(
        previewer.previewLoading,
        (v) => {
          edit.previewLoading.value = v
        },
        { immediate: true },
      ),
      watch(
        previewer.previewError,
        (v) => {
          edit.previewError.value = v
        },
        { immediate: true },
      ),
      watch(
        previewer.previewResult,
        (v) => {
          edit.previewResult.value = v
          // Feed the cost estimator. Cache hits skew downward (the cost
          // we want to estimate is *compute*, not network), so they're
          // excluded. ``elapsed_ms`` comes straight from the backend's
          // perf_counter wrapper around the converter call.
          if (v && !v.cached && typeof v.elapsed_ms === 'number') {
            costEstimator.record(
              draft.bitmap.value.algorithm,
              edit.previewQuality.value,
              v.elapsed_ms,
            )
          }
        },
        { immediate: true },
      ),
      watch(
        kind,
        (v) => {
          edit.kind.value = v
        },
        { immediate: true },
      ),
      watch(
        pageCount,
        (v) => {
          edit.pageCount.value = v
        },
        { immediate: true },
      ),
      watch(
        currentPage,
        (v) => {
          edit.currentPage.value = v
        },
        { immediate: true },
      ),
    )
    edit.setGoToPage(goToPage)
    edit.setPreviewCallbacks({ cancel: previewer.cancel, retry: previewer.retry })

    // Initial rehydrate + file fetch. Wrapped in a microtask so the
    // wiring isn't blocked on the (potentially slow) library-file
    // download.
    queueMicrotask(() => {
      const installed = (store.selectedProfile?.pens ?? [])
        .filter((p) => p.installed && p.color)
        .map((p) => p.color)
      draft.rehydrateDraft({
        placement: store.selectedPlacement ?? null,
        installedPenColors: installed,
      })
      void ensureSelectedFile()
    })
  }

  function dispose(): void {
    previewer.dispose()
  }

  // Auto-wire on first call. Each subsequent ``useFileManager()`` call
  // is a no-op for wiring but returns the same singleton handles.
  ensureWired()

  // Best-effort cleanup on unmount of the calling component; the
  // singleton stays initialised so the next mount re-uses the same
  // wiring. ``onBeforeUnmount`` here only fires when the active
  // component instance tears down, not the module — exactly the
  // semantics we want.
  onBeforeUnmount(() => {
    previewer.cancel()
  })

  return {
    selectedFile: _selectedFile,
    previewUrl: _previewUrl,
    textPreview: _textPreview,
    sourceName,
    kind,
    showsBitmapForm,
    hasSource,
    previewSvg: previewer.previewSvg,
    previewResult: previewer.previewResult,
    previewLoading: previewer.previewLoading,
    previewError: previewer.previewError,
    pageCount,
    currentPage,
    multiPassLayerCount,
    setFile,
    ensureSelectedFile,
    uploadSelected,
    clearAll,
    goToPage,
    buildOptions,
    previewer,
    dispose,
  }
}

// Module-level reset hook used by EditModal on modal close. Wipes the
// in-memory file and tears down the preview scheduler so a new modal
// open starts from a clean slate.
export function resetFileManager(): void {
  _selectedFile.value = null
  if (_previewUrl.value) {
    URL.revokeObjectURL(_previewUrl.value)
    _previewUrl.value = null
  }
  _textPreview.value = ''
  for (const stop of _disposers) {
    try {
      stop()
    } catch {
      /* ignore */
    }
  }
  _disposers = []
  _initialised.value = false
}
