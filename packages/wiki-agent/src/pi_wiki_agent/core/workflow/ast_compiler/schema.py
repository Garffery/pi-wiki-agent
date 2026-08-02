"""
YAML schema shorthand → JSON Schema compiler.

Converts compact YAML type notation into standard JSON Schema dicts.
"""
from __future__ import annotations

from typing import Any

_TYPE_MAP = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}


def compile_schema(shorthand: Any) -> dict | None:
    """Convert YAML schema shorthand to JSON Schema dict.

    Shorthand forms::

        field: str          →  {"type": "string"}
        field: str?         →  {"type": "string"} (key ending in ``?`` → optional)
        field: int          →  {"type": "integer"}
        field: float        →  {"type": "number"}
        field: bool         →  {"type": "boolean"}
        field: [str]        →  {"type": "array", "items": {"type": "string"}}
        field: {enum: [a]}  →  {"type": "string", "enum": ["a", "b"]}
        field:              →  nested object with properties
          sub_a: str
          sub_b?: int

    Returns ``None`` when ``shorthand`` is ``None``.
    """
    if shorthand is None:
        return None

    # str / str? / int / float / bool
    if isinstance(shorthand, str):
        optional = shorthand.endswith("?")
        base = shorthand[:-1] if optional else shorthand
        if base in _TYPE_MAP:
            return {"type": _TYPE_MAP[base]}
        return {"type": base}

    # [str] — array of single type
    if isinstance(shorthand, list):
        if len(shorthand) == 1 and isinstance(shorthand[0], str) and shorthand[0] in _TYPE_MAP:
            return {"type": "array", "items": {"type": _TYPE_MAP[shorthand[0]]}}
        if shorthand:
            return {"type": "array", "items": compile_schema(shorthand[0]) or {}}
        return {"type": "array", "items": {}}

    # {enum: [...]}
    if isinstance(shorthand, dict) and "enum" in shorthand and len(shorthand) == 1:
        return {"type": "string", "enum": shorthand["enum"]}

    # Nested object: {field1: str, field2: int, optional?: str, ...}
    if isinstance(shorthand, dict):
        required: list[str] = []
        properties: dict[str, dict] = {}
        for key, val in shorthand.items():
            if isinstance(key, str) and key.endswith("?"):
                real_key = key[:-1]
                properties[real_key] = compile_schema(val) or {}
            else:
                required.append(key)
                properties[key] = compile_schema(val) or {}
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    return None
