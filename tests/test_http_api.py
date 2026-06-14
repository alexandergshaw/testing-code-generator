"""HTTP API surface: /api/generate (zip), /api/health, /api/options, CORS, key."""
import io
import zipfile

import pytest

from app import app


@pytest.fixture
def client():
    app.config.update(TESTING=True)
    return app.test_client()


def _names(resp):
    return zipfile.ZipFile(io.BytesIO(resp.data)).namelist()


# --------------------------------------------------------------------------- #
# /api/generate
# --------------------------------------------------------------------------- #
def test_generate_minimal_body_returns_zip(client):
    resp = client.post("/api/generate", json={})  # all defaults
    assert resp.status_code == 200
    assert resp.mimetype == "application/zip"
    assert any(n.endswith("README.md") for n in _names(resp))


def test_generate_nested_stack_config(client):
    resp = client.post("/api/generate", json={
        "project_name": "shop",
        "stack": {"backend": "fastapi", "frontend": "react", "database": "sqlite"},
        "schema": [{"name": "Product", "fields": [{"name": "title", "type": "string", "required": True}]}],
    })
    assert resp.status_code == 200
    names = _names(resp)
    assert any(n.endswith("main.py") for n in names)        # FastAPI backend
    assert "shop.zip" in resp.headers.get("Content-Disposition", "")


def test_generate_flat_body_also_works(client):
    resp = client.post("/api/generate", json={"backend": "express", "project_name": "api"})
    assert resp.status_code == 200
    assert any(n.endswith("server.js") for n in _names(resp))


def test_generate_with_custom_structure(client):
    resp = client.post("/api/generate", json={
        "project_name": "cs101",
        "stack": {"backend": "flask"},
        "structure": {
            "root": "cs101",
            "layout": "monorepo",
            "files": [{"path": "assignments/hw1/README.md", "content": "# HW1"}],
        },
    })
    assert resp.status_code == 200
    names = _names(resp)
    assert "cs101/apps/api/app.py" in names                 # monorepo dir
    assert "cs101/assignments/hw1/README.md" in names       # injected file


def test_generate_bad_structure_is_json_400(client):
    resp = client.post("/api/generate", json={
        "stack": {"backend": "flask"},
        "structure": {"files": [{"path": "../escape", "content": "x"}]},
    })
    assert resp.status_code == 400
    assert resp.is_json and "error" in resp.get_json()


def test_generate_invalid_stack_is_json_400(client):
    resp = client.post("/api/generate", json={"stack": {"backend": "django", "database": "sqlite"}})
    assert resp.status_code == 400
    assert resp.is_json and "error" in resp.get_json()


def test_generate_non_json_is_json_400(client):
    resp = client.post("/api/generate", data="not json", content_type="text/plain")
    assert resp.status_code == 400
    assert resp.is_json and "error" in resp.get_json()


def test_generate_wrong_method_is_json_error(client):
    # GET on the POST-only endpoint: the root-mounted static handler shadows it,
    # so this is a 404 (not 405) — but still a JSON error, never HTML or a zip.
    resp = client.get("/api/generate")
    assert resp.status_code in (404, 405)
    assert resp.is_json and "error" in resp.get_json()


# --------------------------------------------------------------------------- #
# Env-gated API key
# --------------------------------------------------------------------------- #
def test_api_key_enforced_only_when_configured(client, monkeypatch):
    # No env var -> open.
    assert client.post("/api/generate", json={}).status_code == 200

    monkeypatch.setenv("API_KEY", "s3cret")
    assert client.post("/api/generate", json={}).status_code == 401              # missing
    assert client.post("/api/generate", json={}, headers={"x-api-key": "nope"}).status_code == 401
    ok = client.post("/api/generate", json={}, headers={"x-api-key": "s3cret"})
    assert ok.status_code == 200 and ok.mimetype == "application/zip"


def test_api_key_does_not_gate_discovery(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "s3cret")
    assert client.get("/api/health").status_code == 200    # health stays open
    assert client.get("/api/options").status_code == 200   # discovery stays open


# --------------------------------------------------------------------------- #
# Discovery / health / openapi
# --------------------------------------------------------------------------- #
def test_health(client):
    body = client.get("/api/health").get_json()
    assert body["status"] == "ok" and "version" in body


def test_options_catalog(client):
    body = client.get("/api/options").get_json()
    assert "backend" in body["axes"]
    backend_ids = [o["id"] for o in body["options"]["backend"]]
    assert {"flask", "django", "express"} <= set(backend_ids)
    assert "tags" in body and "field_types" in body and "defaults" in body


def test_openapi_served(client):
    resp = client.get("/api/openapi.json")
    assert resp.status_code == 200
    assert resp.get_json()["openapi"].startswith("3.")


# --------------------------------------------------------------------------- #
# CORS
# --------------------------------------------------------------------------- #
def test_cors_preflight(client):
    resp = client.open("/api/generate", method="OPTIONS")
    assert resp.status_code == 204
    assert resp.headers["Access-Control-Allow-Origin"] == "*"
    assert "x-api-key" in resp.headers["Access-Control-Allow-Headers"]


def test_cors_header_on_response(client):
    resp = client.post("/api/generate", json={})
    assert resp.headers["Access-Control-Allow-Origin"] == "*"


def test_ui_routes_have_no_cors_header(client):
    # The HTML UI is same-origin only; CORS headers are scoped to /api/*.
    assert "Access-Control-Allow-Origin" not in client.get("/").headers
