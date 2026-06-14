"""Package-manager axis: package.json field + README command rewriting, tag-gated."""
import json

import pytest

from generator.composer import compose
from generator.errors import InvalidSelection


def _tree(pkg, frontend="react", backend="none"):
    return compose(
        {"backend": backend, "frontend": frontend, "database": "none",
         "styling": "plain", "auth": "none", "api": "rest", "pkg": pkg},
        "App",
    )


def _package_json(tree):
    return json.loads(next(tree[p] for p in tree if p.endswith("package.json")))


@pytest.mark.parametrize(
    "pkg, field",
    [("pnpm", "pnpm@9.12.0"), ("yarn", "yarn@4.5.0"), ("bun", "bun@1.1.34")],
)
def test_package_json_gets_manager_field(pkg, field):
    assert _package_json(_tree(pkg)).get("packageManager") == field


def test_npm_has_no_manager_field():
    assert "packageManager" not in _package_json(_tree("npm"))


def test_readme_rewrites_js_commands():
    readme = next(t for p, t in _tree("pnpm").items() if p.endswith("README.md")).decode()
    assert "pnpm install" in readme
    assert "pnpm dev" in readme
    assert "npm run" not in readme  # "npm run dev" was rewritten to "pnpm dev"


def test_python_run_commands_untouched():
    # pip lines must not be rewritten by a JS package manager.
    tree = compose(
        {"backend": "flask", "frontend": "react", "database": "none",
         "styling": "plain", "auth": "none", "api": "rest", "pkg": "pnpm"},
        "App",
    )
    readme = next(t for p, t in tree.items() if p.endswith("README.md")).decode()
    assert "pip install -r requirements.txt" in readme  # backend untouched
    assert "pnpm install" in readme  # frontend rewritten


def test_non_npm_requires_node_runtime():
    with pytest.raises(InvalidSelection):
        compose(
            {"backend": "flask", "frontend": "vanilla", "database": "none",
             "styling": "plain", "auth": "none", "api": "rest", "pkg": "pnpm"},
            "App",
        )
