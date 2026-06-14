# Tech-Stack App Generator

A small Flask web app: pick a tech stack and download a ready-to-run starter
project as a `.zip`. Generation is **fully deterministic** — projects are
assembled from authored templates, so there are no LLMs, no API costs, and the
output always runs.

## Run the generator

```bash
python -m venv .venv
.venv\Scripts\activate              # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt  # runtime deps + pytest
python app.py
```

Open <http://localhost:5000>, choose your stack, and click **Download .zip**.

## Deploy to Vercel

This app is Vercel-ready and runs as a single Python (Vercel Function):

- `app.py` exposes a `Flask` instance named `app` at the repo root, which Vercel
  auto-detects as the entrypoint — no `vercel.json` or routing config required.
- Runtime dependencies are in `requirements.txt` (Vercel installs these; `pytest`
  is kept out, in `requirements-dev.txt`).
- Static assets live in `public/**` so Vercel serves them from its CDN. Flask is
  pointed at `public/` too, so local dev serves the same `/css/...` and `/js/...`
  paths.
- Zips are built in memory (`BytesIO`), so the read-only serverless filesystem is
  a non-issue.

Deploy by connecting the Git repo in the Vercel dashboard, or:

```bash
npm i -g vercel
vercel          # preview deploy
vercel --prod   # production
vercel dev      # run the serverless setup locally
```

## What you can pick

| Axis      | Options                                            |
| --------- | -------------------------------------------------- |
| Backend   | Python: Flask, FastAPI, Litestar, Starlette · Node: Express, Fastify, Hono, Koa, NestJS · Go: net/http, Gin, Chi, Echo · Ruby: Sinatra · None |
| Frontend  | Vanilla JS, React, Vue, Svelte, Preact, SolidJS, Lit (Vite), None |
| Database  | None (in-memory) · Python: SQLite/PostgreSQL (SQLAlchemy) · Node: Drizzle + SQLite |
| Styling   | Plain CSS, Bootstrap (CDN), Tailwind (Play CDN)    |
| Auth      | None, JWT (stateless HS256: `/api/login` + `/api/me`) |
| API style | REST, GraphQL (Strawberry `/graphql`, Python + in-memory) |
| Package manager | npm, pnpm, yarn, bun (JS toolchain)          |

Compatibility between options is decided by **capability tags** (`lang:python`,
`framework:react`, `engine:postgres`, …): each option declares what it
`provides` and `requires`, so the catalogue can grow across languages without a
central rules table. The same tags drive the live browser gating and the server
validator.

With a backend **and** a frontend you get a `backend/` + `frontend/` layout;
otherwise the single component sits at the project root. Each zip includes a
`README.md` with run instructions and a `stackgen.json` recording the exact
configuration. Incompatible combinations (e.g. a database with no backend) are
blocked both in the browser and on the server from one shared rule set.

## Customize

Beyond the four axes, you can tailor the generated app deterministically — no
LLMs involved:

- **Data model.** Define your own entities and typed fields (string, text,
  integer, float, boolean, datetime) in the form. The generator emits SQLAlchemy
  models, full CRUD endpoints, and a list/create/delete UI per entity by looping
  templates over your schema. Leave it empty for a sample `Item`. *Custom
  entities require a backend (Flask/FastAPI persist via SQLAlchemy; Express uses
  an in-memory store).*
- **Add-ons.** Multi-select extras layered into the build: **Docker**
  (Dockerfiles + Compose, with a Postgres service when selected), **Tests**
  (pytest against the API), **CI** (GitHub Actions), **Lint** (Ruff / Prettier),
  **Env** (`.env.example`), and **MIT License**. Add-ons that don't fit the
  chosen stack are hidden in the UI and dropped server-side.
- **Presets.** *Save config* downloads the selection as `stackgen.json`,
  *Copy share link* encodes it into a `?c=…` URL, and *Import config* reloads a
  saved file. Every zip also contains its own `stackgen.json`, so a build is
  reproducible. For scripting, `POST /api/generate` takes a config JSON body and
  streams back the zip.

## How it works

```
app.py                 Flask UI: GET / (+?c= preset), POST /generate, POST /api/generate
generator/
  registry.py          Catalogue of options, add-ons + compatibility rules
  schema.py            Entity/field normalize, validate, type mapping
  composer.py          Validate -> render (schema + add-ons) -> merged file tree
  preset.py            Config serialize / encode / decode (mirrored in preset.js)
  project_env.py       Isolated Jinja env ([[ ]] delimiters) for scaffolds
  zipper.py            File tree -> in-memory zip
  errors.py            Shared InvalidSelection
scaffolds/             Source templates for the GENERATED apps (incl. addons/)
templates/, public/    The generator's own UI (public/ = CDN-served assets)
tests/                 Composer, schema, add-on, preset, and route tests
```

Each stack option and add-on is a self-contained *module* (a folder under
`scaffolds/` plus a registry entry). Add-on templates use the path tokens
`__backend__` / `__frontend__` / `__root__` to land files in the right place, and
files that render empty are skipped — so adding an option later means adding one
folder and one entry, no re-authoring of combinations.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The suite renders **every valid stack combination**, compiles the generated
Python, validates generated JSON, exercises custom-schema rendering, add-on
placement/manifest folding, and preset round-trips, and checks that invalid
combinations are rejected.
