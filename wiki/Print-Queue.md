# Print queue & resume

OmniPlot has a **durable** print queue. Once a job is enqueued it
survives reboots, power loss, browser tab closures and operator panic
buttons. The queue is the single source of truth for what the plotter
should do next.

## States

A run moves through these states:

```
queued → running → (paused) → completed
                 ↘ (canceled)
                 ↘ (failed)
```

- **queued** — enqueued, not yet started (or re-queued after a resume)
- **running** — actively streaming G-code
- **paused** — soft-pause, an operator-confirm pen swap, or a recovery
  stop; resumable from the checkpoint
- **completed** — every line acked
- **canceled** — operator-initiated stop; the queue cleaned up
- **failed** — error mid-stream (serial drop, timeout, dialect error)

## Checkpointing

While running, the queue persists the last-acked line into SQLite —
throttled to **every 50 lines or every 2 s**, plus on every stream-state
flip (pause, swap, error, done), so a synchronous commit per `ok` never
stalls the event loop. After a crash or power loss you lose at most
~50 lines of checkpoint; every pause/error boundary is always durable.

After a power loss:

1. on boot the queue scans for runs in `running` state
2. it moves them to `paused` with their last checkpoint — never
   auto-resumed, since the head's physical position is unknown after an
   unclean stop
3. the UI surfaces the paused run for the operator
4. on *Resume*, the streamer rebuilds a modal-state preamble (last known
   feed rate, absolute/relative mode, pen up/down state) and starts
   from the line after the last ack

If you don't trust the checkpoint, *Cancel* and re-queue from scratch.

## Pause, resume, cancel

Three buttons on every running run (Plotter tab, Queue card, header
Workshop button):

- **Pause** — finishes the current line, stops sending more lines. The
  serial link stays open. Resume picks up exactly where it left off.
- **Resume** — continues a streaming run, or re-queues a paused run
  from its checkpoint (with the modal preamble).
- **Cancel** — aborts the stream and closes the run as `canceled`. The
  final checkpoint is persisted, so the run could still be resumed by
  re-queuing if needed.

The pause button is also bound to **⌘/Ctrl + K**, resume to **⌘/Ctrl + R**.

## Guided pen changes

When a run hits a layer assigned to a different pen than the active
slot, the queue:

1. issues a soft-pause; the run shows as `paused` with a `swap_prompt`
   (e.g. *"Change pen to Red (#ff0000)"*) on every connected client
2. waits for explicit confirmation (no auto-resume on timer)
3. on **Resume** (`POST /queue/{run_id}/resume`), streaming continues
   past the swap and the prompt clears

The G-code that gets downloaded keeps an `M0` at the swap point, so
running the file through another sender on another day still behaves
the same way.

## Error recovery & skipped layers

The profile's `recovery_policy` decides what happens when the firmware
rejects a command mid-stream:

- **abort** — the run goes to `failed`
- **pause_and_prompt** — the run goes to `paused` at the live
  checkpoint; the operator drives resume
- **skip_layer** — the queue advances the checkpoint past the next
  layer boundary, records the label in `skipped_layers` and re-queues.
  Resume uses the **live** checkpoint, so already-inked layers are never
  re-plotted.

## Priority

`priority` is an **integer** field (default `0`) on `POST /queue`. The
worker always picks the highest-priority queued run first (ties broken
by enqueue time). A higher-priority job does **not** preempt the run
that is currently streaming — it goes next once the current run
finishes or is paused/canceled.

## Idempotency

`POST /queue` honours an `Idempotency-Key` HTTP header. If a run
already exists with that key, it is returned instead of creating a
duplicate — the key is stored with the run, with **no expiry window**.
Useful for automation that retries on network errors without risking a
duplicate plot.

## API

| Method & path | What |
| --- | --- |
| `GET /queue` | List runs, active first — **summaries without `gcode`** (`id`, `name`, `profile_name`, `total_lines`, `acked_lines`, `state`, `priority`, `error`, `swap_prompt`, `skipped_layers`, `idempotency_key`, `created_at`, `updated_at`) |
| `GET /queue/{run_id}` | The full run, including the `gcode` payload |
| `POST /queue` | Enqueue (honours `Idempotency-Key`) |
| `POST /queue/{run_id}/pause` | Soft-pause |
| `POST /queue/{run_id}/resume` | Resume from checkpoint / confirm a pen swap |
| `POST /queue/{run_id}/cancel` | Abort and clean up |
| `DELETE /queue/{run_id}` | Remove a run (`409` while streaming — cancel first) |

The UI polls `GET /queue` every few seconds; the summary projection
keeps that poll small even with large programs queued.

All queue endpoints honour the optional `OMNIPLOT_API_KEY`.

## See also

- [Pen magazine](Pen-Magazine.md)
- [`docs/api_reference.md`](../docs/api_reference.md) — Queue section
- [`docs/hardware_streaming.md`](../docs/hardware_streaming.md)
