# Per-slot calibration

Pens are not identical. A Sakura Micron 005 needs the servo to drop
further than a Stabilo 88 to make ink contact. OmniPlot lets you
override the pen-up / pen-down command **per magazine slot**.

## In the profile

The global `pen` block sets defaults; any slot can override:

```yaml
pen:
  up_command: "SP,1"
  down_command: "SP,0"
  up_delay_ms: 250
  down_delay_ms: 150

pens:
  slot_count: 4
  slots:
    - id: 1
      name: "Sakura 005"
      colour: "#111"
      # Sakura needs a deeper drop
      down_command: "SP,0,2400"
      down_delay_ms: 220
    - id: 2
      name: "Stabilo 88"
      colour: "#1f4cd2"
      # Default servo position works fine
    - id: 3
      name: "Brush pen"
      colour: "#000"
      # Brush is thicker — barely touch
      down_command: "SP,0,1600"
      up_command: "SP,1,1100"
```

The same overrides exist for `up_command`, `down_command`, `up_delay_ms`
and `down_delay_ms`.

## Calibrating

A typical session:

1. Settings → *Profiles* → your profile → *Edit*.
2. Scroll to the slot row, click *Test*.
3. The UI sends `home`, then a small jog into the magazine, picks the
   pen, lowers it, draws a 10 mm test line, lifts, returns the pen.
4. Check the test line:
   - **no ink at all** → drop the pen deeper (smaller value for servo
     PWM that means "more down" — depends on the firmware)
   - **scratches the paper / digs in** → raise the pen
   - **ink fades mid-line** → lengthen `down_delay_ms` so the servo
     fully settles before motion starts
5. Save the profile and run *Test* again.

## When per-slot calibration isn't enough

If different pens need different *speeds* (a brush at 80 mm/s smears,
a Micron at 80 mm/s is fine), set per-layer speed in the editor's
Expert mode. The per-layer override wins over the profile default and
applies regardless of slot.

If different pens need different XY offsets (the carousel doesn't
centre the tip exactly above 0,0), turn on **per-pen tip offsets** in
Settings → Cameras → Offset camera and give each slot an `xy_offset_mm`.
The generator then translates that pen's strokes by the offset so layers
drawn with different pens register against one origin.

The feature is **opt-in**: it's off by default (`apply_pen_offsets:
false`), so existing profiles produce identical G-code until you enable
it. Measure each offset relative to a reference pen — leave that pen at
`0` and align the others to it.

## Measuring offsets with a camera

Instead of typing offsets, OmniPlot can **measure** them with a camera at a
fixed station: present each pen, click *Measure*, and its `xy_offset_mm` is
filled in automatically relative to a reference pen. The station also supports a
detection zone (ROI), a Raspberry Pi **GPIO-driven light**, an **mm-per-pixel
assistant**, and hands-free **fetch → travel → grab** on a connected plotter.

> The **offset camera** is dedicated to this and is a different camera from
> the **timelapse camera** — both are configured (and both optional) under
> Settings → Cameras.

See the dedicated guide: **[Offset camera](Offset-Camera.md)**.

## Logging

Every calibration test goes into the audit trail
(`GET /audit`) — connect, run, slot test. Useful when you have several
people tuning the same machine.

## See also

- [Offset camera](Offset-Camera.md) — measure per-pen XY offsets automatically
- [Pen magazine](Pen-Magazine.md)
- [Machine profiles](Machine-Profiles.md)
- [`docs/tool_change_mechanisms.md`](../docs/tool_change_mechanisms.md)
