"""Node database support (Drizzle/Mongoose/Prisma): rendering, gating, node --check."""
import json
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
NODE_DBS = ["drizzle-sqlite", "drizzle-postgres", "drizzle-mysql",
            "mongo", "prisma-sqlite", "prisma-postgres"]


def _compose(backend, database, **kw):
    return compose(
        {"backend": backend, "frontend": "none", "database": database,
         "styling": "plain", "auth": "none", "api": "rest", "pkg": "npm"},
        "Shop", schema=SCHEMA, **kw,
    )


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


@pytest.mark.parametrize("backend", NODE_BACKENDS)
def test_drizzle_postgres_data_layer_rendered(backend):
    tree = compose(
        {"backend": backend, "frontend": "none", "database": "drizzle-postgres",
         "styling": "plain", "auth": "none", "api": "rest", "pkg": "npm"},
        "Shop", schema=SCHEMA,
    )
    names = {p.split("/")[-1] for p in tree}
    assert {"schema.js", "db.js", "repo.js"} <= names  # Drizzle data layer present
    schema = next(tree[p] for p in tree if p.endswith("schema.js")).decode()
    assert 'pgTable("products"' in schema
    assert "doublePrecision" in schema   # float column mapped to pg type
    db = next(tree[p] for p in tree if p.endswith("db.js")).decode()
    assert "drizzle-orm/postgres-js" in db
    assert "ready" in db                  # async setup gated behind a ready promise
    import json
    pkg = json.loads(next(tree[p] for p in tree if p.endswith("package.json")))
    assert "drizzle-orm" in pkg["dependencies"]
    assert "postgres" in pkg["dependencies"]
    assert "better-sqlite3" not in pkg["dependencies"]  # not the SQLite driver


def test_drizzle_postgres_docker_compose_has_db_service():
    tree = compose(
        {"backend": "express", "frontend": "none", "database": "drizzle-postgres",
         "styling": "plain", "auth": "none", "api": "rest", "pkg": "npm"},
        "Shop", schema=SCHEMA, addons=["docker"],
    )
    compose_yml = next(tree[p] for p in tree if p.endswith("docker-compose.yml")).decode()
    assert "image: postgres:16" in compose_yml            # a Postgres service is added
    assert "postgres://postgres:postgres@db:5432/app" in compose_yml  # node driver URL
    assert "psycopg2" not in compose_yml                  # not the Python driver URL


@pytest.mark.parametrize("backend", NODE_BACKENDS)
def test_drizzle_mysql_data_layer_rendered(backend):
    tree = _compose(backend, "drizzle-mysql")
    schema = next(tree[p] for p in tree if p.endswith("schema.js")).decode()
    assert 'mysqlTable("products"' in schema
    assert "double" in schema            # float column mapped to a MySQL type
    db = next(tree[p] for p in tree if p.endswith("db.js")).decode()
    assert "mysql2/promise" in db
    assert "AUTO_INCREMENT" in db
    pkg = json.loads(next(tree[p] for p in tree if p.endswith("package.json")))
    assert "mysql2" in pkg["dependencies"]


@pytest.mark.parametrize("backend", NODE_BACKENDS)
def test_mongo_data_layer_rendered(backend):
    tree = _compose(backend, "mongo")
    schema = next(tree[p] for p in tree if p.endswith("schema.js")).decode()
    assert 'mongoose.model("Product"' in schema
    repo = next(tree[p] for p in tree if p.endswith("repo.js")).decode()
    assert "id: String(_id)" in repo     # ObjectId surfaced as a string id
    assert "isValidObjectId" in repo
    pkg = json.loads(next(tree[p] for p in tree if p.endswith("package.json")))
    assert "mongoose" in pkg["dependencies"]


@pytest.mark.parametrize("database,provider", [("prisma-sqlite", "sqlite"),
                                               ("prisma-postgres", "postgresql")])
def test_prisma_data_layer_rendered(database, provider):
    tree = _compose("express", database)
    prisma = next(tree[p] for p in tree if p.endswith("schema.prisma")).decode()
    assert f'provider = "{provider}"' in prisma
    assert "model Product {" in prisma
    assert "id Int @id @default(autoincrement())" in prisma
    assert "price Float?" in prisma      # optional field gets a "?"
    assert "title String" in prisma and "title String?" not in prisma  # required: no "?"
    repo = next(tree[p] for p in tree if p.endswith("repo.js")).decode()
    assert "prisma.product" in repo      # camelCase client delegate
    pkg = json.loads(next(tree[p] for p in tree if p.endswith("package.json")))
    assert "@prisma/client" in pkg["dependencies"]
    assert "prisma" in pkg["devDependencies"]
    assert pkg["scripts"]["postinstall"] == "prisma generate"  # client gen on install


@pytest.mark.parametrize("database,image,port", [
    ("drizzle-mysql", "mysql:8", "3306"),
    ("mongo", "mongo:7", "27017"),
    ("prisma-postgres", "postgres:16", "5432"),
])
def test_node_db_docker_compose_service(database, image, port):
    tree = _compose("express", database, addons=["docker"])
    yml = next(tree[p] for p in tree if p.endswith("docker-compose.yml")).decode()
    assert f"image: {image}" in yml
    assert f'"{port}:{port}"' in yml


def test_sqlite_dbs_have_no_docker_service():
    # File/in-memory stores must not add a DB service to compose.
    for database in ("drizzle-sqlite", "prisma-sqlite", "none"):
        tree = _compose("express", database, addons=["docker"])
        yml = next(tree[p] for p in tree if p.endswith("docker-compose.yml")).decode()
        assert "image:" not in yml, database


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
@pytest.mark.parametrize("database", NODE_DBS)
def test_node_db_js_syntax(backend, database, tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    tree = compose(
        {"backend": backend, "frontend": "none", "database": database,
         "styling": "plain", "auth": "jwt", "api": "rest", "pkg": "npm"},
        "Shop", schema=SCHEMA,
    )
    for path, data in tree.items():
        if path.endswith(".js"):
            f = tmp_path / path.split("/")[-1]
            f.write_bytes(data)
            result = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
            assert result.returncode == 0, f"{path}: {result.stderr}"
