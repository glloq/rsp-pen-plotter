# Klipper config snippets

The reference plotter build uses **Klipper** on an RP2040 (BTT SKR Pico).
These snippets cover the OmniPlot side of the equation — the things you
need to teach Klipper so OmniPlot's G-code works out of the box.

Klipper itself is unmodified. OmniPlot speaks standard G-code to it.

## Minimum CoreXY config

```ini
[mcu]
serial: /dev/serial/by-id/usb-Klipper_rp2040_<your-uid>

[printer]
kinematics: corexy
max_velocity: 250
max_accel: 3000

# X / Y
[stepper_x]
step_pin: gpio11
dir_pin: gpio10
enable_pin: !gpio12
microsteps: 16
rotation_distance: 40
endstop_pin: ^gpio4
position_endstop: 0
position_max: 420
homing_speed: 30

[stepper_y]
step_pin: gpio6
dir_pin: !gpio5
enable_pin: !gpio7
microsteps: 16
rotation_distance: 40
endstop_pin: ^gpio3
position_endstop: 0
position_max: 297
homing_speed: 30

# TMC2209 in StealthChop
[tmc2209 stepper_x]
uart_pin: gpio9
run_current: 0.6
stealthchop_threshold: 999999

[tmc2209 stepper_y]
uart_pin: gpio8
run_current: 0.6
stealthchop_threshold: 999999
```

## Pen lift servo

```ini
[servo pen]
pin: gpio29
minimum_pulse_width: 0.0005
maximum_pulse_width: 0.0025
initial_angle: 60

# Macros OmniPlot's profile expects
[gcode_macro PEN_UP]
gcode:
    SET_SERVO SERVO=pen ANGLE=60
    G4 P200

[gcode_macro PEN_DOWN]
gcode:
    SET_SERVO SERVO=pen ANGLE=20
    G4 P150
```

Then in the OmniPlot profile:

```yaml
pen:
  up_command: "PEN_UP"
  down_command: "PEN_DOWN"
  up_delay_ms: 0       # the macro already waits
  down_delay_ms: 0
```

## Pen carousel (4 slots)

```ini
[stepper_carousel]
step_pin: gpio14
dir_pin: gpio13
enable_pin: !gpio15
microsteps: 16
rotation_distance: 8
gear_ratio: 4:1        # belt or planetary
endstop_pin: ^gpio18
position_endstop: 0
position_min: -360
position_max: 360
homing_speed: 20

[gcode_macro PICK_PEN]
description: Rotate carousel to slot {SLOT} and pick the pen
gcode:
    {% set angle = (params.SLOT | int) * 90 %}
    MANUAL_STEPPER STEPPER=stepper_carousel MOVE={angle}
    G4 P300
    PEN_DOWN
```

In the OmniPlot profile, set the per-pen pickup as a tool-change macro
(see [`docs/tool_change_mechanisms.md`](../docs/tool_change_mechanisms.md)).

## Serial connection from OmniPlot

Klipper exposes a **virtual_serial** port. Make sure `klippy` runs with
`-a` pointing at a stable path, then set OmniPlot's *Plotter → Connect*
to that path (e.g. `/tmp/klippy_uds`) using the `unix-socket` terminator.

Alternatively, run Moonraker and proxy through its HTTP / WS API — but
the direct path is leaner.

## OmniPlot-friendly Klipper macros

```ini
[gcode_macro START_PLOT]
gcode:
    G28              ; home
    G90              ; absolute coordinates
    G21              ; millimetres
    PEN_UP

[gcode_macro END_PLOT]
gcode:
    PEN_UP
    G0 X0 Y0
    M84              ; disable motors
```

Reference these in the OmniPlot profile's `prologue` and `epilogue`
fields and they'll wrap every job.

## See also

- [Machine profiles](Machine-Profiles.md)
- [`docs/hardware_streaming.md`](../docs/hardware_streaming.md)
- [`docs/tool_change_mechanisms.md`](../docs/tool_change_mechanisms.md)
- Klipper docs: <https://www.klipper3d.org/>
