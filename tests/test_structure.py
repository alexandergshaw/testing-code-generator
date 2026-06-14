"""Custom directory/file structure: dir overrides, root control, injected files."""
import py_compile

import pytest

from generator.composer import compose
from generator.errors import InvalidSelection

STACK = {"backend": "flask", "frontend": "react", "database": "none",
         "styling": "plain", "auth": "none", "api": "rest", "pkg": "npm"}


def _tree(structure, stack=None, **kw):
    return compose({**STACK, **(stack or {})}, "Shop", structure=structure, **kw)


def test_default_layout_unchanged():
    tree = _tree(None)
    assert "shop/backend/app.py" in tree
    assert "shop/frontend/package.json" in tree


def test_custom_component_dirs():
    tree = _tree({"layout": "nested", "dirs": {"backend": "server", "frontend": "web"}})
    assert "shop/server/app.py" in tree
    assert "shop/web/package.json" in tree
    assert not any("/backend/" in p for p in tree)


def test_monorepo_preset():
    tree = _tree({"layout": "monorepo"})
    assert "shop/apps/api/app.py" in tree
    assert "shop/apps/web/package.json" in tree


def test_custom_dirs_thread_into_docker_and_readme():
    tree = _tree({"dirs": {"backend": "server", "frontend": "web"}}, addons=["docker"])
    compose_yml = next(tree[p] for p in tree if p.endswith("docker-compose.yml")).decode()
    assert "build: ./server" in compose_yml and "build: ./web" in compose_yml
    readme = next(tree[p] for p in tree if p.endswith("README.md")).decode()
    assert "cd server" in readme  # run steps follow the renamed dir


def test_custom_root_name():
    tree = _tree({"root": "cs101"})
    assert all(p.startswith("cs101/") for p in tree)
    assert "cs101/backend/app.py" in tree


def test_no_wrapping_folder():
    tree = _tree({"root": ""}, stack={"frontend": "none"})
    assert "app.py" in tree            # backend at the zip root, no wrapper
    assert "README.md" in tree
    assert not any(p.startswith("shop/") for p in tree)


def test_injected_files_and_empty_folder():
    tree = _tree({"files": [
        {"path": "assignments/hw1/README.md", "content": "# Homework 1"},
        {"path": "assignments/hw1/starter.py", "content": "print('hi')"},
        {"path": "assignments/hw2/"},  # empty folder
    ]})
    assert tree["shop/assignments/hw1/README.md"].decode() == "# Homework 1"
    assert tree["shop/assignments/hw1/starter.py"].decode() == "print('hi')"
    assert "shop/assignments/hw2/.gitkeep" in tree


def test_injected_file_collision_rejected():
    with pytest.raises(InvalidSelection):
        _tree({"files": [{"path": "backend/app.py", "content": "x"}]})


@pytest.mark.parametrize("bad", [
    {"root": "/etc/passwd"},
    {"files": [{"path": "../escape.txt", "content": "x"}]},
    {"dirs": {"backend": "../up"}},
    {"layout": "bogus"},
])
def test_unsafe_structure_rejected(bad):
    with pytest.raises(InvalidSelection):
        _tree(bad)


def test_files_only_project_without_stack():
    tree = compose(
        {"backend": "none", "frontend": "none", "database": "none", "styling": "plain"},
        "Course",
        structure={"files": [{"path": "syllabus.md", "content": "# Syllabus"}]},
    )
    assert tree["course/syllabus.md"].decode() == "# Syllabus"
    # No stack, but the custom file makes it a valid (files-only) project.
    assert not any(p.endswith("app.py") for p in tree)


def test_relocated_backend_still_compiles(tmp_path):
    # The core safety claim: moving a component dir doesn't break the app.
    tree = compose({**STACK, "frontend": "none", "database": "sqlite"}, "Shop",
                   structure={"dirs": {"backend": "server"}})
    for path, data in tree.items():
        if path.endswith(".py"):
            full = tmp_path / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_bytes(data)
            py_compile.compile(str(full), doraise=True)
    assert "shop/server/app.py" in tree
