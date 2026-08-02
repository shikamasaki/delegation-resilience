#!/usr/bin/env python3
"""Offline, runner-independent verification of a portable assurance bundle."""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import platform
import sys
from typing import Any

try:
    from tools.artifact_validation import load_local_artifact
    from tools.data_loading import canonical_json_bytes, load_data, load_json_bytes
    from tools.portable_checks import (
        dependency_freshness,
        verify_portable_capabilities,
    )
    from tools.schema_validation import schema_errors
    from tools.trust import (
        VerifiedStatement,
        byte_digest,
        validate_trust_policy,
        verify_dsse_envelope,
    )
    from tools.validate_profile import (
        canonical_digest,
        validate_attestation,
        validate_profile,
    )
    from tools.verifier_manifest import (
        VERIFIER_VERSION,
        verifier_code_digest,
        verifier_environment_digest,
    )
except ModuleNotFoundError:
    from artifact_validation import load_local_artifact
    from data_loading import canonical_json_bytes, load_data, load_json_bytes
    from portable_checks import dependency_freshness, verify_portable_capabilities
    from schema_validation import schema_errors
    from trust import (
        VerifiedStatement,
        byte_digest,
        validate_trust_policy,
        verify_dsse_envelope,
    )
    from validate_profile import (
        canonical_digest,
        validate_attestation,
        validate_profile,
    )
    from verifier_manifest import (
        VERIFIER_VERSION,
        verifier_code_digest,
        verifier_environment_digest,
    )

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROLE_PURPOSE = {
    "exercise_attestation": "exercise_attestation",
    "exercise_evidence": "exercise_evidence",
    "human_evidence": "human_evidence",
    "dependency_snapshot": "dependency_snapshot",
}
ROLE_SCHEMA = {
    "exercise_attestation": "attestation.schema.json",
    "exercise_evidence": "exercise-evidence.schema.json",
    "human_evidence": "human-drill-evidence.schema.json",
    "dependency_snapshot": "dependency-snapshot.schema.json",
}
ROLE_PAYLOAD_TYPE = {
    "exercise_attestation": "application/vnd.delegation-resilience.exercise-attestation.v0alpha1+json",
    "exercise_evidence": "application/vnd.delegation-resilience.exercise-evidence.v0alpha1+json",
    "human_evidence": "application/vnd.delegation-resilience.human-evidence.v0alpha1+json",
    "dependency_snapshot": "application/vnd.delegation-resilience.dependency-snapshot.v0alpha2+json",
}


def _record_proof_errors(
    label: str,
    errors: list[str],
    *,
    conformance_errors: list[str],
    integrity_errors: list[str],
    signature_errors: list[str],
    issuer_trust_errors: list[str],
) -> bool:
    signature_not_checked = False
    for error in errors:
        message = f"{label}: {error}"
        if "does not byte-match" in error:
            integrity_errors.append(message)
        elif "payloadType mismatch" in error or error.startswith("DSSE schema:"):
            conformance_errors.append(message)
            if error.startswith("DSSE schema:"):
                signature_not_checked = True
        elif (
            "invalid base64" in error
            or error.startswith("DSSE payload")
            or error.startswith("DSSE envelope")
        ):
            conformance_errors.append(message)
            signature_not_checked = True
        elif "signature is invalid" in error:
            signature_errors.append(message)
        else:
            issuer_trust_errors.append(message)
            if "keyid is not uniquely trusted" in error:
                signature_not_checked = True
    return signature_not_checked


def _load_ref(
    reference: dict[str, Any], *, base: pathlib.Path, root: pathlib.Path
) -> tuple[bytes | None, list[str]]:
    return load_local_artifact(
        reference, base_dir=base, artifact_root=root, strict_paths=True
    )


