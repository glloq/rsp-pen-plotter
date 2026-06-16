// Global Vitest setup — keeps the unit suite network-free and deterministic.
//
// happy-dom resolves a relative SSE URL (``/preview/stream?...``) against its
// synthetic origin (``http://localhost:3000``), so any component that mounts
// the real ``useProgressiveStream`` and opens a stream would otherwise spawn a
// genuine ``EventSource`` → a real TCP connect to 127.0.0.1:3000. With no
// server there that surfaces as ``ECONNREFUSED`` / ``socket hang up`` noise
// and, worse, leaves a reconnect handle open so the runner never exits with a
// clean summary (audit P1).
//
// Replacing the global with a no-op stub means a stream open during a test is
// inert: no socket, no reconnect timer, nothing to leak. Tests that exercise
// the stream's real semantics (``useProgressiveStream.test.ts``,
// ``useEditorPreviewStream.test.ts``) inject their own fake factory / stub
// handle and never touch this global, so they're unaffected.
import { api } from './src/api/client'
import { i18n } from './src/i18n'
import en from './src/locales/en.json'
import fr from './src/locales/fr.json'

// The app now lazy-loads locale catalogues (only the active language is
// bundled at boot; see src/i18n.ts), so the shared i18n instance starts
// with empty messages. Populate both synchronously here so any test that
// exercises the *real* i18n (stores call ``i18n.global.t`` directly) sees
// fully-translated strings, exactly as it did when both locales were
// statically imported. Tests that ``vi.mock('../i18n')`` use their own
// catalogue and are unaffected.
i18n.global.setLocaleMessage('en', en as Record<string, unknown>)
i18n.global.setLocaleMessage('fr', fr as Record<string, unknown>)

// Network kill-switch for the unit suite.
//
// The app's axios instance defaults to an empty ``baseURL`` (same-origin in
// production). Under happy-dom that resolves against the synthetic origin
// ``http://localhost:3000``, so any component that fires a request on mount —
// e.g. ``SheetPreview`` / ``MagazineEditor`` pulling the pen-width inventory
// in ``onMounted`` — opens a real TCP socket to 127.0.0.1:3000. With no server
// the request errors (``ECONNREFUSED`` locally, ``socket hang up`` /
// ``ECONNRESET`` elsewhere) and, depending on the host, can leave the runner
// hanging without a final summary (audit P1).
//
// These calls are fire-and-forget and their rejection is already handled by
// the call sites, so failing them *synchronously, without a socket* keeps the
// observable behaviour identical while making the suite network-free and
// deterministic. Tests that need a specific response mock ``../api/client``
// wholesale (which replaces this instance) or spy on the store methods, so
// they're unaffected by this adapter.
api.defaults.adapter = () =>
  Promise.reject(
    new Error('Network is disabled in the unit test environment (see vitest.setup.ts).'),
  )

class NoopEventSource {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 2
  readonly url: string
  readyState = NoopEventSource.CLOSED
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  onopen: ((ev: Event) => void) | null = null
  constructor(url: string) {
    this.url = url
  }
  addEventListener(): void {}
  removeEventListener(): void {}
  dispatchEvent(): boolean {
    return false
  }
  close(): void {}
}

globalThis.EventSource = NoopEventSource as unknown as typeof EventSource
