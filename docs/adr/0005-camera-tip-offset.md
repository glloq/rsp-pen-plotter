# 0005 — Camera-assisted per-pen XY tip offset via a dedicated station

- **Status**: accepted (Phase 1 + Phase 2 + optional guided travel & pen-fetch implemented)
- **Date**: 2026-06

> Phase 1 (manual per-pen XY offset + opt-in switch), Phase 2 (camera
> measurement at a dedicated station), and the optional motion helpers —
> guided head-travel (`move_to_station`) and automatic pen-fetch
> (`fetch_pen`) — have all landed. The shipped detector uses Pillow+NumPy
> rather than OpenCV (see the implementation note in the design doc); the
> `aruco` detector and a returned annotated frame remain deferred. Engineering
> detail and delivery split live in
> [`../camera_tip_offset.md`](../camera_tip_offset.md).

## Context

Multi-pen plotters (rack, carousel, tool-changer dock) hold each pen in a
slightly different place, so layers drawn with different pens are shifted a
fraction of a millimetre from one another — visible as colour fringing where
edges should meet. The fix is a per-pen **XY offset** added to that pen's
strokes so all pens draw against one logical origin.

Two facts shape the decision:

1. **The offset is documented but does not exist.**
   [`wiki/Per-Slot-Calibration.md`](../../wiki/Per-Slot-Calibration.md) tells
   operators to set a per-slot `xy_offset_mm` "and the generator translates
   that pen's strokes by the offset" — but `PenSlot`
   (`backend/pen_plotter/models.py:60`) has no such field and nothing in
   `gcode.py` applies one. The wiki describes a phantom feature.
2. **A camera is already in the stack.** `timelapse.py` grabs frames from a
   generic MJPEG/snapshot URL with an injectable grabber, and
   `MachineCapabilities` already carries a `has_pen_sensor` flag. Measuring the
   offset by eye is slow and imprecise; a camera that *sees* the tip can
   measure it to a fraction of a millimetre.

We therefore need to decide (a) that per-pen XY offset becomes a real,
applied, persisted quantity, and (b) **how the camera observes the tip** — the
choice that forecloses the most alternatives and crosses the most module
boundaries, so it earns an ADR.

Options for the camera geometry:

1. **Fixed overhead camera** (e.g. the timelapse camera) watching the whole
   bed. One camera, no extra travel. But it must resolve the whole workspace at
   useful precision, lens distortion varies across the field, the pixel→mm map
   is position-dependent, and it overloads the timelapse camera with a second,
   conflicting role.
2. **Carriage-mounted camera** looking down, driven over a fixed target.
   Sub-millimetre and self-locating. But it adds mass and cabling to a CoreXY
   carriage tuned for speed, and introduces a *second* camera→tool offset that
   itself must be calibrated — calibrating the calibrator.
3. **Dedicated measurement station**: a small camera + fiducial fixture at a
   known machine coordinate. Each pen is presented to it after loading. Local,
   well-lit, distortion-controlled region; a single fixed pixel→mm scalar;
   fully decoupled from drawing and from the timelapse role.

## Decision

Adopt option 3 — a **dedicated measurement station** — and make per-pen
**XY offset** a first-class, applied quantity.

- Add `xy_offset_mm: Point` (default `(0,0)`) and an `offset_source` provenance
  field to `PenSlot`. Default-zero keeps offset-unaware profiles emitting
  byte-identical G-code.
- Apply the offset as a pure post-`transform` translation at the single
  stroke-emission site (`gcode.py:613`), on drawing strokes only — never on
  magazine, park, or pen-change positions. Bounds/preflight checks are
  evaluated per pen with its offset applied.
- Add an optional `tip_calibration` block to `MachineProfile`
  (`camera_url`, `station_position`, `reference_slot`, `mm_per_pixel`,
  `detector`). Offsets are measured **relative to a reference pen**, so the
  absolute station-to-bed registration cancels out.
- Ship in two phases: **Phase 1** is the manual offset (field + injection +
  preflight + UI), useful with no camera and closing the wiki gap; **Phase 2**
  adds the vision pipeline (lazy/optional OpenCV, injectable detector, guided
  measure→accept flow) on top of the same persisted field.

The vision dependency is optional and lazily imported so a Pi without OpenCV
still runs everything else, and Phase 1 needs no vision dependency at all.

## Consequences

### Positive

- **Closes a real registration error** that limits fine multi-colour work, and
  makes the wiki honest.
- **Single injection point, minimal blast radius.** The offset is one
  post-translation at `gcode.py:613`; default-zero preserves the golden-G-code
  and simulator tests.
- **Decoupled measurement.** A small fixed station has controlled lighting and
  a single pixel→mm scalar — far simpler and more precise than an overhead view,
  and it never competes with the timelapse camera.
- **Reuses what exists.** Frame grabbing reuses `timelapse.grab_jpeg`; pen
  presentation reuses the tool-change orchestrator and machine-coordinate
  travel; the capability flag and the magazine calibration UI already have a
  place for it.
- **Phasable.** The camera work is never on the critical path for the fix
  itself — Phase 1 delivers value alone.

### Negative

- **A physical fixture to build and place.** The station is extra hardware the
  operator must mount at a known coordinate and keep clear of the drawing area.
- **Station calibration of its own.** `mm_per_pixel` and the fiducial position
  need a one-time calibration routine.
- **Lighting sensitivity.** The default `dark_blob` detector needs an evenly
  lit, high-contrast station; poor lighting forces the printed-target (`aruco`)
  detector instead.
- **Relative, not absolute.** We measure pen-to-reference differences, not
  absolute bed registration — sufficient for stroke alignment but not a bed
  survey.
- **New optional dependency** (`opencv-python-headless`) for Phase 2, guarded
  so it stays optional.

## What this rules out for now

- **Z / contact-depth and tip-width measurement** — out of scope; Z is already
  partly served by per-slot `pen_up_command` / `pen_down_command`.
- **Closed-loop correction during a plot** and **bed skew/rotation/scale
  calibration** — we measure a static per-pen translation only.
- **Overhead and carriage-mounted camera geometries** — rejected above; could
  be revisited as alternate `detector` backends if the station proves limiting.

## Alternatives we still reject

A **fixed overhead camera** seems cheaper (reuse the timelapse view) but trades
the whole problem for a harder one: full-bed resolution, position-dependent
distortion, and a camera doing two jobs at once. A **carriage-mounted camera**
is the most precise in principle but pays for it in carriage mass, cabling, and
a second offset to calibrate — on a speed-tuned CoreXY that is the wrong
trade. The dedicated station keeps the measurement problem small and local.
