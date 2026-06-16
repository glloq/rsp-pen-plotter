// Lazy "is this element on screen?" gate, backed by IntersectionObserver
// (audit B3).
//
// The file library renders every row up front (natural scroll + layout),
// but the expensive per-row work — fetching the full SVG detail and
// running it through DOMPurify for the thumbnail — used to fire for ALL
// rows on pane open and on every filter change. This composable lets each
// row defer that work until it actually scrolls into view: the row passes
// its root element and watches the returned ``visible`` ref.
//
// Degrades to eager (``visible = true`` immediately) when
// IntersectionObserver is unavailable (SSR, very old browsers) so nothing
// that depends on it stays permanently hidden.

import { onScopeDispose, ref, watch, type Ref } from 'vue'

export interface InViewportOptions {
  /** Pre-load margin around the root so rows just below the fold start
   *  loading before they're fully visible. Default 300px. */
  rootMargin?: string
  /** Latch ``true`` on first intersection and stop observing (default).
   *  Set false to track visibility both ways. */
  once?: boolean
}

export function useInViewport(
  elRef: Ref<HTMLElement | null>,
  options: InViewportOptions = {},
): Ref<boolean> {
  const visible = ref(false)

  if (typeof IntersectionObserver === 'undefined') {
    visible.value = true
    return visible
  }

  const once = options.once !== false
  let observer: IntersectionObserver | null = null

  function disconnect(): void {
    observer?.disconnect()
    observer = null
  }

  function observe(el: HTMLElement): void {
    disconnect()
    try {
      observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) {
              visible.value = true
              if (once) disconnect()
            } else if (!once) {
              visible.value = false
            }
          }
        },
        { rootMargin: options.rootMargin ?? '300px' },
      )
      observer.observe(el)
    } catch {
      // A broken / stub observer must not strand the element invisible
      // forever — degrade to eager.
      visible.value = true
    }
  }

  watch(
    elRef,
    (el) => {
      if (el) observe(el)
      else disconnect()
    },
    { immediate: true },
  )

  onScopeDispose(disconnect)

  return visible
}
