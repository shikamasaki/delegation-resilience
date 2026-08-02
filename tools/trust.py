"""Offline DSSE and deny-by-default trust-policy verification."""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import hashlib
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

try:
    from tools.data_loading import canonical_json_bytes, load_json_bytes
    from tools.schema_validation import schema_errors
except ModuleNotFoundError:
    from data_loading import canonical_json_bytes, load_json_bytes
    from schema_validation import schema_errors


@dataclass(frozen=True)
class VerifiedStatement:
    subject_digest: str
    kind: str
    purpose: str
    issuer: dict[str, Any]
    key_id: str
    independence_domain: str
    payload: dict[str, Any]


def byte_digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def validate_trust_policy(policy: dict[str, Any], *, as_of: dt.datetime) -> list[str]:
    errors = [
        f"trust policy schema: {item}"
        for item in schema_errors("trust-policy.schema.json", policy)
    ]
    if errors:
        return errors
    valid_from = _parse_time(policy["validFrom"])
    valid_until = _parse_time(policy["validUntil"])
    if valid_from is None or valid_until is None or valid_until <= valid_from:
        errors.append("trust policy validity interval is invalid")
    elif as_of < valid_from or as_of >= valid_until:
        errors.append("trust policy is not current at the requested evaluation time")
    key_ids = [item["keyId"] for item in policy["keys"]]
    if len(key_ids) != len(set(key_ids)):
        errors.append("trust policy contains duplicate keyId")
    issuer_domains: dict[tuple[str, str], str] = {}
    for key in policy["keys"]:
        start = _parse_time(key["validFrom"])
        end = _parse_time(key["validUntil"])
        if start is None or end is None or end <= start:
            errors.append(f"trust key[{key['keyId']}] validity interval is invalid")
        try:
            public = base64.b64decode(key["publicKey"], validate=True)
            if len(public) != 32:
                raise ValueError
            expected_key_id = "sha256:" + hashlib.sha256(public).hexdigest()
            if key["keyId"] != expected_key_id:
                errors.append(
                    f"trust key[{key['keyId']}] keyId does not match its public key"
                )
        except (binascii.Error, ValueError):
            errors.append(f"trust key[{key['keyId']}] publicKey is not raw Ed25519")
        purposes = [item["purpose"] for item in key["authorizations"]]
        if len(purposes) != len(set(purposes)):
            errors.append(
                f"trust key[{key['keyId']}] contains duplicate purpose authorization"
            )
        issuer_identity = (key["issuer"]["id"], key["issuer"]["type"])
        prior_domain = issuer_domains.setdefault(
            issuer_identity, key["independenceDomain"]
        )
        if prior_domain != key["independenceDomain"]:
            errors.append(
                "one issuer identity cannot claim multiple independence domains: "
                f"{issuer_identity[0]}"
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


def _string_set(value: Any) -> set[str]:
    """Return only string members from an untrusted JSON array."""
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str)}


def _pae(payload_type: bytes, payload: bytes) -> bytes:
    """DSSE Pre-Authentication Encoding."""
    return b"DSSEv1 %d %s %d %s" % (
        len(payload_type),
        payload_type,
        len(payload),
        payload,
    )


def create_dsse_envelope(
    payload: dict[str, Any], *, payload_type: str, key_id: str, private_key: bytes
) -> dict[str, Any]:
    payload_bytes = canonical_json_bytes(payload)
    key = Ed25519PrivateKey.from_private_bytes(private_key)
    signature = key.sign(_pae(payload_type.encode("utf-8"), payload_bytes))
    return {
        "payloadType": payload_type,
        "payload": base64.b64encode(payload_bytes).decode("ascii"),
        "signatures": [
            {"keyid": key_id, "sig": base64.b64encode(signature).decode("ascii")}
        ],
    }


def _artifact_time(payload: dict[str, Any]) -> tuple[dt.datetime | None, str | None]:
    if payload.get("_type") == "https://in-toto.io/Statement/v1":
        predicate = payload.get("predicate", {})
        if isinstance(predicate, dict):
            return _parse_time(predicate.get("createdAt")), None
    present = [
        field for field in ("issuedAt", "observedAt", "createdAt") if field in payload
    ]
    if len(present) != 1:
        return None, "signed artifact must contain exactly one recognized artifact time"
    return _parse_time(payload[present[0]]), None


