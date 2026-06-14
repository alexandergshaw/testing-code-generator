# ROADMAP — remaining objectives & how to finish them

Read **[CLAUDE.md](CLAUDE.md)** first (architecture, conventions, gotchas). This file
is the work queue + copy-paste recipes. Goal of the project: be *exhaustive* across
axes/options and languages, while **every generated combo actually runs**.

## Status snapshot
- 7 axes, all tag-driven. 14 backends / 4 languages, 7 frontends. ~223 tests pass
  (1 skipped = Ruby `ruby -c`, no local toolchain). Pairwise keeps the suite ~10s.
- Node DB via the **repo seam**: Drizzle+SQLite **and** Drizzle+Postgres landed.
  Backends are data-layer-agnostic, so new ORMs are a `repo.js` drop-in, not
  per-backend edits. Postgres uses async postgres-js: `db.js` exposes a `ready`
  promise (table create + seed) that `repo.js` awaits per call, so async setup
  never races the first request without touching handlers. Docker addon now spins
  up a `postgres:16` service for `drizzle-postgres` too (driver-aware DATABASE_URL).

## Objectives (priority order)

### 1. Finish the Node data story — ride the repo seam (HIGH, live-verifiable)
Backends already call the async `repo` API, so each new option is just a new data
module under `scaffolds/database/<id>/` (schema/db/repo) + a registry entry. No
backend edits. Follow the `database/drizzle` precedent.
- **Drizzle + Postgres** (`drizzle-postgres`) — ✅ DONE. `scaffolds/database/drizzle-postgres/`
  (pg-core schema + postgres-js `db.js` with a `ready` promise + async `repo.js`).
  Registered with `engine:postgres`/`db:drizzle`/`lang:node` + `db_url` context;
  docker-compose generalized to add a Postgres service for it. Tests in
  `tests/test_node_db.py` (render + `node --check` both schema branches + compose).
  Verified render + syntax here; live Postgres run is CI-only. **Use this as the
  precedent for the async-driver ORMs below (Mongo/MySQL/Prisma).**
- **Prisma** (`prisma-postgres`/`prisma-sqlite`): ships `schema.prisma` (generated from
  entities) + a repo using `@prisma/client`. Note: needs `prisma generate` in the run
  steps (`context["run"]`) — it downloads a query-engine binary, so it's *not* offline;
  document that. Gate `requires=("lang:node",)`.
- **MySQL** (Drizzle `mysql-core` + `mysql2`) and **MongoDB** (`mongoose`, schemaless
  repo) — same drop-in shape, new `engine:` tags.

### 2. Django (Python, own ORM) (MED, live-verifiable, special-case)
Django can't reuse the shared SQLAlchemy `db.py` — it has its own ORM + project
layout (`manage.py`, `settings.py`, `urls.py`, `wsgi.py`, an app with `models.py`,
DRF or plain `JsonResponse` views). Decision needed: make `backend=django` **self-
contained** (brings its own SQLite via Django ORM, schema-driven models) and have it
provide a tag so the `database` axis is constrained for it (e.g. django provides
`in-memory`-equivalent or its own `has-db`; simplest: `django` `requires` nothing and
the data axis is forced to `none` for it via a tag, with Django supplying DB itself).
This is the one backend that doesn't fit the shared-data-layer model — plan it
deliberately.

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
