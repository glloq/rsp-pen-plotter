# G-code library

The **G-code files** tab is a library of saved programs you can re-print on
demand — no re-conversion, no editor round-trip. Generate once, save, and plot
the same file again whenever you like.

A saved program is just stored text. **Saving never starts a print.** Printing
is always an explicit action.

## Saving a program

Generate a plot as usual, then open the **Simulator** tab. Beside *Start print*
is a **Save G-code** button: it stores the current program — its name, the
target machine profile, the full G-code, and the per-colour drawn lengths used
by the [ink odometer](Ink-Odometer.md) — into the library.

The per-colour lengths are captured at save time because raw G-code can't be
decomposed back into colours later. That's what lets a re-print advance the ink
odometer correctly.

## Re-printing

The **G-code files** tab lists every saved program (newest first) with its name,
size and line count. For each entry you can:

- **Print** — enqueues the program as a run and starts it. The run is linked
  back to the saved file, and the file's stored per-colour lengths are added to
  the ink odometer.
- **Rename** — inline edit.
- **Delete** — with confirmation.

If a saved file is currently printing, its live run state (queued / running /
paused) shows inline and the Print button is disabled until it finishes.

Re-printing goes through the normal [print queue](Print-Queue.md): it
checkpoints, survives reboots, and honours guided pen changes exactly like a
freshly generated job.

## Where it's stored

Saved programs live in the SQLite database (`OMNIPLOT_DB`), so they survive
upgrades and reboots. Back them up by copying the database file — see the
[FAQ](FAQ.md).

## API

| Method & path | What |
| --- | --- |
| `GET /gcode-files` | List saved programs (no payload) |
| `POST /gcode-files` | Save `{ name, profile_name, gcode, length_mm_by_color? }` |
| `PATCH /gcode-files/{id}` | Rename |
| `DELETE /gcode-files/{id}` | Delete |
| `POST /gcode-files/{id}/print` | Enqueue and launch the saved program |

These honour the optional `OMNIPLOT_API_KEY`. Full details:
[`docs/api_reference.md`](../docs/api_reference.md).

## See also

- [Print queue & resume](Print-Queue.md)
- [Ink odometer](Ink-Odometer.md)
- [Raw G-code direct send](File-Type-Gcode.md)