def verify_dsse_envelope(
    envelope_bytes: bytes,
    *,
    trust_policy: dict[str, Any],
    purpose: str,
    as_of: dt.datetime,
    expected_payload: bytes | None = None,
    expected_payload_type: str | None = None,
) -> tuple[VerifiedStatement | None, list[str]]:
    errors: list[str] = []
    try:
        envelope = load_json_bytes(envelope_bytes, source="DSSE envelope")
    except ValueError as exc:
        return None, [str(exc)]
    errors.extend(
        f"DSSE schema: {item}"
        for item in schema_errors("dsse-envelope.schema.json", envelope)
    )
    if errors:
        return None, errors
    if (
        expected_payload_type is not None
        and envelope["payloadType"] != expected_payload_type
    ):
        errors.append(f"DSSE payloadType mismatch: expected {expected_payload_type}")
    try:
        payload_bytes = base64.b64decode(envelope["payload"], validate=True)
        signature_bytes = base64.b64decode(
            envelope["signatures"][0]["sig"], validate=True
        )
    except (binascii.Error, ValueError):
        return None, ["DSSE envelope contains invalid base64"]
    if expected_payload is not None and payload_bytes != expected_payload:
        errors.append("DSSE payload does not byte-match the referenced artifact")
    try:
        payload = load_json_bytes(payload_bytes, source="DSSE payload")
    except ValueError as exc:
        errors.append(str(exc))
        return None, errors

    key_id = envelope["signatures"][0]["keyid"]
    keys = [
        item for item in trust_policy.get("keys", []) if item.get("keyId") == key_id
    ]
    if len(keys) != 1:
        errors.append(f"DSSE keyid is not uniquely trusted: {key_id}")
        return None, errors
    key = keys[0]
    if key.get("status") != "active":
        errors.append(f"TRUST_KEY_REVOKED: {key_id}")
    authorization = next(
        (
            item
            for item in key.get("authorizations", [])
            if item.get("purpose") == purpose
        ),
        None,
    )
    if authorization is None:
        errors.append(f"issuer key is not authorized for purpose: {purpose}")
    semantic_payload = payload
    if payload.get("_type") == "https://in-toto.io/Statement/v1":
        candidate = payload.get("predicate")
        if isinstance(candidate, dict):
            semantic_payload = candidate
    kind = str(semantic_payload.get("kind", ""))
    if authorization and kind not in authorization.get("artifactKinds", []):
        errors.append(f"issuer key is not authorized for artifact kind: {kind}")

    issuer = semantic_payload.get("issuer")
    if not isinstance(issuer, dict):
        issuer = key.get("issuer", {})
    elif issuer != key.get("issuer"):
        errors.append("artifact issuer does not match the trusted key issuer")
    self_attestable_human_types = {
        "participant_acknowledgement",
        "withdrawal_status",
    }
    if purpose == "human_evidence":
        evidence_type = semantic_payload.get("evidenceType")
        subjects = _string_set(semantic_payload.get("subjectRefs"))
        if evidence_type in self_attestable_human_types:
            if issuer.get("type") != "human" or subjects != {issuer.get("id")}:
                errors.append(
                    "participant acknowledgement or withdrawal status must be self-issued by its sole human subject"
                )
        elif issuer.get("type") == "human":
            errors.append(
                "non-participant-statement human evidence must be issued by a non-human independent issuer"
            )
        elif issuer.get("id") in subjects:
            errors.append(
                "human evidence issuer cannot attest its own participant subject"
            )

    if authorization:
        system_under_test = semantic_payload.get("systemUnderTest")
        environment = (
            system_under_test.get("environment")
            if isinstance(system_under_test, dict)
            else None
        )
        scope_fields = {
            "scenarioRefs": semantic_payload.get("scenarioRef"),
            "environmentRefs": semantic_payload.get("environmentRef") or environment,
            "evidenceTypes": semantic_payload.get("evidenceType"),
        }
        for policy_field, artifact_value in scope_fields.items():
            allowed = authorization.get(policy_field)
            if allowed is not None and artifact_value not in allowed:
                errors.append(
                    f"issuer authorization {policy_field} excludes: {artifact_value}"
                )
        scalar_scopes = {
            "apiVersions": semantic_payload.get("apiVersion"),
            "payloadTypes": envelope.get("payloadType"),
            "objectRefs": semantic_payload.get("objectRef"),
        }
        for policy_field, artifact_value in scalar_scopes.items():
            allowed = authorization.get(policy_field)
            if allowed is not None and artifact_value not in allowed:
                errors.append(
                    f"issuer authorization {policy_field} excludes: {artifact_value}"
                )
        set_scopes = {
            "subjectRefs": _string_set(semantic_payload.get("subjectRefs")),
            "covers": _string_set(semantic_payload.get("covers")),
        }
        for policy_field, artifact_values in set_scopes.items():
            allowed = authorization.get(policy_field)
            if allowed is not None and not artifact_values <= set(allowed):
                errors.append(
                    f"issuer authorization {policy_field} excludes: "
                    + ", ".join(sorted(artifact_values - set(allowed)))
                )

    artifact_time, artifact_time_error = _artifact_time(payload)
    if artifact_time_error:
        errors.append(artifact_time_error)
    key_start = _parse_time(key.get("validFrom"))
    key_end = _parse_time(key.get("validUntil"))
    if artifact_time is None:
        errors.append("signed artifact has no recognized issuance/observation time")
    else:
        if artifact_time > as_of:
            errors.append("signed artifact time is in the future")
        if key_start and artifact_time < key_start:
            errors.append("signed artifact predates the signing key validity")
        if key_end and artifact_time >= key_end:
            errors.append("signed artifact is after the signing key validity")
        if authorization:
            age = (as_of - artifact_time).total_seconds()
            if age > authorization["maxAgeSeconds"]:
                errors.append("signed artifact exceeds the authorized maximum age")
    if key_start and key_end and not (key_start <= as_of < key_end):
        errors.append("signing key is not current at the requested evaluation time")
    payload_digest = byte_digest(payload_bytes)
    if payload_digest in {
        item.get("digest") for item in trust_policy.get("revokedSubjects", [])
    }:
        errors.append(f"TRUST_SUBJECT_REVOKED: {payload_digest}")

    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(key["publicKey"], validate=True)
        )
        public_key.verify(
            signature_bytes,
            _pae(envelope["payloadType"].encode("utf-8"), payload_bytes),
        )
    except (binascii.Error, ValueError, InvalidSignature):
        errors.append("DSSE signature is invalid")
    if errors:
        return None, errors
    return (
        VerifiedStatement(
            subject_digest=payload_digest,
            kind=kind,
            purpose=purpose,
            issuer=issuer,
            key_id=key_id,
            independence_domain=key["independenceDomain"],
            payload=payload,
        ),
        [],
    )
