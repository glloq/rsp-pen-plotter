# FAQ

### Do I need a Raspberry Pi?

No. OmniPlot is a normal Python + Vue web app — it runs on any Linux box,
on macOS for development, and on Windows under WSL. The Pi is the
recommended *appliance* host because it's silent, cheap, and lives next
to the plotter.

### Can I run OmniPlot without a plotter?

Yes. The full software chain runs and is validated in the simulator. No
serial connection is needed to convert, edit, generate G-code, or
preview.

### Which plotters work?

Anything with a documented G-code dialect: AxiDraw, iDraw, EiBot Board
(EBB), GRBL plotters, Klipper plotters, Marlin plotters, FluidNC, the
NextDraw, and DIY CoreXY / H-Bot / linear-rail builds. The reference
build is a CoreXY on Klipper with BTT SKR Pico.

If your plotter speaks a dialect we haven't profiled, you write one
YAML file. See [Machine profiles](Machine-Profiles.md).

### Why a microcontroller for motion? Why not just the Pi?

A general-purpose Linux kernel can't reliably hit ~100 kHz step pulses
without dropping pulses on a busy system (USB activity, log writes,
swap, your `apt upgrade`). Klipper on an RP2040 *can*, deterministically.
The Pi orchestrates; the MCU does step generation.

### Where are my files stored?

In the SQLite database at `OMNIPLOT_DB` (default
`backend/data/omniplot.db`) plus a file-content store keyed by SHA-256
hash. The library survives upgrades. To back up: copy the database file
and the `backend/data/files/` folder.

### How does the queue survive a power loss?

Every ~1 second the running job's last-acked line number is committed
to SQLite. On the next boot, the queue scans for `running` runs, marks
them `paused`, and offers to resume. Resume rebuilds a short modal
preamble (units, absolute/relative mode, last feed rate, pen state) and
streams from the line after the checkpoint. See [Print queue & resume](Print-Queue.md).

### Can I export the G-code and plot from another tool?

Yes. *Generate* always produces a downloadable file. The downloaded
G-code keeps `M0` at pen-change points so it remains portable to other
senders.

### Does OmniPlot upload my files anywhere?

No. The appliance is fully local. There is no telemetry, no analytics,
no auto-upload. The only network calls are:

- the optional update check against `github.com/glloq/rsp-pen-plotter`
- `apt` / `npm` / `uv` package installs during `update.sh`

You can disable update checks entirely with
`OMNIPLOT_DISABLE_UPDATE=1` (the endpoint vanishes).

### Why so many raster algorithms?

Different artwork wants different treatment. A logo needs `direct`, a
portrait wants `stippling` or `crosshatch`, a landscape begs for
`flowfield`. Most users settle on three or four favourites and ignore
the rest — the Assistant wizard picks one for you based on the source.

### Can I use a touchscreen?

Yes. The UI is responsive down to ~800 × 480 (a 7-inch DSI screen
works). The header collapses to icons and the Files pane shrinks. Some
power-user surfaces (Compare drawer, Profile editor) expect more room
and will scroll horizontally.

### Multi-language UI?

Yes. French and English ship today, more are easy to add — they're flat
JSON files in `frontend/src/locales/`. PRs welcome.

### Why "OmniPlot"?

Because it plots anything (bitmaps, vectors, documents, raw G-code) on
anything (CoreXY, AxiDraw, iDraw, EBB, custom). The repository is
called `rsp-pen-plotter` for historical reasons.

### How do I uninstall?

```bash
sudo systemctl disable --now omniplot
sudo rm /etc/systemd/system/omniplot.service
sudo rm -rf /etc/omniplot
rm -rf ~/rsp-pen-plotter
```

Done.

### I have a different question

Open an [issue](https://github.com/glloq/rsp-pen-plotter/issues) — and
if the answer is generally useful, it'll land here.
