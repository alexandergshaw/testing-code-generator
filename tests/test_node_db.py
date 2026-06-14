"""Node database support via Drizzle: rendering, tag gating, and node --check."""
import shutil
import subprocess

import pytest

from generator.composer import compose
from generator.errors import InvalidSelection

SCHEMA = [
    {"name": "Product", "fields": [
        {"name": "title", "type": "string", "required": True},
        {"name": "price", "type": "float"},
        {"name": "in_stock", "type": "boolean"},
    ]},
]

NODE_BACKENDS = ["express", "fastify", "hono", "koa"]


@pytest.mark.parametrize("backend", NODE_BACKENDS)
def test_drizzle_data_layer_rendered(backend):
    tree = compose(
        {"backend": backend, "frontend": "none", "database": "drizzle-sqlite",
         "styling": "plain", "auth": "none", "api": "rest", "pkg": "npm"},
        "Shop", schema=SCHEMA,
    )
    names = {p.split("/")[-1] for p in tree}
    assert {"schema.js", "db.js", "repo.js"} <= names  # Drizzle data layer present
    schema = next(tree[p] for p in tree if p.endswith("schema.js")).decode()
    assert 'sqliteTable("products"' in schema
    assert '{ mode: "boolean" }' in schema  # boolean column mapped
    import json
    pkg = json.loads(next(tree[p] for p in tree if p.endswith("package.json")))
    assert "drizzle-orm" in pkg["dependencies"]
    assert "better-sqlite3" in pkg["dependencies"]


def test_in_memory_repo_when_no_db():
    tree = compose(
        {"backend": "express", "frontend": "none", "database": "none",
         "styling": "plain", "auth": "none", "api": "rest", "pkg": "npm"},
        "Shop", schema=SCHEMA,
    )
    names = {p.split("/")[-1] for p in tree}
    assert "repo.js" in names          # in-memory repo provided
    assert "schema.js" not in names    # but no Drizzle schema
    repo = next(tree[p] for p in tree if p.endswith("repo.js")).decode()
    assert "stores" in repo


def test_drizzle_requires_node_backend():
    for backend in ("flask", "nethttp", "sinatra", "none"):
        with pytest.raises(InvalidSelection):
            compose(
                {"backend": backend, "frontend": "react" if backend == "none" else "none",
                 "database": "drizzle-sqlite", "styling": "plain",
                 "auth": "none", "api": "rest", "pkg": "npm"},
                "Shop", schema=(SCHEMA if backend != "none" else ()),
            )


@pytest.mark.parametrize("backend", NODE_BACKENDS)
def test_drizzle_js_syntax(backend, tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    tree = compose(
        {"backend": backend, "frontend": "none", "database": "drizzle-sqlite",
         "styling": "plain", "auth": "jwt", "api": "rest", "pkg": "npm"},
        "Shop", schema=SCHEMA,
    )
    for path, data in tree.items():
        if path.endswith(".js"):
            f = tmp_path / path.split("/")[-1]
            f.write_bytes(data)
            result = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
            assert result.returncode == 0, f"{path}: {result.stderr}"
