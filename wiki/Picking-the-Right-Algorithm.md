# Picking the right algorithm

OmniPlot ships 48 visible raster algorithms (52 registered — four legacy
duplicates are hidden from the pickers, see below). This page is a
decision tree, not a catalogue — for the full algorithm table see
[`docs/converters.md`](../docs/converters.md).

> Algorithms group into three **families**: *fill* packs ink across a
> region (stippling, halftone, hatching, flow field), *lines* emits
> discrete outlines (contours, edges, centerline), *mono_stroke* produces
> a single continuous polyline (spiral, TSP, Hilbert). Mono-stroke
> algorithms minimise pen-ups but constrain the look.

## By input + intent

| Input | Intent | Pick |
| --- | --- | --- |
| Logo / icon / sharp line art | Crisp outlines | `direct` (potrace) |
| Technical drawing (raster) | Faithful lines | `edges` or `centerline` |
| Portrait photo | Editorial / shaded | `crosshatch` or `stippling` |
| Portrait photo | Print-press feel | `halftone` |
| Landscape photo | Organic, sketchy | `flowfield` or `squiggle` |
| Comic / graphic-novel page | Strong outlines + fill | `direct` then `crosshatch` (multi-pass) |
| Topographic map / contour | Iso-lines | `concentric_offset` |
| Portrait photo | Iconic single-line | `spiral` (tonal), `string_art`, `ridge_lines` (rows or radial), `hilbert` (adaptive) |
| Portrait photo | Engraving / banknote | `etch`, `dither` |
| Portrait photo | Organic / botanical | `phyllotaxis`, `voronoi_mosaic`, `space_colonization`, `reaction_diffusion` |
| Portrait photo | Painterly patches | `superpixel_hatch` |
| Portrait photo | Words as shading | `text_fill` |
| Landscape photo | Marbled topography | `noise_contours` |
| Abstract poster | Generative pattern | `truchet`, `brick`, `rings`, `sunburst`, `circle_pack`, `hitomezashi`, `cubic_disarray`, `penrose`, `curve_stitching`, `maze`, `moire`, `weave`, `honeycomb`, `harmonograph`, `attractor`, `lsystem`, `chladni` |
| Anything | Tone as structure | `quadtree`, `cubic_disarray` |
| Anything | One unbroken stroke | `tsp_opt`, `hilbert`, `gosper`, `spiral`, `string_art` |
| Anything (debug) | "Just draw it raster" | `scanlines` |

### Hidden legacy duplicates

Four algorithms stay registered (old placements and presets keep
rendering) but no longer appear in the pickers — each is covered by a
visible entry:

| Hidden | Use instead |
| --- | --- |
| `tsp` | `tsp_opt` (method `nn` is byte-identical; `nn_2opt` / `mst` are strictly better) |
| `grid` | `crosshatch` with `angle_deg: 0` + `crossed: true` |
| `eulerian_hatch` | `crosshatch` with `joined: true` |
| `contours` | `concentric_offset` (subpixel marching-squares rings vs the approximate hull walk) |

## By plot-time budget

| Budget | Avoid | Prefer |
| --- | --- | --- |
| < 5 min on A5 | TSP / flow field / Voronoi stippling | `scanlines`, `halftone`, `direct`, `truchet` |
| 10 – 20 min on A4 | Voronoi / low-poly on big sources | `stippling`, `crosshatch` (`joined: true` for fewer pen-lifts) |
| All night on A2 | (nothing — go wild) | `tsp_opt`, `flowfield`, `circle_pack`, multi-pass stacks |

The editor surfaces the live time estimate. Aim for ~1.5× the simulator's
estimate as a real-world upper bound — pen flow, paper friction and
pen-changes add up.

## By pen count

| Pens available | Strategy |
| --- | --- |
| 1 | Pick a fill algorithm (`stippling`, `crosshatch`) — tone is encoded in density |
| 2 – 3 | Run colour separation (k-means on bitmap, layer-based on vector) and assign one algorithm per layer |
| 4 + | Multi-pass per layer (e.g. crosshatch + reverse crosshatch at 45°) for depth |

## Algorithm cheat-sheet

The wizard recommends one of these for each (source, goal) pair:

- **stippling** — density follows tone; portraits, faces, fur
- **crosshatch** — angled hatches per tonal band; editorial illustrations
- **halftone** — circles on a regular grid; print-press, comics
- **flowfield** — tone-aware streamlines follow the image gradient
  (darker = denser structure); landscapes, atmosphere
- **direct** (potrace) — pure B/W outlines; logos, line art
- **edges** — edge-detected silhouettes; line drawings from photos
- **concentric_offset** — inward offset rings; maps, topography
- **scanlines** — modulated raster sweep; minimalist, glitchy
- **tsp_opt** — single tour through stipple seeds; one continuous stroke
- **hilbert / gosper** — space-filling curves; geometric / abstract
- **voronoi_stipple** — tone-aware Lloyd-relaxed stippling, dots pulled
  toward dark pixels; gallery quality
- **lowpoly** — Delaunay triangulation of sampled points; geometric portraits
- **squiggle** — wavy raster sweep; organic feel without per-stroke logic
- **circle_pack** — non-overlapping circle packing; generative art
- **etch / dither** — engraving strokes / error-diffusion dots; banknote
  and retro-print portraits
- **noise_contours** — tone isolines warped by fractal noise; marbled
  topography
- **superpixel_hatch** — per-patch hatching along local orientation;
  painterly
- **string_art** — one continuous thread between rim pegs; iconic single-line
- **text_fill** — repeated single-stroke text as the shading texture;
  typewriter-art

> **Tone awareness.** Most fill algorithms read the per-pixel luminance
> map the pipeline injects alongside the mask — dark areas get denser
> strokes or dots automatically, so the result follows the source image's
> structure rather than just the region silhouette. The 2026-06 tonal
> batch extended this to the classic fills (`crosshatch`, `halftone`,
> `stippling`, `scanlines`, `squiggle`, `scribble`, `lowpoly`, `gosper`,
> `concentric_offset`, `contours`, `eulerian_hatch`, `tsp_opt`), so the
> shaded monochrome masters shade correctly even at the default single
> luminance band instead of producing a flat uniform fill. Regions with
> no tonal contrast (logos, multicolour clusters) render exactly as
> before.

## Tuning

Each algorithm exposes a small option schema; see `GET /algorithms` (or
the `/manifests/algorithms` manifest) for the live shape. Geometry knobs
are pixel-based — they apply at segmentation resolution, not in mm.
Common knobs:

- `density` (stippling, voronoi_stipple, tsp_opt, lowpoly) — fraction of
  region pixels that become dots / sample points
- `angle_deg` (crosshatch, halftone, dashes) — primary stroke direction
- `spacing_mm` (crosshatch, scanlines, concentric_offset, moire, …) —
  raster / hatch pitch on paper (millimetres; constant across page
  formats)
- `cell_size_mm` / `cell_mm` (halftone, truchet, and other cell-based
  patterns) — pattern cell size on paper
- `dot_radius_mm` (stippling, voronoi_stipple) — pen-dot footprint
- `step_mm` (flowfield) — streamline integration step
- `iterations` (voronoi_stipple) and `method` (tsp_opt) — quality / time
  tradeoff
- `seed` (randomised algorithms) — deterministic re-rolls

Defaults are tuned to look reasonable on a Pi-class device in under a few
seconds.

## See also

- [`docs/converters.md`](../docs/converters.md) — every algorithm with kind + complexity
- [The editor](The-Editor.md)
- [Multi-pass plotting](Multi-Pass-Plotting.md)
