"""Blind dual-provider stage ordering with sealed-result enforcement."""

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List

from .finalize import finalize
from .result_validation import validate_sealed_result

Runner = Callable[[str, str], Dict[str, Any]]
_ENGINES = ("claude", "codex")


def _run_stage(runner: Runner, stage: str) -> List[Dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(runner, stage, engine) for engine in _ENGINES]
        return [future.result() for future in futures]


def _stage_errors(records: List[Dict[str, Any]], stage: str, packet: Dict[str, str]) -> Dict[str, List[str]]:
    errors: Dict[str, List[str]] = {}
    for engine, record in zip(_ENGINES, records):
        item_errors = validate_sealed_result(record, stage, engine, packet)
        semantic = record.get("semantic", {}) if isinstance(record, dict) else {}
        envelope = record.get("envelope", {}) if isinstance(record, dict) else {}
        if semantic.get("status") != "PASS" or semantic.get("blocking"):
            item_errors.append("STAGE_SEMANTIC_BLOCKER")
        if envelope.get("status") != "PASS":
            item_errors.append("STAGE_EXECUTION_BLOCKER")
        if item_errors:
            errors[engine] = item_errors
    return errors


def run_dual_stages(runner: Runner, packet: Dict[str, str]) -> Dict[str, Any]:
    """Start Review only after both Evaluate semantic+envelope pairs pass."""
    evaluate = _run_stage(runner, "evaluate")
    evaluate_errors = _stage_errors(evaluate, "evaluate", packet)
    if evaluate_errors:
        return {"status": "BLOCKED", "stage": "evaluate", "errors": evaluate_errors, "results": evaluate}

    review = _run_stage(runner, "review")
    review_errors = _stage_errors(review, "review", packet)
    if review_errors:
        return {"status": "BLOCKED", "stage": "review", "errors": review_errors, "results": evaluate + review}

    final = finalize(evaluate + review, packet)
    return {"status": final["status"], "stage": "final", "final": final, "results": evaluate + review}
