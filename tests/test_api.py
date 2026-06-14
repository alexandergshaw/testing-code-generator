"""API-style axis: GraphQL renders for Python backends and is tag-gated."""
import pytest

from generator.composer import compose
from generator.errors import InvalidSelection

BACKEND_FILE = {"flask": "app.py", "fastapi": "main.py"}


def _tree(backend, api, database="none"):
    return compose(
        {"backend": backend, "frontend": "none", "database": database,
         "styling": "plain", "auth": "none", "api": api},
        "App",
    )


def _server(backend, api, database="none"):
    tree = _tree(backend, api, database)
    return next(tree[p] for p in tree if p.endswith(BACKEND_FILE[backend])).decode()


@pytest.mark.parametrize("backend", list(BACKEND_FILE))
def test_graphql_renders_and_folds_dependency(backend):
    blob = _server(backend, "graphql")
    assert "/graphql" in blob
    assert "strawberry" in blob
    tree = _tree(backend, "graphql")
    reqs = next(tree[p] for p in tree if p.endswith("requirements.txt")).decode()
    assert "strawberry-graphql" in reqs


@pytest.mark.parametrize("backend", list(BACKEND_FILE))
def test_rest_has_no_graphql(backend):
    assert "/graphql" not in _server(backend, "rest")


def test_graphql_requires_python_backend():
    for backend in ("express", "nethttp"):
        with pytest.raises(InvalidSelection):
            compose(
                {"backend": backend, "frontend": "none", "database": "none",
                 "styling": "plain", "auth": "none", "api": "graphql"},
                "App",
            )


def test_graphql_requires_no_database():
    with pytest.raises(InvalidSelection):
        compose(
            {"backend": "flask", "frontend": "none", "database": "sqlite",
             "styling": "plain", "auth": "none", "api": "graphql"},
            "App",
        )
