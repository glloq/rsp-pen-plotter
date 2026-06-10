# Machine profiles

A machine profile tells OmniPlot how *your* plotter wants to be driven —
the G-code dialect, the workspace bounds, the pen-up / pen-down command,
the pen magazine layout, the default speeds.

Adding a new plotter to OmniPlot is one YAML file, no code.

## Where they live

- bundled profiles → `backend/pen_plotter/profiles/*.yaml`
- imported / user profiles → `OMNIPLOT_PROFILES_DIR` (platform user dir
  by default)

The bundled ones are read-only; the *Profile editor* in the UI saves
into the user dir.

## Anatomy

The schema is **flat** — speeds, pen commands and tool-change settings
sit at the top level, not in nested blocks. A typical profile
(`my-axidraw.yaml`, adapted from the bundled `axidraw_v3.yaml`):

```yaml
name: "My AxiDraw V3"
units: "mm"                      # mm | inch
workspace:                       # drawable bounds, in profile units
  x_min: 0.0
  y_min: 0.0
  x_max: 300.0
  y_max: 218.0
origin: "top_left"               # top_left | bottom_left
gcode_dialect: "ebb"             # grbl | marlin | klipper | ebb | custom
pen_up_command: "SP,1"
pen_down_command: "SP,0"
tool_change_method: "manual_pause"   # manual_pause | carousel | rack | none
tool_change_command: "M0"            # required
drawing_speed_mm_s: 50.0
travel_speed_mm_s: 130.0
acceleration_mm_s2: 1000.0
pen_lift_time_ms: 250.0          # servo settle time per lift/drop; 0 = instant
pen_slot_count: 1
pens:                            # optional magazine; one PenSlot per entry
  - index: 0
    name: "Sakura Micron 005"
    color: "#111111"
    installed: true
    # position: { x: ..., y: ... }      # carousel/rack slot coordinates
    # pen_up_command: "SP,1,14000"      # per-slot calibration override
    # pen_down_command: "SP,0,11000"
# pen_change_position: { x: 0.0, y: 0.0 }  # park point for manual swaps
ebb:                             # only for gcode_dialect: ebb
  steps_per_mm: 80.0
  servo_up: 16000
  servo_down: 12000
  servo_rate: 400
  serial_terminator: "cr"
```

There is no `description` field — `name` is the only label, and it's
also the lookup key. When `pens` is omitted, one default slot per
`pen_slot_count` is synthesized.

A full reference, with every supported field, the validation rules and
example bundled profiles: [`docs/profile_format.md`](../docs/profile_format.md).

## Editing in the UI

Settings → *Profiles* → pick a profile → click *Duplicate to user*. The
*Profile editor* opens with every field exposed. Save commits to the user
directory; the editor's *Export YAML* button dumps the current state to
a downloadable file.

The editor validates against the same Pydantic model the backend uses, so
"saved" implies "loadable" — you can't ship a broken profile.

## Multi-dialect support

The same OmniPlot install can serve different machines simultaneously
(e.g. an EBB-based AxiDraw and a Klipper-based DIY CoreXY). The
generator picks the dialect from the placement's profile, not from a
global setting.

The active machine determines which available pens the editor offers
in the *Colours* / *Layers* steps.

## Per-slot calibration

The magazine is a list of slots. Each slot can override the global pen
up / pen down commands — useful when one pen needs a deeper servo
position. See [Per-slot calibration](Per-Slot-Calibration.md).

## EBB vs G-code

The EBB protocol (used by AxiDraw and clones) is not G-code. OmniPlot
ships a **native EBB generator** that targets the EBB command set
directly (`SM,…`, `SP,…`) instead of templating G-code. Pick
`gcode_dialect: ebb` and the generator path switches.

Template-based G-code generation is used for everything else; templates
live in `backend/pen_plotter/templates/`.

## See also

- [`docs/profile_format.md`](../docs/profile_format.md)
- [`docs/hardware_streaming.md`](../docs/hardware_streaming.md)
- [Per-slot calibration](Per-Slot-Calibration.md)
- [Pen magazine](Pen-Magazine.md)
