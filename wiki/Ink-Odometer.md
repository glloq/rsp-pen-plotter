# Ink odometer

OmniPlot tracks how much line each pen has drawn, per colour, across every job —
an **ink odometer**. It's a rough fuel gauge for your pens: when a colour's
total creeps up toward where that pen usually runs dry, you know a swap is
coming.

## What it counts

Each colour in your app-wide ink inventory carries an `odometer_mm` total. The
odometer **advances only when a plot is actually launched on the machine** — not
when you generate, preview, or save. Specifically:

- **Launching the current job** adds that job's per-colour drawn lengths.
- **Re-printing a saved program** from the [G-code library](G-code-Library.md)
  adds the per-colour lengths stored with that file.

Saving a program to the library does **not** move the odometer — ink is only
counted when it actually hits paper.

The totals are stored in SQLite (`OMNIPLOT_DB`) and survive restarts and
upgrades.

## Reading and resetting

The ink inventory panel shows each colour's odometer as a distance in metres
(e.g. `12.480 m`), highlighted once it's above zero. When you physically swap a
pen for a fresh one, press the reset (↺) button on that colour to zero its
total.

## API

The odometer lives on the available-colours inventory:

| Method & path | What |
| --- | --- |
| `GET /available-colors` | Inventory, including each colour's `odometer_mm` |
| `PATCH /available-colors/{id}` | Set `odometer_mm` (the UI sends old + delta, or `0` to reset) |

See [`docs/api_reference.md`](../docs/api_reference.md) — *Plans, policy,
available colours*.

## See also

- [G-code library](G-code-Library.md)
- [Pen magazine](Pen-Magazine.md)
- [Per-slot calibration](Per-Slot-Calibration.md)
