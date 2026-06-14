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
    AXIS_LABELS,
    OPTIONS,
    VERSIONS,
    addon_applies,
    axis_default,
    docker_image,
    get_addon,
    get_module,
)
from .schema import is_default, normalize, render_flags, validate_schema
from .structure import normalize_structure

BACKEND_PORT = 8000
FRONTEND_PORT = 3000

# Path-segment tokens an add-on (or any scaffold) can use to target a component.
_DIR_TOKENS = ("__backend__", "__frontend__", "__root__")

__all__ = ["InvalidSelection", "compose", "validate", "slugify", "build_context"]


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate(selection: dict[str, str], *, require_component: bool = True) -> None:
    """Check a selection against the registry and capability tags.

    Each option declares ``provides``/``requires`` tags; a selection is valid
    when every selected option's required tags are provided by the rest of the
    selection, plus the structural rule that at least one runnable component
    (backend or frontend) is chosen. Raises ``InvalidSelection`` on the first
    problem found. ``require_component=False`` relaxes the structural rule (used
    for files-only projects that ship just custom files).
    """
    for axis in AXES:
        if axis not in selection:
            raise InvalidSelection(f"Missing choice for {axis}.")
        valid_ids = {m.id for m in OPTIONS[axis]}
        if selection[axis] not in valid_ids:
            raise InvalidSelection(
                f"Unknown {axis} option: {selection[axis]!r}."
            )

    mods = [get_module(axis, selection[axis]) for axis in AXES]
    provided: set[str] = set().union(*(m.provides for m in mods)) if mods else set()
    for mod in mods:
        for tag in mod.requires:
            if tag not in provided:
                raise InvalidSelection(
                    mod.requires_msg
                    or f"{mod.label} isn't compatible with the rest of the stack."
                )
    if require_component and "backend" not in provided and "frontend" not in provided:
        raise InvalidSelection("Pick at least a backend or a frontend — not neither.")


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
    structure=None,
) -> dict:
    """Derive every variable the scaffold templates may reference."""
    backend, frontend = selection["backend"], selection["frontend"]
    database, styling = selection["database"], selection["styling"]

    has_backend = backend != "none"
    has_frontend = frontend != "none"
    has_db = database != "none"
    # A frontend that ships npm deps needs a build step (a Vite SPA); vanilla
    # does not. Deriving from npm keeps this true for any future SPA framework.
    spa = has_frontend and bool(get_module("frontend", frontend).npm)
    # The backend's language drives manifest synthesis and per-language templates.
    backend_lang = (
        get_module("backend", backend).context.get("lang", "") if has_backend else ""
    )
    # Resolve the (optionally customized) layout: component dir names + root wrapper
    # + any user-injected files. Everything downstream derives from these, so a
    # renamed/relocated component stays internally consistent (and runnable).
    slug = slugify(project_name)
    struct = normalize_structure(structure, selection, default_root=slug)

    ctx = {
        "project_name": project_name or "my-app",
        "project_slug": slug,
        "root_dir": struct.root,
        "structure_files": struct.files,
        "backend": backend,
        "frontend": frontend,
        "database": database,
        "styling": styling,
        "has_backend": has_backend,
        "has_frontend": has_frontend,
        "has_db": has_db,
        "spa": spa,
        "backend_lang": backend_lang,
        "python_backend": backend_lang == "python",
        "node_backend": backend_lang == "node",
        "backend_dir": struct.backend_dir,
        "frontend_dir": struct.frontend_dir,
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
    # Docker base images, driven by versions.json so Renovate bumps them too.
    ctx["python_image"] = docker_image("python")
    ctx["node_image"] = docker_image("node")
    ctx.update(render_flags(ctx["entities"]))
    # Add-on flags: ``addons`` is the list of resolved add-on modules.
    selected_addons = {m.id for m in addons}
    ctx["addons"] = selected_addons
    for mod in ADDONS:
        ctx[f"addon_{mod.id}"] = mod.id in selected_addons

    # Expose every axis selection generically (so new axes like `auth` are
    # available to templates without touching this function).
    for axis in AXES:
        ctx.setdefault(axis, selection.get(axis, axis_default(axis)))

    # package.json "packageManager" field for the chosen JS package manager.
    ctx["pkg_field"] = get_module("pkg", ctx["pkg"]).context.get("pm_field")

    # Merge per-module static render vars (e.g. db_url, db_driver, prisma_*).
    for axis in AXES:
        mod = get_module(axis, selection[axis])
        for key in ("db_url", "db_driver", "prisma_provider", "prisma_url"):
            if key in mod.context:
                ctx[key] = mod.context[key]
    # Docker service descriptor for server-backed databases (file/in-memory
    # stores leave this None, so the compose addon adds no extra service).
    ctx["docker_db"] = get_module("database", database).context.get("docker")
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
        tree[_join(ctx["root_dir"], dest_dir, rel)] = content


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
    if ctx_extra.get("pkg_field"):
        pkg["packageManager"] = ctx_extra["pkg_field"]
    if scripts:
        pkg["scripts"] = scripts
    if deps:
        pkg["dependencies"] = dict(sorted(deps.items()))
    if dev:
        pkg["devDependencies"] = dict(sorted(dev.items()))
    return (json.dumps(pkg, indent=2) + "\n").encode("utf-8")


def _go_mod(module_name: str, requires) -> bytes:
    """Render a minimal go.mod. ``requires`` is an iterable of (path, version)."""
    lines = [f"module {module_name}", "", f"go {VERSIONS['golang_runtime']}"]
    requires = sorted(set(requires))
    if requires:
        lines += ["", "require ("] + [f"\t{p} {v}" for p, v in requires] + [")"]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _gemfile(gems) -> bytes:
    """Render a Ruby Gemfile from ``(name, version)`` pairs (pinned ``~>``)."""
    lines = ['source "https://rubygems.org"', ""]
    lines += [f'gem "{name}", "~> {ver}"' for name, ver in sorted(set(gems))]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _build_manifests(selection: dict, ctx: dict, tree: dict, addon_mods=()) -> None:
    slug = ctx["project_slug"]  # package/module *name* (independent of layout)
    root = ctx["root_dir"]      # where files are rooted in the tree
    backend_mod = get_module("backend", selection["backend"])
    frontend_mod = get_module("frontend", selection["frontend"])
    addon_mods = list(addon_mods)
    backend_dir = ctx["backend_dir"]
    # Every backend-affecting axis (data, auth, api) can contribute deps.
    side_mods = [get_module(axis, selection[axis]) for axis in ("database", "auth", "api")]
    backend_part = [backend_mod, *side_mods, *addon_mods]

    # Backend manifest, keyed by the backend's language. Add-on deps fold in via
    # each module's language-appropriate dependency fields (empty halves no-op).
    lang = ctx["backend_lang"]
    if lang == "python":
        reqs = set()
        for mod in backend_part:
            reqs |= set(mod.requirements)
        tree[_join(root, backend_dir, "requirements.txt")] = (
            "\n".join(sorted(reqs)) + "\n"
        ).encode("utf-8")
    elif lang == "node":
        tree[_join(root, backend_dir, "package.json")] = _package_json(
            f"{slug}-backend", [backend_mod, *side_mods, *addon_mods], ctx
        )
    elif lang == "go":
        go_req = set()
        for mod in backend_part:
            go_req |= set(mod.context.get("go_require", ()))
        tree[_join(root, backend_dir, "go.mod")] = _go_mod(slug, go_req)
    elif lang == "ruby":
        gems = set()
        for mod in backend_part:
            gems |= set(mod.context.get("gems", ()))
        tree[_join(root, backend_dir, "Gemfile")] = _gemfile(gems)

    # Frontend manifest (SPA only).
    if ctx["spa"]:
        tree[_join(root, ctx["frontend_dir"], "package.json")] = _package_json(
            f"{slug}-frontend", [frontend_mod, *addon_mods], ctx
        )


# --------------------------------------------------------------------------- #
# README
# --------------------------------------------------------------------------- #
def _apply_pkg_manager(run_lines, manager):
    """Rewrite npm install/run commands for the chosen JS package manager."""
    if manager == "npm":
        return run_lines
    install = {"pnpm": "pnpm install", "yarn": "yarn", "bun": "bun install"}[manager]
    out = []
    for line in run_lines:
        stripped = line.strip()
        if stripped == "npm install":
            out.append(install)
        elif stripped.startswith("npm run "):
            script = stripped[len("npm run "):]
            out.append({"pnpm": f"pnpm {script}", "yarn": f"yarn {script}",
                        "bun": f"bun run {script}"}[manager])
        else:
            out.append(line)
    return out


def _readme(selection: dict, ctx: dict) -> bytes:
    lines = [f"# {ctx['project_name']}", ""]
    lines.append("Generated by the Tech-Stack App Generator. Stack:")
    lines.append("")
    for axis in AXES:
        mod = get_module(axis, selection[axis])
        lines.append(f"- **{AXIS_LABELS[axis]}:** {mod.label}")
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
        run = _apply_pkg_manager(run, ctx["pkg"])
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
    structure=None,
) -> dict[str, bytes]:
    """Validate inputs and return ``{relative_path: bytes}`` for the zip.

    ``schema`` is the raw list of entity dicts (empty → default ``Item`` demo);
    ``addons`` is the list of selected add-on ids; ``structure`` is the optional
    layout config (component dirs, root wrapper, injected files).
    """
    # Fill any axis the caller omitted with its default (keeps older 4-axis
    # callers and presets working as new axes are added).
    selection = {**{axis: axis_default(axis) for axis in AXES}, **selection}
    # A files-only project (no backend/frontend, but custom files supplied) is a
    # valid output — e.g. a folder of class assignments — so relax the structural
    # rule in that one case.
    has_custom_files = bool(isinstance(structure, dict) and structure.get("files"))
    files_only = (selection["backend"] == "none" and selection["frontend"] == "none"
                  and has_custom_files)
    validate(selection, require_component=not files_only)
    validate_schema(schema, selection)
    addon_mods = resolve_addons(addons, selection)
    entities = normalize(schema)

    ctx = build_context(
        selection,
        project_name,
        entities=entities,
        is_default_schema=is_default(schema),
        addons=addon_mods,
        structure=structure,
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
    root = ctx["root_dir"]
    _build_manifests(selection, ctx, tree, addon_mods)
    tree[_join(root, "README.md")] = _readme(selection, ctx)
    config = to_config(ctx["project_name"], selection, [m.id for m in addon_mods],
                       schema, structure or {})
    tree[_join(root, "stackgen.json")] = (
        json.dumps(config, indent=2) + "\n"
    ).encode("utf-8")

    # 5. User-injected custom files/folders (additive; a collision with a
    #    generated file is an error, never a silent overwrite).
    for rel, content in ctx["structure_files"]:
        key = _join(root, rel)
        if key in tree:
            raise InvalidSelection(
                f"Custom file {rel!r} would overwrite a generated file."
            )
        tree[key] = content.encode("utf-8")

    return tree
