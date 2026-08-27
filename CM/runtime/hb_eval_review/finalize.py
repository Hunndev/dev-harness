"""Fail-closed reconciliation of sealed semantic results and execution envelopes."""

from typing import Any, Dict, Iterable, List, Tuple

from .result_validation import validate_sealed_result

_REQUIRED: Tuple[Tuple[str, str], ...] = (
    ("evaluate", "claude"), ("evaluate", "codex"),
    ("review", "claude"), ("review", "codex"),
)


def _semantic(item: Dict[str, Any]) -> Dict[str, Any]:
    value = item.get("semantic")
    return value if isinstance(value, dict) else {}


def _has_high_risk_disagreement(records: Iterable[Dict[str, Any]]) -> bool:
    dispositions = set()
    for record in records:
        for finding in _semantic(record).get("findings") or []:
            if finding.get("risk") == "HIGH":
                dispositions.add(finding.get("disposition"))
    return "BLOCK" in dispositions and "PASS" in dispositions


def finalize(records: List[Dict[str, Any]], packet: Dict[str, str]) -> Dict[str, Any]:
    """Produce a deterministic final state without trusting provider self-attestation."""
    indexed: Dict[Tuple[Any, Any], Dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        semantic = _semantic(record)
        envelope = record.get("envelope") if isinstance(record.get("envelope"), dict) else {}
        indexed[(semantic.get("stage"), envelope.get("engine"))] = record
    missing = [f"{stage}:{engine}" for stage, engine in _REQUIRED if (stage, engine) not in indexed]
    if missing:
        return {"status": "BLOCKED", "error_codes": ["FINAL_REQUIRED_RESULT_MISSING"], "missing": missing}

    validation: Dict[str, List[str]] = {}
    ordered: List[Dict[str, Any]] = []
    for stage, engine in _REQUIRED:
        record = indexed[(stage, engine)]
        ordered.append(record)
        errors = validate_sealed_result(record, stage, engine, packet)
        if errors:
            validation[f"{stage}:{engine}"] = errors
    if validation:
        return {"status": "BLOCKED", "error_codes": ["FINAL_SEALED_RESULT_INVALID"], "validation": validation}

    semantics = [_semantic(record) for record in ordered]
    envelopes = [record["envelope"] for record in ordered]
    if any(item.get("status") == "BLOCKED" or item.get("blocking") for item in semantics):
        return {"status": "BLOCKED", "error_codes": ["FINAL_PROVIDER_BLOCKER"]}
    if any(item.get("status") != "PASS" for item in envelopes):
        return {"status": "BLOCKED", "error_codes": ["FINAL_EXECUTION_BLOCKER"]}
    if _has_high_risk_disagreement(ordered):
        return {"status": "NEEDS_HUMAN_REVIEW", "error_codes": ["FINAL_HIGH_RISK_DISAGREEMENT"]}
    if any(item.get("status") == "NEEDS_HUMAN_REVIEW" for item in semantics):
        return {"status": "NEEDS_HUMAN_REVIEW", "error_codes": ["FINAL_PROVIDER_ESCALATION"]}
    return {
        "status": "PASS", "packet_id": packet["packet_id"],
        "source_snapshot_id": packet["source_snapshot_id"],
        "evidence_bundle_id": packet["evidence_bundle_id"],
        "sealed_results": [f"{stage}:{engine}" for stage, engine in _REQUIRED],
    }
