"""Verifier-side checks that do not import or execute exercise generators."""

from __future__ import annotations

import datetime as dt
import hashlib
from collections import Counter
from typing import Any

try:
    from tools.trust import VerifiedStatement
except ModuleNotFoundError:
    from trust import VerifiedStatement


def _scenario(profile: dict[str, Any], scenario_ref: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in profile.get("spec", {}).get("exerciseScenarios", [])
            if item.get("scenarioId") == scenario_ref
        ),
        None,
    )


def _response_loss_expected_payload(
    profile: dict[str, Any], scenario_ref: str
) -> tuple[dict[str, Any] | None, list[str]]:
    """Reconstruct the complete deterministic witness without importing the runner."""
    scenario = _scenario(profile, scenario_ref)
    if scenario is None:
        return None, ["portable response-loss scenario is absent from the profile"]
    if scenario.get("exerciseMode") != "deterministic_simulation":
        return None, ["portable response-loss scenario is not deterministic_simulation"]
    try:
        parameters = {
            item["name"]: item["value"]
            for item in scenario["executionPlan"]["parameters"]
        }
        initial_backlog = int(parameters["initial_backlog"])
        arrival_rate = int(parameters["arrival_rate"])
        duration_hours = int(parameters["simulation_duration"])
        response_loss_count = int(parameters["response_loss_count"])
        random_seed = str(scenario["executionPlan"]["randomSeed"])
    except (KeyError, TypeError, ValueError):
        return None, ["portable response-loss scenario parameters are invalid"]
    total = initial_backlog + arrival_rate * duration_hours
    if initial_backlog < 0 or arrival_rate < 0 or duration_hours < 0 or total < 1:
        return None, ["portable response-loss workload is invalid"]
    if response_loss_count < 1 or response_loss_count > total:
        return None, ["portable response-loss count is outside the workload"]

    intent_ids = [f"refund-intent-{index + 1:04d}" for index in range(total)]
    ranked = sorted(
        intent_ids,
        key=lambda intent_id: hashlib.sha256(
            f"{random_seed}:{intent_id}".encode("utf-8")
        ).digest(),
    )
    faulted = set(ranked[:response_loss_count])
    events: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []
    for index, intent_id in enumerate(intent_ids):
        effect_id = f"refund-effect-{index + 1:04d}"
        effects.append(
            {
                "effectId": effect_id,
                "intentId": intent_id,
                "amountJpy": 1000 + (index % 10) * 100,
                "idempotencyKey": intent_id,
            }
        )
        if intent_id in faulted:
            events.extend(
                [
                    {"intentId": intent_id, "event": "OUTCOME_UNKNOWN"},
                    {
                        "intentId": intent_id,
                        "event": "CONFIRMED_SUCCEEDED_FROM_RECONCILIATION",
                        "effectId": effect_id,
                    },
                ]
            )
        else:
            events.append(
                {
                    "intentId": intent_id,
                    "event": "CONFIRMED_SUCCEEDED_FROM_RESPONSE",
                }
            )
    return (
        {
            "variant": "profile_aware",
            "contract": {
                "timeoutSemantics": "OUTCOME_UNKNOWN",
                "idempotencyKeyScope": "logical_intent",
                "retryPolicy": "reconcile_before_retry",
            },
            "summary": {
                "intentCount": total,
                "externalEffectCount": total,
                "duplicateRefundCount": 0,
                "responseLostEffectCount": response_loss_count,
                "unknownOutcomeCount": response_loss_count,
                "reconciledUnknownCount": response_loss_count,
                "unrecognizedExternalEffectCountAtCompletion": 0,
                "maxUnknownDurationSteps": 1,
            },
            "events": events,
            "providerEffects": effects,
        },
        [],
    )


