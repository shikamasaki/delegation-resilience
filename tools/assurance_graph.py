"""Semantic model and deterministic verifier for the Assurance Graph profile."""

from __future__ import annotations

import hashlib
import pathlib
from typing import Any

try:
    from tools.data_loading import canonical_json_bytes, load_json_bytes
    from tools.schema_validation import schema_errors
except ModuleNotFoundError:
    from data_loading import canonical_json_bytes, load_json_bytes
    from schema_validation import schema_errors

GRAPH_SCHEMA = "assurance-graph.schema.json"

EDGE_ENDPOINT_TYPES = {
    "attempts": ({"intent"}, {"attempt"}),
    "uses": ({"attempt"}, {"capability", "actor", "dependency"}),
    "produces": ({"attempt"}, {"external_effect", "evidence", "artifact"}),
    "observes": ({"attestation", "exercise", "evidence"}, {"evidence", "external_effect", "attempt"}),
    "reconciles": ({"attempt", "evidence", "attestation", "exercise"}, {"external_effect"}),
    "supports": ({"evidence", "attestation", "exercise", "artifact"}, {"claim"}),
    "depends_on": ({"claim", "attempt", "exercise"}, {"dependency"}),
    "invalidates": ({"dependency", "evidence", "attestation", "artifact"}, {"claim", "attestation"}),
    "shares_fate_with": ({"dependency"}, {"dependency"}),
    "hands_off_to": ({"attempt", "actor", "capability"}, {"actor", "capability", "attempt"}),
    "produces_artifact": ({"exercise", "attempt", "attestation"}, {"artifact"}),
}


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def _safe_artifact(root: pathlib.Path, uri: str) -> pathlib.Path | None:
    candidate = (root / uri).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _source_index(graph: dict[str, Any], errors: list[str]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for source in graph.get("sourceArtifacts", []):
        source_id = source.get("id")
        if source_id in index:
            _error(errors, f"duplicate source artifact id: {source_id}")
        else:
            index[source_id] = source
    return index


def _check_source_refs(
    element: dict[str, Any], source_index: dict[str, dict[str, Any]],
    artifact_root: pathlib.Path | None, errors: list[str], label: str,
) -> None:
    refs = element.get("sourceRefs", [])
    for source_ref in refs:
        source = source_index.get(source_ref)
        if source is None:
            _error(errors, f"{label} references missing sourceRef: {source_ref}")
            continue
        if artifact_root is not None:
            path = _safe_artifact(artifact_root, source["uri"])
            if path is None:
                _error(errors, f"{label} source artifact is missing: {source['uri']}")
            elif "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() != source["digest"]:
                _error(errors, f"{label} source artifact digest mismatch: {source['uri']}")
    provenance = element.get("provenance", {})
    for source_ref in provenance.get("sourceRefs", []):
        if source_ref not in source_index:
            _error(errors, f"{label} provenance references missing sourceRef: {source_ref}")
    digest = element.get("artifactDigest")
    if digest and not any(source_index.get(ref, {}).get("digest") == digest for ref in refs):
        _error(errors, f"{label} artifactDigest is not bound to a sourceRef")


def validate_graph(
    graph: dict[str, Any], *, artifact_root: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Return deterministic semantic validation and claim disposition."""
    errors = list(schema_errors(GRAPH_SCHEMA, graph))
    source_index = _source_index(graph, errors)
    node_index: dict[str, dict[str, Any]] = {}
    for node in graph.get("nodes", []):
        node_id = node.get("id")
        if node_id in node_index:
            _error(errors, f"duplicate node id: {node_id}")
        else:
            node_index[node_id] = node
        _check_source_refs(node, source_index, artifact_root, errors, f"node[{node_id}]")
    edge_index: dict[str, dict[str, Any]] = {}
    edge_pairs: set[tuple[str, str, str]] = set()
    for edge in graph.get("edges", []):
        edge_id = edge.get("id")
        if edge_id in edge_index:
            _error(errors, f"duplicate edge id: {edge_id}")
        else:
            edge_index[edge_id] = edge
        pair = (edge.get("type", ""), edge.get("from", ""), edge.get("to", ""))
        if pair in edge_pairs:
            _error(errors, f"duplicate edge: {pair[0]} {pair[1]} -> {pair[2]}")
        edge_pairs.add(pair)
        if edge.get("from") not in node_index:
            _error(errors, f"edge[{edge_id}] has dangling from reference")
        if edge.get("to") not in node_index:
            _error(errors, f"edge[{edge_id}] has dangling to reference")
        else:
            allowed_from, allowed_to = EDGE_ENDPOINT_TYPES[edge.get("type", "")]
            from_type = node_index.get(edge.get("from"), {}).get("type")
            to_type = node_index.get(edge.get("to"), {}).get("type")
            if from_type not in allowed_from or to_type not in allowed_to:
                _error(errors, f"edge[{edge_id}] has invalid endpoint types: {from_type} -> {to_type}")
        _check_source_refs(edge, source_index, artifact_root, errors, f"edge[{edge_id}]")
    for source in source_index.values():
        if artifact_root is not None:
            path = _safe_artifact(artifact_root, source["uri"])
            if path is None:
                _error(errors, f"source artifact is missing: {source['uri']}")
            elif "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() != source["digest"]:
                _error(errors, f"source artifact digest mismatch: {source['uri']}")

    dependencies = {node_id for node_id, node in node_index.items() if node.get("type") == "dependency"}
    shared_fate: set[str] = set()
    for edge in edge_index.values():
        if edge.get("type") == "shares_fate_with" and edge.get("from") in dependencies and edge.get("to") in dependencies:
            shared_fate.update((edge["from"], edge["to"]))
    invalidated: set[str] = {
        edge["to"] for edge in edge_index.values() if edge.get("type") == "invalidates"
    }
    claim_results: list[dict[str, Any]] = []
    for claim_id, claim in sorted(node_index.items()):
        if claim.get("type") != "claim":
            continue
        supports = [edge for edge in edge_index.values() if edge.get("type") == "supports" and edge.get("to") == claim_id]
        direct_dependencies = {
            edge["to"] for edge in edge_index.values()
            if edge.get("type") == "depends_on" and edge.get("from") == claim_id
        }
        reasons: list[str] = []
        if claim.get("assurance") != "observed" or any(edge.get("assurance") != "observed" for edge in supports):
            reasons.append("support contains inferred or derived relations")
        if direct_dependencies & shared_fate:
            reasons.append("dependency shares fate with another dependency")
        invalidated_support = any(edge.get("from") in invalidated for edge in supports)
        if claim_id in invalidated or invalidated_support:
            reasons.append("claim is invalidated")
        status = "NOT_DEMONSTRATED"
        claim_results.append({"claimId": claim_id, "requestedStatus": claim.get("attributes", {}).get("status", "UNKNOWN"), "verifiedSupport": status, "reasons": sorted(reasons)})
    outcome = "GRAPH_REJECTED" if errors else "GRAPH_VERIFIED"
    return {
        "apiVersion": "delegation-resilience.org/assurance-graph/v0alpha1",
        "kind": "AssuranceGraphVerificationResult",
        "graphVerificationOutcome": outcome,
        "graphDigest": "sha256:" + hashlib.sha256(canonical_json_bytes(graph)).hexdigest(),
        "claimResults": claim_results,
        "errors": sorted(errors),
        "limitations": [
            "Graph verification does not demonstrate recovery capability.",
            "Inferred or shared-fate relations never independently support a claim.",
            "The graph is a reproducible derived artifact, not authorization or runtime execution.",
        ],
    }


def verify_file(path: pathlib.Path, *, artifact_root: pathlib.Path | None = None) -> dict[str, Any]:
    return validate_graph(load_json_bytes(path.read_bytes(), source=str(path)), artifact_root=artifact_root)


def canonical_graph_bytes(graph: dict[str, Any]) -> bytes:
    return canonical_json_bytes(graph)
