# OmniPlot wiki

Welcome. This wiki is the long-form companion to the reference
[`docs/`](../docs/README.md) — tutorials, recipes, troubleshooting, hardware
notes, and the kind of background that doesn't fit in API tables.

If you just want to install the appliance, the
[top-level README](../README.md) covers that in one command.

## Browse by goal

### I want to print my first plot

1. [Install on a Raspberry Pi](Install-on-a-Raspberry-Pi.md)
2. [First print — a stippled photo](Tutorial-First-Print.md)
3. [Understanding the editor](The-Editor.md)
4. [Picking the right algorithm](Picking-the-Right-Algorithm.md)

### I'm tuning a particular machine

- [Machine profiles explained](Machine-Profiles.md)
- [Pen magazine & tool change](Pen-Magazine.md)
- [Calibrating per-slot pen depth](Per-Slot-Calibration.md)
- [Offset camera — measure per-pen offsets](Offset-Camera.md)
- [Multi-pass plotting](Multi-Pass-Plotting.md)
- [Klipper config snippets](Klipper-Config.md)

### I'm working with a particular file type

- [Bitmaps & raster algorithms](File-Type-Bitmaps.md)
- [SVG, PDF, EPS, DXF — vector inputs](File-Type-Vectors.md)
- [Office documents (DOCX, ODT, RTF, HTML)](File-Type-Documents.md)
- [Text & Markdown with Hershey fonts](File-Type-Text.md)
- [Raw G-code direct send](File-Type-Gcode.md)

### Something isn't working

- [Troubleshooting — installer](Troubleshooting-Install.md)
- [Troubleshooting — first connection](Troubleshooting-Connection.md)
- [Troubleshooting — bad plot quality](Troubleshooting-Quality.md)
- [FAQ](FAQ.md)

### I'm a developer

- [Architecture deep dive](Architecture-Deep-Dive.md)
- [Adding a converter](../docs/adding_a_converter.md)
- [Adding a raster algorithm](Adding-a-Raster-Algorithm.md)
- [Frontend extension points](../docs/frontend.md)
- [API reference](../docs/api_reference.md)

### Reference

- [Glossary](Glossary.md)
- [Supported file types](Supported-File-Types.md)
- [Keyboard shortcuts](../docs/shortcuts.md)
- [Environment variables](Environment-Variables.md)

## Project links

- [README](../README.md) · quick presentation
- [`docs/`](../docs/README.md) · reference manual
- [`docs/adr/`](../docs/adr/README.md) · architecture decision records
- [`ROADMAP_V0.2`](../docs/ROADMAP_V0.2.md) · what's coming next
- [Issues](https://github.com/glloq/rsp-pen-plotter/issues)

> Found something wrong or missing? Edit the page on GitHub — or open an
> issue. Long-form pages in this wiki are intentionally evergreen; if a doc
> needs to track the codebase exactly it lives in `docs/` instead.
