"""Shared per-request upload size cap for the upload-accepting endpoints.

Single home for the ``OMNIPLOT_MAX_UPLOAD_MB`` resolution previously
duplicated verbatim in ``api/upload.py`` and ``api/files.py``.
"""

from __future__ import annotations

import os

_DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def max_upload_bytes() -> int:
    """Return the per-request body cap, configurable via env var.

    ``OMNIPLOT_MAX_UPLOAD_MB`` (positive integer) overrides the default
    50 MB. Resolved at call time so tests can monkeypatch the env var
    without re-importing the module.
    """
    raw = os.environ.get("OMNIPLOT_MAX_UPLOAD_MB", "").strip()
    if raw:
        try:
            mb = int(raw)
            if mb > 0:
                return mb * 1024 * 1024
        except ValueError:
            pass
    return _DEFAULT_MAX_UPLOAD_BYTES
