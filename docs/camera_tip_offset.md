# Camera-assisted pen-tip offset — design study

- **Status**: Phase 1 (manual offset) + Phase 2 (vision measurement, annotated preview, optional guided travel & pen-fetch) implemented · only the `aruco` detector deferred
- **Date**: 2026-06
- **Companion ADR**: [`adr/0005-camera-tip-offset.md`](adr/0005-camera-tip-offset.md)

> **Implementation note (Phase 2).** The shipped `dark_blob` detector uses
> **Pillow + NumPy**, not OpenCV — both are already dependencies, so the
> appliance needs nothing extra and the detector is unit-tested on synthetic
> frames with no camera. The `aruco` detector (printed fiducial, sub-pixel)
> remains future work behind the same `detector` field. Every measurement
> returns an **annotated preview** (the frame with the tip marked) for
> confirmation. **Guided travel** (`move_to_station`) and **automatic
> pen-fetch** (`fetch_pen`) are both implemented as *optional* flags on the
> measure call: with a connected plotter, `fetch_pen` loads the slot's pen via
> a tool-change swap and `move_to_station` drives the head to
> `station_position` before grabbing — otherwise the operator does these by
> hand.

> Goal: let OmniPlot register the **XY offset of each pen's tip** so that
> strokes drawn with different pens land on the same logical coordinate, and
> let a **camera at a fixed measurement station** measure that offset
> automatically instead of by trial-and-error.

This document is the engineering detail behind ADR 0005. It records the
current state, the chosen approach (a *dedicated measurement station*), the
data-model and pipeline changes, and a two-phase delivery plan that ships a
useful feature before any computer vision is written.

---

## 1. Why this is needed

When a plotter carries more than one pen — a rack, a carousel, a tool-changer
dock — each pen is held in a slightly different place. The body of a Sakura
Micron does not sit where the body of a brush pen sits, and even two identical
pens reseated in the gripper land microns apart. The result is **registration
error**: a layer drawn with pen B is shifted a fraction of a millimetre from
the layer drawn with pen A, so fine multi-colour work shows colour fringing at
edges that should meet.

The fix is a per-pen **XY offset** applied to that pen's strokes so every pen
draws against the same origin. Measuring it by hand (draw a cross with each
pen, eyeball the misalignment, type a correction, repeat) is slow and
imprecise. A camera that *sees* the tip can measure the offset to a fraction of
a millimetre in one pass.

---

## 2. Current state (what the code does today)

Grounding the study in the code as it stands on `main`:

### 2.1 A camera source already exists

`backend/pen_plotter/timelapse.py` already grabs JPEG frames from a generic
`stream_url` (a snapshot URL or an `multipart/x-mixed-replace` MJPEG stream —
typically a Pi Camera behind `mjpg-streamer`, or a USB webcam). The frame
grabber is injected (`JpegGrabber`), so **the same camera and the same grabber
can feed a vision pipeline** — no new hardware class, no second camera assumed.

### 2.2 The capability model already anticipates a sensor

`MachineCapabilities` (`backend/pen_plotter/domain/capability.py:235`) carries:

```python
has_pen_sensor: bool = False
has_sheet_loader: bool = False
max_pens_in_magazine: int = 1
```

A vision-based tip finder is a concrete implementation of "pen sensor", so the
flag has a natural home — though we will likely want a richer sub-model than a
bare bool (see §5.1).

### 2.3 The XY offset is documented but NOT implemented

This is the important gap. The wiki page
[`wiki/Per-Slot-Calibration.md`](../wiki/Per-Slot-Calibration.md) says:

> If different pens need different XY offsets … use the per-slot `xy_offset_mm`
> field in the profile. The generator translates that pen's strokes by the
> offset.

But the `PenSlot` model (`backend/pen_plotter/models.py:60`) has **no such
field**:

```python
class PenSlot(BaseModel):
    index: int
    name: str = ""
    color: str = "#000000"
    installed: bool = True
    position: Point | None = None        # magazine ENGAGEMENT point, not a draw offset
    pen_up_command: str | None = None
    pen_down_command: str | None = None
```

`PenSlot.position` is the point where the gripper engages the pen in the
magazine (`strategies.py:188`, `gcode.py:541`) — it is **not** a drawing
offset and is never added to stroke coordinates. So today there is no per-pen
stroke compensation at all; the wiki describes a feature that was never built.

**Phase 1 of this study closes that gap**, independently of any camera.

### 2.4 Where strokes get their coordinates

The single point where user-unit geometry becomes machine millimetres is the
per-polyline loop in `generate_gcode` (`backend/pen_plotter/core/gcode.py:613`):

```python
for polyline in layer.polylines:
    machine_points = [transform(px, py) for px, py in polyline]
    ...
```

