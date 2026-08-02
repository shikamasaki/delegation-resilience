#!/usr/bin/env python3
"""Build the test-key-only portable Refund verification bundle."""

from __future__ import annotations

import argparse
import base64
import copy
import pathlib
import sys
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from game_days.refund.runner import canonical_digest
from tools.data_loading import canonical_json_bytes, load_data
from tools.trust import byte_digest, create_dsse_envelope

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "examples" / "refund" / "portable-verification"
KEY_ROOT = ROOT / "tests" / "fixtures" / "trust" / "keys"
CREATED_AT = "2026-08-02T07:00:00Z"


def _seed(name: str) -> bytes:
    return base64.b64decode((KEY_ROOT / f"{name}.seed").read_text().strip())


def _key(name: str) -> tuple[str, str]:
    public = (
        Ed25519PrivateKey.from_private_bytes(_seed(name))
        .public_key()
        .public_bytes(Encoding.Raw, PublicFormat.Raw)
    )
    return byte_digest(public), base64.b64encode(public).decode("ascii")


def _ref(uri: str, content: bytes) -> dict[str, str]:
    return {"uri": uri, "digest": byte_digest(content)}


def _proof(payload: dict[str, Any], *, key_name: str, payload_type: str) -> bytes:
    key_id, _ = _key(key_name)
    envelope = create_dsse_envelope(
        payload,
        payload_type=payload_type,
        key_id=key_id,
        private_key=_seed(key_name),
    )
    return canonical_json_bytes(envelope)


def _trust_policy() -> dict[str, Any]:
    bundle_key, bundle_public = _key("bundle-assembler")
    runner_key, runner_public = _key("refund-game-day-runner")
    dependency_key, dependency_public = _key("dependency-observer")
    common = {
        "status": "active",
        "validFrom": "2026-08-01T00:00:00Z",
        "validUntil": "2027-01-01T00:00:00Z",
    }
    return {
        "apiVersion": "delegation-resilience.org/v0alpha2",
        "kind": "TrustPolicy",
        "metadata": {"id": "refund-portable-verification", "version": "0.2.0-alpha.1"},
        "sequenceNumber": 1,
        "validFrom": "2026-08-01T00:00:00Z",
        "validUntil": "2026-09-01T00:00:00Z",
        "keys": [
            {
                "keyId": bundle_key,
                "algorithm": "Ed25519",
                "publicKey": bundle_public,
                "issuer": {
                    "id": "delegation-resilience-reference",
                    "type": "organization",
                },
                "independenceDomain": "reference-bundle-assembly",
                **common,
                "authorizations": [
                    {
                        "purpose": "verification_bundle",
                        "artifactKinds": ["VerificationBundle"],
                        "maxAgeSeconds": 2678400,
                    }
                ],
            },
            {
                "keyId": runner_key,
                "algorithm": "Ed25519",
                "publicKey": runner_public,
                "issuer": {"id": "refund-game-day-runner", "type": "workload"},
                "independenceDomain": "refund-exercise-runner",
                **common,
                "authorizations": [
                    {
                        "purpose": "exercise_attestation",
                        "artifactKinds": ["ExerciseAttestation"],
                        "scenarioRefs": ["refund-response-loss-after-commit"],
                        "environmentRefs": ["deterministic-in-memory-simulation"],
                        "maxAgeSeconds": 2678400,
                    },
                    {
                        "purpose": "exercise_evidence",
                        "artifactKinds": ["ExerciseEvidence"],
                        "scenarioRefs": ["refund-response-loss-after-commit"],
                        "environmentRefs": ["deterministic-in-memory-simulation"],
                        "maxAgeSeconds": 2678400,
                    },
                ],
            },
            {
                "keyId": dependency_key,
                "algorithm": "Ed25519",
                "publicKey": dependency_public,
                "issuer": {"id": "refund-dependency-observer", "type": "workload"},
                "independenceDomain": "refund-configuration-observer",
                **common,
                "authorizations": [
                    {
                        "purpose": "dependency_snapshot",
                        "artifactKinds": ["DependencySnapshot"],
                        "maxAgeSeconds": 2678400,
                    }
                ],
            },
        ],
        "revokedSubjects": [],
        "humanEvidenceRules": {
            "requireParticipantIssuerSeparation": True,
            "requireAttestationIssuerSeparation": True,
            "minimumIndependenceDomains": 2,
        },
    }


