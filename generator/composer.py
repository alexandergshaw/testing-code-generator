"""Assemble a generated project's file tree from the selected modules."""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

from .errors import InvalidSelection
from .preset import to_config
from .project_env import SCAFFOLDS_DIR, build_project_env
from .registry import (
    ADDONS,
    AXES,
    CONSTRAINTS,
    OPTIONS,
    addon_applies,
    get_addon,
    get_module,
)
from .schema import is_default, normalize, render_flags, validate_schema

BACKEND_PORT = 8000
FRONTEND_PORT = 3000

# Path-segment tokens an add-on (or any scaffold) can use to target a component.
_DIR_TOKENS = ("__backend__", "__frontend__", "__root__")

__all__ = ["InvalidSelection", "compose", "validate", "slugify", "build_context"]


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


def resolve_addons(addons, selection: dict) -> list:
    """Validate add-on ids and return the applicable selected add-on modules.

    Unknown ids raise ``InvalidSelection``; ids that don't fit the chosen stack
    are dropped silently (the UI also hides them).
    """
    mods = []
    for addon_id in dict.fromkeys(addons):  # de-dupe, keep order
        try:
            mod = get_addon(addon_id)
        except KeyError:
            raise InvalidSelection(f"Unknown add-on: {addon_id!r}.") from None
        if addon_applies(mod, selection):
            mods.append(mod)
    return mods


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def slugify(name: str) -> str:
    """Filesystem/zip-safe project slug; falls back to ``my-app``."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", (name or "").strip()).strip("-_")
    return slug.lower() or "my-app"


def build_context(
    selection: dict[str, str],
    project_name: str,
    *,
    entities=None,
    is_default_schema: bool = True,
    addons=(),
) -> dict:
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
        "entities": list(entities) if entities is not None else normalize([]),
        "is_default_schema": is_default_schema,
        "year": _dt.date.today().year,
    }
    # Compose build-context paths (kept as plain vars so templates don't end a
    # line on a block tag, which trim_blocks would swallow).
    ctx["backend_build"] = f"./{ctx['backend_dir']}" if ctx["backend_dir"] else "."
    ctx["frontend_build"] = f"./{ctx['frontend_dir']}" if ctx["frontend_dir"] else "."
    ctx.update(render_flags(ctx["entities"]))
    # Add-on flags: ``addons`` is the list of resolved add-on modules.
    selected_addons = {m.id for m in addons}
    ctx["addons"] = selected_addons
    for mod in ADDONS:
        ctx[f"addon_{mod.id}"] = mod.id in selected_addons

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


def _resolve_tokens(rel: str, ctx: dict) -> str:
    """Replace ``__backend__`` / ``__frontend__`` / ``__root__`` path segments
    with the resolved component directory, dropping ones that resolve to root."""
    mapping = {
        "__backend__": ctx["backend_dir"],
        "__frontend__": ctx["frontend_dir"],
        "__root__": "",
    }
    parts = []
    for seg in rel.split("/"):
        seg = mapping.get(seg, seg)
        if seg:
            parts.append(seg)
    return "/".join(parts)


# --------------------------------------------------------------------------- #
# File collection
# --------------------------------------------------------------------------- #
def _render_module(src: str, dest_dir: str, ctx: dict, env, tree: dict) -> None:
    """Render every file under ``scaffolds/<src>`` into ``tree``.

    ``.j2`` files are rendered with the project env; any that render to only
    whitespace are skipped (cheap conditional files). Path tokens in the
    relative path are resolved so a single module can target several components.
    """
    base = SCAFFOLDS_DIR / src
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base).as_posix()
        if rel.endswith(".j2"):
            rendered = env.get_template(f"{src}/{rel}").render(**ctx)
            if not rendered.strip():
                continue
            content = rendered.encode("utf-8")
            rel = rel[: -len(".j2")]
        else:
            content = path.read_bytes()
        rel = _resolve_tokens(rel, ctx)
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


def _build_manifests(selection: dict, ctx: dict, tree: dict, addon_mods=()) -> None:
    slug = ctx["project_slug"]
    backend_mod = get_module("backend", selection["backend"])
    db_mod = get_module("database", selection["database"])
    frontend_mod = get_module("frontend", selection["frontend"])
    addon_mods = list(addon_mods)

    # Backend manifest. Add-on Python deps fold into requirements.txt; add-on npm
    # deps fold into whichever package.json exists (their empty halves no-op).
    if ctx["python_backend"]:
        reqs = set(backend_mod.requirements) | set(db_mod.requirements)
        for mod in addon_mods:
            reqs |= set(mod.requirements)
        tree[_join(slug, ctx["backend_dir"], "requirements.txt")] = (
            "\n".join(sorted(reqs)) + "\n"
        ).encode("utf-8")
    elif ctx["node_backend"]:
        tree[_join(slug, ctx["backend_dir"], "package.json")] = _package_json(
            f"{slug}-backend", [backend_mod, *addon_mods], ctx
        )

    # Frontend manifest (SPA only).
    if ctx["spa"]:
        tree[_join(slug, ctx["frontend_dir"], "package.json")] = _package_json(
            f"{slug}-frontend", [frontend_mod, *addon_mods], ctx
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

    lines.append("## Data model")
    lines.append("")
    for entity in ctx["entities"]:
        fields = ", ".join(f"`{f.name}`: {f.type}" for f in entity.fields)
        lines.append(f"- **{entity.class_name}** — `{entity.route}` ({fields})")
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

    if ctx["addons"]:
        lines.append("## Add-ons")
        lines.append("")
        for addon_id in sorted(ctx["addons"]):
            for note in get_addon(addon_id).context.get("notes", ()):
                lines.append(f"- {note}")
        lines.append("")
    return ("\n".join(lines)).encode("utf-8")


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def compose(
    selection: dict[str, str],
    project_name: str,
    *,
    schema=(),
    addons=(),
) -> dict[str, bytes]:
    """Validate inputs and return ``{relative_path: bytes}`` for the zip.

    ``schema`` is the raw list of entity dicts (empty → default ``Item`` demo);
    ``addons`` is the list of selected add-on ids.
    """
    validate(selection)
    validate_schema(schema, selection)
    addon_mods = resolve_addons(addons, selection)
    entities = normalize(schema)

    ctx = build_context(
        selection,
        project_name,
        entities=entities,
        is_default_schema=is_default(schema),
        addons=addon_mods,
    )
    env = build_project_env()
    tree: dict[str, bytes] = {}

    # 1. Shared base files at the project root.
    _render_module("base", "", ctx, env, tree)

    # 2. Each selected axis module that contributes files.
    for axis in AXES:
        mod = get_module(axis, selection[axis])
        if mod.src:
            _render_module(mod.src, _component_dir(axis, ctx), ctx, env, tree)

    # 3. Applicable selected add-ons (placement via path tokens).
    for mod in addon_mods:
        if mod.src:
            _render_module(mod.src, "", ctx, env, tree)

    # 4. Computed manifests + README + the reproducible config.
    _build_manifests(selection, ctx, tree, addon_mods)
    tree[_join(ctx["project_slug"], "README.md")] = _readme(selection, ctx)
    config = to_config(ctx["project_name"], selection, [m.id for m in addon_mods], schema)
    tree[_join(ctx["project_slug"], "stackgen.json")] = (
        json.dumps(config, indent=2) + "\n"
    ).encode("utf-8")

    return tree