`transform` is built by `_make_transform` (`gcode.py:203`) and maps the drawing
into the sheet/workspace region. The active pen for the layer is already
resolved a few lines above (`pen = pens.get(slot)`, `gcode.py:607`) and is
already used for per-slot pen-up/down overrides. **This is the natural and only
injection point for the XY offset.**

---

## 3. Goals and non-goals

**Goals**

- A real, persisted **per-pen XY offset** applied to that pen's strokes.
- A **dedicated measurement station**: a fixed point in the workspace where any
  pen can be presented to a camera and its tip located.
- Automatic computation of each pen's offset from a vision measurement, with a
  manual-entry fallback that works with no camera at all.
- No regression for single-pen or offset-unaware profiles (offset defaults to
  zero → byte-identical G-code).

**Non-goals (this study)**

- Z / contact-depth measurement (already partly covered by per-slot
  `pen_up_command` / `pen_down_command`; out of scope per the chosen offset
  type — XY only).
- Tip *width* / line-weight measurement.
- Closed-loop correction *during* a plot, or skew/rotation/scale calibration of
  the bed. We measure a static per-pen translation, nothing more.
- Carriage-mounted or fixed-overhead camera geometries — explicitly rejected in
  ADR 0005 in favour of the dedicated station.

---

## 4. Chosen approach — a dedicated measurement station

A small fixture mounted at a **known, fixed machine coordinate**
`station_position = (Xs, Ys)` inside (or just outside) the drawable workspace.
It carries:

- a **camera** pointed at the spot where a presented tip will sit, and
- a **fiducial reference** in the camera's field of view (a printed crosshair /
  ArUco marker / a machined witness mark) at a known offset from `station_position`.

The calibration cycle for one pen:

1. The pen is loaded (via the existing tool-change path) and the head travels to
   `station_position` — these are **machine coordinates**, so they bypass the
   drawing transform exactly like the magazine engagement points do today.
2. The camera grabs a frame (reusing `grab_jpeg`).
3. The vision step locates the tip centroid in pixels and the fiducial in
   pixels, and converts the tip→fiducial vector to millimetres using the
   station's known pixel scale.
4. That gives the tip's **actual** machine position. The difference between the
   actual position and the *reference pen's* actual position is the pen's
   `xy_offset_mm`.

### Why the station, not the alternatives

| Approach | Why it lost (per ADR 0005) |
|---|---|
| **Fixed overhead camera** | Must cover the whole bed at usable resolution; pixel→mm varies with lens distortion across the field; conflates measurement with the timelapse view. |
| **Carriage-mounted camera** | Adds mass + cabling to a CoreXY carriage tuned for speed; introduces a *second* camera→nozzle offset that itself needs calibrating. |
| **Dedicated station** ✅ | Measurement is local to one small, well-lit, distortion-controlled region; pixel→mm is a single fixed scalar; fully decoupled from drawing and from the timelapse camera role; the head already knows how to travel to a machine coordinate and present a pen there. |

The station is **relative**: we calibrate every pen against a chosen reference
pen (slot 1 by default), so the absolute station-to-bed registration cancels
out. Only the *differences* between pens matter for stroke alignment, and those
are what we apply.

---

## 5. Data-model changes

### 5.1 `PenSlot` — the offset field

Add the field the wiki already promises:

```python
class PenSlot(BaseModel):
    ...
    # XY translation (machine mm) added to every stroke drawn with this pen,
    # compensating for where this pen's tip sits relative to the reference pen.
    # Defaults to (0, 0) so offset-unaware profiles emit identical G-code.
    xy_offset_mm: Point = Field(default_factory=lambda: Point(x=0.0, y=0.0))
    # Provenance, so the UI can show "measured 2026-06-17" vs "typed by hand"
    # and re-measurement can be prompted when a pen is reseated.
    offset_source: Literal["manual", "vision", "unset"] = "unset"
```

`Point` already exists (`models.py:53`). Defaulting to zero is what preserves
the golden-G-code tests.

### 5.2 Profile-level station + camera config

A new optional block on `MachineProfile` (kept optional so every bundled
profile loads unchanged):

```yaml
tip_calibration:
  camera_url: "http://localhost:8080/?action=snapshot"  # reuse timelapse source
  station_position: { x: 20.0, y: 400.0 }   # machine mm; where the pen is presented
  reference_slot: 1                          # offsets are measured relative to this pen
  mm_per_pixel: 0.05                         # station pixel scale (calibrated once)
  detector: "dark_blob"                      # | "aruco" — see §6
```

Modelled as a `TipCalibrationConfig` Pydantic model, referenced from
`MachineProfile`. The `has_pen_sensor` capability bool becomes "true when
`tip_calibration` is present"; we may later promote it to a small sub-model, but
the bool stays valid for back-compat.

