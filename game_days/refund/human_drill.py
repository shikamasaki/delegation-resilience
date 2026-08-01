#!/usr/bin/env python3
"""Fail-closed preflight for the facilitated Refund human-takeover drill."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from game_days.refund.runner import canonical_digest
from tools.artifact_validation import validate_human_evidence

SCENARIO_ID = "refund-facilitated-human-takeover"
INDEPENDENCE_BOUNDARIES = {
    "identity",
    "policy",
    "provider_outcome",
    "agent_connector",
}
HUMAN_SAFEGUARDS = {
    "briefing_consent",
    "data_use_retention",
    "operator_abort_rights",
    "fatigue_shift_plan",
}
OPERATOR_CHANNEL_SUBJECT = {"customer-operations-channel"}
TRUST_GATE = (
    "trusted issuer signature verification is not implemented; preflight remains "
    "advisory"
)
PREFLIGHT_SCHEMA = (
    pathlib.Path(__file__).resolve().parents[2]
    / "profiles"
    / "transactional-action"
    / "schema"
    / "human-drill-preflight.schema.json"
)


def _manifest_schema_errors(manifest: dict[str, Any]) -> list[str]:
    schema = json.loads(PREFLIGHT_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(manifest), key=lambda item: list(item.path))
    return [
        "preflight manifest schema: "
        + (".".join(str(item) for item in error.path) or "<root>")
        + f": {error.message}"
        for error in errors
    ]


def _report(
    profile: dict[str, Any],
    manifest: dict[str, Any],
    missing: list[str],
    *,
    participant_count: int,
    required_count: int,
) -> dict[str, Any]:
    digest_bound_prerequisites = [item for item in missing if item != TRUST_GATE]
    return {
        "preflight": "refund-human-takeover/v0alpha1",
        "scenarioRef": SCENARIO_ID,
        "evaluatedProfileDigest": canonical_digest(profile),
        "manifestDigest": canonical_digest(manifest),
        "ready": False,
        "digestBoundPrerequisitesComplete": not digest_bound_prerequisites,
        "trustedIssuerVerificationImplemented": False,
        "missingPrerequisites": missing,
        "declaredOperatorCount": participant_count,
        "requiredOperatorCount": required_count,
        "claimResultCeilingBeforeCompletedDrill": "not_demonstrated",
        "humanTakeoverMayBeClaimed": False,
        "reason": (
            "Preflight readiness is not exercise evidence. human_takeover can only be "
            "claimed by a completed, semantically valid Attestation with facilitated "
            "or live participants, verified authority, verified access, observed "
            "human-handover evidence, and trusted issuer signature verification."
        ),
    }


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


def evaluate_readiness(
    profile: dict[str, Any],
    manifest: dict[str, Any],
    *,
    evidence_root: pathlib.Path | None = None,
    as_of: dt.datetime | None = None,
) -> dict[str, Any]:
    """Evaluate prerequisites without promoting any recovery capability."""
    scenario = _scenario(profile)
    parameters = _parameters(scenario)
    missing = _manifest_schema_errors(manifest)
    bindings = scenario.get("executionPlan", {}).get("humanEvidenceBindings", {})
    missing_binding_names = {
        "qualification",
        "authority",
        "operationalAccess",
    } - set(bindings)
    if missing_binding_names:
        missing.append(
            "scenario humanEvidenceBindings are missing: "
            + ", ".join(sorted(missing_binding_names))
        )
    qualification_binding = bindings.get("qualification", {})
    authority_binding = bindings.get("authority", {})
    access_binding = bindings.get("operationalAccess", {})

    declared_operator_count = parameters["operator_count"]
    if type(declared_operator_count) is not int or declared_operator_count < 1:
        raise ValueError("operator_count must be a positive integer")
    required_count = declared_operator_count
    evaluation_time = as_of or dt.datetime.now(dt.timezone.utc)
    if missing:
        missing.append(TRUST_GATE)
        participants = manifest.get("participants", [])
        participant_count = len(participants) if isinstance(participants, list) else 0
        return _report(
            profile,
            manifest,
            missing,
            participant_count=participant_count,
            required_count=required_count,
        )

    if manifest.get("scenarioRef") != SCENARIO_ID:
        missing.append(
            "manifest scenarioRef must identify the facilitated takeover scenario"
        )
    if scenario.get("exerciseMode") != "sandbox":
        missing.append("the facilitated takeover scenario must remain sandbox-only")

    environment_id = manifest.get("sandboxEnvironmentId", "")
    if not environment_id or environment_id == "UNPROVISIONED":
        missing.append("a provisioned sandbox environment must be identified")
    if not manifest.get("facilitatorId"):
        missing.append("an accountable facilitator must be assigned")

    participants = manifest.get("participants", [])
    participant_ids = [item.get("participantId") for item in participants]
    if len(participants) < required_count:
        missing.append(
            f"at least {required_count} real qualified operators are required"
        )
    if len({item for item in participant_ids if item}) != len(participants):
        missing.append("participant IDs must be present and unique")
    if any(item.get("simulated") is not False for item in participants):
        missing.append("simulated participants cannot qualify the human takeover drill")
    for participant in participants:
        participant_id = participant["participantId"]
        evidence_errors = validate_human_evidence(
            participant.get("qualificationEvidence"),
            base_dir=evidence_root,
            artifact_root=evidence_root,
            scenario_ref=SCENARIO_ID,
            environment_ref=manifest["sandboxEnvironmentId"],
            evidence_type="qualification",
            subject_refs={participant_id},
            object_refs={str(qualification_binding.get("objectRef", ""))},
            covers=set(qualification_binding.get("covers", [])),
            as_of=evaluation_time,
        )
        missing.extend(
            f"qualification evidence[{participant_id}]: {error}"
            for error in evidence_errors
        )

    participant_set = {item for item in participant_ids if item}
    authority_verified: set[str] = set()
    for item in manifest["authorityVerifications"]:
        participant_ref = item["participantRef"]
        evidence_errors = validate_human_evidence(
            item.get("evidence"),
            base_dir=evidence_root,
            artifact_root=evidence_root,
            scenario_ref=SCENARIO_ID,
            environment_ref=manifest["sandboxEnvironmentId"],
            evidence_type="authority",
            subject_refs={participant_ref},
            object_refs={str(authority_binding.get("objectRef", ""))},
            covers=set(authority_binding.get("covers", [])),
            as_of=evaluation_time,
        )
        if not evidence_errors:
            authority_verified.add(participant_ref)
        missing.extend(
            f"authority evidence[{participant_ref}]: {error}"
            for error in evidence_errors
        )
    access_verified: set[str] = set()
    for item in manifest["operationalAccessVerifications"]:
        participant_ref = item["participantRef"]
        evidence_errors = validate_human_evidence(
            item.get("evidence"),
            base_dir=evidence_root,
            artifact_root=evidence_root,
            scenario_ref=SCENARIO_ID,
            environment_ref=manifest["sandboxEnvironmentId"],
            evidence_type="operational_access",
            subject_refs={participant_ref},
            object_refs={str(access_binding.get("objectRef", ""))},
            covers=set(access_binding.get("covers", [])),
            as_of=evaluation_time,
        )
        if not evidence_errors:
            access_verified.add(participant_ref)
        missing.extend(
            f"operational-access evidence[{participant_ref}]: {error}"
            for error in evidence_errors
        )
    if participant_set - authority_verified:
        missing.append(
            "every participant needs sandbox authority verification evidence"
        )
    if participant_set - access_verified:
        missing.append(
            "every participant needs operational access verification evidence"
        )
    authority_refs = [
        item.get("participantRef") for item in manifest["authorityVerifications"]
    ]
    access_refs = [
        item.get("participantRef")
        for item in manifest["operationalAccessVerifications"]
    ]
    if len(authority_refs) != len(set(authority_refs)):
        missing.append("authority verification participantRefs must be unique")
    if len(access_refs) != len(set(access_refs)):
        missing.append("operational access participantRefs must be unique")
    if set(authority_refs) - participant_set:
        missing.append("authority verification references an unknown participant")
    if set(access_refs) - participant_set:
        missing.append(
            "operational access verification references an unknown participant"
        )

    controls = manifest.get("controls", {})
    required_controls = {
        "faultInjectionApproved": "fault injection must be approved",
        "providerSandboxReady": "the refund provider sandbox must be ready",
        "evidenceSinkReady": "the evidence sink must be ready",
        "handoverTimerReady": "the 15-minute handover timer must be ready",
        "missionClockReady": "the 24-hour mission clock must be ready",
        "abortAuthorityAssigned": "abort authority must be assigned",
        "participantBriefingAndConsentRecorded": (
            "participant briefing and consent must be recorded"
        ),
        "operatorAbortRightsConfirmed": (
            "each operator's right to pause or withdraw must be confirmed"
        ),
        "fatigueAndShiftPlanReady": (
            "a fatigue-aware shift and reserve staffing plan must be ready"
        ),
    }
    for field, message in required_controls.items():
        if controls.get(field) is not True:
            missing.append(message)

    independence = manifest.get("operatorChannelIndependenceEvidence", [])
    covered_boundaries: set[str] = set()
    for index, observation in enumerate(independence):
        declared_covers = set(observation["covers"])
        evidence_errors = validate_human_evidence(
            observation.get("evidence"),
            base_dir=evidence_root,
            artifact_root=evidence_root,
            scenario_ref=SCENARIO_ID,
            environment_ref=manifest["sandboxEnvironmentId"],
            evidence_type="channel_independence",
            subject_refs=OPERATOR_CHANNEL_SUBJECT,
            object_refs={"customer-operations-channel"},
            covers=declared_covers,
            as_of=evaluation_time,
        )
        if not evidence_errors:
            covered_boundaries.update(declared_covers)
        missing.extend(
            f"operator-channel evidence[{index}]: {error}" for error in evidence_errors
        )
    missing_boundaries = INDEPENDENCE_BOUNDARIES - covered_boundaries
    if missing_boundaries:
        missing.append(
            "operator-channel independence requires digest-bound evidence for: "
            + ", ".join(sorted(missing_boundaries))
        )

    safeguard_observations = manifest.get("participantSafeguardEvidence", [])
    covered_safeguards: set[str] = set()
    for index, observation in enumerate(safeguard_observations):
        declared_covers = set(observation["covers"])
        evidence_errors = validate_human_evidence(
            observation.get("evidence"),
            base_dir=evidence_root,
            artifact_root=evidence_root,
            scenario_ref=SCENARIO_ID,
            environment_ref=manifest["sandboxEnvironmentId"],
            evidence_type="participant_safeguard",
            subject_refs=participant_set,
            object_refs={SCENARIO_ID},
            covers=declared_covers,
            as_of=evaluation_time,
        )
        if not evidence_errors:
            covered_safeguards.update(declared_covers)
        missing.extend(
            f"participant-safeguard evidence[{index}]: {error}"
            for error in evidence_errors
        )
    missing_safeguards = HUMAN_SAFEGUARDS - covered_safeguards
    if missing_safeguards:
        missing.append(
            "participant safeguards require digest-bound evidence for: "
            + ", ".join(sorted(missing_safeguards))
        )

    missing.append(TRUST_GATE)
    return _report(
        profile,
        manifest,
        missing,
        participant_count=len(participants),
        required_count=required_count,
    )


def _load_yaml(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a mapping")
    return value


def _report_bytes(report: dict[str, Any]) -> bytes:
    return (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def main() -> int:
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        type=pathlib.Path,
        default=repo_root / "examples" / "refund" / "profile.yaml",
    )
    parser.add_argument(
        "--as-of",
        default=dt.datetime.now(dt.timezone.utc).isoformat(),
        help="RFC 3339 time used for evidence freshness checks",
    )
    parser.add_argument(
        "--manifest",
        type=pathlib.Path,
        default=repo_root
        / "examples"
        / "refund"
        / "game-day"
        / "human-drill"
        / "preflight-input.yaml",
    )
    parser.add_argument(
        "--report",
        type=pathlib.Path,
        default=repo_root
        / "examples"
        / "refund"
        / "game-day"
        / "human-drill"
        / "preflight-report.json",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--check-ready", action="store_true")
    args = parser.parse_args()

    try:
        evaluation_time = dt.datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
        report = evaluate_readiness(
            _load_yaml(args.profile),
            _load_yaml(args.manifest),
            evidence_root=args.manifest.parent,
            as_of=evaluation_time,
        )
    except (KeyError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    expected = _report_bytes(report)
    if args.write:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes(expected)
        print(f"wrote human-drill preflight report to {args.report}")
        return 0
    if args.verify:
        if not args.report.exists() or args.report.read_bytes() != expected:
            print(
                f"ERROR: stale human-drill preflight report: {args.report}",
                file=sys.stderr,
            )
            return 1
        print("ok -- human-drill preflight report is reproducible")
        return 0

    if not report["ready"]:
        for item in report["missingPrerequisites"]:
            print(f"NOT READY: {item}", file=sys.stderr)
        return 1
    print("ready -- prerequisites are present; no capability is demonstrated yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
