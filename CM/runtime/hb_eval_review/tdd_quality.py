"""TDD test-design and sensitivity contract validation without filesystem I/O."""

import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

_VALID_RED_REASONS = {"missing_behavior", "bug_reproduced"}
_BEHAVIOR_ASSERTIONS = {"observable_behavior", "state", "side_effect", "error_contract"}
_BASELINES = {"RED_TO_GREEN", "PASS_TO_PASS"}
_OBSERVED_FIELDS = {"argv", "cwd", "exit_code", "selected_tests", "executed", "recorded_at",
                    "test_file_sha256", "run_id", "git_dir", "artifacts", "test_file",
                    "source_snapshot_id", "sut_sha256"}
_APPROVAL_FIELDS = {"schema_version", "kind", "repo", "git_dir", "artifacts", "run_id",
                    "test_file", "old_sha256", "new_sha256", "revision", "revision_line",
                    "approved_by", "approval_source", "recorded_at"}


def canonical_json_bytes(data: Dict[str, Any]) -> bytes:
    """Serialize frozen evidence and approval records identically across producers."""
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            + "\n").encode("utf-8")


def canonical_design_bytes(data: Dict[str, Any]) -> bytes:
    """Return the exact bytes whose digest binds sensitivity to its frozen design."""
    return canonical_json_bytes(data)


def _hex(value: Any, length: int) -> bool:
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{" + str(length) + "}", value) is not None


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and "\x00" not in value


def _absolute(value: Any) -> bool:
    return _text(value) and Path(value).is_absolute()


def _relative_test_file(value: Any) -> bool:
    return (_text(value) and "\\" not in value and not PurePosixPath(value).is_absolute()
            and ".." not in PurePosixPath(value).parts and PurePosixPath(value).as_posix() == value
            and value != ".")


def _utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)", value):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() == timedelta(0)
    except ValueError:
        return False


def _valid_observation(data: Dict[str, Any], sensitivity: bool = False) -> bool:
    observed = data.get("observed")
    required = _OBSERVED_FIELDS | ({"baseline_sha256"} if sensitivity else set())
    allowed = required | ({"approval"} if sensitivity else set())
    if not isinstance(observed, dict) or not required <= observed.keys() <= allowed:
        return False
    argv, selected = observed.get("argv"), observed.get("selected_tests")
    if not (isinstance(argv, list) and argv and all(_text(arg) for arg in argv)
            and isinstance(selected, list) and selected and all(_text(item) for item in selected)):
        return False
    if (type(observed.get("executed")) is not int or observed["executed"] < 1
            or observed["executed"] != len(selected) or len(selected) != len(set(selected))):
        return False
    return (type(observed.get("exit_code")) is int
            and all(_absolute(observed.get(key)) for key in ("cwd", "git_dir", "artifacts"))
            and _relative_test_file(observed.get("test_file"))
            and _utc_timestamp(observed.get("recorded_at"))
            and _hex(observed.get("run_id"), 32)
            and all(_hex(observed.get(key), 64)
                    for key in ("test_file_sha256", "source_snapshot_id", "sut_sha256"))
            and (not sensitivity or _hex(observed.get("baseline_sha256"), 64)))


def _valid_approval(data: Dict[str, Any]) -> bool:
    """Check the recorded receipt; its file provenance is checked by the producer."""
    observed = data.get("observed")
    if not isinstance(observed, dict):
        return False
    approval = observed.get("approval")
    if not isinstance(approval, dict) or set(approval) != {"record_path", "record_sha256", "record"}:
        return False
    record = approval.get("record")
    if not isinstance(record, dict) or set(record) != _APPROVAL_FIELDS:
        return False
    if not (_absolute(approval.get("record_path")) and _hex(approval.get("record_sha256"), 64)
            and all(_absolute(record.get(key)) for key in ("repo", "git_dir", "artifacts"))
            and _hex(record.get("run_id"), 32) and _relative_test_file(record.get("test_file"))
            and all(_hex(record.get(key), 64) for key in ("old_sha256", "new_sha256"))
            and record.get("schema_version") == "1.0"
            and record.get("kind") == "tdd-red-revision-approval"
            and record.get("approved_by") == "user" and _text(record.get("approval_source"))
            and _utc_timestamp(record.get("recorded_at"))
            and type(record.get("revision")) is int and record["revision"] in (1, 2)):
        return False
    line = record.get("revision_line")
    prefix = "revision " + str(record["revision"]) + ": "
    if not isinstance(line, str) or not line.startswith(prefix) or not _text(line[len(prefix):]):
        return False
    repo = Path(os.path.abspath(record["repo"]))
    record_path = Path(os.path.abspath(approval["record_path"]))
    if record_path == repo or repo in record_path.parents:
        return False
    for record_key, observed_key in (("repo", "cwd"), ("git_dir", "git_dir"),
                                      ("artifacts", "artifacts"), ("run_id", "run_id"),
                                      ("test_file", "test_file")):
        if record.get(record_key) != observed.get(observed_key):
            return False
    if (record["old_sha256"] != data.get("red_test_hash")
            or record["new_sha256"] != data.get("green_test_hash")):
        return False
    try:
        return hashlib.sha256(canonical_json_bytes(record)).hexdigest() == approval["record_sha256"]
    except (ValueError, TypeError, UnicodeError):
        return False