---

## 6. Vision pipeline

Reuses `timelapse.grab_jpeg` for frame acquisition. The new module
(`backend/pen_plotter/vision/tip_detect.py`, suggested) is pure and injectable
like the timelapse grabber/assembler, so it is unit-testable against saved
fixture frames with **no camera and no plotter**.

Two detector strategies behind one interface:

- **`dark_blob`** (default, zero printed targets): the station has a flat, evenly
  lit, light background. The pen tip is the darkest compact blob in a region of
  interest. Threshold → largest contour → centroid. The fiducial is a machined
  witness mark at a fixed pixel location (or the ROI centre). Robust for a
  controlled, fixed-lighting station; this is why the station beats an overhead
  view.
- **`aruco`** (optional, higher precision): a printed ArUco/AprilTag at the
  station gives a sub-pixel, distortion-corrected reference frame; the tip
  centroid is then expressed in the marker's coordinate system.

OpenCV (`opencv-python-headless`) is the natural dependency. It is **optional**:
the import is lazy and guarded so a Pi without it still runs everything else,
and the manual-offset path (Phase 1) needs no vision dependency at all.

Detector contract (sketch):

```python
@dataclass
class TipMeasurement:
    found: bool
    tip_px: tuple[float, float] | None      # centroid in pixels
    tip_mm: tuple[float, float] | None      # station-frame mm (after mm_per_pixel)
    confidence: float                        # 0..1, for UI gating
    annotated_jpeg: bytes | None             # frame with overlay, for operator review

def detect_tip(frame: bytes, cfg: TipCalibrationConfig) -> TipMeasurement: ...
```

Returning the annotated frame lets the operator confirm the right blob was
picked before the offset is saved — the same "show, then commit" pattern the
host-swap editor preview uses.

---

## 7. Calibration flow

```
For the reference pen (slot N = reference_slot):
  load pen N → travel to station_position → grab frame → detect_tip
  → record tip_mm[N]   (this pen's offset is 0 by definition)

For each other installed pen P:
  load pen P → travel to station_position → grab frame → detect_tip
  → offset[P] = tip_mm[P] - tip_mm[reference_slot]
  → persist PenSlot.xy_offset_mm = offset[P], offset_source = "vision"
```

Each step routes through the **existing tool-change orchestrator** to fetch the
pen, and reuses `pen_change_point` / machine-coordinate travel that the carousel
and load-pause paths already emit. Low confidence or `found == False` aborts the
step and surfaces the annotated frame for manual entry instead of saving a bad
offset.

---

## 8. Applying the offset (G-code)

The only change in the hot path is at `gcode.py:613`. The active pen is already
resolved (`pen = pens.get(slot)`), so:

```python
ox, oy = (pen.xy_offset_mm.x, pen.xy_offset_mm.y) if pen else (0.0, 0.0)
for polyline in layer.polylines:
    machine_points = [(mx + ox, my + oy) for mx, my in (transform(px, py) for px, py in polyline)]
    ...
```

Notes:

- The offset is added **after** `transform`, in machine mm — it is a pure
  post-translation of drawn strokes.
- It is applied **only to drawing strokes**, never to magazine engagement,
  park, or pen-change positions (those are physical machine points and must not
  move).
- When every pen's offset is zero (the default), the expression collapses to
  today's behaviour, so the golden-G-code and simulator tests stay green. New
  golden cases cover a non-zero offset.

### Preflight interaction

`_exceeds_workspace` (`gcode.py:250`) and `preflight.py` check bounds against
the transformed drawing. A non-zero offset can push a pen's strokes past the
edge, so the bounds check must be evaluated **per pen with its offset applied**
(take the union, or the worst-case max offset). This is the one non-trivial
ripple beyond the one-line injection and must land in the same change so the
out-of-bounds warning stays honest.

---

## 9. API surface (sketch)

- `GET  /plotter/tip-calibration` — station config + current per-slot offsets.
- `POST /plotter/tip-calibration/measure` `{ slot }` — run one measurement;
  returns `TipMeasurement` (incl. annotated frame) **without** persisting.
- `POST /plotter/tip-calibration/commit` `{ slot, xy_offset_mm, source }` —
  persist an offset (manual or accepted-from-vision).
- `POST /plotter/tip-calibration/run-all` — guided sequence over installed pens.

Every measure/commit is an operator-visible action → write it to the **audit
trail** (`GET /audit`), consistent with how slot tests, connect, run and home
are already logged.

---

## 10. Frontend (sketch)

Extend the existing magazine / per-slot calibration UI (the `MagazineView.vue`
slot grid already shows a calibration badge per slot — roadmap C.4). Per slot:

