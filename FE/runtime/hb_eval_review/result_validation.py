"""Validate model-owned semantics separately from parent-owned execution facts."""

import hashlib
import json
import re
from typing import Any, Dict, List

from .redaction import find_secret_shaped

_SEMANTIC_REQUIRED = {"schema_version", "stage", "status", "blocking", "findings", "evidence_refs"}
_SEMANTIC_ALLOWED = _SEMANTIC_REQUIRED | {"verdicts", "summary"}
_SELF_ATTESTATION = {
    "fresh", "read_only", "repository_mutated", "engine", "provider", "model",
    "run_id", "session_id", "packet_id", "source_snapshot_id", "evidence_bundle_id",
}
_ENVELOPE_REQUIRED = {
    "schema_version", "stage", "engine", "provider", "run_id", "started_at", "finished_at",
    "exit_code", "timed_out", "fresh_process", "session_resumed", "isolation_mode",
    "source_snapshot_before", "source_snapshot_after", "packet_id", "evidence_bundle_id",
    "repository_mutated", "result_sha256", "status", "error_code",
}
_ALLOWED_STATUS = {"PASS", "BLOCKED", "NEEDS_HUMAN_REVIEW"}
# The finding-level enums the floor and the gate actually read, straight from
# `contracts/provider-result-base.schema.json`.
_ALLOWED_DISPOSITION = {"PASS", "BLOCK", "HUMAN"}
_ALLOWED_RISK = {"LOW", "MEDIUM", "HIGH"}
# Every field the same contract marks `required` on a finding.
_FINDING_REQUIRED = frozenset(
    {"finding_id", "risk", "disposition", "evidence_ref", "message", "blocking"}
)
_FINDING_STRINGS = ("finding_id", "evidence_ref", "message")
STATUS_RANK = {"PASS": 0, "NEEDS_HUMAN_REVIEW": 1, "BLOCKED": 2}
_ENFORCED_ISOLATION = {"macos-sandbox-exec", "container-read-only"}


