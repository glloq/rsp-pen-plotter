# Bundled plotter presets

Roadmap step **B.6**. The presets below ship with the backend; a user
profile in `OMNIPLOT_PROFILES_DIR` with the same `name` overrides the
bundled version.

## Capability matrix

| Preset                       | Dialect | Workspace        | Magazine | Tool-change mode | Command source | Arcs |
|------------------------------|---------|------------------|----------|------------------|----------------|------|
| **AxiDraw V3**               | `ebb`   | 300 × 218 mm     |        1 | `manual` (derived) | `operator`   | —    |
| **NextDraw A2**              | `ebb`   | 595 × 419 mm     |        1 | `manual` (explicit) | `operator`  | —    |
| **iDraw A3 (GRBL)**          | `grbl`  | 420 × 297 mm     |        1 | `manual` (explicit) | `operator`  | ✓    |
| **Custom CoreXY A3**         | `grbl`  | 300 × 420 mm     |        6 | `manual` (derived) | `operator`   | ✓    |
| **Custom CoreXY A3 (rack)**  | `grbl`  | 300 × 420 mm     |        6 | `host_macro` (explicit) | `host`  | ✓    |

"Derived" means the v0.2 Capability Model is inferred from
`tool_change_method` at load time (A.5 migration). "Explicit" means
the YAML carries a full `capabilities:` block that wins over the
legacy field.

## Notes per preset

### AxiDraw V3 — `axidraw_v3.yaml`

Reference AxiDraw V3 with the stock servo & EBB calibration. Emits
native EBB commands (`SM`/`SP`/`EM`/`SC`), not G-code. Single-pen
manual swap workflow.

### NextDraw A2 — `nextdraw.yaml`

Bantam Tools NextDraw. Same EBB controller class as the AxiDraw,
different workspace and pen-down servo target. Demonstrates an
**explicit** Capability Model block — the YAML overrides the default
manual prompt body to mention the machine by name. Useful as a
template for other EBB-class machines with a custom holder.

### iDraw A3 (GRBL) — `idraw_a3.yaml`

iDraw / EleksDraw class plotter on a GRBL controller. Servo pen lift
via `M03 S<value>` (the standard hack for a hobby servo on a GRBL
laser controller). G2/G3 arc support enabled.

### Custom CoreXY A3 — `custom_plotter.yaml`

DIY CoreXY reference design. Six-slot magazine but **manual** swap
mode — the YAML doesn't define a swap macro, so the orchestrator
prompts the operator at each layer change.

### Custom CoreXY A3 (rack) — `corexy_rack_demo.yaml`

Same hardware as above but with an **explicit** `host_macro`
capability block. Demonstrates the full v0.2 host-managed swap mode:
the orchestrator streams the YAML-defined sequence verbatim
(comments + travel moves + servo commands) with `wait_ms` between
sends. Placeholders `{slot}`, `{color}`, `{label}`, `{layer}` are
substituted from the active `SwapContext`.

This is the canonical example for **adding a host-driven swap macro
to your own DIY plotter** — copy it, change the workspace + pin
assignments, leave the macro structure alone.

## How to add a new preset

1. Drop a YAML file in `backend/pen_plotter/profiles/` (or in
   `OMNIPLOT_PROFILES_DIR` for a user-private preset).
2. Required fields are documented in `docs/profile_format.md`.
3. For a non-manual swap mode, define a `capabilities.tool_change`
   block per the schema in `docs/profile_format.md` § Capability Model.
4. Add a row to the matrix above + a "Notes per preset" entry.
5. Add a smoke test in `backend/tests/test_bundled_profiles.py` if
   the preset exercises a path the existing tests don't cover (new
   dialect, new tool-change mode, new feature flag).
