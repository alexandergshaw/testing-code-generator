"""Assemble a generated project's file tree from the selected modules."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .project_env import SCAFFOLDS_DIR, build_project_env
from .registry import AXES, CONSTRAINTS, OPTIONS, get_module

BACKEND_PORT = 8000
FRONTEND_PORT = 3000


class InvalidSelection(ValueError):
    """Raised when a stack selection violates a compatibility rule."""


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate(selection: dict[str, str]) -> None:
    """Check a selection against the registry and compatibility rules.

    Raises ``InvalidSelection`` with a human-readable message on the first
    problem found.
    """
    for axis in AXES:
        if axis not in selection:
            raise InvalidSelection(f"Missing choice for {axis}.")
        valid_ids = {m.id for m in OPTIONS[axis]}
        if selection[axis] not in valid_ids:
            raise InvalidSelection(
                f"Unknown {axis} option: {selection[axis]!r}."
            )

    for rule in CONSTRAINTS:
        when = rule["when"]
        if selection[when["axis"]] not in when["values"]:
            continue
        if "require" in rule:
            req = rule["require"]
            if selection[req["axis"]] not in req["values"]:
                raise InvalidSelection(rule["message"])
        if "forbid" in rule:
            forbid = rule["forbid"]
            if selection[forbid["axis"]] in forbid["values"]:
                raise InvalidSelection(rule["message"])


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def slugify(name: str) -> str:
    """Filesystem/zip-safe project slug; falls back to ``my-app``."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", (name or "").strip()).strip("-_")
    return slug.lower() or "my-app"


def build_context(selection: dict[str, str], project_name: str) -> dict:
    """Derive every variable the scaffold templates may reference."""
    backend, frontend = selection["backend"], selection["frontend"]
    database, styling = selection["database"], selection["styling"]

    has_backend = backend != "none"
    has_frontend = frontend != "none"
    has_db = database != "none"
    spa = frontend in ("react", "vue")
    two_dirs = has_backend and has_frontend

    ctx = {
        "project_name": project_name or "my-app",
        "project_slug": slugify(project_name),
        "backend": backend,
        "frontend": frontend,
        "database": database,
        "styling": styling,
        "has_backend": has_backend,
        "has_frontend": has_frontend,
        "has_db": has_db,
        "spa": spa,
        "python_backend": backend in ("flask", "fastapi"),
        "node_backend": backend == "express",
        "backend_dir": "backend" if two_dirs else "",
        "frontend_dir": "frontend" if two_dirs else "",
        "backend_port": BACKEND_PORT,
        "frontend_port": FRONTEND_PORT,
        "api_base_url": f"http://localhost:{BACKEND_PORT}",
    }
    # Merge per-module static render vars (e.g. db_url, db_driver).
    for axis in AXES:
        mod = get_module(axis, selection[axis])
        for key in ("db_url", "db_driver"):
            if key in mod.context:
                ctx[key] = mod.context[key]
    return ctx


def _component_dir(axis: str, ctx: dict) -> str:
    """Where files from a module on ``axis`` are placed in the project."""
    if axis in ("backend", "database"):
        return ctx["backend_dir"]
    if axis == "frontend":
        return ctx["frontend_dir"]
    return ""  # base / styling


def _join(*parts: str) -> str:
    return "/".join(p for p in parts if p)


# --------------------------------------------------------------------------- #
# File collection
# --------------------------------------------------------------------------- #
def _render_module(src: str, dest_dir: str, ctx: dict, env, tree: dict) -> None:
    """Render every file under ``scaffolds/<src>`` into ``tree``."""
    base = SCAFFOLDS_DIR / src
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base).as_posix()
        if rel.endswith(".j2"):
            template = env.get_template(f"{src}/{rel}")
            content = template.render(**ctx).encode("utf-8")
            rel = rel[: -len(".j2")]
        else:
            content = path.read_bytes()
        tree[_join(ctx["project_slug"], dest_dir, rel)] = content


