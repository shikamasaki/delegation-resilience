#!/usr/bin/env python3
"""Run the deterministic refund response-loss comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

import rfc8785
import yaml


SCENARIO_ID = "refund-response-loss-after-commit"
STARTED_AT = "2026-08-02T00:00:00Z"
FAULT_AT = "2026-08-02T00:01:00Z"
COMPLETED_AT = "2026-08-02T01:00:00Z"
ISSUED_AT = "2026-08-02T01:01:00Z"
VALID_UNTIL = "2026-11-01T00:00:00Z"


class ResponseLost(RuntimeError):
    """The provider committed the effect but the caller lost the response."""


@dataclass(frozen=True)
class RefundIntent:
    intent_id: str
    amount_jpy: int


class FakeRefundProvider:
    """Authoritative provider with native idempotency and outcome lookup."""

    def __init__(self) -> None:
        self._by_key: dict[str, dict[str, Any]] = {}
        self._effects: list[dict[str, Any]] = []

    def commit(
        self, intent: RefundIntent, idempotency_key: str, lose_response: bool
    ) -> dict[str, Any]:
        effect = self._by_key.get(idempotency_key)
        if effect is None:
            effect = {
                "effectId": f"refund-effect-{len(self._effects) + 1:04d}",
                "intentId": intent.intent_id,
                "amountJpy": intent.amount_jpy,
                "idempotencyKey": idempotency_key,
            }
            self._by_key[idempotency_key] = effect
            self._effects.append(effect)
        if lose_response:
            raise ResponseLost(intent.intent_id)
        return effect

    def lookup_by_intent(self, intent_id: str) -> list[dict[str, Any]]:
        return [effect for effect in self._effects if effect["intentId"] == intent_id]

    @property
    def effects(self) -> list[dict[str, Any]]:
        return list(self._effects)


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def byte_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _scenario(profile: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    scenarios = profile["spec"]["exerciseScenarios"]
    try:
        return next(item for item in scenarios if item["scenarioId"] == scenario_id)
    except StopIteration as exc:
        raise ValueError(f"scenario not found: {scenario_id}") from exc


def _parameters(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        item["name"]: item["value"]
        for item in scenario["executionPlan"]["parameters"]
    }


def build_workload(scenario: dict[str, Any]) -> list[RefundIntent]:
    parameters = _parameters(scenario)
    initial_backlog = int(parameters["initial_backlog"])
    arrival_rate = int(parameters["arrival_rate"])
    duration_hours = int(parameters["simulation_duration"])
    total = initial_backlog + arrival_rate * duration_hours
    return [
        RefundIntent(
            intent_id=f"refund-intent-{index + 1:04d}",
            amount_jpy=1000 + (index % 10) * 100,
        )
        for index in range(total)
    ]


def select_faulted_intents(
    workload: list[RefundIntent], count: int, seed: str
) -> set[str]:
    if count < 0 or count > len(workload):
        raise ValueError("response_loss_count must be within the workload size")
    ranked = sorted(
        workload,
        key=lambda intent: hashlib.sha256(
            f"{seed}:{intent.intent_id}".encode("utf-8")
        ).digest(),
    )
    return {intent.intent_id for intent in ranked[:count]}


def _duplicate_count(effects: list[dict[str, Any]]) -> int:
    counts: dict[str, int] = {}
    for effect in effects:
        intent_id = effect["intentId"]
        counts[intent_id] = counts.get(intent_id, 0) + 1
    return sum(max(0, count - 1) for count in counts.values())


def run_profile_aware(
    workload: list[RefundIntent], faulted_intents: set[str]
) -> dict[str, Any]:
    provider = FakeRefundProvider()
    events: list[dict[str, Any]] = []
    acknowledged_effects: set[str] = set()
    unknown_durations: list[int] = []

    for intent in workload:
        stable_key = intent.intent_id
        try:
            effect = provider.commit(
                intent,
                idempotency_key=stable_key,
                lose_response=intent.intent_id in faulted_intents,
            )
            acknowledged_effects.add(effect["effectId"])
            events.append(
                {
                    "intentId": intent.intent_id,
                    "event": "CONFIRMED_SUCCEEDED_FROM_RESPONSE",
                }
            )
        except ResponseLost:
            events.append(
                {"intentId": intent.intent_id, "event": "OUTCOME_UNKNOWN"}
            )
            observed = provider.lookup_by_intent(intent.intent_id)
            if len(observed) != 1:
                raise AssertionError("authoritative reconciliation was not singular")
            acknowledged_effects.add(observed[0]["effectId"])
            unknown_durations.append(1)
            events.append(
                {
                    "intentId": intent.intent_id,
                    "event": "CONFIRMED_SUCCEEDED_FROM_RECONCILIATION",
                    "effectId": observed[0]["effectId"],
                }
            )

    effects = provider.effects
    return {
        "variant": "profile_aware",
        "contract": {
            "timeoutSemantics": "OUTCOME_UNKNOWN",
            "idempotencyKeyScope": "logical_intent",
            "retryPolicy": "reconcile_before_retry",
        },
        "summary": {
            "intentCount": len(workload),
            "externalEffectCount": len(effects),
            "duplicateRefundCount": _duplicate_count(effects),
            "responseLossCount": len(faulted_intents),
            "unknownOutcomeCount": len(unknown_durations),
            "reconciledUnknownCount": len(unknown_durations),
            "unrecognizedExternalEffectCount": len(
                {effect["effectId"] for effect in effects} - acknowledged_effects
            ),
            "maxUnknownDurationSteps": max(unknown_durations, default=0),
        },
        "events": events,
        "providerEffects": effects,
    }


def run_conventional_retry(
    workload: list[RefundIntent], faulted_intents: set[str]
) -> dict[str, Any]:
    provider = FakeRefundProvider()
    events: list[dict[str, Any]] = []
    acknowledged_effects: set[str] = set()

    for intent in workload:
        attempt = 1
        try:
            effect = provider.commit(
                intent,
                idempotency_key=f"{intent.intent_id}:attempt:{attempt}",
                lose_response=intent.intent_id in faulted_intents,
            )
        except ResponseLost:
            events.append(
                {
                    "intentId": intent.intent_id,
                    "event": "TIMEOUT_INTERPRETED_AS_FAILURE",
                }
            )
            attempt += 1
            effect = provider.commit(
                intent,
                idempotency_key=f"{intent.intent_id}:attempt:{attempt}",
                lose_response=False,
            )
            events.append(
                {
                    "intentId": intent.intent_id,
                    "event": "RETRIED_WITH_NEW_ATTEMPT_KEY",
                }
            )
        acknowledged_effects.add(effect["effectId"])

    effects = provider.effects
    return {
        "variant": "conventional_retry",
        "contract": {
            "timeoutSemantics": "FAILED",
            "idempotencyKeyScope": "execution_attempt",
            "retryPolicy": "retry_on_timeout_without_reconciliation",
        },
        "summary": {
            "intentCount": len(workload),
            "externalEffectCount": len(effects),
            "duplicateRefundCount": _duplicate_count(effects),
            "responseLossCount": len(faulted_intents),
            "unknownOutcomeCount": 0,
            "reconciledUnknownCount": 0,
            "unrecognizedExternalEffectCount": len(
                {effect["effectId"] for effect in effects} - acknowledged_effects
            ),
            "maxUnknownDurationSteps": 0,
        },
        "events": events,
        "providerEffects": effects,
    }


def run_experiment(profile: dict[str, Any]) -> dict[str, Any]:
    scenario = _scenario(profile, SCENARIO_ID)
    parameters = _parameters(scenario)
    workload = build_workload(scenario)
    faulted = select_faulted_intents(
        workload,
        count=int(parameters["response_loss_count"]),
        seed=scenario["executionPlan"]["randomSeed"],
    )
    profile_aware = run_profile_aware(workload, faulted)
    baseline = run_conventional_retry(workload, faulted)

    duplicate_gap = (
        baseline["summary"]["duplicateRefundCount"]
        - profile_aware["summary"]["duplicateRefundCount"]
    )
    invisible_effect_gap = baseline["summary"]["unrecognizedExternalEffectCount"]
    return {
        "experiment": "refund-response-loss-game-day/v0alpha1",
        "scenarioRef": SCENARIO_ID,
        "randomSeed": scenario["executionPlan"]["randomSeed"],
        "faultedIntentIds": sorted(faulted),
        "conditions": {
            "initialBacklog": int(parameters["initial_backlog"]),
            "arrivalRatePerHour": int(parameters["arrival_rate"]),
            "simulationDurationHours": int(parameters["simulation_duration"]),
            "totalIntentCount": len(workload),
            "responseLossCount": len(faulted),
        },
        "variants": [profile_aware, baseline],
        "materialGaps": [
            {
                "gapId": "attempt-scoped-idempotency-after-ambiguous-commit",
                "detected": duplicate_gap > 0,
                "measurement": duplicate_gap,
                "unit": "duplicate_external_effects",
                "interpretation": (
                    "Retrying an ambiguous commit with a new attempt-scoped key "
                    "created externally visible duplicate refunds."
                ),
            },
            {
                "gapId": "application-log-external-outcome-divergence",
                "detected": invisible_effect_gap > 0,
                "measurement": invisible_effect_gap,
                "unit": "unrecognized_external_effects",
                "interpretation": (
                    "The conventional workflow acknowledged the retry while the "
                    "first committed effects remained absent from its internal outcome view."
                ),
            },
        ],
        "claimResult": "not_demonstrated",
        "demonstratedCapabilities": ["external_reconciliation"],
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def build_artifacts(profile: dict[str, Any]) -> dict[str, bytes]:
    experiment = run_experiment(profile)
    variants = {item["variant"]: item for item in experiment["variants"]}
    runner_source = pathlib.Path(__file__).read_bytes()
    profile_evidence = _json_bytes(variants["profile_aware"])
    baseline_evidence = _json_bytes(variants["conventional_retry"])

    profile_summary = variants["profile_aware"]["summary"]
    baseline_summary = variants["conventional_retry"]["summary"]
    run_report = {
        **{key: value for key, value in experiment.items() if key != "variants"},
        "variants": [
            {
                "variant": variant["variant"],
                "contract": variant["contract"],
                "summary": variant["summary"],
            }
            for variant in experiment["variants"]
        ],
    }
    attestation = {
        "apiVersion": "delegation-resilience.org/v0alpha1",
        "kind": "ExerciseAttestation",
        "metadata": {
            "id": "refund-response-loss-synthetic-run",
            "version": "0.1.0-alpha.1",
        },
        "evaluatedProfile": {
            "uri": "../profile.yaml",
            "digest": canonical_digest(profile),
        },
        "scenarioRef": SCENARIO_ID,
        "issuer": {"id": "refund-game-day-runner", "type": "workload"},
        "issuedAt": ISSUED_AT,
        "validUntil": VALID_UNTIL,
        "exerciseMode": "deterministic_simulation",
        "startedAt": STARTED_AT,
        "completedAt": COMPLETED_AT,
        "systemUnderTest": {
            "environment": "deterministic-in-memory-simulation",
            "components": [
                {
                    "componentId": "refund-game-day-runner",
                    "kind": "comparison-runner",
                    "version": "0.1.0-alpha.1",
                    "artifact": {
                        "uri": "../../../game_days/refund/runner.py",
                        "digest": byte_digest(runner_source),
                    },
                },
                {
                    "componentId": "fake-refund-provider",
                    "kind": "authoritative-outcome-simulator",
                    "version": "0.1.0-alpha.1",
                    "artifact": {
                        "uri": "../../../game_days/refund/runner.py",
                        "digest": byte_digest(runner_source),
                    },
                },
            ],
        },
        "actualConditions": {
            "randomSeed": experiment["randomSeed"],
            "faultSchedule": [
                {
                    "faultId": "response-loss-after-commit",
                    "target": "refund-connector",
                    "startedAt": FAULT_AT,
                    "completedAt": FAULT_AT,
                }
            ],
            "workload": [
                {
                    "measurementId": "workload-initial-backlog",
                    "metric": "initial_backlog",
                    "value": experiment["conditions"]["initialBacklog"],
                    "unit": "requests",
                },
                {
                    "measurementId": "workload-arrival-rate",
                    "metric": "arrival_rate",
                    "value": experiment["conditions"]["arrivalRatePerHour"],
                    "unit": "requests_per_hour",
                },
                {
                    "measurementId": "workload-total-intents",
                    "metric": "total_intent_count",
                    "value": experiment["conditions"]["totalIntentCount"],
                    "unit": "requests",
                },
                {
                    "measurementId": "workload-response-losses",
                    "metric": "response_loss_count",
                    "value": experiment["conditions"]["responseLossCount"],
                    "unit": "attempts",
                },
            ],
            "sharedDependencies": ["refund-provider-status-api"],
        },
        "humanParticipation": {
            "mode": "none",
            "participantCount": 0,
            "roles": [],
            "authorityVerified": False,
            "operationalAccessVerified": False,
            "observations": ["No human takeover capability was exercised."],
        },
        "claimResults": [
            {
                "claimRef": "refund-provider-outage",
                "result": "not_demonstrated",
                "demonstratedCapabilities": ["external_reconciliation"],
                "measurementRefs": [
                    "profile-aware-duplicate-refunds",
                    "profile-aware-reconciled-unknowns",
                    "baseline-duplicate-refunds",
                    "baseline-unrecognized-effects",
                ],
                "evidenceRequirementRefs": ["refund-provider-outcome"],
                "notes": (
                    "The synthetic run exercised external reconciliation only; "
                    "it did not exercise human takeover or 24-hour mission recovery."
                ),
            }
        ],
        "measurements": [
            {
                "measurementId": "profile-aware-duplicate-refunds",
                "metric": "duplicate_refund_count",
                "value": profile_summary["duplicateRefundCount"],
                "unit": "count",
                "method": "authoritative fake-provider effect count by intent",
            },
            {
                "measurementId": "profile-aware-reconciled-unknowns",
                "metric": "reconciled_unknown_count",
                "value": profile_summary["reconciledUnknownCount"],
                "unit": "count",
                "method": "authoritative lookup after response loss",
            },
            {
                "measurementId": "baseline-duplicate-refunds",
                "metric": "duplicate_refund_count",
                "value": baseline_summary["duplicateRefundCount"],
                "unit": "count",
                "method": "authoritative fake-provider effect count by intent",
            },
            {
                "measurementId": "baseline-unrecognized-effects",
                "metric": "unrecognized_external_effect_count",
                "value": baseline_summary["unrecognizedExternalEffectCount"],
                "unit": "count",
                "method": "provider effects absent from application acknowledgements",
            },
        ],
        "evidence": [
            {
                "evidenceObservationId": "profile-aware-provider-outcomes",
                "evidenceRequirementRef": "refund-provider-outcome",
                "artifact": {
                    "uri": "evidence/profile-aware-provider-outcomes.json",
                    "digest": byte_digest(profile_evidence),
                },
                "observedAt": COMPLETED_AT,
            },
            {
                "evidenceObservationId": "baseline-provider-outcomes",
                "evidenceRequirementRef": "refund-provider-outcome",
                "artifact": {
                    "uri": "evidence/baseline-provider-outcomes.json",
                    "digest": byte_digest(baseline_evidence),
                },
                "observedAt": COMPLETED_AT,
            },
        ],
        "evidenceGaps": [
            "No qualified human participated.",
            "The 15-minute handover and 24-hour mission recovery were not exercised.",
            "The provider, policy service, identity provider, and evidence sink were simulated.",
            "Only response loss after commit was injected.",
        ],
        "residualUncertainty": [
            "A real provider may implement idempotency and outcome lookup differently.",
            "The conventional baseline represents attempt-scoped idempotency, not every retry implementation.",
            "The simulation does not establish production workload or operator capacity.",
        ],
    }

    return {
        "run-report.json": _json_bytes(run_report),
        "evidence/profile-aware-provider-outcomes.json": profile_evidence,
        "evidence/baseline-provider-outcomes.json": baseline_evidence,
        "attestation.yaml": yaml.safe_dump(
            attestation, sort_keys=False, allow_unicode=True
        ).encode("utf-8"),
    }


def write_artifacts(output_dir: pathlib.Path, artifacts: dict[str, bytes]) -> None:
    for relative, content in artifacts.items():
        target = output_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def verify_artifacts(output_dir: pathlib.Path, artifacts: dict[str, bytes]) -> list[str]:
    errors: list[str] = []
    for relative, expected in artifacts.items():
        target = output_dir / relative
        if not target.exists():
            errors.append(f"missing generated artifact: {target}")
            continue
        actual = target.read_bytes()
        if actual != expected:
            errors.append(f"generated artifact is stale: {target}")
    return errors


def _load_profile(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        profile = yaml.safe_load(handle)
    if not isinstance(profile, dict):
        raise ValueError("profile must contain a mapping")
    return profile


def main() -> int:
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        type=pathlib.Path,
        default=repo_root / "examples" / "refund" / "profile.yaml",
    )
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=repo_root / "examples" / "refund" / "game-day",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    profile = _load_profile(args.profile)
    artifacts = build_artifacts(profile)
    if args.write:
        write_artifacts(args.output_dir, artifacts)
        print(f"wrote {len(artifacts)} artifacts to {args.output_dir}")
        return 0

    errors = verify_artifacts(args.output_dir, artifacts)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("ok -- refund game day artifacts are reproducible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
