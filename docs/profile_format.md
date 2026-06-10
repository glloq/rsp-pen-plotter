# Machine Profile Format

A machine profile is a YAML file describing one target plotter. All
machine-specific behavior lives here, not in code, so supporting a new plotter
is a YAML file with no code changes. Profiles are validated against the
`MachineProfile` Pydantic model in `backend/pen_plotter/models.py`.

Bundled profiles live in `backend/pen_plotter/profiles/`; user-imported
profiles are stored under `OMNIPLOT_PROFILES_DIR` and override bundled ones with
the same name.

## Fields

| Field | Type | Notes |
| --- | --- | --- |
| `name` | string | Unique display name; used to look the profile up |
| `units` | `"mm"` \| `"inch"` | Profile measurement units |
| `workspace` | object | `{ x_min, y_min, x_max, y_max }` drawable bounds |
| `origin` | `"top_left"` \| `"bottom_left"` | Coordinate origin; controls Y direction. Legacy `"center"` is auto-migrated to `"bottom_left"` by a validator (it was only ever treated as a Y-flip), so old profiles keep loading |
| `gcode_dialect` | `"grbl"` \| `"marlin"` \| `"klipper"` \| `"ebb"` \| `"custom"` | Selects the output generator |
| `pen_up_command` | string | Raw command emitted to lift the pen |
| `pen_down_command` | string | Raw command emitted to lower the pen |
| `tool_change_method` | `"manual_pause"` \| `"carousel"` \| `"rack"` \| `"none"` | How pen changes happen |
| `tool_change_command` | string | Command emitted at a tool change |
| `drawing_speed_mm_s` | float | Default drawing feed (mm/s) |
| `travel_speed_mm_s` | float | Pen-up travel feed (mm/s) |
| `acceleration_mm_s2` | float | Acceleration limit (mm/s²) |
| `pen_lift_time_ms` | float (default `0.0`) | Time for one pen lift or drop to physically settle. Two transitions happen per drawn polyline, so this feeds the preflight time estimate; `0` = instant. Typical SG90/EBB servos sit around 150–250 ms |
| `pen_slot_count` | int | Number of physical pen slots |
| `pens` | list of `PenSlot` \| null | The magazine (see below). When omitted, one default slot per `pen_slot_count` is synthesized |
| `pen_change_position` | `{ x, y }` \| null | Machine-coordinate park point for *manual* pen swaps / magazine load pauses, so the head clears the drawing. `null` falls back to the workspace home corner (`x_min` / `y_min`); carousel and rack profiles ignore it |
| `supports_arcs` | bool (default `false`) | Enable G2/G3 arc fitting |
| `arc_tolerance_mm` | float (default `0.1`) | Max deviation when fitting arcs |
| `ebb` | `EbbConfig` \| null | Required only when `gcode_dialect: "ebb"` |
| `capabilities` | `MachineCapabilities` \| null | **v0.2 Capability Model** (see below). Optional; derived from `tool_change_method` when omitted. |

### `PenSlot`

One entry per magazine position:

| Field | Type | Notes |
| --- | --- | --- |
| `index` | int | Slot number, referenced by layer assignments |
| `name` | string (default `""`) | Operator label |
| `color` | string (default `"#000000"`) | Ink colour, shown in the palette |
| `installed` | bool (default `true`) | Whether a pen currently sits in the slot |
| `position` | `{ x, y }` \| null | Slot coordinates for carousel / rack pickups |
| `pen_up_command` | string \| null | Per-slot calibration: overrides the profile's pen-up command (e.g. a different servo depth) |
| `pen_down_command` | string \| null | Per-slot calibration: overrides the profile's pen-down command |

### `MachineCapabilities` (v0.2, roadmap A.5)

Introduced as the v0.2 home for tool-change behavior, future sensors,
and any other capability flag. The block is **optional in YAML** — if
absent, the backend derives a sensible default from
`tool_change_method` + `pen_slot_count`. Existing profiles keep working
unchanged.

