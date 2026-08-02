import copy
import datetime as dt
import json
import pathlib
import tempfile
import unittest

import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from game_days.refund.human_drill import evaluate_readiness, preflight_context_digest
from game_days.refund.runner import byte_digest, canonical_digest
from tools.artifact_validation import validate_human_evidence
from tools.data_loading import canonical_json_bytes
from tools.trust import (
    create_dsse_envelope,
    validate_trust_policy,
    verify_dsse_envelope,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]


class RefundHumanDrillPreflightTest(unittest.TestCase):
    def setUp(self):
        with (ROOT / "examples" / "refund" / "profile.yaml").open() as handle:
            self.profile = yaml.safe_load(handle)
        with (
            ROOT
            / "examples"
            / "refund"
            / "game-day"
            / "human-drill"
            / "preflight-input.yaml"
        ).open() as handle:
            self.manifest = yaml.safe_load(handle)

    def test_repository_fixture_is_not_ready_and_cannot_demonstrate_takeover(self):
        report = evaluate_readiness(self.profile, self.manifest)
        self.assertFalse(report["ready"])
        self.assertGreater(len(report["missingPrerequisites"]), 0)
        self.assertEqual(
            "not_demonstrated", report["claimResultCeilingBeforeCompletedDrill"]
        )
        self.assertFalse(report["humanTakeoverMayBeClaimed"])

    def test_complete_digest_bound_preflight_remains_advisory_without_trust(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["sandboxEnvironmentId"] = "refund-sandbox-01"
        manifest["preflightRunId"] = "refund-human-run-0001"
        manifest["challenge"] = "challenge-refund-human-run-0001"
        manifest["facilitatorId"] = "facilitator-01"
        manifest["abortAuthorityId"] = "abort-authority-01"
        manifest["participantDataUse"] = {
            "purpose": "facilitated resilience exercise",
            "audiences": ["exercise-assurance-team"],
            "retentionUntil": "2026-11-01T00:00:00Z",
        }
        manifest["participants"] = [
            {
                "participantId": "operator-01",
                "simulated": False,
            },
            {
                "participantId": "operator-02",
                "simulated": False,
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            evidence_root = pathlib.Path(directory)

            briefing_bytes = canonical_json_bytes(
                {
                    "title": "Refund human takeover drill briefing",
                    "run": manifest["preflightRunId"],
                    "challenge": manifest["challenge"],
                }
            )
            briefing_path = evidence_root / "briefing" / "briefing.json"
            briefing_path.parent.mkdir(parents=True, exist_ok=True)
            briefing_path.write_bytes(briefing_bytes)
            manifest["briefingArtifact"] = {
                "uri": "briefing/briefing.json",
                "digest": byte_digest(briefing_bytes),
            }

            def artifact(name, evidence_type, subject_refs, object_ref, covers):
                envelope = {
                    "apiVersion": "delegation-resilience.org/v0alpha2",
                    "kind": "HumanDrillEvidence",
                    "scenarioRef": "refund-facilitated-human-takeover",
                    "environmentRef": "refund-sandbox-01",
                    "evidenceType": evidence_type,
                    "subjectRefs": subject_refs,
                    "objectRef": object_ref,
                    "finding": "satisfied",
                    "covers": covers,
                    "issuer": {"id": "test-evidence-issuer", "type": "service"},
                    "observedAt": "2026-08-02T00:00:00Z",
                    "validUntil": "2026-11-01T00:00:00Z",
                    "assurance": "digest_bound",
                }
                if evidence_type == "participant_acknowledgement":
                    envelope["participantDecision"] = "acknowledged"
                if evidence_type == "withdrawal_status":
                    envelope["participantStatus"] = "active"
                content = (
                    json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n"
                ).encode()
                path = evidence_root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                return {"uri": name, "digest": byte_digest(content)}

            for participant in manifest["participants"]:
                participant_id = participant["participantId"]
                participant["qualificationEvidence"] = artifact(
                    f"evidence/{participant_id}-qualification.json",
                    "qualification",
                    [participant_id],
                    "refund-facilitated-human-takeover",
                    ["refund_operator_qualification"],
                )

            manifest["authorityVerifications"] = [
                {
                    "participantRef": participant,
                    "evidence": artifact(
                        f"evidence/{participant}-authority.json",
                        "authority",
                        [participant],
                        "execute_refund",
                        ["sandbox_refund_authority"],
                    ),
                }
                for participant in ["operator-01", "operator-02"]
            ]
            manifest["operationalAccessVerifications"] = [
                {
                    "participantRef": participant,
                    "evidence": artifact(
                        f"evidence/{participant}-access.json",
                        "operational_access",
                        [participant],
                        "refund-sandbox-console",
                        ["sandbox_operational_access"],
                    ),
                }
                for participant in ["operator-01", "operator-02"]
            ]
            manifest["operatorChannelIndependenceEvidence"] = [
                {
                    "covers": [
                        "identity",
                        "policy",
                        "provider_outcome",
                        "agent_connector",
                    ],
                    "evidence": artifact(
                        "evidence/operator-channel-dependency-test.json",
                        "channel_independence",
                        ["customer-operations-channel"],
                        "customer-operations-channel",
                        ["identity", "policy", "provider_outcome", "agent_connector"],
                    ),
                }
            ]
            manifest["participantSafeguardEvidence"] = [
                {
                    "covers": [
                        "briefing_consent",
                        "data_use_retention",
                        "operator_abort_rights",
                        "fatigue_shift_plan",
                    ],
                    "evidence": artifact(
                        "evidence/participant-safeguards.json",
                        "participant_safeguard",
                        ["operator-01", "operator-02"],
                        "refund-facilitated-human-takeover",
                        [
                            "briefing_consent",
                            "data_use_retention",
                            "operator_abort_rights",
                            "fatigue_shift_plan",
                        ],
                    ),
                }
            ]
            manifest["facilitatorAssignmentEvidence"] = artifact(
                "evidence/facilitator-assignment.json",
                "facilitator_assignment",
                ["facilitator-01"],
                "refund-facilitated-human-takeover",
                ["facilitator_accountability"],
            )
            manifest["abortAuthorityAssignmentEvidence"] = artifact(
                "evidence/abort-authority-assignment.json",
                "abort_authority_assignment",
                ["abort-authority-01"],
                "refund-facilitated-human-takeover",
                ["abort_authority"],
            )
            manifest["participantAcknowledgements"] = [
                {
                    "participantRef": participant,
                    "evidence": artifact(
                        f"evidence/{participant}-acknowledgement.json",
                        "participant_acknowledgement",
                        [participant],
                        "refund-facilitated-human-takeover",
                        [
                            "briefing_consent",
                            "data_use_retention",
                            "operator_abort_rights",
                        ],
                    ),
                }
                for participant in ["operator-01", "operator-02"]
            ]
            manifest["withdrawalStatusEvidence"] = [
                {
                    "participantRef": participant,
                    "evidence": artifact(
                        f"evidence/{participant}-withdrawal-status.json",
                        "withdrawal_status",
                        [participant],
                        "refund-facilitated-human-takeover",
                        ["active_participation"],
                    ),
                }
                for participant in ["operator-01", "operator-02"]
            ]
            manifest["controls"] = {key: True for key in manifest["controls"]}

            context_digest = preflight_context_digest(manifest)
            briefing_digest = manifest["briefingArtifact"]["digest"]
            for field, sequence in (
                ("participantAcknowledgements", 1),
                ("withdrawalStatusEvidence", 2),
            ):
                for item in manifest[field]:
                    reference = item["evidence"]
                    path = evidence_root / reference["uri"]
                    evidence = json.loads(path.read_text())
                    evidence.update(
                        {
                            "statementSequence": sequence,
                            "preflightRunId": manifest["preflightRunId"],
                            "challenge": manifest["challenge"],
                            "profileDigest": canonical_digest(self.profile),
                            "preflightContextDigest": context_digest,
                            "briefingArtifactDigest": briefing_digest,
                        }
                    )
                    content = canonical_json_bytes(evidence)
                    path.write_bytes(content)
                    reference["digest"] = byte_digest(content)

            report = evaluate_readiness(
                self.profile,
                manifest,
                evidence_root=evidence_root,
                as_of=dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
            )
            self.assertFalse(report["ready"])
            self.assertTrue(
                report["digestBoundPrerequisitesComplete"],
                report["missingPrerequisites"],
            )
            self.assertTrue(report["trustedIssuerVerificationImplemented"])
            self.assertFalse(report["trustedEvidenceComplete"])
            self.assertTrue(
                any(
                    "external trust policy" in item
                    for item in report["missingPrerequisites"]
                )
            )

            self.assertEqual(
                "not_demonstrated",
                report["claimResultCeilingBeforeCompletedDrill"],
            )
            self.assertFalse(report["humanTakeoverMayBeClaimed"])

            trusted_manifest = copy.deepcopy(manifest)
            seeds = [bytes([1]) * 32, bytes([2]) * 32, bytes([3]) * 32, bytes([4]) * 32]
            issuers = [
                {"id": "human-evidence-authority-a", "type": "service"},
                {"id": "human-evidence-authority-b", "type": "service"},
                {"id": "operator-01", "type": "human"},
                {"id": "operator-02", "type": "human"},
            ]
            key_records = []
            for index, seed in enumerate(seeds):
                public = (
                    Ed25519PrivateKey.from_private_bytes(seed)
                    .public_key()
                    .public_bytes(Encoding.Raw, PublicFormat.Raw)
                )
                evidence_types = (
                    ["participant_acknowledgement", "withdrawal_status"]
                    if index >= 2
                    else [
                        "qualification",
                        "authority",
                        "operational_access",
                        "channel_independence",
                        "participant_safeguard",
                        "facilitator_assignment",
                        "abort_authority_assignment",
                    ]
                )
                subject_refs = (
                    [issuers[index]["id"]]
                    if index >= 2
                    else [
                        "operator-01",
                        "operator-02",
                        "customer-operations-channel",
                        "facilitator-01",
                        "abort-authority-01",
                    ]
                )
                object_refs = (
                    ["refund-facilitated-human-takeover"]
                    if index >= 2
                    else [
                        "refund-facilitated-human-takeover",
                        "execute_refund",
                        "refund-sandbox-console",
                        "customer-operations-channel",
                    ]
                )
                covers = (
                    [
                        "briefing_consent",
                        "data_use_retention",
                        "operator_abort_rights",
                        "active_participation",
                    ]
                    if index >= 2
                    else [
                        "refund_operator_qualification",
                        "sandbox_refund_authority",
                        "sandbox_operational_access",
                        "identity",
                        "policy",
                        "provider_outcome",
                        "agent_connector",
                        "briefing_consent",
                        "data_use_retention",
                        "operator_abort_rights",
                        "fatigue_shift_plan",
                        "facilitator_accountability",
                        "abort_authority",
                    ]
                )
                key_records.append(
                    {
                        "keyId": byte_digest(public),
                        "algorithm": "Ed25519",
                        "publicKey": __import__("base64").b64encode(public).decode(),
                        "issuer": issuers[index],
                        "independenceDomain": f"human-evidence-domain-{index + 1}",
                        "status": "active",
                        "validFrom": "2026-08-01T00:00:00Z",
                        "validUntil": "2026-12-01T00:00:00Z",
                        "authorizations": [
                            {
                                "purpose": "human_evidence",
                                "artifactKinds": ["HumanDrillEvidence"],
                                "scenarioRefs": ["refund-facilitated-human-takeover"],
                                "environmentRefs": ["refund-sandbox-01"],
                                "evidenceTypes": evidence_types,
                                "apiVersions": ["delegation-resilience.org/v0alpha2"],
                                "payloadTypes": [
                                    "application/vnd.delegation-resilience.human-evidence.v0alpha2+json"
                                ],
                                "subjectRefs": subject_refs,
                                "objectRefs": object_refs,
                                "covers": covers,
                                "maxAgeSeconds": 86400,
                            }
                        ],
                    }
                )
            trust_policy = {
                "apiVersion": "delegation-resilience.org/v0alpha2",
                "kind": "TrustPolicy",
                "metadata": {"id": "human-preflight-test", "version": "1"},
                "sequenceNumber": 1,
                "validFrom": "2026-08-01T00:00:00Z",
                "validUntil": "2026-12-01T00:00:00Z",
                "keys": key_records,
                "revokedSubjects": [],
                "humanEvidenceRules": {
                    "requireParticipantIssuerSeparation": True,
                    "requireAttestationIssuerSeparation": True,
                    "minimumIndependenceDomains": 2,
                },
            }
            independent_references = [
                *[
                    item["qualificationEvidence"]
                    for item in trusted_manifest["participants"]
                ],
                *[
                    item["evidence"]
                    for item in trusted_manifest["authorityVerifications"]
                ],
                *[
                    item["evidence"]
                    for item in trusted_manifest["operationalAccessVerifications"]
                ],
                *[
                    item["evidence"]
                    for item in trusted_manifest["operatorChannelIndependenceEvidence"]
                ],
                *[
                    item["evidence"]
                    for item in trusted_manifest["participantSafeguardEvidence"]
                ],
                trusted_manifest["facilitatorAssignmentEvidence"],
                trusted_manifest["abortAuthorityAssignmentEvidence"],
            ]
            participant_references = [
                *[
                    item["evidence"]
                    for item in trusted_manifest["participantAcknowledgements"]
                ],
                *[
                    item["evidence"]
                    for item in trusted_manifest["withdrawalStatusEvidence"]
                ],
            ]

            def sign_reference(reference, key_index, *, context_digest=None):
                source_path = evidence_root / reference["uri"]
                envelope = json.loads(source_path.read_text())
                if context_digest is not None:
                    envelope["preflightContextDigest"] = context_digest
                envelope["issuer"] = issuers[key_index]
                content = canonical_json_bytes(envelope)
                path = evidence_root / "trusted" / reference["uri"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                reference["uri"] = str(path.relative_to(evidence_root))
                reference["digest"] = byte_digest(content)
                proof = create_dsse_envelope(
                    envelope,
                    payload_type=(
                        "application/vnd.delegation-resilience."
                        "human-evidence.v0alpha2+json"
                    ),
                    key_id=key_records[key_index]["keyId"],
                    private_key=seeds[key_index],
                )
                proof_path = path.with_suffix(".dsse.json")
                proof_bytes = canonical_json_bytes(proof)
                proof_path.write_bytes(proof_bytes)
                reference["proof"] = {
                    "uri": str(proof_path.relative_to(evidence_root)),
                    "digest": byte_digest(proof_bytes),
                }

            for index, reference in enumerate(independent_references):
                sign_reference(reference, index % 2)
            trusted_context_digest = preflight_context_digest(trusted_manifest)
            for reference in participant_references:
                envelope = json.loads((evidence_root / reference["uri"]).read_text())
                key_index = 2 if envelope["subjectRefs"] == ["operator-01"] else 3
                sign_reference(
                    reference,
                    key_index,
                    context_digest=trusted_context_digest,
                )

            participant_statements = {
                item["participantRef"]: {
                    "sequence": 2,
                    "status": "active",
                    "statementDigest": item["evidence"]["digest"],
                }
                for item in trusted_manifest["withdrawalStatusEvidence"]
            }

            def highwater(state=None):
                return {
                    "apiVersion": "delegation-resilience.org/v0alpha2",
                    "kind": "ParticipantSequenceHighWatermarks",
                    "trustPolicyRef": "human-preflight-test",
                    "trustPolicySequenceNumber": 1,
                    "preflightRunId": trusted_manifest["preflightRunId"],
                    "challenge": trusted_manifest["challenge"],
                    "participantStatements": copy.deepcopy(
                        state or participant_statements
                    ),
                }

            trusted_report = evaluate_readiness(
                self.profile,
                trusted_manifest,
                evidence_root=evidence_root,
                as_of=dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
                trust_policy=trust_policy,
                min_policy_sequence=1,
                participant_sequence_highwatermarks=highwater(),
            )
            self.assertTrue(
                trusted_report["ready"], trusted_report["missingPrerequisites"]
            )
            self.assertTrue(trusted_report["trustedEvidenceComplete"])
            self.assertFalse(trusted_report["humanTakeoverMayBeClaimed"])

            stale_state = copy.deepcopy(participant_statements)
            stale_state["operator-01"]["sequence"] = 3
            stale_highwater_report = evaluate_readiness(
                self.profile,
                trusted_manifest,
                evidence_root=evidence_root,
                as_of=dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
                trust_policy=trust_policy,
                min_policy_sequence=1,
                participant_sequence_highwatermarks=highwater(stale_state),
            )
            self.assertFalse(stale_highwater_report["ready"])
            self.assertTrue(
                any(
                    "stale participant status sequence" in item
                    for item in stale_highwater_report["missingPrerequisites"]
                )
            )

            withdrawn_state = copy.deepcopy(participant_statements)
            withdrawn_state["operator-01"].update(
                {
                    "status": "withdrawn",
                    "statementDigest": "sha256:" + "0" * 64,
                }
            )
            withdrawn_report = evaluate_readiness(
                self.profile,
                trusted_manifest,
                evidence_root=evidence_root,
                as_of=dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
                trust_policy=trust_policy,
                min_policy_sequence=1,
                participant_sequence_highwatermarks=highwater(withdrawn_state),
            )
            self.assertFalse(withdrawn_report["ready"])
            self.assertTrue(
                any(
                    "already observed withdrawal" in item
                    for item in withdrawn_report["missingPrerequisites"]
                )
            )

            equivocation_state = copy.deepcopy(participant_statements)
            equivocation_state["operator-01"]["statementDigest"] = "sha256:" + "f" * 64
            equivocation_report = evaluate_readiness(
                self.profile,
                trusted_manifest,
                evidence_root=evidence_root,
                as_of=dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
                trust_policy=trust_policy,
                min_policy_sequence=1,
                participant_sequence_highwatermarks=highwater(equivocation_state),
            )
            self.assertFalse(equivocation_report["ready"])
            self.assertTrue(
                any(
                    "equal-sequence participant status equivocation" in item
                    for item in equivocation_report["missingPrerequisites"]
                )
            )

            conflicting_domains = copy.deepcopy(trust_policy)
            extra_key = copy.deepcopy(conflicting_domains["keys"][0])
            extra_public = (
                Ed25519PrivateKey.from_private_bytes(bytes([9]) * 32)
                .public_key()
                .public_bytes(Encoding.Raw, PublicFormat.Raw)
            )
            extra_key["keyId"] = byte_digest(extra_public)
            extra_key["publicKey"] = (
                __import__("base64").b64encode(extra_public).decode()
            )
            extra_key["independenceDomain"] = "fabricated-second-domain"
            conflicting_domains["keys"].append(extra_key)
            self.assertTrue(
                any(
                    "cannot claim multiple independence domains" in item
                    for item in validate_trust_policy(
                        conflicting_domains,
                        as_of=dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
                    )
                )
            )

            cross_policy = copy.deepcopy(trust_policy)
            cross_auth = cross_policy["keys"][2]["authorizations"][0]
            cross_auth["evidenceTypes"].append("qualification")
            cross_auth["subjectRefs"].append("operator-02")
            cross_auth["covers"].append("refund_operator_qualification")
            cross_payload = {
                "apiVersion": "delegation-resilience.org/v0alpha2",
                "kind": "HumanDrillEvidence",
                "scenarioRef": "refund-facilitated-human-takeover",
                "environmentRef": "refund-sandbox-01",
                "evidenceType": "qualification",
                "subjectRefs": ["operator-02"],
                "objectRef": "refund-facilitated-human-takeover",
                "finding": "satisfied",
                "covers": ["refund_operator_qualification"],
                "issuer": {"id": "operator-01", "type": "human"},
                "observedAt": "2026-08-02T00:00:00Z",
                "validUntil": "2026-11-01T00:00:00Z",
                "assurance": "digest_bound",
            }
            cross_envelope = create_dsse_envelope(
                cross_payload,
                payload_type=(
                    "application/vnd.delegation-resilience.human-evidence.v0alpha2+json"
                ),
                key_id=key_records[2]["keyId"],
                private_key=seeds[2],
            )
            _, cross_errors = verify_dsse_envelope(
                canonical_json_bytes(cross_envelope),
                trust_policy=cross_policy,
                purpose="human_evidence",
                as_of=dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
            )
            self.assertTrue(
                any("non-participant-statement" in item for item in cross_errors)
            )

            insufficient_independence = copy.deepcopy(trust_policy)
            insufficient_independence["humanEvidenceRules"][
                "minimumIndependenceDomains"
            ] = 3
            rejected_independence = evaluate_readiness(
                self.profile,
                trusted_manifest,
                evidence_root=evidence_root,
                as_of=dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
                trust_policy=insufficient_independence,
                min_policy_sequence=1,
            )
            self.assertFalse(rejected_independence["ready"])
            self.assertTrue(
                any(
                    "required independence domains" in item
                    for item in rejected_independence["missingPrerequisites"]
                )
            )

            revoked_policy = copy.deepcopy(trust_policy)
            revoked_policy["keys"][0].update(
                {
                    "status": "revoked",
                    "revokedAt": "2026-08-02T00:30:00Z",
                    "revocationReason": "test revocation",
                }
            )
            rejected_revocation = evaluate_readiness(
                self.profile,
                trusted_manifest,
                evidence_root=evidence_root,
                as_of=dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
                trust_policy=revoked_policy,
                min_policy_sequence=1,
            )
            self.assertFalse(rejected_revocation["ready"])
            self.assertTrue(
                any(
                    "TRUST_KEY_REVOKED" in item
                    for item in rejected_revocation["missingPrerequisites"]
                )
            )

            reused_artifact = copy.deepcopy(manifest)
            shared_artifact = reused_artifact["participants"][0][
                "qualificationEvidence"
            ]
            for participant in reused_artifact["participants"]:
                participant["qualificationEvidence"] = shared_artifact
            for item in reused_artifact["authorityVerifications"]:
                item["evidence"] = shared_artifact
            for item in reused_artifact["operationalAccessVerifications"]:
                item["evidence"] = shared_artifact
            reused_artifact["operatorChannelIndependenceEvidence"][0]["evidence"] = (
                shared_artifact
            )
            reused_artifact["participantSafeguardEvidence"][0]["evidence"] = (
                shared_artifact
            )
            for item in reused_artifact["participantAcknowledgements"]:
                item["evidence"] = shared_artifact
            for item in reused_artifact["withdrawalStatusEvidence"]:
                item["evidence"] = shared_artifact
            rejected_reuse = evaluate_readiness(
                self.profile,
                reused_artifact,
                evidence_root=evidence_root,
                as_of=dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
            )
            self.assertFalse(rejected_reuse["ready"])
            self.assertTrue(
                any(
                    "evidenceType does not match" in item
                    or "subjectRefs do not match" in item
                    for item in rejected_reuse["missingPrerequisites"]
                )
            )

            invalid_qualification = copy.deepcopy(manifest)
            invalid_qualification["participants"][0]["qualificationEvidence"][
                "digest"
            ] = "sha256:" + "0" * 64
            rejected_qualification = evaluate_readiness(
                self.profile,
                invalid_qualification,
                evidence_root=evidence_root,
                as_of=dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
            )
            self.assertFalse(rejected_qualification["ready"])
            self.assertTrue(
                any(
                    "artifact byte digest does not match" in item
                    for item in rejected_qualification["missingPrerequisites"]
                )
            )

            string_boolean = copy.deepcopy(manifest)
            string_boolean["controls"]["faultInjectionApproved"] = "false"
            string_boolean["participants"][0]["simulated"] = "false"
            rejected = evaluate_readiness(
                self.profile,
                string_boolean,
                evidence_root=evidence_root,
                as_of=dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
            )
            self.assertFalse(rejected["ready"])
            self.assertTrue(
                any(
                    "participants.0.simulated" in item
                    for item in rejected["missingPrerequisites"]
                )
            )
            self.assertTrue(
                any(
                    "faultInjectionApproved" in item
                    for item in rejected["missingPrerequisites"]
                )
            )

    def test_fabricated_or_escaping_evidence_is_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["participants"] = [
            {
                "participantId": "operator-01",
                "simulated": False,
                "qualificationEvidence": {
                    "uri": "../operator-01-qualification",
                    "digest": "sha256:" + "0" * 64,
                },
            },
            {
                "participantId": "operator-02",
                "simulated": False,
                "qualificationEvidence": {
                    "uri": "../operator-02-qualification",
                    "digest": "sha256:" + "0" * 64,
                },
            },
        ]
        manifest["authorityVerifications"] = [
            {
                "participantRef": participant,
                "evidence": {"uri": "../outside", "digest": "sha256:" + "0" * 64},
            }
            for participant in ["operator-01", "operator-02"]
        ]
        with tempfile.TemporaryDirectory() as directory:
            report = evaluate_readiness(
                self.profile, manifest, evidence_root=pathlib.Path(directory)
            )
        self.assertFalse(report["ready"])
        self.assertTrue(
            any("authority evidence" in item for item in report["missingPrerequisites"])
        )

    def test_unknown_manifest_fields_fail_closed(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["totallyUnknownKey"] = True
        report = evaluate_readiness(self.profile, manifest)
        self.assertFalse(report["ready"])
        self.assertTrue(
            any(
                "Additional properties are not allowed" in item
                for item in report["missingPrerequisites"]
            )
        )

    def test_v0alpha1_preflight_remains_parseable_but_cannot_enter_trusted_flow(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["apiVersion"] = "delegation-resilience.org/v0alpha1"
        manifest.pop("participantAcknowledgements")
        manifest.pop("withdrawalStatusEvidence")
        report = evaluate_readiness(self.profile, manifest)
        self.assertFalse(report["ready"])
        self.assertTrue(
            any(
                "v0alpha1 preflight cannot contain v0alpha2 fields" in item
                for item in report["missingPrerequisites"]
            )
        )

    def test_withdrawal_is_representable_and_blocks_active_status(self):
        evidence = {
            "apiVersion": "delegation-resilience.org/v0alpha2",
            "kind": "HumanDrillEvidence",
            "scenarioRef": "refund-facilitated-human-takeover",
            "environmentRef": "refund-sandbox-01",
            "evidenceType": "withdrawal_status",
            "subjectRefs": ["operator-01"],
            "objectRef": "refund-facilitated-human-takeover",
            "finding": "withdrawn",
            "participantStatus": "withdrawn",
            "statementSequence": 2,
            "preflightRunId": "refund-human-run-0001",
            "challenge": "challenge-refund-human-run-0001",
            "profileDigest": "sha256:" + "1" * 64,
            "preflightContextDigest": "sha256:" + "2" * 64,
            "briefingArtifactDigest": "sha256:" + "3" * 64,
            "covers": ["active_participation"],
            "issuer": {"id": "operator-01", "type": "human"},
            "observedAt": "2026-08-02T00:00:00Z",
            "validUntil": "2026-11-01T00:00:00Z",
            "assurance": "digest_bound",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            content = canonical_json_bytes(evidence)
            (root / "withdrawal.json").write_bytes(content)
            errors = validate_human_evidence(
                {"uri": "withdrawal.json", "digest": byte_digest(content)},
                base_dir=root,
                artifact_root=root,
                scenario_ref=evidence["scenarioRef"],
                environment_ref=evidence["environmentRef"],
                evidence_type="withdrawal_status",
                subject_refs={"operator-01"},
                object_refs={evidence["objectRef"]},
                covers={"active_participation"},
                as_of=dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
                expected_finding="satisfied",
                participant_status="active",
            )
        self.assertTrue(any("finding does not match" in item for item in errors))
        self.assertTrue(
            any("participantStatus does not match" in item for item in errors)
        )


if __name__ == "__main__":
    unittest.main()