- show current `xy_offset_mm` and its source badge (measured / manual / unset);
- a **Measure** button (enabled only when `tip_calibration` is configured and
  the plotter is connected) that calls `/measure`, shows the annotated frame and
  the proposed offset, and lets the operator **Accept** (→ `/commit`) or edit by
  hand;
- a **Calibrate all** action for the guided sequence.

---

## 11. Delivery plan

**Phase 1 — manual offset (no vision).** ✅ **Implemented.** Adds
`PenSlot.xy_offset_mm` + `offset_source`, the opt-in `MachineProfile.
apply_pen_offsets` switch, the offset application at `gcode.py` (a pure
post-`transform` translation, drawing strokes only), the offset-aware
workspace bounds check (`_pen_offset_envelope`), manual entry + an opt-in
toggle in the magazine UI (`MagazineEditor.vue`), and tests
(`backend/tests/test_pen_offset.py`, `MagazineEditor.test.ts`). Off by default
so existing profiles emit byte-identical G-code. This closes the wiki gap
(§2.3) and is useful on any multi-pen machine with zero camera.

**Phase 2 — vision automation.** ✅ **Implemented.** `TipCalibrationConfig` on
the profile; `vision/tip_detect.py` (`dark_blob` detector via Pillow+NumPy,
`offset_between`, and a `TipCalibrator` session); the measure/status/reset API
(`api/tip_calibration.py`); the UI station config + per-slot **Measure** flow
that writes `offset_source: "vision"`; tests
(`backend/tests/test_tip_calibration.py`, `MagazineEditor.test.ts`). Built
entirely on Phase 1's persisted field, so it is additive.

**Phase 2b — guided travel.** ✅ **Implemented (optional).** The measure call
takes `move_to_station` + `station_position` + `profile_name`; when set it
drives the head to the station via `controller.goto` before grabbing (409 if
disconnected, 422 if under-specified). The magazine UI exposes a station X/Y +
an auto-move toggle (enabled once a station position is set).

**Phase 2c — automatic pen-fetch.** ✅ **Implemented (optional).** The measure
call takes `fetch_pen`; when set it loads the slot's pen via the existing
tool-change orchestrator (`ToolChangeOrchestrator.plan` → swap commands,
streamed with their host-side dwells) before any travel. Host-macro / firmware
magazines fetch automatically; a *manual* profile returns 409 ("load by hand").
The magazine UI exposes a "Load pen from magazine" toggle. Order per measure:
**fetch → travel → grab**.

**Annotated preview.** ✅ **Implemented.** Every measurement returns the frame
as a JPEG data URL with the detected tip marked (or the plain frame when
nothing was found, so framing/lighting can be checked). The magazine UI shows
it under the slot so the operator confirms the right blob was picked.

**Still deferred.** Only the `aruco` detector (printed fiducial, sub-pixel),
which needs OpenCV — additive behind the existing `detector` field.

This ordering means the camera work was never on the critical path for the
registration fix itself.

---

## 12. Open questions / risks

- **Lighting & background at the station.** `dark_blob` robustness depends on a
  controlled, evenly lit, high-contrast station. If that can't be guaranteed,
  the `aruco` detector (printed target) is the fallback and should arguably be
  the default.
- **`mm_per_pixel` calibration.** The station scale itself needs a one-time
  calibration (present a feature of known size, or two presented points a known
  distance apart). Worth a small dedicated routine.
- **Tip-down vs tip-up presentation.** Should the pen be lowered to contact a
  surface (risking ink/marks) or measured pen-up at a known height? Pen-up at a
  fixed height avoids marking the station but assumes the tip is on the optical
  axis; to be validated on hardware.
- **Repeatability of the magazine.** If reseating a pen moves it by more than
  the achievable measurement precision, the offset is only as good as the last
  seating — hence `offset_source`/timestamp so the UI can prompt re-measurement.
- **Capability shape.** Whether `has_pen_sensor: bool` is enough or should
  become a sub-model is deferred to implementation; the bool stays back-compat
  either way.

---

## 13. References

- ADR: [`adr/0005-camera-tip-offset.md`](adr/0005-camera-tip-offset.md)
- Existing camera I/O: `backend/pen_plotter/timelapse.py`
- Capability model: `backend/pen_plotter/domain/capability.py`
- Pen model + injection point: `backend/pen_plotter/models.py:60`,
  `backend/pen_plotter/core/gcode.py:613`
- Tool-change mechanisms: [`tool_change_mechanisms.md`](tool_change_mechanisms.md)
- Per-slot calibration (the gap this closes): [`../wiki/Per-Slot-Calibration.md`](../wiki/Per-Slot-Calibration.md)
