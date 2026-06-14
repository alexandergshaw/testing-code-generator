# CLAUDE.md — project guide

Deterministic **tech-stack app generator**: a Flask UI lets a user pick a stack
(across 7 axes), define data entities, and download a ready-to-run app as a zip.
The same engine is exposed as a **JSON HTTP API** (`POST /api/generate` → zip) for
other apps. **No LLMs** — everything is Jinja2 template composition. Core promise:
**every generated combo actually runs.** Deployed on Vercel via `vercel.json`
(`@vercel/python` builds `app.py`; `includeFiles` bundles `scaffolds/`+`templates/`
— without it generation 500s in prod); all generation in-memory (`BytesIO`).

> **Remaining work + step-by-step recipes live in [ROADMAP.md](ROADMAP.md).** Read it
> before extending the catalog.

## Run & test
```bash
.venv\Scripts\activate                      # Windows (venv already set up)
pip install -r requirements-dev.txt
pytest -q                                   # ~214 tests, ~10s
python app.py                               # generator UI at http://localhost:5000
```
Local toolchains for live-verifying generated apps: **Python, Node, Go** only.
Ruby/PHP/Java/C#/Elixir/Rust are **not installed** → those scaffolds can only be
authored + structurally tested here; real compile/run is CI-only.

## Architecture (all under `generator/`)
- **`registry.py`** — the catalogue. `Module` dataclass (`id,label,axis,src,
  requirements,npm,npm_dev,provides,requires,requires_msg,context`). `OPTIONS` per
  axis, `AXES`, `CORE_AXES`, `ADDONS`. `_apply_default_tags()` derives provides from
  axis+lang (+`context["extra_provides"]`). Compatibility is **capability tags**, not
  a rules table: an option `provides` tags and `requires` tags; valid ⇔ every
  required tag is provided by the selection (+ structural "≥1 of backend/frontend").
- **`composer.py`** — `validate()` (tag engine), `build_context()` (per-axis +
  `backend_lang`/`has_db`/`spa`/`is_default_schema`/entity flags), `_render_module()`
  (renders `scaffolds/<src>`; path tokens `__backend__`/`__frontend__`/`__root__`;
  **files that render to whitespace are skipped** → cheap conditional files),
  `_build_manifests()` (per-language: requirements.txt / package.json / go.mod /
  Gemfile — dispatch on `backend_lang`; `side_mods` = database+auth+api fold deps in),
  `_apply_pkg_manager()` (rewrites npm cmds in README), `compose()` (fills axis
  defaults, validates, renders base+axes+addons, emits README + `stackgen.json`,
  injects custom files). **Layout:** the tree is rooted at `root_dir` (not the
  slug); `backend_dir`/`frontend_dir` come from `structure`, so Docker/README/build
  paths follow renames for free. `validate(require_component=False)` allows a
  files-only project. `slug` still names packages (package.json/go module).
- **`schema.py`** — user entities. `FIELD_TYPES` (per-language column maps:
  `sa/py/go/ddl/input`), `Field`/`Entity` (props: `class_name,var,camel,plural,table,
  route,mapped,pydantic,sa,go,ddl,prisma,django`; `Field.pascal` for struct ids),
  `normalize()`, `validate_schema()`, `render_flags()`. Empty schema → default `Item{name}`.
- **`structure.py`** — custom layout. `normalize_structure(raw, selection,
  default_root)` → `Structure(root, backend_dir, frontend_dir, files)`; `LAYOUTS`
  presets (`nested`/`monorepo`); `_safe_relpath()` blocks `..`/absolute paths. Files
  with a trailing `/` (or no content) become an empty folder via `.gitkeep`.
- **`preset.py`** — config `to_config/from_config/encode/decode` (base64url; mirrored
  by `public/js/preset.js`). Config carries `structure`; `from_config` returns a
  5-tuple `(name, selection, addons, schema, structure)`. `errors.py` — shared
  `InvalidSelection`.
- **`project_env.py`** — Jinja env for scaffolds: **delimiters are `[[ ]]` / `[% %]`
  / `[# #]`**, `trim_blocks`+`lstrip_blocks` on.