def _inventory_refs(predicate: dict[str, Any]) -> list[dict[str, Any]]:
    refs = [predicate["profile"], *predicate["opaqueArtifacts"]]
    for item in [
        *predicate["attestations"],
        *predicate["supportingArtifacts"],
        predicate["dependencySnapshot"],
    ]:
        refs.extend([item["artifact"], item["proof"]])
    return refs


def _attestation_refs(attestation: dict[str, Any]) -> list[dict[str, Any]]:
    refs = [attestation.get("evaluatedProfile", {})]
    refs.extend(item.get("artifact", {}) for item in attestation.get("evidence", []))
    refs.extend(
        item.get("artifact", {})
        for item in attestation.get("systemUnderTest", {}).get("components", [])
        if item.get("artifact")
    )
    participation = attestation.get("humanParticipation", {})
    refs.extend(
        item.get("qualificationEvidence", {})
        for item in participation.get("participants", [])
    )
    refs.extend(
        item.get("artifact", {})
        for item in [
            *participation.get("authorityEvidence", []),
            *participation.get("operationalAccessEvidence", []),
        ]
    )
    return refs


def verify_bundle(
    bundle_bytes: bytes,
    *,
    bundle_base: pathlib.Path,
    artifact_root: pathlib.Path,
    trust_policy: dict[str, Any],
    as_of: dt.datetime,
    min_policy_sequence: int,
    expected_verifier_code_digest: str,
    expected_verifier_environment_digest: str,
) -> dict[str, Any]:
    conformance_errors: list[str] = []
    actual_code_digest = verifier_code_digest()
    actual_environment_digest = verifier_environment_digest()
    if platform.python_implementation() != "CPython" or sys.version_info[:3] != (
        3,
        12,
        8,
    ):
        conformance_errors.append(
            "portable verifier requires the declared CPython 3.12.8 runtime"
        )
    if expected_verifier_code_digest != actual_code_digest:
        conformance_errors.append(
            "VERIFIER_CODE_MISMATCH: running verifier does not match the caller-pinned code digest"
        )
    if expected_verifier_environment_digest != actual_environment_digest:
        conformance_errors.append(
            "VERIFIER_ENVIRONMENT_MISMATCH: running verifier does not match the caller-pinned environment digest"
        )
    integrity_errors: list[str] = []
    signature_errors: list[str] = []
    issuer_trust_errors = validate_trust_policy(trust_policy, as_of=as_of)
    signature_attempted = False
    signature_not_checked = bool(issuer_trust_errors)
    required_proof_count = 1
    if trust_policy.get("sequenceNumber", 0) < min_policy_sequence:
        issuer_trust_errors.append(
            "TRUST_POLICY_ROLLBACK: sequenceNumber is below the required minimum"
        )
    bundle_statement: VerifiedStatement | None = None
    if not issuer_trust_errors:
        signature_attempted = True
        bundle_statement, errors = verify_dsse_envelope(
            bundle_bytes,
            trust_policy=trust_policy,
            purpose="verification_bundle",
            as_of=as_of,
            expected_payload_type="application/vnd.in-toto+json",
        )
        signature_not_checked = (
            _record_proof_errors(
                "bundle signature",
                errors,
                conformance_errors=conformance_errors,
                integrity_errors=integrity_errors,
                signature_errors=signature_errors,
                issuer_trust_errors=issuer_trust_errors,
            )
            or signature_not_checked
        )
    bundle_payload = bundle_statement.payload if bundle_statement else {}
    if bundle_payload:
        conformance_errors.extend(
            f"bundle schema: {item}"
            for item in schema_errors("verification-bundle.schema.json", bundle_payload)
        )
    if conformance_errors or not bundle_payload:
        predicate: dict[str, Any] = {}
    else:
        predicate = bundle_payload["predicate"]

    loaded_artifacts: dict[str, tuple[dict[str, Any], bytes, pathlib.Path]] = {}
    verified_artifacts: dict[str, VerifiedStatement] = {}
    verified_proof_count = 1 if bundle_statement is not None else 0
    profile: dict[str, Any] = {}
    dependency_snapshot: dict[str, Any] = {}
    attestation_entries: list[tuple[dict[str, Any], pathlib.Path]] = []
    subject_inventory: dict[str, str] = {}
    if predicate:
        refs = _inventory_refs(predicate)
        uris = [item.get("uri") for item in refs]
        if len(uris) != len(set(uris)):
            integrity_errors.append("bundle inventory contains duplicate artifact URI")
        if len({str(uri).casefold() for uri in uris}) != len(uris):
            integrity_errors.append(
                "bundle inventory contains case-colliding artifact URIs"
            )
        expected_subjects = {
            (item["uri"], item["digest"].removeprefix("sha256:")) for item in refs
        }
        actual_subjects = {
            (item.get("name"), item.get("digest", {}).get("sha256"))
            for item in bundle_payload.get("subject", [])
        }
        subject_names = [item.get("name") for item in bundle_payload.get("subject", [])]
        if len(subject_names) != len(set(subject_names)):
            integrity_errors.append(
                "in-toto subject inventory contains duplicate names"
            )
        if len({str(name).casefold() for name in subject_names}) != len(subject_names):
            integrity_errors.append(
                "in-toto subject inventory contains case-colliding names"
            )
        subject_inventory = {name: digest for name, digest in actual_subjects}
        if actual_subjects != expected_subjects:
            integrity_errors.append(
                "in-toto subject inventory does not exactly match bundle references"
            )

        for reference in predicate["opaqueArtifacts"]:
            _, errors = _load_ref(reference, base=bundle_base, root=artifact_root)
            integrity_errors.extend(f"opaque artifact: {item}" for item in errors)

        profile_bytes, errors = _load_ref(
            predicate["profile"], base=bundle_base, root=artifact_root
        )
        integrity_errors.extend(f"profile: {item}" for item in errors)
        if profile_bytes is not None:
            try:
                candidate_profile = load_json_bytes(
                    profile_bytes, source="bundled profile"
                )
            except ValueError as exc:
                conformance_errors.append(str(exc))
            else:
                candidate_errors = [
                    f"profile schema: {item}"
                    for item in schema_errors("profile.schema.json", candidate_profile)
                ]
                candidate_errors.extend(
                    f"profile semantics: {item}"
                    for item in validate_profile(candidate_profile)
                )
                conformance_errors.extend(candidate_errors)
                if not candidate_errors:
                    profile = candidate_profile

        signed_items = [
            *predicate["attestations"],
            *predicate["supportingArtifacts"],
            predicate["dependencySnapshot"],
        ]
        signed_artifact_digests = [item["artifact"]["digest"] for item in signed_items]
        if len(signed_artifact_digests) != len(set(signed_artifact_digests)):
            integrity_errors.append(
                "bundle contains duplicate signed artifact digest"
            )
        required_proof_count = 1 + len(signed_items)
        for item in signed_items:
            role = item["role"]
            artifact_bytes, artifact_errors = _load_ref(
                item["artifact"], base=bundle_base, root=artifact_root
            )
            proof_bytes, proof_errors = _load_ref(
                item["proof"], base=bundle_base, root=artifact_root
            )
            integrity_errors.extend(
                f"{role} artifact: {error}" for error in artifact_errors
            )
            integrity_errors.extend(f"{role} proof: {error}" for error in proof_errors)
            if artifact_bytes is None or proof_bytes is None:
                continue
            try:
                artifact = load_json_bytes(
                    artifact_bytes, source=f"bundled {role} artifact"
                )
            except ValueError as exc:
                conformance_errors.append(str(exc))
                continue
            artifact_schema_errors = [
                f"{role} schema: {error}"
                for error in schema_errors(ROLE_SCHEMA[role], artifact)
            ]
            conformance_errors.extend(artifact_schema_errors)
            payload_type = ROLE_PAYLOAD_TYPE[role]
            if (
                role == "human_evidence"
                and artifact.get("apiVersion") == "delegation-resilience.org/v0alpha2"
            ):
                payload_type = (
                    "application/vnd.delegation-resilience.human-evidence.v0alpha2+json"
                )
            signature_attempted = True
            statement, proof_validation_errors = verify_dsse_envelope(
                proof_bytes,
                trust_policy=trust_policy,
                purpose=ROLE_PURPOSE[role],
                as_of=as_of,
                expected_payload=artifact_bytes,
                expected_payload_type=payload_type,
            )
            signature_not_checked = (
                _record_proof_errors(
                    f"{role} proof",
                    proof_validation_errors,
                    conformance_errors=conformance_errors,
                    integrity_errors=integrity_errors,
                    signature_errors=signature_errors,
                    issuer_trust_errors=issuer_trust_errors,
                )
                or signature_not_checked
            )
            if statement is not None:
                verified_proof_count += 1
            digest = item["artifact"]["digest"]
            loaded_artifacts[digest] = (
                artifact,
                artifact_bytes,
                bundle_base / item["artifact"]["uri"],
            )
            artifact_is_usable = statement is not None and not artifact_schema_errors
            if artifact_is_usable:
                verified_artifacts[digest] = statement
            if role == "exercise_attestation" and artifact_is_usable:
                attestation_entries.append(
                    (artifact, bundle_base / item["artifact"]["uri"])
                )
            elif role == "dependency_snapshot" and artifact_is_usable:
                dependency_snapshot = artifact

    claim_freshness: dict[str, str] = {}
    freshness_errors: list[str] = []
    if profile and dependency_snapshot:
        if dependency_snapshot.get("evaluatedProfile", {}).get(
            "digest"
        ) != canonical_digest(profile):
            freshness_errors.append(
                "dependency snapshot evaluatedProfile.digest does not match profile"
            )
        claim_freshness, errors = dependency_freshness(
            profile, dependency_snapshot, as_of=as_of
        )
        freshness_errors.extend(errors)
        if errors:
            claim_freshness = {
                str(claim.get("claimId")): "STALE"
                for claim in profile.get("spec", {}).get("recoveryClaims", [])
            }

    claim_results: list[dict[str, Any]] = []
    claim_definitions = {
        item.get("claimId"): item
        for item in profile.get("spec", {}).get("recoveryClaims", [])
    }
    for attestation, attestation_path in attestation_entries:
        for reference in _attestation_refs(attestation):
            uri = reference.get("uri")
            digest = reference.get("digest")
            if not isinstance(uri, str) or not isinstance(digest, str):
                integrity_errors.append(
                    "attestation contains an invalid artifact reference"
                )
                continue
            _, reference_errors = _load_ref(
                reference, base=attestation_path.parent, root=artifact_root
            )
            integrity_errors.extend(
                f"attestation artifact: {item}" for item in reference_errors
            )
            if reference_errors:
                continue
            target = (attestation_path.parent.resolve() / uri).resolve()
            try:
                bundle_name = target.relative_to(artifact_root.resolve()).as_posix()
            except ValueError:
                integrity_errors.append(
                    "attestation artifact reference escapes the bundle"
                )
                continue
            if subject_inventory.get(bundle_name) != digest.removeprefix("sha256:"):
                integrity_errors.append(
                    f"attestation artifact is not exactly covered by the signed manifest: {bundle_name}"
                )
        supported_by_claim, portable_errors = verify_portable_capabilities(
            profile, attestation, verified_artifacts
        )
        conformance_errors.extend(
            f"portable capability check: {item}" for item in portable_errors
        )
        if profile:
            conformance_errors.extend(
                f"attestation semantics: {item}"
                for item in validate_attestation(
                    profile,
                    attestation,
                    as_of,
                    artifact_base=attestation_path.parent,
                    artifact_root=artifact_root,
                    portable_supported_capabilities=supported_by_claim,
                    verified_evidence_issuers={
                        digest: statement.issuer
                        for digest, statement in verified_artifacts.items()
                        if statement.purpose == "exercise_evidence"
                    },
                )
            )
        for result in attestation.get("claimResults", []):
            claim_ref = str(result.get("claimRef"))
            claim_supported = supported_by_claim.get(claim_ref, set())
            required = set(
                claim_definitions.get(claim_ref, {}).get("requiredCapabilities", [])
            )
            freshness = claim_freshness.get(claim_ref, "UNKNOWN")
            attested = result.get("result", "inconclusive")
            verified_support = "UNKNOWN"
            if (
                attested == "demonstrated"
                and required <= claim_supported
                and freshness == "CURRENT_RELATIVE_TO_SNAPSHOT"
            ):
                verified_support = "SUPPORTED"
            blockers: list[str] = []
            if attested != "demonstrated":
                blockers.append(f"attested result is {attested}")
            if required - claim_supported:
                blockers.append("required capabilities remain unsupported")
            if freshness != "CURRENT_RELATIVE_TO_SNAPSHOT":
                blockers.append(f"assurance freshness is {freshness}")
            if attested == "failed":
                blockers.append(
                    "failure is authenticated but not independently verified as a current contradiction"
                )
            claim_results.append(
                {
                    "claimRef": claim_ref,
                    "attestationDigest": byte_digest(canonical_json_bytes(attestation)),
                    "attestedResult": attested,
                    "verifiedSupport": verified_support,
                    "supportedCapabilities": sorted(claim_supported & required),
                    "unsupportedCapabilities": sorted(required - claim_supported),
                    "freshness": freshness,
                    "blockers": blockers,
                    "evidenceGaps": list(attestation.get("evidenceGaps", [])),
                }
            )

    all_required_proofs_verified = (
        verified_proof_count == required_proof_count
        and not signature_errors
        and not signature_not_checked
    )
    if not all_required_proofs_verified:
        integrity_errors.append(
            "not every required signed artifact proof was verified"
        )
    all_errors = sorted(
        set(
            conformance_errors
            + integrity_errors
            + signature_errors
            + issuer_trust_errors
            + freshness_errors
        )
    )
    issuer_groups: dict[tuple[str, str, str], set[str]] = {}
    for statement in [bundle_statement, *verified_artifacts.values()]:
        if statement is None:
            continue
        key = (
            str(statement.issuer.get("id")),
            str(statement.issuer.get("type")),
            statement.independence_domain,
        )
        issuer_groups.setdefault(key, set()).add(statement.purpose)
    if freshness_errors:
        global_freshness = "STALE"
    elif not claim_freshness:
        global_freshness = "UNKNOWN"
    elif "STALE" in claim_freshness.values():
        global_freshness = "STALE"
    elif "REVIEW_REQUIRED" in claim_freshness.values():
        global_freshness = "REVIEW_REQUIRED"
    else:
        global_freshness = "CURRENT_RELATIVE_TO_SNAPSHOT"
    signature_status = (
        "INVALID"
        if signature_errors
        else "VALID"
        if signature_attempted and not signature_not_checked
        else "NOT_CHECKED"
    )
    issuer_trust_status = (
        "UNTRUSTED"
        if issuer_trust_errors
        else "TRUSTED"
        if all_required_proofs_verified
        else "NOT_CHECKED"
    )
    packet_verified = (
        not all_errors
        and signature_status == "VALID"
        and issuer_trust_status == "TRUSTED"
    )
    result = {
        "apiVersion": "delegation-resilience.org/v0alpha2",
        "kind": "VerificationResult",
        "packetVerificationOutcome": (
            "PACKET_VERIFIED" if packet_verified else "PACKET_REJECTED"
        ),
        "bundleDigest": byte_digest(bundle_bytes),
        "verifier": {
            "name": "delegation-resilience-portable-verifier",
            "version": VERIFIER_VERSION,
            "codeDigest": actual_code_digest,
            "environmentDigest": actual_environment_digest,
            "runtime": "CPython-3.12.8",
        },
        "evaluatedAt": as_of.isoformat().replace("+00:00", "Z"),
        "inputs": {
            "trustPolicyDigest": canonical_digest(trust_policy),
            "trustPolicySequenceNumber": trust_policy.get("sequenceNumber", 0),
            "minimumTrustPolicySequence": min_policy_sequence,
            "expectedVerifierCodeDigest": expected_verifier_code_digest,
            "expectedVerifierEnvironmentDigest": expected_verifier_environment_digest,
            "dependencySnapshotDigest": (
                byte_digest(canonical_json_bytes(dependency_snapshot))
                if dependency_snapshot
                else "sha256:" + "0" * 64
            ),
        },
        "checks": {
            "conformance": "INVALID" if conformance_errors else "VALID",
            "integrity": "FAILED" if integrity_errors else "VERIFIED",
            "signature": signature_status,
            "issuerTrust": issuer_trust_status,
            "freshness": global_freshness,
        },
        "authenticatedIssuers": [
            {
                "id": key[0],
                "type": key[1],
                "independenceDomain": key[2],
                "purposes": sorted(purposes),
            }
            for key, purposes in sorted(issuer_groups.items())
        ],
        "claimResults": claim_results,
        "errors": all_errors,
        "limitations": [
            "Signature validity binds bytes to an authorized key; it does not prove that an observation is truthful or complete.",
            "The reference exercise is deterministic simulation and does not demonstrate human takeover, production equivalence, or general system safety.",
            "Freshness is relative only to the caller-supplied signed dependency snapshot; the verifier does not observe the running deployment or prove the snapshot truthful.",
            "The verifier environment digest covers the declared interpreter binary, platform ABI, and installed verifier-distribution files; it is not a hermetic runtime or process-integrity attestation and cannot exclude preloaded code, site customization, or operating-system compromise.",
            "Deployment acceptability and legal or regulatory compliance remain accountable organizational decisions.",
        ],
        "decisionBoundary": {"deploymentDisposition": "NOT_EVALUATED"},
    }
    result_schema_errors = schema_errors("verification-result.schema.json", result)
    if result_schema_errors:
        result["packetVerificationOutcome"] = "PACKET_REJECTED"
        result["checks"]["conformance"] = "INVALID"
        result["errors"] = sorted(
            set(
                result["errors"]
                + [f"verification result schema: {e}" for e in result_schema_errors]
            )
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=pathlib.Path)
    parser.add_argument("--trust-policy", required=True, type=pathlib.Path)
    parser.add_argument("--artifact-root", type=pathlib.Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--min-policy-sequence", required=True, type=int)
    parser.add_argument("--expected-verifier-code-digest", required=True)
    parser.add_argument("--expected-verifier-environment-digest", required=True)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    try:
        as_of = dt.datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
        if as_of.tzinfo is None:
            raise ValueError("--as-of requires an explicit timezone")
        bundle_bytes = args.bundle.read_bytes()
        policy = load_data(args.trust_policy)
        root = (args.artifact_root or args.bundle.parent).resolve()
        result = verify_bundle(
            bundle_bytes,
            bundle_base=args.bundle.parent,
            artifact_root=root,
            trust_policy=policy,
            as_of=as_of,
            min_policy_sequence=args.min_policy_sequence,
            expected_verifier_code_digest=args.expected_verifier_code_digest,
            expected_verifier_environment_digest=(
                args.expected_verifier_environment_digest
            ),
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    output = canonical_json_bytes(result) + b"\n"
    if args.output:
        args.output.write_bytes(output)
    else:
        sys.stdout.buffer.write(output)
    return 0 if result["packetVerificationOutcome"] == "PACKET_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