```yaml
capabilities:
  tool_change:
    mode: manual           # firmware | host_macro | manual | single_pen
    command_source: operator  # machine | host | operator
    recovery_policy: pause_and_prompt  # abort | pause_and_prompt | skip_layer
    manual_prompt:
      title: "Change pen"
      body: "Insert pen {color} into the holder, then press Resume."
      timeout_s: null
    host_macro:
      - send: "M6 T{slot}"
        wait_ms: 500
      - send: "G4 P0"
  has_pen_sensor: false
  has_sheet_loader: false
  max_pens_in_magazine: 1
```

Legacy ↔ v0.2 mapping (applied automatically when `capabilities` is
omitted):

| Legacy `tool_change_method` | Derived `mode`     | Derived `command_source` |
|-----------------------------|--------------------|--------------------------|
| `manual_pause`              | `manual`           | `operator`               |
| `carousel`                  | `firmware`         | `machine`                |
| `rack`                      | `host_macro`       | `host`                   |
| `none`                      | `single_pen`       | `machine`                |

When both `tool_change_method` and an explicit `capabilities` block are
present, **`capabilities` wins** — `tool_change_method` is preserved
only for backwards compatibility and will be removed in a future major
version (deprecation window per `docs/contract_architecture.md`).

The `ToolChangeOrchestrator` (roadmap B.2) routes through
`capabilities.tool_change` and ignores the legacy field.


### `EbbConfig` (EiBotBoard / AxiDraw-class)

| Field | Default | Units |
| --- | --- | --- |
| `steps_per_mm` | `80.0` | Motor steps per millimeter of Cartesian travel |
| `servo_up` | `16000` | Pen-up servo pulse width, in 83.3 ns units (EBB `SP`) |
| `servo_down` | `12000` | Pen-down servo pulse width, in 83.3 ns units (EBB `SP`) |
| `servo_rate` | `400` | Servo travel rate, in EBB `SC` units |
| `serial_terminator` | `"cr"` | Line terminator the board expects (EBB uses CR) |

The two AxiDraw motors form an H-bot, so a Cartesian move is emitted as mixed
motor steps (see `core/ebb.py`).

## Dialect routing

`POST /generate` selects the generator from `gcode_dialect`:

- `ebb` → `core/ebb.py` emits native EiBotBoard commands (`SM`/`SP`/`EM`/`SC`).
- everything else → `core/gcode.py` renders the per-command Jinja2 templates in
  `backend/pen_plotter/templates/`.

## Examples

### `custom_plotter.yaml` — DIY CoreXY A3 (GRBL)

```yaml
name: "Custom CoreXY A3"
units: "mm"
workspace: { x_min: 0.0, y_min: 0.0, x_max: 300.0, y_max: 420.0 }
origin: "bottom_left"
gcode_dialect: "grbl"
pen_up_command: "M280 P0 S40"     # SG90 servo on a PCA9685 (M280 angle)
pen_down_command: "M280 P0 S90"
tool_change_method: "manual_pause"
tool_change_command: "M0"
drawing_speed_mm_s: 60.0
travel_speed_mm_s: 120.0
acceleration_mm_s2: 1500.0
pen_lift_time_ms: 150.0           # SG90 hobby servo settling time
pen_slot_count: 6
supports_arcs: true               # GRBL supports G2/G3
arc_tolerance_mm: 0.1
```

### `axidraw_v3.yaml` — AxiDraw V3 (EBB)

```yaml
name: "AxiDraw V3"
units: "mm"
workspace: { x_min: 0.0, y_min: 0.0, x_max: 300.0, y_max: 218.0 }
origin: "top_left"
gcode_dialect: "ebb"
pen_up_command: "SP,1"
pen_down_command: "SP,0"
tool_change_method: "manual_pause"
tool_change_command: "M0"
drawing_speed_mm_s: 50.0
travel_speed_mm_s: 130.0
acceleration_mm_s2: 1000.0
pen_lift_time_ms: 250.0    # AxiDraw EBB servo ~250 ms per lift/drop
pen_slot_count: 1
ebb:
  steps_per_mm: 80.0
  servo_up: 16000
  servo_down: 12000
  servo_rate: 400
  serial_terminator: "cr"
```

## Import / export

- `GET /profiles/{name}/export` returns a profile as YAML.
- `POST /profiles/import` validates a YAML profile and stores it; invalid YAML or
  schema violations return `400`.
