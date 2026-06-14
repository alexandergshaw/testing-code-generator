"""Tests for feature add-ons: placement, gating, manifest folding."""
import json
import py_compile

import pytest

from generator.composer import compose
from generator.errors import InvalidSelection

FLASK = {"backend": "flask", "frontend": "vanilla", "database": "sqlite", "styling": "plain"}
REACT = {"backend": "fastapi", "frontend": "react", "database": "postgres", "styling": "tailwind"}


def _names(tree):
    return set(tree)


def test_docker_lands_in_each_component():
    tree = compose(REACT, "Shop", addons=["docker"])
    names = _names(tree)
    assert "shop/backend/Dockerfile" in names
    assert "shop/frontend/Dockerfile" in names
    assert "shop/docker-compose.yml" in names
    compose_yml = tree["shop/docker-compose.yml"].decode()
    assert "db:" in compose_yml and "postgres:16" in compose_yml  # postgres service


def test_docker_single_component_at_root():
    tree = compose(
        {"backend": "flask", "frontend": "none", "database": "none", "styling": "plain"},
        "Api", addons=["docker"],
    )
    assert "api/Dockerfile" in tree  # backend at root
    assert not any(p.endswith("frontend/Dockerfile") for p in tree)


def test_empty_render_files_are_skipped():
    # ruff.toml only renders for Python backends; Express must not get one.
    tree = compose(
        {"backend": "express", "frontend": "none", "database": "none", "styling": "plain"},
        "Api", addons=["lint"],
    )
    assert not any(p.endswith("ruff.toml") for p in tree)


def test_tests_addon_compiles_and_requires_python():
    tree = compose(FLASK, "Shop", addons=["tests"])
    test_files = [p for p in tree if p.endswith("test_api.py")]
    assert test_files
    # pytest + httpx folded into requirements (backend/ since a frontend exists).
    reqs = tree["shop/backend/requirements.txt"].decode()
    assert "pytest" in reqs and "httpx" in reqs


def test_tests_addon_dropped_for_express():
    # tests requires a Python backend; selecting it on Express is silently dropped.
    tree = compose(
        {"backend": "express", "frontend": "none", "database": "none", "styling": "plain"},
        "Api", addons=["tests"],
    )
    assert not any(p.endswith("test_api.py") for p in tree)


def test_lint_folds_prettier_into_spa_package_json():
    tree = compose(REACT, "Shop", addons=["lint"])
    pkg = json.loads(tree["shop/frontend/package.json"])
    assert "prettier" in pkg.get("devDependencies", {})
    assert pkg.get("scripts", {}).get("format")


def test_license_and_ci_present():
    tree = compose(FLASK, "Shop", addons=["license", "ci"])
    assert "shop/LICENSE" in tree
    assert "shop/.github/workflows/ci.yml" in tree
    assert str(__import__("datetime").date.today().year) in tree["shop/LICENSE"].decode()


def test_unknown_addon_rejected():
    with pytest.raises(InvalidSelection):
        compose(FLASK, "Shop", addons=["bogus"])


def test_generated_backend_with_addons_still_compiles(tmp_path):
    tree = compose(FLASK, "Shop", addons=["docker", "tests", "ci", "lint", "env", "license"])
    for path, data in tree.items():
        if path.endswith(".py"):
            full = tmp_path / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_bytes(data)
            py_compile.compile(str(full), doraise=True)
