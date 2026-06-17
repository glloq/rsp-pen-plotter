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
centre the tip exactly above 0,0), turn on **per-pen tip offsets** in the
Couleurs tab and give each slot an `xy_offset_mm`. The generator then
translates that pen's strokes by the offset so layers drawn with
different pens register against one origin.

The feature is **opt-in**: it's off by default (`apply_pen_offsets:
false`), so existing profiles produce identical G-code until you enable
it. Measure each offset relative to a reference pen — leave that pen at
`0` and align the others to it.

## Measuring offsets with a camera

You can also **measure** offsets instead of typing them. Configure a
`tip_calibration` block on the profile (a camera URL + `mm_per_pixel` +
a reference slot) — in the Couleurs tab, tick *Measure with a camera
station*. Then, with offsets enabled, each slot grows a **Measure**
button:

1. Present the **reference** pen at the station, click *Measure*.
2. Present each other pen and click *Measure* — its `xy_offset_mm` is
   filled in automatically (tagged as camera-measured) as the difference
   from the reference.

The detector finds the dark pen tip against the light station
background, so the station wants even lighting and good contrast. After
each measurement a **preview image** appears under the slot with the
detected tip marked, so you can confirm the right point was picked before
trusting the offset. *Reset measurements* starts a fresh run.

With a connected plotter you can also automate the motion:

- *Load pen from magazine before measuring* fetches the slot's pen via
  the normal tool-change swap (host-driven / firmware magazines; a manual
  magazine still needs a hand swap).
- Set a **station X/Y** and tick *Move head to station before measuring*
  to drive the head there automatically.

With both on, each *Measure* does **fetch → travel → grab** in one click.

> Design notes:
> [`docs/adr/0005-camera-tip-offset.md`](../docs/adr/0005-camera-tip-offset.md)
> and [`docs/camera_tip_offset.md`](../docs/camera_tip_offset.md).

## Logging

Every calibration test goes into the audit trail
(`GET /audit`) — connect, run, slot test. Useful when you have several
people tuning the same machine.

## See also

- [Pen magazine](Pen-Magazine.md)
- [Machine profiles](Machine-Profiles.md)
- [`docs/tool_change_mechanisms.md`](../docs/tool_change_mechanisms.md)
