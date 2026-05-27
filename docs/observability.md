# Observability

This document describes the backend observability primitives introduced
by step **A.1** of `docs/ROADMAP_V0.2.md`: structured JSON logging and
correlation IDs propagated across the request lifecycle.

OpenTelemetry tracing (step A.2) and detailed pipeline spans (B.5) land
on top of the same context layer.

---

## Structured JSON logs

Every log record is emitted as a single JSON object on stderr with this
schema:

| Field         | Type    | Description                                              |
|---------------|---------|----------------------------------------------------------|
| `ts`          | string  | ISO-8601 UTC timestamp                                   |
| `level`       | string  | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`      |
| `logger`      | string  | Qualified logger name (e.g. `pen_plotter.queue`)         |
| `msg`         | string  | Formatted log message                                    |
| `exc`         | string  | Formatted traceback when `logger.exception(...)` is used |
| correlation\* | string  | Bound correlation fields (see below) — included if set   |
| extras        | any     | Any field passed via `logger.info(..., extra={...})`     |

Sensitive keys are redacted before serialization (case-insensitive
match on the key, value replaced by `***`):

`api_key`, `authorization`, `password`, `secret`, `token`, `x-api-key`.

### Configuration

| Env var                  | Default | Effect                                            |
|--------------------------|---------|---------------------------------------------------|
| `OMNIPLOT_LOG_LEVEL`     | `INFO`  | Root log level (`DEBUG`/`INFO`/`WARNING`/...)     |
| `OMNIPLOT_LOG_FORMAT`    | `json`  | `json` for structured output, `text` for legacy   |

Logging is configured at import time in `pen_plotter.main`. Re-importing
or calling `configure_logging()` again is a no-op unless `force=True`.

---

## Correlation IDs

A fixed set of correlation fields is propagated through
`contextvars.ContextVar` so each async task naturally inherits the
context of its caller. The canonical list lives in
`pen_plotter.observability.context.CORRELATION_FIELDS`:

- `request_id`   — one HTTP request (mint or accept `X-Request-ID`)
- `job_id`       — one upload / conversion job
- `run_id`       — one machine execution run
- `placement_id` — one placement of a job on the sheet
- `algorithm_id` — current render algorithm (e.g. `stippling`)
- `quality_tier` — `draft` / `standard` / `final`
- `profile_name` — machine profile in effect
- `source_kind`  — `bitmap_photo` / `bitmap_illustration` / `vector_svg` / ...

Adding a new field requires editing `CORRELATION_FIELDS` and the
internal `_VARS` mapping — the API rejects unknown names on purpose.

### Binding context in code

```python
from pen_plotter.observability import bind_context, clear_context

tokens = bind_context(job_id=job.id, algorithm_id="crosshatch")
try:
    do_the_work()
finally:
    clear_context(tokens)
```

Every log record emitted inside the `try` block will carry both
`job_id` and `algorithm_id` automatically.

### HTTP requests

`RequestContextMiddleware` mints a UUID4 for each incoming request (or
accepts an inbound `X-Request-ID` header) and binds it for the duration
of the call. The same value is echoed on the response so clients can
quote it when reporting an issue.

A single `http_request` access log line is emitted at the end of each
request with `method`, `path`, `status`, and `elapsed_ms`.

---

---

## Distributed tracing (OpenTelemetry)

Tracing is **opt-in** and a no-op until `OMNIPLOT_OTEL_ENABLED=1`. When
enabled, the backend installs a `TracerProvider` with 100 % sampling
(appliance default; multi-machine deployments will switch to
tail-sampling in roadmap step D.6) and instruments the FastAPI app so
every route receives a server span automatically.

### Configuration

| Env var                   | Default                              | Effect                              |
|---------------------------|--------------------------------------|-------------------------------------|
| `OMNIPLOT_OTEL_ENABLED`   | unset (disabled)                     | Set to `1` to activate tracing      |
| `OMNIPLOT_OTEL_EXPORTER`  | `otlp`                               | `otlp` or `console`                 |
| `OMNIPLOT_OTLP_ENDPOINT`  | `http://localhost:4318/v1/traces`    | OTLP HTTP target                    |
| `OMNIPLOT_SERVICE_NAME`   | `omniplot-backend`                   | `service.name` on the OTel resource |

### Pipeline spans

The conversion pipeline emits the following spans today (more to come
in roadmap step B.5):

- `pipeline.convert_file` — overall conversion, attributes:
  `mime`, `size_bytes`, `filename` (+ correlation context)
- `pipeline.segment_and_render` — bitmap converters only
- `pipeline.convert` — non-bitmap converters, attribute: `converter`
- `pipeline.sanitize_svg` / `pipeline.extract_layers`
- `pipeline.optimize_svg` — attributes: `svg_bytes`, `layer_count`
- `pipeline.generate_gcode` — attributes: `svg_bytes`, `profile_name`, `scale_mode`

### Adding a span at a call site

```python
from pen_plotter.observability import traced_span

with traced_span("phase.my_step", count=n, layer="red"):
    do_work()
```

When tracing is disabled, `traced_span` is a true no-op — no SDK calls,
no allocations beyond the nullcontext. Currently bound correlation
fields are copied onto every span as attributes so traces stay
correlated with the JSON logs from A.1.

---

## Performance baseline

`scripts/perf_baseline.py` runs deterministic synthetic fixtures and
emits a markdown table of p50/p95/p99 per pipeline phase. See
`docs/perf-baseline.md` for the captured snapshot and how to reproduce
it. Future refactors must update that document with the new numbers
in the same PR.

---

## Future work

- **B.5** — Sub-step spans for parse/preprocess/segmentation/render/optimize/gcode (finer than today).
- **D.1** — py-spy profiling activable, flamegraphs reproductibles.
- **D.4** — SLO budgets et alerting sur ces signaux.
