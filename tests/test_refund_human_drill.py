import copy
import datetime as dt
import json
import pathlib
import tempfile
import unittest

import yaml

from game_days.refund.human_drill import evaluate_readiness
from game_days.refund.runner import byte_digest

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
        manifest["facilitatorId"] = "facilitator-01"
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

            def artifact(name, evidence_type, subject_refs, object_ref, covers):
                envelope = {
                    "apiVersion": "delegation-resilience.org/v0alpha1",
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
            manifest["controls"] = {key: True for key in manifest["controls"]}

            report = evaluate_readiness(
                self.profile,
                manifest,
                evidence_root=evidence_root,
                as_of=dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
            )
            self.assertFalse(report["ready"])
            self.assertTrue(report["digestBoundPrerequisitesComplete"])
            self.assertFalse(report["trustedIssuerVerificationImplemented"])
            self.assertTrue(
                any(
                    "trusted issuer signature verification" in item
                    for item in report["missingPrerequisites"]
                )
            )
            self.assertEqual(
                "not_demonstrated",
                report["claimResultCeilingBeforeCompletedDrill"],
            )
            self.assertFalse(report["humanTakeoverMayBeClaimed"])

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


if __name__ == "__main__":
    unittest.main()
