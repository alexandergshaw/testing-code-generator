"""Preset configs: serialize a full selection so it can be saved, shared, and
re-imported. The JS side (``public/js/preset.js``) mirrors ``encode``/``decode``.
"""

from __future__ import annotations

import base64
import json

from .errors import InvalidSelection
from .registry import AXES

CONFIG_VERSION = 1


def to_config(project_name: str, selection: dict, addons, schema) -> dict:
    """Build the canonical config dict for a generation request."""
    return {
        "version": CONFIG_VERSION,
        "project_name": project_name,
        "stack": {axis: selection[axis] for axis in AXES},
        "addons": sorted(dict.fromkeys(addons)),
        "schema": list(schema),
    }


def from_config(config: dict):
    """Validate a config dict and return ``(project_name, selection, addons,
    schema)``. Raises ``InvalidSelection`` on a malformed config."""
    if not isinstance(config, dict):
        raise InvalidSelection("Config must be a JSON object.")
    if config.get("version") != CONFIG_VERSION:
        raise InvalidSelection(
            f"Unsupported config version: {config.get('version')!r}."
        )
    stack = config.get("stack")
    if not isinstance(stack, dict) or any(axis not in stack for axis in AXES):
        raise InvalidSelection("Config 'stack' must include all four axes.")

    selection = {axis: stack[axis] for axis in AXES}
    addons = config.get("addons", [])
    schema = config.get("schema", [])
    if not isinstance(addons, list) or not isinstance(schema, list):
        raise InvalidSelection("Config 'addons' and 'schema' must be lists.")
    return config.get("project_name", "my-app"), selection, addons, schema


def encode(config: dict) -> str:
    """Compact, URL-safe base64 token for a shareable link."""
    raw = json.dumps(config, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode(token: str) -> dict:
    """Inverse of :func:`encode`. Raises ``InvalidSelection`` on bad input."""
    try:
        padding = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token + padding)
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise InvalidSelection("Could not decode shared config link.") from exc
