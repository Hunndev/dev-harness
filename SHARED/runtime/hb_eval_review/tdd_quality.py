"""TDD test-design and sensitivity contract validation."""

from typing import Any, Dict, List, Optional

_VALID_RED_REASONS = {"missing_behavior", "bug_reproduced"}
_BEHAVIOR_ASSERTIONS = {"observable_behavior", "state", "side_effect", "error_contract"}
_BASELINES = {"RED_TO_GREEN", "PASS_TO_PASS"}


def effective_baseline(data: Dict[str, Any]) -> Optional[str]:
    """Interpret the baseline without rewriting legacy evidence.

    Version 1.0 predates the baseline field and only means Red-to-Green.
    New evidence must use version 1.1 with an explicit, supported value.
    """
    if data.get("schema_version") == "1.0" and "baseline" not in data:
        return "RED_TO_GREEN"
    baseline = data.get("baseline")
    if data.get("schema_version") == "1.1" and isinstance(baseline, str) and baseline in _BASELINES:
        return baseline
    return None


def validate_test_design(data: Dict[str, Any]) -> List[str]:
    """Return stable error codes; an empty list means the design contract passes."""
    errors: List[str] = []
    baseline = effective_baseline(data)
    if baseline is None:
        errors.append("TDD_BASELINE_INVALID")
    if not data.get("acceptance_refs"):
        errors.append("TDD_AC_TRACE_MISSING")
    if baseline == "RED_TO_GREEN" and data.get("red_failure_kind") not in _VALID_RED_REASONS:
        errors.append("TDD_RED_REASON_INVALID")
    elif baseline == "PASS_TO_PASS" and "red_failure_kind" in data:
        errors.append("TDD_RED_REASON_INVALID")
    assertions = data.get("assertions") or []
    if not assertions or not any(item.get("kind") in _BEHAVIOR_ASSERTIONS for item in assertions):
        errors.append("TDD_ASSERTION_WEAK")
    if data.get("system_under_test_mocked") is not False:
        errors.append("TDD_SUT_MOCKED")
    if data.get("tier") == "T2":
        reviewer = data.get("reviewer") or {}
        if not (reviewer.get("independent") is True and reviewer.get("read_only") is True):
            errors.append("TDD_T2_REVIEW_MISSING")
    return errors


def validate_test_sensitivity(data: Dict[str, Any]) -> List[str]:
    """Validate baseline identity, transition, regression, and risk evidence."""
    errors: List[str] = []
    baseline = effective_baseline(data)
    if baseline is None:
        errors.append("TDD_BASELINE_INVALID")
    same_hash = data.get("red_test_hash") == data.get("green_test_hash")
    if not same_hash and data.get("approved_red_revision") is not True:
        errors.append("TDD_TEST_IDENTITY_CHANGED")
    expected_before = "PASS" if baseline == "PASS_TO_PASS" else "FAIL"
    if data.get("red_outcome") != expected_before or data.get("green_outcome") != "PASS":
        errors.append("TDD_TRANSITION_INVALID")
    if (data.get("regression") or {}).get("status") != "PASS":
        errors.append("TDD_REGRESSION_NOT_PASSING")
    mutation = data.get("mutation") or {}
    if mutation.get("required") is True:
        if mutation.get("performed") is not True or mutation.get("outcome") != "KILLED":
            errors.append("TDD_MUTATION_EVIDENCE_MISSING")
    return errors
