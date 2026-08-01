#!/usr/bin/env python3
"""Cross-artifact semantic validation for DelegationResilienceProfile v0alpha1."""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys
from typing import Any

import yaml


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _check_refs(
    errors: list[str], owner: str, field: str, refs: list[str], available: set[str]
) -> None:
    for ref in refs:
        if ref not in available:
            errors.append(f"{owner}.{field} references missing ID: {ref}")


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
    scenarios = {
        item.get("scenarioId") for item in spec.get("exerciseScenarios", [])
    }

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
        "claimId": [
            item.get("claimId") for item in spec.get("recoveryClaims", [])
        ],
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

    return errors


def validate_attestation(
    profile: dict[str, Any], attestation: dict[str, Any], as_of: dt.datetime
) -> list[str]:
    """Validate an attestation against the profile and its evidence ceilings."""
    errors: list[str] = []
    spec = profile.get("spec", {})
    claims = {
        item.get("claimId"): item for item in spec.get("recoveryClaims", [])
    }
    scenarios = {
        item.get("scenarioId"): item for item in spec.get("exerciseScenarios", [])
    }
    evidence_ids = {
        item.get("evidenceId")
        for item in spec.get("evidenceProfile", {}).get("requirements", [])
    }

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

    measurements = {
        item.get("measurementId") for item in attestation.get("measurements", [])
    }
    observed_evidence = {
        item.get("evidenceRequirementRef") for item in attestation.get("evidence", [])
    }
    _check_refs(
        errors,
        "attestation",
        "evidenceRequirementRefs",
        list(observed_evidence),
        evidence_ids,
    )

    for result in attestation.get("claimResults", []):
        claim_ref = result.get("claimRef")
        claim = claims.get(claim_ref)
        owner = f"claimResult[{claim_ref}]"
        if claim is None:
            errors.append(f"{owner} references missing RecoveryClaim")
            continue

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
        if result.get("result") == "demonstrated":
            if attestation.get("exerciseMode") == "tabletop":
                errors.append(f"{owner} cannot be demonstrated by a tabletop exercise")
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
            unobserved = set(result.get("evidenceRequirementRefs", [])) - observed_evidence
            if unobserved:
                errors.append(
                    f"{owner} cites evidence not present in the attestation: "
                    + ", ".join(sorted(unobserved))
                )

        if "human_takeover" in demonstrated:
            participation = attestation.get("humanParticipation", {})
            if attestation.get("exerciseMode") not in {
                "sandbox",
                "live_drill",
                "production_like",
            }:
                errors.append(
                    f"{owner} cannot demonstrate human_takeover in "
                    f"{attestation.get('exerciseMode')} mode"
                )
            if participation.get("mode") not in {"facilitated", "live"}:
                errors.append(
                    f"{owner} requires facilitated or live human participation"
                )
            if participation.get("participantCount", 0) < 1:
                errors.append(f"{owner} has no participating human")
            if not participation.get("authorityVerified"):
                errors.append(f"{owner} did not verify human authority")
            if not participation.get("operationalAccessVerified"):
                errors.append(f"{owner} did not verify human operational access")

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
            errors.extend(validate_attestation(profile, attestation, as_of))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("ok -- semantic validation done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
