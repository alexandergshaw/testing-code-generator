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

import json
from dataclasses import dataclass, field
from pathlib import Path


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
# Version pins — single source of truth, kept fresh from each ecosystem's
# official registry by Renovate (see versions.json + renovate.json). The helpers
# build the per-ecosystem dependency specs modules declare, so a version bump only
# ever edits versions.json — never this catalogue.
# --------------------------------------------------------------------------- #
VERSIONS = json.loads(
    (Path(__file__).resolve().parent / "versions.json").read_text(encoding="utf-8")
)


def v(ecosystem: str, name: str) -> str:
    """The pinned version string for ``name`` in ``ecosystem`` (from versions.json)."""
    return VERSIONS[ecosystem][name]


def _npm(*names):
    return tuple((n, v("npm", n)) for n in names)


def _pypi(*specs):
    # ``specs`` may carry extras (e.g. "uvicorn[standard]"); the version key is the
    # bare package name.
    return tuple(f"{s}{v('pypi', s.split('[')[0])}" for s in specs)


def _go(*modules):
    return tuple((m, v("golang", m)) for m in modules)


def _gems(*names):
    return tuple((n, v("rubygems", n)) for n in names)


def docker_image(name: str) -> str:
    """``"postgres"`` -> ``"postgres:16"`` using the pinned tag."""
    return f"{name}:{v('docker', name)}"


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
        requirements=_pypi("Flask", "flask-cors"),
        context={"run": ["pip install -r requirements.txt", "python app.py"],
                 "lang": "python", "extra_provides": ("graphql:strawberry",)},
    ),
    Module(
        id="fastapi",
        label="FastAPI",
        axis="backend",
        summary="Modern async Python API with auto docs.",
        src="backend/fastapi",
        requirements=_pypi("fastapi", "uvicorn[standard]", "pydantic"),
        context={"run": ["pip install -r requirements.txt",
                          "uvicorn main:app --reload --port 8000"],
                 "lang": "python", "extra_provides": ("graphql:strawberry",)},
    ),
    Module(
        id="litestar",
        label="Litestar",
        axis="backend",
        summary="Modern Python ASGI API (Litestar).",
        src="backend/litestar",
        requirements=_pypi("litestar[standard]"),
        context={"run": ["pip install -r requirements.txt",
                          "uvicorn main:app --port 8000"],
                 "lang": "python"},
    ),
    Module(
        id="starlette",
        label="Starlette",
        axis="backend",
        summary="Lightweight Python ASGI API (Starlette).",
        src="backend/starlette",
        requirements=_pypi("starlette", "uvicorn[standard]"),
        context={"run": ["pip install -r requirements.txt",
                          "uvicorn main:app --port 8000"],
                 "lang": "python"},
    ),
    Module(
        id="django",
        label="Django",
        axis="backend",
        summary="Python / Django — own ORM + built-in SQLite, JSON API.",
        src="backend/django",
        requirements=_pypi("Django"),
        # Self-contained: Django brings its own ORM + SQLite, so it does NOT
        # provide ``data:shared`` — every non-``none`` database option requires
        # that tag, so the database axis is effectively forced to ``none`` here.
        provides=frozenset({"backend", "lang:python", "runtime:python"}),
        requires_msg="Django supplies its own database; leave Database set to none.",
        context={"run": ["pip install -r requirements.txt",
                         "python manage.py migrate --run-syncdb",
                         "python manage.py runserver 8000"],
                 "lang": "python"},
    ),
    Module(
        id="express",
        label="Express",
        axis="backend",
        summary="Node.js / Express JSON API (in-memory store).",
        src="backend/express",
        npm=_npm("express", "cors"),
        context={"run": ["npm install", "npm run dev"],
                 "lang": "node",
                 "npm_scripts": {"start": "node server.js",
                                 "dev": "node --watch server.js"}},
    ),
    Module(
        id="fastify",
        label="Fastify",
        axis="backend",
        summary="Node.js / Fastify JSON API (in-memory store).",
        src="backend/fastify",
        npm=_npm("fastify"),
        context={"run": ["npm install", "npm run dev"],
                 "lang": "node",
                 "npm_scripts": {"start": "node server.js",
                                 "dev": "node --watch server.js"}},
    ),
    Module(
        id="hono",
        label="Hono",
        axis="backend",
        summary="Hono (Node) JSON API (in-memory store).",
        src="backend/hono",
        npm=_npm("hono", "@hono/node-server"),
        context={"run": ["npm install", "npm run dev"],
                 "lang": "node",
                 "npm_scripts": {"start": "node server.js",
                                 "dev": "node --watch server.js"}},
    ),
    Module(
        id="koa",
        label="Koa",
        axis="backend",
        summary="Node.js / Koa JSON API (in-memory store).",
        src="backend/koa",
        npm=_npm("koa", "@koa/router", "koa-bodyparser"),
        context={"run": ["npm install", "npm run dev"],
                 "lang": "node",
                 "npm_scripts": {"start": "node server.js",
                                 "dev": "node --watch server.js"}},
    ),
    Module(
        id="nestjs",
        label="NestJS",
        axis="backend",
        summary="Node.js / NestJS (TypeScript) JSON API (in-memory store).",
        src="backend/nestjs",
        npm=_npm("@nestjs/common", "@nestjs/core", "@nestjs/platform-express",
                 "reflect-metadata", "rxjs"),
        npm_dev=_npm("typescript", "@types/node"),
        context={"run": ["npm install", "npm run build", "npm start"],
                 "lang": "node",
                 "npm_scripts": {"build": "tsc", "start": "node dist/main.js"}},
    ),
    Module(
        id="nethttp",
        label="Go (net/http)",
        axis="backend",
        summary="Go standard-library JSON API (in-memory store).",
        src="backend/nethttp",
        context={"run": ["go run ."], "lang": "go"},
    ),
    Module(
        id="gin",
        label="Gin (Go)",
        axis="backend",
        summary="Go Gin JSON API (in-memory store).",
        src="backend/gin",
        context={"run": ["go mod tidy", "go run ."], "lang": "go",
                 "go_require": _go("github.com/gin-gonic/gin")},
    ),
    Module(
        id="chi",
        label="Chi (Go)",
        axis="backend",
        summary="Go Chi JSON API (in-memory store).",
        src="backend/chi",
        context={"run": ["go mod tidy", "go run ."], "lang": "go",
                 "go_require": _go("github.com/go-chi/chi/v5")},
    ),
    Module(
        id="echo",
        label="Echo (Go)",
        axis="backend",
        summary="Go Echo JSON API (in-memory store).",
        src="backend/echo",
        context={"run": ["go mod tidy", "go run ."], "lang": "go",
                 "go_require": _go("github.com/labstack/echo/v4")},
    ),
    Module(
        id="sinatra",
        label="Sinatra (Ruby)",
        axis="backend",
        summary="Ruby Sinatra JSON API (in-memory store).",
        src="backend/sinatra",
        context={"run": ["bundle install", "ruby app.rb"], "lang": "ruby",
                 "gems": _gems("sinatra", "puma", "rackup")},
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
        npm=_npm("react", "react-dom"),
        npm_dev=_npm("@vitejs/plugin-react", "vite"),
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
        npm=_npm("vue"),
        npm_dev=_npm("@vitejs/plugin-vue", "vite"),
        context={"run": ["npm install", "npm run dev"],
                 "npm_type": "module",
                 "npm_scripts": {"dev": "vite", "build": "vite build",
                                 "preview": "vite preview"}},
    ),
    Module(
        id="svelte",
        label="Svelte (Vite)",
        axis="frontend",
        summary="Svelte 5 single-page app via Vite.",
        src="frontend/svelte",
        npm=_npm("svelte"),
        npm_dev=_npm("@sveltejs/vite-plugin-svelte", "vite"),
        context={"run": ["npm install", "npm run dev"],
                 "npm_type": "module",
                 "npm_scripts": {"dev": "vite", "build": "vite build",
                                 "preview": "vite preview"}},
    ),
    Module(
        id="preact",
        label="Preact (Vite)",
        axis="frontend",
        summary="Preact single-page app via Vite.",
        src="frontend/preact",
        npm=_npm("preact"),
        npm_dev=_npm("@preact/preset-vite", "vite"),
        context={"run": ["npm install", "npm run dev"],
                 "npm_type": "module",
                 "npm_scripts": {"dev": "vite", "build": "vite build",
                                 "preview": "vite preview"}},
    ),
    Module(
        id="solid",
        label="SolidJS (Vite)",
        axis="frontend",
        summary="SolidJS single-page app via Vite.",
        src="frontend/solid",
        npm=_npm("solid-js"),
        npm_dev=_npm("vite-plugin-solid", "vite"),
        context={"run": ["npm install", "npm run dev"],
                 "npm_type": "module",
                 "npm_scripts": {"dev": "vite", "build": "vite build",
                                 "preview": "vite preview"}},
    ),
    Module(
        id="lit",
        label="Lit (Vite)",
        axis="frontend",
        summary="Lit web-components SPA via Vite.",
        src="frontend/lit",
        npm=_npm("lit"),
        npm_dev=_npm("vite"),
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
           src="database/memory",
           provides=frozenset({"in-memory"})),
    Module(
        id="sqlite",
        label="SQLite",
        axis="database",
        summary="File-backed SQLite via SQLAlchemy.",
        src="database/sql",
        requirements=_pypi("SQLAlchemy"),
        provides=frozenset({"has-db", "engine:sqlite"}),
        requires=("lang:python", "data:shared"),
        requires_msg="A database needs a Python backend (Flask or FastAPI).",
        context={"db_url": "sqlite:///app.db", "db_driver": "sqlite"},
    ),
    Module(
        id="postgres",
        label="PostgreSQL",
        axis="database",
        summary="PostgreSQL via SQLAlchemy (set DATABASE_URL).",
        src="database/sql",
        requirements=_pypi("SQLAlchemy", "psycopg2-binary"),
        provides=frozenset({"has-db", "engine:postgres"}),
        requires=("lang:python", "data:shared"),
        requires_msg="A database needs a Python backend (Flask or FastAPI).",
        context={"db_url": "postgresql+psycopg2://postgres:postgres@localhost:5432/app",
                 "db_driver": "postgres",
                 "docker": {"image": docker_image("postgres"), "port": "5432",
                            "url": "postgresql+psycopg2://postgres:postgres@db:5432/app",
                            "env": {"POSTGRES_PASSWORD": "postgres", "POSTGRES_DB": "app"}}},
    ),
    Module(
        id="drizzle-sqlite",
        label="Drizzle + SQLite",
        axis="database",
        summary="SQLite via Drizzle ORM (Node, better-sqlite3).",
        src="database/drizzle",
        npm=_npm("drizzle-orm", "better-sqlite3"),
        provides=frozenset({"has-db", "engine:sqlite", "db:drizzle"}),
        requires=("lang:node", "data:shared"),
        requires_msg="Drizzle needs a Node backend.",
    ),
    Module(
        id="drizzle-postgres",
        label="Drizzle + PostgreSQL",
        axis="database",
        summary="PostgreSQL via Drizzle ORM (Node, postgres-js; set DATABASE_URL).",
        src="database/drizzle-postgres",
        npm=_npm("drizzle-orm", "postgres"),
        provides=frozenset({"has-db", "engine:postgres", "db:drizzle"}),
        requires=("lang:node", "data:shared"),
        requires_msg="Drizzle needs a Node backend.",
        context={"db_url": "postgres://postgres:postgres@localhost:5432/app",
                 "docker": {"image": docker_image("postgres"), "port": "5432",
                            "url": "postgres://postgres:postgres@db:5432/app",
                            "env": {"POSTGRES_PASSWORD": "postgres", "POSTGRES_DB": "app"}}},
    ),
    Module(
        id="drizzle-mysql",
        label="Drizzle + MySQL",
        axis="database",
        summary="MySQL via Drizzle ORM (Node, mysql2; set DATABASE_URL).",
        src="database/drizzle-mysql",
        npm=_npm("drizzle-orm", "mysql2"),
        provides=frozenset({"has-db", "engine:mysql", "db:drizzle"}),
        requires=("lang:node", "data:shared"),
        requires_msg="Drizzle needs a Node backend.",
        context={"db_url": "mysql://root:root@localhost:3306/app",
                 "docker": {"image": docker_image("mysql"), "port": "3306",
                            "url": "mysql://root:root@db:3306/app",
                            "env": {"MYSQL_ROOT_PASSWORD": "root", "MYSQL_DATABASE": "app"}}},
    ),
    Module(
        id="mongo",
        label="MongoDB (Mongoose)",
        axis="database",
        summary="MongoDB via Mongoose ODM (Node; set DATABASE_URL).",
        src="database/mongo",
        npm=_npm("mongoose"),
        provides=frozenset({"has-db", "engine:mongo", "db:mongoose"}),
        requires=("lang:node", "data:shared"),
        requires_msg="Mongoose needs a Node backend.",
        context={"db_url": "mongodb://localhost:27017/app",
                 "docker": {"image": docker_image("mongo"), "port": "27017",
                            "url": "mongodb://db:27017/app", "env": {}}},
    ),
    Module(
        id="prisma-sqlite",
        label="Prisma + SQLite",
        axis="database",
        summary="SQLite via Prisma ORM (Node; runs `prisma generate` on install).",
        src="database/prisma",
        npm=_npm("@prisma/client"),
        npm_dev=_npm("prisma"),
        provides=frozenset({"has-db", "engine:sqlite", "db:prisma"}),
        requires=("lang:node", "data:shared"),
        requires_msg="Prisma needs a Node backend.",
        context={"db_url": "file:./dev.db",
                 "prisma_provider": "sqlite",
                 "prisma_url": '"file:./dev.db"',
                 "npm_scripts": {"postinstall": "prisma generate",
                                 "predev": "prisma db push --skip-generate",
                                 "prestart": "prisma db push --skip-generate"}},
    ),
    Module(
        id="prisma-postgres",
        label="Prisma + PostgreSQL",
        axis="database",
        summary="PostgreSQL via Prisma ORM (Node; runs `prisma generate` on install).",
        src="database/prisma",
        npm=_npm("@prisma/client"),
        npm_dev=_npm("prisma"),
        provides=frozenset({"has-db", "engine:postgres", "db:prisma"}),
        requires=("lang:node", "data:shared"),
        requires_msg="Prisma needs a Node backend.",
        context={"db_url": "postgresql://postgres:postgres@localhost:5432/app",
                 "prisma_provider": "postgresql",
                 "prisma_url": 'env("DATABASE_URL")',
                 "npm_scripts": {"postinstall": "prisma generate",
                                 "predev": "prisma db push --skip-generate",
                                 "prestart": "prisma db push --skip-generate"},
                 "docker": {"image": docker_image("postgres"), "port": "5432",
                            "url": "postgresql://postgres:postgres@db:5432/app",
                            "env": {"POSTGRES_PASSWORD": "postgres", "POSTGRES_DB": "app"}}},
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
        requirements=_pypi("strawberry-graphql"),
        # v1: Flask/FastAPI (which ship the Strawberry schema), in-memory store.
        requires=("graphql:strawberry", "in-memory"),
        requires_msg="GraphQL (this version) needs Flask or FastAPI and no database.",
    ),
]