def _observation_identity_errors(data: Dict[str, Any]) -> List[str]:
    observed = data.get("observed") or {}
    changed = data.get("red_test_hash") != data.get("green_test_hash")
    valid_receipt = _valid_approval(data)
    approved = changed and valid_receipt
    if (data.get("approved_red_revision") is not approved
            or (changed and not approved)
            or ("approval" in observed and not valid_receipt)
            or data.get("green_test_hash") != observed.get("test_file_sha256")):
        return ["TDD_TEST_IDENTITY_CHANGED"]
    return []


def effective_baseline(data: Dict[str, Any]) -> Optional[str]:
    """Interpret the baseline without rewriting legacy evidence.

    Version 1.0 predates the baseline field and only means Red-to-Green.
    Versions 1.1 and 1.2 require an explicit, supported value.
    """
    if data.get("schema_version") == "1.0" and "baseline" not in data:
        return "RED_TO_GREEN"
    baseline = data.get("baseline")
    if data.get("schema_version") in ("1.1", "1.2") and isinstance(baseline, str) and baseline in _BASELINES:
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
    if data.get("schema_version") == "1.2":
        observed = data.get("observed")
        if (not _valid_observation(data)
                or (baseline == "RED_TO_GREEN" and observed["exit_code"] == 0)
                or (baseline == "PASS_TO_PASS" and observed["exit_code"] != 0)):
            errors.append("TDD_OBSERVATION_INVALID")
    return errors


def validate_test_sensitivity(data: Dict[str, Any]) -> List[str]:
    """Validate baseline identity, transition, regression, and risk evidence."""
    errors: List[str] = []
    baseline = effective_baseline(data)
    if baseline is None:
        errors.append("TDD_BASELINE_INVALID")
    same_hash = data.get("red_test_hash") == data.get("green_test_hash")
    if data.get("schema_version") == "1.2":
        if not _valid_observation(data, sensitivity=True):
            errors.append("TDD_OBSERVATION_INVALID")
        else:
            if data["observed"]["exit_code"] != 0:
                errors.append("TDD_OBSERVATION_INVALID")
            errors.extend(_observation_identity_errors(data))
    elif not same_hash and data.get("approved_red_revision") is not True:
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


def validate_observation_pair(design: Dict[str, Any], sensitivity: Dict[str, Any]) -> List[str]:
    """Bind 1.2 evidence to one frozen baseline; retain legacy semantic compatibility.

    This function does not read live sources or rerun tests. The observed producer
    owns PASS/FAIL-only execution selection and approval-record provenance.
    """
    versions = (design.get("schema_version"), sensitivity.get("schema_version"))
    if "1.2" not in versions:
        return []
    if versions != ("1.2", "1.2"):
        return ["TDD_OBSERVATION_INVALID"]
    if not _valid_observation(design) or not _valid_observation(sensitivity, sensitivity=True):
        return ["TDD_OBSERVATION_INVALID"]
    errors: List[str] = []
    red, green = design["observed"], sensitivity["observed"]
    if (effective_baseline(design) != effective_baseline(sensitivity)
            or any(red[key] != green[key] for key in ("run_id", "cwd", "git_dir", "artifacts", "test_file"))
            or red["test_file_sha256"] != sensitivity.get("red_test_hash")):
        errors.append("TDD_BASELINE_MISMATCH")
    try:
        if hashlib.sha256(canonical_design_bytes(design)).hexdigest() != green["baseline_sha256"]:
            errors.append("TDD_BASELINE_MISMATCH")
    except (ValueError, TypeError, UnicodeError):
        errors.append("TDD_OBSERVATION_INVALID")
    if not set(red["selected_tests"]) <= set(green["selected_tests"]):
        errors.append("TDD_TEST_IDENTITY_CHANGED")
    errors.extend(_observation_identity_errors(sensitivity))
    return list(dict.fromkeys(errors))
