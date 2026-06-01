# OmniPlot wiki source

This folder is the **source** for the project's [GitHub wiki](https://github.com/glloq/rsp-pen-plotter/wiki).
Long-form guides, tutorials, troubleshooting and reference live here.

> Looking for the actual wiki experience (sidebar nav, search)? Browse the
> wiki on GitHub once it's been synced. To read here in the repo, start at
> [`Home.md`](Home.md).

## Why a folder in the repo?

GitHub wikis are stored in a separate `*.wiki.git` repository. Keeping the
markdown source in the main repo means:

- changes go through normal pull requests with review
- the wiki stays in lockstep with code changes that affect it
- contributors don't need wiki write access to propose fixes
- the source is searchable from `grep`, IDEs and the issue tracker

A small GitHub Action syncs the contents of this folder to the actual wiki on
push to `main` (when configured).

## Layout

| Path | Purpose |
| --- | --- |
| [`Home.md`](Home.md) | Wiki landing page (sets the *Home* tab on GitHub) |
| [`_Sidebar.md`](_Sidebar.md) | Navigation rendered alongside every page |
| [`_Footer.md`](_Footer.md) | Footer rendered below every page |
| `<Title>.md` | One page per topic; filenames double as URL slugs |
| `../docs/` | Reference manual — schemas, APIs, ADRs — kept tight against the code |

## Pages

- [Home](Home.md)
- [FAQ](FAQ.md)
- [Glossary](Glossary.md)
- [Install on a Raspberry Pi](Install-on-a-Raspberry-Pi.md)
- [Tutorial — first print](Tutorial-First-Print.md)
- [The editor](The-Editor.md)
- [Picking the right algorithm](Picking-the-Right-Algorithm.md)
- [Multi-pass plotting](Multi-Pass-Plotting.md)
- [Print queue & resume](Print-Queue.md)
- [Supported file types](Supported-File-Types.md)
  - [Bitmaps](File-Type-Bitmaps.md)
  - [Vectors](File-Type-Vectors.md)
  - [Documents](File-Type-Documents.md)
  - [Text & Markdown](File-Type-Text.md)
  - [Raw G-code](File-Type-Gcode.md)
- [Machine profiles](Machine-Profiles.md)
- [Pen magazine](Pen-Magazine.md)
- [Per-slot calibration](Per-Slot-Calibration.md)
- [Klipper config snippets](Klipper-Config.md)
- [Environment variables](Environment-Variables.md)
- [Architecture deep dive](Architecture-Deep-Dive.md)
- [Adding a raster algorithm](Adding-a-Raster-Algorithm.md)
- Troubleshooting: [Install](Troubleshooting-Install.md) · [Connection](Troubleshooting-Connection.md) · [Quality](Troubleshooting-Quality.md)

## Editing convention

- one `.md` per page, no nested folders (the GitHub wiki is flat)
- file name = page title with dashes between words — that's the URL slug
- cross-link with `[Label](Page-Name.md)`; never use absolute wiki URLs
- references to repository docs use `[label](../docs/foo.md)` so they
  resolve correctly both in the repo *and* on the wiki after sync

## See also

- [README](../README.md) — quick presentation
- [`docs/`](../docs/README.md) — reference manual