# --------------------------------------------------------------------------- #
# Package manager (JS toolchain; tunes install/run commands + package.json)
# --------------------------------------------------------------------------- #
_PKG = [
    Module(id="npm", label="npm", axis="pkg",
           summary="Default Node package manager."),
    Module(id="pnpm", label="pnpm", axis="pkg",
           summary="Fast, disk-efficient package manager.",
           requires=("runtime:node",),
           requires_msg="pnpm needs a Node backend or a build-step frontend.",
           context={"pm_field": "pnpm@9.12.0"}),
    Module(id="yarn", label="Yarn", axis="pkg",
           summary="Yarn package manager.",
           requires=("runtime:node",),
           requires_msg="Yarn needs a Node backend or a build-step frontend.",
           context={"pm_field": "yarn@4.5.0"}),
    Module(id="bun", label="Bun", axis="pkg",
           summary="Bun runtime + package manager.",
           requires=("runtime:node",),
           requires_msg="Bun needs a Node backend or a build-step frontend.",
           context={"pm_field": "bun@1.1.34"}),
]


# Core axes are always present in a config; extension axes default to their
# first (no-op) option, so older presets and 4-axis callers keep working.
CORE_AXES = ("backend", "frontend", "database", "styling")
AXES = ("backend", "frontend", "database", "styling", "auth", "api", "pkg")