`app.py` (Flask): `GET /` renders the form (+`?c=` preset prefill). **There is no
`POST /generate`** — generation runs only through the **JSON API**, which the UI
calls too (one code path). API: `POST /api/generate` (lenient body —
`_parse_api_request` accepts a nested `stack` or flat axes + `addons`/`schema`/
`structure`, omitted axes default via `compose`), `GET /api/options` (discovery),
`GET /api/health`, `GET /api/openapi.json`. Cross-cutting (scoped to `/api/*`):
`_cors_headers` (open CORS), `_api_gate` (OPTIONS preflight + **env-gated**
`x-api-key`, enforced only when `API_KEY` is set), `HTTPException`/`Exception`
handlers → JSON errors, `MAX_CONTENT_LENGTH` 4 MB. Spec in `public/openapi.json`;
examples in `API.md`. UI: `templates/index.html`, `public/css/app.css`,
`public/js/{entities,structure,preset,form}.js` (load order matters: `form.js`
intercepts submit → builds config via `window.buildConfig` (preset.js, all 7 axes
+ `structure` from structure.js) → `fetch('/api/generate')` → downloads the blob;
form.js also gates options live using the same tags as the server).

`scaffolds/`: `backend/<id>/`, `frontend/<id>/`, `database/{sql,memory,drizzle}/`,
`addons/<id>/`, `base/`. Tests in `tests/` use **pairwise** coverage
(`tests/pairwise.py`) so the render matrix stays small as options grow.

## Catalog (7 axes, all tag-driven)
- **backend (15):** Python: flask, fastapi, litestar, starlette, django · Node:
  express, fastify, hono, koa, nestjs · Go: nethttp, gin, chi, echo · Ruby:
  sinatra · none
- **frontend (7):** vanilla, react, vue, svelte, preact, solid, lit · none
- **database:** none(in-memory) · Python (SQLAlchemy): sqlite/postgres · Node:
  drizzle-sqlite/postgres/mysql, mongo (Mongoose), prisma-sqlite/postgres —
  language-tagged + `data:shared`-gated
- **styling:** plain, bootstrap, tailwind · **auth:** none, jwt (stdlib HS256) ·
  **api:** rest, graphql (Strawberry; Flask/FastAPI only) · **pkg:** npm/pnpm/yarn/bun

Every backend ships schema-driven CRUD + JWT. Node backends use a **repo seam**
(`repo.list/create/get/update/remove`, async) so the data layer swaps without
touching route handlers — the database axis provides `repo.js`. **Django is the
exception:** it owns its ORM + SQLite, so it does *not* provide the `data:shared`
tag that every non-`none` database option requires → the database axis is forced
to `none` for it (validator + UI both gate on this). Django seeds via a
`post_migrate` signal in `app/apps.py`; run with `migrate --run-syncdb`.

## Conventions & gotchas (learned the hard way)
- **"It runs" is sacred.** Don't ship a scaffold you can't verify compiles/runs
  (Angular was cut for this reason — Analog/Vite build was silently broken).
- **Jinja delimiter adjacency:** a literal `[` next to `[[` or `[%` mis-lexes. Put a
  space: `fields: [ [% for ... %]`, `list[ [[ x ]] ]`, `Optional[ ... ]`.
- **trim_blocks gotcha:** never end a line on a `[% ... %]` whose value you need —
  the trailing newline is eaten. Compute a plain var instead (see `backend_build`).
- **Per-language verify:** `py_compile` (py), `node --check` (js), `go build`/`go vet`
  (go) — gate on `shutil.which`. Go: gofmt wants tabs (templates use spaces; `go
  build`/`vet` accept spaces — gofmt is style-only). Generated ruff config uses
  `select=["E","F"]` (import-sort "I" dropped — fragile with dynamic fields).
- **Adding an axis:** append to `AXES`, give it `OPTIONS`+`AXIS_LABELS`, add to
  `DEFAULTS`. `compose()` fills omitted axes from `axis_default()`; `preset.from_config`
  requires only `CORE_AXES`. Update test fixtures' `stack` dicts (test_preset CONFIG).
- **PowerShell:** `2>&1` on a native exe flips `$?` (Go prints "downloading" to
  stderr) — don't redirect; `$x:` is a drive-qualifier (use `${x}`); background
  `go mod tidy` output truncates mid-download → run `go build` directly after.
- After live tests: kill the server on port 8000 and delete the `build_*` temp dir.
