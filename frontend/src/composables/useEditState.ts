import { computed, type ComputedRef, type Ref, ref } from 'vue'

// Editor-pane state shared between the right-hand settings cards
// (SourceSection) and the left-hand preview pane (EditPreviewPane). The
// modal is mounted at most once at a time, so a module-level singleton
// is simpler than provide/inject between siblings.
export type EditFileKind = 'bitmap' | 'typography' | 'document' | 'none'

interface PalettePreviewEntry {
  color: string
}

interface PreviewResultLike {
  svg?: string
  elapsed_ms?: number
  cached?: boolean
  palette?: PalettePreviewEntry[]
}

// Raw mutable state, owned by SourceSection.
const _selectedFile = ref<File | null>(null)
const _previewUrl = ref<string | null>(null)
const _textPreview = ref<string>('')
const _previewSvg = ref<string>('')
const _previewLoading = ref<boolean>(false)
const _previewError = ref<string | null>(null)
const _previewResult = ref<PreviewResultLike | null>(null)
const _kind = ref<EditFileKind>('none')
const _pageCount = ref<number>(0)
const _currentPage = ref<number>(0)
let _goToPage: (page: number) => Promise<void> = async () => {}

// Derived read-only views surfaced to the preview pane.
const _previewElapsedMs: ComputedRef<number | null> = computed(
  () => _previewResult.value?.elapsed_ms ?? null,
)
const _previewCached: ComputedRef<boolean> = computed(
  () => Boolean(_previewResult.value?.cached),
)
const _previewPalette: ComputedRef<string[]> = computed(
  () => (_previewResult.value?.palette ?? []).map((entry) => entry.color),
)

export interface EditState {
  selectedFile: Ref<File | null>
  previewUrl: Ref<string | null>
  textPreview: Ref<string>
  previewSvg: Ref<string>
  previewLoading: Ref<boolean>
  previewError: Ref<string | null>
  previewResult: Ref<PreviewResultLike | null>
  previewElapsedMs: Ref<number | null>
  previewCached: Ref<boolean>
  previewPalette: Ref<string[]>
  kind: Ref<EditFileKind>
  pageCount: Ref<number>
  currentPage: Ref<number>
  goToPage: (page: number) => Promise<void>
  setGoToPage: (fn: (page: number) => Promise<void>) => void
}

// Wipe every shared ref back to its empty/initial state. Called when
// the modal closes or the selected placement changes — otherwise the
// singleton would surface the previous session's preview SVG / palette
// before the new mount's mirror watches have caught up.
export function resetEditState(): void {
  _selectedFile.value = null
  _previewUrl.value = null
  _textPreview.value = ''
  _previewSvg.value = ''
  _previewLoading.value = false
  _previewError.value = null
  _previewResult.value = null
  _kind.value = 'none'
  _pageCount.value = 0
  _currentPage.value = 0
  _goToPage = async () => {}
}

export function useEditState(): EditState {
  return {
    selectedFile: _selectedFile,
    previewUrl: _previewUrl,
    textPreview: _textPreview,
    previewSvg: _previewSvg,
    previewLoading: _previewLoading,
    previewError: _previewError,
    previewResult: _previewResult,
    previewElapsedMs: _previewElapsedMs,
    previewCached: _previewCached,
    previewPalette: _previewPalette,
    kind: _kind,
    pageCount: _pageCount,
    currentPage: _currentPage,
    goToPage: (page) => _goToPage(page),
    setGoToPage: (fn) => {
      _goToPage = fn
    },
  }
}
