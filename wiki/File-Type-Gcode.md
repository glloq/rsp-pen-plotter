# Raw G-code

Raw G-code enters OmniPlot **through the API, not the file picker**. There
is no `.gcode` / `.nc` / `.tap` upload: the drag-and-drop pipeline only
accepts formats it can normalise to the SVG pivot, and a G-code file would
be rejected with a 415. Instead, you hand the program to the backend as a
string — it bypasses the converter pipeline entirely. No SVG pivot, no
toolpath optimisation, no scaling. It is streamed exactly as you wrote it.

## Two entry points

**`POST /queue`** — the durable path. Enqueue the program as a print run;
it survives reboots and resumes from its checkpoint:

```bash
curl -X POST http://plotter.local:8000/queue \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: my-batch-42' \
  -d '{
    "name": "city-map",
    "profile_name": "Custom CoreXY A3",
    "gcode": "G21\nG90\nG0 X10 Y10\n...",
    "priority": 0
  }'
```

The `Idempotency-Key` header makes retries safe — a second request with
the same key returns the existing run instead of plotting twice.

**`POST /plotter/run`** — the immediate path. Streams the program to the
connected plotter right away (`409` if a job is already running):

```bash
curl -X POST http://plotter.local:8000/plotter/run \
  -H 'Content-Type: application/json' \
  -d '{"gcode": "G21\nG90\n...", "profile_name": "Custom CoreXY A3"}'
```

Supplying `profile_name` is optional on `/plotter/run`, but recommended:
it lets the controller compute guided tool-change pauses, so a manual run
on a multi-pen profile still halts at swap boundaries.

If `OMNIPLOT_API_KEY` is set, add `-H 'X-API-Key: <key>'` to both calls.

> The `pen_plotter.sdk` package is a *plugin* SDK (converters, algorithms,
> profiles) — it is not an HTTP client. Use `curl`, `httpx` or any HTTP
> library against the endpoints above.

## When to use this

- you've generated G-code in another tool (`vpype write`, Saxi, Inkscape's
  Gcode tools, ploterifs, custom Python)
- you want to print a known-good file repeatedly
- you're debugging a firmware-specific dialect

## When *not* to use this

- you want pre-flight bounds / time checks — those need the SVG pivot
- the source file's dialect doesn't match your active machine profile
- you want pen-up / pen-down commands tuned per pen slot

## Dialect matching

Each machine profile declares a G-code dialect (`marlin`, `grbl`, `ebb`,
`klipper`, custom). OmniPlot does **not** translate one dialect to
another for raw programs — that's only done at generation time. If your
file uses `M3 S0` to lift the pen and your profile expects `M5`, you
need to translate manually or regenerate.

Common mismatches:

| Symptom | Cause |
| --- | --- |
| Pen never lifts | `M3` / `M5` vs servo `M280` mismatch |
| Pen always down | Same, but the lift command is silently rejected |
| `?` printed in the log | Unknown G-code line — most senders forward it but mark the response |
| Coordinates outside workspace | Source file's origin doesn't match your machine's |

## What the queue computes on raw G-code

At enqueue time the queue counts the **executable lines** (for the
progress bar and the resume checkpoint) and scans the program for
tool-change boundaries to plan guided pauses against the profile. It
does **not** compute a bounding box or a time estimate, and it won't
catch dialect mismatches — it doesn't simulate the firmware's
interpretation.

## Streaming model

Raw G-code uses the same OK-acknowledged streamer as generated jobs:

- one line at a time
- waits for `ok` before sending the next
- pause / resume / abort work as for any run
- if the stream stalls (no `ok` for 30 s), the run fails with an
  error the operator can act on (resume re-queues from the checkpoint)

## See also

- [`docs/hardware_streaming.md`](../docs/hardware_streaming.md)
- [`docs/api_reference.md`](../docs/api_reference.md) — Queue and Plotter control sections
- [Machine profiles](Machine-Profiles.md)
- [Print queue & resume](Print-Queue.md)
