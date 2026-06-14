# HTTP API

Deterministic project generator over HTTP: POST a stack config, get back a
ready-to-run project as a `.zip`. No LLMs — Jinja2 composition, and every option
combination is generated to actually run.

Base URL is your deployment origin (e.g. `https://<project>.vercel.app`). The
OpenAPI spec is served at [`/api/openapi.json`](public/openapi.json).

## Endpoints

| Method & path        | Purpose                                                        |
| -------------------- | ------------------------------------------------------------- |
| `POST /api/generate` | Generate a project zip from a stack config.                   |
| `GET  /api/options`  | Discovery catalog: axes, valid options, add-ons, field types, defaults, compatibility tags. |
| `GET  /api/health`   | Liveness check.                                               |
| `GET  /api/openapi.json` | The OpenAPI 3.1 spec.                                     |

CORS is open (`Access-Control-Allow-Origin: *`) on all `/api/*` routes, so
browser apps can call it directly.

## Authentication

Optional and **env-gated**. If the deployment sets an `API_KEY` environment
variable, every `POST /api/generate` must send a matching `x-api-key` header
(else `401`). If `API_KEY` is unset, the API is open. `health` and `options`
are never gated.

## `POST /api/generate`

Request body (JSON). Axes may be nested under `stack` (the canonical preset
config the UI exports) **or** placed at the top level. Any omitted axis falls
back to its default, so the smallest valid body is `{}`.

| Field          | Type     | Default    | Notes                                            |
| -------------- | -------- | ---------- | ------------------------------------------------ |
| `project_name` | string   | `my-app`   | Used for the zip name and the project root dir.  |
| `stack`        | object   | all defaults | `backend, frontend, database, styling, auth, api, pkg`. |
| `addons`       | string[] | `[]`       | e.g. `["docker", "tests"]`.                       |
| `schema`       | object[] | one demo `Item` | Entities (see below). Empty → default demo.  |

An **entity**: `{ "name": "Product", "plural": "products", "fields": [ ... ] }`
(`plural` optional). A **field**: `{ "name": "title", "type": "string",
"required": true }` — types: `string, text, integer, float, boolean, datetime`.

Call `GET /api/options` for the current valid option ids and which combinations
are compatible (`tags`).

**Responses:** `200` → `application/zip` (with `Content-Disposition`);
`400` → `{"error": ...}` (malformed body or incompatible stack);
`401` → `{"error": ...}` (API key required but missing/invalid).

### curl

```bash
curl -X POST https://<project>.vercel.app/api/generate \
  -H 'content-type: application/json' \
  -H 'x-api-key: YOUR_KEY' \
  -d '{
        "project_name": "shop",
        "stack": { "backend": "fastapi", "frontend": "react", "database": "sqlite", "auth": "jwt" },
        "addons": ["docker"],
        "schema": [
          { "name": "Product", "fields": [
            { "name": "title", "type": "string", "required": true },
            { "name": "price", "type": "float" }
          ] }
        ]
      }' \
  -o shop.zip
```

### JavaScript (fetch)

```js
const res = await fetch("https://<project>.vercel.app/api/generate", {
  method: "POST",
  headers: { "content-type": "application/json", "x-api-key": "YOUR_KEY" },
  body: JSON.stringify({
    project_name: "shop",
    stack: { backend: "express", frontend: "vue", database: "drizzle-sqlite" },
  }),
});
if (!res.ok) throw new Error((await res.json()).error);
const blob = await res.blob(); // application/zip
```

### Python (requests)

```python
import requests

res = requests.post(
    "https://<project>.vercel.app/api/generate",
    headers={"x-api-key": "YOUR_KEY"},
    json={"project_name": "shop", "stack": {"backend": "django"}},
)
res.raise_for_status()
open("shop.zip", "wb").write(res.content)
```

## Deploying to Vercel

The repo ships [`vercel.json`](vercel.json) which builds `app.py` with
`@vercel/python` and routes all paths to it. The `includeFiles` list bundles the
runtime data dirs (`scaffolds/`, `templates/`, `public/`, `generator/`) — without
it, generation 500s in production with `FileNotFoundError`.

```bash
vercel            # preview deploy
vercel --prod     # production
```

Set the Python version to 3.12 in the Vercel project settings, and (optionally)
add an `API_KEY` environment variable to lock the generate endpoint.
