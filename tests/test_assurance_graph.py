from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from tools.assurance_graph import canonical_graph_bytes, validate_graph
from tools.data_loading import canonical_json_bytes, load_json_bytes
from tools.schema_validation import schema_errors


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assurance-graph"


class AssuranceGraphTest(unittest.TestCase):
    def setUp(self):
        self.graph = load_json_bytes((EXAMPLE / "graph.json").read_bytes())
        self.artifact_root = EXAMPLE

    def test_schema_and_example_verify_without_promoting_claim(self):
        self.assertEqual([], schema_errors("assurance-graph.schema.json", self.graph))
        result = validate_graph(self.graph, artifact_root=self.artifact_root)
        self.assertEqual("GRAPH_VERIFIED", result["graphVerificationOutcome"])
        self.assertEqual("NOT_DEMONSTRATED", result["claimResults"][0]["verifiedSupport"])
        reasons = result["claimResults"][0]["reasons"]
        self.assertTrue(any("shares fate" in reason for reason in reasons))
        self.assertIn("claim is invalidated", reasons)

    def test_canonical_graph_and_standalone_result_are_deterministic(self):
        first = canonical_graph_bytes(self.graph)
        second = canonical_graph_bytes(load_json_bytes(first))
        self.assertEqual(first, second)
        expected = canonical_json_bytes(validate_graph(self.graph, artifact_root=self.artifact_root))
        command = [sys.executable, "tools/verify_assurance_graph.py", str(EXAMPLE / "graph.json"), "--artifact-root", str(EXAMPLE)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr.decode())
        self.assertEqual(expected + b"\n", result.stdout)

    def test_missing_source_reference_is_fail_closed(self):
        graph = copy.deepcopy(self.graph)
        graph["nodes"][0]["sourceRefs"] = ["src:missing"]
        result = validate_graph(graph, artifact_root=self.artifact_root)
        self.assertEqual("GRAPH_REJECTED", result["graphVerificationOutcome"])
        self.assertTrue(any("missing sourceRef" in item for item in result["errors"]))

    def test_duplicate_ids_edges_and_dangling_reference_are_rejected(self):
        graph = copy.deepcopy(self.graph)
        graph["nodes"].append(copy.deepcopy(graph["nodes"][0]))
        graph["edges"].append(copy.deepcopy(graph["edges"][0]))
        graph["edges"].append({**copy.deepcopy(graph["edges"][1]), "id": "edge:dangling", "to": "claim:missing"})
        result = validate_graph(graph, artifact_root=self.artifact_root)
        self.assertEqual("GRAPH_REJECTED", result["graphVerificationOutcome"])
        self.assertTrue(any("duplicate node id" in item for item in result["errors"]))
        self.assertTrue(any("duplicate edge" in item for item in result["errors"]))
        self.assertTrue(any("dangling to" in item for item in result["errors"]))

    def test_digest_mismatch_and_strict_json_are_rejected(self):
        graph = copy.deepcopy(self.graph)
        graph["sourceArtifacts"][0]["digest"] = "sha256:" + "0" * 64
        result = validate_graph(graph, artifact_root=self.artifact_root)
        self.assertEqual("GRAPH_REJECTED", result["graphVerificationOutcome"])
        with self.assertRaises(ValueError):
            load_json_bytes(b'{"a":1,"a":2}')
        with self.assertRaises(ValueError):
            load_json_bytes(b'{"a":NaN}')
        with self.assertRaises(ValueError):
            load_json_bytes(b'{"a":Infinity}')
        with self.assertRaises(ValueError):
            load_json_bytes(b'{"a":-Infinity}')

    def test_inferred_support_without_observed_evidence_never_supports_claim(self):
        graph = copy.deepcopy(self.graph)
        graph["edges"] = [edge for edge in graph["edges"] if edge["type"] != "invalidates"]
        graph["nodes"] = [
            {**node, "assurance": "inferred"} if node["type"] == "attestation" else node
            for node in graph["nodes"]
        ]
        result = validate_graph(graph, artifact_root=self.artifact_root)
        self.assertEqual("GRAPH_VERIFIED", result["graphVerificationOutcome"])
        self.assertEqual("NOT_DEMONSTRATED", result["claimResults"][0]["verifiedSupport"])


if __name__ == "__main__":
    unittest.main()
