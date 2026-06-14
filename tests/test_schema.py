"""Tests for schema normalization and validation."""
import pytest

from generator.errors import InvalidSelection
from generator.schema import (
    DEFAULT_SCHEMA,
    FIELD_TYPES,
    is_default,
    normalize,
    validate_schema,
)

PY = {"backend": "flask", "frontend": "none", "database": "sqlite", "styling": "plain"}


def test_empty_schema_falls_back_to_default():
    assert is_default([]) is True
    entities = normalize([])
    assert [e.name for e in entities] == ["Item"]
    assert entities[0].plural == "items"
    assert entities[0].fields[0].name == "name"


def test_normalize_computes_names_and_types():
    raw = [
        {
            "name": "ProductLine",
            "fields": [
                {"name": "title", "type": "string", "required": True},
                {"name": "price", "type": "float"},
            ],
        }
    ]
    (ent,) = normalize(raw)
    assert ent.class_name == "ProductLine"
    assert ent.var == "product_line"
    assert ent.plural == "product_lines"
    assert ent.route == "/api/product_lines"
    assert ent.fields[0].sa == FIELD_TYPES["string"]["sa"]
    assert ent.fields[1].py == "float"
    assert ent.fields[1].input == "number"


def test_explicit_plural_is_respected():
    (ent,) = normalize([{"name": "Person", "plural": "people",
                         "fields": [{"name": "name", "type": "string"}]}])
    assert ent.plural == "people"
    assert ent.route == "/api/people"


def test_custom_schema_requires_python_backend():
    schema = [{"name": "Product", "fields": [{"name": "name", "type": "string"}]}]
    with pytest.raises(InvalidSelection):
        validate_schema(schema, {**PY, "backend": "express"})
    with pytest.raises(InvalidSelection):
        validate_schema(schema, {**PY, "backend": "none"})
    validate_schema(schema, PY)  # flask is fine


@pytest.mark.parametrize(
    "schema",
    [
        [{"name": "1Bad", "fields": [{"name": "x", "type": "string"}]}],
        [{"name": "Good", "fields": []}],
        [{"name": "Good", "fields": [{"name": "Bad-Name", "type": "string"}]}],
        [{"name": "Good", "fields": [{"name": "id", "type": "integer"}]}],
        [{"name": "Good", "fields": [{"name": "x", "type": "nope"}]}],
        [{"name": "Good", "fields": [{"name": "x", "type": "string"},
                                     {"name": "x", "type": "integer"}]}],
        [{"name": "Dup", "fields": [{"name": "x", "type": "string"}]},
         {"name": "dup", "fields": [{"name": "y", "type": "string"}]}],
    ],
)
def test_invalid_schemas_rejected(schema):
    with pytest.raises(InvalidSelection):
        validate_schema(schema, PY)


def test_default_schema_constant_is_valid_shape():
    validate_schema(DEFAULT_SCHEMA, PY)
    assert normalize(DEFAULT_SCHEMA)[0].class_name == "Item"
