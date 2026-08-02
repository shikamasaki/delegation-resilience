#!/usr/bin/env python3
"""Fail-closed preflight for the facilitated Refund human-takeover drill."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import pathlib
import sys
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from game_days.refund.runner import canonical_digest
from tools.artifact_validation import load_local_artifact, validate_human_evidence
from tools.data_loading import load_data, load_data_bytes
from tools.schema_validation import schema_errors
from tools.trust import VerifiedStatement, validate_trust_policy, verify_dsse_envelope

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
    "a current external trust policy and trusted DSSE proof are required for every "
    "human evidence artifact"
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
    messages = [
        "preflight manifest schema: "
        + (".".join(str(item) for item in error.path) or "<root>")
        + f": {error.message}"
        for error in errors
    ]
    if manifest.get("apiVersion") == "delegation-resilience.org/v0alpha1":
        v0alpha2_fields = {
            "preflightRunId",
            "challenge",
            "abortAuthorityId",
            "facilitatorAssignmentEvidence",
            "abortAuthorityAssignmentEvidence",
            "briefingArtifact",
            "participantDataUse",
            "participantAcknowledgements",
            "withdrawalStatusEvidence",
        }
        present = sorted(v0alpha2_fields & set(manifest))
        if present:
            messages.append(
                "v0alpha1 preflight cannot contain v0alpha2 fields: "
                + ", ".join(present)
            )

        def has_proof(value: Any) -> bool:
            if isinstance(value, dict):
                return "proof" in value or any(
                    has_proof(item) for item in value.values()
                )
            if isinstance(value, list):
                return any(has_proof(item) for item in value)
            return False

        if has_proof(manifest):
            messages.append("v0alpha1 preflight cannot contain trust-proof references")
    return messages


def preflight_context_digest(manifest: dict[str, Any]) -> str:
    """Bind participant statements to the non-participant preflight context."""
    context = copy.deepcopy(manifest)
    context.pop("participantAcknowledgements", None)
    context.pop("withdrawalStatusEvidence", None)
    return canonical_digest(context)


def _report(
    profile: dict[str, Any],
    manifest: dict[str, Any],
    missing: list[str],
    *,
    participant_count: int,
    required_count: int,
    evaluated_at: dt.datetime,
    trust_policy: dict[str, Any] | None,
    min_policy_sequence: int | None,
    participant_sequence_highwatermarks: dict[str, Any] | None,
) -> dict[str, Any]:
    digest_bound_prerequisites = [item for item in missing if item != TRUST_GATE]
    return {
        "preflight": "refund-human-takeover/v0alpha2",
        "scenarioRef": SCENARIO_ID,
        "evaluatedAt": evaluated_at.isoformat().replace("+00:00", "Z"),
        "evaluatedProfileDigest": canonical_digest(profile),
        "manifestDigest": canonical_digest(manifest),
        "preflightRunId": manifest.get("preflightRunId"),
        "challenge": manifest.get("challenge"),
        "preflightContextDigest": preflight_context_digest(manifest),
        "trustPolicy": (
            {
                "id": trust_policy.get("metadata", {}).get("id"),
                "digest": canonical_digest(trust_policy),
                "sequenceNumber": trust_policy.get("sequenceNumber"),
                "minimumSequenceNumber": min_policy_sequence,
            }
            if trust_policy is not None
            else None
        ),
        "participantSequenceHighWatermarks": (
            {
                "digest": canonical_digest(participant_sequence_highwatermarks),
                "participantStatements": participant_sequence_highwatermarks.get(
                    "participantStatements", {}
                ),
            }
            if participant_sequence_highwatermarks is not None
            else None
        ),
        "ready": not missing,
        "digestBoundPrerequisitesComplete": not digest_bound_prerequisites,
        "trustedIssuerVerificationImplemented": True,
        "trustedEvidenceComplete": not missing,
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
    trust_policy: dict[str, Any] | None = None,
    min_policy_sequence: int | None = None,
    participant_sequence_highwatermarks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate prerequisites without promoting any recovery capability."""
    scenario = _scenario(profile)
    parameters = _parameters(scenario)
    schema_missing = _manifest_schema_errors(manifest)
    missing = list(schema_missing)
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
    trusted_domains: set[str] = set()
    trusted_issuer_ids: set[tuple[str, str]] = set()
    if trust_policy is None:
        missing.append(TRUST_GATE)
    else:
        missing.extend(validate_trust_policy(trust_policy, as_of=evaluation_time))
        if min_policy_sequence is None:
            missing.append("a minimum trust-policy sequence high-watermark is required")
        elif trust_policy.get("sequenceNumber", 0) < min_policy_sequence:
            missing.append(
                "TRUST_POLICY_ROLLBACK: sequenceNumber is below the required minimum"
            )
        if participant_sequence_highwatermarks is None:
            missing.append(
                "consumer-held participant statement sequence high-watermarks are required"
            )

    def verify_trust(
        reference: Any, *, label: str, count_independence: bool = True
    ) -> VerifiedStatement | None:
        if (
            trust_policy is None
            or evidence_root is None
            or not isinstance(reference, dict)
        ):
            return None
        content, content_errors = load_local_artifact(
            reference, base_dir=evidence_root, artifact_root=evidence_root
        )
        proof_content, proof_errors = load_local_artifact(
            reference.get("proof"), base_dir=evidence_root, artifact_root=evidence_root
        )
        for error in content_errors + proof_errors:
            missing.append(f"{label} trust proof: {error}")
        if content is None or proof_content is None:
            return None
        try:
            evidence = load_data_bytes(content, source=f"{label} artifact")
        except ValueError as exc:
            missing.append(f"{label} trust proof: {exc}")
            return None
        if evidence.get("apiVersion") != "delegation-resilience.org/v0alpha2":
            missing.append(
                f"{label} trust proof: trusted human-drill evidence requires v0alpha2"
            )
            return None
        payload_type = (
            "application/vnd.delegation-resilience.human-evidence.v0alpha2+json"
            if evidence.get("apiVersion") == "delegation-resilience.org/v0alpha2"
            else "application/vnd.delegation-resilience.human-evidence.v0alpha1+json"
        )
        statement, proof_validation_errors = verify_dsse_envelope(
            proof_content,
            trust_policy=trust_policy,
            purpose="human_evidence",
            as_of=evaluation_time,
            expected_payload=content,
            expected_payload_type=payload_type,
        )
        missing.extend(
            f"{label} trust proof: {error}" for error in proof_validation_errors
        )
        if statement is not None:
            protected_human_ids = {
                manifest.get("facilitatorId"),
                manifest.get("abortAuthorityId"),
                *(
                    item.get("participantId")
                    for item in manifest.get("participants", [])
                    if isinstance(item, dict)
                ),
            }
            self_statement = evidence.get("evidenceType") in {
                "participant_acknowledgement",
                "withdrawal_status",
            }
            if not self_statement and statement.issuer.get("id") in protected_human_ids:
                missing.append(
                    f"{label} issuer must be separate from participants, facilitator, and abort authority"
                )
                return None
            if count_independence:
                trusted_domains.add(statement.independence_domain)
                trusted_issuer_ids.add(
                    (str(statement.issuer.get("id")), str(statement.issuer.get("type")))
                )
        return statement

    if schema_missing:
        participants = manifest.get("participants", [])
        participant_count = len(participants) if isinstance(participants, list) else 0
        return _report(
            profile,
            manifest,
            missing,
            participant_count=participant_count,
            required_count=required_count,
            evaluated_at=evaluation_time,
            trust_policy=trust_policy,
            min_policy_sequence=min_policy_sequence,
            participant_sequence_highwatermarks=participant_sequence_highwatermarks,
        )

    if manifest.get("scenarioRef") != SCENARIO_ID:
        missing.append(
            "manifest scenarioRef must identify the facilitated takeover scenario"
        )
    if scenario.get("exerciseMode") != "sandbox":
        missing.append("the facilitated takeover scenario must remain sandbox-only")
    if manifest.get("apiVersion") != "delegation-resilience.org/v0alpha2":
        missing.append("trusted human-drill preflight requires a v0alpha2 manifest")

    environment_id = manifest.get("sandboxEnvironmentId", "")
    if not environment_id or environment_id == "UNPROVISIONED":
        missing.append("a provisioned sandbox environment must be identified")
    if (
        not manifest.get("facilitatorId")
        or manifest.get("facilitatorId") == "UNASSIGNED"
    ):
        missing.append("an accountable facilitator must be assigned")
    if (
        not manifest.get("abortAuthorityId")
        or manifest.get("abortAuthorityId") == "UNASSIGNED"
    ):
        missing.append("an independently identified abort authority must be assigned")
    if manifest.get("abortAuthorityId") == manifest.get("facilitatorId"):
        missing.append("abort authority must be distinct from the facilitator")
    if not manifest.get("challenge") or str(manifest.get("challenge")).startswith(
        ("UNPROVISIONED", "PLACEHOLDER")
    ):
        missing.append("a one-time non-placeholder preflight challenge is required")

    if participant_sequence_highwatermarks is not None:
        missing.extend(
            "participant high-watermarks schema: " + item
            for item in schema_errors(
                "participant-sequence-highwatermarks.schema.json",
                participant_sequence_highwatermarks,
            )
        )
        expected_policy_ref = (
            trust_policy.get("metadata", {}).get("id") if trust_policy else None
        )
        if (
            participant_sequence_highwatermarks.get("trustPolicyRef")
            != expected_policy_ref
        ):
            missing.append("participant high-watermarks bind the wrong trust policy")
        if participant_sequence_highwatermarks.get("trustPolicySequenceNumber") != (
            trust_policy or {}
        ).get("sequenceNumber"):
            missing.append(
                "participant high-watermarks bind the wrong trust-policy sequence"
            )
        if participant_sequence_highwatermarks.get("preflightRunId") != manifest.get(
            "preflightRunId"
        ):
            missing.append("participant high-watermarks bind the wrong preflight run")
        if participant_sequence_highwatermarks.get("challenge") != manifest.get(
            "challenge"
        ):
            missing.append("participant high-watermarks bind the wrong challenge")

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
    if manifest.get("abortAuthorityId") in set(participant_ids):
        missing.append("abort authority must be distinct from every participant")

    briefing_bytes, briefing_errors = load_local_artifact(
        manifest.get("briefingArtifact"),
        base_dir=evidence_root,
        artifact_root=evidence_root,
    )
    missing.extend(f"briefing artifact: {item}" for item in briefing_errors)
    briefing_digest = None
    if briefing_bytes is not None:
        briefing_digest = "sha256:" + hashlib.sha256(briefing_bytes).hexdigest()

    role_assignments = [
        (
            "facilitatorAssignmentEvidence",
            "facilitator_assignment",
            str(manifest.get("facilitatorId", "")),
            {"facilitator_accountability"},
        ),
        (
            "abortAuthorityAssignmentEvidence",
            "abort_authority_assignment",
            str(manifest.get("abortAuthorityId", "")),
            {"abort_authority"},
        ),
    ]
    for field, evidence_type, subject, covers in role_assignments:
        evidence_errors = validate_human_evidence(
            manifest.get(field),
            base_dir=evidence_root,
            artifact_root=evidence_root,
            scenario_ref=SCENARIO_ID,
            environment_ref=manifest["sandboxEnvironmentId"],
            evidence_type=evidence_type,
            subject_refs={subject},
            object_refs={SCENARIO_ID},
            covers=covers,
            as_of=evaluation_time,
        )
        missing.extend(f"{field}: {item}" for item in evidence_errors)
        if (
            not evidence_errors
            and trust_policy is not None
            and verify_trust(manifest.get(field), label=field) is None
        ):
            missing.append(f"{field} lacks a trusted independent issuer")
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
        if not evidence_errors:
            verify_trust(
                participant.get("qualificationEvidence"),
                label=f"qualification evidence[{participant_id}]",
            )

    participant_set = {item for item in participant_ids if item}
    authority_verified: set[str] = set()
    for item in manifest.get("authorityVerifications", []):
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
            verify_trust(
                item.get("evidence"), label=f"authority evidence[{participant_ref}]"
            )
            authority_verified.add(participant_ref)
        missing.extend(
            f"authority evidence[{participant_ref}]: {error}"
            for error in evidence_errors
        )
    access_verified: set[str] = set()
    for item in manifest.get("operationalAccessVerifications", []):
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
            verify_trust(
                item.get("evidence"),
                label=f"operational-access evidence[{participant_ref}]",
            )
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
        item.get("participantRef")
        for item in manifest.get("authorityVerifications", [])
    ]
    access_refs = [
        item.get("participantRef")
        for item in manifest.get("operationalAccessVerifications", [])
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
            verify_trust(
                observation.get("evidence"),
                label=f"operator-channel evidence[{index}]",
            )
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
            verify_trust(
                observation.get("evidence"),
                label=f"participant-safeguard evidence[{index}]",
            )
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

    participant_statement_sequences: dict[str, dict[str, int]] = {}
    expected_profile_digest = canonical_digest(profile)
    expected_context_digest = preflight_context_digest(manifest)

    def verify_participant_statements(
        field: str,
        evidence_type: str,
        required_covers: set[str],
        *,
        participant_decision: str | None = None,
        participant_status: str | None = None,
    ) -> None:
        observations = manifest.get(field, [])
        refs = [item.get("participantRef") for item in observations]
        if len(refs) != len(set(refs)):
            missing.append(f"{field} participantRefs must be unique")
        verified: set[str] = set()
        for item in observations:
            participant_ref = item.get("participantRef")
            if participant_ref not in participant_set:
                missing.append(f"{field} references an unknown participant")
                continue
            evidence_errors = validate_human_evidence(
                item.get("evidence"),
                base_dir=evidence_root,
                artifact_root=evidence_root,
                scenario_ref=SCENARIO_ID,
                environment_ref=manifest["sandboxEnvironmentId"],
                evidence_type=evidence_type,
                subject_refs={participant_ref},
                object_refs={SCENARIO_ID},
                covers=required_covers,
                as_of=evaluation_time,
                expected_finding="satisfied",
                participant_decision=participant_decision,
                participant_status=participant_status,
            )
            missing.extend(
                f"{field}[{participant_ref}]: {error}" for error in evidence_errors
            )
            if not evidence_errors:
                statement = verify_trust(
                    item.get("evidence"),
                    label=f"{field}[{participant_ref}]",
                    count_independence=False,
                )
                if statement is None:
                    continue
                payload = statement.payload
                expected_bindings = {
                    "preflightRunId": manifest.get("preflightRunId"),
                    "challenge": manifest.get("challenge"),
                    "profileDigest": expected_profile_digest,
                    "preflightContextDigest": expected_context_digest,
                    "briefingArtifactDigest": briefing_digest,
                }
                binding_errors = [
                    f"{name} does not bind the current preflight"
                    for name, expected in expected_bindings.items()
                    if payload.get(name) != expected
                ]
                missing.extend(
                    f"{field}[{participant_ref}]: {error}" for error in binding_errors
                )
                sequence = payload.get("statementSequence")
                if type(sequence) is not int or sequence < 1:
                    missing.append(
                        f"{field}[{participant_ref}]: statementSequence is invalid"
                    )
                    continue
                participant_statement_sequences.setdefault(participant_ref, {})[
                    evidence_type
                ] = sequence
                if evidence_type == "withdrawal_status":
                    held_statement = (
                        (participant_sequence_highwatermarks or {})
                        .get("participantStatements", {})
                        .get(participant_ref)
                    )
                    if not isinstance(held_statement, dict):
                        missing.append(
                            f"{field}[{participant_ref}]: consumer high-watermark is missing"
                        )
                    else:
                        held_sequence = held_statement.get("sequence")
                        held_status = held_statement.get("status")
                        held_digest = held_statement.get("statementDigest")
                        incoming_status = payload.get("participantStatus")
                        incoming_digest = statement.subject_digest
                        if held_status == "withdrawn":
                            missing.append(
                                f"{field}[{participant_ref}]: consumer has already observed withdrawal"
                            )
                        elif type(held_sequence) is not int:
                            missing.append(
                                f"{field}[{participant_ref}]: consumer high-watermark sequence is invalid"
                            )
                        elif sequence < held_sequence:
                            missing.append(
                                f"{field}[{participant_ref}]: stale participant status sequence"
                            )
                        elif sequence == held_sequence and (
                            held_status != incoming_status
                            or held_digest != incoming_digest
                        ):
                            missing.append(
                                f"{field}[{participant_ref}]: equal-sequence participant status equivocation"
                            )
                if not binding_errors:
                    verified.add(participant_ref)
        absent = participant_set - verified
        if absent and trust_policy is not None:
            missing.append(
                f"{field} is missing trusted participant statements: "
                + ", ".join(sorted(absent))
            )

    verify_participant_statements(
        "participantAcknowledgements",
        "participant_acknowledgement",
        {"briefing_consent", "data_use_retention", "operator_abort_rights"},
        participant_decision="acknowledged",
    )
    verify_participant_statements(
        "withdrawalStatusEvidence",
        "withdrawal_status",
        {"active_participation"},
        participant_status="active",
    )

    highwater_participants = set(
        (participant_sequence_highwatermarks or {}).get("participantStatements", {})
    )
    if trust_policy is not None and highwater_participants != participant_set:
        missing.append(
            "participant high-watermarks must exactly cover current participants"
        )
    for participant_ref, sequences in participant_statement_sequences.items():
        acknowledgement = sequences.get("participant_acknowledgement")
        status = sequences.get("withdrawal_status")
        if (
            acknowledgement is not None
            and status is not None
            and status < acknowledgement
        ):
            missing.append(
                f"withdrawalStatusEvidence[{participant_ref}] predates acknowledgement"
            )

    if trust_policy is not None:
        minimum_domains = trust_policy.get("humanEvidenceRules", {}).get(
            "minimumIndependenceDomains", 2
        )
        if len(trusted_domains) < minimum_domains:
            missing.append(
                "trusted human evidence does not span the required independence domains"
            )
        if len(trusted_issuer_ids) < minimum_domains:
            missing.append(
                "trusted human evidence does not span the required independent issuer identities"
            )
    return _report(
        profile,
        manifest,
        missing,
        participant_count=len(participants),
        required_count=required_count,
        evaluated_at=evaluation_time,
        trust_policy=trust_policy,
        min_policy_sequence=min_policy_sequence,
        participant_sequence_highwatermarks=participant_sequence_highwatermarks,
    )


def _load_yaml(path: pathlib.Path) -> dict[str, Any]:
    return load_data(path)


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
        "--trust-policy",
        type=pathlib.Path,
        help="external trust policy; bundle-supplied keys are never trusted",
    )
    parser.add_argument(
        "--as-of",
        default=dt.datetime.now(dt.timezone.utc).isoformat(),
        help="RFC 3339 time used for evidence freshness checks",
    )
    parser.add_argument(
        "--min-policy-sequence",
        type=int,
        help="consumer-held trust-policy high-watermark (required with --trust-policy)",
    )
    parser.add_argument(
        "--participant-sequence-highwatermarks",
        type=pathlib.Path,
        help=(
            "consumer-held latest participant statement sequence/status/digest; "
            "required with --trust-policy and refreshed immediately before fault injection"
        ),
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
            trust_policy=load_data(args.trust_policy) if args.trust_policy else None,
            min_policy_sequence=args.min_policy_sequence,
            participant_sequence_highwatermarks=(
                load_data(args.participant_sequence_highwatermarks)
                if args.participant_sequence_highwatermarks
                else None
            ),
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
