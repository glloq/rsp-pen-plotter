// Reactive multi-selection for the layers list. Provided by
// LayersSection at the section root and injected by LayerCard and the
// bulk-actions bar — same pattern as the existing
// ``layersCollapseAll`` toggle.
//
// Selection model is "list-box" semantics:
//   - plain click  → set selection to just this one (or clear if it
//     was the only selected one)
//   - shift+click  → range select from the last anchor to this index
//   - ctrl/⌘+click → toggle this entry, keep the rest
//
// The anchor (last single-click target) is tracked so a subsequent
// shift+click produces the expected range. Cleared when the layers
// list changes (placement switch / re-upload) so the next click starts
// fresh.

import { computed, ref, type InjectionKey, type Ref } from 'vue'

export interface LayerSelection {
  selected: Ref<Set<string>>
  anchorId: Ref<string | null>
  count: Ref<number>
  isSelected: (id: string) => boolean
  toggle: (id: string) => void
  selectOnly: (id: string) => void
  selectRange: (allIds: string[], toId: string) => void
  selectAll: (allIds: string[]) => void
  clear: () => void
  handleClick: (id: string, event: MouseEvent, allIds: string[]) => void
}

export const LayerSelectionKey: InjectionKey<LayerSelection> = Symbol('LayerSelection')

export function createLayerSelection(): LayerSelection {
  const selected = ref<Set<string>>(new Set())
  const anchorId = ref<string | null>(null)
  const count = computed(() => selected.value.size)

  function isSelected(id: string): boolean {
    return selected.value.has(id)
  }

  function toggle(id: string): void {
    const next = new Set(selected.value)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    selected.value = next
    anchorId.value = id
  }

  function selectOnly(id: string): void {
    selected.value = new Set([id])
    anchorId.value = id
  }

  function selectRange(allIds: string[], toId: string): void {
    const fromId = anchorId.value
    if (!fromId) {
      selectOnly(toId)
      return
    }
    const fromIdx = allIds.indexOf(fromId)
    const toIdx = allIds.indexOf(toId)
    if (fromIdx < 0 || toIdx < 0) {
      selectOnly(toId)
      return
    }
    const [lo, hi] = fromIdx <= toIdx ? [fromIdx, toIdx] : [toIdx, fromIdx]
    selected.value = new Set(allIds.slice(lo, hi + 1))
  }

  function selectAll(allIds: string[]): void {
    selected.value = new Set(allIds)
    anchorId.value = allIds[allIds.length - 1] ?? null
  }

  function clear(): void {
    selected.value = new Set()
    anchorId.value = null
  }

  function handleClick(id: string, event: MouseEvent, allIds: string[]): void {
    if (event.shiftKey) {
      selectRange(allIds, id)
      event.preventDefault()
      return
    }
    if (event.ctrlKey || event.metaKey) {
      toggle(id)
      event.preventDefault()
      return
    }
    // Plain click: select-only, except if this is already the sole
    // selected one — then clear (so "click once more to deselect"
    // works without forcing a chord).
    if (selected.value.size === 1 && selected.value.has(id)) {
      clear()
      return
    }
    selectOnly(id)
  }

  return {
    selected,
    anchorId,
    count,
    isSelected,
    toggle,
    selectOnly,
    selectRange,
    selectAll,
    clear,
    handleClick,
  }
}
