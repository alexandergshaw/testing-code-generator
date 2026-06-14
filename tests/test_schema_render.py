"""Render generated apps from a custom multi-entity schema and compile them."""
import pathlib
import py_compile
import shutil
import subprocess

import pytest

from generator.composer import compose

SCHEMA = [
    {
        "name": "Product",
        "fields": [
            {"name": "title", "type": "string", "required": True},
            {"name": "price", "type": "float"},
            {"name": "in_stock", "type": "boolean"},
        ],
    },
    {
        "name": "Customer",
        "plural": "customers",
        "fields": [
            {"name": "email", "type": "string", "required": True},
            {"name": "joined", "type": "datetime"},
        ],
    },
]


@pytest.mark.parametrize("backend", ["flask", "fastapi"])
@pytest.mark.parametrize("database", ["none", "sqlite", "postgres"])
def test_custom_schema_backend_compiles(backend, database, tmp_path):
    selection = {"backend": backend, "frontend": "none",
                 "database": database, "styling": "plain"}
    tree = compose(selection, "Shop", schema=SCHEMA)

    py_files = [p for p in tree if p.endswith(".py")]
    assert py_files
    for path in py_files:
        full = tmp_path / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(tree[path])
        py_compile.compile(str(full), doraise=True)

    # The generated backend exposes every entity's plural route.
    blob = b"\n".join(tree[p] for p in py_files).decode()
    assert "/api/products" in blob
    assert "/api/customers" in blob
    # With a database, ORM model classes are generated; in-memory uses dicts.
    if database != "none":
        assert "class Product(Base)" in blob
        assert "class Customer(Base)" in blob


def test_unquoted_type_annotations(tmp_path):
    """Field types must render unquoted (regression for the [[[ lexer bug)."""
    tree = compose(
        {"backend": "fastapi", "frontend": "none", "database": "sqlite",
         "styling": "plain"},
        "Shop", schema=SCHEMA,
    )
    main = next(tree[p] for p in tree if p.endswith("main.py")).decode()
    db = next(tree[p] for p in tree if p.endswith("db.py")).decode()
    assert "Optional[float]" in main and "Optional['float']" not in main
    assert "Mapped[str]" in db and "Mapped['str']" not in db


@pytest.mark.parametrize("frontend", ["none", "react"])
def test_express_custom_schema_renders(frontend, tmp_path):
    selection = {"backend": "express", "frontend": frontend,
                 "database": "none", "styling": "plain"}
    tree = compose(selection, "Shop", schema=SCHEMA)
    server_bytes = next(tree[p] for p in tree if p.endswith("server.js"))
    server = server_bytes.decode()
    for entity in ("products", "customers"):
        assert f"/api/{entity}" in server
        assert f"let {entity}" in server

    node = shutil.which("node")
    if node:
        path = tmp_path / "server.js"
        path.write_bytes(server_bytes)
        result = subprocess.run(
            [node, "--check", str(path)], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr


def test_go_custom_schema_builds(tmp_path):
    selection = {"backend": "nethttp", "frontend": "none",
                 "database": "none", "styling": "plain"}
    tree = compose(selection, "Shop", schema=SCHEMA)
    main_go = next(tree[p] for p in tree if p.endswith("main.go")).decode()
    for struct in ("type Product struct", "type Customer struct"):
        assert struct in main_go
    assert "/api/products" in main_go and "/api/customers" in main_go

    go = shutil.which("go")
    if go:
        for path, data in tree.items():
            if path.endswith(("main.go", "go.mod")):
                (tmp_path / pathlib.Path(path).name).write_bytes(data)
        result = subprocess.run(
            [go, "build", "./..."], cwd=tmp_path, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr


def test_no_seed_for_custom_schema(tmp_path):
    tree = compose(
        {"backend": "flask", "frontend": "none", "database": "sqlite",
         "styling": "plain"},
        "Shop", schema=SCHEMA,
    )
    db = next(tree[p] for p in tree if p.endswith("db.py")).decode()
    assert "add_all" not in db  # seeding only happens for the default schema
