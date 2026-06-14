"""Tech-Stack App Generator — Flask UI.

Renders a stack-picker form and streams back a ready-to-run project as a zip.
"""
from __future__ import annotations

import json

from flask import Flask, abort, render_template, request, send_file

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

# Static assets live in public/ so Vercel serves them from its CDN. Pointing
# Flask's static folder there (mounted at the root URL) keeps local `python
# app.py` serving the same /css/... and /js/... paths.
app = Flask(__name__, static_folder="public", static_url_path="")

DEFAULTS = {"backend": "flask", "frontend": "vanilla", "database": "none",
            "styling": "plain", "auth": "none", "api": "rest", "pkg": "npm"}


def _render(selected, project_name="my-app", error=None, addons=(), schema=(), status=200):
    html = render_template(
        "index.html",
        axes=AXES,
        axis_labels=AXIS_LABELS,
        options=OPTIONS,
        addons=ADDONS,
        selected=selected,
        selected_addons=list(addons),
        schema_json=json.dumps(list(schema)),
        project_name=project_name,
        error=error,
        module_tags_json=json.dumps(module_tags()),
        addons_meta_json=json.dumps(ADDONS_META),
        field_types_json=json.dumps(list(FIELD_TYPES)),
    )
    return (html, status) if status != 200 else html


def _zip_response(tree, project_name):
    return send_file(
        to_zip(tree),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{slugify(project_name)}.zip",
    )


@app.get("/")
def index():
    """Render the form, optionally pre-filled from a shared ``?c=`` preset."""
    token = request.args.get("c")
    if token:
        try:
            name, selection, addons, schema = preset.from_config(preset.decode(token))
            return _render(selection, name, addons=addons, schema=schema)
        except InvalidSelection:
            pass  # fall through to defaults on a bad link
    return _render(DEFAULTS)


@app.post("/generate")
def generate():
    # Only axes the form actually sent; the composer fills any omitted axis with
    # its default (so new axes don't break partial posts).
    selection = {axis: request.form[axis] for axis in AXES if request.form.get(axis)}
    project_name = request.form.get("project_name", "").strip()
    addons = request.form.getlist("addons")
    schema = _parse_schema(request.form.get("schema", ""))
    try:
        tree = compose(selection, project_name, schema=schema, addons=addons)
    except InvalidSelection as exc:
        merged = {**DEFAULTS, **{k: v for k, v in selection.items() if v}}
        return _render(merged, project_name or "my-app", str(exc),
                       addons=addons, schema=schema, status=400)
    return _zip_response(tree, project_name)


@app.post("/api/generate")
def api_generate():
    """Generate from a JSON preset config (for scripting/CLI use)."""
    config = request.get_json(silent=True)
    if config is None:
        abort(400, "Expected a JSON config body.")
    try:
        name, selection, addons, schema = preset.from_config(config)
        tree = compose(selection, name, schema=schema, addons=addons)
    except InvalidSelection as exc:
        abort(400, str(exc))
    return _zip_response(tree, name)


def _parse_schema(raw: str):
    if not raw.strip():
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


if __name__ == "__main__":
    app.run(port=5000, debug=True)
