# Tutorial — your first stippled portrait

Goal: turn a photo into a stippled pen plot in about ten minutes, without
touching any setting that isn't strictly necessary.

You'll need:

- a Raspberry Pi running OmniPlot ([install guide](Install-on-a-Raspberry-Pi.md))
- a plotter connected over USB, with at least one pen
- a JPG or PNG photo on your laptop or phone

## 1. Open the UI

Browse to `http://<pi-ip>:8000`. The interface has two panes: **Files** on
the left, **Canvas** on the right. The Canvas has three tabs: *Sheet*
(layout), *Simulator* (stroke-by-stroke preview), *Plotter* (live status).

If you see *"Backend unreachable"*, the systemd unit isn't running yet —
see [Troubleshooting — installer](Troubleshooting-Install.md).

## 2. Drop in the photo

Drag the JPG anywhere on the page. The Files pane gets a new row with a
thumbnail, the file type chip and the dimensions. Drops never edit
anything — the file just goes into the library.

## 3. Place it on the sheet

Click the file in the Files pane → *Place on sheet*. A green
selection-handle frame appears on the A3 preview. The handles let you
scale, the body lets you drag, the right-side rail shows the effective
size in mm.

## 4. Open the editor — Assistant mode

With the placement selected, hit **Edit**. The Assistant wizard opens
(six steps shown on the top rail).

- **Source** — already filled in: *bitmap photo*.
- **Goal** — pick *Portrait / shaded fill*. The wizard recommends
  **stippling** based on the source kind and your goal.
- **Render** — confirm stippling, drop the density to ~70 % if the
  preview looks too dense, watch it re-render. The right side shows the
  live preview and an estimated drawing time.
- **Colours** — for a mono plot, leave at *1 colour*. The pen is mapped
  to slot 1.
- **Layers** — only one for a stippled render. Skip.
- **Review** — final pre-flight: drawing length, travel, estimated time,
  bounds OK / not OK. Click **Generate**.

If anything goes red on the Review step, see
[Troubleshooting — plot quality](Troubleshooting-Quality.md).

## 5. Simulate

Once *Generate* completes, the Canvas auto-switches to the *Simulator*
tab. Press play. The simulator draws the actual G-code stroke-by-stroke
with optional pen-up moves visible.

This is your last chance to catch a problem cheaply.

## 6. Send to the plotter

Switch to the **Plotter** tab:

- **Connect** → pick the USB port. The status pill turns green.
- **Home** → the carriage moves to the corner you've defined as 0,0.
- **Run job** → confirms once, then starts streaming. Progress shows on
  the Plotter tab, in the right-rail Queue card, and in the system tray
  *Workshop* button.

If a pen change is needed mid-print (more colours, multi-pass), the
queue pauses automatically and shows a *Swap to slot N* modal until you
confirm.

## 7. Save the result as a preset

Once you're happy with the algorithm settings, the editor's *Save as
preset* button captures the algorithm, options and per-layer settings.
Next time, a single click reapplies the same look to a new photo.

## See also

- [Picking the right algorithm](Picking-the-Right-Algorithm.md)
- [The editor in depth](The-Editor.md)
- [Multi-pass plotting](Multi-Pass-Plotting.md)
- [Print queue & resume](Print-Queue.md)
