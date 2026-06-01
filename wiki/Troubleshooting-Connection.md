# Troubleshooting — connection

The *Plotter → Connect* button hangs, errors, or the carriage moves wrong.

## "Port not found" / no devices in the dropdown

1. Check the cable. USB-A → USB-B printer cables are *not* all data-capable;
   some are power-only.
2. Make sure the MCU is powered. RP2040 boards can be USB-powered; some
   plotter controllers need their main 24 V input to be live before USB
   enumerates.
3. List the serial devices on the Pi:
   ```bash
   ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
   ```
   Klipper RP2040 boards typically appear at `/dev/ttyACM0`; CH340-based
   boards at `/dev/ttyUSB0`.
4. If you see the device file but the dropdown is empty, the OmniPlot
   process can't read it — back to *Operation not permitted* in
   [Troubleshooting — installer](Troubleshooting-Install.md).

## "Permission denied" on the chosen port

```bash
groups
# must include "dialout"
sudo usermod -aG dialout $USER
# log out and back in
```

## Connects, then disconnects within a second

The baud rate or line terminator is wrong. Symptoms:

- *"unexpected response: ?"* in the audit log
- the plotter never replies `ok`

Common combos:

| Firmware | Baud | Terminator |
| --- | --- | --- |
| Marlin | 115200 | LF |
| GRBL | 115200 | LF |
| Klipper (direct serial) | 250000 | LF |
| EBB / AxiDraw | 9600 | CRLF |

Set the right one in the *Connect* modal and retry.

## Connects but homing crashes the carriage

The profile's `position_max` is bigger than the physical workspace.
Edit the profile (Settings → Profiles), reduce `workspace.width_mm` and
`workspace.height_mm`, then re-home.

## Jog moves the wrong direction

You wired the stepper backwards. Two fixes:

- swap one motor coil pair, **or**
- invert the axis in the firmware (`!step_pin` in Klipper) — this is
  the OmniPlot-friendly answer because nothing about OmniPlot needs to
  change

CoreXY surprises: inverting just X or just Y produces diagonal motion.
You probably need to swap the motor cables instead.

## Pen never lifts (or never lowers)

The `up_command` / `down_command` in your profile doesn't match what
the firmware expects. See [Per-slot calibration](Per-Slot-Calibration.md)
for the calibration workflow, and check that:

- Marlin / GRBL servo plotters usually want `M3 S0` (down) and `M5`
  (up)
- Klipper plotters usually call a `PEN_UP` / `PEN_DOWN` macro
- EBB controllers use `SP,1` (up) and `SP,0` (down)

## Stream stalls partway through a job

The streamer waits for `ok` after every line. If the firmware stops
acking, OmniPlot eventually shows a *"stream timeout"* toast and the
queue marks the run as `failed`.

Causes worth checking, in order:

1. USB cable wiggled loose (or a USB hub power dropping out)
2. SD card on the MCU is full (logs filling it up)
3. firmware threw an error and is waiting for human attention (some
   firmwares print the error then go silent)
4. you sent a comment or macro the firmware rejects — check the audit
   log for the last line sent

## See also

- [Install on a Raspberry Pi](Install-on-a-Raspberry-Pi.md)
- [Machine profiles](Machine-Profiles.md)
- [Klipper config snippets](Klipper-Config.md)
- [`docs/hardware_streaming.md`](../docs/hardware_streaming.md)
