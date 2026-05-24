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
import { useEditState } from './useEditState'
import { useBitmapDraft } from './useBitmapDraft'
import { usePreviewScheduler } from './usePreviewScheduler'
import { applyMasterStyleToLayers } from './useStylePropagation'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'

const IMAGE_EXT = ['png', 'jpg', 'jpeg', 'tiff', 'webp', 'heic']
const TYPOGRAPHY_EXT = ['txt', 'md']
const DOCUMENT_EXT = ['pdf', 'svg', 'eps', 'ps', 'ai', 'docx', 'odt', 'rtf', 'html']
export const FILE_ACCEPT
  = '.svg,.png,.jpg,.jpeg,.tiff,.webp,.heic,.pdf,.dxf,.eps,.ps,.ai,.txt,.md,.html,.docx,.odt,.rtf'

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

  const hasSource = computed<boolean>(
    () => Boolean(_selectedFile.value || store.selectedPlacement?.source_file),
  )

  function buildOptions(): Record<string, unknown> | undefined {
    if (showsBitmapForm.value) return draft.buildBitmapOptions()
    if (kind.value === 'typography') return draft.buildTypographyOptions()
    return undefined
  }

  // ---- Preview scheduler ----
  const previewer = usePreviewScheduler({
    fileGetter: () => _selectedFile.value,
    algorithmGetter: () => draft.bitmap.value.algorithm,
    optionsBuilder: () => buildOptions(),
    shouldRun: () => kind.value === 'bitmap',
    failedMessage: t?.('upload.failed') ?? 'preview failed',
    timeoutMessage: t?.('upload.previewTimeout')
      ?? 'Preview too slow — lower the detail tier or hit Apply to render anyway.',
    // Long-render progress toast wiring. Toast appears after 800ms
    // (so quick renders never surface one), ticks every second so the
    // operator sees the elapsed time, and exposes a cancel button
    // that aborts the in-flight /preview round-trip.
    progressMessage: (seconds: number) =>
      t?.('upload.previewProgress', { seconds })
        ?? `Rendering preview… (${seconds}s)`,
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
      // the header menu).
    }
  }

  function setFile(file: File | null): void {
    _selectedFile.value = file
  }

  // ---- Upload ----
  const multiPassLayerCount = computed(() =>
    Object.values(store.layerAlgorithms).filter(
      (spec) => Array.isArray((spec as { passes?: unknown[] }).passes)
        && (spec as { passes: unknown[] }).passes.length > 0,
    ).length,
  )

  async function uploadSelected(): Promise<void> {
    if (!_selectedFile.value) return
    if (multiPassLayerCount.value > 0) {
      const message = t?.('passes.reuploadWarning', { count: multiPassLayerCount.value })
        ?? `${multiPassLayerCount.value} layer(s) have multi-pass overrides that will be lost. Continue?`
      const ok = window.confirm(message)
      if (!ok) return
    }
    const wasMono = draft.printMode.value === 'monochrome'
    await store.upload(_selectedFile.value, buildOptions())
    previewer.clear()
    if (wasMono) {
      await applyMasterStyleToLayers(store, {
        styleId: draft.monoMasterStyleId.value,
        penSlot: draft.monoPenSlot.value,
      })
      // Refresh the live preview so the canvas reflects the per-band
      // recipes that ``applyMasterStyleToLayers`` just installed via
      // /rerender. Without this, the pane would either stay blank
      // (previewer.clear() above) until the placement SVG arrives, or
      // keep the pre-Apply uniform-algo preview visible — confusing
      // the operator who expected to see the result of their changes.
      previewer.schedule({ immediate: true })
    }
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
        () => draft.bitmap.value,
        () => {
          if (_selectedFile.value && kind.value === 'bitmap') {
            previewer.schedule()
          } else {
            previewer.clear()
          }
        },
        { deep: true },
      ),
      watch(_selectedFile, () => {
        if (_selectedFile.value && kind.value === 'bitmap') {
          previewer.schedule({ immediate: true })
        }
      }),

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
      watch(_selectedFile, (v) => { edit.selectedFile.value = v }, { immediate: true }),
      watch(_previewUrl, (v) => { edit.previewUrl.value = v }, { immediate: true }),
      watch(_textPreview, (v) => { edit.textPreview.value = v }, { immediate: true }),
      watch(previewer.previewSvg, (v) => { edit.previewSvg.value = v }, { immediate: true }),
      watch(previewer.previewLoading, (v) => { edit.previewLoading.value = v }, { immediate: true }),
      watch(previewer.previewError, (v) => { edit.previewError.value = v }, { immediate: true }),
      watch(previewer.previewResult, (v) => { edit.previewResult.value = v }, { immediate: true }),
      watch(kind, (v) => { edit.kind.value = v }, { immediate: true }),
      watch(pageCount, (v) => { edit.pageCount.value = v }, { immediate: true }),
      watch(currentPage, (v) => { edit.currentPage.value = v }, { immediate: true }),
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
    try { stop() } catch { /* ignore */ }
  }
  _disposers = []
  _initialised.value = false
}
