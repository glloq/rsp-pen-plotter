# Hardware & Streaming

The host streams a generated program to the microcontroller over serial. The
hardware layer is deliberately small and fully testable: the serial link is an
injected protocol, so the controller and streamer are exercised with an
in-memory mock and never need real hardware in tests.

## Transport (`hardware/transport.py`)

`Transport` is a `Protocol` with three async methods: `write_line(line)`,
`read_line()`, and `close()`.

- **`SerialTransport`** wraps `pyserial-asyncio`. It appends the configured line
  terminator on write (LF for GRBL/Marlin, CR for EiBotBoard) and, on `close()`,
  closes the writer and awaits `wait_closed()` so the file descriptor is
  released before any reconnect.
- **`MockTransport`** records every line written and replies `ok` to each — used
  by the test suite and for offline development.

## Streamer (`hardware/streamer.py`)

`GcodeStreamer` implements the standard `ok`-acknowledged handshake: it sends
one command, waits for the controller's `ok`, then sends the next.

- `executable_lines(gcode)` strips comments and blanks to sendable commands.
- **Flow control:** `_wait_ok()` reads until it sees `ok`; an `error`/`alarm`/`!!`
  response raises `StreamError`, and a missing acknowledgment within
  `ack_timeout_s` (default 30 s) also raises — guarding against a stalled or
  disconnected controller.
- **Pause/resume/abort:** an `asyncio.Event` gates each line. `pause()` clears
  it (the stream stops after the current line is acked), `resume()` sets it, and
  `abort()` sets it with an abort flag so the loop exits promptly.
- **Progress:** an optional async callback receives a `StreamProgress`
  (`total`, `sent`, `acked`, `state`) after each acknowledgment and on every
  state change. States: `idle`, `running`, `paused`, `done`, `aborted`, `error`.

## Controller (`hardware/controller.py`)

`PlotterController` owns the active transport and the streaming task and exposes
the operations the API surfaces:

- `open_serial(...)` / `attach(transport)` and `disconnect()` (aborts the job,
  awaits the task, closes the transport, clears state).
- `jog(dx, dy, profile)` and `home(profile)` send control lines immediately,
  but are rejected with `RuntimeError` while a job owns the transport.
- `run(gcode)` launches streaming as a background task; `pause()`, `resume()`,
  `abort()` delegate to the streamer.
- `subscribe()` / `unsubscribe()` manage progress queues; `_broadcast()` fans a
  snapshot out to all subscribers (the `/ws/plotter` WebSocket is one).

A module-level singleton `controller` is shared by the API routers.

## G-code generation templates (`templates/`)

For non-EBB dialects, `core/gcode.py` renders per-command Jinja2 fragments with
`StrictUndefined`: `header.j2`, `footer.j2`, `pen_up.j2`, `pen_down.j2`,
`travel.j2`, `line.j2`, `arc.j2`, `tool_change.j2`. Numeric fields use format
filters, so values can't inject stray newlines. Pen/tool commands come verbatim
from the profile (streamed to hardware, not interpreted by a shell).

When `profile.supports_arcs` is set, `core/arcs.py` collapses runs of
co-circular points into `G2`/`G3` arc moves within `arc_tolerance_mm`.

## Native EBB generation (`core/ebb.py`)

EiBotBoard plotters (AxiDraw class) do not speak G-code. `generate_ebb()` reuses
the same layer reading and workspace transform as the G-code path, then emits
native EBB commands: `SM` (timed relative stepper move), `SP` (servo pen),
`EM`/`SC` (motor enable/config). Because the two motors form an H-bot, a
Cartesian move `(dx, dy)` maps to mixed motor steps `a = dx + dy`,
`b = dx - dy`, scaled by `ebb.steps_per_mm`. All servo positions and speeds come
from the profile's `EbbConfig`.

## Reference hardware

CoreXY frame (~A3), 2× NEMA 17 for X/Y plus one for the pen carousel, TMC2209
drivers, an SG90 pen-lift servo on a PCA9685, a BTT SKR Pico (RP2040) running
Klipper, hosted by a Raspberry Pi 4. Any plotter with a documented G-code
dialect — or an EBB — is supported through a profile alone.
