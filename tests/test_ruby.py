"""Ruby Sinatra backend: structure + Gemfile, with `ruby -c` when available."""
import shutil
import subprocess

import pytest

from generator.composer import compose

SCHEMA = [
    {"name": "Product", "fields": [
        {"name": "title", "type": "string", "required": True},
        {"name": "price", "type": "float"},
    ]},
]


def _tree(auth="jwt"):
    return compose(
        {"backend": "sinatra", "frontend": "none", "database": "none",
         "styling": "plain", "auth": auth, "api": "rest", "pkg": "npm"},
        "Shop", schema=SCHEMA,
    )


def test_sinatra_renders_routes_and_gemfile():
    tree = _tree()
    rb = next(tree[p] for p in tree if p.endswith("app.rb")).decode()
    for route in ("/api/products", "/api/products/:id", "/api/login", "/api/me"):
        assert route in rb
    assert "HS256" in rb
    gemfile = next(tree[p] for p in tree if p.endswith("Gemfile")).decode()
    assert "sinatra" in gemfile and "puma" in gemfile


def test_no_auth_has_no_login():
    rb = next(t for p, t in _tree(auth="none").items() if p.endswith("app.rb")).decode()
    assert "/api/login" not in rb


def test_sinatra_ruby_syntax(tmp_path):
    ruby = shutil.which("ruby")
    if not ruby:
        pytest.skip("ruby toolchain not installed")
    path = tmp_path / "app.rb"
    path.write_bytes(next(t for p, t in _tree().items() if p.endswith("app.rb")))
    result = subprocess.run([ruby, "-c", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
