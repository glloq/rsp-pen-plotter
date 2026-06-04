"""HTTPException, validation and ApiError all render the same envelope.

Covers P1 from the v0.2 audit: legacy v0.1 endpoints raise
``HTTPException`` while v0.2+ endpoints raise :class:`ApiError`. The
global handlers normalize both into the ``{code, message, details,
path}`` shape so the SPA only handles one form.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from pen_plotter.errors import ApiError, install_error_handler


def _app() -> FastAPI:
    app = FastAPI()
    install_error_handler(app)

    @app.get("/legacy-string")
    def legacy_string() -> None:
        raise HTTPException(status_code=404, detail="Unknown profile")

    @app.get("/legacy-list")
    def legacy_list() -> None:
        raise HTTPException(status_code=400, detail=[{"loc": "x", "msg": "bad"}])

    @app.get("/legacy-dict")
    def legacy_dict() -> None:
        raise HTTPException(
            status_code=409, detail={"message": "busy", "reason": "printing"}
        )

    @app.get("/modern")
    def modern() -> None:
        raise ApiError(
            code="manifest.unknown",
            message="no manifest for domain 'bogus'",
            status_code=400,
            details={"domain": "bogus"},
        )

    class Payload(BaseModel):
        n: int

    @app.post("/validated")
    def validated(payload: Payload) -> Payload:
        return payload

    return app


def test_http_exception_string_detail_normalized() -> None:
    client = TestClient(_app())
    res = client.get("/legacy-string")
    assert res.status_code == 404
    body = res.json()
    assert body == {
        "code": "not_found",
        "message": "Unknown profile",
        "details": {},
        "path": "/legacy-string",
    }


def test_http_exception_list_detail_moves_to_details() -> None:
    client = TestClient(_app())
    res = client.get("/legacy-list")
    assert res.status_code == 400
    body = res.json()
    assert body["code"] == "bad_request"
    assert body["message"] == "validation_error"
    assert body["details"]["errors"] == [{"loc": "x", "msg": "bad"}]


def test_http_exception_dict_detail_picks_message() -> None:
    client = TestClient(_app())
    res = client.get("/legacy-dict")
    assert res.status_code == 409
    body = res.json()
    assert body["code"] == "conflict"
    assert body["message"] == "busy"
    assert body["details"] == {"reason": "printing"}


def test_api_error_preserves_explicit_code() -> None:
    client = TestClient(_app())
    res = client.get("/modern")
    assert res.status_code == 400
    body = res.json()
    assert body == {
        "code": "manifest.unknown",
        "message": "no manifest for domain 'bogus'",
        "details": {"domain": "bogus"},
        "path": "/modern",
    }


def test_request_validation_error_renders_envelope() -> None:
    client = TestClient(_app())
    res = client.post("/validated", json={"n": "not-a-number"})
    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "validation_error"
    assert body["message"] == "request validation failed"
    assert isinstance(body["details"]["errors"], list)
    assert body["path"] == "/validated"
