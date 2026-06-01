# Glossary

Terms used throughout OmniPlot, in roughly the order you'll meet them.

### Appliance
A self-contained install of OmniPlot on a single host (typically a
Raspberry Pi) that serves a web UI for a single plotter. The default
deployment shape.

### Bootstrap
The one-line `bash <(curl …) --service` install command. See
[Install on a Raspberry Pi](Install-on-a-Raspberry-Pi.md).

### Carousel
A rotating pen magazine where each slot holds a different pen and the
plotter mechanically picks one by rotating the carousel. Contrast with
*manual swap*, where the operator changes the pen by hand.

### CoreXY
A 2-motor parallel-kinematics design where the X and Y axes share both
motors. Compact, fast, harder to wire than Cartesian. The reference
plotter build uses CoreXY.

### Converter
A backend class that turns a specific MIME type into the SVG pivot.
One per format (`BitmapConverter`, `PdfConverter`, …). See
[`docs/converters.md`](../docs/converters.md).

### Dialect (G-code)
The flavour of G-code a particular firmware speaks. `marlin`, `grbl`,
`klipper`, `ebb` are the common ones. OmniPlot picks the dialect from
the active machine profile.

### EBB / EiBotBoard
The control board used by AxiDraw and clones. Speaks a proprietary
ASCII protocol (`SM,…`, `SP,…`) rather than G-code. OmniPlot ships a
native EBB generator for this dialect.

### Hershey font
Single-stroke font (each glyph is a polyline, not a filled outline).
Designed for plotters and engraving machines in the 1960s. Used by
OmniPlot's TXT, MD and DXF text converters.

### IR (GeometryIR)
An internal intermediate representation that captures geometry without
serialising to SVG. Optional, gated by `OMNIPLOT_IR_ENABLED=1`. Will
replace the SVG pivot for some pipeline stages in a future version;
write-only today.

### Klipper
The recommended motion-control firmware. Runs on a microcontroller
(RP2040 / STM32) and accepts G-code via USB. Distinguishing feature:
the planner runs on the host (the Pi), the MCU does step generation.

### Layer (OmniPlot)
A group of strokes that share a pen and a set of settings (algorithm,
speed, simplification, optimisation). Top-level `<g>` elements in the
SVG pivot.

### Magazine
The pen rack. See [Pen magazine](Pen-Magazine.md).

### MCU
Microcontroller unit. In OmniPlot, the chip that does real-time step
generation (RP2040 on the SKR Pico, ESP32 on FluidNC, etc.). Klipper
or FluidNC runs on it.

### Modal preamble
A small G-code header sent on resume after a pause / power-loss. Carries
the firmware's modal state (units, absolute/relative, last feed rate,
pen up/down) so the next line behaves the same as it would have during
the original stream.

### Pivot (SVG pivot)
The single normalised SVG representation every input converges on.
After the converter step, all formats look the same to the toolpath
generator. See [`docs/architecture.md`](../docs/architecture.md).

### Placement
A `(library file, position on sheet, layers, settings, variant)` tuple.
Edits in the editor modify a placement, not the underlying file.

### Plan
The full set of placements ready to plot. The output of *Generate*.

### Pre-flight
The set of checks run before plotting: bounds, drawing length, travel
length, estimated time, pen-change count, missing pen-slot detection.

### Profile (machine)
A YAML file describing one plotter — G-code dialect, workspace bounds,
pen lift, magazine, default speeds. See [Machine profiles](Machine-Profiles.md).

### Slot
One position in the pen magazine. Holds one pen.

### Swap (pen swap)
A pen change mid-plot. Can be automatic (carousel) or manual (operator
prompt).

### Variant
A saved alternative version of a placement. The Compare drawer renders
two variants side-by-side.

### vpype
The pen-plotter pre-processing toolkit OmniPlot leans on for layer
manipulation, line merging, simplification, sorting and SVG↔G-code
plumbing. <https://github.com/abey79/vpype>

### Workshop mode
A full-screen "run cockpit" UI surface. Hides the editor entirely and
shows large run-time controls and progress. Toggle from the header
button.
