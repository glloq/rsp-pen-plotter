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

A minimal profile (`my-axidraw.yaml`):

```yaml
name: my-axidraw
description: AxiDraw v3 with 0.5 mm Sakura Micron
gcode_dialect: ebb              # ebb | marlin | grbl | klipper | custom

workspace:
  width_mm: 297
  height_mm: 210
  margin_mm: 10
  origin: top_left              # top_left | bottom_left

motion:
  travel_speed_mm_s: 80
  drawing_speed_mm_s: 30
  acceleration_mm_s2: 1500

pen:
  up_command: "SP,1"
  down_command: "SP,0"
  up_delay_ms: 250
  down_delay_ms: 150

pens:                            # the magazine
  slot_count: 1
  slots:
    - { id: 1, name: "Sakura Micron 005", colour: "#111" }
```

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
