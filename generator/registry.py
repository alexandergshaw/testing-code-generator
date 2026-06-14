"""The catalogue of stack options and the compatibility rules between them.

This module is pure data + a couple of small helpers. Both the server-side
validator (``composer.validate``) and the browser form (``static/js/form.js``,
fed via the index template) consume ``CONSTRAINTS`` so the two never drift.

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
           summary="In-memory sample data."),
    Module(
        id="sqlite",
        label="SQLite",
        axis="database",
        summary="File-backed SQLite via SQLAlchemy.",
        src="database/sql",
        requirements=("SQLAlchemy>=2.0",),
        context={"db_url": "sqlite:///app.db", "db_driver": "sqlite"},
    ),
    Module(
        id="postgres",
        label="PostgreSQL",
        axis="database",
        summary="PostgreSQL via SQLAlchemy (set DATABASE_URL).",
        src="database/sql",
        requirements=("SQLAlchemy>=2.0", "psycopg2-binary>=2.9"),
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


AXES = ("backend", "frontend", "database", "styling")

AXIS_LABELS = {
    "backend": "Backend framework",
    "frontend": "Frontend framework",
    "database": "Database / ORM",
    "styling": "Styling",
}

OPTIONS: dict[str, list[Module]] = {
    "backend": _BACKENDS,
    "frontend": _FRONTENDS,
    "database": _DATABASES,
    "styling": _STYLING,
}

# Flat lookup: (axis, id) -> Module
_INDEX = {(m.axis, m.id): m for mods in OPTIONS.values() for m in mods}


def get_module(axis: str, option_id: str) -> Module:
    try:
        return _INDEX[(axis, option_id)]
    except KeyError as exc:  # pragma: no cover - guarded by validate()
        raise KeyError(f"Unknown {axis} option: {option_id!r}") from exc


# --------------------------------------------------------------------------- #
# Compatibility rules — single source of truth for server + browser
# --------------------------------------------------------------------------- #
#   when:    this rule applies when selection[when.axis] is in when.values
#   require: then selection[require.axis] MUST be in require.values
#   forbid:  then selection[forbid.axis] must NOT be in forbid.values
CONSTRAINTS = [
    {
        "when": {"axis": "backend", "values": ["none"]},
        "require": {"axis": "database", "values": ["none"]},
        "message": "A project with no backend can't include a database.",
    },
    {
        "when": {"axis": "backend", "values": ["none"]},
        "forbid": {"axis": "frontend", "values": ["none"]},
        "message": "Pick at least a backend or a frontend — not neither.",
    },
    {
        "when": {"axis": "database", "values": ["sqlite", "postgres"]},
        "require": {"axis": "backend", "values": ["flask", "fastapi"]},
        "message": "A database needs a Python backend (Flask or FastAPI).",
    },
]
