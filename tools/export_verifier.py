#!/usr/bin/env python3
"""Export the standalone verifier without any exercise runner or generator."""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys

try:
    from tools.data_loading import canonical_json_bytes
    from tools.verifier_manifest import TOOL_FILES, published_verifier_manifest
except ModuleNotFoundError:
    from data_loading import canonical_json_bytes
    from verifier_manifest import TOOL_FILES, published_verifier_manifest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def export(target: pathlib.Path) -> None:
    if target.exists() and any(target.iterdir()):
        raise ValueError("export target must be absent or empty")
    (target / "tools").mkdir(parents=True, exist_ok=True)
    (target / "profiles" / "transactional-action" / "schema").mkdir(
        parents=True, exist_ok=True
    )
    for name in TOOL_FILES:
        shutil.copyfile(ROOT / "tools" / name, target / "tools" / name)
    for schema in (ROOT / "profiles" / "transactional-action" / "schema").glob(
        "*.json"
    ):
        shutil.copyfile(
            schema,
            target / "profiles" / "transactional-action" / "schema" / schema.name,
        )
    shutil.copyfile(
        ROOT / "requirements-verifier.txt", target / "requirements-verifier.txt"
    )
    (target / "VERIFIER-MANIFEST.json").write_bytes(
        canonical_json_bytes(published_verifier_manifest()) + b"\n"
    )
    (target / "README.txt").write_text(
        "Delegation Resilience portable verifier v0alpha2\n"
        "No exercise runner or artifact generator is included.\n"
        "Install requirements-verifier.txt, then run tools/verify_bundle.py.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=pathlib.Path)
    args = parser.parse_args()
    try:
        export(args.target)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"exported standalone verifier to {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
