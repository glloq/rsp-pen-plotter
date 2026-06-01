# Print queue & resume

OmniPlot has a **durable** print queue. Once a job is enqueued it
survives reboots, power loss, browser tab closures and operator panic
buttons. The queue is the single source of truth for what the plotter
should do next.

## States

A run moves through these states:

```
pending → running → (paused) → finished
                  ↘ (aborted)
                  ↘ (failed)
```

- **pending** — enqueued, not yet started
- **running** — actively streaming G-code
- **paused** — soft-pause; the streamer has stopped sending but the
  serial link is still open
- **finished** — every line acked
- **aborted** — operator-initiated stop; the queue cleaned up
- **failed** — error mid-stream (serial drop, timeout, dialect error)

## Checkpointing

While running, the queue records the last-acked line every ~1 s into
SQLite. After a power loss:

1. on boot the queue scans for runs in `running` state
2. it moves them to `paused` with their last checkpoint
3. the UI shows a *"Run #N was interrupted — resume?"* prompt
4. on confirm, the streamer rebuilds a modal-state preamble (last known
   feed rate, absolute/relative mode, pen up/down state) and starts
   from the line after the last ack

If you don't trust the checkpoint, *Abort* and re-queue from scratch.

## Pause, resume, abort

Three buttons on every running run (Plotter tab, Queue card, header
Workshop button):

- **Pause** — finishes the current line, lifts the pen, stops sending
  more lines. The serial link stays open. Resume picks up exactly where
  it left off.
- **Resume** — sends the modal preamble and continues.
- **Abort** — sends the profile's emergency stop sequence (default:
  pen up + home), then closes the run as `aborted`.

The pause button is also bound to **⌘/Ctrl + K**, resume to **⌘/Ctrl + R**.

## Guided pen changes

When a run hits a layer assigned to a different pen than the active
slot, the queue:

1. issues a soft-pause
2. shows a *Swap to slot N — &lt;pen name&gt;* modal on every connected
   client
3. waits for explicit confirmation (no auto-resume on timer)
4. on confirm, marks the new slot as active and resumes

The G-code that gets downloaded keeps an `M0` at the swap point, so
running the file through another sender on another day still behaves
the same way.

## Priority

The queue supports two priority levels: **normal** and **high**. A
high-priority job pauses the currently-running normal job (with a
guided pen-park), runs to completion, then resumes the original. Useful
for a quick test plot mid-batch.

Set priority at enqueue time via the *Priority* dropdown on the
*Generate* step, or via the `priority` field on `POST /queue`.

## Idempotency

`POST /queue` honours an `Idempotency-Key` HTTP header. Two requests
with the same key inside a 24 h window collapse to the same run. Useful
for automation that retries on network errors without risking a
duplicate plot.

## API

| Method & path | What |
| --- | --- |
| `GET /queue` | List active + pending + recent finished |
| `GET /queue/{run_id}` | A single run with checkpoint + swap state |
| `POST /queue` | Enqueue (honours `Idempotency-Key`) |
| `POST /queue/{run_id}/pause` | Soft-pause |
| `POST /queue/{run_id}/resume` | Resume from checkpoint |
| `POST /queue/{run_id}/cancel` | Abort and clean up |
| `POST /queue/{run_id}/confirm-swap` | Confirm a guided pen change |

All queue endpoints honour the optional `OMNIPLOT_API_KEY`.

## See also

- [Pen magazine](Pen-Magazine.md)
- [`docs/api_reference.md`](../docs/api_reference.md) — Queue section
- [`docs/hardware_streaming.md`](../docs/hardware_streaming.md)
