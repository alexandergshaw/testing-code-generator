"""Route-level tests for the Flask generator UI shell.

Generation now runs entirely through the JSON API (see tests/test_http_api.py);
the UI is a client of it. These tests cover the rendered shell only.
"""
import pytest

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


def test_index_lists_axes(client):
    res = client.get("/")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "Backend framework" in body
    assert "Frontend framework" in body


def test_index_has_structure_controls(client):
    body = client.get("/").get_data(as_text=True)
    assert "Project structure" in body          # layout/root controls
    assert "Files &amp; folders" in body         # custom files editor
    assert 'src="/js/structure.js"' in body


def test_generate_form_route_removed(client):
    # The old form-POST endpoint is gone; the UI uses POST /api/generate instead.
    assert client.post("/generate", data={}).status_code in (404, 405)