def _verify_response_loss_context(
    profile: dict[str, Any], attestation: dict[str, Any]
) -> list[str]:
    scenario_ref = str(attestation.get("scenarioRef", ""))
    scenario = _scenario(profile, scenario_ref)
    if scenario is None:
        return ["portable response-loss context has no profile scenario"]
    parameters = {
        item.get("name"): item.get("value")
        for item in scenario.get("executionPlan", {}).get("parameters", [])
    }
    try:
        total = int(parameters["initial_backlog"]) + int(
            parameters["arrival_rate"]
        ) * int(parameters["simulation_duration"])
        expected_workload = [
            {
                "measurementId": "workload-initial-backlog",
                "metric": "initial_backlog",
                "value": int(parameters["initial_backlog"]),
                "unit": "requests",
            },
            {
                "measurementId": "workload-arrival-rate",
                "metric": "arrival_rate",
                "value": int(parameters["arrival_rate"]),
                "unit": "requests_per_hour",
            },
            {
                "measurementId": "workload-total-intents",
                "metric": "total_intent_count",
                "value": total,
                "unit": "requests",
            },
            {
                "measurementId": "workload-response-losses",
                "metric": "response_loss_count",
                "value": int(parameters["response_loss_count"]),
                "unit": "attempts",
            },
        ]
    except (KeyError, TypeError, ValueError):
        return ["portable response-loss context parameters are invalid"]
    conditions = attestation.get("actualConditions", {})
    errors: list[str] = []
    if conditions.get("randomSeed") != scenario.get("executionPlan", {}).get(
        "randomSeed"
    ):
        errors.append("portable response-loss actualConditions.randomSeed mismatch")
    if conditions.get("workload") != expected_workload:
        errors.append("portable response-loss actualConditions.workload mismatch")
    if conditions.get("sharedDependencies") != scenario.get("executionPlan", {}).get(
        "sharedDependencies", []
    ):
        errors.append(
            "portable response-loss actualConditions.sharedDependencies mismatch"
        )
    injects = scenario.get("injects", [])
    schedule = conditions.get("faultSchedule", [])
    if not isinstance(schedule, list) or len(schedule) != len(injects):
        errors.append("portable response-loss fault schedule count mismatch")
        return errors
    started = _parse_time(attestation.get("startedAt"))
    completed = _parse_time(attestation.get("completedAt"))
    for index, (fault, inject) in enumerate(zip(schedule, injects, strict=True)):
        if not isinstance(fault, dict):
            errors.append(f"portable response-loss faultSchedule[{index}] is invalid")
            continue
        if fault.get("target") != inject.get("target"):
            errors.append(
                f"portable response-loss faultSchedule[{index}].target mismatch"
            )
        if fault.get("faultId") != scenario.get("metadata", {}).get("id"):
            errors.append(
                f"portable response-loss faultSchedule[{index}].faultId mismatch"
            )
        fault_started = _parse_time(fault.get("startedAt"))
        fault_completed = _parse_time(fault.get("completedAt"))
        if (
            fault_started is None
            or fault_completed is None
            or fault_completed < fault_started
            or (inject.get("duration") == "0s" and fault_completed != fault_started)
            or (started is not None and fault_started < started)
            or (completed is not None and fault_completed > completed)
        ):
            errors.append(
                f"portable response-loss faultSchedule[{index}] timing mismatch"
            )
    return errors


