# ROADMAP — remaining objectives & how to finish them

Read **[CLAUDE.md](CLAUDE.md)** first (architecture, conventions, gotchas). This file
is the work queue + copy-paste recipes. Goal of the project: be *exhaustive* across
axes/options and languages, while **every generated combo actually runs**.

## Status snapshot
- 7 axes, all tag-driven. 15 backends / 4 languages, 7 frontends. ~301 tests pass
  (1 skipped = Ruby `ruby -c`, no local toolchain). Pairwise keeps the suite ~10s.
- **Cloud HTTP API landed** (the end goal): `POST /api/generate` (JSON→zip, lenient
  body), `GET /api/options` (discovery), `GET /api/health`, `GET /api/openapi.json`,
  with open CORS, env-gated `x-api-key`, and JSON errors — all scoped to `/api/*` in
  [app.py](app.py). `vercel.json` makes it deployable (`@vercel/python` + the
  critical `includeFiles`). Verified via `tests/test_http_api.py` + a real-socket
  smoke. **Remaining = a user step:** `vercel dev`/`vercel deploy` (touches the
  user's Vercel account) and setting `API_KEY` + Python 3.12 in project settings.
- **Django landed** (Objective #2): self-contained Python backend (own ORM +
  built-in SQLite). It deliberately does NOT provide the `data:shared` tag, so the
  database axis is forced to `none` (every non-`none` DB option requires that tag).
  Live-verified end-to-end (CRUD + JWT) on Django 6.
- **Node data story is DONE** via the **repo seam** (Objective #1 complete): Drizzle
  (SQLite/Postgres/MySQL), Mongoose (Mongo), Prisma (SQLite/Postgres). Backends are
  data-layer-agnostic, so each ORM is a pure `repo.js` drop-in — zero backend edits.
  Async drivers (postgres-js/mysql2/mongoose) use a `ready` promise in `db.js`
  (table create + seed) that `repo.js` awaits per call, so async setup never races
  the first request. Docker addon is **data-driven**: each server-DB module carries a
  `docker` descriptor → `build_context` exposes `docker_db` → compose adds the right
  service (postgres:16 / mysql:8 / mongo:7) with a driver-aware DATABASE_URL; file/
  in-memory stores add none. Prisma wires `prisma generate` (postinstall) + `prisma
  db push` (predev/prestart) via npm lifecycle scripts — no backend/composer edits.

## Objectives (priority order)

### 0. ✅ DONE (code) — Cloud HTTP API on Vercel  ·  ⏳ deploy is a user step
The generator is now a JSON API callable from other apps. All in [app.py](app.py),
scoped to `/api/*`: `POST /api/generate` (lenient body via `_parse_api_request`),
`GET /api/options`, `GET /api/health`, `GET /api/openapi.json`; `_cors_headers`
(open CORS), `_api_gate` (preflight + env-gated `x-api-key`), JSON error handlers.
[`vercel.json`](vercel.json) builds `app.py` with `@vercel/python`; **`includeFiles`
is load-bearing** (bundles `scaffolds/`/`templates/`/`public/`/`generator/` — without
it prod 500s on `FileNotFoundError`, even though local works). Spec in
`public/openapi.json`, examples in [API.md](API.md). Tests: `tests/test_http_api.py`.
- **To finish (needs the user's Vercel account):** `vercel dev` to confirm
  `includeFiles` bundles the data dirs (a 200 on `/api/health` does NOT prove
  generation works — must POST `/api/generate` under `vercel dev`); then `vercel`
  (preview) → `vercel --prod`. Set **Python 3.12** in project settings and an
  optional **`API_KEY`** env var to lock the generate endpoint.
- **Later (out of scope):** rate limiting (needs Upstash/Redis on serverless),
  API-key issuance/metering, a base64-in-JSON response variant.

### 1. ✅ DONE — Node data story (rode the repo seam)
All six Node data layers shipped as `scaffolds/database/<id>/` drop-ins + registry
entries, no backend edits. Tests in `tests/test_node_db.py` (render + `node --check`
across 6 DBs × 4 backends, both seed branches, + docker-compose service per engine).
Verified render + syntax here; live DB runs (servers + `prisma generate` network) are
CI-only. New seam helpers added along the way: `Entity.camel` (Prisma client
delegate), `Field.prisma` (Prisma field type), the `docker_db` context descriptor.
- **Drizzle + Postgres** (`drizzle-postgres`), **Drizzle + MySQL** (`drizzle-mysql`,
  no RETURNING → create re-reads by `insertId`, remove uses `affectedRows`),
  **MongoDB** (`mongo`, Mongoose; ObjectId surfaced as a string `id`, invalid ids →
  not-found), **Prisma** (`prisma-sqlite` literal `file:` url / `prisma-postgres`
  `env("DATABASE_URL")`; one scaffold, two registry entries like `database/sql`).
- **If extending:** the async-driver precedent is `database/drizzle-postgres`; the
  "one scaffold serves two engines via context" precedent is `database/prisma`.
- **Optional polish:** Drizzle+MySQL `boolean` reads back as tinyint via the driver
  (drizzle casts it); a `mongo` auth/replica-set note for production; Prisma needs
  network on install (engine download) — already documented in the option summary.

### 2. ✅ DONE — Django (Python, own ORM, self-contained)
`scaffolds/backend/django/` — `manage.py`, `project/{settings,urls,wsgi,middleware}.py`
(minimal: `INSTALLED_APPS=["app"]`, a dependency-free CORS middleware, no admin/auth
apps), `app/{models,views,apps}.py`. Plain `JsonResponse` views (no DRF), generic and
schema-driven via a `REGISTRY` (plural → model + fields); `Field.django` maps types.
JWT is the same stdlib HS256 as the other Python backends. **Tag design (the crux):**
backends now provide `data:shared` (added in `_apply_default_tags`); Django sets
`provides` explicitly *without* it, and every non-`none` DB option `requires`
`data:shared` → Django is only valid with `database=none` and supplies its own SQLite.
Seed via a `post_migrate` signal in `app/apps.py` (default schema only). Run steps +
Docker CMD use `migrate --run-syncdb` (app ships no migrations → syncdb creates tables;
do NOT add an empty `migrations/` package, or syncdb skips it). **Live-verified**:
venv + `pip install Django` (6.0) + `migrate --run-syncdb` + `runserver` → seed, full
CRUD, JWT login/me/401 all pass. Pairwise matrix py_compiles it automatically.

### 3. New language backends (MED, **CI-only** verification)
PHP, Java, C#, Elixir, Rust. Each = one backend scaffold (schema-driven in-memory
CRUD + stdlib HS256 JWT) + a manifest + registry entry, following the **Sinatra**
precedent (`scaffolds/backend/sinatra/app.rb.j2`, `_gemfile` in composer). They can
only be authored + structurally tested here (no toolchains) — **do them against a CI
image that has the toolchain** so the gated check (`php -l`, `dotnet build`, `javac`/
`mvn`, `mix compile`, `cargo check`) actually runs. Watch execution-model wrinkles:
PHP is shared-nothing (use a file/SQLite store, not in-memory globals); Elixir needs
an Agent/ETS for mutable state; Rust/Elixir need framework crates/deps. Add a
manifest builder branch in `_build_manifests` per language (composer.py) — see
`_go_mod`/`_gemfile` for the pattern, or ship the manifest as a scaffold file.

### 4. Angular frontend (MED) — revisit, was cut
The Vite + `@analogjs/vite-plugin-angular` path produced a **silently broken** build
(exit 0 but 0.7 KB bundle — AOT didn't run; tsconfig-resolution warning). Redo it
with the **official `@angular/cli` toolchain** (`angular.json`, `ng build`) instead of
the Vite/Analog plugin. Heavier setup; verify the dist bundle is real (>100 KB) before
shipping. Don't re-ship until `ng build` produces a genuine bundle.

### 5. More styling options (LOW–MED) — refactor first
Bulma/Pico/Open-Props (CDN, cheap), Sass (build), MUI/Chakra (React), Vuetify (Vue).
**Problem:** styling is currently handled inline in *every* frontend template
(`[% if styling=="bootstrap" %]...`), so each new option touches all 7 frontends.
**Recommended first:** centralize — compute `styling_head` (CDN/link HTML) + a class
map in `build_context`, have frontends emit `[[ styling_head ]]` / `[[ cls.input ]]`,
then new CDN styling = a registry/context entry only. Do this refactor before adding
many styling options.

### 6. CI toolchain matrix + verification harness (MED, enables #3)
- Stand up CI (GitHub Actions) that installs Python/Node/Go/Ruby/PHP/.NET/JVM/Elixir/
  Rust and runs `pytest` — so the toolchain-gated checks/builds actually execute and
  the "it runs" guarantee is enforced for every language, not just the three local ones.
- Optional: centralize the per-language static checks (currently inline + `shutil.which`
  gated in each test) into one helper (the long-deferred "Phase 0.6 verification
  harness"). Low value until #3 lands.

### 7. (Optional) Python repo-seam symmetry (LOW)
Give the Python backends the same `repo` seam as Node to unlock Tortoise/Peewee
alongside SQLAlchemy. Nice consistency; not required.

---

## Recipes (copy the named precedent)

**Add a backend** — folder `scaffolds/backend/<id>/` with the server file (loop
`entities`; per-entity routes `[[ entity.route ]]` for list/create/get/update/delete;
gate `[% if auth == "jwt" %]` JWT block — copy from any backend; Node backends call
`repo.x("[[ entity.plural ]]")`, Python use SQLAlchemy/`has_db` inline, Go use typed
structs via `f.pascal`/`f.go`). Register in `registry.py` `_BACKENDS` with
`context={"lang": "...", "run": [...]}` + deps (`requirements`/`npm`/`go_require`/
`gems`). Add a `_build_manifests` branch if it's a new language. Verify: render →
language check → live boot → CRUD+JWT.

**Add a frontend (SPA)** — folder `scaffolds/frontend/<id>/` (`data.js[.j2]` with
`ENTITIES`/`API`/`coerce`, an app component looping entities + a typed input per field,
`index.html`, `vite.config`, `styles.css`). Register with `npm`/`npm_dev`/`npm_scripts`
(`npm_type:"module"`). `spa` is auto-true when the module has npm deps. Verify:
`npm install` + `vite build`.

**Add a Node data layer (ORM)** — folder `scaffolds/database/<id>/`: `schema.js.j2`
(tables from entities + `columns` allow-lists keyed by plural), `db.js.j2` (connection +
create-tables + seed when `is_default_schema`), `repo.js.j2` (the async repo API).
Register a `database` option: `requires=("lang:node",)`, `provides={"has-db",
"engine:<x>","db:<orm>"}`, npm deps (fold automatically via `side_mods`). **No backend
changes.** Verify: render + `node --check` + live CRUD + **restart-persistence**.

**Add a new language** — see Objective #3. Backend scaffold + manifest (builder branch
or scaffold file) + registry (`context["lang"]`). Author + gated check; verify in CI.

**Add an axis** — append to `AXES`/`OPTIONS`/`AXIS_LABELS`, add to `app.py` `DEFAULTS`,
update `test_preset.py` CONFIG `stack`. Options self-describe via tags. Backends/
frontends read the new axis value from context (it's exposed generically). Precedents:
auth (`_AUTH`), api (`_API`), pkg (`_PKG`).

## Verification playbook (per change)
1. `pytest -q` green (pairwise matrix renders+compiles every option/pair).
2. Generate to a temp dir (`compose(...)` + `zipper.to_zip` → extract), install deps,
   boot, curl `GET/POST/PUT/DELETE /api/<plural>` + JWT login/`me`/401; for DB, restart
   and confirm rows persist. Then kill port 8000 + delete the temp dir.
3. UI: `preview_start` the generator, eval that the new option renders and tag-gating
   enables/disables it correctly, check no console errors, stop the preview.
4. Update the README catalog table + add a focused test (render + gated language check).
