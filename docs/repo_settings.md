# Repository settings — branch protection

> Why this document exists: two successive audits
> (`audit_projet_2026-07-15.md`, `audit_exhaustif_2026-07-19.md`) found
> the `main` CI red **for weeks** without anyone noticing — first for
> mypy/prettier gates, then for a stale manifest snapshot. The local
> test suites pass, so nothing surfaces the breakage during normal
> development. Branch protection makes a red gate block the merge
> instead of rotting silently. These are GitHub *repository settings*;
> they cannot be enabled from code, so this page documents the exact
> configuration for the repo admin.

## Required status checks on `main`

GitHub → **Settings → Branches → Add branch ruleset** (or classic
*Branch protection rules*), pattern `main`:

1. **Require status checks to pass before merging** — enable, and mark
   as required:
   - `Backend — lint + type + tests`
   - `Frontend — lint + type + tests + build`
   - `E2E — Playwright (modal V2 + operator + editor parcours)`
2. **Require branches to be up to date before merging** — enable.
   The drift gates (OpenAPI snapshot, TS types, manifest snapshot)
   compare generated artifacts against the committed ones, so a PR
   branched before a contract change can be green on its own commit
   yet stale against `main`. Requiring up-to-date branches re-runs the
   gates against the merged state.
3. Leave force-push and deletion disabled (the default).

No other rule is needed: reviews stay at the maintainer's discretion,
and the CI jobs above already cover lint, types, tests, contract
drift and the operator E2E parcours.

## Why not enforce from CI

A workflow cannot protect the branch it runs on — by the time CI runs,
the merge already happened. The `concurrency` group in `ci.yml` and
the drift gates are already as strict as code can be; the missing
piece is the merge-blocking bit, which only lives in repository
settings.
