# Deployment topologies

Roadmap step **D.6**. The backend supports five process roles via
the ``OMNIPLOT_ROLE`` env var. The default — ``monolith`` — is
unchanged from v0.1 (everything in one process, suitable for a Pi
appliance). The other four roles compose into a multi-machine
deployment.

## Role matrix

| Role          | HTTP | Queue worker | Hardware | Telemetry |
|---------------|:----:|:------------:|:--------:|:---------:|
| `monolith`    |  ✓   |      ✓       |    ✓     |     —     |
| `api`         |  ✓   |      —       |    —     |     —     |
| `render`      |  —   |      ✓       |    —     |     —     |
| `executor`    |  —   |      —       |    ✓     |     —     |
| `telemetry`   |  —   |      —       |    —     |     ✓     |

Set the role with the env var::

    OMNIPLOT_ROLE=api  uvicorn pen_plotter.main:app

Capabilities are surfaced by :mod:`pen_plotter.deployment` —
:func:`resolve_role` reads the env var and the lifespan in
:mod:`pen_plotter.main` activates / skips subsystems accordingly.

## Topology examples

### Appliance (default)

A Raspberry Pi running the backend + a single plotter. Use
``OMNIPLOT_ROLE=monolith`` (or leave unset). One process owns HTTP,
the queue, and the hardware transport. This is what every existing
deployment looks like today.

### Two-machine workshop

A small studio with a server (X86 box, Mac mini, …) and one or
two plotters. Run::

    server:    OMNIPLOT_ROLE=api uvicorn pen_plotter.main:app
    plotter-1: OMNIPLOT_ROLE=executor uvicorn pen_plotter.main:app
    plotter-2: OMNIPLOT_ROLE=executor uvicorn pen_plotter.main:app

Render work still happens on the API box today (the queue worker
falls back to the API role's process pool); split it off when the
render queue grows beyond what one CPU can serve.

### Render farm + appliance

For a small print farm running compute-heavy algorithms (TSP,
voronoi_stipple, flowfield) on a workstation while the plotter
stays on the appliance::

    workstation: OMNIPLOT_ROLE=render uvicorn pen_plotter.main:app
    appliance:   OMNIPLOT_ROLE=monolith uvicorn pen_plotter.main:app

## Current limits

- The boundary is **in-process**: a non-monolith role today loads the
  components it needs and skips the others, but cross-process
  coordination still goes through the shared SQLite database. The
  follow-up that ships actual IPC (HTTP between roles, or a real
  message queue) is tracked as part of the audit #1 phase 3
  workerized compute boundary.
- Concurrent access from multiple processes to the same SQLite file
  has known limitations under heavy write contention. Use
  ``OMNIPLOT_DB=/path/to/shared.db`` on a fast local disk; switch
  to the audit-#1 Postgres adapter if you exceed it.

## Future work

- IPC between roles (HTTP between API ↔ render ↔ executor).
- Postgres adapter for the multi-machine mode (`OMNIPLOT_DB=postgres://…`).
- Tail-sampling for telemetry role in multi-machine deployments
  (roadmap A.2 decision).
