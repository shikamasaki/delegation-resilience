#!/usr/bin/env python3
"""Runner-independent Assurance Graph verifier."""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib

try:
    from tools.assurance_graph import verify_file
    from tools.data_loading import canonical_json_bytes
except ModuleNotFoundError:
    from assurance_graph import verify_file
    from data_loading import canonical_json_bytes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("graph", type=pathlib.Path)
    parser.add_argument("--artifact-root", type=pathlib.Path)
    args = parser.parse_args()
    result = verify_file(args.graph, artifact_root=args.artifact_root)
    print(canonical_json_bytes(result).decode("utf-8"))
    return 0 if result["graphVerificationOutcome"] == "GRAPH_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
