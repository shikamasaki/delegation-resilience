"""Content manifest for the versioned Assurance Graph verifier."""

from __future__ import annotations

import hashlib
import pathlib
from typing import Any

try:
    from tools.data_loading import canonical_json_bytes
except ModuleNotFoundError:
    from data_loading import canonical_json_bytes

ROOT = pathlib.Path(__file__).resolve().parents[1]
GRAPH_VERIFIER_VERSION = "0.1.0-alpha.1"
GRAPH_VERIFIER_FILES = (
    "tools/assurance_graph.py",
    "tools/data_loading.py",
    "tools/schema_validation.py",
    "tools/verify_assurance_graph.py",
    "profiles/assurance-graph/schema/assurance-graph.schema.json",
    "requirements-verifier.txt",
)


def _digest(path: pathlib.Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def build_assurance_graph_manifest() -> dict[str, Any]:
    files = [
        {"path": relative, "digest": _digest(ROOT / relative)}
        for relative in sorted(GRAPH_VERIFIER_FILES)
    ]
    return {
        "name": "delegation-resilience-assurance-graph-verifier",
        "version": GRAPH_VERIFIER_VERSION,
        "files": files,
    }


def assurance_graph_code_digest() -> str:
    return "sha256:" + hashlib.sha256(
        canonical_json_bytes(build_assurance_graph_manifest())
    ).hexdigest()


if __name__ == "__main__":
    import json

    manifest = build_assurance_graph_manifest()
    print(json.dumps({**manifest, "codeDigest": assurance_graph_code_digest()}, indent=2, sort_keys=True))
