"""User-defined data schema: normalization, validation, and type mapping.

A *schema* is a list of entities the user wants their app to manage. Each entity
has a name and one or more typed fields. The composer feeds the normalized
entities into the scaffold templates, which loop over them to emit models, CRUD
endpoints, and UI.

When the user supplies no schema, we fall back to ``DEFAULT_SCHEMA`` — a single
``Item { name: string }`` entity — so the generated app is exactly the original
"items" demo. Every template therefore only needs the looping code path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import InvalidSelection

# Logical field type -> concrete forms for each target language.
#   sa    : SQLAlchemy column type
#   py    : Python / pydantic annotation
#   ts    : JSON/JS value kind (informational)
#   input : HTML input type for the generated form
#   ddl   : SQLite column type for raw CREATE TABLE (Drizzle / better-sqlite3)
FIELD_TYPES = {
    "string":   {"sa": "String(255)", "py": "str",      "go": "string",  "ts": "string",  "input": "text",          "ddl": "TEXT"},
    "text":     {"sa": "Text",        "py": "str",      "go": "string",  "ts": "string",  "input": "textarea",      "ddl": "TEXT"},
    "integer":  {"sa": "Integer",     "py": "int",      "go": "int",     "ts": "number",  "input": "number",        "ddl": "INTEGER"},
    "float":    {"sa": "Float",       "py": "float",    "go": "float64", "ts": "number",  "input": "number",        "ddl": "REAL"},
    "boolean":  {"sa": "Boolean",     "py": "bool",     "go": "bool",    "ts": "boolean", "input": "checkbox",      "ddl": "INTEGER"},
    "datetime": {"sa": "DateTime",    "py": "datetime", "go": "string",  "ts": "string",  "input": "datetime-local", "ddl": "TEXT"},
}

DEFAULT_SCHEMA = [
    {"name": "Item", "fields": [{"name": "name", "type": "string", "required": True}]}
]

_ENTITY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PLURAL_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _snake(name: str) -> str:
    """``ProductLine`` -> ``product_line``."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    required: bool = False

    @property
    def sa(self) -> str:
        return FIELD_TYPES[self.type]["sa"]

    @property
    def sa_base(self) -> str:
        """SQLAlchemy type name without args, e.g. ``String`` from ``String(255)``."""
        return self.sa.split("(")[0]

    @property
    def py(self) -> str:
        return FIELD_TYPES[self.type]["py"]

    @property
    def input(self) -> str:
        return FIELD_TYPES[self.type]["input"]

    @property
    def go(self) -> str:
        return FIELD_TYPES[self.type]["go"]

    @property
    def ddl(self) -> str:
        return FIELD_TYPES[self.type]["ddl"]

    @property
    def prisma(self) -> str:
        """Prisma model field type, with ``?`` for optional fields."""
        base = {"integer": "Int", "float": "Float", "boolean": "Boolean",
                "datetime": "DateTime"}.get(self.type, "String")
        return base if self.required else f"{base}?"

    @property
    def django(self) -> str:
        """Django ORM model field, e.g. ``models.FloatField(null=True, blank=True)``."""
        kind, args = {
            "string": ("CharField", ["max_length=255"]),
            "text": ("TextField", []),
            "integer": ("IntegerField", []),
            "float": ("FloatField", []),
            "boolean": ("BooleanField", []),
            "datetime": ("DateTimeField", []),
        }[self.type]
        if not self.required:
            args += ["null=True", "blank=True"]
        return f"models.{kind}({', '.join(args)})"

    @property
    def pascal(self) -> str:
        """snake_case field name -> exported Go/struct identifier (``in_stock`` -> ``InStock``)."""
        return "".join(part[:1].upper() + part[1:] for part in self.name.split("_"))

    @property
    def mapped(self) -> str:
        """SQLAlchemy 2.0 ``Mapped[...]`` annotation."""
        return f"Mapped[{self.py}]"

    @property
    def pydantic(self) -> str:
        """Pydantic field annotation incl. default for optional fields."""
        return self.py if self.required else f"Optional[{self.py}] = None"


