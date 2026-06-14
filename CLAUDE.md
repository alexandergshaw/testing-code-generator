# CLAUDE.md — project guide

Deterministic **tech-stack app generator**: a Flask UI lets a user pick a stack
(across 7 axes), define data entities, and download a ready-to-run app as a zip.
**No LLMs** — everything is Jinja2 template composition. Core promise: **every
generated combo actually runs.** Deployed on Vercel (single `app` in `app.py`,
assets in `public/`, all generation in-memory).

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
  defaults, validates, renders base+axes+addons, emits README + `stackgen.json`).
- **`schema.py`** — user entities. `FIELD_TYPES` (per-language column maps:
  `sa/py/go/ddl/input`), `Field`/`Entity` (props: `class_name,var,plural,table,route,
  pascal,mapped,pydantic,sa,go,ddl`), `normalize()`, `validate_schema()`,
  `render_flags()`. Empty schema → default single `Item{name}`.
- **`preset.py`** — config `to_config/from_config/encode/decode` (base64url; mirrored
  by `public/js/preset.js`). `errors.py` — shared `InvalidSelection`.
- **`project_env.py`** — Jinja env for scaffolds: **delimiters are `[[ ]]` / `[% %]`
  / `[# #]`**, `trim_blocks`+`lstrip_blocks` on.

`app.py` (Flask): `GET /` (+`?c=` preset prefill), `POST /generate`, `POST
/api/generate` (JSON→zip), `DEFAULTS`, `ADDONS_META`. UI: `templates/index.html`,
`public/css/app.css`, `public/js/{form,entities,preset}.js` (form.js gates options
live using the same tags as the server).

`scaffolds/`: `backend/<id>/`, `frontend/<id>/`, `database/{sql,memory,drizzle}/`,
`addons/<id>/`, `base/`. Tests in `tests/` use **pairwise** coverage
(`tests/pairwise.py`) so the render matrix stays small as options grow.

## Catalog (7 axes, all tag-driven)
- **backend (14):** Python: flask, fastapi, litestar, starlette · Node: express,
  fastify, hono, koa, nestjs · Go: nethttp, gin, chi, echo · Ruby: sinatra · none
- **frontend (7):** vanilla, react, vue, svelte, preact, solid, lit · none
- **database:** none(in-memory) · sqlite/postgres (SQLAlchemy, Python) ·
  drizzle-sqlite (Node) — language-tagged
- **styling:** plain, bootstrap, tailwind · **auth:** none, jwt (stdlib HS256) ·
  **api:** rest, graphql (Strawberry; Flask/FastAPI only) · **pkg:** npm/pnpm/yarn/bun

Every backend ships schema-driven CRUD + JWT. Node backends use a **repo seam**
(`repo.list/create/get/update/remove`, async) so the data layer (in-memory vs
Drizzle) swaps without touching route handlers — the database axis provides `repo.js`.

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
