import base64
import copy
import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest

from game_days.refund.portable_bundle import build_artifacts
from tools.artifact_validation import load_local_artifact
from tools.data_loading import canonical_json_bytes, load_json_bytes
from tools.portable_checks import dependency_freshness, verify_portable_capabilities
from tools.trust import (
    VerifiedStatement,
    byte_digest,
    create_dsse_envelope,
    validate_trust_policy,
)
from tools.validate_profile import validate_attestation
from tools.verify_bundle import verify_bundle
from tools.verifier_manifest import (
    verifier_code_digest,
    verifier_environment_digest,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
AS_OF = dt.datetime(2026, 8, 3, tzinfo=dt.timezone.utc)


class PortableVerificationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.directory.name)
        for relative, content in build_artifacts().items():
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        self.policy = json.loads((self.root / "trust-policy.json").read_text())

    def tearDown(self):
        self.directory.cleanup()

    def verify(self, *, policy=None, min_sequence=1):
        return verify_bundle(
            (self.root / "bundle.dsse.json").read_bytes(),
            bundle_base=self.root,
            artifact_root=self.root,
            trust_policy=policy or self.policy,
            as_of=AS_OF,
            min_policy_sequence=min_sequence,
            expected_verifier_code_digest=verifier_code_digest(),
            expected_verifier_environment_digest=verifier_environment_digest(),
        )

    def resign_bundle(self, statement):
        envelope = json.loads((self.root / "bundle.dsse.json").read_text())
        seed = base64.b64decode(
            (ROOT / "tests" / "fixtures" / "trust" / "keys" / "bundle-assembler.seed")
            .read_text()
            .strip()
        )
        resigned = create_dsse_envelope(
            statement,
            payload_type="application/vnd.in-toto+json",
            key_id=envelope["signatures"][0]["keyid"],
            private_key=seed,
        )
        (self.root / "bundle.dsse.json").write_bytes(canonical_json_bytes(resigned))

    def test_golden_bundle_is_portably_verified_without_deployment_decision(self):
        result = self.verify()
        self.assertEqual("PACKET_VERIFIED", result["packetVerificationOutcome"])
        self.assertEqual("CURRENT_RELATIVE_TO_SNAPSHOT", result["checks"]["freshness"])
        claim = result["claimResults"][0]
        self.assertEqual(["external_reconciliation"], claim["supportedCapabilities"])
        self.assertIn("human_takeover", claim["unsupportedCapabilities"])
        self.assertEqual("UNKNOWN", claim["verifiedSupport"])
        self.assertEqual(
            "NOT_EVALUATED", result["decisionBoundary"]["deploymentDisposition"]
        )

    def test_same_inputs_produce_byte_identical_canonical_result(self):
        first = canonical_json_bytes(self.verify())
        second = canonical_json_bytes(self.verify())
        self.assertEqual(first, second)

    def test_caller_pinned_verifier_identity_fails_closed(self):
        result = verify_bundle(
            (self.root / "bundle.dsse.json").read_bytes(),
            bundle_base=self.root,
            artifact_root=self.root,
            trust_policy=self.policy,
            as_of=AS_OF,
            min_policy_sequence=1,
            expected_verifier_code_digest="sha256:" + "0" * 64,
            expected_verifier_environment_digest=verifier_environment_digest(),
        )
        self.assertEqual("PACKET_REJECTED", result["packetVerificationOutcome"])
        self.assertTrue(
            any("VERIFIER_CODE_MISMATCH" in item for item in result["errors"])
        )

    def test_tampered_evidence_is_rejected(self):
        path = self.root / "evidence" / "profile-aware-provider-outcomes.json"
        path.write_bytes(path.read_bytes() + b" ")
        result = self.verify()
        self.assertEqual("PACKET_REJECTED", result["packetVerificationOutcome"])
        self.assertEqual("FAILED", result["checks"]["integrity"])

    def test_tampered_dsse_payload_is_rejected(self):
        path = self.root / "attestation.dsse.json"
        envelope = json.loads(path.read_text())
        payload = bytearray(base64.b64decode(envelope["payload"]))
        payload[-1] ^= 1
        envelope["payload"] = base64.b64encode(payload).decode()
        path.write_bytes(canonical_json_bytes(envelope))
        result = self.verify()
        self.assertEqual("PACKET_REJECTED", result["packetVerificationOutcome"])
        self.assertEqual("FAILED", result["checks"]["integrity"])

    def test_signed_manifest_cannot_omit_an_attestation_dependency(self):
        envelope = json.loads((self.root / "bundle.dsse.json").read_text())
        statement = json.loads(base64.b64decode(envelope["payload"]))
        statement["predicate"]["opaqueArtifacts"] = []
        statement["subject"] = [
            item
            for item in statement["subject"]
            if item["name"] != "evidence/refund-runner.py"
        ]
        seed = base64.b64decode(
            (ROOT / "tests" / "fixtures" / "trust" / "keys" / "bundle-assembler.seed")
            .read_text()
            .strip()
        )
        resigned = create_dsse_envelope(
            statement,
            payload_type="application/vnd.in-toto+json",
            key_id=envelope["signatures"][0]["keyid"],
            private_key=seed,
        )
        (self.root / "bundle.dsse.json").write_bytes(canonical_json_bytes(resigned))
        result = self.verify()
        self.assertEqual("PACKET_REJECTED", result["packetVerificationOutcome"])
        self.assertTrue(
            any("not exactly covered" in error for error in result["errors"])
        )

    def test_manifest_rejects_missing_opaque_artifact_even_when_resigned(self):
        envelope = json.loads((self.root / "bundle.dsse.json").read_text())
        statement = json.loads(base64.b64decode(envelope["payload"]))
        reference = {
            "uri": "evidence/declared-but-missing.bin",
            "digest": "sha256:" + "0" * 64,
        }
        statement["predicate"]["opaqueArtifacts"].append(reference)
        statement["subject"].append(
            {"name": reference["uri"], "digest": {"sha256": "0" * 64}}
        )
        self.resign_bundle(statement)
        result = self.verify()
        self.assertEqual("PACKET_REJECTED", result["packetVerificationOutcome"])
        self.assertTrue(
            any(
                "opaque artifact: artifact file does not exist" in item
                for item in result["errors"]
            )
        )

    def test_bundle_roles_are_position_bound(self):
        envelope = json.loads((self.root / "bundle.dsse.json").read_text())
        statement = json.loads(base64.b64decode(envelope["payload"]))
        statement["predicate"]["dependencySnapshot"]["role"] = "exercise_evidence"
        self.resign_bundle(statement)
        result = self.verify()
        self.assertEqual("PACKET_REJECTED", result["packetVerificationOutcome"])
        self.assertTrue(any("bundle schema" in item for item in result["errors"]))

    def test_self_consistent_but_fabricated_portable_evidence_is_rejected(self):
        attestation = json.loads((self.root / "attestation.json").read_text())
        evidence = json.loads(
            (
                self.root / "evidence" / "profile-aware-provider-outcomes.json"
            ).read_text()
        )
        evidence["payload"]["events"] = [
            {"intentId": "refund-intent-0001", "event": "OUTCOME_UNKNOWN"},
            {
                "intentId": "refund-intent-0001",
                "event": "CONFIRMED_SUCCEEDED_FROM_RECONCILIATION",
                "effectId": "refund-effect-0001",
            },
        ]
        evidence["payload"]["providerEffects"] = [
            {
                "intentId": "refund-intent-0001",
                "effectId": "refund-effect-0001",
                "amountJpy": 1000,
                "idempotencyKey": "refund-intent-0001",
            }
        ]
        evidence["payload"]["summary"] = {
            "intentCount": 1,
            "externalEffectCount": 1,
            "duplicateRefundCount": 0,
            "responseLostEffectCount": 1,
            "unknownOutcomeCount": 1,
            "reconciledUnknownCount": 1,
            "unrecognizedExternalEffectCountAtCompletion": 0,
            "maxUnknownDurationSteps": 1,
        }
        digest = attestation["evidence"][0]["artifact"]["digest"]
        statement = VerifiedStatement(
            subject_digest=digest,
            kind="ExerciseEvidence",
            purpose="exercise_evidence",
            issuer=evidence["issuer"],
            key_id="test-key",
            independence_domain="test-domain",
            payload=evidence,
        )
        support, errors = verify_portable_capabilities(
            json.loads((self.root / "profile.json").read_text()),
            attestation,
            {digest: statement},
        )
        self.assertEqual({}, support)
        self.assertTrue(any("independently reconstructed" in item for item in errors))

    def test_malformed_portable_event_fails_closed_without_exception(self):
        attestation = json.loads((self.root / "attestation.json").read_text())
        evidence = json.loads(
            (
                self.root / "evidence" / "profile-aware-provider-outcomes.json"
            ).read_text()
        )
        evidence["payload"]["events"] = [1]
        digest = attestation["evidence"][0]["artifact"]["digest"]
        support, errors = verify_portable_capabilities(
            json.loads((self.root / "profile.json").read_text()),
            attestation,
            {
                digest: VerifiedStatement(
                    digest,
                    "ExerciseEvidence",
                    "exercise_evidence",
                    evidence["issuer"],
                    "test-key",
                    "test-domain",
                    evidence,
                )
            },
        )
        self.assertEqual({}, support)
        self.assertTrue(any("must be objects" in item for item in errors))

    def test_portable_witness_is_bound_to_attested_actual_conditions(self):
        attestation = json.loads((self.root / "attestation.json").read_text())
        attestation["actualConditions"]["randomSeed"] = "different-seed"
        evidence = json.loads(
            (
                self.root / "evidence" / "profile-aware-provider-outcomes.json"
            ).read_text()
        )
        digest = next(
            item["artifact"]["digest"]
            for item in attestation["evidence"]
            if item["evidenceObservationId"] == "profile-aware-provider-outcomes"
        )
        support, errors = verify_portable_capabilities(
            json.loads((self.root / "profile.json").read_text()),
            attestation,
            {
                digest: VerifiedStatement(
                    digest,
                    "ExerciseEvidence",
                    "exercise_evidence",
                    evidence["issuer"],
                    "test-key",
                    "test-domain",
                    evidence,
                )
            },
        )
        self.assertEqual({}, support)
        self.assertTrue(
            any("actualConditions.randomSeed mismatch" in item for item in errors)
        )

    def test_unknown_key_is_not_trusted(self):
        policy = copy.deepcopy(self.policy)
        runner_key = next(
            item
            for item in policy["keys"]
            if item["issuer"]["id"] == "refund-game-day-runner"
        )
        runner_key["keyId"] = "sha256:" + "0" * 64
        result = self.verify(policy=policy)
        self.assertEqual("PACKET_REJECTED", result["packetVerificationOutcome"])
        self.assertEqual("UNTRUSTED", result["checks"]["issuerTrust"])
        self.assertEqual("NOT_CHECKED", result["checks"]["signature"])

    def test_invalid_signature_is_distinct_from_issuer_trust(self):
        envelope = json.loads((self.root / "bundle.dsse.json").read_text())
        signature = bytearray(base64.b64decode(envelope["signatures"][0]["sig"]))
        signature[0] ^= 1
        envelope["signatures"][0]["sig"] = base64.b64encode(signature).decode()
        (self.root / "bundle.dsse.json").write_bytes(canonical_json_bytes(envelope))
        result = self.verify()
        self.assertEqual("PACKET_REJECTED", result["packetVerificationOutcome"])
        self.assertEqual("INVALID", result["checks"]["signature"])
        self.assertEqual("NOT_CHECKED", result["checks"]["issuerTrust"])

    def test_one_failed_artifact_proof_prevents_aggregate_trusted_status(self):
        path = self.root / "attestation.dsse.json"
        envelope = json.loads(path.read_text())
        signature = bytearray(base64.b64decode(envelope["signatures"][0]["sig"]))
        signature[0] ^= 1
        envelope["signatures"][0]["sig"] = base64.b64encode(signature).decode()
        proof_bytes = canonical_json_bytes(envelope)
        path.write_bytes(proof_bytes)
        bundle_envelope = json.loads((self.root / "bundle.dsse.json").read_text())
        statement = json.loads(base64.b64decode(bundle_envelope["payload"]))
        proof_ref = statement["predicate"]["attestations"][0]["proof"]
        proof_ref["digest"] = byte_digest(proof_bytes)
        for subject in statement["subject"]:
            if subject["name"] == proof_ref["uri"]:
                subject["digest"]["sha256"] = proof_ref["digest"].removeprefix(
                    "sha256:"
                )
        self.resign_bundle(statement)
        result = self.verify()
        self.assertEqual("INVALID", result["checks"]["signature"])
        self.assertEqual("NOT_CHECKED", result["checks"]["issuerTrust"])

    def test_revoked_key_rejects_all_historical_signatures_without_timestamp(self):
        policy = copy.deepcopy(self.policy)
        runner_key = next(
            item
            for item in policy["keys"]
            if item["issuer"]["id"] == "refund-game-day-runner"
        )
        runner_key.update(
            {
                "status": "revoked",
                "revokedAt": "2026-08-03T00:00:00Z",
                "revocationReason": "test compromise",
            }
        )
        result = self.verify(policy=policy)
        self.assertEqual("PACKET_REJECTED", result["packetVerificationOutcome"])
        self.assertTrue(any("TRUST_KEY_REVOKED" in e for e in result["errors"]))

    def test_revoked_statement_is_rejected_separately_from_key_revocation(self):
        policy = copy.deepcopy(self.policy)
        artifact = self.root / "attestation.json"
        policy["revokedSubjects"] = [
            {
                "digest": byte_digest(artifact.read_bytes()),
                "revokedAt": "2026-08-03T00:00:00Z",
                "reason": "withdrawn statement",
            }
        ]
        result = self.verify(policy=policy)
        self.assertTrue(any("TRUST_SUBJECT_REVOKED" in e for e in result["errors"]))

    def test_expired_policy_and_policy_rollback_fail_closed(self):
        expired = copy.deepcopy(self.policy)
        expired["validUntil"] = "2026-08-03T00:00:00Z"
        self.assertEqual(
            "PACKET_REJECTED", self.verify(policy=expired)["packetVerificationOutcome"]
        )
        rollback = self.verify(min_sequence=2)
        self.assertTrue(any("TRUST_POLICY_ROLLBACK" in e for e in rollback["errors"]))

    def test_wrong_scenario_scope_is_rejected(self):
        policy = copy.deepcopy(self.policy)
        runner_key = next(
            item
            for item in policy["keys"]
            if item["issuer"]["id"] == "refund-game-day-runner"
        )
        for authorization in runner_key["authorizations"]:
            authorization["scenarioRefs"] = ["different-scenario"]
        result = self.verify(policy=policy)
        self.assertTrue(
            any("scenarioRefs excludes" in error for error in result["errors"])
        )

    def test_dependency_changes_have_distinct_invalidation_reasons(self):
        profile = json.loads((self.root / "profile.json").read_text())
        snapshot = json.loads((self.root / "dependency-snapshot.json").read_text())
        snapshot["dependencies"][0]["observedVersion"] = "changed"
        freshness, errors = dependency_freshness(profile, snapshot, as_of=AS_OF)
        self.assertEqual([], errors)
        self.assertEqual("STALE", freshness["refund-provider-outage"])
        claim = profile["spec"]["recoveryClaims"][0]
        claim["assuranceDependencies"][0]["invalidationPolicy"] = "manual_review"
        freshness, _ = dependency_freshness(profile, snapshot, as_of=AS_OF)
        self.assertEqual("REVIEW_REQUIRED", freshness["refund-provider-outage"])

    def test_malformed_signed_dependency_snapshot_is_rejected_without_crash(self):
        snapshot_path = self.root / "dependency-snapshot.json"
        snapshot = json.loads(snapshot_path.read_text())
        snapshot["observedAt"] = "2026-08-02T07:00:00"
        snapshot["systemUnderTest"] = 1
        snapshot_bytes = canonical_json_bytes(snapshot)
        snapshot_path.write_bytes(snapshot_bytes)

        dependency_key = next(
            item
            for item in self.policy["keys"]
            if item["issuer"]["id"] == "refund-dependency-observer"
        )
        seed = base64.b64decode(
            (
                ROOT
                / "tests"
                / "fixtures"
                / "trust"
                / "keys"
                / "dependency-observer.seed"
            )
            .read_text()
            .strip()
        )
        proof = create_dsse_envelope(
            snapshot,
            payload_type=(
                "application/vnd.delegation-resilience."
                "dependency-snapshot.v0alpha2+json"
            ),
            key_id=dependency_key["keyId"],
            private_key=seed,
        )
        proof_bytes = canonical_json_bytes(proof)
        (self.root / "dependency-snapshot.dsse.json").write_bytes(proof_bytes)

        bundle_envelope = json.loads((self.root / "bundle.dsse.json").read_text())
        statement = json.loads(base64.b64decode(bundle_envelope["payload"]))
        dependency = statement["predicate"]["dependencySnapshot"]
        dependency["artifact"]["digest"] = byte_digest(snapshot_bytes)
        dependency["proof"]["digest"] = byte_digest(proof_bytes)
        replacements = {
            dependency["artifact"]["uri"]: byte_digest(snapshot_bytes).removeprefix(
                "sha256:"
            ),
            dependency["proof"]["uri"]: byte_digest(proof_bytes).removeprefix(
                "sha256:"
            ),
        }
        for subject in statement["subject"]:
            if subject["name"] in replacements:
                subject["digest"]["sha256"] = replacements[subject["name"]]
        self.resign_bundle(statement)

        result = self.verify()
        self.assertEqual("PACKET_REJECTED", result["packetVerificationOutcome"])
        self.assertEqual("INVALID", result["checks"]["conformance"])
        self.assertTrue(
            any(
                "signed artifact has no recognized issuance/observation time" in error
                for error in result["errors"]
            )
        )

    def test_dependency_freshness_rejects_timezone_naive_timestamps(self):
        profile = json.loads((self.root / "profile.json").read_text())
        snapshot = json.loads((self.root / "dependency-snapshot.json").read_text())
        snapshot["observedAt"] = "2026-08-02T07:00:00"
        freshness, errors = dependency_freshness(profile, snapshot, as_of=AS_OF)
        self.assertEqual({}, freshness)
        self.assertEqual(
            ["dependency snapshot timestamps must be timezone-aware"], errors
        )

    def test_portable_validation_context_never_imports_exercise_runner(self):
        profile = json.loads((self.root / "profile.json").read_text())
        attestation = json.loads((self.root / "attestation.json").read_text())
        sys.modules.pop("game_days.refund.runner", None)
        validate_attestation(
            profile,
            attestation,
            AS_OF,
            artifact_base=self.root,
            artifact_root=self.root,
            portable_supported_capabilities={},
        )
        self.assertNotIn("game_days.refund.runner", sys.modules)

    def test_strict_json_rejects_duplicate_keys(self):
        with self.assertRaisesRegex(ValueError, "duplicate object key"):
            load_json_bytes(b'{"kind":"one","kind":"two"}')

    def test_portable_artifact_paths_reject_traversal_syntax(self):
        outside = self.root / "outside.json"
        outside.write_bytes(b"{}")
        nested = self.root / "nested"
        nested.mkdir()
        _, errors = load_local_artifact(
            {"uri": "../outside.json", "digest": byte_digest(b"{}")},
            base_dir=nested,
            artifact_root=self.root,
            strict_paths=True,
        )
        self.assertEqual(
            ["artifact URI must not use absolute or traversal syntax"], errors
        )

    def test_portable_artifact_paths_reject_noncanonical_aliases(self):
        (self.root / "alias.json").write_bytes(b"{}")
        _, errors = load_local_artifact(
            {"uri": "./alias.json", "digest": byte_digest(b"{}")},
            base_dir=self.root,
            artifact_root=self.root,
            strict_paths=True,
        )
        self.assertEqual(
            ["artifact URI must not use absolute or traversal syntax"], errors
        )

    def test_embedded_or_mismatched_key_identity_is_not_a_trust_anchor(self):
        policy = copy.deepcopy(self.policy)
        policy["keys"][0]["publicKey"] = base64.b64encode(b"x" * 32).decode()
        errors = validate_trust_policy(policy, as_of=AS_OF)
        self.assertTrue(any("keyId does not match" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
