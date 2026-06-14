"""Custom project structure: where components live, the root wrapper, and any
extra files/folders the caller injects (e.g. one folder per class assignment).

This lets a request reshape the generated layout *without* breaking the "it runs"
guarantee: component directory names are threaded through every derived path
(Docker build context, README ``cd``, manifests) by the composer, and extra files
are purely additive — a collision with a generated file is rejected. Nothing here
renders templates; it only normalizes + validates the user's ``structure`` config,
mirroring the role ``schema.py`` plays for entities.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import InvalidSelection

# Named layout presets -> component directory overrides. "nested" is the historical
# default (backend/ + frontend/ when both exist, else root) and so adds no override.
LAYOUTS = {
    "nested": {},
    "monorepo": {"backend": "apps/api", "frontend": "apps/web"},
}

_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _safe_relpath(raw: str, *, what: str) -> str:
    """Normalize a relative path and reject absolute paths / ``..`` traversal."""
    p = (raw or "").strip().replace("\\", "/")
    if p.startswith("/"):
        raise InvalidSelection(f"Invalid {what} {raw!r}: must be relative (no leading '/').")
    p = p.strip("/")
    parts = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == ".." or not _SEGMENT_RE.match(seg):
            raise InvalidSelection(
                f"Invalid {what} {raw!r}: use relative paths of letters, digits, "
                "'.', '_', '-' and '/' (no '..' or absolute paths)."
            )
        parts.append(seg)
    return "/".join(parts)


@dataclass(frozen=True)
class Structure:
    root: str            # "" => no wrapping folder (files at the zip root)
    backend_dir: str
    frontend_dir: str
    files: tuple[tuple[str, str], ...]  # (relpath, text content)


def normalize_structure(raw, selection: dict, *, default_root: str) -> Structure:
    """Validate the ``structure`` config and resolve it against the selection."""
    raw = raw or {}
    if not isinstance(raw, dict):
        raise InvalidSelection("'structure' must be a JSON object.")

    # Root: an explicit value (including "") wins; otherwise the project slug.
    root = _safe_relpath(raw.get("root") or "", what="root") if "root" in raw else default_root

    has_backend = selection.get("backend", "none") != "none"
    has_frontend = selection.get("frontend", "none") != "none"
    both = has_backend and has_frontend

    layout = raw.get("layout", "nested")
    if layout not in LAYOUTS:
        raise InvalidSelection(
            f"Unknown layout {layout!r}: choose one of {', '.join(sorted(LAYOUTS))}."
        )
    preset = LAYOUTS[layout]
    dirs = raw.get("dirs") or {}
    if not isinstance(dirs, dict):
        raise InvalidSelection("'structure.dirs' must be a JSON object.")

    def resolve(axis: str) -> str:
        # explicit override > layout preset > historical default (nested when both).
        if axis in dirs:
            return _safe_relpath(dirs[axis] or "", what=f"{axis} directory")
        if axis in preset:
            return preset[axis]
        return axis if both else ""

    backend_dir = resolve("backend") if has_backend else ""
    frontend_dir = resolve("frontend") if has_frontend else ""
    if both and backend_dir == frontend_dir:
        raise InvalidSelection(
            "Backend and frontend directories must differ when both are present."
        )

    files: list[tuple[str, str]] = []
    seen: set[str] = set()
    raw_files = raw.get("files", [])
    if not isinstance(raw_files, list):
        raise InvalidSelection("'structure.files' must be a JSON array.")
    for entry in raw_files:
        if not isinstance(entry, dict) or "path" not in entry:
            raise InvalidSelection("Each structure file needs a 'path'.")
        is_dir = str(entry["path"]).rstrip().endswith("/")
        rel = _safe_relpath(entry["path"], what="file path")
        if not rel:
            raise InvalidSelection("A structure file 'path' cannot be empty.")
        content = entry.get("content")
        if content is not None and not isinstance(content, str):
            raise InvalidSelection(f"Content for {rel!r} must be a string.")
        # Trailing-slash path (or no content) => an empty folder via .gitkeep.
        path, text = (f"{rel}/.gitkeep", "") if is_dir else (rel, content or "")
        if path in seen:
            raise InvalidSelection(f"Duplicate structure file: {rel!r}.")
        seen.add(path)
        files.append((path, text))

    return Structure(root=root, backend_dir=backend_dir,
                     frontend_dir=frontend_dir, files=tuple(files))
