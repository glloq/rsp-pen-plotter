# 0004 — SQLite (via SQLModel) for jobs, audit, and library metadata

- **Status**: accepted
- **Date**: 2024-09 (back-dated)

## Context

OmniPlot persists three categories of data on the host:

1. **Job history**: every `/generate` round-trip captures its input plan,
   resolved plan, hash, options snapshot, and the resulting G-code path
   for replay.
2. **Audit log**: immutable trail of operator-visible events (uploads,
   deletes, rerenders, profile edits) for diagnosis + compliance.
3. **Library metadata**: a row per uploaded source file —
   `source_file` name, `source_mime`, `size_bytes`, `folder`, `layer_count`,
   the SVG / segmentation result paths on disk, the `last_options` snapshot
   the rerender cache reads.

We don't persist large blobs in the database — those live in
`storage/files/<file_id>/` on disk and are pointed at by integer ids in
the rows.

Options on the table:

1. **Flat JSON files** under `storage/`. Easy to bootstrap, awful once you
   need to scan the library for "files in folder X" or "jobs in the last
   24h" or to enforce referential integrity between jobs and library
   entries.
2. **SQLite** + SQLAlchemy / SQLModel. Single file, zero install, ACID,
   first-class query support, file-system backups work.
3. **PostgreSQL.** Industrial-strength, but requires a separate daemon and
   a non-trivial install on the Pi target. Overkill for a single-host
   application.
4. **A document store (TinyDB, JSON-LD).** Lightweight but no schema
   enforcement, no foreign keys, no triggers (which we use for the audit
   log immutability — see below).

## Decision

Use **SQLite via SQLModel**, with the database living at
`storage/omniplot.sqlite`. SQLModel gives us Pydantic-compatible row
models (see [ADR 0003](./0003-pydantic.md)) and lets the API layer reuse
the same class for "wire shape" and "DB row".

Schema migrations are managed by hand-written `ALTER TABLE` scripts in
`persistence.py::ensure_schema`. We accepted a manual approach because:

- The migration footprint is tiny (a few new columns per release).
- Alembic adds another moving piece for a single-developer-friendly project.
- Each migration runs once at boot and is idempotent.

The audit log enforces immutability **at the SQLite level**, via
`BEFORE UPDATE` / `BEFORE DELETE` triggers that `RAISE` (added in the
phase-4 security hardening lot). Application-level append-only would have
been bypassable from any new code path; the trigger is a single source of
truth.

## Consequences

### Positive

- **Single file, atomic backups.** A `cp omniplot.sqlite omniplot.bak`
  during a quiescent period is a complete snapshot. Operators love this.
- **No service to manage.** No daemons, no ports, no service files. SQLite
  is in-process.
- **ACID + foreign keys give us referential integrity.** Library entries
  reference jobs; jobs reference plans; placements reference library
  files. We rely on these to drive the GET `/files/integrity` boot scan.
- **Triggers for invariants.** The audit-log immutability is a
  database-level guarantee. Code paths that try to mutate the table fail
  fast at the boundary.
- **Concurrent reads are fine.** SQLite's WAL mode gives us many readers
  + one writer; the API is sequential per request so contention is
  negligible.

### Negative

- **Single-writer bottleneck.** SQLite serializes writes. For a single-host
  pen plotter this is fine; if we ever ran multiple OmniPlot instances
  pointing at the same store, this'd be the first thing to fall over.
- **mypy + SQLModel was the worst typing story we shipped.** Several
  modules carry per-file `ignore_errors` flags. The L12 lot in the audit
  is dedicated to extracting a repository pattern that fixes this without
  changing the persistence layer.
- **No native JSON columns until SQLite 3.38+.** We serialize complex
  options (e.g. `last_options`) as TEXT and parse them in Python. Hot
  query paths cope; if we ever needed to filter inside a JSON blob this
  would be a problem.
- **VACUUM is operator-managed.** We don't auto-shrink on file delete;
  the database file grows then plateaus. Mitigated by the fact that no
  blob lives in the DB.

## What this rules out for now

- **Multi-host deployment.** SQLite is host-local. Moving to a service
  deployment with a queue would require swapping for PostgreSQL — flagged
  as a Future Lot if the project ever serves more than one operator at
  once.
- **Live remote backups.** SQLite supports the [Backup
  API](https://www.sqlite.org/backup.html) for hot copies, but we haven't
  wired that into the surface yet; operators rely on file-level copies
  during quiet windows.

## Alternatives we still reject

A flat-JSON store would be simpler for the first release and a nightmare
by the time the library has 500 entries. We saw that exact failure mode in
an earlier prototype.

PostgreSQL would let us scale horizontally but the operational cost (a
daemon to install, a port to firewall, a backup schedule to maintain) is
not justified for a single-host plotter studio.
