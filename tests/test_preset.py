"""Preset round-trip, stackgen.json emission, and the JSON generate API."""
import io
import json
import zipfile

import pytest

from app import app as flask_app
from generator import preset
from generator.composer import compose
from generator.errors import InvalidSelection

CONFIG = {
    "version": 1,
    "project_name": "Shop",
    "stack": {"backend": "flask", "frontend": "vanilla",
              "database": "sqlite", "styling": "bootstrap", "auth": "none", "api": "rest"},
    "addons": ["docker", "tests"],
    "schema": [{"name": "Product", "fields": [{"name": "title", "type": "string"}]}],
}


@pytest.fixture
def client():
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


def test_to_from_config_round_trip():
    name, selection, addons, schema = preset.from_config(CONFIG)
    rebuilt = preset.to_config(name, selection, addons, schema)
    assert rebuilt == CONFIG


def test_encode_decode_round_trip():
    assert preset.decode(preset.encode(CONFIG)) == CONFIG


def test_decode_bad_token_raises():
    with pytest.raises(InvalidSelection):
        preset.decode("!!!not-base64!!!")


@pytest.mark.parametrize("bad", [
    {"version": 99, "stack": {}},
    {"version": 1, "stack": {"backend": "flask"}},  # missing axes
    {"version": 1, "stack": {"backend": "flask", "frontend": "none",
                             "database": "none", "styling": "plain"},
     "addons": "nope"},
])
def test_from_config_rejects_malformed(bad):
    with pytest.raises(InvalidSelection):
        preset.from_config(bad)


def test_stackgen_json_in_zip():
    tree = compose(CONFIG["stack"], "Shop",
                   schema=CONFIG["schema"], addons=CONFIG["addons"])
    blob = tree["shop/stackgen.json"]
    saved = json.loads(blob)
    assert saved["stack"] == CONFIG["stack"]
    assert saved["schema"] == CONFIG["schema"]
    assert "docker" in saved["addons"] and "tests" in saved["addons"]


def test_api_generate_returns_zip(client):
    res = client.post("/api/generate", json=CONFIG)
    assert res.status_code == 200
    assert res.mimetype == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(res.data)).namelist()
    assert "shop/stackgen.json" in names
    assert any(n.endswith("Dockerfile") for n in names)  # docker add-on applied


def test_api_generate_rejects_bad_config(client):
    assert client.post("/api/generate", json={"version": 1}).status_code == 400
    assert client.post("/api/generate", data="notjson").status_code == 400


def test_index_prefills_from_share_link(client):
    token = preset.encode(CONFIG)
    res = client.get(f"/?c={token}")
    assert res.status_code == 200
    assert "Shop" in res.get_data(as_text=True)
