# Keyboard shortcuts

Single source of truth for the v0.2 keyboard shortcuts. The list lives
in `frontend/src/composables/useKeyboardShortcuts.ts`
(`SHORTCUTS` constant) — keep this document in sync when you add or
change a binding.

The shortcuts are **only active outside editable surfaces** (inputs,
textareas, contenteditable). Normal typing is never intercepted.

## Bindings

| Shortcut          | Action                              | ID                |
|-------------------|-------------------------------------|-------------------|
| Ctrl/Cmd + Enter  | Next step in the modal              | `modal.next`      |
| Ctrl/Cmd + ⌫      | Previous step in the modal          | `modal.previous`  |
| Ctrl/Cmd + M      | Toggle assisted / expert mode       | `mode.toggle`     |
| Ctrl/Cmd + P      | Toggle the perf overlay (C.8)       | `perf.toggle`     |
| Ctrl/Cmd + K      | Pause the active run                | `queue.pause`     |
| Ctrl/Cmd + R      | Resume the active run               | `queue.resume`    |

Components opt into a binding by registering a handler:

```ts
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'

useKeyboardShortcuts([
  { id: 'modal.next', handler: () => advance() },
])
```

The composable wires `onMounted` / `onBeforeUnmount` automatically, so a
component using a shortcut releases it as soon as it leaves the tree.

## Microcopy conventions (roadmap C.9)

The v0.2 modal + inspectors follow the audit #7 §7 microcopy rules:

1. **Action** (what the operator is about to do) — verb + object.
2. **Consequence** — what changes when they confirm.
3. **Recommendation** — what we think they should pick, with a reason.

Example for a Cancel-run confirm:

> **Action :** Annuler le run.
> **Conséquence :** L'impression s'arrête immédiatement et ne pourra
> pas être reprise.
> **Recommandation :** Préfère la pause si tu veux pouvoir reprendre
> plus tard.

## i18n

`v2.*` translation keys live in `frontend/src/locales/{en,fr}.json`.
Adding a new v0.2 surface requires adding the key in **both** files
in the same PR. The vitest type-check picks up missing keys.
