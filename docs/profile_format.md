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
| `origin` | `"top_left"` \| `"bottom_left"` \| `"center"` | Coordinate origin; controls Y direction |
| `gcode_dialect` | `"grbl"` \| `"marlin"` \| `"klipper"` \| `"ebb"` \| `"custom"` | Selects the output generator |
| `pen_up_command` | string | Raw command emitted to lift the pen |
| `pen_down_command` | string | Raw command emitted to lower the pen |
| `tool_change_method` | `"manual_pause"` \| `"carousel"` \| `"rack"` \| `"none"` | How pen changes happen |
| `tool_change_command` | string | Command emitted at a tool change |
| `drawing_speed_mm_s` | float | Default drawing feed (mm/s) |
| `travel_speed_mm_s` | float | Pen-up travel feed (mm/s) |
| `acceleration_mm_s2` | float | Acceleration limit (mm/s²) |
| `pen_slot_count` | int | Number of physical pen slots |
| `supports_arcs` | bool (default `false`) | Enable G2/G3 arc fitting |
| `arc_tolerance_mm` | float (default `0.1`) | Max deviation when fitting arcs |
| `ebb` | `EbbConfig` \| null | Required only when `gcode_dialect: "ebb"` |

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