AXIS_LABELS = {
    "backend": "Backend framework",
    "frontend": "Frontend framework",
    "database": "Database / ORM",
    "styling": "Styling",
    "auth": "Authentication",
    "api": "API style",
    "pkg": "Package manager",
}

OPTIONS: dict[str, list[Module]] = {
    "backend": _BACKENDS,
    "frontend": _FRONTENDS,
    "database": _DATABASES,
    "styling": _STYLING,
    "auth": _AUTH,
    "api": _API,
    "pkg": _PKG,
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

    Backends provide ``backend`` + their language + ``data:shared`` (they consume
    a data layer from the database axis — SQLAlchemy for Python, the repo seam for
    Node); frontends provide ``frontend`` + ``framework:<id>`` (+ ``runtime:node``
    when they build with npm). A self-contained backend (e.g. Django, which owns
    its ORM) opts out simply by setting ``provides`` explicitly without
    ``data:shared`` — then every non-``none`` database option (which requires it)
    becomes incompatible. Data layers and framework-specific styling set their tags
    inline.
    """
    for mod in _BACKENDS:
        if mod.id == "none" or mod.provides:
            continue
        lang = mod.context.get("lang", "")
        tags = {"backend", "data:shared"}
        if lang:
            tags |= {f"lang:{lang}", f"runtime:{lang}"}
        tags |= set(mod.context.get("extra_provides", ()))
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
        requirements=_pypi("pytest", "httpx"),
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
        requirements=_pypi("ruff"),
        npm_dev=_npm("prettier"),
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
