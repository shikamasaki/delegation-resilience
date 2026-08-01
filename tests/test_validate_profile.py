import copy
import datetime as dt
import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_profile", ROOT / "tools" / "validate_profile.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ProfileSemanticValidationTest(unittest.TestCase):
    def setUp(self):
        with (ROOT / "examples" / "refund" / "profile.yaml").open() as handle:
            self.profile = yaml.safe_load(handle)

    def test_reference_profile_is_valid(self):
        self.assertEqual([], MODULE.validate_profile(self.profile))

    def test_missing_action_reference_is_rejected(self):
        changed = copy.deepcopy(self.profile)
        changed["spec"]["recoveryClaims"][0]["actionRefs"].append("missing_action")
        errors = MODULE.validate_profile(changed)
        self.assertTrue(any("missing_action" in error for error in errors))

    def test_asserted_permitted_claim_is_rejected(self):
        changed = copy.deepcopy(self.profile)
        changed["spec"]["recoveryClaims"][0]["deploymentDisposition"] = "PERMITTED"
        errors = MODULE.validate_profile(changed)
        self.assertTrue(
            any(
                "must use deploymentDisposition PROHIBITED" in error for error in errors
            )
        )

    def test_unreferenced_constitutional_constraint_is_rejected(self):
        changed = copy.deepcopy(self.profile)
        changed["spec"]["recoveryClaims"][0]["constraintRefs"] = ["no-self-approval"]
        errors = MODULE.validate_profile(changed)
        self.assertTrue(any("retain-review-and-remedy" in error for error in errors))

    def test_missing_dependency_topology_reference_is_rejected(self):
        changed = copy.deepcopy(self.profile)
        scenario = next(
            item
            for item in changed["spec"]["exerciseScenarios"]
            if item["scenarioId"] == "refund-shared-idp-outage"
        )
        scenario["executionPlan"]["dependencyTopology"][0]["dependencyRefs"].append(
            "missing-control-plane"
        )
        errors = MODULE.validate_profile(changed)
        self.assertTrue(any("missing-control-plane" in error for error in errors))

    def test_optional_topology_keeps_label_style_dependency_semantics(self):
        changed = copy.deepcopy(self.profile)
        scenario = next(
            item
            for item in changed["spec"]["exerciseScenarios"]
            if item["scenarioId"] == "refund-shared-idp-outage"
        )
        del scenario["executionPlan"]["dependencyAnalysisRequired"]
        scenario["executionPlan"]["sharedDependencies"] = ["informational-label"]
        scenario["injects"][0]["target"] = "external-fault-label"
        self.assertEqual([], MODULE.validate_profile(changed))

    def test_duplicate_dependency_reference_is_rejected(self):
        changed = copy.deepcopy(self.profile)
        scenario = next(
            item
            for item in changed["spec"]["exerciseScenarios"]
            if item["scenarioId"] == "refund-shared-idp-outage"
        )
        component = scenario["executionPlan"]["dependencyTopology"][0]
        component["dependencyRefs"].append(component["dependencyRefs"][0])
        errors = MODULE.validate_profile(changed)
        self.assertTrue(any("duplicate dependencyRef" in error for error in errors))

    def test_duplicate_dependency_component_is_rejected(self):
        changed = copy.deepcopy(self.profile)
        scenario = next(
            item
            for item in changed["spec"]["exerciseScenarios"]
            if item["scenarioId"] == "refund-shared-idp-outage"
        )
        scenario["executionPlan"]["dependencyTopology"].append(
            copy.deepcopy(scenario["executionPlan"]["dependencyTopology"][0])
        )
        errors = MODULE.validate_profile(changed)
        self.assertTrue(
            any("duplicate dependency componentId" in error for error in errors)
        )

    def test_required_dependency_topology_cannot_be_omitted(self):
        changed = copy.deepcopy(self.profile)
        scenario = next(
            item
            for item in changed["spec"]["exerciseScenarios"]
            if item["scenarioId"] == "refund-shared-idp-outage"
        )
        del scenario["executionPlan"]["dependencyTopology"]
        errors = MODULE.validate_profile(changed)
        self.assertTrue(
            any("requires a dependency topology" in error for error in errors)
        )

    def test_dependency_cycle_and_self_reference_are_rejected(self):
        changed = copy.deepcopy(self.profile)
        scenario = next(
            item
            for item in changed["spec"]["exerciseScenarios"]
            if item["scenarioId"] == "refund-shared-idp-outage"
        )
        topology = scenario["executionPlan"]["dependencyTopology"]
        shared_idp = next(
            item
            for item in topology
            if item["componentId"] == "shared-control-plane-idp"
        )
        shared_idp["dependencyRefs"] = ["shared-control-plane-idp"]
        errors = MODULE.validate_profile(changed)
        self.assertTrue(any("depends on itself" in error for error in errors))
        self.assertTrue(any("dependency cycle" in error for error in errors))

    def test_required_dependency_role_cannot_be_omitted(self):
        changed = copy.deepcopy(self.profile)
        scenario = next(
            item
            for item in changed["spec"]["exerciseScenarios"]
            if item["scenarioId"] == "refund-shared-idp-outage"
        )
        scenario["executionPlan"]["dependencyTopology"] = [
            item
            for item in scenario["executionPlan"]["dependencyTopology"]
            if item["role"] != "human_handover"
        ]
        errors = MODULE.validate_profile(changed)
        self.assertTrue(
            any("missing required role: human_handover" in error for error in errors)
        )

    def test_human_evidence_bindings_are_semantically_bound(self):
        changed = copy.deepcopy(self.profile)
        scenario = next(
            item
            for item in changed["spec"]["exerciseScenarios"]
            if item["scenarioId"] == "refund-facilitated-human-takeover"
        )
        bindings = scenario["executionPlan"]["humanEvidenceBindings"]
        bindings["qualification"]["objectRef"] = "another-scenario"
        bindings["authority"]["objectRef"] = "missing-action"
        errors = MODULE.validate_profile(changed)
        self.assertTrue(any("qualification.objectRef" in error for error in errors))
        self.assertTrue(any("missing-action" in error for error in errors))

    def test_deterministic_run_cannot_demonstrate_human_takeover(self):
        attestation = self._attestation()
        attestation["claimResults"][0]["result"] = "demonstrated"
        attestation["claimResults"][0]["demonstratedCapabilities"] = [
            "containment",
            "handover",
            "mission_recovery",
            "revalidation",
            "external_reconciliation",
            "human_takeover",
        ]
        errors = self._validate(attestation)
        self.assertTrue(
            any(
                "cannot be demonstrated by deterministic_simulation" in error
                for error in errors
            )
        )

    def test_human_takeover_requires_declared_operator_count(self):
        attestation = self._attestation()
        attestation["scenarioRef"] = "refund-facilitated-human-takeover"
        attestation["exerciseMode"] = "sandbox"
        attestation["humanParticipation"] = {
            "mode": "facilitated",
            "participantCount": 1,
            "roles": ["refund-operator"],
            "participants": [
                {
                    "participantId": "operator-01",
                    "role": "refund-operator",
                    "simulated": False,
                    "qualified": True,
                }
            ],
            "authorityVerified": True,
            "authorityEvidence": [{"participantRef": "operator-01"}],
            "operationalAccessVerified": True,
            "operationalAccessEvidence": [{"participantRef": "operator-01"}],
        }
        result = attestation["claimResults"][0]
        result["result"] = "demonstrated"
        result["demonstratedCapabilities"] = [
            "containment",
            "handover",
            "mission_recovery",
            "revalidation",
            "external_reconciliation",
            "human_takeover",
        ]
        result["evidenceRequirementRefs"] = [
            "authorization-decision",
            "refund-provider-outcome",
            "human-handover",
        ]
        attestation["evidence"].extend(
            [
                {
                    "evidenceObservationId": "authorization-observation",
                    "evidenceRequirementRef": "authorization-decision",
                    "finding": "satisfied",
                },
                {
                    "evidenceObservationId": "handover-observation",
                    "evidenceRequirementRef": "human-handover",
                    "finding": "satisfied",
                },
            ]
        )
        errors = self._validate(attestation)
        self.assertTrue(
            any("at least 2 participating humans" in error for error in errors)
        )

    def test_handover_capability_also_requires_real_human_evidence(self):
        attestation = self._attestation()
        attestation["scenarioRef"] = "refund-facilitated-human-takeover"
        attestation["exerciseMode"] = "sandbox"
        attestation["claimResults"][0]["demonstratedCapabilities"] = ["handover"]
        errors = self._validate(attestation)
        self.assertTrue(
            any("facilitated or live human participation" in error for error in errors)
        )

    def test_aggregate_human_booleans_without_participants_are_rejected(self):
        attestation = self._attestation()
        attestation["scenarioRef"] = "refund-facilitated-human-takeover"
        attestation["exerciseMode"] = "sandbox"
        attestation["humanParticipation"].update(
            {
                "mode": "facilitated",
                "participantCount": 2,
                "authorityVerified": True,
                "operationalAccessVerified": True,
            }
        )
        attestation["claimResults"][0]["demonstratedCapabilities"] = ["handover"]
        errors = self._validate(attestation)
        self.assertTrue(
            any("does not match the participant list" in error for error in errors)
        )

    def test_structured_human_artifacts_are_verified_and_forgery_is_rejected(self):
        attestation = self._attestation()
        attestation["scenarioRef"] = "refund-facilitated-human-takeover"
        attestation["exerciseMode"] = "sandbox"
        attestation["systemUnderTest"]["environment"] = "refund-sandbox-01"

        with tempfile.TemporaryDirectory() as directory:
            artifact_root = pathlib.Path(directory)

            def artifact(name, content):
                path = artifact_root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                return {
                    "uri": name,
                    "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
                }

            def human_artifact(name, evidence_type, subject, object_ref, covers):
                envelope = {
                    "apiVersion": "delegation-resilience.org/v0alpha1",
                    "kind": "HumanDrillEvidence",
                    "scenarioRef": "refund-facilitated-human-takeover",
                    "environmentRef": "refund-sandbox-01",
                    "evidenceType": evidence_type,
                    "subjectRefs": [subject],
                    "objectRef": object_ref,
                    "finding": "satisfied",
                    "covers": covers,
                    "issuer": {"id": "test-issuer", "type": "service"},
                    "observedAt": "2026-08-01T00:00:00Z",
                    "validUntil": "2026-11-01T00:00:00Z",
                    "assurance": "digest_bound",
                }
                return artifact(
                    name,
                    (json.dumps(envelope, sort_keys=True) + "\n").encode(),
                )

            def exercise_artifact(name):
                envelope = {
                    "apiVersion": "delegation-resilience.org/v0alpha1",
                    "kind": "ExerciseEvidence",
                    "scenarioRef": "refund-facilitated-human-takeover",
                    "environmentRef": "refund-sandbox-01",
                    "issuer": {"id": "synthetic-test-runner", "type": "workload"},
                    "observedAt": "2026-08-02T00:05:00Z",
                    "validUntil": "2026-11-01T00:00:00Z",
                    "assurance": "digest_bound",
                    "assertions": [
                        {
                            "evidenceRequirementRef": "human-handover",
                            "finding": "satisfied",
                        }
                    ],
                    "payload": {"handover": True},
                }
                return artifact(
                    name,
                    (json.dumps(envelope, sort_keys=True) + "\n").encode(),
                )

            participants = []
            authority_evidence = []
            access_evidence = []
            for participant_id in ["operator-01", "operator-02"]:
                participants.append(
                    {
                        "participantId": participant_id,
                        "role": "refund-operator",
                        "simulated": False,
                        "qualified": True,
                        "qualificationEvidence": human_artifact(
                            f"{participant_id}-qualification.json",
                            "qualification",
                            participant_id,
                            "refund-facilitated-human-takeover",
                            ["refund_operator_qualification"],
                        ),
                    }
                )
                authority_evidence.append(
                    {
                        "participantRef": participant_id,
                        "artifact": human_artifact(
                            f"{participant_id}-authority.json",
                            "authority",
                            participant_id,
                            "execute_refund",
                            ["sandbox_refund_authority"],
                        ),
                    }
                )
                access_evidence.append(
                    {
                        "participantRef": participant_id,
                        "artifact": human_artifact(
                            f"{participant_id}-access.json",
                            "operational_access",
                            participant_id,
                            "refund-sandbox-console",
                            ["sandbox_operational_access"],
                        ),
                    }
                )
            attestation["humanParticipation"] = {
                "mode": "facilitated",
                "participantCount": 2,
                "roles": ["refund-operator"],
                "participants": participants,
                "authorityVerified": True,
                "authorityEvidence": authority_evidence,
                "operationalAccessVerified": True,
                "operationalAccessEvidence": access_evidence,
            }
            result = attestation["claimResults"][0]
            result["demonstratedCapabilities"] = ["handover"]
            result["capabilityEvidence"] = [
                {
                    "capability": "handover",
                    "measurementRefs": ["unknown-duration"],
                    "evidenceRequirementRefs": ["human-handover"],
                }
            ]
            result["evidenceRequirementRefs"] = ["human-handover"]
            attestation["evidence"] = [
                {
                    "evidenceObservationId": "human-handover-observation",
                    "evidenceRequirementRef": "human-handover",
                    "finding": "satisfied",
                    "artifact": exercise_artifact("handover.json"),
                    "observedAt": "2026-08-02T00:05:00Z",
                }
            ]
            errors = MODULE.validate_attestation(
                self.profile,
                attestation,
                dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
                artifact_base=artifact_root,
                artifact_root=artifact_root,
            )
            self.assertEqual(1, len(errors))
            self.assertIn("trusted issuer signature verification", errors[0])

            forged = copy.deepcopy(attestation)
            forged["humanParticipation"]["participants"][0]["qualificationEvidence"][
                "digest"
            ] = "sha256:" + "0" * 64
            errors = MODULE.validate_attestation(
                self.profile,
                forged,
                dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
                artifact_base=artifact_root,
                artifact_root=artifact_root,
            )
            self.assertTrue(
                any("artifact byte digest does not match" in error for error in errors)
            )

    def test_arbitrary_digest_bound_bytes_cannot_satisfy_exercise_evidence(self):
        attestation = self._attestation()
        result = attestation["claimResults"][0]
        result["demonstratedCapabilities"] = ["external_reconciliation"]
        result["capabilityEvidence"] = [
            {
                "capability": "external_reconciliation",
                "measurementRefs": ["unknown-duration"],
                "evidenceRequirementRefs": ["refund-provider-outcome"],
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = pathlib.Path(directory)
            content = b'{"observed":true}\n'
            artifact_path = artifact_root / "arbitrary.json"
            artifact_path.write_bytes(content)
            attestation["evidence"][0]["artifact"] = {
                "uri": "arbitrary.json",
                "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
            }
            errors = MODULE.validate_attestation(
                self.profile,
                attestation,
                dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
                artifact_base=artifact_root,
                artifact_root=artifact_root,
            )
        self.assertTrue(any("exercise evidence schema" in error for error in errors))
        self.assertTrue(
            any("without satisfied evidence observations" in error for error in errors)
        )

    def test_self_authored_typed_evidence_cannot_promote_technical_capability(self):
        attestation = self._attestation()
        result = attestation["claimResults"][0]
        result["demonstratedCapabilities"] = ["external_reconciliation"]
        result["capabilityEvidence"] = [
            {
                "capability": "external_reconciliation",
                "measurementRefs": ["unknown-duration"],
                "evidenceRequirementRefs": ["refund-provider-outcome"],
            }
        ]
        errors = self._validate(attestation)
        self.assertTrue(
            any(
                "lacks byte-identical deterministic replay evidence" in error
                for error in errors
            )
        )

    def test_capability_evidence_must_match_demonstrated_capabilities(self):
        attestation = self._attestation()
        attestation["claimResults"][0]["demonstratedCapabilities"] = [
            "mission_recovery"
        ]
        errors = self._validate(attestation)
        self.assertTrue(
            any(
                "demonstratedCapabilities and capabilityEvidence differ" in error
                for error in errors
            )
        )

    def test_replayed_evidence_cannot_be_substituted_for_another_capability(self):
        attestation = self._attestation()
        result = attestation["claimResults"][0]
        result["demonstratedCapabilities"] = ["mission_recovery"]
        result["capabilityEvidence"] = [
            {
                "capability": "mission_recovery",
                "measurementRefs": ["unknown-duration"],
                "evidenceRequirementRefs": ["refund-provider-outcome"],
            }
        ]
        errors = self._validate(attestation)
        self.assertTrue(
            any(
                "not supported by the deterministic replay verdict" in error
                for error in errors
            )
        )

    def test_exercise_evidence_rejects_duplicate_requirement_assertions(self):
        attestation = self._attestation()
        source = (
            ROOT / "tests" / "fixtures" / "valid" / "evidence" / "semantic-test.json"
        )
        envelope = json.loads(source.read_text())
        envelope["assertions"].append(
            {
                "evidenceRequirementRef": "refund-provider-outcome",
                "finding": "contradicted",
            }
        )
        content = (json.dumps(envelope, sort_keys=True) + "\n").encode()
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = pathlib.Path(directory)
            artifact_path = artifact_root / "ambiguous.json"
            artifact_path.write_bytes(content)
            attestation["evidence"][0]["artifact"] = {
                "uri": "ambiguous.json",
                "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
            }
            errors = MODULE.validate_attestation(
                self.profile,
                attestation,
                dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
                artifact_base=artifact_root,
                artifact_root=artifact_root,
            )
        self.assertTrue(
            any("duplicate requirement assertions" in error for error in errors)
        )

    def test_satisfied_observation_requires_byte_verified_artifact(self):
        attestation = self._attestation()
        attestation["evidence"][0]["artifact"]["digest"] = "sha256:" + "0" * 64
        errors = self._validate(attestation)
        self.assertTrue(
            any("artifact byte digest does not match" in error for error in errors)
        )

    def test_invalid_operator_count_fails_closed_without_crashing(self):
        for invalid_count in ["two", True, 2.9, 0, -1]:
            with self.subTest(invalid_count=invalid_count):
                changed = copy.deepcopy(self.profile)
                scenario = next(
                    item
                    for item in changed["spec"]["exerciseScenarios"]
                    if item["scenarioId"] == "refund-facilitated-human-takeover"
                )
                parameter = next(
                    item
                    for item in scenario["executionPlan"]["parameters"]
                    if item["name"] == "operator_count"
                )
                parameter["value"] = invalid_count
                attestation = self._attestation()
                attestation["scenarioRef"] = "refund-facilitated-human-takeover"
                attestation["exerciseMode"] = "sandbox"
                attestation["claimResults"][0]["demonstratedCapabilities"].append(
                    "human_takeover"
                )
                errors = self._validate(attestation, profile=changed)
                self.assertTrue(
                    any("not a positive integer" in error for error in errors)
                )

    def test_stale_attestation_is_rejected(self):
        attestation = self._attestation()
        attestation["validUntil"] = "2026-08-01T00:00:00Z"
        errors = self._validate(attestation)
        self.assertTrue(any("stale" in error for error in errors))

    def test_profile_digest_mismatch_is_rejected(self):
        attestation = self._attestation()
        attestation["evaluatedProfile"]["digest"] = "sha256:" + "0" * 64
        errors = self._validate(attestation)
        self.assertTrue(any("canonical profile digest" in error for error in errors))

    def test_tabletop_cannot_demonstrate_operational_claim(self):
        attestation = self._attestation()
        attestation["exerciseMode"] = "tabletop"
        attestation["scenarioRef"] = "refund-facilitated-human-takeover"
        attestation["claimResults"][0]["result"] = "demonstrated"
        errors = self._validate(attestation)
        self.assertTrue(any("tabletop" in error for error in errors))

    def test_claim_outside_scenario_scope_is_rejected(self):
        changed = copy.deepcopy(self.profile)
        second_claim = copy.deepcopy(changed["spec"]["recoveryClaims"][0])
        second_claim["claimId"] = "different-recovery-claim"
        changed["spec"]["recoveryClaims"].append(second_claim)
        attestation = self._attestation()
        attestation["claimResults"][0]["claimRef"] = "different-recovery-claim"
        errors = self._validate(attestation, profile=changed)
        self.assertTrue(any("is not covered by scenario" in error for error in errors))

    def test_duplicate_claim_result_is_rejected(self):
        attestation = self._attestation()
        attestation["claimResults"].append(
            copy.deepcopy(attestation["claimResults"][0])
        )
        self._assert_duplicate(attestation, "claimResults.claimRef")

    def test_duplicate_measurement_id_is_rejected(self):
        attestation = self._attestation()
        attestation["measurements"].append(
            copy.deepcopy(attestation["measurements"][0])
        )
        self._assert_duplicate(attestation, "measurements.measurementId")

    def test_duplicate_fault_id_is_rejected(self):
        attestation = self._attestation()
        attestation["actualConditions"]["faultSchedule"].append(
            copy.deepcopy(attestation["actualConditions"]["faultSchedule"][0])
        )
        self._assert_duplicate(attestation, "actualConditions.faultSchedule.faultId")

    def test_duplicate_component_id_is_rejected(self):
        attestation = self._attestation()
        attestation["systemUnderTest"]["components"].append(
            copy.deepcopy(attestation["systemUnderTest"]["components"][0])
        )
        self._assert_duplicate(attestation, "systemUnderTest.components.componentId")

    def test_duplicate_evidence_observation_id_is_rejected(self):
        attestation = self._attestation()
        attestation["evidence"].append(copy.deepcopy(attestation["evidence"][0]))
        self._assert_duplicate(attestation, "evidence.evidenceObservationId")

    def test_same_evidence_requirement_allows_distinct_observations(self):
        attestation = self._attestation()
        second_observation = copy.deepcopy(attestation["evidence"][0])
        second_observation["evidenceObservationId"] = (
            "refund-provider-outcome-observation-002"
        )
        attestation["evidence"].append(second_observation)
        errors = self._validate(attestation)
        self.assertEqual([], errors)

    def test_mixed_evidence_findings_cannot_demonstrate_claim(self):
        attestation = self._attestation()
        attestation["claimResults"][0]["result"] = "demonstrated"
        attestation["claimResults"][0]["demonstratedCapabilities"] = [
            "containment",
            "handover",
            "mission_recovery",
            "revalidation",
            "external_reconciliation",
            "human_takeover",
        ]
        contradictory = copy.deepcopy(attestation["evidence"][0])
        contradictory["evidenceObservationId"] = (
            "refund-provider-outcome-observation-contradicted"
        )
        contradictory["finding"] = "contradicted"
        attestation["evidence"].append(contradictory)
        errors = self._validate(attestation)
        self.assertTrue(
            any("unresolved adverse observations" in error for error in errors)
        )

    def _assert_duplicate(self, attestation, label):
        errors = self._validate(attestation)
        self.assertTrue(any(f"duplicate {label}" in error for error in errors))

    def _validate(self, attestation, *, profile=None):
        artifact_base = ROOT / "tests" / "fixtures" / "valid"
        return MODULE.validate_attestation(
            profile or self.profile,
            attestation,
            dt.datetime(2026, 8, 2, 1, tzinfo=dt.timezone.utc),
            artifact_base=artifact_base,
            artifact_root=ROOT,
        )

    def _attestation(self):
        return {
            "evaluatedProfile": {
                "uri": "../profile.yaml",
                "digest": MODULE.canonical_digest(self.profile),
            },
            "scenarioRef": "refund-response-loss-after-commit",
            "issuer": {"id": "synthetic-test-runner", "type": "workload"},
            "exerciseMode": "deterministic_simulation",
            "startedAt": "2026-08-02T00:00:00Z",
            "completedAt": "2026-08-02T00:10:00Z",
            "issuedAt": "2026-08-02T00:11:00Z",
            "validUntil": "2026-10-01T00:00:00Z",
            "humanParticipation": {
                "mode": "none",
                "participantCount": 0,
                "roles": [],
                "participants": [],
                "authorityVerified": False,
                "authorityEvidence": [],
                "operationalAccessVerified": False,
                "operationalAccessEvidence": [],
            },
            "claimResults": [
                {
                    "claimRef": "refund-provider-outage",
                    "result": "not_demonstrated",
                    "demonstratedCapabilities": [],
                    "capabilityEvidence": [],
                    "measurementRefs": ["unknown-duration"],
                    "evidenceRequirementRefs": ["refund-provider-outcome"],
                }
            ],
            "measurements": [
                {
                    "measurementId": "unknown-duration",
                    "metric": "unknown_duration",
                    "value": 3,
                    "unit": "seconds",
                }
            ],
            "evidence": [
                {
                    "evidenceObservationId": "refund-provider-outcome-observation-001",
                    "evidenceRequirementRef": "refund-provider-outcome",
                    "finding": "satisfied",
                    "artifact": {
                        "uri": "evidence/semantic-test.json",
                        "digest": (
                            "sha256:f858eabe0b2bf2ba76377697404a6285491c4dee5"
                            "01e036bf6ce6650bc7247c4"
                        ),
                    },
                    "observedAt": "2026-08-02T00:02:00Z",
                }
            ],
            "systemUnderTest": {
                "environment": "synthetic-test-fixture",
                "components": [{"componentId": "refund-runner"}],
            },
            "actualConditions": {
                "faultSchedule": [
                    {
                        "faultId": "drop-response",
                        "startedAt": "2026-08-02T00:01:00Z",
                        "completedAt": "2026-08-02T00:01:00Z",
                    }
                ]
            },
        }


if __name__ == "__main__":
    unittest.main()
