# OmniPlot

> **Universal pen plotter studio** — drag, drop, plot anything.

OmniPlot is an open-source web application that turns any file — images, PDFs,
office documents, SVG vectors, plain text, Markdown — into beautifully plotted
output on any pen plotter, through one unified interface.

![status](https://img.shields.io/badge/status-pre--alpha-orange)
![license](https://img.shields.io/badge/license-MIT-blue)

---

## Install in two commands

Prerequisites: a Linux host (Raspberry Pi 4/5 recommended) with Node.js 20+ and
either [`uv`](https://docs.astral.sh/uv/) (preferred) or Python 3.12+.

```bash
git clone https://github.com/glloq/rsp-pen-plotter.git
cd rsp-pen-plotter
./install.sh        # backend deps + frontend build
./start.sh          # one process serves UI + API on http://<host>:8000
```

Open `http://localhost:8000` (and `http://<host-ip>:8000` from any device on
your LAN).

To start on boot via systemd (Raspberry Pi or any systemd Linux):

```bash
sudo ./install-service.sh
sudo systemctl status omniplot      # check state
sudo journalctl -u omniplot -f      # follow logs
```

For development with hot reload:

```bash
./start.sh --dev   # backend --reload on :8000 + Vite on :5173
```

### Configuration

`./install-service.sh` creates a `.env.service` (mode 600) with these
overrides; for non-systemd use, set the same variables in the shell before
`./start.sh`.

| Variable             | Default      | Effect                                                                  |
| -------------------- | ------------ | ----------------------------------------------------------------------- |
| `HOST`               | `0.0.0.0`    | Interface to bind. Set to `127.0.0.1` to restrict to this machine only. |
| `PORT`               | `8000`       | UI + API port.                                                          |
| `OMNIPLOT_API_KEY`   | unset        | When set, machine-control endpoints require this key (header `X-API-Key` or `?token=` for WebSockets). Strongly recommended on a LAN. |
| `OMNIPLOT_DB`        | `backend/data/omniplot.db` | SQLite database path. |
| `OMNIPLOT_STATIC_DIR`| `frontend/dist` | Override where the built UI is served from. |

---

## What it does

- **Universal input**: PNG, JPG, HEIC, TIFF, WebP, SVG, PDF, EPS, DXF, DOCX,
  ODT, HTML, Markdown, TXT, raw G-code.
- **Algorithm choice for raster art**: direct vectorization, stippling,
  halftone, hatching, flow imager.
- **Color separation**: from SVG layers, color attributes, or raster
  quantization (k-means).
- **Machine profiles**: any plotter (DIY CoreXY, AxiDraw, iDraw, EBB,
  custom G-code dialect) via YAML — no code changes needed for a new machine.
- **Sheet preview**: see the placed drawing on the workspace, with margin,
  effective scale, dimensions in mm, and an out-of-bounds warning.
- **Visual simulator**: validate the full output before touching hardware.
- **Hershey single-stroke fonts**: clean text rendered for plotting.
- **Multilingual UI** (French and English to start).

### Production-grade operation

- **Persistent print queue** with priorities, pause/resume/cancel, and
  reboot recovery: a job interrupted by a crash or power loss can be safely
  resumed from its checkpoint with a reconstructed modal-state preamble.
- **Pre-flight check**: bounds, drawing dimensions, effective scale,
  estimated drawing+travel time, pen-change count, missing pen slots —
  surfaced in the UI before generation; generation is blocked if a layer is
  assigned to a missing or out-of-range pen slot.
- **Guided operator workflow** for manual pen changes: the queue replaces the
  firmware pause with a software-guided pause that prompts the operator and
  resumes on confirmation. The downloaded G-code keeps `M0` so it stays
  portable to other senders.
- **Pen-swap planner**: one-click layer reordering to minimize tool changes,
  with the planner's effect surfaced through the preflight swap count.
- **Per-slot calibration**: override the pen-up / pen-down commands per
  magazine slot (e.g. different servo depths per pen).
- **Idempotent job submission**: `POST /queue` honours an `Idempotency-Key`
  header for safe automation retries.
- **Audit trail**: append-only log of sensitive actions (plotter connect,
  run, home, abort; queue enqueue, cancel; macro run) viewable from the UI
  and via `GET /audit`.
- **Optional API-key auth**: machine-control and macro-execution endpoints
  can be gated by `OMNIPLOT_API_KEY`; disabled by default for local use.
- **Additive schema migrations**: new nullable model columns are added to
  existing SQLite databases on startup, so an upgrade doesn't break a Pi
  that's been running for a while.

---

## Architecture

A clean separation between the Linux host (user interface, orchestration,
graphics pipeline) and a real-time MCU for step generation, with a converter
plugin layer that normalizes every input to a single SVG pivot format.

```
 ┌─────────────────────────────────────────┐
 │ 1. User interface         (Vue, web)    │ ─┐
 │ 2. Orchestrator           (FastAPI)     │  │  Pi (host)
 │ 3. Graphics preparation   (vpype)       │  │
 │ 4. Toolpath generation    (vpype)       │ ─┘
 │ 5. Real-time motion       (Klipper)     │ ─── MCU
 │ 6. Drivers                (TMC2209)     │ ─┐
 │ 7. Mechanics              (CoreXY)      │ ─┘  Hardware
 └─────────────────────────────────────────┘
```

Real-time motion control is delegated to a microcontroller (Klipper on RP2040
recommended) because Linux on the Pi does not provide deterministic timing for
step generation up to ~100 kHz.

### Multi-format converter

```
 [Bitmap] [Vector] [Document] [G-code direct]
     │       │        │            │
     └───────┴────┬───┴────────────┘
                  ▼
        ┌──────────────────────┐
        │ Conversion layer     │   ← one plugin per format
        └──────────────────────┘
                  ▼
        ┌──────────────────────┐
        │ Normalized SVG       │   ← pivot format
        └──────────────────────┘
                  ▼
        ┌──────────────────────┐
        │ Standard pipeline    │
        │ (separation →        │
        │  toolpath → G-code)  │
        └──────────────────────┘
```

---

## Tech stack

### Backend (Python)

| Concern                 | Library                                                |
| ----------------------- | ------------------------------------------------------ |
| Web framework           | `fastapi` + `uvicorn[standard]`                        |
| Models / validation     | `pydantic`                                             |
| Plotter core            | `vpype` + plugins                                      |
| Raster vectorization    | `potrace`                                              |
| Image I/O               | `Pillow`, `pillow-heif`                                |
| Color quantization      | `scikit-learn` (k-means)                               |
| PDF / DXF / EPS         | `pymupdf`, `ezdxf`, `ghostscript`                      |
| HTML & documents → PDF  | `weasyprint`, `libreoffice --headless`                 |
| Text                    | `hershey-fonts`, `markdown-it-py`, `beautifulsoup4`    |
| G-code templates        | `Jinja2`                                               |
| Profile files           | `PyYAML`                                               |
| Serial to MCU           | `pyserial-asyncio`                                     |
| Persistence             | `SQLModel` (SQLite)                                    |
| Tests / lint            | `pytest`, `httpx`, `ruff`                              |
| Tooling                 | `uv`                                                   |

### Frontend (Web UI)

| Concern        | Library                              |
| -------------- | ------------------------------------ |
| Framework      | Vue 3 + TypeScript (strict)          |
| Build          | Vite                                 |
| Styling        | Tailwind CSS                         |
| State          | Pinia                                |
| HTTP           | `axios`                              |
| SVG            | native DOM + `svg-pan-zoom`          |
| Drag-and-drop  | `vuedraggable`                       |
| i18n           | `vue-i18n`                           |
| Tests          | `vitest`                             |

### MCU (motion control)

- **Firmware**: Klipper on RP2040 (recommended) or FluidNC on ESP32.
- **Recommended board**: BTT SKR Pico (RP2040 + 4× TMC2209 integrated).

---

## Project layout

```
rsp-pen-plotter/
├── install.sh / start.sh / install-service.sh
├── deploy/omniplot.service.in        # systemd unit template
├── backend/                          # FastAPI app (Python)
│   ├── pyproject.toml                # uv-managed
│   └── pen_plotter/
│       ├── main.py                   # router wiring, static frontend mount
│       ├── auth.py                   # optional API-key dependency
│       ├── audit.py                  # audit trail
│       ├── persistence.py            # SQLite engine + additive migrations
│       ├── queue.py                  # durable print queue + worker
│       ├── api/                      # upload, optimize, generate, preflight,
│       │                             # plotter, queue, audit, jobs, …
│       ├── converters/               # one plugin per format (svg, bitmap,
│       │                             # pdf, dxf, eps, html, markdown, …)
│       ├── core/                     # gcode, ebb, arcs, sanitize, layers,
│       │                             # toolpath, preflight, resume,
│       │                             # toolchange
│       ├── hardware/                 # Transport / Streamer / Controller
│       ├── profiles/                 # example YAML machine profiles
│       └── templates/                # Jinja2 G-code fragments
├── frontend/                         # Vue 3 + TS + Tailwind (Vite)
│   └── src/
│       ├── components/               # FileUpload, SheetPreview, SvgPreview,
│       │                             # LayerPanel, Simulator, PlotterPanel,
│       │                             # QueuePanel, AuditPanel, MacroPanel,
│       │                             # ProfileEditor, ConfirmDialog, …
│       ├── stores/                   # job, plotter, queue, macros (Pinia)
│       ├── lib/                      # gcode parser, placement, penorder
│       ├── api/client.ts             # axios + WS helpers
│       └── locales/                  # fr.json, en.json
└── docs/                             # architecture, API reference, profiles,
                                      # converters, hardware streaming, …
```

---

## Status

Built and tested end-to-end:

- Full conversion pipeline (bitmap → vector, vector passthrough, PDF/EPS/DXF,
  documents via LibreOffice, HTML via WeasyPrint, Markdown/TXT via Hershey).
- Color separation, layer editor (reorder, visibility, pen-slot, speed,
  simplification, optimize toggle).
- G-code generation (multi-dialect) and native EBB output. Optional G2/G3
  arc fitting.
- Visual simulator with workspace framing and hi-DPI rendering.
- Plotter connection (serial / mock transport), ok-acknowledged streamer,
  jog / home / goto / send / pause / resume / abort, WebSocket progress.
- Durable print queue with checkpoint/resume, idempotent enqueue, guided
  tool-change pauses, audit trail.
- Profile editor + import/export, presets, macros, optional API-key auth.
- One-command appliance (`./start.sh`) and systemd auto-start.

Backend currently ships ~145 unit and integration tests; the frontend ships
unit tests for placement, pen ordering and the G-code simulator.

### Out of scope today, on the backlog

- Outbound webhooks on run completion (would add an HTTP runtime dependency
  and network policy concerns; deliberately deferred).
- Full RBAC with operator/admin roles (the API-key + audit trail covers the
  practical local-deployment threat model).
- Multi-plotter print farm and predictive maintenance.
- Hardware-in-the-loop endurance test suite.

---

## Hardware reference

The recommended build for this project:

- **Frame**: CoreXY, ~A3 effective print area
- **Steppers**: 2× NEMA 17 for X/Y, 1× NEMA 17 for the pen magazine carousel
- **Drivers**: TMC2209 in StealthChop (integrated on the SKR Pico)
- **Pen up/down**: SG90 servo driven by PCA9685
- **Magazine**: rotating carousel with N slots (configurable per profile)
- **Controller board**: BTT SKR Pico (RP2040 + 4× TMC2209)
- **Host**: Raspberry Pi 4 (8 GB recommended)
- **Firmware**: Klipper

Any plotter with a documented G-code dialect can be supported by writing a
new machine profile YAML — no code changes required.

---

## Documentation

Full documentation lives in [`docs/`](docs/README.md): architecture, API
reference, profile format, adding a converter, hardware streaming, and more.

---

## Contributing

Contributions are welcome.

- To add support for a new input format, see
  [`docs/adding_a_converter.md`](docs/adding_a_converter.md).
- To add a new machine profile, see
  [`docs/profile_format.md`](docs/profile_format.md).

---

## License

MIT.

---

## Acknowledgments

This project stands on the shoulders of:

- **vpype** by Antoine Beyeler — the pen plotter pre-processing toolkit,
  central to everything OmniPlot does.
- **Klipper** by Kevin O'Connor — the firmware that makes Raspberry Pi-driven
  motion control reliable.
- **The plotter art community** on Reddit, Discord, and personal blogs — for
  years of generously shared techniques and tooling.
