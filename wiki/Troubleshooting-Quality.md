# Troubleshooting — plot quality

## Lines are wobbly / wavy

- **acceleration too high** — the firmware overshoots corners. Lower
  `max_accel` (Klipper / Marlin) by 25 % and try again.
- **belt tension uneven** — pluck each belt; the X and Y belts should
  give roughly the same musical note. Re-tension the loose one.
- **pen too soft against the carriage** — a brush-tip pen on a stiff
  spring scribbles. Use a less stiff spring or switch to a felt
  finger-tip mount.

## Lines drift over time

- **lost steps** — motor current too low. Bump `run_current` on the
  TMC2209 (Klipper) or microstep voltage (Marlin). Don't exceed the
  driver's rated current.
- **belt slipping on the pulley** — tighten the grub screw on the
  pulley.
- **paper moving** — the suction / clip is letting go. On a flatbed,
  use four corner clips minimum.

## Diagonal lines look stepped

- microstepping too coarse. Bump to 16× or 32× (Klipper handles 256×
  with TMC2209 in StealthChop).
- the drawing's `linesimplify` tolerance is too high. Drop it to
  0.05 mm or lower in the Expert layer panel.

## Pen skips / dry strokes

- **pen up too high during travel** — touchdown after a travel takes
  longer than `down_delay_ms` allows. Increase it by 100 ms.
- **drawing_speed_mm_s too fast** — felt tips at >50 mm/s often skip.
  Drop to 25–30 mm/s.
- **pen ink fading** — a problem on long plots; either a fresh pen or
  drop to a thinner line so the same ink covers more.

## Pen tears the paper

- **pen too low** — calibrate per-slot pen-down depth (less down).
- **paper too soft** — switch to 120 gsm or thicker for ink-pen plots.
- **drawing_speed_mm_s too slow** — paradoxically, very slow strokes
  saturate paper and let it tear. 20 mm/s minimum for most pens.

## Multi-colour layers don't register

- **paper shifting between pens** — the swap mechanism (manual or
  carousel) is moving the sheet. On flatbed: clamp harder. On
  rotary: index the carousel from a hard stop, not from a soft home.
- **per-pen XY offset uncalibrated** — Settings → Profile → slot →
  *Calibrate XY offset*. The wizard plots one cross per slot from the
  same home; measure the offset in mm and enter it.

## Cross-hatch looks dark in places, light in others

- the bitmap source has uneven tonality (e.g. a JPEG with bad gamma).
  Pre-process with a level / curves adjustment so the histogram
  doesn't pile up at one end.
- the algorithm's `density` is too low to discriminate tones — bump
  to 70–80 %.

## Stippling looks like Swiss cheese

- `min_distance_mm` is too high. Drop to 0.4 mm for a felt tip, 0.25 mm
  for a 0.3 mm fineliner. The wizard's defaults are conservative.
- the source image has wide flat highlights that the algorithm leaves
  empty by design. If you want some dots in the highlights, raise
  `min_density` from 0 to ~5 %.

## Plot is offset from the page

- **origin mismatch** — your profile says `origin: top_left` but the
  firmware homes to the bottom left (or vice versa). Edit the profile.
- **margin too small** — the page slipped into the home corner.
  Increase `margin_mm` in the profile, re-home, retry.

## Plot is mirrored

- **CoreXY motor wiring** — swap the two motor cables on the
  controller. Re-home before testing.

## See also

- [Picking the right algorithm](Picking-the-Right-Algorithm.md)
- [Per-slot calibration](Per-Slot-Calibration.md)
- [The editor](The-Editor.md)
- [`docs/perf-baseline.md`](../docs/perf-baseline.md) for what's normal
