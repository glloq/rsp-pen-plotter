# Architecture Decision Records

Short, durable write-ups of the structural choices the project leans on. Each
ADR captures **what** was decided, **why** the alternatives lost, and **what
trade-offs that locked us into** — so future contributors can tell which
choices are accidents of history and which are load-bearing.

Format: shortened MADR. One file per decision, numbered in the filename
(`NNNN-slug.md`). Status is normally one of `accepted`, `superseded by …`,
`deprecated`. We don't usually track `proposed` here — the repo runs through
PR review so anything that landed in `adr/` is by definition accepted. The one
exception is a forward-looking *study* recorded ahead of implementation (e.g.
[0005](./0005-camera-tip-offset.md)); it carries `proposed` until the first
code lands, then flips to `accepted`.

| ADR | Status | Subject |
|---|---|---|
| [0001-svg-pivot.md](./0001-svg-pivot.md) | accepted | Every input format normalizes to a single SVG pivot |
| [0002-vpype-dependency.md](./0002-vpype-dependency.md) | accepted | Use vpype for layout / optimization / G-code emission |
| [0003-pydantic.md](./0003-pydantic.md) | accepted | Pydantic models for every API boundary + persistence schema |
| [0004-sqlite.md](./0004-sqlite.md) | accepted | SQLite (with SQLModel) for job history + audit + library metadata |
| [0005-camera-tip-offset.md](./0005-camera-tip-offset.md) | proposed | Camera-assisted per-pen XY tip offset via a dedicated measurement station |

## When to write a new ADR

Write one when the project picks an option that:

- forecloses meaningful alternatives (replacing it later is multi-PR work)
- isn't obvious from the code (the *why* takes more than a sentence)
- crosses module boundaries (it's a contract between subsystems)

Skip ADRs for tactical choices — pick a library, name a function, etc. Those
belong in the relevant module's docstring or the PR description.

## When to supersede

When an ADR no longer reflects reality, mark its status `superseded by NNNN`
and link the replacement. Don't delete: the history is the value.
