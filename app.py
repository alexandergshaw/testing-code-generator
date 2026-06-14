"""Tech-Stack App Generator — Flask UI.

Renders a stack-picker form and streams back a ready-to-run project as a zip.
"""
from __future__ import annotations

import json

from flask import Flask, render_template, request, send_file

from generator.composer import InvalidSelection, compose, slugify
from generator.registry import AXES, AXIS_LABELS, CONSTRAINTS, OPTIONS
from generator.zipper import to_zip

# Static assets live in public/ so Vercel serves them from its CDN. Pointing
# Flask's static folder there (mounted at the root URL) keeps local `python
# app.py` serving the same /css/... and /js/... paths.
app = Flask(__name__, static_folder="public", static_url_path="")

DEFAULTS = {"backend": "flask", "frontend": "vanilla",
            "database": "none", "styling": "plain"}


def _render(selected: dict, project_name: str = "my-app", error: str | None = None):
    return render_template(
        "index.html",
        axes=AXES,
        axis_labels=AXIS_LABELS,
        options=OPTIONS,
        selected=selected,
        project_name=project_name,
        error=error,
        constraints_json=json.dumps(CONSTRAINTS),
    )


@app.get("/")
def index():
    return _render(DEFAULTS)


@app.post("/generate")
def generate():
    selection = {axis: request.form.get(axis, "") for axis in AXES}
    project_name = request.form.get("project_name", "").strip()
    try:
        tree = compose(selection, project_name)
    except InvalidSelection as exc:
        merged = {**DEFAULTS, **{k: v for k, v in selection.items() if v}}
        return _render(merged, project_name or "my-app", str(exc)), 400

    buf = to_zip(tree)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{slugify(project_name)}.zip",
    )


if __name__ == "__main__":
    app.run(port=5000, debug=True)
