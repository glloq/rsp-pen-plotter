# OmniPlot

> **Universal pen plotter studio** — drag, drop, plot anything.

OmniPlot is an open-source web application that turns any file — images, PDFs, Word documents, SVG vectors, plain text, Markdown — into beautifully plotted output on any pen plotter, through a unified, intuitive interface.

![status](https://img.shields.io/badge/status-pre--alpha-orange)
![license](https://img.shields.io/badge/license-MIT-blue)

---

## Highlights

- **Universal input**: PNG, JPG, HEIC, TIFF, WebP, SVG, PDF, EPS, DXF, DOCX, ODT, HTML, Markdown, TXT, raw G-code
- **Algorithm choice for raster art**: direct vectorization, stippling, hatching, halftone, flow imager, TSP art
- **Color separation**: automatic detection from SVG layers, color attributes, or raster quantization
- **Pen magazine support**: assign each layer to a physical pen slot, with optimized tool-change ordering
- **Machine profiles**: target any plotter (custom DIY, AxiDraw, iDraw, …) via YAML configuration — no code changes required to add a new machine
- **Visual simulator**: validate the full output without touching hardware
- **Hershey single-stroke fonts**: text rendered as clean single-stroke output, ideal for plotting
- **Multilingual UI**: i18n-ready from day one

---

## Why

Existing pen plotter tools fall into two camps: powerful CLI tools (vpype, Inkscape extensions) that require expertise, or commercial software locked to one specific machine (AxiDraw, iDraw). OmniPlot is the missing middle: a friendly web interface that handles *any* input on *any* hardware.

---

## Architecture

Seven-layer architecture with a clean separation between the Raspberry Pi host and a real-time MCU for step generation. A converter plugin layer normalizes all inputs to a single SVG pivot format, after which the standard pipeline runs identically regardless of input type.

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

Real-time motion control is delegated to a microcontroller (Klipper on RP2040 recommended) because Linux on the Pi does not provide deterministic timing for step generation up to ~100 kHz.

### Multi-format converter

```
 [Bitmap] [Vector] [Document] [G-code direct]
     │       │        │            │
     └───────┴────┬───┴────────────┘
                  ▼
        ┌──────────────────────┐
        │ Conversion layer     │   ← one plugin per format
        │ (plugin per format)  │
        └──────────────────────┘
                  ▼
        ┌──────────────────────┐
        │ Normalized SVG       │   ← format pivot
        │ (pivot format)       │
        └──────────────────────┘
                  ▼
        ┌──────────────────────┐
        │ Standard pipeline    │
        │ (separation →        │
        │  toolpath → G-code)  │
        └──────────────────────┘
```

---

## Tech Stack

### Backend (Python on Raspberry Pi)

| Concern | Library |
| --- | --- |
| Web framework | `fastapi` + `uvicorn[standard]` |
| Models / validation | `pydantic` |
| Plotter core | `vpype` + plugins (`vpype-gcode`, `vpype-occult`, `vpype-flow-imager`, `hatched`) |
| Raster vectorization | `pypotrace` or `potrace` binary |
| Image I/O | `Pillow`, `pillow-heif`, `scikit-image` |
| Color quantization | `scikit-learn` (k-means) |
| PDF | `pymupdf`, `pypdfium2`, `pdfplumber` |
| DXF | `ezdxf` |
| HTML → PDF | `weasyprint` |
| Documents → PDF | `libreoffice --headless` subprocess |
| EPS / AI → PDF | `ghostscript` subprocess |
| Text rendering | `hersheyfonts`, `markdown-it-py`, `python-docx`, `beautifulsoup4` |
| G-code templates | `Jinja2` |
| Profile files | `PyYAML` |
| Serial to MCU | `pyserial-asyncio` |
| Persistence | `SQLModel` |
| Tests | `pytest`, `httpx` |
| Tooling | `uv`, `ruff`, `mypy` |

### Frontend (Web UI)

| Concern | Library |
| --- | --- |
| Framework | Vue 3 |
| Build | Vite |
| Language | TypeScript (strict) |
| Styling | Tailwind CSS |
| Components | Naive UI |
| SVG | native DOM SVG + `svg-pan-zoom` |
| Drag-and-drop | `vuedraggable` (SortableJS) |
| State | Pinia |
| HTTP | `axios` |
| WebSocket | native browser API |
| Color picker | `@simonwep/pickr` |
| i18n | `vue-i18n` |

### MCU (motion control)

- **Firmware**: Klipper on RP2040 (recommended) or FluidNC on ESP32
- **Recommended board**: BTT SKR Pico (RP2040 + 4× TMC2209 integrated)

---

## Project Structure

```
rsp-pen-plotter/
├── backend/
│   ├── pyproject.toml
│   ├── pen_plotter/
│   │   ├── main.py                 # FastAPI app, router wiring, /health
│   │   ├── models.py               # Pydantic shared models
│   │   ├── persistence.py          # SQLModel job-history storage
│   │   ├── presets.py              # built-in parameter presets
│   │   ├── api/
│   │   │   ├── upload.py           # POST /upload
│   │   │   ├── optimize.py         # POST /optimize
│   │   │   ├── generate.py         # POST /generate
│   │   │   ├── plotter.py          # /plotter/* control + /ws/plotter
│   │   │   ├── profiles.py         # profile list/get/export/import
│   │   │   ├── presets.py          # GET /presets
│   │   │   ├── jobs.py             # job history
│   │   │   ├── fonts.py            # GET /fonts (Hershey)
│   │   │   └── algorithms.py       # GET /algorithms (raster art)
│   │   ├── converters/
│   │   │   ├── base.py             # Abstract Converter + ConversionResult
│   │   │   ├── registry.py         # MIME → Converter
│   │   │   ├── defaults.py         # registers the built-in converters
│   │   │   ├── svg.py              # passthrough + sanitization
│   │   │   ├── bitmap.py           # PNG/JPG/HEIC + algorithms
│   │   │   ├── pdf.py              # pymupdf
│   │   │   ├── dxf.py              # ezdxf
│   │   │   ├── eps.py              # ghostscript subprocess
│   │   │   ├── document.py         # docx/odt/rtf → libreoffice
│   │   │   ├── html.py             # weasyprint
│   │   │   ├── markdown.py         # md-it + Hershey
│   │   │   ├── text.py             # txt + Hershey
│   │   │   ├── gcode.py            # direct bypass
│   │   │   └── algorithms/         # direct, halftone, stippling
│   │   ├── core/
│   │   │   ├── layers.py           # layer extraction + labeled_group_fragments
│   │   │   ├── toolpath.py         # vpype wrapper
│   │   │   ├── gcode.py            # Jinja2 G-code renderer
│   │   │   ├── ebb.py              # native EiBotBoard generation
│   │   │   ├── arcs.py             # optional G2/G3 arc fitting
│   │   │   └── sanitize.py         # SVG hardening
│   │   ├── typography/
│   │   │   └── hershey.py          # single-stroke rendering + layout
│   │   ├── profiles/
│   │   │   ├── custom_plotter.yaml
│   │   │   └── axidraw_v3.yaml
│   │   ├── templates/              # Jinja2 G-code templates
│   │   │   ├── header.j2  footer.j2  pen_up.j2  pen_down.j2
│   │   │   └── travel.j2  line.j2  arc.j2  tool_change.j2
│   │   └── hardware/
│   │       ├── transport.py        # Transport protocol + Serial/Mock
│   │       ├── streamer.py         # ok-acknowledged streaming
│   │       ├── controller.py       # connection + job lifecycle
│   │       └── commands.py         # jog / home builders
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.vue
│       ├── main.ts
│       ├── i18n.ts
│       ├── components/
│       │   ├── FileUpload.vue
│       │   ├── SvgPreview.vue
│       │   ├── LayerPanel.vue
│       │   ├── LayerCard.vue
│       │   ├── GcodePreview.vue
│       │   ├── Simulator.vue
│       │   ├── JogControls.vue
│       │   ├── PlotterPanel.vue
│       │   └── JobHistory.vue
│       ├── stores/
│       │   ├── job.ts
│       │   └── plotter.ts
│       ├── lib/gcode.ts            # browser-side simulator parser
│       ├── api/client.ts
│       └── locales/
│           ├── fr.json
│           └── en.json
├── docs/                           # see docs/README.md
│   ├── architecture.md
│   ├── getting_started.md
│   ├── api_reference.md
│   ├── converters.md
│   ├── adding_a_converter.md
│   ├── profile_format.md
│   ├── hardware_streaming.md
│   ├── frontend.md
│   └── audit_report.md
└── README.md
```

---

## Roadmap

The project is built in twelve phases. Each phase produces a testable deliverable. Estimates are for one developer working part-time.

### Phase 0 — Setup & contracts *(1-2 days)*
Monorepo, scaffolding for backend (FastAPI + uv) and frontend (Vite + Vue + TS + Tailwind). Pydantic models for `Job`, `Layer`, `MachineProfile`. Example YAML profile. Health endpoint working end-to-end.

### Phase 1 — Conversion layer skeleton *(2-3 days)*
Abstract `Converter` interface, MIME-based registry, `POST /upload` endpoint with dispatch. Only the SVG passthrough converter is implemented at this stage. Integration tests verify the dispatch routing.

### Phase 2 — Bitmap converters *(4-6 days)*
PNG / JPG / TIFF / HEIC support via Pillow + pillow-heif. Color quantization (k-means), per-color masks, potrace. Algorithm options: direct vectorization, stippling, hatching, halftone, flow imager. UI exposes algorithm choice with preview.

### Phase 3 — Vector converters *(3-5 days)*
PDF via pymupdf (vector extraction), DXF via ezdxf, EPS via ghostscript subprocess. Multi-page PDF with page selection in the UI.

### Phase 4 — Document converters *(4-6 days)*
TXT and Markdown rendered with Hershey single-stroke fonts. HTML via weasyprint. DOCX / ODT / RTF via libreoffice subprocess. Typography panel: font selection (~10 Hershey styles), size, margins, alignment.

### Phase 5 — SVG viewer & layer toggles *(3-5 days)*
File upload component, pan/zoom SVG viewer, layer panel with visibility toggles and color swatches. State management in Pinia.

### Phase 6 — Layer manipulation *(3-4 days)*
Drag-and-drop reordering, pen-slot dropdowns, per-layer parameters (speed, simplification), live statistics (length in mm, estimated duration).

### Phase 7 — Toolpath optimization *(3-5 days)*
`vpype linemerge` → `linesimplify` → `linesort` pipeline. Before/after metrics for travel reduction. Optimized paths previewed live in the SVG viewer.

### Phase 8 — Machine profiles & G-code *(4-6 days)*
YAML profile schema (Pydantic-validated). Jinja2 templates per command type (header, pen up/down, line, tool change, footer). Generation endpoint. Two example profiles (custom CoreXY + AxiDraw V3). Inline G-code preview panel.

### Phase 9 — Visual simulator *(4-7 days)* **— key milestone**
G-code parser (G0/G1 + pen up/down events), animated playback on a canvas, speed controls (1× / 5× / 100× / max), duration cross-validation. At the end of this phase, the entire software chain is validated without any hardware involvement.

### Phase 10 — Plotter connection *(5-10 days)*
pyserial link to the MCU, G-code streamer with buffer management (line-by-line with `ok` acknowledgment), WebSocket push of position and progress to the UI. Manual jog controls, home, pause / resume / abort. Pen-slot calibration routine.

### Phase 11 — Polish *(ongoing)*
Job queue with SQLite history, full i18n (French and English to start), error handling (jam detection, lost position, missing pen), profile import/export, parameter presets (fine line, dense hatching, stippling, halftone, …).

---

## Hardware Reference

The reference build for this project:

- **Frame**: CoreXY, ~A3 effective print area
- **Steppers**: 2× NEMA 17 for X/Y, 1× NEMA 17 for the pen magazine carousel
- **Drivers**: TMC2209 in StealthChop (integrated on the SKR Pico)
- **Pen up/down**: SG90 servo driven by PCA9685
- **Magazine**: rotating carousel with N slots (slot count is configurable per machine profile)
- **Controller board**: BTT SKR Pico (RP2040 + 4× TMC2209)
- **Host**: Raspberry Pi 4 (8 GB recommended)
- **Firmware**: Klipper

Any plotter with a documented G-code dialect can be supported by writing a new machine profile YAML — no code changes required.

---

## Getting Started

> Full documentation lives in [`docs/`](docs/README.md) — architecture, API
> reference, profile format, adding a converter, hardware streaming, and more.

### Prerequisites

- Raspberry Pi 4 or 5 (8 GB RAM recommended for development on-device)
- Python 3.12+
- Node.js 20+
- `uv` for Python dependency management
- A pen plotter (DIY CoreXY recommended; AxiDraw also supported via profile)

### Quick setup

```bash
git clone https://github.com/glloq/rsp-pen-plotter.git
cd rsp-pen-plotter

./install.sh   # backend deps (uv sync) + frontend deps and build
./start.sh     # production: one process serves the UI and API on :8000
```

The interface opens at `http://localhost:8000` (and at `http://<host-ip>:8000`
on the LAN). Set `OMNIPLOT_API_KEY=...` before `./start.sh` to require an API
key for machine-control endpoints when the host is reachable from other
devices.

For development with hot reload, use `./start.sh --dev` instead — the UI runs
on `http://localhost:5173` and the API on `http://localhost:8000`.

The legacy manual flow (`uv sync` + `uv run uvicorn …` and `npm run dev` in
another terminal) still works for development.

---

## Contributing

Contributions are welcome. Each phase tracks a dedicated branch and milestone.

To add support for a new input format, see `docs/adding_a_converter.md`. To add a new machine profile, see `docs/profile_format.md`.

---

## License

MIT.

---

## Acknowledgments

This project stands on the shoulders of:

- **vpype** by Antoine Beyeler — the pen plotter pre-processing toolkit, central to everything OmniPlot does
- **Klipper** by Kevin O'Connor — the firmware that makes Raspberry Pi-driven motion control reliable
- **The plotter art community** on Reddit, Discord, and personal blogs — for years of generously shared techniques and tooling
