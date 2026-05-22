# Getting Started

## Prerequisites

- Python 3.12+
- Node.js 20+
- [`uv`](https://github.com/astral-sh/uv) for Python dependency management
- System tools used by some converters (optional, only for those formats):
  - `potrace` — bitmap vectorization
  - `ghostscript` — EPS/AI rasterization
  - `libreoffice` — DOCX/ODT/RTF conversion
- A pen plotter for the hardware features (a DIY CoreXY or an AxiDraw); the full
  software chain runs and is validated in the simulator without any hardware.

## Backend

```bash
cd backend
uv sync                                    # install dependencies (incl. dev)
uv run uvicorn pen_plotter.main:app --reload
```

The API serves on `http://localhost:8000`. Check it with
`curl http://localhost:8000/health`.

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OMNIPLOT_DB` | `omniplot.db` | SQLite job-history database path |
| `OMNIPLOT_PROFILES_DIR` | platform user dir | Where imported user profiles are stored |

CORS is preconfigured to allow the Vite dev origin `http://localhost:5173`.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

The UI serves on `http://localhost:5173`. The API base URL defaults to
`http://localhost:8000` and can be overridden with the `VITE_API_URL`
environment variable (set it explicitly in production).

## Tests and quality gates

Backend:

```bash
cd backend
uv run ruff check .     # lint (E, F, I, N, UP, B, D)
uv run mypy             # strict type checking of pen_plotter
uv run pytest           # full test suite
```

Frontend:

```bash
cd frontend
npm run test            # vitest
npm run build           # vue-tsc --noEmit type check + production build
```

## Typical workflow

1. Upload a file → the matching converter normalizes it to the SVG pivot.
2. Inspect and toggle layers, assign pen slots, set per-layer speed/simplify.
3. Optimize toolpaths (vpype) and review the travel-reduction metrics.
4. Generate G-code against a machine profile and preview it.
5. Validate in the simulator, then connect to the plotter and stream the job.
