"""Tech-Stack App Generator — Flask UI + JSON HTTP API.

`GET /` renders a stack-picker form and `POST /generate` streams back a project
zip. The `/api/*` surface is the machine-callable side (designed for other apps
and Vercel deployment): JSON in, a project `.zip` out, with JSON errors, CORS, an
optional env-gated API key, and discovery/health endpoints.
"""
from __future__ import annotations

import json
import os

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException

from generator import preset
from generator.composer import InvalidSelection, compose, slugify
from generator.registry import ADDONS, AXES, AXIS_LABELS, OPTIONS, module_tags
from generator.schema import FIELD_TYPES
from generator.zipper import to_zip

# Metadata the browser needs to gate add-ons against the chosen stack.
ADDONS_META = [
    {
        "id": m.id,
        "requires_backend": list(m.context.get("requires_backend", ())),
        "requires_frontend": list(m.context.get("requires_frontend", ())),
    }
    for m in ADDONS
]

# Static assets live in public/ and are served from Vercel's CDN (vercel.json: the
# @vercel/static build + the "filesystem" route). Serving them at /public/* — which
# matches their on-disk path — means the exact same URLs work locally (Flask) and on
# Vercel. Routing them through the Python function instead leaves the page unstyled.
app = Flask(__name__, static_folder="public", static_url_path="/public")

# Cap the request body so a bad caller can't stream huge payloads at the function
# (over-size bodies raise 413 -> JSON error). 4 MB leaves room for injected custom
# files while staying under Vercel's ~4.5 MB response limit.
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024

DEFAULTS = {"backend": "flask", "frontend": "vanilla", "database": "none",
            "styling": "plain", "auth": "none", "api": "rest", "pkg": "npm"}


# --------------------------------------------------------------------------- #
# API cross-cutting concerns (CORS, env-gated key, JSON errors)
# --------------------------------------------------------------------------- #
def _json_error(status: int, message: str):
    return jsonify(error=message), status


@app.before_request
def _api_gate():
    """Short-circuit CORS preflight and enforce the optional API key on /api/*."""
    if not request.path.startswith("/api/"):
        return None
    if request.method == "OPTIONS":
        return ("", 204)  # CORS preflight; headers added in _cors_headers
    # The key is enforced only when API_KEY is configured (so the app can deploy
    # open and be locked down later by setting the env var — no code change).
    required = os.environ.get("API_KEY")
    if required and request.path == "/api/generate":
        if request.headers.get("x-api-key") != required:
            return _json_error(401, "Invalid or missing API key.")
    return None


@app.after_request
def _cors_headers(response):
    """Allow any origin to call the JSON API (no credentials, public generator)."""
    if request.path.startswith("/api/"):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, x-api-key"
        response.headers["Access-Control-Expose-Headers"] = "Content-Disposition"
        response.headers["Access-Control-Max-Age"] = "86400"
    return response


@app.errorhandler(HTTPException)
def _on_http_error(err: HTTPException):
    """JSON errors for the API; default HTML pages for the UI."""
    if request.path.startswith("/api/"):
        return jsonify(error=err.description), err.code
    return err.get_response()


@app.errorhandler(Exception)
def _on_uncaught(err: Exception):
    if isinstance(err, HTTPException):
        return _on_http_error(err)
    app.logger.exception("Unhandled error")
    if request.path.startswith("/api/"):
        return _json_error(500, "Internal server error.")
    raise err


# --------------------------------------------------------------------------- #
# HTML UI
# --------------------------------------------------------------------------- #
def _render(selected, project_name="my-app", addons=(), schema=(), structure=None):
    return render_template(
        "index.html",
        axes=AXES,
        axis_labels=AXIS_LABELS,
        options=OPTIONS,
        addons=ADDONS,
        selected=selected,
        selected_addons=list(addons),
        schema_json=json.dumps(list(schema)),
        structure_json=json.dumps(structure or {}),
        project_name=project_name,
        module_tags_json=json.dumps(module_tags()),
        addons_meta_json=json.dumps(ADDONS_META),
        field_types_json=json.dumps(list(FIELD_TYPES)),
    )


def _zip_response(tree, project_name):
    return send_file(
        to_zip(tree),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{slugify(project_name)}.zip",
    )


@app.get("/")
def index():
    """Render the form, optionally pre-filled from a shared ``?c=`` preset.

    Generation itself goes through the JSON API (``POST /api/generate``) — the
    browser builds the config and downloads the zip — so there is one code path.
    """
    token = request.args.get("c")
    if token:
        try:
            name, selection, addons, schema, structure = preset.from_config(
                preset.decode(token)
            )
            return _render(selection, name, addons=addons, schema=schema,
                           structure=structure)
        except InvalidSelection:
            pass  # fall through to defaults on a bad link
    return _render(DEFAULTS)


# --------------------------------------------------------------------------- #
# JSON HTTP API
# --------------------------------------------------------------------------- #
def _parse_api_request(body):
    """Lenient request parsing for external callers.

    Accepts either the canonical preset config (a nested ``stack`` object, as the
    UI's "export config" produces) or a flat body where the axis keys sit at the
    top level. Any omitted axis is filled by ``compose`` from ``axis_default``, so
    the smallest valid body is ``{}`` (all defaults).
    """
    if not isinstance(body, dict):
        raise InvalidSelection("Request body must be a JSON object.")
    stack = body.get("stack", body)
    if not isinstance(stack, dict):
        raise InvalidSelection("'stack' must be a JSON object.")
    selection = {axis: stack[axis] for axis in AXES if axis in stack}
    addons = body.get("addons", [])
    schema = body.get("schema", [])
    structure = body.get("structure", {})
    if not isinstance(addons, list) or not isinstance(schema, list):
        raise InvalidSelection("'addons' and 'schema' must be JSON arrays.")
    if not isinstance(structure, dict):
        raise InvalidSelection("'structure' must be a JSON object.")
    return (body.get("project_name") or "my-app"), selection, addons, schema, structure


@app.post("/api/generate")
def api_generate():
    """Generate a project zip from a JSON stack config (for scripting/other apps)."""
    body = request.get_json(silent=True)
    if body is None:
        return _json_error(
            400, "Expected a JSON object body (Content-Type: application/json)."
        )
    try:
        name, selection, addons, schema, structure = _parse_api_request(body)
        tree = compose(selection, name, schema=schema, addons=addons, structure=structure)
    except InvalidSelection as exc:
        return _json_error(400, str(exc))
    return _zip_response(tree, name)


@app.get("/api/health")
def api_health():
    return jsonify(status="ok", version=preset.CONFIG_VERSION)


@app.get("/api/options")
def api_options():
    """Discovery catalog so callers can build valid requests programmatically."""
    return jsonify(
        version=preset.CONFIG_VERSION,
        axes=list(AXES),
        axis_labels=AXIS_LABELS,
        defaults=DEFAULTS,
        options={
            axis: [
                {"id": m.id, "label": m.label, "summary": m.summary}
                for m in OPTIONS[axis]
            ]
            for axis in AXES
        },
        addons=[
            {
                "id": m.id,
                "label": m.label,
                "summary": m.summary,
                "requires_backend": list(m.context.get("requires_backend", ())),
                "requires_frontend": list(m.context.get("requires_frontend", ())),
            }
            for m in ADDONS
        ],
        field_types=list(FIELD_TYPES),
        tags=module_tags(),
    )


@app.get("/api/openapi.json")
def api_openapi():
    return app.send_static_file("openapi.json")


if __name__ == "__main__":
    app.run(port=5000, debug=True)
