# OmniPlot Documentation

This folder documents OmniPlot — a universal pen plotter studio that turns any
file (images, PDFs, documents, SVG, text) into plotted output on any pen plotter.

## Contents

| Document | What it covers |
| --- | --- |
| [architecture.md](architecture.md) | System layers, the SVG-pivot pipeline, and the module map |
| [getting_started.md](getting_started.md) | Install, run the backend and frontend, run the test suites |
| [api_reference.md](api_reference.md) | Every REST endpoint and the WebSocket message shape |
| [converters.md](converters.md) | Supported input formats and the raster-art algorithms |
| [adding_a_converter.md](adding_a_converter.md) | How to add support for a new input format |
| [profile_format.md](profile_format.md) | Machine profile YAML schema and the bundled examples |
| [hardware_streaming.md](hardware_streaming.md) | Serial transport, the G-code streamer, EBB, and templates |
| [frontend.md](frontend.md) | Vue component map, Pinia stores, i18n, and SVG safety |
| [audit_report.md](audit_report.md) | Codebase audit findings and the fixes applied |
| [adr/](adr/README.md) | Architecture Decision Records — load-bearing structural choices |

## Quick links

- Repository root [README](../README.md)
- Backend package: `backend/pen_plotter/`
- Frontend app: `frontend/src/`