def _parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def verify_portable_capabilities(
    profile: dict[str, Any],
    attestation: dict[str, Any],
    verified_artifacts: dict[str, VerifiedStatement],
) -> tuple[dict[str, set[str]], list[str]]:
    """Return only capabilities supported by a recognized, complete portable check."""
    scenario_ref = str(attestation.get("scenarioRef", ""))
    if scenario_ref != "refund-response-loss-after-commit":
        return {}, []
    scenario = _scenario(profile, scenario_ref)
    claim_refs = set((scenario or {}).get("claimRefs", []))
    if len(claim_refs) != 1:
        return {}, [
            "portable response-loss check requires exactly one scenario claimRef"
        ]
    claim_ref = next(iter(claim_refs))
    candidates: list[dict[str, Any]] = []
    for observation in attestation.get("evidence", []):
        if observation.get("evidenceRequirementRef") != "refund-provider-outcome":
            continue
        digest = observation.get("artifact", {}).get("digest")
        statement = verified_artifacts.get(str(digest))
        if (
            statement
            and statement.purpose == "exercise_evidence"
            and statement.payload.get("kind") == "ExerciseEvidence"
            and statement.payload.get("payload", {}).get("variant") == "profile_aware"
        ):
            candidates.append(statement.payload)
    if len(candidates) != 1:
        return {}, [
            "portable response-loss check requires exactly one trusted profile-aware evidence artifact"
        ]
    payload = candidates[0]["payload"]
    events = payload.get("events")
    effects = payload.get("providerEffects")
    summary = payload.get("summary")
    if (
        not isinstance(events, list)
        or not isinstance(effects, list)
        or not isinstance(summary, dict)
    ):
        return {}, ["portable response-loss evidence payload is incomplete"]
    if any(not isinstance(item, dict) for item in [*events, *effects]):
        return {}, ["portable response-loss events and effects must be objects"]

    unknown = [
        item.get("intentId")
        for item in events
        if item.get("event") == "OUTCOME_UNKNOWN"
    ]
    reconciled = [
        item.get("intentId")
        for item in events
        if item.get("event") == "CONFIRMED_SUCCEEDED_FROM_RECONCILIATION"
    ]
    responses = {
        item.get("intentId")
        for item in events
        if item.get("event") == "CONFIRMED_SUCCEEDED_FROM_RESPONSE"
    }
    effect_counts = Counter(item.get("intentId") for item in effects)
    recognized = responses | set(reconciled)
    recomputed = {
        "responseLostEffectCount": len(unknown),
        "reconciledUnknownCount": len(reconciled),
        "duplicateRefundCount": sum(
            max(0, count - 1) for count in effect_counts.values()
        ),
        "unrecognizedExternalEffectCountAtCompletion": sum(
            count for intent, count in effect_counts.items() if intent not in recognized
        ),
        "externalEffectCount": len(effects),
        "intentCount": len(effect_counts),
    }
    errors: list[str] = []
    if len(unknown) != len(set(unknown)):
        errors.append("portable response-loss evidence repeats an UNKNOWN intent")
    if Counter(unknown) != Counter(reconciled):
        errors.append(
            "portable response-loss evidence does not reconcile every UNKNOWN exactly once"
        )
    if any(item.get("effectId") is None for item in effects):
        errors.append(
            "portable response-loss evidence contains an effect without effectId"
        )
    effect_ids = [item.get("effectId") for item in effects]
    if len(effect_ids) != len(set(effect_ids)):
        errors.append("portable response-loss evidence contains duplicate effectId")
    for key, value in recomputed.items():
        if summary.get(key) != value:
            errors.append(f"portable response-loss summary mismatch for {key}")
    if recomputed["responseLostEffectCount"] < 1:
        errors.append("portable response-loss evidence did not exercise response loss")
    if recomputed["duplicateRefundCount"] != 0:
        errors.append("portable response-loss evidence contains duplicate refunds")
    if recomputed["unrecognizedExternalEffectCountAtCompletion"] != 0:
        errors.append("portable response-loss evidence leaves effects unrecognized")

    measurement_values = {
        item.get("measurementId"): item.get("value")
        for item in attestation.get("measurements", [])
    }
    expected_measurements = {
        "profile-aware-response-lost-effects": recomputed["responseLostEffectCount"],
        "profile-aware-duplicate-refunds": recomputed["duplicateRefundCount"],
        "profile-aware-reconciled-unknowns": recomputed["reconciledUnknownCount"],
        "profile-aware-unrecognized-effects-at-completion": recomputed[
            "unrecognizedExternalEffectCountAtCompletion"
        ],
    }
    for measurement_id, expected in expected_measurements.items():
        if (
            measurement_id in measurement_values
            and measurement_values[measurement_id] != expected
        ):
            errors.append(
                f"portable response-loss attestation measurement mismatch: {measurement_id}"
            )
    result = next(
        (
            item
            for item in attestation.get("claimResults", [])
            if item.get("claimRef") == claim_ref
        ),
        None,
    )
    binding = next(
        (
            item
            for item in (result or {}).get("capabilityEvidence", [])
            if item.get("capability") == "external_reconciliation"
        ),
        None,
    )
    required_refs = {
        "profile-aware-response-lost-effects",
        "profile-aware-duplicate-refunds",
        "profile-aware-reconciled-unknowns",
    }
    if binding is None or not required_refs <= set(binding.get("measurementRefs", [])):
        errors.append(
            "external_reconciliation is not bound to the portable measurements"
        )
    expected_payload, expected_errors = _response_loss_expected_payload(
        profile, scenario_ref
    )
    errors.extend(expected_errors)
    errors.extend(_verify_response_loss_context(profile, attestation))
    if expected_payload is not None and payload != expected_payload:
        errors.append(
            "portable response-loss evidence does not exactly match the independently reconstructed deterministic witness"
        )
    if errors:
        return {}, errors
    return {claim_ref: {"external_reconciliation"}}, []


