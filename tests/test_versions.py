"""versions.json is the single source of truth for pins — keep it in lockstep
with the catalogue (no orphan lookups, no dead entries) and confirm it actually
drives the generated manifests."""
import re

from generator.composer import compose
from generator.registry import ADDONS, OPTIONS, VERSIONS

ALL_MODULES = [m for mods in OPTIONS.values() for m in mods] + list(ADDONS)


def _pypi_name(spec):  # "uvicorn[standard]>=0.29" -> "uvicorn"
    return re.split(r"[<>=\[]", spec, maxsplit=1)[0]


def test_versions_file_shape():
    for section in ("npm", "pypi", "golang", "rubygems", "docker"):
        assert isinstance(VERSIONS[section], dict) and VERSIONS[section]
        assert all(isinstance(val, str) and val for val in VERSIONS[section].values())
    assert isinstance(VERSIONS["golang_runtime"], str)


def test_no_orphan_or_dead_npm_pins():
    used = {name for m in ALL_MODULES for name, _ in (*m.npm, *m.npm_dev)}
    assert used == set(VERSIONS["npm"]), (
        f"npm drift: only-in-catalog={used - set(VERSIONS['npm'])}, "
        f"only-in-versions.json={set(VERSIONS['npm']) - used}"
    )


def test_no_orphan_or_dead_pypi_pins():
    used = {_pypi_name(r) for m in ALL_MODULES for r in m.requirements}
    assert used == set(VERSIONS["pypi"])


def test_no_orphan_or_dead_go_and_gem_pins():
    used_go = {mod for m in ALL_MODULES for mod, _ in m.context.get("go_require", ())}
    assert used_go == set(VERSIONS["golang"])
    used_gems = {name for m in ALL_MODULES for name, _ in m.context.get("gems", ())}
    assert used_gems == set(VERSIONS["rubygems"])


def test_docker_pins_used():
    images = {m.context["docker"]["image"].split(":")[0]
              for m in ALL_MODULES if "docker" in m.context}
    # DB service images + the python/node base images (used by build_context).
    assert images | {"python", "node"} == set(VERSIONS["docker"])


def test_versions_drive_generated_manifests():
    reqs = next(t for p, t in compose(
        {"backend": "flask", "frontend": "none", "database": "sqlite", "styling": "plain"},
        "A").items() if p.endswith("requirements.txt")).decode()
    assert f"Flask{VERSIONS['pypi']['Flask']}" in reqs

    pkg = next(t for p, t in compose(
        {"backend": "express", "frontend": "none", "database": "none", "styling": "plain"},
        "A").items() if p.endswith("package.json")).decode()
    assert VERSIONS["npm"]["express"] in pkg

    gomod = next(t for p, t in compose(
        {"backend": "gin", "frontend": "none", "database": "none", "styling": "plain"},
        "A").items() if p.endswith("go.mod")).decode()
    assert f"go {VERSIONS['golang_runtime']}" in gomod
    assert VERSIONS["golang"]["github.com/gin-gonic/gin"] in gomod

    docker = next(t for p, t in compose(
        {"backend": "fastapi", "frontend": "none", "database": "none", "styling": "plain"},
        "A", addons=["docker"]).items() if p.endswith("Dockerfile")).decode()
    assert f"python:{VERSIONS['docker']['python']}" in docker
