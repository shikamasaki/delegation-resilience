#!/usr/bin/env python3
"""Cross-artifact semantic validation for DelegationResilienceProfile v0alpha1."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import pathlib
import sys
from typing import Any

import rfc8785
import yaml

try:
    from tools.artifact_validation import (
        load_local_artifact,
        validate_exercise_evidence,
        validate_human_evidence,
    )
except ModuleNotFoundError:  # Direct `python tools/validate_profile.py` execution.
    from artifact_validation import (
        load_local_artifact,
        validate_exercise_evidence,
        validate_human_evidence,
    )


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _check_refs(
    errors: list[str], owner: str, field: str, refs: list[str], available: set[str]
) -> None:
    for ref in refs:
        if ref not in available:
            errors.append(f"{owner}.{field} references missing ID: {ref}")


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


def _parse_time(value: str, field: str, errors: list[str]) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        errors.append(f"{field} is not a valid RFC 3339 timestamp: {value!r}")
        return None


def validate_profile(profile: dict[str, Any]) -> list[str]:
    """Validate ID uniqueness, reference integrity, and deployment semantics."""
    errors: list[str] = []
    spec = profile.get("spec", {})

    constraints = {
        item.get("constraintId")
        for item in spec.get("acceptabilityDecision", {}).get(
            "constitutionalConstraints", []
        )
    }
    actions = {item.get("actionId") for item in spec.get("actions", [])}
    evidence = {
        item.get("evidenceId")
        for item in spec.get("evidenceProfile", {}).get("requirements", [])
    }
    claims = {item.get("claimId") for item in spec.get("recoveryClaims", [])}
    collections = {
        "artifact metadata.id": [
            item.get("metadata", {}).get("id")
            for item in [
                spec.get("mission", {}),
                spec.get("acceptabilityDecision", {}),
                spec.get("evidenceProfile", {}),
                *spec.get("actions", []),
                *spec.get("delegationGrants", []),
                *spec.get("recoveryClaims", []),
                *spec.get("exerciseScenarios", []),
            ]
        ],
        "constraintId": [
            item.get("constraintId")
            for item in spec.get("acceptabilityDecision", {}).get(
                "constitutionalConstraints", []
            )
        ],
        "actionId": [item.get("actionId") for item in spec.get("actions", [])],
        "evidenceId": [
            item.get("evidenceId")
            for item in spec.get("evidenceProfile", {}).get("requirements", [])
        ],
        "claimId": [item.get("claimId") for item in spec.get("recoveryClaims", [])],
        "scenarioId": [
            item.get("scenarioId") for item in spec.get("exerciseScenarios", [])
        ],
    }
    for label, values in collections.items():
        for duplicate in _duplicates([value for value in values if value]):
            errors.append(f"duplicate {label}: {duplicate}")

    referenced_constraints: set[str] = set()
    for claim in spec.get("recoveryClaims", []):
        claim_id = claim.get("claimId", "<unknown-claim>")
        owner = f"recoveryClaim[{claim_id}]"
        constraint_refs = claim.get("constraintRefs", [])
        referenced_constraints.update(constraint_refs)
        _check_refs(errors, owner, "constraintRefs", constraint_refs, constraints)
        _check_refs(errors, owner, "actionRefs", claim.get("actionRefs", []), actions)
        _check_refs(
            errors,
            owner,
            "evidenceRequirementRefs",
            claim.get("evidenceRequirementRefs", []),
            evidence,
        )

        support = claim.get("supportStatus")
        disposition = claim.get("deploymentDisposition")
        if support != "SUPPORTED" and disposition != "PROHIBITED":
            errors.append(
                f"{owner} is {support} and must use deploymentDisposition PROHIBITED"
            )
        if support == "CONTRADICTED" and disposition != "PROHIBITED":
            errors.append(f"{owner} is contradicted and cannot be deployed")

    for constraint in sorted(constraints - referenced_constraints):
        errors.append(
            f"constitutional constraint has no supporting RecoveryClaim: {constraint}"
        )

    mission_id = spec.get("mission", {}).get("metadata", {}).get("id")
    for grant in spec.get("delegationGrants", []):
        grant_id = grant.get("grantId", "<unknown-grant>")
        if grant.get("missionRef") != mission_id:
            errors.append(
                f"delegationGrant[{grant_id}].missionRef references missing ID: "
                f"{grant.get('missionRef')}"
            )
        _check_refs(
            errors,
            f"delegationGrant[{grant_id}]",
            "actionRefs",
            grant.get("actionRefs", []),
            actions,
        )

    for scenario in spec.get("exerciseScenarios", []):
        scenario_id = scenario.get("scenarioId", "<unknown-scenario>")
        _check_refs(
            errors,
            f"exerciseScenario[{scenario_id}]",
            "claimRefs",
            scenario.get("claimRefs", []),
            claims,
        )
        execution_plan = scenario.get("executionPlan", {})
        human_bindings = execution_plan.get("humanEvidenceBindings")
        if human_bindings:
            qualification = human_bindings.get("qualification", {})
            authority = human_bindings.get("authority", {})
            if qualification.get("objectRef") != scenario_id:
                errors.append(
                    f"exerciseScenario[{scenario_id}].humanEvidenceBindings."
                    "qualification.objectRef must reference its scenarioId"
                )
            _check_refs(
                errors,
                f"exerciseScenario[{scenario_id}].humanEvidenceBindings.authority",
                "objectRef",
                [authority.get("objectRef")],
                actions,
            )
        topology = execution_plan.get("dependencyTopology", [])
        analysis_required = execution_plan.get("dependencyAnalysisRequired") is True
        if analysis_required and not topology:
            errors.append(
                f"exerciseScenario[{scenario_id}] requires a dependency topology"
            )
        if topology:
            component_ids = [item.get("componentId") for item in topology]
            for duplicate in _duplicates(
                [component_id for component_id in component_ids if component_id]
            ):
                errors.append(
                    f"exerciseScenario[{scenario_id}] has duplicate dependency "
                    "componentId: "
                    f"{duplicate}"
                )
            available_components = {
                component_id for component_id in component_ids if component_id
            }
            for component in topology:
                dependency_refs = component.get("dependencyRefs", [])
                for duplicate in _duplicates(dependency_refs):
                    errors.append(
                        f"exerciseScenario[{scenario_id}].component"
                        f"[{component.get('componentId')}] has duplicate "
                        f"dependencyRef: {duplicate}"
                    )
                _check_refs(
                    errors,
                    f"exerciseScenario[{scenario_id}].component[{component.get('componentId')}]",
                    "dependencyRefs",
                    dependency_refs,
                    available_components,
                )
                if component.get("componentId") in set(dependency_refs):
                    errors.append(
                        f"exerciseScenario[{scenario_id}].component"
                        f"[{component.get('componentId')}] depends on itself"
                    )
            graph = {
                component.get("componentId"): component.get("dependencyRefs", [])
                for component in topology
                if component.get("componentId")
            }
            cycle = _dependency_cycle(graph)
            if cycle:
                errors.append(
                    f"exerciseScenario[{scenario_id}] dependency cycle: "
                    + " -> ".join(cycle)
                )
            if analysis_required:
                required_roles = {
                    "primary_execution",
                    "fallback_execution",
                    "authorization",
                    "external_outcome",
                    "human_handover",
                }
                observed_roles = {item.get("role") for item in topology}
                for role in sorted(required_roles - observed_roles):
                    errors.append(
                        f"exerciseScenario[{scenario_id}] dependency topology "
                        f"is missing required role: {role}"
                    )
            if analysis_required:
                _check_refs(
                    errors,
                    f"exerciseScenario[{scenario_id}].executionPlan",
                    "sharedDependencies",
                    scenario.get("executionPlan", {}).get("sharedDependencies", []),
                    available_components,
                )
                _check_refs(
                    errors,
                    f"exerciseScenario[{scenario_id}]",
                    "injects.target",
                    [item.get("target") for item in scenario.get("injects", [])],
                    available_components,
                )

    return errors


def _deterministic_replay_artifacts(
    profile: dict[str, Any], scenario_ref: str | None
) -> dict[str, bytes]:
    """Rebuild evidence only for the two reviewed, built-in deterministic runners."""
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        if scenario_ref == "refund-response-loss-after-commit":
            from game_days.refund.runner import build_artifacts

            return build_artifacts(profile)
        if scenario_ref == "refund-shared-idp-outage":
            from game_days.refund.shared_fate import build_artifacts

            return build_artifacts(profile)
    except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError):
        return {}
    return {}


def validate_attestation(
    profile: dict[str, Any],
    attestation: dict[str, Any],
    as_of: dt.datetime,
    *,
    artifact_base: pathlib.Path | None = None,
    artifact_root: pathlib.Path | None = None,
) -> list[str]:
    """Validate an attestation against the profile and its evidence ceilings."""
    errors: list[str] = []
    spec = profile.get("spec", {})
    claims = {item.get("claimId"): item for item in spec.get("recoveryClaims", [])}
    scenarios = {
        item.get("scenarioId"): item for item in spec.get("exerciseScenarios", [])
    }
    evidence_ids = {
        item.get("evidenceId")
        for item in spec.get("evidenceProfile", {}).get("requirements", [])
    }

    evaluated_profile = attestation.get("evaluatedProfile", {})
    expected_profile_digest = canonical_digest(profile)
    if evaluated_profile.get("digest") != expected_profile_digest:
        errors.append(
            "attestation evaluatedProfile.digest does not match the canonical profile "
            f"digest: expected {expected_profile_digest}"
        )

    scenario_ref = attestation.get("scenarioRef")
    scenario = scenarios.get(scenario_ref)
    if scenario is None:
        errors.append(f"attestation references missing scenario: {scenario_ref}")
    elif attestation.get("exerciseMode") != scenario.get("exerciseMode"):
        errors.append(
            "attestation exerciseMode does not match the declared ExerciseSpec"
        )

    started = _parse_time(attestation.get("startedAt"), "startedAt", errors)
    completed = _parse_time(attestation.get("completedAt"), "completedAt", errors)
    issued = _parse_time(attestation.get("issuedAt"), "issuedAt", errors)
    valid_until = _parse_time(attestation.get("validUntil"), "validUntil", errors)
    if started and completed and completed < started:
        errors.append("completedAt precedes startedAt")
    if completed and issued and issued < completed:
        errors.append("issuedAt precedes completedAt")
    if issued and valid_until and valid_until <= issued:
        errors.append("validUntil must be later than issuedAt")
    if valid_until and valid_until <= as_of:
        errors.append("attestation is stale at the requested evaluation time")

    attestation_ids = {
        "claimResults.claimRef": [
            item.get("claimRef") for item in attestation.get("claimResults", [])
        ],
        "measurements.measurementId": [
            item.get("measurementId") for item in attestation.get("measurements", [])
        ],
        "actualConditions.faultSchedule.faultId": [
            item.get("faultId")
            for item in attestation.get("actualConditions", {}).get("faultSchedule", [])
        ],
        "systemUnderTest.components.componentId": [
            item.get("componentId")
            for item in attestation.get("systemUnderTest", {}).get("components", [])
        ],
        "evidence.evidenceObservationId": [
            item.get("evidenceObservationId")
            for item in attestation.get("evidence", [])
        ],
        "humanParticipation.participants.participantId": [
            item.get("participantId")
            for item in attestation.get("humanParticipation", {}).get(
                "participants", []
            )
        ],
        "humanParticipation.authorityEvidence.participantRef": [
            item.get("participantRef")
            for item in attestation.get("humanParticipation", {}).get(
                "authorityEvidence", []
            )
        ],
        "humanParticipation.operationalAccessEvidence.participantRef": [
            item.get("participantRef")
            for item in attestation.get("humanParticipation", {}).get(
                "operationalAccessEvidence", []
            )
        ],
    }
    for label, values in attestation_ids.items():
        for duplicate in _duplicates([value for value in values if value]):
            errors.append(f"duplicate {label}: {duplicate}")

    measurements = {
        item.get("measurementId") for item in attestation.get("measurements", [])
    }
    observed_evidence = {
        item.get("evidenceRequirementRef") for item in attestation.get("evidence", [])
    }
    verified_observation_ids: set[str] = set()
    replay_verified_observation_ids: set[str] = set()
    environment_ref = attestation.get("systemUnderTest", {}).get("environment", "")
    attestation_issuer = attestation.get("issuer", {})
    replay_artifacts = (
        _deterministic_replay_artifacts(profile, scenario_ref)
        if attestation.get("exerciseMode") == "deterministic_simulation"
        else {}
    )
    replay_attestation: dict[str, Any] = {}
    replay_attestation_bytes = replay_artifacts.get("attestation.yaml")
    if replay_attestation_bytes is not None:
        loaded_replay_attestation = yaml.safe_load(replay_attestation_bytes)
        if isinstance(loaded_replay_attestation, dict):
            replay_attestation = loaded_replay_attestation
    for observation in attestation.get("evidence", []):
        observation_id = observation.get(
            "evidenceObservationId", "<unknown-observation>"
        )
        artifact_errors = validate_exercise_evidence(
            observation.get("artifact"),
            base_dir=artifact_base,
            artifact_root=artifact_root,
            scenario_ref=str(scenario_ref),
            environment_ref=environment_ref,
            evidence_requirement_ref=str(observation.get("evidenceRequirementRef", "")),
            finding=str(observation.get("finding", "")),
            issuer=attestation_issuer,
            observation_observed_at=str(observation.get("observedAt", "")),
            as_of=as_of,
        )
        if not artifact_errors:
            verified_observation_ids.add(observation_id)
            content, load_errors = load_local_artifact(
                observation.get("artifact"),
                base_dir=artifact_base,
                artifact_root=artifact_root,
            )
            artifact_uri = observation.get("artifact", {}).get("uri")
            if (
                not load_errors
                and isinstance(artifact_uri, str)
                and replay_artifacts.get(artifact_uri) == content
            ):
                replay_verified_observation_ids.add(observation_id)
        errors.extend(
            f"evidence[{observation_id}]: {error}" for error in artifact_errors
        )
    for component in attestation.get("systemUnderTest", {}).get("components", []):
        if "artifact" not in component:
            continue
        component_id = component.get("componentId", "<unknown-component>")
        _, artifact_errors = load_local_artifact(
            component.get("artifact"),
            base_dir=artifact_base,
            artifact_root=artifact_root,
        )
        errors.extend(
            f"systemUnderTest.component[{component_id}]: {error}"
            for error in artifact_errors
        )
    satisfied_evidence = {
        item.get("evidenceRequirementRef")
        for item in attestation.get("evidence", [])
        if item.get("finding") == "satisfied"
        and item.get("evidenceObservationId") in verified_observation_ids
    }
    replay_verified_satisfied_evidence = {
        item.get("evidenceRequirementRef")
        for item in attestation.get("evidence", [])
        if item.get("finding") == "satisfied"
        and item.get("evidenceObservationId") in replay_verified_observation_ids
    }
    adverse_evidence = {
        item.get("evidenceRequirementRef")
        for item in attestation.get("evidence", [])
        if item.get("finding") in {"contradicted", "unavailable", "inconclusive"}
    }
    _check_refs(
        errors,
        "attestation",
        "evidenceRequirementRefs",
        list(observed_evidence),
        evidence_ids,
    )

    participation = attestation.get("humanParticipation", {})
    participants = participation.get("participants", [])
    participant_ids = {
        item.get("participantId") for item in participants if item.get("participantId")
    }
    if participation.get("participantCount") != len(participants):
        errors.append(
            "humanParticipation.participantCount does not match the participant list"
        )
    if participation.get("mode") == "none" and participants:
        errors.append("humanParticipation mode none cannot list participants")
    declared_roles = set(participation.get("roles", []))
    participant_roles = {item.get("role") for item in participants if item.get("role")}
    if participant_roles - declared_roles:
        errors.append(
            "humanParticipation.roles omits participant roles: "
            + ", ".join(sorted(participant_roles - declared_roles))
        )

    for result in attestation.get("claimResults", []):
        claim_ref = result.get("claimRef")
        claim = claims.get(claim_ref)
        owner = f"claimResult[{claim_ref}]"
        if claim is None:
            errors.append(f"{owner} references missing RecoveryClaim")
            continue
        if scenario is not None and claim_ref not in set(scenario.get("claimRefs", [])):
            errors.append(f"{owner} is not covered by scenario[{scenario_ref}]")

        _check_refs(
            errors,
            owner,
            "measurementRefs",
            result.get("measurementRefs", []),
            measurements,
        )
        _check_refs(
            errors,
            owner,
            "evidenceRequirementRefs",
            result.get("evidenceRequirementRefs", []),
            evidence_ids,
        )

        demonstrated = set(result.get("demonstratedCapabilities", []))
        required = set(claim.get("requiredCapabilities", []))
        capability_bindings = result.get("capabilityEvidence", [])
        binding_capabilities = [item.get("capability") for item in capability_bindings]
        for duplicate in _duplicates(
            [item for item in binding_capabilities if isinstance(item, str)]
        ):
            errors.append(f"{owner} has duplicate capabilityEvidence: {duplicate}")
        bound_capabilities = {
            item for item in binding_capabilities if isinstance(item, str)
        }
        if demonstrated != bound_capabilities:
            errors.append(
                f"{owner} demonstratedCapabilities and capabilityEvidence differ"
            )
        result_measurement_refs = set(result.get("measurementRefs", []))
        result_evidence_refs = set(result.get("evidenceRequirementRefs", []))
        expected_result = next(
            (
                item
                for item in replay_attestation.get("claimResults", [])
                if item.get("claimRef") == claim_ref
            ),
            None,
        )
        technical_capabilities = demonstrated - {"handover", "human_takeover"}
        if technical_capabilities and expected_result is not None:
            replay_context_fields = {
                "exerciseMode": attestation.get("exerciseMode"),
                "startedAt": attestation.get("startedAt"),
                "completedAt": attestation.get("completedAt"),
                "systemUnderTest": attestation.get("systemUnderTest"),
                "actualConditions": attestation.get("actualConditions"),
            }
            expected_context_fields = {
                key: replay_attestation.get(key) for key in replay_context_fields
            }
            if replay_context_fields != expected_context_fields:
                errors.append(
                    f"{owner} technical capabilities do not match deterministic "
                    "replay conditions or system under test"
                )
        for binding in capability_bindings:
            capability = binding.get("capability", "<unknown-capability>")
            binding_owner = f"{owner}.capabilityEvidence[{capability}]"
            if capability not in required:
                errors.append(
                    f"{binding_owner} is not a required capability of the claim"
                )
            binding_measurements = set(binding.get("measurementRefs", []))
            binding_evidence = set(binding.get("evidenceRequirementRefs", []))
            _check_refs(
                errors,
                binding_owner,
                "measurementRefs",
                list(binding_measurements),
                measurements,
            )
            if not binding_measurements <= result_measurement_refs:
                errors.append(
                    f"{binding_owner} cites measurements outside its claim result"
                )
            _check_refs(
                errors,
                binding_owner,
                "evidenceRequirementRefs",
                list(binding_evidence),
                set(claim.get("evidenceRequirementRefs", [])),
            )
            if not binding_evidence <= result_evidence_refs:
                errors.append(
                    f"{binding_owner} cites evidence outside its claim result"
                )
            if capability not in {"handover", "human_takeover"}:
                unreplayed = binding_evidence - replay_verified_satisfied_evidence
                if unreplayed:
                    errors.append(
                        f"{binding_owner} lacks byte-identical deterministic replay "
                        "evidence: " + ", ".join(sorted(unreplayed))
                    )
                expected_binding = next(
                    (
                        item
                        for item in (expected_result or {}).get(
                            "capabilityEvidence", []
                        )
                        if item.get("capability") == capability
                    ),
                    None,
                )
                if expected_binding is None or (
                    set(expected_binding.get("measurementRefs", []))
                    != binding_measurements
                    or set(expected_binding.get("evidenceRequirementRefs", []))
                    != binding_evidence
                ):
                    errors.append(
                        f"{binding_owner} is not supported by the deterministic "
                        "replay verdict"
                    )
                actual_measurements = {
                    item.get("measurementId"): item
                    for item in attestation.get("measurements", [])
                    if item.get("measurementId") in binding_measurements
                }
                expected_measurements = {
                    item.get("measurementId"): item
                    for item in replay_attestation.get("measurements", [])
                    if item.get("measurementId") in binding_measurements
                }
                if actual_measurements != expected_measurements:
                    errors.append(
                        f"{binding_owner} measurements do not match deterministic "
                        "replay"
                    )
        if result.get("result") == "demonstrated":
            if attestation.get("exerciseMode") in {
                "tabletop",
                "deterministic_simulation",
            }:
                errors.append(
                    f"{owner} cannot be demonstrated by "
                    f"{attestation.get('exerciseMode')}"
                )
            missing_capabilities = required - demonstrated
            if missing_capabilities:
                errors.append(
                    f"{owner} is demonstrated without required capabilities: "
                    + ", ".join(sorted(missing_capabilities))
                )
            missing_evidence = set(claim.get("evidenceRequirementRefs", [])) - set(
                result.get("evidenceRequirementRefs", [])
            )
            if missing_evidence:
                errors.append(
                    f"{owner} is demonstrated without required evidence: "
                    + ", ".join(sorted(missing_evidence))
                )
        if demonstrated:
            unsatisfied = (
                set(result.get("evidenceRequirementRefs", [])) - satisfied_evidence
            )
            if unsatisfied:
                errors.append(
                    f"{owner} demonstrates capabilities without satisfied evidence "
                    "observations: " + ", ".join(sorted(unsatisfied))
                )
            conflicting = (
                set(result.get("evidenceRequirementRefs", [])) & adverse_evidence
            )
            if conflicting:
                errors.append(
                    f"{owner} cites evidence with unresolved adverse observations: "
                    + ", ".join(sorted(conflicting))
                )

        human_capabilities = {"handover", "human_takeover"} & demonstrated
        if human_capabilities:
            errors.append(
                f"{owner} cannot demonstrate human capability until trusted issuer "
                "signature verification is implemented"
            )
            if attestation.get("exerciseMode") not in {
                "sandbox",
                "live_drill",
                "production_like",
            }:
                errors.append(
                    f"{owner} cannot demonstrate human capability in "
                    f"{attestation.get('exerciseMode')} mode"
                )
            if participation.get("mode") not in {"facilitated", "live"}:
                errors.append(
                    f"{owner} requires facilitated or live human participation"
                )
            scenario_parameters = {
                item.get("name"): item.get("value")
                for item in (scenario or {})
                .get("executionPlan", {})
                .get("parameters", [])
            }
            declared_operator_count = scenario_parameters.get("operator_count", 1)
            if type(declared_operator_count) is not int or declared_operator_count < 1:
                errors.append(
                    f"{owner} scenario operator_count is not a positive integer: "
                    f"{declared_operator_count!r}"
                )
                minimum_participants = 1
            else:
                minimum_participants = declared_operator_count
            if participation.get("participantCount", 0) < minimum_participants:
                errors.append(
                    f"{owner} requires at least {minimum_participants} "
                    "participating humans"
                )
            if any(item.get("simulated") is not False for item in participants):
                errors.append(f"{owner} includes simulated human participants")
            if any(item.get("qualified") is not True for item in participants):
                errors.append(f"{owner} includes unqualified human participants")
            human_bindings = (
                (scenario or {}).get("executionPlan", {}).get("humanEvidenceBindings")
            )
            if not isinstance(human_bindings, dict):
                errors.append(
                    f"{owner} requires scenario humanEvidenceBindings for "
                    "qualification, authority, and operational access"
                )
                human_bindings = {}
            qualification_binding = human_bindings.get("qualification", {})
            authority_binding = human_bindings.get("authority", {})
            access_binding = human_bindings.get("operationalAccess", {})
            for participant in participants:
                participant_id = participant.get(
                    "participantId", "<unknown-participant>"
                )
                evidence_errors = validate_human_evidence(
                    participant.get("qualificationEvidence"),
                    base_dir=artifact_base,
                    artifact_root=artifact_root,
                    scenario_ref=str(scenario_ref),
                    environment_ref=environment_ref,
                    evidence_type="qualification",
                    subject_refs={participant_id},
                    object_refs={str(qualification_binding.get("objectRef", ""))},
                    covers=set(qualification_binding.get("covers", [])),
                    as_of=as_of,
                )
                errors.extend(
                    f"{owner} qualification artifact[{participant_id}]: {error}"
                    for error in evidence_errors
                )
            authority_participants: set[str] = set()
            for item in participation.get("authorityEvidence", []):
                participant_ref = item.get("participantRef", "<unknown-participant>")
                evidence_errors = validate_human_evidence(
                    item.get("artifact"),
                    base_dir=artifact_base,
                    artifact_root=artifact_root,
                    scenario_ref=str(scenario_ref),
                    environment_ref=environment_ref,
                    evidence_type="authority",
                    subject_refs={participant_ref},
                    object_refs={str(authority_binding.get("objectRef", ""))},
                    covers=set(authority_binding.get("covers", [])),
                    as_of=as_of,
                )
                if not evidence_errors:
                    authority_participants.add(participant_ref)
                errors.extend(
                    f"{owner} authority artifact[{participant_ref}]: {error}"
                    for error in evidence_errors
                )
            access_participants: set[str] = set()
            for item in participation.get("operationalAccessEvidence", []):
                participant_ref = item.get("participantRef", "<unknown-participant>")
                evidence_errors = validate_human_evidence(
                    item.get("artifact"),
                    base_dir=artifact_base,
                    artifact_root=artifact_root,
                    scenario_ref=str(scenario_ref),
                    environment_ref=environment_ref,
                    evidence_type="operational_access",
                    subject_refs={participant_ref},
                    object_refs={str(access_binding.get("objectRef", ""))},
                    covers=set(access_binding.get("covers", [])),
                    as_of=as_of,
                )
                if not evidence_errors:
                    access_participants.add(participant_ref)
                errors.extend(
                    f"{owner} operational-access artifact[{participant_ref}]: {error}"
                    for error in evidence_errors
                )
            missing_authority = participant_ids - authority_participants
            missing_access = participant_ids - access_participants
            if missing_authority:
                errors.append(
                    f"{owner} lacks participant authority artifacts: "
                    + ", ".join(sorted(missing_authority))
                )
            if missing_access:
                errors.append(
                    f"{owner} lacks participant operational-access artifacts: "
                    + ", ".join(sorted(missing_access))
                )
            if participation.get("authorityVerified") is not True:
                errors.append(f"{owner} did not verify human authority")
            if participation.get("operationalAccessVerified") is not True:
                errors.append(f"{owner} did not verify human operational access")
            cited_evidence = set(result.get("evidenceRequirementRefs", []))
            if "human-handover" not in cited_evidence:
                errors.append(f"{owner} does not cite human-handover evidence")
            elif "human-handover" not in satisfied_evidence:
                errors.append(f"{owner} has no satisfied human-handover evidence")
            elif "human-handover" in adverse_evidence:
                errors.append(f"{owner} has unresolved adverse human-handover evidence")

    for fault in attestation.get("actualConditions", {}).get("faultSchedule", []):
        fault_id = fault.get("faultId", "<unknown-fault>")
        fault_started = _parse_time(
            fault.get("startedAt"), f"faultSchedule[{fault_id}].startedAt", errors
        )
        fault_completed = _parse_time(
            fault.get("completedAt"),
            f"faultSchedule[{fault_id}].completedAt",
            errors,
        )
        if fault_started and fault_completed and fault_completed < fault_started:
            errors.append(f"faultSchedule[{fault_id}] completes before it starts")
        if started and fault_started and fault_started < started:
            errors.append(f"faultSchedule[{fault_id}] starts before the exercise")
        if completed and fault_completed and fault_completed > completed:
            errors.append(f"faultSchedule[{fault_id}] ends after the exercise")

    return errors


def _load_yaml(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a mapping")
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", type=pathlib.Path)
    parser.add_argument("--attestation", action="append", type=pathlib.Path, default=[])
    parser.add_argument(
        "--artifact-root",
        type=pathlib.Path,
        help="root boundary for local artifacts referenced by attestations",
    )
    parser.add_argument(
        "--as-of",
        default=dt.datetime.now(dt.timezone.utc).isoformat(),
        help="RFC 3339 time used for staleness checks",
    )
    args = parser.parse_args()

    try:
        profile = _load_yaml(args.profile)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(exc, file=sys.stderr)
        return 2

    errors = validate_profile(profile)
    as_of_errors: list[str] = []
    as_of = _parse_time(args.as_of, "--as-of", as_of_errors)
    errors.extend(as_of_errors)
    if as_of:
        for path in args.attestation:
            try:
                attestation = _load_yaml(path)
            except (OSError, ValueError, yaml.YAMLError) as exc:
                errors.append(str(exc))
                continue
            errors.extend(
                validate_attestation(
                    profile,
                    attestation,
                    as_of,
                    artifact_base=path.parent,
                    artifact_root=args.artifact_root,
                )
            )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("ok -- semantic validation done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
