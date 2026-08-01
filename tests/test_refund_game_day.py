import datetime as dt
import json
import pathlib
import tempfile
import unittest

import yaml

from game_days.refund.runner import (
    build_artifacts,
    byte_digest,
    canonical_digest,
    run_experiment,
    verify_artifacts,
    write_artifacts,
)
from tools.validate_profile import validate_attestation

ROOT = pathlib.Path(__file__).resolve().parents[1]


class RefundGameDayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "examples" / "refund" / "profile.yaml").open() as handle:
            cls.profile = yaml.safe_load(handle)

    def test_response_loss_comparison_exposes_external_effect_gap(self):
        result = run_experiment(self.profile)
        variants = {item["variant"]: item for item in result["variants"]}
        profile_aware = variants["profile_aware"]["summary"]
        baseline = variants["conventional_retry"]["summary"]

        self.assertEqual(105, result["conditions"]["totalIntentCount"])
        self.assertEqual(10, result["conditions"]["responseLossCount"])
        self.assertEqual(0, profile_aware["duplicateRefundCount"])
        self.assertEqual(10, profile_aware["responseLostEffectCount"])
        self.assertEqual(10, profile_aware["reconciledUnknownCount"])
        self.assertEqual(10, baseline["duplicateRefundCount"])
        self.assertEqual(10, baseline["responseLostEffectCount"])
        self.assertEqual(
            0, profile_aware["unrecognizedExternalEffectCountAtCompletion"]
        )
        self.assertEqual(10, baseline["unrecognizedExternalEffectCountAtCompletion"])
        self.assertTrue(all(gap["detected"] for gap in result["materialGaps"]))

    def test_fault_selection_and_artifacts_are_reproducible(self):
        first = build_artifacts(self.profile)
        second = build_artifacts(self.profile)
        self.assertEqual(first, second)
        report = json.loads(first["run-report.json"])
        self.assertEqual(
            [
                "refund-intent-0006",
                "refund-intent-0014",
                "refund-intent-0048",
                "refund-intent-0051",
                "refund-intent-0058",
                "refund-intent-0063",
                "refund-intent-0064",
                "refund-intent-0071",
                "refund-intent-0079",
                "refund-intent-0084",
            ],
            report["faultedIntentIds"],
        )

    def test_artifact_verification_rejects_corruption(self):
        artifacts = build_artifacts(self.profile)
        with tempfile.TemporaryDirectory() as directory:
            output_dir = pathlib.Path(directory)
            write_artifacts(output_dir, artifacts)
            (output_dir / "run-report.json").write_text("corrupted\n")
            errors = verify_artifacts(output_dir, artifacts)
        self.assertTrue(any("run-report.json" in error for error in errors))

    def test_profile_digest_uses_canonical_key_order(self):
        self.assertEqual(
            canonical_digest({"b": 2, "a": 1}),
            canonical_digest({"a": 1, "b": 2}),
        )

    def test_generated_attestation_does_not_overclaim(self):
        artifacts = build_artifacts(self.profile)
        attestation = yaml.safe_load(artifacts["attestation.yaml"])
        result = attestation["claimResults"][0]

        self.assertEqual("not_demonstrated", result["result"])
        self.assertEqual(
            ["external_reconciliation"], result["demonstratedCapabilities"]
        )
        self.assertEqual(
            ["external_reconciliation"],
            [item["capability"] for item in result["capabilityEvidence"]],
        )
        self.assertEqual(
            canonical_digest(self.profile),
            attestation["evaluatedProfile"]["digest"],
        )
        for observation in attestation["evidence"]:
            uri = observation["artifact"]["uri"]
            self.assertEqual(
                byte_digest(artifacts[uri]), observation["artifact"]["digest"]
            )
        runner_digest = byte_digest(
            (ROOT / "game_days" / "refund" / "runner.py").read_bytes()
        )
        for component in attestation["systemUnderTest"]["components"]:
            self.assertEqual(runner_digest, component["artifact"]["digest"])
        self.assertEqual("none", attestation["humanParticipation"]["mode"])
        self.assertEqual(
            [],
            validate_attestation(
                self.profile,
                attestation,
                dt.datetime(2026, 8, 3, tzinfo=dt.timezone.utc),
                artifact_base=ROOT / "examples" / "refund" / "game-day",
                artifact_root=ROOT,
            ),
        )

    def test_baseline_contract_is_explicit(self):
        result = run_experiment(self.profile)
        baseline = next(
            item
            for item in result["variants"]
            if item["variant"] == "conventional_retry"
        )
        self.assertEqual(
            "execution_attempt", baseline["contract"]["idempotencyKeyScope"]
        )
        self.assertEqual(
            "retry_on_timeout_without_reconciliation",
            baseline["contract"]["retryPolicy"],
        )


if __name__ == "__main__":
    unittest.main()
