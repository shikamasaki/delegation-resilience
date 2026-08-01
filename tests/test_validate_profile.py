import copy
import datetime as dt
import importlib.util
import pathlib
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
        self.assertTrue(any("must use deploymentDisposition PROHIBITED" in error for error in errors))

    def test_unreferenced_constitutional_constraint_is_rejected(self):
        changed = copy.deepcopy(self.profile)
        changed["spec"]["recoveryClaims"][0]["constraintRefs"] = ["no-self-approval"]
        errors = MODULE.validate_profile(changed)
        self.assertTrue(any("retain-review-and-remedy" in error for error in errors))

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
        errors = MODULE.validate_attestation(
            self.profile,
            attestation,
            dt.datetime(2026, 8, 2, tzinfo=dt.timezone.utc),
        )
        self.assertTrue(any("cannot demonstrate human_takeover" in error for error in errors))

    def test_stale_attestation_is_rejected(self):
        attestation = self._attestation()
        attestation["validUntil"] = "2026-08-01T00:00:00Z"
        errors = MODULE.validate_attestation(
            self.profile,
            attestation,
            dt.datetime(2026, 8, 2, tzinfo=dt.timezone.utc),
        )
        self.assertTrue(any("stale" in error for error in errors))

    def test_tabletop_cannot_demonstrate_operational_claim(self):
        attestation = self._attestation()
        attestation["exerciseMode"] = "tabletop"
        attestation["scenarioRef"] = "refund-facilitated-human-takeover"
        attestation["claimResults"][0]["result"] = "demonstrated"
        errors = MODULE.validate_attestation(
            self.profile,
            attestation,
            dt.datetime(2026, 8, 2, tzinfo=dt.timezone.utc),
        )
        self.assertTrue(any("tabletop" in error for error in errors))

    def test_claim_outside_scenario_scope_is_rejected(self):
        changed = copy.deepcopy(self.profile)
        second_claim = copy.deepcopy(changed["spec"]["recoveryClaims"][0])
        second_claim["claimId"] = "different-recovery-claim"
        changed["spec"]["recoveryClaims"].append(second_claim)
        attestation = self._attestation()
        attestation["claimResults"][0]["claimRef"] = "different-recovery-claim"
        errors = MODULE.validate_attestation(
            changed,
            attestation,
            dt.datetime(2026, 8, 2, tzinfo=dt.timezone.utc),
        )
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
        self._assert_duplicate(
            attestation, "actualConditions.faultSchedule.faultId"
        )

    def test_duplicate_component_id_is_rejected(self):
        attestation = self._attestation()
        attestation["systemUnderTest"]["components"].append(
            copy.deepcopy(attestation["systemUnderTest"]["components"][0])
        )
        self._assert_duplicate(
            attestation, "systemUnderTest.components.componentId"
        )

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
        errors = MODULE.validate_attestation(
            self.profile,
            attestation,
            dt.datetime(2026, 8, 2, tzinfo=dt.timezone.utc),
        )
        self.assertEqual([], errors)

    def _assert_duplicate(self, attestation, label):
        errors = MODULE.validate_attestation(
            self.profile,
            attestation,
            dt.datetime(2026, 8, 2, tzinfo=dt.timezone.utc),
        )
        self.assertTrue(any(f"duplicate {label}" in error for error in errors))

    def _attestation(self):
        return {
            "scenarioRef": "refund-response-loss-after-commit",
            "exerciseMode": "deterministic_simulation",
            "startedAt": "2026-08-02T00:00:00Z",
            "completedAt": "2026-08-02T00:10:00Z",
            "issuedAt": "2026-08-02T00:11:00Z",
            "validUntil": "2026-10-01T00:00:00Z",
            "humanParticipation": {
                "mode": "none",
                "participantCount": 0,
                "authorityVerified": False,
                "operationalAccessVerified": False,
            },
            "claimResults": [
                {
                    "claimRef": "refund-provider-outage",
                    "result": "not_demonstrated",
                    "demonstratedCapabilities": ["external_reconciliation"],
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
                }
            ],
            "systemUnderTest": {
                "components": [
                    {"componentId": "refund-runner"}
                ]
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
