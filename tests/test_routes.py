"""Route-level tests for the Flask generator UI."""
import io
import zipfile

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


def test_generate_returns_zip(client):
    res = client.post(
        "/generate",
        data={
            "project_name": "My App",
            "backend": "flask",
            "frontend": "vanilla",
            "database": "sqlite",
            "styling": "bootstrap",
        },
    )
    assert res.status_code == 200
    assert res.mimetype == "application/zip"
    assert "my-app.zip" in res.headers["Content-Disposition"]

    zf = zipfile.ZipFile(io.BytesIO(res.data))
    names = zf.namelist()
    assert any(n.endswith("app.py") for n in names)
    assert any(n.endswith("index.html") for n in names)
    assert any(n.endswith("db.py") for n in names)
    assert "my-app/README.md" in names


def test_generate_rejects_invalid_selection(client):
    res = client.post(
        "/generate",
        data={
            "project_name": "x",
            "backend": "none",
            "frontend": "none",
            "database": "none",
            "styling": "plain",
        },
    )
    assert res.status_code == 400
    assert "at least a backend or a frontend" in res.get_data(as_text=True).lower()