@dataclass(frozen=True)
class Entity:
    name: str
    fields: tuple[Field, ...]
    plural: str

    @property
    def class_name(self) -> str:
        return self.name[:1].upper() + self.name[1:]

    @property
    def var(self) -> str:
        return _snake(self.name)

    @property
    def camel(self) -> str:
        """``ProductLine`` -> ``productLine`` (e.g. a Prisma client accessor)."""
        return self.class_name[:1].lower() + self.class_name[1:]

    @property
    def table(self) -> str:
        return self.plural

    @property
    def route(self) -> str:
        return f"/api/{self.plural}"


def normalize(raw) -> list[Entity]:
    """Turn raw schema dicts (or nothing) into ``Entity`` objects.

    Assumes ``validate_schema`` has already passed; falls back to the default
    single-entity schema when ``raw`` is empty.
    """
    rows = list(raw) if raw else DEFAULT_SCHEMA
    entities = []
    for ent in rows:
        name = ent["name"].strip()
        fields = tuple(
            Field(
                name=f["name"].strip(),
                type=f["type"],
                required=bool(f.get("required", False)),
            )
            for f in ent["fields"]
        )
        plural = (ent.get("plural") or "").strip() or f"{_snake(name)}s"
        entities.append(Entity(name=name, fields=fields, plural=plural))
    return entities


def is_default(raw) -> bool:
    return not raw


def render_flags(entities) -> dict:
    """Schema-derived context that keeps generated imports precise (lint-clean).

    Returns the exact SQLAlchemy column types used (``id`` always needs
    ``Integer``) plus whether any field needs ``datetime`` / ``Optional``.
    """
    sa_types = {"Integer"}
    uses_datetime = False
    uses_optional = False
    for entity in entities:
        for fld in entity.fields:
            sa_types.add(fld.sa_base)
            if fld.type == "datetime":
                uses_datetime = True
            if not fld.required:
                uses_optional = True
    return {
        "sa_types_used": sorted(sa_types),
        "uses_datetime": uses_datetime,
        "uses_optional": uses_optional,
    }


def validate_schema(raw, selection: dict) -> None:
    """Validate a user-supplied schema; raise ``InvalidSelection`` on problems."""
    if not raw:
        return  # default schema is always valid

    if selection.get("backend") == "none":
        raise InvalidSelection("Custom data entities need a backend.")

    seen_entities = set()
    for ent in raw:
        name = (ent.get("name") or "").strip()
        if not _ENTITY_RE.match(name):
            raise InvalidSelection(
                f"Invalid entity name {name!r}: use a letter followed by "
                "letters or digits (e.g. Product)."
            )
        key = name.lower()
        if key in seen_entities:
            raise InvalidSelection(f"Duplicate entity name: {name!r}.")
        seen_entities.add(key)

        fields = ent.get("fields") or []
        if not fields:
            raise InvalidSelection(f"Entity {name!r} needs at least one field.")

        plural = (ent.get("plural") or "").strip()
        if plural and not _PLURAL_RE.match(plural):
            raise InvalidSelection(
                f"Invalid plural {plural!r} for {name!r}: lowercase letters, "
                "digits, and underscores only."
            )

        seen_fields = set()
        for fld in fields:
            fname = (fld.get("name") or "").strip()
            if not _FIELD_RE.match(fname):
                raise InvalidSelection(
                    f"Invalid field name {fname!r} on {name!r}: lowercase "
                    "letters, digits, and underscores only."
                )
            if fname == "id":
                raise InvalidSelection(
                    f"Field {fname!r} on {name!r} is reserved (id is added "
                    "automatically)."
                )
            if fname in seen_fields:
                raise InvalidSelection(
                    f"Duplicate field {fname!r} on entity {name!r}."
                )
            seen_fields.add(fname)

            if fld.get("type") not in FIELD_TYPES:
                raise InvalidSelection(
                    f"Unknown type {fld.get('type')!r} for {name}.{fname}; "
                    f"allowed: {', '.join(FIELD_TYPES)}."
                )
