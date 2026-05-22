# Architecture

OmniPlot is split into a Python backend (FastAPI) that orchestrates the
conversion-to-G-code pipeline and drives the plotter, and a Vue 3 frontend that
provides the studio UI. Real-time step generation is delegated to a
microcontroller running Klipper (or FluidNC), because a general-purpose OS on
the host cannot guarantee deterministic timing.

## Seven-layer model

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

This repository implements layers 1–4 plus the host side of the link to the MCU
(serial streaming). Layers 5–7 are firmware and hardware.

## The SVG-pivot pipeline

Every input format is normalized to a single **SVG pivot** representation, after
which one identical pipeline runs regardless of where the SVG came from.

```
 [Bitmap] [Vector] [Document] [G-code]      ← raw upload
     │       │        │           │
     └───────┴───┬────┴───────────┘
                 ▼
       Converter (one plugin per MIME)       converters/
                 ▼
       Normalized SVG (pivot format)         labeled <g inkscape:label> groups
                 ▼
       Layer extraction                      core/layers.py
                 ▼
       Toolpath optimization (vpype)         core/toolpath.py
                 ▼
       G-code / EBB generation               core/gcode.py · core/ebb.py
                 ▼
       Simulator / Plotter streaming         frontend · hardware/
```

The pivot SVG contract: each drawing layer is a top-level `<g>` element carrying
an `inkscape:label`. Coordinates are interpreted in the document's `viewBox`
user units (millimeters for text/Markdown by construction). `core/layers.py`
exposes `labeled_group_fragments()` as the single source of truth for mapping
SVG groups to layers — both layer extraction and G-code generation consume it.

## Backend module map

```
backend/pen_plotter/
├── main.py             FastAPI app, CORS, router wiring, /health, lifespan
├── models.py           Shared Pydantic contracts (MachineProfile, LayerInfo, Job, EbbConfig)
├── persistence.py      SQLModel job-history storage (OMNIPLOT_DB)
├── presets.py          Built-in parameter presets
├── api/                HTTP + WebSocket routers
│   ├── upload.py       POST /upload  (dispatch via converter registry)
│   ├── optimize.py     POST /optimize
│   ├── generate.py     POST /generate (routes ebb → core/ebb, else core/gcode)
│   ├── plotter.py      /plotter/* control + /ws/plotter progress
│   ├── profiles.py     profile list / get / export / import
│   ├── presets.py      GET /presets
│   ├── jobs.py         job history
│   ├── fonts.py        GET /fonts (Hershey font names)
│   └── algorithms.py   GET /algorithms (raster-art choices)
├── converters/         One plugin per input format → SVG
│   ├── base.py         Converter ABC + ConversionResult
│   ├── registry.py     MIME → Converter index
│   ├── defaults.py     Registers every built-in converter
│   ├── svg/bitmap/pdf/dxf/eps/document/html/markdown/text/gcode.py
│   └── algorithms/     Raster-art strategies (direct, halftone, stippling)
├── core/               Format-agnostic pipeline
│   ├── layers.py       Layer extraction + labeled_group_fragments()
│   ├── toolpath.py     vpype linemerge → linesimplify → linesort
│   ├── gcode.py        Jinja2 template-driven G-code generation
│   ├── ebb.py          Native EiBotBoard (AxiDraw) command generation
│   ├── arcs.py         Optional G2/G3 arc fitting
│   └── sanitize.py     SVG hardening (strips script/event handlers)
├── typography/hershey.py   Single-stroke text → SVG
├── profiles/           YAML machine profiles + loader (OMNIPLOT_PROFILES_DIR)
├── templates/          Jinja2 G-code fragments (header, line, arc, pen_*, …)
└── hardware/           Serial link to the MCU
    ├── transport.py    Transport protocol, SerialTransport, MockTransport
    ├── streamer.py     Line-by-line streaming with ok-acknowledgment
    ├── controller.py   Connection + job lifecycle, progress broadcast
    └── commands.py     jog / home command builders
```

## Frontend module map

```
frontend/src/
├── App.vue             Layout and panel composition
├── main.ts, i18n.ts    App bootstrap, vue-i18n setup
├── api/client.ts       Typed axios client + WebSocket URL helper
├── stores/
│   ├── job.ts          Upload, layers, optimization, generation state
│   └── plotter.ts      Connection, streaming status, WebSocket
├── components/         FileUpload, SvgPreview, LayerPanel, LayerCard,
│                       GcodePreview, Simulator, JogControls, PlotterPanel, JobHistory
├── lib/gcode.ts        Browser-side G-code parser for the simulator
└── locales/            en.json, fr.json (vue-i18n messages)
```

## Design principles

- **Plotter-agnostic core.** No machine-specific behavior lives in code; it is
  all data in the machine profile (commands, speeds, servo positions, dialect).
  Supporting a new plotter is a YAML file, not a code change.
- **One pivot, one pipeline.** Adding a format means adding one converter; the
  rest of the pipeline is untouched.
- **Testable hardware.** The serial transport is an injected protocol, so the
  controller and streamer are fully exercised with an in-memory mock.
