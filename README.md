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
| Backend   | Flask, FastAPI, Express, None                      |
| Frontend  | Vanilla JS, React (Vite), Vue (Vite), None         |
| Database  | None, SQLite, PostgreSQL (Python backends only)    |
| Styling   | Plain CSS, Bootstrap (CDN), Tailwind (Play CDN)    |

Every generated project is a tiny "items" demo: the backend exposes a JSON API
(`/api/health`, `GET`/`POST /api/items`); the frontend lists items and adds new
ones, calling the backend when present or using mock data when not. With a
backend **and** a frontend you get a `backend/` + `frontend/` layout; otherwise
the single component sits at the project root. Each zip includes a `README.md`
with run instructions for the exact stack chosen.

Incompatible combinations (e.g. a database with no backend) are blocked both in
the browser and on the server from one shared rule set.

## How it works

```
app.py                 Flask UI: GET / (form) + POST /generate (zip)
generator/
  registry.py          Catalogue of options + compatibility rules
  composer.py          Validate selection -> render -> merged file tree
  project_env.py       Isolated Jinja env ([[ ]] delimiters) for scaffolds
  zipper.py            File tree -> in-memory zip
scaffolds/             Source templates for the GENERATED apps
templates/, static/    The generator's own UI
tests/                 Composer + route tests
```

Each stack option is a self-contained *module* (a folder under `scaffolds/` plus
a registry entry). Adding an option later means adding one folder and one entry —
no need to re-author every combination.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The suite renders **every valid stack combination**, compiles the generated
Python, validates generated JSON, and checks that invalid combinations are
rejected.
