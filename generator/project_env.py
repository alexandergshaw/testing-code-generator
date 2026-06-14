"""Isolated Jinja2 environment for rendering *generated project* templates.

This is deliberately separate from Flask's own Jinja environment (which renders
the generator UI with the usual ``{{ }}`` / ``{% %}`` delimiters). Scaffold
templates under ``scaffolds/`` use ``[[ ]]`` and ``[% %]`` so that template
syntax belonging to the *generated* app (e.g. a Flask app's own ``{{ }}``
templates, or a Vue/JSX expression) passes through untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

SCAFFOLDS_DIR = Path(__file__).resolve().parent.parent / "scaffolds"


def build_project_env(scaffolds_dir: Path = SCAFFOLDS_DIR) -> Environment:
    """Return a Jinja2 ``Environment`` configured for scaffold rendering."""
    env = Environment(
        loader=FileSystemLoader(str(scaffolds_dir)),
        variable_start_string="[[",
        variable_end_string="]]",
        block_start_string="[%",
        block_end_string="%]",
        comment_start_string="[#",
        comment_end_string="#]",
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
        autoescape=False,
    )
    env.filters["tojson_pretty"] = lambda v: json.dumps(v, indent=2)
    return env


def render_string(env: Environment, source: str, context: dict) -> str:
    """Render a raw template string with the project environment."""
    return env.from_string(source).render(**context)
