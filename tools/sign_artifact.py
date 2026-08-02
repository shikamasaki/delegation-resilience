#!/usr/bin/env python3
"""Create a deterministic JSON artifact and an Ed25519 DSSE envelope."""

from __future__ import annotations

import argparse
import base64
import binascii
import pathlib
import sys

try:
    from tools.data_loading import canonical_json_bytes, load_data
    from tools.trust import create_dsse_envelope
except ModuleNotFoundError:
    from data_loading import canonical_json_bytes, load_data
    from trust import create_dsse_envelope


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("--private-key", required=True, type=pathlib.Path)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--payload-type", required=True)
    parser.add_argument("--artifact-output", required=True, type=pathlib.Path)
    parser.add_argument("--proof-output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    try:
        value = load_data(args.input)
        key_bytes = base64.b64decode(
            args.private_key.read_text(encoding="utf-8").strip(), validate=True
        )
        if len(key_bytes) != 32:
            raise ValueError("private key must be a base64-encoded raw Ed25519 seed")
        envelope = create_dsse_envelope(
            value,
            payload_type=args.payload_type,
            key_id=args.key_id,
            private_key=key_bytes,
        )
        artifact_bytes = canonical_json_bytes(value) + b"\n"
        # DSSE signs canonical JSON without a trailing newline; the portable artifact
        # uses those exact bytes to avoid representation ambiguity.
        artifact_bytes = artifact_bytes[:-1]
        proof_bytes = canonical_json_bytes(envelope) + b"\n"
        args.artifact_output.parent.mkdir(parents=True, exist_ok=True)
        args.proof_output.parent.mkdir(parents=True, exist_ok=True)
        args.artifact_output.write_bytes(artifact_bytes)
        args.proof_output.write_bytes(proof_bytes)
    except (OSError, ValueError, binascii.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
