// Dialog accessibility for the V2 editor modal: focus management + the
// keyboard contract a modal dialog owes (Escape to close, Tab trapped
// inside, focus moved in on open and returned to the opener on close).
//
// Extracted from ``EditModalV2.vue`` (Phase 4 of the editor audit) and
// hardened: it now captures the element that had focus when the dialog
// opened and restores focus there on close (so keyboard users aren't
// dumped at the top of the page), and it skips ``aria-disabled`` and
// hidden controls when computing the tab ring.
import type { Ref } from 'vue'

// Tabbable candidates inside the dialog. ``aria-disabled`` and the
// ``hidden`` attribute are filtered out at query time below — the CSS
// selector can't express either.
const FOCUSABLE_SELECTOR = [
  'button:not([disabled])',
  '[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

export interface DialogAccessibilityDeps {
  dialogRoot: Ref<HTMLElement | null>
  /** Called on Escape — typically ``() => emit('cancel')``. */
  onEscape: () => void
}

export function useEditorDialogAccessibility(deps: DialogAccessibilityDeps) {
  // The control that had focus when the dialog opened, restored on close.
  let opener: HTMLElement | null = null

  function focusables(): HTMLElement[] {
    const root = deps.dialogRoot.value
    if (!root) return []
    return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
      // Skip controls that are present but not actually operable: an
      // ``aria-disabled`` element still matches ``:not([disabled])`` (the
      // two are independent), and ``hidden`` elements aren't tabbable.
      (el) => el.getAttribute('aria-disabled') !== 'true' && !el.hidden,
    )
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault()
      deps.onEscape()
      return
    }
    if (event.key !== 'Tab') return
    // Recompute every keystroke so the trap follows content that mounted
    // after open (e.g. the lazy expert tabs, or a freshly revealed card).
    const ring = focusables()
    if (ring.length === 0) return
    const first = ring[0]!
    const last = ring[ring.length - 1]!
    const active = document.activeElement as HTMLElement | null
    // Wrap at the ends. Also pull focus back when it has escaped the
    // dialog entirely (active not inside the ring) — a Tab from outside
    // lands on the first control rather than leaking to the page.
    if (event.shiftKey && (active === first || !ring.includes(active as HTMLElement))) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && (active === last || !ring.includes(active as HTMLElement))) {
      event.preventDefault()
      first.focus()
    }
  }

  // Start trapping. Capture the opener BEFORE moving focus inside so the
  // restore on ``deactivate`` returns to where the operator came from.
  function activate(): void {
    opener = (document.activeElement as HTMLElement | null) ?? null
    window.addEventListener('keydown', onKeydown)
  }

  // Move focus to the first tabbable control in the dialog. Call after the
  // dialog's content has rendered (``await nextTick()``).
  function focusInitial(): void {
    focusables()[0]?.focus()
  }

  // Stop trapping and return focus to the opener, but only when it's still
  // in the document and focusable — a stale/detached trigger would throw
  // or silently no-op, so fall back to leaving focus where it is.
  function deactivate(): void {
    window.removeEventListener('keydown', onKeydown)
    if (opener && document.contains(opener) && typeof opener.focus === 'function') {
      opener.focus()
    }
    opener = null
  }

  return { activate, focusInitial, deactivate }
}
