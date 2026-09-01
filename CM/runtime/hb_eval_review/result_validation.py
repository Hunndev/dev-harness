"""Validate model-owned semantics separately from parent-owned execution facts."""

import re
from typing import Any, Dict, List

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
_ENFORCED_ISOLATION = {"macos-sandbox-exec", "container-read-only"}
_SECRET_RE = re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*[^\s,]{6,}")


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
    if data.get("status") not in _ALLOWED_STATUS:
        errors.append("SEMANTIC_STATUS_INVALID")
    if not data.get("evidence_refs"):
        errors.append("SEMANTIC_EVIDENCE_MISSING")
    if _SECRET_RE.search(str(data)):
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
    return validate_semantic_result(sealed["semantic"], expected_stage) + validate_execution_envelope(
        sealed["envelope"], expected_stage, expected_engine, packet
    )


# Compatibility is intentionally fail-closed: old combined model-owned results cannot validate.
def validate_provider_result(
    data: Dict[str, Any], expected_stage: str, expected_engine: str, packet: Dict[str, str]
) -> List[str]:
    return validate_sealed_result(data, expected_stage, expected_engine, packet)
