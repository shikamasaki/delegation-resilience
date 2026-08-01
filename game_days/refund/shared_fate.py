#!/usr/bin/env python3
"""Run the deterministic refund shared-fate dependency exercise."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

import yaml

from game_days.refund.runner import (
    byte_digest,
    canonical_digest,
    exercise_evidence_bytes,
)

SCENARIO_ID = "refund-shared-idp-outage"
STARTED_AT = "2026-08-02T02:00:00Z"
FAULT_STARTED_AT = "2026-08-02T02:01:00Z"
FAULT_COMPLETED_AT = "2026-08-02T06:01:00Z"
COMPLETED_AT = "2026-08-02T06:02:00Z"
ISSUED_AT = "2026-08-02T06:03:00Z"
VALID_UNTIL = "2026-11-01T00:00:00Z"

CRITICAL_ROLES = {
    "primary_execution",
    "fallback_execution",
    "authorization",
    "external_outcome",
    "human_handover",
}


def _dependency_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        if state.get(node) == 1:
            return stack[stack.index(node) :] + [node]
        if state.get(node) == 2:
            return None
        state[node] = 1
        stack.append(node)
        for dependency in graph.get(node, []):
            cycle = visit(dependency)
            if cycle:
                return cycle
        stack.pop()
        state[node] = 2
        return None

    for component_id in sorted(graph):
        cycle = visit(component_id)
        if cycle:
            return cycle
    return None


def _scenario(profile: dict[str, Any]) -> dict[str, Any]:
    try:
        return next(
            item
            for item in profile["spec"]["exerciseScenarios"]
            if item["scenarioId"] == SCENARIO_ID
        )
    except StopIteration as exc:
        raise ValueError(f"scenario not found: {SCENARIO_ID}") from exc


def _parameters(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        item["name"]: item["value"] for item in scenario["executionPlan"]["parameters"]
    }


def validate_topology(topology: list[dict[str, Any]]) -> list[str]:
    """Return structural errors that JSON Schema cannot express."""
    errors: list[str] = []
    if not topology:
        return ["dependency topology is empty"]
    component_ids = [item["componentId"] for item in topology]
    duplicates = sorted(
        component_id
        for component_id in set(component_ids)
        if component_ids.count(component_id) > 1
    )
    for duplicate in duplicates:
        errors.append(f"duplicate dependency componentId: {duplicate}")

    available = set(component_ids)
    for item in topology:
        if len(item["dependencyRefs"]) != len(set(item["dependencyRefs"])):
            errors.append(
                f"component[{item['componentId']}] has duplicate dependencyRefs"
            )
        for dependency in item["dependencyRefs"]:
            if dependency not in available:
                errors.append(
                    f"component[{item['componentId']}] references missing dependency: "
                    f"{dependency}"
                )
        if item["componentId"] in set(item["dependencyRefs"]):
            errors.append(f"component[{item['componentId']}] depends on itself")
    graph = {item["componentId"]: item["dependencyRefs"] for item in topology}
    cycle = _dependency_cycle(graph)
    if cycle:
        errors.append("dependency cycle: " + " -> ".join(cycle))
    return errors


def propagate_failure(
    topology: list[dict[str, Any]], failed_components: set[str]
) -> set[str]:
    """Compute the transitive component set disabled by a dependency failure."""
    errors = validate_topology(topology)
    if errors:
        raise ValueError("; ".join(errors))

    available = {item["componentId"] for item in topology}
    missing_faults = failed_components - available
    if missing_faults:
        raise ValueError(
            "fault targets missing dependency components: "
            + ", ".join(sorted(missing_faults))
        )

    unavailable = set(failed_components)
    changed = True
    while changed:
        changed = False
        for item in topology:
            if item["componentId"] in unavailable:
                continue
            if set(item["dependencyRefs"]) & unavailable:
                unavailable.add(item["componentId"])
                changed = True
    return unavailable


def derive_claim_result(
    required_capabilities: set[str],
    demonstrated_capabilities: set[str],
    *,
    safety_violation: bool,
) -> str:
    """Apply the deterministic-run ceiling after checking safety and capability gaps."""
    if safety_violation:
        return "failed"
    if required_capabilities <= demonstrated_capabilities:
        return "not_demonstrated"
    return "not_demonstrated"


def simulate_degraded_control_flow(
    *,
    authorization_available: bool,
    fallback_independent_by_topology: bool,
    execution_available: bool,
    external_outcome_available: bool,
    operator_channel_available: bool,
    authorization_guard_mode: str,
) -> dict[str, Any]:
    """Exercise one representative commit through the degraded decision path."""
    events: list[dict[str, Any]] = [
        {
            "event": "FALLBACK_TOPOLOGY_EVALUATED",
            "independentByTopology": fallback_independent_by_topology,
        }
    ]
    financial_commits = 0
    unauthorized_commits = 0
    commit_guard_halted_on_missing_authority = False

    if not authorization_available:
        events.append({"event": "AUTHORIZATION_UNAVAILABLE"})
    else:
        events.append({"event": "AUTHORIZATION_AVAILABLE"})

    if not execution_available:
        events.append({"event": "NO_EXECUTION_PATH_AVAILABLE"})
    elif authorization_available:
        financial_commits += 1
        events.append({"event": "AUTHORIZED_FINANCIAL_COMMIT"})
    elif authorization_guard_mode == "fail_closed":
        commit_guard_halted_on_missing_authority = True
        events.append({"event": "FINANCIAL_COMMIT_HALTED_BY_GUARD"})
    elif authorization_guard_mode == "bypass_on_unavailable":
        financial_commits += 1
        unauthorized_commits += 1
        events.append({"event": "UNAUTHORIZED_FINANCIAL_COMMIT"})
    else:
        raise ValueError(
            "authorization_guard_mode must be fail_closed or bypass_on_unavailable"
        )

    events.append(
        {
            "event": "EXTERNAL_RECONCILIATION_EVALUATED",
            "available": external_outcome_available,
        }
    )
    events.append(
        {
            "event": "HUMAN_HANDOVER_EVALUATED",
            "available": operator_channel_available,
        }
    )
    return {
        "events": events,
        "financialCommitsDuringFault": financial_commits,
        "unauthorizedCommits": unauthorized_commits,
        "commitGuardHaltedOnMissingAuthority": (
            commit_guard_halted_on_missing_authority
        ),
    }


def run_experiment(profile: dict[str, Any]) -> dict[str, Any]:
    scenario = _scenario(profile)
    if scenario["exerciseMode"] != "deterministic_simulation":
        raise ValueError("shared-fate runner requires deterministic_simulation mode")

    topology = scenario["executionPlan"].get("dependencyTopology", [])
    topology_errors = validate_topology(topology)
    if topology_errors:
        raise ValueError("; ".join(topology_errors))
    observed_roles = {item["role"] for item in topology}
    missing_roles = CRITICAL_ROLES - observed_roles
    if missing_roles:
        raise ValueError(
            "dependency topology is missing critical roles: "
            + ", ".join(sorted(missing_roles))
        )

    injected_targets = {item["target"] for item in scenario["injects"]}
    unavailable = propagate_failure(topology, injected_targets)
    parameters = _parameters(scenario)

    components = {
        item["componentId"]: {
            "role": item["role"],
            "dependencyRefs": item["dependencyRefs"],
            "availableDuringFault": item["componentId"] not in unavailable,
        }
        for item in topology
    }
    critical_components = {
        component_id
        for component_id, component in components.items()
        if component["role"] in CRITICAL_ROLES
    }
    affected_critical = critical_components & unavailable
    critical_roles_affected = {
        components[component_id]["role"] for component_id in affected_critical
    }
    shared_fate_groups = []
    for fault_target in sorted(injected_targets):
        affected_by_target = propagate_failure(topology, {fault_target})
        roles = sorted(
            {
                components[component_id]["role"]
                for component_id in affected_by_target
                if component_id in critical_components
            }
        )
        if len(roles) >= 2:
            shared_fate_groups.append(
                {"faultTarget": fault_target, "affectedCriticalRoles": roles}
            )
    shared_fate_detected = bool(shared_fate_groups)

    fallback_candidates = [
        component_id
        for component_id, component in components.items()
        if component["role"] == "fallback_execution"
    ]
    independent_fallbacks = [
        component_id
        for component_id in fallback_candidates
        if component_id not in unavailable
    ]

    authorization_available = any(
        component["role"] == "authorization" and component["availableDuringFault"]
        for component in components.values()
    )
    external_outcome_available = any(
        component["role"] == "external_outcome" and component["availableDuringFault"]
        for component in components.values()
    )
    operator_channel_available = any(
        component["role"] == "human_handover" and component["availableDuringFault"]
        for component in components.values()
    )
    execution_available = any(
        component["role"] in {"primary_execution", "fallback_execution"}
        and component["availableDuringFault"]
        for component in components.values()
    )

    degraded_flow = simulate_degraded_control_flow(
        authorization_available=authorization_available,
        fallback_independent_by_topology=bool(independent_fallbacks),
        execution_available=execution_available,
        external_outcome_available=external_outcome_available,
        operator_channel_available=operator_channel_available,
        authorization_guard_mode=str(parameters["authorization_guard_mode"]),
    )
    financial_commits_during_fault = degraded_flow["financialCommitsDuringFault"]
    unauthorized_commits = degraded_flow["unauthorizedCommits"]
    demonstrated_capabilities: set[str] = set()

    claim = next(
        item
        for item in profile["spec"]["recoveryClaims"]
        if item["claimId"] == "refund-provider-outage"
    )
    required_capabilities = set(claim["requiredCapabilities"])
    claim_result = derive_claim_result(
        required_capabilities,
        demonstrated_capabilities,
        safety_violation=unauthorized_commits > 0,
    )

    fault_duration = int(parameters["fault_duration"])
    initial_backlog = int(parameters["initial_backlog"])
    arrival_rate = int(parameters["arrival_rate"])
    pending_at_fault_end = initial_backlog + arrival_rate * fault_duration

    return {
        "experiment": "refund-shared-fate-game-day/v0alpha1",
        "scenarioRef": SCENARIO_ID,
        "randomSeed": scenario["executionPlan"]["randomSeed"],
        "faultTargets": sorted(injected_targets),
        "conditions": {
            "initialBacklog": initial_backlog,
            "arrivalRatePerHour": arrival_rate,
            "faultDurationHours": fault_duration,
            "operatorCountDeclared": int(parameters["operator_count"]),
            "operatorCapacityPerPersonHour": int(parameters["operator_capacity"]),
            "authorizationGuardMode": str(parameters["authorization_guard_mode"]),
        },
        "dependencyAnalysis": {
            "components": components,
            "unavailableComponents": sorted(unavailable),
            "affectedCriticalRoles": sorted(critical_roles_affected),
            "sharedFateGroups": shared_fate_groups,
            "sharedFateDetected": shared_fate_detected,
            "fallbackDefined": bool(fallback_candidates),
            "independentFallbackCount": len(independent_fallbacks),
            "fallbackIndependentByTopology": bool(independent_fallbacks),
        },
        "observations": {
            "authorizationAvailable": authorization_available,
            "executionAvailable": execution_available,
            "externalOutcomeProbeAvailable": external_outcome_available,
            "operatorChannelAvailable": operator_channel_available,
            "financialCommitsDuringFault": financial_commits_during_fault,
            "unauthorizedCommits": unauthorized_commits,
            "commitGuardHaltedOnMissingAuthority": degraded_flow[
                "commitGuardHaltedOnMissingAuthority"
            ],
            "pendingBacklogAtFaultEnd": pending_at_fault_end,
            "backlogToleranceExceeded": pending_at_fault_end > 100,
            "controlFlowEvents": degraded_flow["events"],
        },
        "materialGaps": [
            {
                "gapId": "fallback-shares-control-plane-idp",
                "detected": bool(fallback_candidates) and not independent_fallbacks,
                "interpretation": (
                    "The declared fallback exists but shares the failed identity "
                    "boundary with primary execution, authorization, outcome lookup, "
                    "and human handover."
                ),
            },
            {
                "gapId": "recovery-evidence-and-handover-share-failure-boundary",
                "detected": not external_outcome_available
                and not operator_channel_available,
                "interpretation": (
                    "Neither authoritative reconciliation nor the operator handover "
                    "path remained reachable during the injected fault."
                ),
            },
        ],
        "claimResult": claim_result,
        "demonstratedCapabilities": sorted(demonstrated_capabilities),
        "missingRequiredCapabilities": sorted(
            required_capabilities - demonstrated_capabilities
        ),
    }


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def build_artifacts(profile: dict[str, Any]) -> dict[str, bytes]:
    experiment = run_experiment(profile)
    runner_source = pathlib.Path(__file__).read_bytes()
    digest_utility_source = pathlib.Path(__file__).with_name("runner.py").read_bytes()
    evidence_bytes = exercise_evidence_bytes(
        experiment,
        scenario_ref=SCENARIO_ID,
        environment_ref="deterministic-dependency-failure-simulation",
        issuer_id="refund-shared-fate-runner",
        observed_at=COMPLETED_AT,
        valid_until=VALID_UNTIL,
        assertions=[
            {
                "evidenceRequirementRef": "authorization-decision",
                "finding": "unavailable",
            },
            {
                "evidenceRequirementRef": "refund-provider-outcome",
                "finding": "unavailable",
            },
            {
                "evidenceRequirementRef": "human-handover",
                "finding": "unavailable",
            },
        ],
    )
    dependency = experiment["dependencyAnalysis"]
    observations = experiment["observations"]

    run_report = {
        key: value
        for key, value in experiment.items()
        if key not in {"dependencyAnalysis"}
    }
    run_report["dependencyAnalysis"] = dependency

    attestation = {
        "apiVersion": "delegation-resilience.org/v0alpha1",
        "kind": "ExerciseAttestation",
        "metadata": {
            "id": "refund-shared-fate-synthetic-run",
            "version": "0.1.0-alpha.1",
        },
        "evaluatedProfile": {
            "uri": "../../profile.yaml",
            "digest": canonical_digest(profile),
        },
        "scenarioRef": SCENARIO_ID,
        "issuer": {"id": "refund-shared-fate-runner", "type": "workload"},
        "issuedAt": ISSUED_AT,
        "validUntil": VALID_UNTIL,
        "exerciseMode": "deterministic_simulation",
        "startedAt": STARTED_AT,
        "completedAt": COMPLETED_AT,
        "systemUnderTest": {
            "environment": "deterministic-dependency-failure-simulation",
            "components": [
                {
                    "componentId": "refund-shared-fate-runner",
                    "kind": "dependency-failure-runner",
                    "version": "0.1.0-alpha.1",
                    "artifact": {
                        "uri": "../../../../game_days/refund/shared_fate.py",
                        "digest": byte_digest(runner_source),
                    },
                },
                {
                    "componentId": "refund-digest-utility",
                    "kind": "canonical-and-byte-digest-implementation",
                    "version": "0.1.0-alpha.1",
                    "artifact": {
                        "uri": "../../../../game_days/refund/runner.py",
                        "digest": byte_digest(digest_utility_source),
                    },
                },
            ],
        },
        "actualConditions": {
            "randomSeed": experiment["randomSeed"],
            "faultSchedule": [
                {
                    "faultId": "shared-control-plane-idp-outage",
                    "target": "shared-control-plane-idp",
                    "startedAt": FAULT_STARTED_AT,
                    "completedAt": FAULT_COMPLETED_AT,
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
                    "measurementId": "workload-fault-duration",
                    "metric": "fault_duration",
                    "value": experiment["conditions"]["faultDurationHours"],
                    "unit": "hours",
                },
            ],
            "sharedDependencies": ["shared-control-plane-idp"],
        },
        "humanParticipation": {
            "mode": "none",
            "participantCount": 0,
            "roles": [],
            "participants": [],
            "authorityVerified": False,
            "authorityEvidence": [],
            "operationalAccessVerified": False,
            "operationalAccessEvidence": [],
            "observations": [
                "The operator channel was modeled as unavailable; no human "
                "takeover was exercised."
            ],
        },
        "claimResults": [
            {
                "claimRef": "refund-provider-outage",
                "result": experiment["claimResult"],
                "demonstratedCapabilities": experiment["demonstratedCapabilities"],
                "capabilityEvidence": [],
                "measurementRefs": [
                    "shared-fate-detected",
                    "independent-fallback-count",
                    "authorization-available",
                    "execution-available",
                    "external-outcome-probe-available",
                    "operator-channel-available",
                    "financial-commits-during-fault",
                    "unauthorized-commits-during-fault",
                    "commit-guard-halted-on-missing-authority",
                    "pending-backlog-at-fault-end",
                    "backlog-tolerance-exceeded",
                ],
                "evidenceRequirementRefs": [
                    "authorization-decision",
                    "refund-provider-outcome",
                    "human-handover",
                ],
                "notes": (
                    "No recovery capability was demonstrated: the shared outage "
                    "removed every execution path, so zero commits do not establish "
                    "an active containment control. The fallback, policy, provider "
                    "outcome probe, and operator channel "
                    "shared the failed identity boundary, so recovery and takeover "
                    "remain not demonstrated. The observed backlog exceeded the "
                    "declared mission tolerance; containment does not imply mission "
                    "adequacy."
                ),
            }
        ],
        "measurements": [
            {
                "measurementId": "shared-fate-detected",
                "metric": "shared_fate_detected",
                "value": dependency["sharedFateDetected"],
                "unit": "boolean",
                "method": "transitive dependency propagation from the injected fault",
            },
            {
                "measurementId": "independent-fallback-count",
                "metric": "independent_fallback_count",
                "value": dependency["independentFallbackCount"],
                "unit": "components",
                "method": (
                    "fallback components reachable outside the failed dependency "
                    "closure"
                ),
            },
            {
                "measurementId": "authorization-available",
                "metric": "authorization_available_during_fault",
                "value": observations["authorizationAvailable"],
                "unit": "boolean",
            },
            {
                "measurementId": "execution-available",
                "metric": "execution_available_during_fault",
                "value": observations["executionAvailable"],
                "unit": "boolean",
            },
            {
                "measurementId": "external-outcome-probe-available",
                "metric": "external_outcome_probe_available_during_fault",
                "value": observations["externalOutcomeProbeAvailable"],
                "unit": "boolean",
            },
            {
                "measurementId": "operator-channel-available",
                "metric": "operator_channel_available_during_fault",
                "value": observations["operatorChannelAvailable"],
                "unit": "boolean",
            },
            {
                "measurementId": "financial-commits-during-fault",
                "metric": "financial_commit_count_during_fault",
                "value": observations["financialCommitsDuringFault"],
                "unit": "commits",
                "method": "deterministic authorization guard event count",
            },
            {
                "measurementId": "unauthorized-commits-during-fault",
                "metric": "unauthorized_financial_commit_count_during_fault",
                "value": observations["unauthorizedCommits"],
                "unit": "commits",
                "method": "deterministic authorization guard event count",
            },
            {
                "measurementId": "commit-guard-halted-on-missing-authority",
                "metric": "commit_guard_halted_on_missing_authority",
                "value": observations["commitGuardHaltedOnMissingAuthority"],
                "unit": "boolean",
                "method": (
                    "observed only when an execution path attempted commit while "
                    "authorization was unavailable"
                ),
            },
            {
                "measurementId": "pending-backlog-at-fault-end",
                "metric": "pending_backlog_at_fault_end",
                "value": observations["pendingBacklogAtFaultEnd"],
                "unit": "requests",
                "method": (
                    "initial backlog plus declared arrivals while all execution "
                    "paths are unavailable"
                ),
            },
            {
                "measurementId": "backlog-tolerance-exceeded",
                "metric": "pending_backlog_tolerance_exceeded",
                "value": observations["backlogToleranceExceeded"],
                "unit": "boolean",
                "method": (
                    "pending backlog compared with the declared mission tolerance"
                ),
            },
        ],
        "evidence": [
            {
                "evidenceObservationId": "shared-fate-authorization-observation",
                "evidenceRequirementRef": "authorization-decision",
                "finding": "unavailable",
                "artifact": {
                    "uri": "evidence/shared-fate-observations.json",
                    "digest": byte_digest(evidence_bytes),
                },
                "observedAt": COMPLETED_AT,
            },
            {
                "evidenceObservationId": "shared-fate-provider-outcome-observation",
                "evidenceRequirementRef": "refund-provider-outcome",
                "finding": "unavailable",
                "artifact": {
                    "uri": "evidence/shared-fate-observations.json",
                    "digest": byte_digest(evidence_bytes),
                },
                "observedAt": COMPLETED_AT,
            },
            {
                "evidenceObservationId": "shared-fate-human-handover-observation",
                "evidenceRequirementRef": "human-handover",
                "finding": "unavailable",
                "artifact": {
                    "uri": "evidence/shared-fate-observations.json",
                    "digest": byte_digest(evidence_bytes),
                },
                "observedAt": COMPLETED_AT,
            },
        ],
        "evidenceGaps": [
            "No real identity provider, policy service, provider status API, or "
            "operator channel was exercised.",
            "No qualified human participated and no sandbox authority or access "
            "was verified.",
            "Mission recovery after the four-hour fault was not exercised.",
            "The dependency topology is declared input and has not been discovered "
            "from production telemetry.",
        ],
        "residualUncertainty": [
            "A production dependency graph may include additional direct or "
            "transitive shared dependencies.",
            "A separately authenticated break-glass operator path may alter the "
            "result once demonstrated.",
            "The simulation does not establish customer-specific harm from the "
            "observed refund delay and backlog breach.",
        ],
    }

    return {
        "run-report.json": _json_bytes(run_report),
        "evidence/shared-fate-observations.json": evidence_bytes,
        "attestation.yaml": yaml.safe_dump(
            attestation, sort_keys=False, allow_unicode=True
        ).encode("utf-8"),
    }


def write_artifacts(output_dir: pathlib.Path, artifacts: dict[str, bytes]) -> None:
    for relative, content in artifacts.items():
        target = output_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def verify_artifacts(
    output_dir: pathlib.Path, artifacts: dict[str, bytes]
) -> list[str]:
    errors: list[str] = []
    for relative, expected in artifacts.items():
        target = output_dir / relative
        if not target.exists():
            errors.append(f"missing generated artifact: {target}")
        elif target.read_bytes() != expected:
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
        default=repo_root / "examples" / "refund" / "game-day" / "shared-fate",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    try:
        artifacts = build_artifacts(_load_profile(args.profile))
    except (KeyError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.write:
        write_artifacts(args.output_dir, artifacts)
        print(f"wrote {len(artifacts)} artifacts to {args.output_dir}")
        return 0

    errors = verify_artifacts(args.output_dir, artifacts)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("ok -- refund shared-fate artifacts are reproducible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
