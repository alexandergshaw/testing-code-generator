"""Exhaustively exercise the composer across every stack combination."""
import itertools
import json
import py_compile

import pytest

from generator.composer import InvalidSelection, compose, slugify, validate
from generator.registry import AXES, OPTIONS

ALL_COMBOS = [
    dict(zip(AXES, values))
    for values in itertools.product(*([m.id for m in OPTIONS[a]] for a in AXES))
]


def _is_valid(selection: dict) -> bool:
    try:
        validate(selection)
        return True
    except InvalidSelection:
        return False


VALID = [c for c in ALL_COMBOS if _is_valid(c)]
INVALID = [c for c in ALL_COMBOS if not _is_valid(c)]


def _ids(combos):
    return ["-".join(c[a] for a in AXES) for c in combos]


def test_combo_split_is_sane():
    assert VALID, "expected at least one valid combination"
    assert INVALID, "expected at least one invalid combination"
    assert len(VALID) + len(INVALID) == len(ALL_COMBOS)


@pytest.mark.parametrize("selection", VALID, ids=_ids(VALID))
def test_valid_combo_renders_runnable_tree(selection, tmp_path):
    tree = compose(selection, "Demo App")
    assert tree, "composer returned an empty tree"

    slug = slugify("Demo App")
    assert f"{slug}/README.md" in tree

    for path, data in tree.items():
        assert path.startswith(f"{slug}/"), f"{path} not rooted under project slug"
        full = tmp_path / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)
        # Generated Python must at least parse/compile.
        if path.endswith(".py"):
            py_compile.compile(str(full), doraise=True)
        # Generated package.json / config JSON must be valid JSON.
        if path.endswith(".json"):
            json.loads(data)


@pytest.mark.parametrize("selection", INVALID, ids=_ids(INVALID))
def test_invalid_combo_is_rejected(selection):
    with pytest.raises(InvalidSelection):
        compose(selection, "Demo App")


@pytest.mark.parametrize(
    "selection, expected_suffix",
    [
        ({"backend": "flask", "frontend": "none", "database": "sqlite", "styling": "plain"}, "app.py"),
        ({"backend": "fastapi", "frontend": "none", "database": "none", "styling": "plain"}, "main.py"),
        ({"backend": "express", "frontend": "none", "database": "none", "styling": "plain"}, "server.js"),
        ({"backend": "none", "frontend": "react", "database": "none", "styling": "tailwind"}, "src/main.jsx"),
        ({"backend": "none", "frontend": "vue", "database": "none", "styling": "bootstrap"}, "src/main.js"),
        ({"backend": "none", "frontend": "vanilla", "database": "none", "styling": "plain"}, "index.html"),
    ],
)
def test_expected_entrypoint_present(selection, expected_suffix):
    tree = compose(selection, "Demo App")
    assert any(p.endswith(expected_suffix) for p in tree), (
        f"{expected_suffix} missing for {selection}"
    )


def test_two_dir_layout_when_backend_and_frontend():
    tree = compose(
        {"backend": "flask", "frontend": "react", "database": "sqlite", "styling": "plain"},
        "Demo App",
    )
    assert any(p.startswith("demo-app/backend/") for p in tree)
    assert any(p.startswith("demo-app/frontend/") for p in tree)


def test_db_layer_present_only_with_database():
    with_db = compose(
        {"backend": "flask", "frontend": "none", "database": "sqlite", "styling": "plain"},
        "Demo App",
    )
    without_db = compose(
        {"backend": "flask", "frontend": "none", "database": "none", "styling": "plain"},
        "Demo App",
    )
    assert any(p.endswith("db.py") for p in with_db)
    assert not any(p.endswith("db.py") for p in without_db)


@pytest.mark.parametrize(
    "raw, expected",
    [("My App", "my-app"), ("  ", "my-app"), ("Foo_Bar 1", "foo_bar-1"), ("!!!", "my-app")],
)
def test_slugify(raw, expected):
    assert slugify(raw) == expected
