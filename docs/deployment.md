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
- **Don't ship a multi-role topology to production yet.** The role
  matrix above is wired and tested in-process, but until IPC lands a
  multi-machine deployment relies on the shared SQLite file as its
  only synchronization channel — fine for development, not for a
  shared studio. Stay on `monolith` until phase 3.
- Concurrent access from multiple processes to the same SQLite file
  has known limitations under heavy write contention. Use
  ``OMNIPLOT_DB=/path/to/shared.db`` on a fast local disk; switch
  to the audit-#1 Postgres adapter if you exceed it.

## Production hardening

OmniPlot is built for a single machine on a trusted LAN. The defaults
make a fresh install runnable with zero configuration, which is the
wrong posture for a workshop that anyone on the network can reach.
Apply the four steps below before exposing the appliance to a shared
network — and never expose it directly to the public internet.

### 1. Require authentication

Generate a strong secret (32+ random characters) and configure both
env vars in your systemd unit / `.env.service`:

```ini
OMNIPLOT_API_KEY=<secret>
OMNIPLOT_REQUIRE_AUTH=1
```

`OMNIPLOT_REQUIRE_AUTH=1` makes the service **refuse to start** if
the key is missing — so an accidental restart without the secret
cannot silently come up with the plotter controls open. With a key
configured, every router (uploads, files, profiles, macros, generate,
queue, plotter, system, …) requires the key on the `X-API-Key`
header or the `token=` query parameter; only `/health` and the
static SPA stay open so a browser can land on the login screen.

### 2. Terminate TLS at a reverse proxy

The FastAPI process speaks plain HTTP. For any deployment beyond
`localhost`, terminate TLS in a reverse proxy on the same host —
Caddy and nginx are both fine. Minimal Caddy example:

```caddy
plotter.local {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8000
}
```

Point `OMNIPLOT_CORS_ORIGINS` at the public origin
(`https://plotter.local`) so browsers from other LAN devices can
reach the API. Wildcard CORS origins (`*`) are rejected at startup
because they cannot legally combine with credentialed requests.

The reverse proxy is also the right place to add a
`Content-Security-Policy` header if your environment needs one;
the SPA renders sanitized SVG via `v-html`, so a CSP shipped from
the backend would have to permit `unsafe-inline` styles and
defeat much of the point. The backend already sets the safe trio
(`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`) on every response.

### 3. Backups

Three on-disk pieces of state need to be backed up:

| What | Where | Why |
| --- | --- | --- |
| Job + audit DB | `backend/data/omniplot.db` (override with `OMNIPLOT_DB`) | Queue, runs, audit trail. |
| Uploaded files | `backend/data/files/` (override with `OMNIPLOT_FILES_DIR`) | Originals + previews. |
| Macros | `backend/data/macros.json` (override with `OMNIPLOT_MACROS_FILE`) | Operator-defined commands. |
| Machine profiles | bundled in the package + any custom YAML | Recreate from VCS. |

Stop the service before copying the SQLite file to avoid a partial
read. A minimal nightly backup:

```sh
systemctl stop omniplot
tar czf /backup/omniplot-$(date +%F).tgz \
    backend/data/omniplot.db \
    backend/data/files \
    backend/data/macros.json
systemctl start omniplot
```

Restore by stopping the service, replacing the three paths with the
archived contents, and starting again. There is no migration story
yet, so always restore into the same OmniPlot version that produced
the archive.

### 4. Self-update

`POST /system/update` is guarded by the API key and shells out to
`update.sh`. Set `OMNIPLOT_DISABLE_UPDATE=1` to remove the endpoint
entirely if your appliance should only be updated by hand on the
host.

## Future work

- IPC between roles (HTTP between API ↔ render ↔ executor).
- Postgres adapter for the multi-machine mode (`OMNIPLOT_DB=postgres://…`).
- Tail-sampling for telemetry role in multi-machine deployments
  (roadmap A.2 decision).
