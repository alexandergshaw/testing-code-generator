"""The catalogue of stack options and the compatibility rules between them.

This module is pure data + a couple of small helpers. Compatibility is decided
by capability **tags**: each option ``provides`` some tags and ``requires``
others, and a selection is valid when every option's requirements are provided
by the rest of the selection. Both the server-side validator
(``composer.validate``) and the browser form (``public/js/form.js``, fed
``module_tags()`` via the index template) use the same tags so they never drift.

Composition semantics (kept deliberately uniform so every module is independent):

* A **backend** is always a small JSON API (``/api/health`` + a sample ``items``
  resource). When a frontend is also chosen it lives in ``backend/``; otherwise
  at the project root.
* A **frontend** is always the UI. It reads ``styling`` / ``has_backend`` /
  ``api_base_url`` from the render context and either calls the backend API or
  falls back to mock data. It lives in ``frontend/`` (or root when alone).
* A **database** contributes a SQLAlchemy layer into the backend; the backend
  template wires it in conditionally via context flags.
* **Styling** contributes *no files* — only context. Frontends emit the right
  CDN tags / inline CSS based on the chosen id, so styling never fights the
  frontend over file placement.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Module:
    """One selectable option on one axis."""

    id: str
    label: str
    axis: str
    summary: str = ""
    # Folder under ``scaffolds/`` whose files this module contributes (or None).
    src: str | None = None
    # Python dependency lines (backend / database modules).
    requirements: tuple[str, ...] = ()
    # npm runtime/dev dependencies as (name, version) pairs.
    npm: tuple[tuple[str, str], ...] = ()
    npm_dev: tuple[tuple[str, str], ...] = ()
    # Capability tags this option contributes (provides) and depends on
    # (requires). Compatibility is decided by tag satisfaction, not hardcoded id
    # lists, so the catalogue can grow without editing a central rules table.
    # Common tags: backend / frontend, lang:<x>, runtime:<x>, framework:<x>,
    # kind:spa|meta, engine:<x>. Left empty -> sensible defaults are derived
    # from the axis + context["lang"] (see _apply_default_tags).
    provides: frozenset[str] = frozenset()
    requires: tuple[str, ...] = ()
    # Message shown when a `requires` tag is unmet.
    requires_msg: str = ""
    # Extra render context and metadata (npm scripts, run commands, ...).
    context: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Backend frameworks
# --------------------------------------------------------------------------- #
_BACKENDS = [
    Module(
        id="flask",
        label="Flask",
        axis="backend",
        summary="Python micro-framework, JSON API.",
        src="backend/flask",
        requirements=("Flask>=3.0", "flask-cors>=4.0"),
        context={"run": ["pip install -r requirements.txt", "python app.py"],
                 "lang": "python"},
    ),
    Module(
        id="fastapi",
        label="FastAPI",
        axis="backend",
        summary="Modern async Python API with auto docs.",
        src="backend/fastapi",
        requirements=("fastapi>=0.110", "uvicorn[standard]>=0.29", "pydantic>=2.0"),
        context={"run": ["pip install -r requirements.txt",
                          "uvicorn main:app --reload --port 8000"],
                 "lang": "python"},
    ),
    Module(
        id="express",
        label="Express",
        axis="backend",
        summary="Node.js / Express JSON API (in-memory store).",
        src="backend/express",
        npm=(("express", "^4.19.2"), ("cors", "^2.8.5")),
        context={"run": ["npm install", "npm run dev"],
                 "lang": "node",
                 "npm_scripts": {"start": "node server.js",
                                 "dev": "node --watch server.js"}},
    ),
    Module(
        id="nethttp",
        label="Go (net/http)",
        axis="backend",
        summary="Go standard-library JSON API (in-memory store).",
        src="backend/nethttp",
        context={"run": ["go run ."], "lang": "go"},
    ),
    Module(id="none", label="No backend", axis="backend",
           summary="Front-end only; uses mock data."),
]


# --------------------------------------------------------------------------- #
# Frontend frameworks
# --------------------------------------------------------------------------- #
_FRONTENDS = [
    Module(
        id="vanilla",
        label="Vanilla JS",
        axis="frontend",
        summary="Plain HTML/CSS/JS, no build step.",
        src="frontend/vanilla",
        context={"run": ["python -m http.server 3000   # open http://localhost:3000"]},
    ),
    Module(
        id="react",
        label="React (Vite)",
        axis="frontend",
        summary="React single-page app via Vite.",
        src="frontend/react",
        npm=(("react", "^18.3.1"), ("react-dom", "^18.3.1")),
        npm_dev=(("@vitejs/plugin-react", "^4.3.1"), ("vite", "^5.4.0")),
        context={"run": ["npm install", "npm run dev"],
                 "npm_type": "module",
                 "npm_scripts": {"dev": "vite", "build": "vite build",
                                 "preview": "vite preview"}},
    ),
    Module(
        id="vue",
        label="Vue (Vite)",
        axis="frontend",
        summary="Vue 3 single-page app via Vite.",
        src="frontend/vue",
        npm=(("vue", "^3.4.0"),),
        npm_dev=(("@vitejs/plugin-vue", "^5.1.0"), ("vite", "^5.4.0")),
        context={"run": ["npm install", "npm run dev"],
                 "npm_type": "module",
                 "npm_scripts": {"dev": "vite", "build": "vite build",
                                 "preview": "vite preview"}},
    ),
    Module(id="none", label="No frontend", axis="frontend",
           summary="API only; no UI generated."),
]


# --------------------------------------------------------------------------- #
# Database / ORM  (SQLAlchemy, Python backends only)
# --------------------------------------------------------------------------- #
_DATABASES = [
    Module(id="none", label="No database", axis="database",
           summary="In-memory sample data.",
           provides=frozenset({"in-memory"})),
    Module(
        id="sqlite",
        label="SQLite",
        axis="database",
        summary="File-backed SQLite via SQLAlchemy.",
        src="database/sql",
        requirements=("SQLAlchemy>=2.0",),
        provides=frozenset({"has-db", "engine:sqlite"}),
        requires=("lang:python",),
        requires_msg="A database needs a Python backend (Flask or FastAPI).",
        context={"db_url": "sqlite:///app.db", "db_driver": "sqlite"},
    ),
    Module(
        id="postgres",
        label="PostgreSQL",
        axis="database",
        summary="PostgreSQL via SQLAlchemy (set DATABASE_URL).",
        src="database/sql",
        requirements=("SQLAlchemy>=2.0", "psycopg2-binary>=2.9"),
        provides=frozenset({"has-db", "engine:postgres"}),
        requires=("lang:python",),
        requires_msg="A database needs a Python backend (Flask or FastAPI).",
        context={"db_url": "postgresql+psycopg2://postgres:postgres@localhost:5432/app",
                 "db_driver": "postgres"},
    ),
]


# --------------------------------------------------------------------------- #
# Styling (context only — no files contributed)
# --------------------------------------------------------------------------- #
_STYLING = [
    Module(id="plain", label="Plain CSS", axis="styling",
           summary="Hand-written CSS, no dependencies."),
    Module(id="bootstrap", label="Bootstrap", axis="styling",
           summary="Bootstrap 5 via CDN."),
    Module(id="tailwind", label="Tailwind", axis="styling",
           summary="Tailwind via Play CDN (great for prototypes)."),
]


# --------------------------------------------------------------------------- #
# Authentication (context-only; backends implement it via the `auth` flag)
# --------------------------------------------------------------------------- #
_AUTH = [
    Module(id="none", label="No auth", axis="auth",
           summary="No authentication."),
    Module(
        id="jwt", label="JWT", axis="auth",
        summary="Stateless HS256 JWT — POST /api/login + protected GET /api/me.",
        requires=("backend",),
        requires_msg="Authentication needs a backend.",
    ),
]


# --------------------------------------------------------------------------- #
# API style (REST default; GraphQL adds a /graphql endpoint)
# --------------------------------------------------------------------------- #
_API = [
    Module(id="rest", label="REST", axis="api",
           summary="Plain JSON REST endpoints."),
    Module(
        id="graphql", label="GraphQL", axis="api",
        summary="Adds a Strawberry /graphql endpoint alongside REST.",
        requirements=("strawberry-graphql>=0.230",),
        # v1: Python backend, in-memory store (no DB-backed resolvers yet).
        requires=("lang:python", "in-memory"),
        requires_msg="GraphQL (this version) needs a Python backend and no database.",
    ),
]


# Core axes are always present in a config; extension axes default to their
# first (no-op) option, so older presets and 4-axis callers keep working.
CORE_AXES = ("backend", "frontend", "database", "styling")
AXES = ("backend", "frontend", "database", "styling", "auth", "api")

AXIS_LABELS = {
    "backend": "Backend framework",
    "frontend": "Frontend framework",
    "database": "Database / ORM",
    "styling": "Styling",
    "auth": "Authentication",
    "api": "API style",
}

OPTIONS: dict[str, list[Module]] = {
    "backend": _BACKENDS,
    "frontend": _FRONTENDS,
    "database": _DATABASES,
    "styling": _STYLING,
    "auth": _AUTH,
    "api": _API,
}


def axis_default(axis: str) -> str:
    """The default (first) option id for an axis."""
    return OPTIONS[axis][0].id

# Flat lookup: (axis, id) -> Module
_INDEX = {(m.axis, m.id): m for mods in OPTIONS.values() for m in mods}


def get_module(axis: str, option_id: str) -> Module:
    try:
        return _INDEX[(axis, option_id)]
    except KeyError as exc:  # pragma: no cover - guarded by validate()
        raise KeyError(f"Unknown {axis} option: {option_id!r}") from exc


# --------------------------------------------------------------------------- #
# Capability tags — single source of truth for server + browser compatibility
# --------------------------------------------------------------------------- #
def _apply_default_tags() -> None:
    """Fill in ``provides`` for modules that didn't set tags explicitly.

    Backends provide ``backend`` + their language; frontends provide
    ``frontend`` + ``framework:<id>`` (+ ``runtime:node`` when they build with
    npm). Data layers and framework-specific styling set their tags inline.
    """
    for mod in _BACKENDS:
        if mod.id == "none" or mod.provides:
            continue
        lang = mod.context.get("lang", "")
        tags = {"backend"}
        if lang:
            tags |= {f"lang:{lang}", f"runtime:{lang}"}
        mod.provides = frozenset(tags)
    for mod in _FRONTENDS:
        if mod.id == "none" or mod.provides:
            continue
        tags = {"frontend", f"framework:{mod.id}", "kind:spa"}
        if mod.npm or mod.npm_dev:
            tags.add("runtime:node")
        mod.provides = frozenset(tags)


_apply_default_tags()


def module_tags() -> dict:
    """Per-option tag metadata for the browser (mirrors the server validator)."""
    return {
        axis: {
            mod.id: {
                "provides": sorted(mod.provides),
                "requires": list(mod.requires),
                "msg": mod.requires_msg,
            }
            for mod in OPTIONS[axis]
        }
        for axis in AXES
    }


# --------------------------------------------------------------------------- #
# Feature add-ons (multi-select, independent of the four axes)
# --------------------------------------------------------------------------- #
# Each add-on is a Module placed under scaffolds/addons/<id>. Add-on templates
# use the path tokens __backend__ / __frontend__ / __root__ to land files in the
# right component. An add-on may declare applicability via context keys
# "requires_backend" / "requires_frontend" (tuples of allowed ids); when the
# current stack doesn't match, the add-on is hidden in the UI and skipped server
# side. Populated in the add-ons build step.
ADDONS: list[Module] = [
    Module(
        id="docker", label="Docker", axis="addon",
        summary="Dockerfiles + Compose (adds a Postgres service when selected).",
        src="addons/docker",
        context={"notes": ["**Docker:** `docker compose up` builds and runs everything."]},
    ),
    Module(
        id="tests", label="Tests", axis="addon",
        summary="pytest smoke tests against the API.",
        src="addons/tests",
        requirements=("pytest>=8.0", "httpx>=0.27"),
        context={
            "requires_backend": ("flask", "fastapi"),
            "notes": ["**Tests:** run `pytest` in the backend folder."],
        },
    ),
    Module(
        id="ci", label="GitHub Actions CI", axis="addon",
        summary="CI workflow that installs deps and builds/compiles on push & PR.",
        src="addons/ci",
        context={"notes": ["**CI:** `.github/workflows/ci.yml` runs on push and PR."]},
    ),
    Module(
        id="lint", label="Lint / format", axis="addon",
        summary="Ruff for Python, Prettier for JS.",
        src="addons/lint",
        requirements=("ruff>=0.5",),
        npm_dev=(("prettier", "^3.3.0"),),
        context={
            "npm_scripts": {"format": "prettier --write ."},
            "notes": ["**Lint:** `ruff check .` (Python) / `npm run format` (JS)."],
        },
    ),
    Module(
        id="env", label="Env config", axis="addon",
        summary="A .env.example listing the app's environment variables.",
        src="addons/env",
        context={
            "requires_backend": ("flask", "fastapi", "express"),
            "notes": ["**Env:** copy `.env.example` to `.env` and adjust."],
        },
    ),
    Module(
        id="license", label="MIT License", axis="addon",
        summary="Adds an MIT LICENSE file.",
        src="addons/license",
        context={"notes": ["**License:** MIT (see `LICENSE`)."]},
    ),
]

ADDON_LABELS = {m.id: m.label for m in ADDONS}

_ADDON_INDEX = {m.id: m for m in ADDONS}


def get_addon(addon_id: str) -> Module:
    return _ADDON_INDEX[addon_id]


def addon_applies(mod: Module, selection: dict) -> bool:
    """Whether an add-on is compatible with the chosen stack."""
    rb = mod.context.get("requires_backend")
    rf = mod.context.get("requires_frontend")
    if rb and selection.get("backend") not in rb:
        return False
    if rf and selection.get("frontend") not in rf:
        return False
    return True
