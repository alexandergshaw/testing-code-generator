"""Exercise the composer across the stack matrix via pairwise coverage.

Rendering every valid combination explodes as axes multiply, so the expensive
render+compile test runs over a small **pairwise** subset (every satisfiable
option-pair appears in at least one combo); validity bookkeeping still uses the
full product, which is cheap.
"""
import itertools
import json
import py_compile

import pytest

from generator.composer import InvalidSelection, compose, slugify, validate
from generator.registry import AXES, OPTIONS

from tests.pairwise import all_valid_combos, pairwise_combos

_OPTION_IDS = {axis: [m.id for m in OPTIONS[axis]] for axis in AXES}


def _is_valid(selection: dict) -> bool:
    try:
        validate(selection)
        return True
    except InvalidSelection:
        return False


VALID = all_valid_combos(AXES, _OPTION_IDS, _is_valid)
PAIRWISE = pairwise_combos(AXES, _OPTION_IDS, _is_valid)


def _ids(combos):
    return ["-".join(c[a] for a in AXES) for c in combos]


def test_combo_split_is_sane():
    assert VALID, "expected at least one valid combination"
    # Pairwise is a strict, much smaller subset of the valid combinations.
    assert 0 < len(PAIRWISE) <= len(VALID)


def test_pairwise_covers_every_option():
    seen = {(axis, value) for sel in PAIRWISE for axis, value in sel.items()}
    for axis in AXES:
        for mod in OPTIONS[axis]:
            assert (axis, mod.id) in seen, f"{axis}={mod.id} not covered by pairwise set"


@pytest.mark.parametrize("selection", PAIRWISE, ids=_ids(PAIRWISE))
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


def test_invalid_combos_rejected_by_compose():
    """Every full combo the validator rejects is also rejected by compose()."""
    checked = 0
    for values in itertools.product(*(_OPTION_IDS[a] for a in AXES)):
        selection = dict(zip(AXES, values))
        if _is_valid(selection):
            continue
        checked += 1
        with pytest.raises(InvalidSelection):
            compose(selection, "Demo App")
    assert checked, "expected at least one invalid combination"


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
