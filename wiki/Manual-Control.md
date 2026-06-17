# Manual control & the plotter cockpit

The **Plotter** tab is the operator's cockpit: a compact manual-control panel, a
live camera feed, timelapse controls and a history of every command sent to the
device. It's where you jog the head, home axes, lift and drop the pen, and watch
a print run.

The cockpit only acts on a **connected** machine, and its controls are disabled
while a move is in flight or a job is running or paused — you can't fight a
stream with a manual jog.

## Connecting

Press **Connect** and pick the serial port, baud rate and line terminator. The
status line shows the live connection and streaming state. **Disconnect** aborts
any active job and closes the serial link.

## Jogging

A Repetier-style control cluster drives the head:

- **X/Y cross** — arrow buttons for ±X and ±Y relative moves. The centre button
  homes **all** axes.
- **Z column** — Z+ / Z− for a motorised Z axis (sent as a relative `dz`).
- **Pen** — ▲ raises and ▼ lowers the pen, using the profile's
  `pen_up_command` / `pen_down_command`. Disabled if the profile doesn't define
  them.
- **Per-axis home** — ⌂X / ⌂Y / ⌂Z home a single axis (each asks for
  confirmation first).
- **Step selector** — a segmented row of step sizes (0.1 / 0.5 / 1 / 10 / 50 mm,
  default 10) shared by every jog button.

Each jog multiplies the selected step by the direction — with the step at 10 mm,
the +X arrow moves the head 10 mm in X.

## Command history

A collapsible panel at the bottom of the cockpit shows the rolling log of G-code
actually sent to the device — manual jogs, homing, pen moves and the lines of a
streamed job. It polls `GET /plotter/commands` only while it's open and the
Plotter tab is visible, so it costs nothing when collapsed.

## Running, pausing, aborting a print

Start a print from the **Simulator** tab's *Start print* button, or re-print a
saved program from the [G-code library](G-code-Library.md). Once a job is
streaming, the cockpit (and the queue card) expose:

- **Pause** — finishes the current line, stops sending more; resume picks up
  from the checkpoint.
- **Resume** — continues a paused run, or confirms a guided pen swap.
- **Abort / Cancel** — stops the stream and closes the run.
- **Emergency stop** — a real-time stop that preempts any in-flight move,
  writing the dialect's emergency payload (GRBL `0x18`, Marlin `M112`, EBB `ES`)
  straight to the line.

See [Print queue & resume](Print-Queue.md) for what happens to the run itself,
and [Pen magazine](Pen-Magazine.md) for guided pen changes.

## API

| Method & path | What |
| --- | --- |
| `GET /plotter/status` | Connection + streaming snapshot |
| `GET /plotter/commands` | Recent commands sent to the device |
| `POST /plotter/connect` / `disconnect` | Open / close the serial link |
| `POST /plotter/jog` | Relative move (`dx_mm`, `dy_mm`, `dz_mm`) |
| `POST /plotter/goto` | Absolute move |
| `POST /plotter/home` | Home all axes, or a single `axis` (X/Y/Z) |
| `POST /plotter/pause` / `resume` / `abort` | Drive a running job |
| `POST /plotter/emergency_stop` | Real-time stop |

Full details: [`docs/api_reference.md`](../docs/api_reference.md) — Plotter
control.

## See also

- [Camera & timelapse](Camera-and-Timelapse.md)
- [G-code library](G-code-Library.md)
- [Print queue & resume](Print-Queue.md)
- [Per-slot calibration](Per-Slot-Calibration.md)
