"""Strict loading and canonical serialization for assurance artifacts."""

from __future__ import annotations

import json
import pathlib
from typing import Any

import rfc8785
import yaml


class DuplicateKeyError(ValueError):
    """Raised when an object contains a duplicate key."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise DuplicateKeyError(f"duplicate object key: {key!r}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _reject_non_json(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_non_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} contains a non-string object key")
            _reject_non_json(item, f"{path}.{key}")
        return
    raise ValueError(f"{path} contains a non-JSON value: {type(value).__name__}")


def load_data_bytes(content: bytes, *, source: str = "artifact") -> dict[str, Any]:
    """Load JSON or YAML while rejecting duplicate keys and non-JSON values."""
    try:
        loaded = yaml.load(content.decode("utf-8"), Loader=_UniqueKeyLoader)
    except (UnicodeDecodeError, yaml.YAMLError, DuplicateKeyError) as exc:
        raise ValueError(f"{source} is not strict JSON-compatible YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"{source} must contain an object")
    _reject_non_json(loaded)
    return loaded


def load_data(path: pathlib.Path) -> dict[str, Any]:
    return load_data_bytes(path.read_bytes(), source=str(path))


def load_json_bytes(content: bytes, *, source: str = "artifact") -> dict[str, Any]:
    """Load strict JSON. Signed DSSE payloads never accept YAML."""

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise DuplicateKeyError(f"duplicate object key: {key!r}")
            result[key] = value
        return result

    try:
        loaded = json.loads(content, object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError) as exc:
        raise ValueError(f"{source} is not strict JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"{source} must contain a JSON object")
    _reject_non_json(loaded)
    return loaded


def canonical_json_bytes(value: Any) -> bytes:
    _reject_non_json(value)
    return rfc8785.dumps(value)
