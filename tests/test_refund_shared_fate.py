import copy
import datetime as dt
import pathlib
import tempfile
import unittest

import yaml

from game_days.refund.runner import byte_digest, canonical_digest
from game_days.refund.shared_fate import (
    build_artifacts,
    derive_claim_result,
    propagate_failure,
    run_experiment,
    validate_topology,
    verify_artifacts,
    write_artifacts,
)
from tools.validate_profile import validate_attestation

ROOT = pathlib.Path(__file__).resolve().parents[1]


class RefundSharedFateTest(unittest.TestCase):
    def setUp(self):
        with (ROOT / "examples" / "refund" / "profile.yaml").open() as handle:
            self.profile = yaml.safe_load(handle)

    def test_shared_fate_disqualifies_declared_fallback(self):
        result = run_experiment(self.profile)
        dependency = result["dependencyAnalysis"]
        observations = result["observations"]

        self.assertTrue(dependency["sharedFateDetected"])
        self.assertTrue(dependency["fallbackDefined"])
        self.assertEqual(0, dependency["independentFallbackCount"])
        self.assertFalse(dependency["fallbackIndependentByTopology"])
        self.assertFalse(observations["authorizationAvailable"])
        self.assertFalse(observations["executionAvailable"])
        self.assertFalse(observations["externalOutcomeProbeAvailable"])
        self.assertFalse(observations["operatorChannelAvailable"])
        self.assertEqual(0, observations["financialCommitsDuringFault"])
        self.assertEqual(0, observations["unauthorizedCommits"])
        self.assertFalse(observations["commitGuardHaltedOnMissingAuthority"])
        self.assertIn(
            "NO_EXECUTION_PATH_AVAILABLE",
            {item["event"] for item in observations["controlFlowEvents"]},
        )
        self.assertEqual("not_demonstrated", result["claimResult"])
        self.assertEqual([], result["demonstratedCapabilities"])
        self.assertTrue(all(gap["detected"] for gap in result["materialGaps"]))

    def test_failure_propagation_is_transitive(self):
        topology = [
            {"componentId": "root", "role": "other", "dependencyRefs": []},
            {"componentId": "middle", "role": "other", "dependencyRefs": ["root"]},
            {
                "componentId": "fallback",
                "role": "fallback_execution",
                "dependencyRefs": ["middle"],
            },
        ]
        self.assertEqual(
            {"root", "middle", "fallback"},
            propagate_failure(topology, {"root"}),
        )

    def test_independent_fallback_is_not_falsely_disqualified(self):
        changed = copy.deepcopy(self.profile)
        scenario = next(
            item
            for item in changed["spec"]["exerciseScenarios"]
            if item["scenarioId"] == "refund-shared-idp-outage"
        )
        fallback = next(
            item
            for item in scenario["executionPlan"]["dependencyTopology"]
            if item["role"] == "fallback_execution"
        )
        fallback["dependencyRefs"] = []

        result = run_experiment(changed)
        dependency = result["dependencyAnalysis"]
        self.assertEqual(1, dependency["independentFallbackCount"])
        self.assertTrue(dependency["fallbackIndependentByTopology"])
        self.assertTrue(dependency["sharedFateDetected"])
        self.assertEqual("not_demonstrated", result["claimResult"])

    def test_partial_critical_role_collapse_is_still_shared_fate(self):
        changed = copy.deepcopy(self.profile)
        scenario = next(
            item
            for item in changed["spec"]["exerciseScenarios"]
            if item["scenarioId"] == "refund-shared-idp-outage"
        )
        operator_channel = next(
            item
            for item in scenario["executionPlan"]["dependencyTopology"]
            if item["role"] == "human_handover"
        )
        operator_channel["dependencyRefs"] = []

        result = run_experiment(changed)
        self.assertTrue(result["dependencyAnalysis"]["sharedFateDetected"])
        self.assertIn(
            "primary_execution",
            result["dependencyAnalysis"]["sharedFateGroups"][0][
                "affectedCriticalRoles"
            ],
        )
        fallback_gap = next(
            item
            for item in result["materialGaps"]
            if item["gapId"] == "fallback-shares-control-plane-idp"
        )
        self.assertTrue(fallback_gap["detected"])

    def test_no_shared_critical_dependency_reports_no_shared_fate(self):
        changed = copy.deepcopy(self.profile)
        scenario = next(
            item
            for item in changed["spec"]["exerciseScenarios"]
            if item["scenarioId"] == "refund-shared-idp-outage"
        )
        for component in scenario["executionPlan"]["dependencyTopology"]:
            if component["role"] in {
                "primary_execution",
                "fallback_execution",
                "authorization",
                "external_outcome",
                "human_handover",
            }:
                component["dependencyRefs"] = []
        result = run_experiment(changed)
        self.assertFalse(result["dependencyAnalysis"]["sharedFateDetected"])
        self.assertEqual([], result["dependencyAnalysis"]["sharedFateGroups"])

    def test_guard_bypass_makes_failed_result_reachable(self):
        changed = copy.deepcopy(self.profile)
        scenario = next(
            item
            for item in changed["spec"]["exerciseScenarios"]
            if item["scenarioId"] == "refund-shared-idp-outage"
        )
        fallback = next(
            item
            for item in scenario["executionPlan"]["dependencyTopology"]
            if item["role"] == "fallback_execution"
        )
        fallback["dependencyRefs"] = []
        guard_mode = next(
            item
            for item in scenario["executionPlan"]["parameters"]
            if item["name"] == "authorization_guard_mode"
        )
        guard_mode["value"] = "bypass_on_unavailable"

        result = run_experiment(changed)
        self.assertEqual(1, result["observations"]["unauthorizedCommits"])
        self.assertEqual("failed", result["claimResult"])

    def test_authorized_commit_is_not_mislabeled_as_containment(self):
        changed = copy.deepcopy(self.profile)
        scenario = next(
            item
            for item in changed["spec"]["exerciseScenarios"]
            if item["scenarioId"] == "refund-shared-idp-outage"
        )
        for component in scenario["executionPlan"]["dependencyTopology"]:
            if component["role"] in {"fallback_execution", "authorization"}:
                component["dependencyRefs"] = []

        result = run_experiment(changed)
        self.assertEqual(1, result["observations"]["financialCommitsDuringFault"])
        self.assertEqual(0, result["observations"]["unauthorizedCommits"])
        self.assertEqual([], result["demonstratedCapabilities"])
        self.assertEqual("not_demonstrated", result["claimResult"])

    def test_invalid_topology_fails_closed(self):
        topology = [
            {
                "componentId": "fallback",
                "role": "fallback_execution",
                "dependencyRefs": ["missing"],
            }
        ]
        self.assertTrue(validate_topology(topology))
        with self.assertRaises(ValueError):
            propagate_failure(topology, {"missing"})

        duplicate = [
            {
                "componentId": "root",
                "role": "other",
                "dependencyRefs": [],
            },
            {
                "componentId": "fallback",
                "role": "fallback_execution",
                "dependencyRefs": ["root", "root"],
            },
        ]
        self.assertTrue(
            any(
                "duplicate dependencyRefs" in error
                for error in validate_topology(duplicate)
            )
        )

    def test_cycle_and_missing_critical_role_fail_closed(self):
        cyclic = [
            {"componentId": "a", "role": "primary_execution", "dependencyRefs": ["b"]},
            {"componentId": "b", "role": "fallback_execution", "dependencyRefs": ["a"]},
        ]
        self.assertTrue(any("cycle" in error for error in validate_topology(cyclic)))
        with self.assertRaises(ValueError):
            propagate_failure(cyclic, {"a"})

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
        with self.assertRaises(ValueError):
            run_experiment(changed)

    def test_claim_derivation_cannot_ignore_missing_capabilities(self):
        required = {"containment", "handover", "mission_recovery"}
        self.assertEqual(
            "not_demonstrated",
            derive_claim_result(required, {"containment"}, safety_violation=False),
        )
        self.assertEqual(
            "failed",
            derive_claim_result(required, required, safety_violation=True),
        )
        self.assertEqual(
            "not_demonstrated",
            derive_claim_result(required, required, safety_violation=False),
        )

    def test_artifacts_are_reproducible_and_semantically_valid(self):
        artifacts = build_artifacts(self.profile)
        attestation = yaml.safe_load(artifacts["attestation.yaml"])
        self.assertEqual(
            canonical_digest(self.profile),
            attestation["evaluatedProfile"]["digest"],
        )
        self.assertEqual("not_demonstrated", attestation["claimResults"][0]["result"])
        self.assertEqual([], attestation["claimResults"][0]["capabilityEvidence"])
        self.assertEqual("none", attestation["humanParticipation"]["mode"])
        measurements = {
            item["measurementId"]: item for item in attestation["measurements"]
        }
        self.assertTrue(measurements["backlog-tolerance-exceeded"]["value"])
        self.assertIn(
            "backlog-tolerance-exceeded",
            attestation["claimResults"][0]["measurementRefs"],
        )
        self.assertEqual(
            [],
            validate_attestation(
                self.profile,
                attestation,
                dt.datetime(2026, 8, 3, tzinfo=dt.timezone.utc),
                artifact_base=(
                    ROOT / "examples" / "refund" / "game-day" / "shared-fate"
                ),
                artifact_root=ROOT,
            ),
        )
        evidence = artifacts["evidence/shared-fate-observations.json"]
        for observation in attestation["evidence"]:
            self.assertEqual(byte_digest(evidence), observation["artifact"]["digest"])
        runner_digest = byte_digest(
            (ROOT / "game_days" / "refund" / "shared_fate.py").read_bytes()
        )
        components = {
            item["componentId"]: item
            for item in attestation["systemUnderTest"]["components"]
        }
        self.assertEqual(
            runner_digest,
            components["refund-shared-fate-runner"]["artifact"]["digest"],
        )
        self.assertEqual(
            byte_digest((ROOT / "game_days" / "refund" / "runner.py").read_bytes()),
            components["refund-digest-utility"]["artifact"]["digest"],
        )

        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory)
            write_artifacts(output, artifacts)
            self.assertEqual([], verify_artifacts(output, artifacts))
            report = output / "run-report.json"
            report.write_text("tampered\n", encoding="utf-8")
            self.assertTrue(verify_artifacts(output, artifacts))

    def test_negative_observations_cannot_demonstrate_the_claim(self):
        attestation = yaml.safe_load(build_artifacts(self.profile)["attestation.yaml"])
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
        errors = validate_attestation(
            self.profile,
            attestation,
            dt.datetime(2026, 8, 3, tzinfo=dt.timezone.utc),
            artifact_base=(ROOT / "examples" / "refund" / "game-day" / "shared-fate"),
            artifact_root=ROOT,
        )
        self.assertTrue(
            any("without satisfied evidence observations" in error for error in errors)
        )

    def test_missing_topology_prevents_artifact_generation(self):
        changed = copy.deepcopy(self.profile)
        scenario = next(
            item
            for item in changed["spec"]["exerciseScenarios"]
            if item["scenarioId"] == "refund-shared-idp-outage"
        )
        scenario["executionPlan"]["dependencyTopology"] = []
        with self.assertRaises(ValueError):
            build_artifacts(changed)


if __name__ == "__main__":
    unittest.main()
