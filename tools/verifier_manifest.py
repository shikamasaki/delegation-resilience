"""Content manifest for the standalone verifier implementation."""

from __future__ import annotations

import hashlib
import importlib.metadata
import pathlib
import platform
import sys
import sysconfig
from typing import Any

try:
    from tools.data_loading import canonical_json_bytes
except ModuleNotFoundError:
    from data_loading import canonical_json_bytes

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERIFIER_VERSION = "0.2.0-alpha.1"
TOOL_FILES = (
    "__init__.py",
    "artifact_validation.py",
    "data_loading.py",
    "portable_checks.py",
    "schema_validation.py",
    "trust.py",
    "validate_profile.py",
    "verifier_manifest.py",
    "verify_bundle.py",
)
VERIFIER_DISTRIBUTIONS = (
    "attrs",
    "cffi",
    "cryptography",
    "jsonschema",
    "jsonschema-specifications",
    "pycparser",
    "PyYAML",
    "referencing",
    "rfc8785",
    "rpds-py",
    "typing_extensions",
)


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _distribution_record(name: str) -> dict[str, Any]:
    distribution = importlib.metadata.distribution(name)
    files = []
    for relative in sorted(
        distribution.files or [],
        key=lambda item: pathlib.PurePosixPath(item).as_posix(),
    ):
        path = pathlib.Path(distribution.locate_file(relative))
        if path.is_file():
            files.append(
                {
                    "path": pathlib.PurePosixPath(relative).as_posix(),
                    "digest": _digest(path.read_bytes()),
                }
            )
    if not files:
        raise RuntimeError(f"distribution has no hashable installed files: {name}")
    return {
        "name": name,
        "version": distribution.version,
        "files": files,
    }


def build_verifier_manifest() -> dict[str, Any]:
    paths = [ROOT / "tools" / name for name in TOOL_FILES]
    paths.extend(
        sorted((ROOT / "profiles" / "transactional-action" / "schema").glob("*.json"))
    )
    paths.append(ROOT / "requirements-verifier.txt")
    return {
        "name": "delegation-resilience-portable-verifier",
        "version": VERIFIER_VERSION,
        "runtime": {
            "implementation": platform.python_implementation(),
            "pythonVersion": platform.python_version(),
            "interpreter": {
                "digest": _digest(pathlib.Path(sys.executable).read_bytes()),
                "cacheTag": sys.implementation.cache_tag,
            },
            "platform": {
                "system": platform.system(),
                "machine": platform.machine(),
                "sysconfigPlatform": sysconfig.get_platform(),
                "soabi": sysconfig.get_config_var("SOABI") or "none",
                "extSuffix": sysconfig.get_config_var("EXT_SUFFIX") or "none",
            },
            "distributions": [
                _distribution_record(name) for name in VERIFIER_DISTRIBUTIONS
            ],
        },
        "files": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "digest": _digest(path.read_bytes()),
            }
            for path in sorted(
                paths, key=lambda item: item.relative_to(ROOT).as_posix()
            )
        ],
    }


def verifier_code_digest() -> str:
    manifest = build_verifier_manifest()
    return _digest(
        canonical_json_bytes(
            {key: manifest[key] for key in ("name", "version", "files")}
        )
    )


def verifier_environment_digest() -> str:
    return _digest(canonical_json_bytes(build_verifier_manifest()["runtime"]))


def published_verifier_manifest() -> dict[str, Any]:
    """Return the export manifest plus independently pinnable digests."""
    manifest = build_verifier_manifest()
    return {
        **manifest,
        "codeDigest": verifier_code_digest(),
        "environmentDigest": verifier_environment_digest(),
    }
