# Raw G-code

You can drop a `.gcode`, `.nc` or `.tap` file straight onto OmniPlot. The
file bypasses the converter pipeline entirely — no SVG pivot, no toolpath
optimisation, no scaling. It goes to the queue exactly as you wrote it.

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
another for raw uploads — that's only done at generation time. If your
file uses `M3 S0` to lift the pen and your profile expects `M5`, you
need to translate manually or regenerate.

Common mismatches:

| Symptom | Cause |
| --- | --- |
| Pen never lifts | `M3` / `M5` vs servo `M280` mismatch |
| Pen always down | Same, but the lift command is silently rejected |
| `?` printed in the log | Unknown G-code line — most senders forward it but mark the response |
| Coordinates outside workspace | Source file's origin doesn't match your machine's |

## Pre-flight on raw G-code

The queue still computes basic stats on raw uploads:

- total line count
- bounding box (parsed from `G0`/`G1` lines)
- estimated drawing time (using the profile's default speeds, no
  acceleration model)

…but it won't catch dialect mismatches because it doesn't simulate the
firmware's interpretation.

## Streaming model

Raw G-code uses the same OK-acknowledged streamer as generated jobs:

- one line at a time
- waits for `ok` before sending the next
- pause / resume / abort buttons work
- if the stream stalls (no `ok` for 30 s), the job goes into the *error*
  state and the operator gets a toast

## The editor isn't useful for raw G-code

When you place a `.gcode` file there's no algorithm to pick and no layers
to assign — the *Edit* button is greyed out. Use *Place* and *Send* (or
*Queue*) directly.

## See also

- [`docs/hardware_streaming.md`](../docs/hardware_streaming.md)
- [Machine profiles](Machine-Profiles.md)
- [Print queue & resume](Print-Queue.md)
