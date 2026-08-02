"""Local artifact integrity and structured human-evidence validation."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

try:
    from tools.data_loading import load_data_bytes
except ModuleNotFoundError:
    from data_loading import load_data_bytes

HUMAN_SCHEMA_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "profiles"
    / "transactional-action"
    / "schema"
    / "human-drill-evidence.schema.json"
)
EXERCISE_SCHEMA_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "profiles"
    / "transactional-action"
    / "schema"
    / "exercise-evidence.schema.json"
)


def _parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_local_artifact(
    reference: Any,
    *,
    base_dir: pathlib.Path | None,
    artifact_root: pathlib.Path | None,
    strict_paths: bool = False,
) -> tuple[bytes | None, list[str]]:
    """Resolve a local artifact without escaping the declared trust root."""
    if not isinstance(reference, dict):
        return None, ["artifact reference is not an object"]
    if base_dir is None or artifact_root is None:
        return None, ["artifact filesystem context is unavailable"]
    uri = reference.get("uri")
    digest = reference.get("digest")
    if not isinstance(uri, str) or not uri or "://" in uri or uri.startswith("file:"):
        return None, ["artifact URI must be a relative local path"]
    pure_uri = pathlib.PurePosixPath(uri)
    if (
        pure_uri.is_absolute()
        or "\\" in uri
        or uri != pure_uri.as_posix()
        or (strict_paths and ".." in pure_uri.parts)
    ):
        return None, ["artifact URI must not use absolute or traversal syntax"]
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        return None, ["artifact digest must be lowercase SHA-256"]
    root = artifact_root.resolve()
    unresolved = base_dir.resolve() / uri
    cursor = base_dir.resolve()
    for part in pure_uri.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return None, ["artifact path contains a symbolic link"]
    target = unresolved.resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None, ["artifact path escapes the declared artifact root"]
    if not target.is_file():
        return None, ["artifact file does not exist"]
    content = target.read_bytes()
    actual = "sha256:" + hashlib.sha256(content).hexdigest()
    if actual != digest:
        return None, ["artifact byte digest does not match"]
    return content, []


def validate_human_evidence(
    reference: Any,
    *,
    base_dir: pathlib.Path | None,
    artifact_root: pathlib.Path | None,
    scenario_ref: str,
    environment_ref: str,
    evidence_type: str,
    subject_refs: set[str],
    object_refs: set[str] | None,
    covers: set[str],
    as_of: dt.datetime,
    expected_finding: str = "satisfied",
    participant_decision: str | None = None,
    participant_status: str | None = None,
) -> list[str]:
    """Validate integrity and the declared semantics of a human evidence envelope."""
    content, errors = load_local_artifact(
        reference, base_dir=base_dir, artifact_root=artifact_root
    )
    if errors:
        return errors
    assert content is not None
    try:
        envelope = load_data_bytes(content, source="human evidence artifact")
    except ValueError as exc:
        return [str(exc)]
    schema = json.loads(HUMAN_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    schema_errors = sorted(
        validator.iter_errors(envelope), key=lambda item: list(item.path)
    )
    if schema_errors:
        return [
            "human evidence schema: "
            + (".".join(str(item) for item in error.path) or "<root>")
            + f": {error.message}"
            for error in schema_errors
        ]

    semantic_errors: list[str] = []
    if envelope["scenarioRef"] != scenario_ref:
        semantic_errors.append("human evidence scenarioRef does not match")
    if envelope["environmentRef"] != environment_ref:
        semantic_errors.append("human evidence environmentRef does not match")
    if envelope["evidenceType"] != evidence_type:
        semantic_errors.append("human evidence evidenceType does not match")
    if set(envelope["subjectRefs"]) != subject_refs:
        semantic_errors.append("human evidence subjectRefs do not match")
    if object_refs is not None and envelope["objectRef"] not in object_refs:
        semantic_errors.append("human evidence objectRef does not match")
    if not covers <= set(envelope["covers"]):
        semantic_errors.append("human evidence covers do not satisfy the assertion")
    if envelope["finding"] != expected_finding:
        semantic_errors.append("human evidence finding does not match")
    if (
        participant_decision is not None
        and envelope.get("participantDecision") != participant_decision
    ):
        semantic_errors.append("human evidence participantDecision does not match")
    if (
        participant_status is not None
        and envelope.get("participantStatus") != participant_status
    ):
        semantic_errors.append("human evidence participantStatus does not match")
    observed_at = _parse_time(envelope["observedAt"])
    valid_until = _parse_time(envelope["validUntil"])
    if observed_at is None or valid_until is None:
        semantic_errors.append("human evidence timestamps are invalid")
    else:
        if valid_until <= observed_at:
            semantic_errors.append("human evidence expires before observation")
        if valid_until <= as_of:
            semantic_errors.append("human evidence is stale")
        if observed_at > as_of:
            semantic_errors.append("human evidence observation is in the future")
    return semantic_errors


def validate_exercise_evidence(
    reference: Any,
    *,
    base_dir: pathlib.Path | None,
    artifact_root: pathlib.Path | None,
    scenario_ref: str,
    environment_ref: str,
    evidence_requirement_ref: str,
    finding: str,
    issuer: dict[str, Any],
    observation_observed_at: str,
    as_of: dt.datetime,
) -> list[str]:
    """Validate a typed exercise-evidence envelope and its outer observation binding."""
    content, errors = load_local_artifact(
        reference, base_dir=base_dir, artifact_root=artifact_root
    )
    if errors:
        return errors
    assert content is not None
    try:
        envelope = load_data_bytes(content, source="exercise evidence artifact")
    except ValueError as exc:
        return [str(exc)]
    schema = json.loads(EXERCISE_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    schema_errors = sorted(
        validator.iter_errors(envelope), key=lambda item: list(item.path)
    )
    if schema_errors:
        return [
            "exercise evidence schema: "
            + (".".join(str(item) for item in error.path) or "<root>")
            + f": {error.message}"
            for error in schema_errors
        ]

    semantic_errors: list[str] = []
    if envelope["scenarioRef"] != scenario_ref:
        semantic_errors.append("exercise evidence scenarioRef does not match")
    if envelope["environmentRef"] != environment_ref:
        semantic_errors.append("exercise evidence environmentRef does not match")
    if envelope["issuer"] != issuer:
        semantic_errors.append("exercise evidence issuer does not match attestation")
    assertion_refs = [
        assertion["evidenceRequirementRef"] for assertion in envelope["assertions"]
    ]
    if len(assertion_refs) != len(set(assertion_refs)):
        semantic_errors.append(
            "exercise evidence contains duplicate requirement assertions"
        )
    matching_assertions = [
        assertion
        for assertion in envelope["assertions"]
        if assertion["evidenceRequirementRef"] == evidence_requirement_ref
        and assertion["finding"] == finding
    ]
    if len(matching_assertions) != 1:
        semantic_errors.append(
            "exercise evidence does not contain exactly one matching assertion"
        )
    observed_at = _parse_time(envelope["observedAt"])
    outer_observed_at = _parse_time(observation_observed_at)
    valid_until = _parse_time(envelope["validUntil"])
    if observed_at is None or outer_observed_at is None or valid_until is None:
        semantic_errors.append("exercise evidence timestamps are invalid")
    else:
        if observed_at != outer_observed_at:
            semantic_errors.append(
                "exercise evidence observedAt does not match observation"
            )
        if valid_until <= observed_at:
            semantic_errors.append("exercise evidence expires before observation")
        if valid_until <= as_of:
            semantic_errors.append("exercise evidence is stale")
        if observed_at > as_of:
            semantic_errors.append("exercise evidence observation is in the future")
    return semantic_errors
