"""Dump the FastAPI OpenAPI schema to JSON.

Roadmap step **A.4**. The frontend pipeline (``openapi-typescript``,
landing alongside A.7) consumes this file to generate strict TypeScript
types for the v0.2 contract. A snapshot of the output is also embedded
at build time as the offline fallback (see ``docs/contract_architecture.md``).

Usage::

    .venv/bin/python scripts/generate_openapi.py > ../frontend/openapi.json
"""

from __future__ import annotations

import json
import sys

from pen_plotter.main import app


def main() -> int:
    """Print the OpenAPI schema to stdout."""
    schema = app.openapi()
    json.dump(schema, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