# --------------------------------------------------------------------------- #
# Manifest synthesis
# --------------------------------------------------------------------------- #
def _package_json(name: str, modules, ctx_extra: dict) -> bytes:
    deps, dev = {}, {}
    scripts, pkg_type = {}, None
    for mod in modules:
        deps.update(dict(mod.npm))
        dev.update(dict(mod.npm_dev))
        scripts.update(mod.context.get("npm_scripts", {}))
        pkg_type = mod.context.get("npm_type", pkg_type)
    pkg = {"name": name, "version": "1.0.0", "private": True}
    if pkg_type:
        pkg["type"] = pkg_type
    if scripts:
        pkg["scripts"] = scripts
    if deps:
        pkg["dependencies"] = dict(sorted(deps.items()))
    if dev:
        pkg["devDependencies"] = dict(sorted(dev.items()))
    return (json.dumps(pkg, indent=2) + "\n").encode("utf-8")


def _build_manifests(selection: dict, ctx: dict, tree: dict) -> None:
    slug = ctx["project_slug"]
    backend_mod = get_module("backend", selection["backend"])
    db_mod = get_module("database", selection["database"])
    frontend_mod = get_module("frontend", selection["frontend"])

    # Backend manifest.
    if ctx["python_backend"]:
        reqs = sorted(set(backend_mod.requirements) | set(db_mod.requirements))
        tree[_join(slug, ctx["backend_dir"], "requirements.txt")] = (
            "\n".join(reqs) + "\n"
        ).encode("utf-8")
    elif ctx["node_backend"]:
        tree[_join(slug, ctx["backend_dir"], "package.json")] = _package_json(
            f"{slug}-backend", [backend_mod], ctx
        )

    # Frontend manifest (SPA only).
    if ctx["spa"]:
        tree[_join(slug, ctx["frontend_dir"], "package.json")] = _package_json(
            f"{slug}-frontend", [frontend_mod], ctx
        )


# --------------------------------------------------------------------------- #
# README
# --------------------------------------------------------------------------- #
def _readme(selection: dict, ctx: dict) -> bytes:
    lines = [f"# {ctx['project_name']}", ""]
    lines.append("Generated by the Tech-Stack App Generator. Stack:")
    lines.append("")
    for axis in AXES:
        mod = get_module(axis, selection[axis])
        lines.append(f"- **{axis.capitalize()}:** {mod.label}")
    lines.append("")
    lines.append("## Getting started")
    lines.append("")

    def section(title, axis, dir_):
        mod = get_module(axis, selection[axis])
        run = mod.context.get("run")
        if not run:
            return
        lines.append(f"### {title}")
        lines.append("")
        lines.append("```bash")
        if dir_:
            lines.append(f"cd {dir_}")
        lines.extend(run)
        lines.append("```")
        lines.append("")

    if ctx["has_backend"]:
        section("Backend", "backend", ctx["backend_dir"])
    if ctx["has_frontend"]:
        section("Frontend", "frontend", ctx["frontend_dir"])

    if ctx["has_backend"] and ctx["has_frontend"]:
        lines.append(
            f"> The frontend calls the backend API at `{ctx['api_base_url']}`. "
            "Start the backend first."
        )
        lines.append("")
    return ("\n".join(lines)).encode("utf-8")


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def compose(selection: dict[str, str], project_name: str) -> dict[str, bytes]:
    """Validate a selection and return ``{relative_path: bytes}`` for the zip."""
    validate(selection)
    ctx = build_context(selection, project_name)
    env = build_project_env()
    tree: dict[str, bytes] = {}

    # 1. Shared base files at the project root.
    _render_module("base", "", ctx, env, tree)

    # 2. Each selected module that contributes files.
    for axis in AXES:
        mod = get_module(axis, selection[axis])
        if mod.src:
            _render_module(mod.src, _component_dir(axis, ctx), ctx, env, tree)

    # 3. Computed manifests + README.
    _build_manifests(selection, ctx, tree)
    tree[_join(ctx["project_slug"], "README.md")] = _readme(selection, ctx)

    return tree
