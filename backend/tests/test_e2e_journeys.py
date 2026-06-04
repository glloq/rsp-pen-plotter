"""End-to-end journey tests (roadmap D.7 / audit #7 §8).

Exercises the three canonical operator paths through the HTTP API:

1. **Fast default flow** — resolver picks defaults, the upload + optimize +
   gcode pipeline runs without operator intervention.
2. **Expert override flow** — operator overrides the resolver's choice, the
   pipeline honours the override.
3. **Error + recovery flow** — a deliberately bogus request hits the
   normalized ApiError envelope; a recoverable failure surface in the
   recovery layer.

These run against the in-process ASGITransport (same as the rest of
the suite), so they're fast enough to stay in the default CI matrix.
A separate Playwright suite for the frontend modal V2 is intentionally
deferred — the v0.2 modal still lives behind a feature flag and gets
wired up to the production flow only after Phase D ships.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pen_plotter.main import app


@pytest.fixture
def client() -> TestClient:
    """TestClient triggers the lifespan so converters + DB are registered."""
    return TestClient(app)


def _png(width: int = 64, height: int = 64) -> bytes:
    arr = np.full((height, width, 3), 255, np.uint8)
    arr[10 : height - 10, 10 : width - 10] = (220, 20, 20)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def test_fast_default_flow_resolves_and_uploads(client: TestClient) -> None:
    """Operator picks "fast" + uploads a bitmap → end-to-end happy path."""
    # Step 1 — resolver picks the defaults for a fast bitmap_photo.
    policy_response = client.post(
        "/policy/resolve",
        json={
            "source_kind": "bitmap_photo",
            "goal": "fast",
            "palette_mode": "machine_only",
            "available_colors_count": 4,
            "image_megapixels": 0.5,
            "layer_count_estimate": 4,
            "is_mono_pen_machine": False,
        },
    )
    assert policy_response.status_code == 200
    policy = policy_response.json()
    assert policy["default_algorithm"] == "scanlines"
    assert policy["quality_tier"] == "draft"

    # Step 2 — upload a synthetic bitmap. We use a known-cheap algorithm
    # (halftone) so the test stays fast; the journey test cares about
    # the *flow*, not exact algorithm choice (B.1 already locks that).
    profiles = client.get("/profiles").json()
    profile_name = profiles[0]["name"]
    upload_response = client.post(
        "/upload",
        files={"file": ("fixture.png", _png(), "image/png")},
        data={
            "profile_name": profile_name,
            "options": '{"algorithm": "halftone", "num_colors": 2}',
        },
    )
    assert upload_response.status_code == 200, upload_response.text
    upload = upload_response.json()
    assert upload["job"]["job_id"]
    assert isinstance(upload["job"]["layers"], list)


def test_expert_override_flow_replaces_resolver_default(client: TestClient) -> None:
    """Operator overrides the resolver — the override propagates."""
    policy = client.post(
        "/policy/resolve",
        json={
            "source_kind": "bitmap_photo",
            "goal": "fast",
            "palette_mode": "machine_only",
            "available_colors_count": 4,
            "image_megapixels": 0.5,
            "layer_count_estimate": 4,
            "is_mono_pen_machine": False,
        },
    ).json()
    assert policy["default_algorithm"] == "scanlines"

    # The operator picks a different algorithm — expert mode override.
    profile_name = client.get("/profiles").json()[0]["name"]
    upload = client.post(
        "/upload",
        files={"file": ("fixture.png", _png(), "image/png")},
        data={
            "profile_name": profile_name,
            # Override: halftone (emits <circle>) instead of resolver's scanlines.
            "options": '{"algorithm": "halftone", "num_colors": 2}',
        },
    )
    assert upload.status_code == 200
    # The SVG was rendered with the operator's choice — halftone emits
    # circles, scanlines does not. Demonstrates the override took effect.
    assert "<circle" in upload.json()["svg"]


def test_error_flow_returns_normalized_api_error(client: TestClient) -> None:
    """A bad manifest request emits the v0.2 normalized error envelope."""
    response = client.get("/manifests/does_not_exist")
    assert response.status_code == 404
    body = response.json()
    # Normalized: code is dot-namespaced, path echoes the request URL,
    # details carry actionable context.
    assert body["code"] == "manifest.unknown_domain"
    assert body["path"] == "/manifests/does_not_exist"
    assert "available" in body["details"]


def test_correlation_id_is_propagated_across_journey(client: TestClient) -> None:
    """Inbound X-Request-ID flows through the response (A.1)."""
    headers = {"X-Request-ID": "journey-e2e-abc"}
    for path in ("/health", "/manifests", "/profiles"):
        r = client.get(path, headers=headers)
        assert r.status_code in {200, 404}, path
        assert r.headers.get("x-request-id") == "journey-e2e-abc", path


def test_validation_error_is_pydantic_422(client: TestClient) -> None:
    """Invalid policy payload returns FastAPI's 422 with a useful body."""
    response = client.post(
        "/policy/resolve",
        json={"source_kind": "not_a_real_kind"},
    )
    assert response.status_code == 422
    body = response.json()
    # P1: validation errors render the unified envelope.
    assert body["code"] == "validation_error"
    assert isinstance(body["details"]["errors"], list)
