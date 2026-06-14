"""Django backend: self-contained ORM rendering, tag gating, and py_compile."""
import py_compile

import pytest

from generator.composer import compose
from generator.errors import InvalidSelection

SCHEMA = [
    {"name": "Product", "fields": [
        {"name": "title", "type": "string", "required": True},
        {"name": "price", "type": "float"},
        {"name": "in_stock", "type": "boolean"},
    ]},
    {"name": "Customer", "plural": "customers", "fields": [
        {"name": "email", "type": "string", "required": True},
        {"name": "joined", "type": "datetime"},
    ]},
]

# Every database that depends on the shared data layer — none should pair with Django.
SHARED_DBS = ["sqlite", "postgres", "drizzle-sqlite", "drizzle-postgres",
              "drizzle-mysql", "mongo", "prisma-sqlite", "prisma-postgres"]


def _compose(database="none", auth="none", schema=SCHEMA):
    return compose(
        {"backend": "django", "frontend": "none", "database": database,
         "styling": "plain", "auth": auth, "api": "rest", "pkg": "npm"},
        "Shop", schema=schema,
    )


def test_django_custom_schema_renders_and_compiles(tmp_path):
    tree = _compose(auth="jwt")
    names = {p.split("/")[-1] for p in tree}
    assert {"manage.py", "settings.py", "urls.py", "wsgi.py", "middleware.py",
            "models.py", "views.py", "apps.py"} <= names

    models = next(tree[p] for p in tree if p.endswith("models.py")).decode()
    assert "class Product(models.Model):" in models
    assert "class Customer(models.Model):" in models
    assert "title = models.CharField(max_length=255)" in models       # required
    assert "price = models.FloatField(null=True, blank=True)" in models  # optional
    assert "joined = models.DateTimeField(null=True, blank=True)" in models

    views = next(tree[p] for p in tree if p.endswith("views.py")).decode()
    assert '"products": (Product, [ "title", "price", "in_stock"])' in views
    assert "def login(request):" in views      # JWT endpoints present
    assert "def me(request):" in views

    urls = next(tree[p] for p in tree if p.endswith("urls.py")).decode()
    assert 'path("api/<str:plural>", views.collection)' in urls
    assert 'path("api/login", views.login)' in urls

    reqs = next(tree[p] for p in tree if p.endswith("requirements.txt")).decode()
    assert "Django>=5.0" in reqs

    for path, data in tree.items():
        if path.endswith(".py"):
            full = tmp_path / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_bytes(data)
            py_compile.compile(str(full), doraise=True)


def test_django_seed_only_for_default_schema():
    apps_default = next(t for p, t in _compose(schema=()).items() if p.endswith("apps.py")).decode()
    assert "post_migrate" in apps_default and "First item" in apps_default
    apps_custom = next(t for p, t in _compose().items() if p.endswith("apps.py")).decode()
    assert "post_migrate" not in apps_custom  # custom schema has no Item to seed


def test_django_no_jwt_endpoints_when_auth_none():
    views = next(t for p, t in _compose(auth="none").items() if p.endswith("views.py")).decode()
    assert "def login(request):" not in views
    assert "import hmac" not in views


@pytest.mark.parametrize("database", SHARED_DBS)
def test_django_rejects_shared_data_layers(database):
    # Django owns its data layer (no `data:shared` tag), so every shared DB is invalid.
    with pytest.raises(InvalidSelection):
        _compose(database=database)


def test_django_docker_cmd_uses_manage_py():
    tree = compose(
        {"backend": "django", "frontend": "none", "database": "none",
         "styling": "plain", "auth": "none", "api": "rest", "pkg": "npm"},
        "Shop", schema=(), addons=["docker"],
    )
    dockerfile = next(tree[p] for p in tree if p.endswith("Dockerfile")).decode()
    assert "manage.py migrate --run-syncdb" in dockerfile
    assert "runserver 0.0.0.0:8000" in dockerfile
    # Django brings its own DB, so no extra DB service in compose.
    yml = next(tree[p] for p in tree if p.endswith("docker-compose.yml")).decode()
    assert "image:" not in yml