def dependency_freshness(
    profile: dict[str, Any], snapshot: dict[str, Any], *, as_of: dt.datetime
) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    if not isinstance(snapshot, dict):
        return {}, ["dependency snapshot must be an object"]
    try:
        observed_raw = snapshot["observedAt"]
        valid_until_raw = snapshot["validUntil"]
        if not isinstance(observed_raw, str) or not isinstance(valid_until_raw, str):
            raise ValueError
        observed = dt.datetime.fromisoformat(observed_raw.replace("Z", "+00:00"))
        valid_until = dt.datetime.fromisoformat(valid_until_raw.replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return {}, ["dependency snapshot timestamps are invalid"]
    if observed.tzinfo is None or valid_until.tzinfo is None or as_of.tzinfo is None:
        return {}, ["dependency snapshot timestamps must be timezone-aware"]
    if observed > as_of:
        errors.append("dependency snapshot observation is in the future")
    if valid_until <= as_of:
        errors.append("dependency snapshot is stale")
    dependencies = snapshot.get("dependencies")
    if not isinstance(dependencies, list) or not all(
        isinstance(item, dict) for item in dependencies
    ):
        return {}, [*errors, "dependency snapshot dependencies must be objects"]
    entries = [
        (item.get("type"), item.get("id"), item.get("observedVersion"))
        for item in dependencies
    ]
    if len(entries) != len({(a, b) for a, b, _ in entries}):
        errors.append("dependency snapshot contains duplicate type/id")
    declared = {
        (item.get("type"), item.get("id"))
        for claim in profile.get("spec", {}).get("recoveryClaims", [])
        for item in claim.get("assuranceDependencies", [])
    }
    observed_keys = {(a, b) for a, b, _ in entries}
    if observed_keys - declared:
        errors.append("dependency snapshot contains undeclared dependencies")
    current = {(a, b): version for a, b, version in entries}
    results: dict[str, str] = {}
    for claim in profile.get("spec", {}).get("recoveryClaims", []):
        freshness = "CURRENT_RELATIVE_TO_SNAPSHOT"
        for dependency in claim.get("assuranceDependencies", []):
            actual = current.get((dependency.get("type"), dependency.get("id")))
            if actual == dependency.get("observedVersion"):
                continue
            if dependency.get("invalidationPolicy") == "any_change":
                freshness = "STALE"
                break
            if freshness != "STALE":
                freshness = "REVIEW_REQUIRED"
        results[str(claim.get("claimId"))] = freshness
    return results, errors