def build_artifacts() -> dict[str, bytes]:
    profile = load_data(ROOT / "examples" / "refund" / "profile.yaml")
    profile_bytes = canonical_json_bytes(profile)
    evidence = load_data(
        ROOT
        / "examples"
        / "refund"
        / "game-day"
        / "evidence"
        / "profile-aware-provider-outcomes.json"
    )
    evidence_bytes = canonical_json_bytes(evidence)
    evidence_proof = _proof(
        evidence,
        key_name="refund-game-day-runner",
        payload_type=(
            "application/vnd.delegation-resilience.exercise-evidence.v0alpha1+json"
        ),
    )
    baseline_evidence = load_data(
        ROOT
        / "examples"
        / "refund"
        / "game-day"
        / "evidence"
        / "baseline-provider-outcomes.json"
    )
    baseline_evidence_bytes = canonical_json_bytes(baseline_evidence)
    baseline_evidence_proof = _proof(
        baseline_evidence,
        key_name="refund-game-day-runner",
        payload_type=(
            "application/vnd.delegation-resilience.exercise-evidence.v0alpha1+json"
        ),
    )

    runner_bytes = (ROOT / "game_days" / "refund" / "runner.py").read_bytes()
    attestation = copy.deepcopy(
        load_data(ROOT / "examples" / "refund" / "game-day" / "attestation.yaml")
    )
    attestation["evaluatedProfile"] = {
        "uri": "profile.json",
        "digest": canonical_digest(profile),
    }
    for component in attestation["systemUnderTest"]["components"]:
        component["artifact"] = _ref("evidence/refund-runner.py", runner_bytes)
    for observation in attestation["evidence"]:
        if observation["evidenceObservationId"] == "baseline-provider-outcomes":
            observation["artifact"] = _ref(
                "evidence/baseline-provider-outcomes.json", baseline_evidence_bytes
            )
        else:
            observation["artifact"] = _ref(
                "evidence/profile-aware-provider-outcomes.json", evidence_bytes
            )
    attestation_bytes = canonical_json_bytes(attestation)
    attestation_proof = _proof(
        attestation,
        key_name="refund-game-day-runner",
        payload_type=(
            "application/vnd.delegation-resilience.exercise-attestation.v0alpha1+json"
        ),
    )

    claim = profile["spec"]["recoveryClaims"][0]
    snapshot = {
        "apiVersion": "delegation-resilience.org/v0alpha2",
        "kind": "DependencySnapshot",
        "metadata": {"id": "refund-dependencies", "version": "0.2.0-alpha.1"},
        "evaluatedProfile": {
            "uri": "profile.json",
            "digest": canonical_digest(profile),
        },
        "issuer": {"id": "refund-dependency-observer", "type": "workload"},
        "observedAt": CREATED_AT,
        "validUntil": "2026-09-01T00:00:00Z",
        "dependencies": [
            {
                "type": item["type"],
                "id": item["id"],
                "observedVersion": item["observedVersion"],
            }
            for item in claim["assuranceDependencies"]
        ],
    }
    snapshot_bytes = canonical_json_bytes(snapshot)
    snapshot_proof = _proof(
        snapshot,
        key_name="dependency-observer",
        payload_type=(
            "application/vnd.delegation-resilience.dependency-snapshot.v0alpha2+json"
        ),
    )

    artifact_refs = {
        "profile.json": _ref("profile.json", profile_bytes),
        "attestation.json": _ref("attestation.json", attestation_bytes),
        "attestation.dsse.json": _ref("attestation.dsse.json", attestation_proof),
        "evidence/profile-aware-provider-outcomes.json": _ref(
            "evidence/profile-aware-provider-outcomes.json", evidence_bytes
        ),
        "evidence/profile-aware-provider-outcomes.dsse.json": _ref(
            "evidence/profile-aware-provider-outcomes.dsse.json", evidence_proof
        ),
        "evidence/baseline-provider-outcomes.json": _ref(
            "evidence/baseline-provider-outcomes.json", baseline_evidence_bytes
        ),
        "evidence/baseline-provider-outcomes.dsse.json": _ref(
            "evidence/baseline-provider-outcomes.dsse.json", baseline_evidence_proof
        ),
        "evidence/refund-runner.py": _ref("evidence/refund-runner.py", runner_bytes),
        "dependency-snapshot.json": _ref("dependency-snapshot.json", snapshot_bytes),
        "dependency-snapshot.dsse.json": _ref(
            "dependency-snapshot.dsse.json", snapshot_proof
        ),
    }
    predicate = {
        "apiVersion": "delegation-resilience.org/v0alpha2",
        "kind": "VerificationBundle",
        "metadata": {"id": "refund-response-loss", "version": "0.2.0-alpha.1"},
        "issuer": {"id": "delegation-resilience-reference", "type": "organization"},
        "createdAt": CREATED_AT,
        "profile": artifact_refs["profile.json"],
        "attestations": [
            {
                "role": "exercise_attestation",
                "artifact": artifact_refs["attestation.json"],
                "proof": artifact_refs["attestation.dsse.json"],
            }
        ],
        "supportingArtifacts": [
            {
                "role": "exercise_evidence",
                "artifact": artifact_refs[
                    "evidence/profile-aware-provider-outcomes.json"
                ],
                "proof": artifact_refs[
                    "evidence/profile-aware-provider-outcomes.dsse.json"
                ],
            },
            {
                "role": "exercise_evidence",
                "artifact": artifact_refs["evidence/baseline-provider-outcomes.json"],
                "proof": artifact_refs["evidence/baseline-provider-outcomes.dsse.json"],
            },
        ],
        "opaqueArtifacts": [artifact_refs["evidence/refund-runner.py"]],
        "dependencySnapshot": {
            "role": "dependency_snapshot",
            "artifact": artifact_refs["dependency-snapshot.json"],
            "proof": artifact_refs["dependency-snapshot.dsse.json"],
        },
    }
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {
                "name": ref["uri"],
                "digest": {"sha256": ref["digest"].removeprefix("sha256:")},
            }
            for ref in sorted(artifact_refs.values(), key=lambda item: item["uri"])
        ],
        "predicateType": (
            "https://delegation-resilience.org/attestations/verification-bundle/v0alpha2"
        ),
        "predicate": predicate,
    }
    bundle_proof = _proof(
        statement,
        key_name="bundle-assembler",
        payload_type="application/vnd.in-toto+json",
    )
    policy_bytes = canonical_json_bytes(_trust_policy())
    return {
        "bundle.dsse.json": bundle_proof,
        "trust-policy.json": policy_bytes,
        "profile.json": profile_bytes,
        "attestation.json": attestation_bytes,
        "attestation.dsse.json": attestation_proof,
        "evidence/profile-aware-provider-outcomes.json": evidence_bytes,
        "evidence/profile-aware-provider-outcomes.dsse.json": evidence_proof,
        "evidence/baseline-provider-outcomes.json": baseline_evidence_bytes,
        "evidence/baseline-provider-outcomes.dsse.json": baseline_evidence_proof,
        "evidence/refund-runner.py": runner_bytes,
        "dependency-snapshot.json": snapshot_bytes,
        "dependency-snapshot.dsse.json": snapshot_proof,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        artifacts = build_artifacts()
        if args.write:
            for relative, content in artifacts.items():
                target = OUTPUT / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            print(f"wrote {len(artifacts)} portable bundle artifacts to {OUTPUT}")
            return 0
        errors = []
        for relative, expected in artifacts.items():
            target = OUTPUT / relative
            if not target.is_file() or target.read_bytes() != expected:
                errors.append(f"stale portable bundle artifact: {target}")
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print("ok -- portable Refund bundle is reproducible")
        return 0
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
