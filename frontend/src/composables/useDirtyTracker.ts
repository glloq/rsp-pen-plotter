// Tracks whether a reactive object has drifted from a baseline
// snapshot. Used by the editor to:
//   - enable / disable the "Apply changes" button when nothing has
//     drifted from what's already uploaded
//   - prompt the operator before closing the modal or switching
//     placements if there are unsaved edits
//
// Snapshot comparison is a structural JSON equality — cheap enough
// for the BitmapDraft / TypographyDraft (a few dozen primitive
// fields), and avoids carrying per-field "is this the same" hooks.
// Fields that aren't JSON-serialisable (Date, Map, File handles)
// should be projected out before snapshotting.

import { computed, ref, watch, type Ref, type WatchStopHandle } from 'vue'

export interface DirtyTracker<T> {
  isDirty: Ref<boolean>
  // Capture the current value as the new baseline — call this
  // immediately after a successful save (e.g. after /upload returns
  // 200) so the dirty flag flips back to false.
  reset: (next?: T) => void
  // Stop the internal watcher (call in onBeforeUnmount). Returning
  // it from the composable so the caller controls lifetime explicitly
  // — important because the editor mounts/unmounts the modal
  // frequently and an orphaned watcher would survive past the modal
  // close and leak.
  stop: WatchStopHandle
}

function snapshot<T>(value: T): string {
  try {
    return JSON.stringify(value)
  } catch {
    return ''
  }
}

export function useDirtyTracker<T>(source: Ref<T>): DirtyTracker<T> {
  const baseline = ref<string>(snapshot(source.value))
  const current = ref<string>(baseline.value)
  const isDirty = computed(() => current.value !== baseline.value)

  const stop = watch(
    source,
    (v) => {
      current.value = snapshot(v)
    },
    { deep: true },
  )

  function reset(next?: T): void {
    const target = next === undefined ? source.value : next
    const s = snapshot(target)
    baseline.value = s
    current.value = s
  }

  return { isDirty, reset, stop }
}
