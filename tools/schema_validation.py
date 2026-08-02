"""Cached, install-location-independent JSON Schema validation."""

from __future__ import annotations

import functools
import pathlib
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

try:
    from tools.data_loading import load_json_bytes
except ModuleNotFoundError:
    from data_loading import load_json_bytes

SCHEMA_ROOT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "profiles"
    / "transactional-action"
    / "schema"
)
SCHEMA_BASE = "https://delegation-resilience.org/schemas/transactional-action/"


@functools.lru_cache(maxsize=1)
def _validators() -> dict[str, Draft202012Validator]:
    schemas: dict[str, dict[str, Any]] = {}
    registry = Registry()
    for path in sorted(SCHEMA_ROOT.glob("*.json")):
        schema = load_json_bytes(path.read_bytes(), source=f"schema {path.name}")
        schema["$id"] = SCHEMA_BASE + path.name
        schemas[path.name] = schema
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return {
        name: Draft202012Validator(
            schema, registry=registry, format_checker=FormatChecker()
        )
        for name, schema in schemas.items()
    }


def schema_errors(schema_name: str, value: Any) -> list[str]:
    validator = _validators()[schema_name]
    return [
        (".".join(str(item) for item in error.path) or "<root>") + f": {error.message}"
        for error in sorted(
            validator.iter_errors(value), key=lambda item: list(item.path)
        )
    ]
