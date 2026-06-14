"""Auth axis: JWT login/me render per backend and are gated to backends."""
import pytest

from generator.composer import compose
from generator.errors import InvalidSelection

# backend id -> the file its server code lands in
BACKEND_FILE = {
    "flask": "app.py",
    "fastapi": "main.py",
    "express": "server.js",
    "nethttp": "main.go",
}


def _server(backend, auth):
    tree = compose(
        {"backend": backend, "frontend": "none", "database": "none",
         "styling": "plain", "auth": auth},
        "App",
    )
    return next(tree[p] for p in tree if p.endswith(BACKEND_FILE[backend])).decode()


@pytest.mark.parametrize("backend", list(BACKEND_FILE))
def test_jwt_adds_login_and_me(backend):
    blob = _server(backend, "jwt")
    assert "/api/login" in blob
    assert "/api/me" in blob
    assert "HS256" in blob


@pytest.mark.parametrize("backend", list(BACKEND_FILE))
def test_no_auth_has_no_login(backend):
    blob = _server(backend, "none")
    assert "/api/login" not in blob


def test_jwt_requires_a_backend():
    with pytest.raises(InvalidSelection):
        compose(
            {"backend": "none", "frontend": "react", "database": "none",
             "styling": "plain", "auth": "jwt"},
            "App",
        )