def canonical_bytes(value: Any) -> bytes:
    """The one canonical serialization used to seal and to re-verify semantic results."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _enum_is_valid(value: Any, allowed: set) -> bool:
    """Membership is only asked of a string, so an unhashable value cannot raise."""
    return isinstance(value, str) and value in allowed


def _finding_types_are_valid(finding: Any) -> bool:
    """The contract's required finding fields, present and of the contract's types.

    Presence is checked, not just the type of whatever the provider chose to send: the
    fields the floor reads are `disposition` and `blocking`, so a finding that simply
    omitted them used to validate clean and floor at PASS. Required is required, exactly
    as `contracts/provider-result-base.schema.json` states.
    """
    if not isinstance(finding, dict) or not _FINDING_REQUIRED.issubset(finding):
        return False
    if not all(isinstance(finding[field], str) for field in _FINDING_STRINGS):
        return False
    if not isinstance(finding["blocking"], bool):
        return False
    if not _enum_is_valid(finding["disposition"], _ALLOWED_DISPOSITION):
        return False
    return _enum_is_valid(finding["risk"], _ALLOWED_RISK)


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _semantic_types_are_valid(data: Dict[str, Any]) -> bool:
    """The contract types of the model-owned fields, checked before anything reads them."""
    findings = data.get("findings")
    if not isinstance(findings, list) or not all(
        _finding_types_are_valid(item) for item in findings
    ):
        return False
    return (
        _string_list(data.get("blocking"))
        and _string_list(data.get("evidence_refs"))
        and isinstance(data.get("status"), str)
    )


def derive_semantic_floor(data: Dict[str, Any]) -> str:
    """Derive the least severe status the model's own findings can justify.

    A provider result is untrusted, so anything off-contract derives BLOCKED: putting a
    string where the contract requires a boolean must never buy a milder floor than the
    boolean would have.
    """
    if not isinstance(data, dict) or not _semantic_types_are_valid(data):
        return "BLOCKED"
    if data["blocking"]:
        return "BLOCKED"
    findings = data["findings"]
    for finding in findings:
        if finding.get("blocking") is True or finding.get("disposition") == "BLOCK":
            return "BLOCKED"
    for finding in findings:
        if finding.get("disposition") == "HUMAN":
            return "NEEDS_HUMAN_REVIEW"
    return "PASS"


def validate_semantic_result(data: Dict[str, Any], expected_stage: str) -> List[str]:
    """Validate only model-owned judgments; reject model self-attestation."""
    if not isinstance(data, dict) or not _SEMANTIC_REQUIRED.issubset(data):
        return ["SEMANTIC_REQUIRED_FIELD_MISSING"]
    errors: List[str] = []
    if _SELF_ATTESTATION.intersection(data):
        errors.append("SEMANTIC_SELF_ATTESTATION_FORBIDDEN")
    if set(data).difference(_SEMANTIC_ALLOWED | _SELF_ATTESTATION):
        errors.append("SEMANTIC_UNKNOWN_FIELD")
    if data.get("schema_version") != "2.0":
        errors.append("SEMANTIC_SCHEMA_VERSION_INVALID")
    if data.get("stage") != expected_stage:
        errors.append("SEMANTIC_STAGE_MISMATCH")
    # A provider result is untrusted input, so an off-schema type is a BLOCKED error
    # code, never an exception out of the validator: the membership test below is only
    # reached once `status` is known to be a string.
    status = data.get("status")
    if not _enum_is_valid(status, _ALLOWED_STATUS):
        errors.append("SEMANTIC_STATUS_INVALID")
    elif STATUS_RANK[status] < STATUS_RANK[derive_semantic_floor(data)]:
        errors.append("SEMANTIC_STATUS_CONTRADICTS_FINDINGS")
    if not _semantic_types_are_valid(data):
        errors.append("SEMANTIC_SCHEMA_INVALID")
    elif data["blocking"]:
        known = {finding["finding_id"] for finding in data["findings"]}
        if any(item not in known for item in data["blocking"]):
            errors.append("SEMANTIC_BLOCKING_ID_UNKNOWN")
    if not data.get("evidence_refs"):
        errors.append("SEMANTIC_EVIDENCE_MISSING")
    if find_secret_shaped(data):
        errors.append("SEMANTIC_SECRET_SHAPED_CONTENT")
    if "implementer_transcript" in data or "prompt" in data:
        errors.append("SEMANTIC_FORBIDDEN_CONTEXT")
    return errors


def validate_execution_envelope(
    data: Dict[str, Any], expected_stage: str, expected_engine: str, packet: Dict[str, str]
) -> List[str]:
    """Validate facts measured and signed by the parent process wrapper."""
    if not isinstance(data, dict) or not _ENVELOPE_REQUIRED.issubset(data):
        return ["ENVELOPE_REQUIRED_FIELD_MISSING"]
    errors: List[str] = []
    if data.get("schema_version") != "2.0":
        errors.append("ENVELOPE_SCHEMA_VERSION_INVALID")
    if data.get("stage") != expected_stage:
        errors.append("ENVELOPE_STAGE_MISMATCH")
    if data.get("engine") != expected_engine:
        errors.append("ENVELOPE_ENGINE_MISMATCH")
    if data.get("packet_id") != packet.get("packet_id"):
        errors.append("ENVELOPE_PACKET_MISMATCH")
    if data.get("source_snapshot_before") != packet.get("source_snapshot_id"):
        errors.append("ENVELOPE_SOURCE_BINDING_MISMATCH")
    if data.get("evidence_bundle_id") != packet.get("evidence_bundle_id"):
        errors.append("ENVELOPE_EVIDENCE_BUNDLE_MISMATCH")
    if data.get("source_snapshot_before") != data.get("source_snapshot_after"):
        errors.append("ENVELOPE_SNAPSHOT_CHANGED")
    if data.get("repository_mutated") is not False:
        errors.append("ENVELOPE_REPOSITORY_MUTATED")
    if data.get("fresh_process") is not True or data.get("session_resumed") is not False:
        errors.append("ENVELOPE_NOT_FRESH")
    if data.get("timed_out") is not False:
        errors.append("ENVELOPE_PROCESS_TIMEOUT")
    if data.get("isolation_mode") not in _ENFORCED_ISOLATION:
        errors.append("ENVELOPE_ISOLATION_NOT_ENFORCED")
    if not re.fullmatch(r"[0-9a-f]{64}", str(data.get("result_sha256", ""))):
        errors.append("ENVELOPE_RESULT_HASH_INVALID")
    return errors


def validate_sealed_result(
    sealed: Dict[str, Any], expected_stage: str, expected_engine: str, packet: Dict[str, str]
) -> List[str]:
    """Require both independently owned halves before a stage can pass."""
    if not isinstance(sealed, dict) or "semantic" not in sealed:
        return ["SEALED_SEMANTIC_MISSING"]
    if "envelope" not in sealed:
        return ["SEALED_ENVELOPE_MISSING"]
    semantic = sealed["semantic"]
    envelope = sealed["envelope"]
    errors = validate_semantic_result(semantic, expected_stage) + validate_execution_envelope(
        envelope, expected_stage, expected_engine, packet
    )
    if isinstance(semantic, dict) and isinstance(envelope, dict):
        if canonical_sha256(semantic) != envelope.get("result_sha256"):
            errors.append("SEALED_RESULT_HASH_MISMATCH")
    return errors


# Compatibility is intentionally fail-closed: old combined model-owned results cannot validate.
def validate_provider_result(
    data: Dict[str, Any], expected_stage: str, expected_engine: str, packet: Dict[str, str]
) -> List[str]:
    return validate_sealed_result(data, expected_stage, expected_engine, packet)
