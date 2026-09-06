import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review import result_validation, run_provider
from hb_eval_review.finalize import finalize
from hb_eval_review.result_validation import (
    derive_semantic_floor,
    validate_execution_envelope,
    validate_sealed_result,
    validate_semantic_result,
)


PACKET = {"packet_id": "p1", "source_snapshot_id": "s1", "evidence_bundle_id": "e1"}


def canonical_json_bytes(value):
    """Spec for canonical semantic bytes; runtime must expose exactly this."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def result_hash(semantic_payload):
    return hashlib.sha256(canonical_json_bytes(semantic_payload)).hexdigest()


def semantic(stage="evaluate", status="PASS"):
    return {
        "schema_version": "2.0", "stage": stage, "status": status,
        "blocking": [], "findings": [], "evidence_refs": ["gate:test"],
    }


def finding(finding_id="F1", **overrides):
    """A contract-complete finding; a test overrides only the field it is about."""
    data = {
        "finding_id": finding_id, "risk": "LOW", "disposition": "PASS",
        "evidence_ref": "gate:test", "message": "reviewed", "blocking": False,
    }
    data.update(overrides)
    return data


def envelope(stage="evaluate", engine="claude", result_sha256=None):
    return {
        "schema_version": "2.0", "stage": stage, "engine": engine,
        "provider": engine, "run_id": f"run-{stage}-{engine}",
        "started_at": "2026-08-26T00:00:00Z", "finished_at": "2026-08-26T00:00:01Z",
        "exit_code": 0, "timed_out": False, "fresh_process": True,
        "session_resumed": False, "isolation_mode": "macos-sandbox-exec",
        "source_snapshot_before": "s1", "source_snapshot_after": "s1",
        "packet_id": "p1", "evidence_bundle_id": "e1",
        "repository_mutated": False,
        "result_sha256": result_sha256 or result_hash(semantic(stage, "PASS")),
        "status": "PASS", "error_code": None,
    }


def sealed(stage="evaluate", engine="claude", status="PASS"):
    payload = semantic(stage, status)
    return {"semantic": payload, "envelope": envelope(stage, engine, result_hash(payload))}


def reseal(record):
    """Re-bind the envelope hash after a test intentionally edits semantic content."""
    record["envelope"]["result_sha256"] = result_hash(record["semantic"])
    return record


class SemanticValidationTests(unittest.TestCase):
    def test_model_self_attestation_is_rejected(self):
        data = semantic()
        data.update({"fresh": True, "read_only": True, "repository_mutated": False})
        errors = validate_semantic_result(data, "evaluate")
        self.assertIn("SEMANTIC_SELF_ATTESTATION_FORBIDDEN", errors)

    def test_clean_semantic_payload_passes(self):
        self.assertEqual([], validate_semantic_result(semantic(), "evaluate"))

    def test_redacted_semantic_passes_the_secret_check(self):
        data = semantic()
        data["findings"] = [{"finding_id": "F1", "message": "token=[REDACTED]"}]
        self.assertNotIn(
            "SEMANTIC_SECRET_SHAPED_CONTENT", validate_semantic_result(data, "evaluate")
        )

    def test_nested_secret_shaped_finding_is_rejected(self):
        data = semantic()
        data["findings"] = [{"finding_id": "F1", "message": "api_key=abcdefghij"}]
        self.assertIn(
            "SEMANTIC_SECRET_SHAPED_CONTENT", validate_semantic_result(data, "evaluate")
        )

    def test_empty_evidence_is_rejected(self):
        data = semantic()
        data["evidence_refs"] = []
        self.assertIn("SEMANTIC_EVIDENCE_MISSING", validate_semantic_result(data, "evaluate"))


class SemanticFindingsContradictionTests(unittest.TestCase):
    def contradicting(self, findings=None, blocking=None):
        data = semantic(status="PASS")
        data["findings"] = findings or []
        data["blocking"] = blocking or []
        return data

    def test_optimistic_status_against_findings_is_contradiction(self):
        cases = {
            "finding_blocking_true": ([finding(blocking=True)], []),
            "finding_disposition_block": (
                [finding(blocking=False, disposition="BLOCK")], []),
            "blocking_id_list": ([finding()], ["F1"]),
            "high_human": ([finding(risk="HIGH", disposition="HUMAN")], []),
            "low_human": ([finding(risk="LOW", disposition="HUMAN")], []),
        }
        for name, (findings, blocking) in cases.items():
            with self.subTest(case=name):
                errors = validate_semantic_result(self.contradicting(findings, blocking), "evaluate")
                self.assertIn("SEMANTIC_STATUS_CONTRADICTS_FINDINGS", errors)

    def test_human_status_still_contradicts_a_blocking_finding(self):
        data = self.contradicting([finding(disposition="BLOCK")])
        data["status"] = "NEEDS_HUMAN_REVIEW"
        self.assertIn(
            "SEMANTIC_STATUS_CONTRADICTS_FINDINGS", validate_semantic_result(data, "evaluate")
        )

    def test_conservative_status_is_not_a_contradiction(self):
        data = semantic(status="BLOCKED")
        self.assertNotIn(
            "SEMANTIC_STATUS_CONTRADICTS_FINDINGS", validate_semantic_result(data, "evaluate")
        )

    def test_coherent_human_status_passes(self):
        data = semantic(status="NEEDS_HUMAN_REVIEW")
        data["findings"] = [finding(risk="LOW", disposition="HUMAN")]
        self.assertEqual([], validate_semantic_result(data, "evaluate"))

    def test_unknown_blocking_id_is_rejected(self):
        data = semantic(status="BLOCKED")
        data["findings"] = [finding(disposition="BLOCK")]
        data["blocking"] = ["F9"]
        self.assertIn("SEMANTIC_BLOCKING_ID_UNKNOWN", validate_semantic_result(data, "evaluate"))

    def test_off_schema_finding_types_are_rejected_without_crashing(self):
        # A provider-supplied file is untrusted input: an off-schema type must come
        # back as a BLOCKED error code, never as a TypeError out of the validator.
        cases = {
            "blocking_dict_item": {"blocking": [{"id": "F1"}]},
            "blocking_not_a_list": {"blocking": "F1"},
            "blocking_int_item": {"blocking": [7]},
            "findings_not_a_list": {"findings": {"finding_id": "F1"}},
            "findings_item_not_a_dict": {"findings": ["F1"]},
            "finding_id_not_a_string": {
                "blocking": ["F1"], "findings": [{"finding_id": ["F1"]}]
            },
        }
        for name, overrides in cases.items():
            with self.subTest(case=name):
                data = semantic(status="BLOCKED")
                data.update(overrides)
                errors = validate_semantic_result(data, "evaluate")
                self.assertIn("SEMANTIC_SCHEMA_INVALID", errors)

    def test_known_blocking_id_is_accepted(self):
        data = semantic(status="BLOCKED")
        data["findings"] = [finding(disposition="BLOCK")]
        data["blocking"] = ["F1"]
        self.assertEqual([], validate_semantic_result(data, "evaluate"))


class SemanticContractTypeTests(unittest.TestCase):
    """REQ-M06: contract types are enforced, so an off-type value cannot buy a PASS."""

    def optimistic(self, **overrides):
        data = semantic(status="PASS")
        data.update(overrides)
        return data

    def test_off_type_top_level_fields_are_schema_invalid(self):
        cases = {
            "blocking_string": {"blocking": "true"},
            "blocking_number": {"blocking": 1},
            "blocking_true": {"blocking": True},
            "evidence_refs_string": {"evidence_refs": "not-a-list"},
            "evidence_refs_item_not_a_string": {"evidence_refs": [7]},
            "status_list": {"status": []},
            "status_dict": {"status": {}},
        }
        for name, overrides in cases.items():
            with self.subTest(case=name):
                errors = validate_semantic_result(self.optimistic(**overrides), "evaluate")
                self.assertIn("SEMANTIC_SCHEMA_INVALID", errors)

    def test_off_type_finding_fields_are_schema_invalid(self):
        """Each case is a complete finding with exactly one field off-type.

        The fixtures used to omit the other mandatory fields, so the presence check
        answered first and the type of `blocking`/`disposition`/`risk` was never the
        reason the case was rejected. One override at a time keeps each type check
        independently covered.
        """
        cases = {
            "blocking_string": {"blocking": "true"},
            "blocking_number": {"blocking": 1},
            "blocking_null": {"blocking": None},
            "disposition_wrong_case": {"disposition": "Block"},
            "disposition_lowercase_human": {"disposition": "human"},
            "disposition_not_a_string": {"disposition": ["BLOCK"]},
            "disposition_unknown": {"disposition": "DEFER"},
            "risk_unknown": {"risk": "CRITICAL"},
            "risk_not_a_string": {"risk": 3},
            "risk_lowercase": {"risk": "high"},
            "finding_id_not_a_string": {"finding_id": ["F1"]},
        }
        for name, overrides in cases.items():
            with self.subTest(case=name):
                errors = validate_semantic_result(
                    self.optimistic(findings=[finding(**overrides)]), "evaluate"
                )
                self.assertIn("SEMANTIC_SCHEMA_INVALID", errors)

    def test_an_off_type_status_is_reported_not_raised(self):
        errors = validate_semantic_result(self.optimistic(status=[]), "evaluate")
        self.assertIn("SEMANTIC_STATUS_INVALID", errors)

    def test_an_off_type_blocking_flag_cannot_derive_a_pass_floor(self):
        cases = {
            "top_level_blocking_string": self.optimistic(blocking="true"),
            "finding_blocking_string": self.optimistic(
                findings=[finding(blocking="true")]
            ),
            "finding_disposition_wrong_case": self.optimistic(
                findings=[finding(disposition="Block")]
            ),
            "finding_risk_unknown": self.optimistic(findings=[finding(risk="CRITICAL")]),
        }
        for name, data in cases.items():
            with self.subTest(case=name):
                self.assertEqual("BLOCKED", derive_semantic_floor(data))

    def test_a_contract_shaped_finding_still_validates(self):
        data = self.optimistic(findings=[{
            "finding_id": "F1", "risk": "LOW", "disposition": "PASS",
            "evidence_ref": "gate:test", "message": "fine", "blocking": False,
        }])
        self.assertEqual([], validate_semantic_result(data, "evaluate"))


class SemanticFindingRequiredFieldTests(unittest.TestCase):
    """The finding fields the contract requires are required, not merely type-checked.

    `contracts/provider-result-base.schema.json` requires every finding to carry
    `finding_id`, `risk`, `disposition`, `evidence_ref`, `message` and `blocking`, but
    the validator only looked at a field when the provider chose to send one. A finding
    that simply omitted `disposition` and `blocking` therefore validated clean and
    derived a PASS floor — a provider could drop exactly the two fields the gate reads.
    """

    def complete(self, **overrides):
        overrides.setdefault("risk", "HIGH")
        return finding(**overrides)

    def payload(self, item, status="PASS"):
        data = semantic(status=status)
        data["findings"] = [item]
        return data

    def test_every_required_finding_field_is_required(self):
        for field in ("finding_id", "risk", "disposition", "evidence_ref", "message", "blocking"):
            with self.subTest(missing=field):
                item = self.complete()
                del item[field]
                errors = validate_semantic_result(self.payload(item), "evaluate")
                self.assertIn("SEMANTIC_SCHEMA_INVALID", errors)

    def test_a_finding_missing_required_fields_cannot_derive_a_pass_floor(self):
        for field in ("disposition", "blocking", "evidence_ref", "message"):
            with self.subTest(missing=field):
                item = self.complete()
                del item[field]
                self.assertEqual("BLOCKED", derive_semantic_floor(self.payload(item)))

    def test_the_reported_finding_shape_from_the_review_is_rejected(self):
        # The exact payload the reviewer reproduced: two model-owned fields and nothing
        # the gate reads. It validated clean and floored at PASS.
        data = self.payload({"finding_id": "F1", "risk": "HIGH"})
        self.assertIn("SEMANTIC_SCHEMA_INVALID", validate_semantic_result(data, "evaluate"))
        self.assertEqual("BLOCKED", derive_semantic_floor(data))

    def test_off_type_required_string_fields_are_schema_invalid(self):
        cases = {
            "evidence_ref_not_a_string": {"evidence_ref": 7},
            "evidence_ref_null": {"evidence_ref": None},
            "message_not_a_string": {"message": ["reviewed"]},
            "message_null": {"message": None},
        }
        for name, overrides in cases.items():
            with self.subTest(case=name):
                errors = validate_semantic_result(
                    self.payload(self.complete(**overrides)), "evaluate"
                )
                self.assertIn("SEMANTIC_SCHEMA_INVALID", errors)

    def test_a_complete_finding_validates_and_keeps_its_own_floor(self):
        self.assertEqual([], validate_semantic_result(self.payload(self.complete()), "evaluate"))
        self.assertEqual("PASS", derive_semantic_floor(self.payload(self.complete())))

    def test_a_complete_finding_still_drives_the_stricter_floors(self):
        blocking = self.complete(disposition="BLOCK", blocking=True)
        human = self.complete(disposition="HUMAN", risk="LOW")
        self.assertEqual("BLOCKED", derive_semantic_floor(self.payload(blocking, "BLOCKED")))
        self.assertEqual(
            "NEEDS_HUMAN_REVIEW", derive_semantic_floor(self.payload(human, "NEEDS_HUMAN_REVIEW"))
        )
        self.assertEqual(
            [], validate_semantic_result(self.payload(human, "NEEDS_HUMAN_REVIEW"), "evaluate")
        )


class EnvelopeValidationTests(unittest.TestCase):
    def test_parent_envelope_passes(self):
        self.assertEqual([], validate_execution_envelope(envelope(), "evaluate", "claude", PACKET))

    def test_stale_or_mutating_envelope_is_rejected(self):
        data = envelope()
        data["source_snapshot_after"] = "changed"
        data["repository_mutated"] = True
        errors = validate_execution_envelope(data, "evaluate", "claude", PACKET)
        self.assertIn("ENVELOPE_SNAPSHOT_CHANGED", errors)
        self.assertIn("ENVELOPE_REPOSITORY_MUTATED", errors)

    def test_timeout_and_weak_isolation_are_rejected(self):
        data = envelope()
        data["timed_out"] = True
        data["isolation_mode"] = "best-effort"
        errors = validate_execution_envelope(data, "evaluate", "claude", PACKET)
        self.assertIn("ENVELOPE_PROCESS_TIMEOUT", errors)
        self.assertIn("ENVELOPE_ISOLATION_NOT_ENFORCED", errors)

    def test_sealed_result_requires_both_halves(self):
        self.assertIn("SEALED_ENVELOPE_MISSING", validate_sealed_result({"semantic": semantic()}, "evaluate", "claude", PACKET))


class FinalizeTests(unittest.TestCase):
    def clean_records(self):
        return [
            sealed("evaluate", "claude"), sealed("evaluate", "codex"),
            sealed("review", "claude"), sealed("review", "codex"),
        ]

    def test_four_clean_sealed_results_pass(self):
        self.assertEqual("PASS", finalize(self.clean_records(), PACKET)["status"])

    def test_missing_envelope_fails_closed(self):
        records = self.clean_records()
        records[0] = {"semantic": semantic("evaluate")}
        self.assertEqual("BLOCKED", finalize(records, PACKET)["status"])

    def test_missing_provider_fails_closed(self):
        self.assertEqual("BLOCKED", finalize(self.clean_records()[:-1], PACKET)["status"])

    def test_semantic_blocker_fails_closed(self):
        records = self.clean_records()
        records[0]["semantic"]["status"] = "BLOCKED"
        records[0]["semantic"]["findings"] = [
            finding("AC-1", risk="HIGH", disposition="BLOCK", blocking=True)
        ]
        records[0]["semantic"]["blocking"] = ["AC-1"]
        reseal(records[0])
        self.assertEqual("BLOCKED", finalize(records, PACKET)["status"])

    def test_an_off_type_blocking_finding_never_finalizes_as_pass(self):
        cases = {
            "finding_blocking_string": {"blocking": "true"},
            "finding_blocking_number": {"blocking": 1},
            "finding_disposition_wrong_case": {"disposition": "Block"},
            "finding_risk_not_a_string": {"risk": 3},
        }
        for name, overrides in cases.items():
            with self.subTest(case=name):
                records = self.clean_records()
                records[0]["semantic"]["findings"] = [finding(**overrides)]
                reseal(records[0])
                self.assertEqual("BLOCKED", finalize(records, PACKET)["status"])

    def test_high_risk_disagreement_requires_human(self):
        records = self.clean_records()
        records[2]["semantic"]["status"] = "BLOCKED"
        records[2]["semantic"]["findings"] = [
            finding("F1", risk="HIGH", disposition="BLOCK")
        ]
        records[3]["semantic"]["findings"] = [
            finding("F2", risk="HIGH", disposition="PASS")
        ]
        reseal(records[2])
        reseal(records[3])
        self.assertEqual("NEEDS_HUMAN_REVIEW", finalize(records, PACKET)["status"])

    def test_high_blocking_finding_never_passes(self):
        records = self.clean_records()
        records[0]["semantic"]["findings"] = [
            finding("F1", risk="HIGH", disposition="BLOCK", blocking=True)
        ]
        reseal(records[0])
        final = finalize(records, PACKET)
        self.assertEqual("BLOCKED", final["status"])
        self.assertEqual(["FINAL_SEALED_RESULT_INVALID"], final["error_codes"])
        self.assertIn(
            "SEMANTIC_STATUS_CONTRADICTS_FINDINGS", final["validation"]["evaluate:claude"]
        )

    def test_finalize_derives_blocked_from_findings_when_validation_is_bypassed(self):
        records = self.clean_records()
        records[0]["semantic"]["findings"] = [
            finding("F1", risk="HIGH", disposition="BLOCK", blocking=True)
        ]
        reseal(records[0])
        with patch("hb_eval_review.finalize.validate_sealed_result", return_value=[]):
            final = finalize(records, PACKET)
        self.assertEqual("BLOCKED", final["status"])
        self.assertEqual(["FINAL_PROVIDER_BLOCKER"], final["error_codes"])

    def test_finalize_derives_human_review_from_findings_when_validation_is_bypassed(self):
        records = self.clean_records()
        records[0]["semantic"]["findings"] = [
            finding("F1", risk="LOW", disposition="HUMAN")
        ]
        reseal(records[0])
        with patch("hb_eval_review.finalize.validate_sealed_result", return_value=[]):
            final = finalize(records, PACKET)
        self.assertEqual("NEEDS_HUMAN_REVIEW", final["status"])
        self.assertEqual(["FINAL_PROVIDER_ESCALATION"], final["error_codes"])

    def test_conservative_provider_block_without_findings_still_blocks(self):
        # A provider may block on something it cannot express as a finding; the
        # explicit status must stand on its own, not only through the findings floor.
        records = self.clean_records()
        records[0]["semantic"]["status"] = "BLOCKED"
        reseal(records[0])
        final = finalize(records, PACKET)
        self.assertEqual("BLOCKED", final["status"])
        self.assertEqual(["FINAL_PROVIDER_BLOCKER"], final["error_codes"])

    def test_provider_human_review_without_findings_escalates(self):
        records = self.clean_records()
        records[2]["semantic"]["status"] = "NEEDS_HUMAN_REVIEW"
        reseal(records[2])
        final = finalize(records, PACKET)
        self.assertEqual("NEEDS_HUMAN_REVIEW", final["status"])
        self.assertEqual(["FINAL_PROVIDER_ESCALATION"], final["error_codes"])

    def test_off_schema_record_fails_closed_without_a_traceback(self):
        records = self.clean_records()
        records[1]["semantic"]["blocking"] = [{"id": "F1"}]
        reseal(records[1])
        final = finalize(records, PACKET)
        self.assertEqual("BLOCKED", final["status"])
        self.assertEqual(["FINAL_SEALED_RESULT_INVALID"], final["error_codes"])
        self.assertIn("SEMANTIC_SCHEMA_INVALID", final["validation"]["evaluate:codex"])

    def test_tampered_semantic_fails_closed(self):
        records = self.clean_records()
        records[1]["semantic"]["summary"] = "tampered after sealing"
        final = finalize(records, PACKET)
        self.assertEqual("BLOCKED", final["status"])
        self.assertEqual(["FINAL_SEALED_RESULT_INVALID"], final["error_codes"])
        self.assertIn("SEALED_RESULT_HASH_MISMATCH", final["validation"]["evaluate:codex"])


class FinalExecutionBlockerTests(unittest.TestCase):
    """EV-2: the fail-closed clause this PR moved must be pinned by its own test.

    `validate_execution_envelope` deliberately never reads `status` — it checks the
    facts the parent measured. That makes `finalize` the only thing standing between an
    operator-supplied non-PASS envelope and a PASS verdict, and until now nothing held
    it there: deleting the clause left the suite green.
    """

    def clean_records(self):
        return [
            sealed("evaluate", "claude"), sealed("evaluate", "codex"),
            sealed("review", "claude"), sealed("review", "codex"),
        ]

    def blocked_envelope_record(self, records, index, status, error_code):
        records[index]["envelope"]["status"] = status
        records[index]["envelope"]["error_code"] = error_code
        return records

    def test_the_status_field_is_not_part_of_envelope_validation(self):
        # States the division of labour the clause depends on: if this ever starts
        # failing, `finalize` is no longer the only guard and the clause can move.
        record = self.blocked_envelope_record(
            self.clean_records(), 0, "BLOCKED", "PROCESS_TIMEOUT"
        )[0]
        errors = validate_execution_envelope(record["envelope"], "evaluate", "claude", PACKET)
        self.assertEqual([], errors)

    def test_a_non_pass_execution_envelope_blocks_the_final_result(self):
        cases = {
            "evaluate_claude": (0, "BLOCKED", "PROCESS_NONZERO"),
            "evaluate_codex": (1, "BLOCKED", "PROVIDER_HOME_NOT_REMOVED"),
            "review_claude": (2, "BLOCKED", "PURGE_INCOMPLETE"),
            "review_codex": (3, "NEEDS_HUMAN_REVIEW", "PROVIDER_DESCENDANTS_ALIVE"),
        }
        for name, (index, status, error_code) in cases.items():
            with self.subTest(case=name):
                records = self.blocked_envelope_record(
                    self.clean_records(), index, status, error_code
                )
                final = finalize(records, PACKET)
                self.assertEqual("BLOCKED", final["status"])
                self.assertEqual(["FINAL_EXECUTION_BLOCKER"], final["error_codes"])

    def test_an_execution_blocker_outranks_a_provider_blocker(self):
        # The clause sits above the semantic floor on purpose (P0-4 option (a)): a
        # parent-measured failure is reported as one, not as the provider's own verdict.
        records = self.blocked_envelope_record(
            self.clean_records(), 0, "BLOCKED", "PROCESS_TIMEOUT"
        )
        records[1]["semantic"]["status"] = "BLOCKED"
        reseal(records[1])
        final = finalize(records, PACKET)
        self.assertEqual(["FINAL_EXECUTION_BLOCKER"], final["error_codes"])

    def test_an_execution_blocker_outranks_a_high_risk_disagreement(self):
        records = self.blocked_envelope_record(
            self.clean_records(), 3, "BLOCKED", "PROCESS_TIMEOUT"
        )
        records[0]["semantic"]["status"] = "BLOCKED"
        records[0]["semantic"]["findings"] = [
            finding("F1", risk="HIGH", disposition="BLOCK")
        ]
        records[1]["semantic"]["findings"] = [
            finding("F2", risk="HIGH", disposition="PASS")
        ]
        reseal(records[0])
        reseal(records[1])
        final = finalize(records, PACKET)
        self.assertEqual("BLOCKED", final["status"])
        self.assertEqual(["FINAL_EXECUTION_BLOCKER"], final["error_codes"])

    def test_a_provider_blocker_without_findings_still_blocks_on_clean_envelopes(self):
        for status, expected_status, expected_code in (
            ("BLOCKED", "BLOCKED", "FINAL_PROVIDER_BLOCKER"),
            ("NEEDS_HUMAN_REVIEW", "NEEDS_HUMAN_REVIEW", "FINAL_PROVIDER_ESCALATION"),
        ):
            with self.subTest(status=status):
                records = self.clean_records()
                records[2]["semantic"]["status"] = status
                records[2]["semantic"]["findings"] = []
                records[2]["semantic"]["blocking"] = []
                reseal(records[2])
                final = finalize(records, PACKET)
                self.assertEqual(expected_status, final["status"])
                self.assertEqual([expected_code], final["error_codes"])


class SealedResultHashTests(unittest.TestCase):
    def test_runtime_exposes_one_canonical_definition(self):
        self.assertEqual(
            canonical_json_bytes({"a": 2, "b": 1}),
            result_validation.canonical_bytes({"b": 1, "a": 2}),
        )
        self.assertIs(run_provider.canonical_bytes, result_validation.canonical_bytes)

    def test_canonical_is_key_order_and_whitespace_insensitive(self):
        left = {"b": 1, "a": {"d": 4, "c": 3}}
        right = {"a": {"c": 3, "d": 4}, "b": 1}
        self.assertEqual(
            result_validation.canonical_bytes(left), result_validation.canonical_bytes(right)
        )

    def test_clean_sealed_result_hash_validates(self):
        self.assertEqual([], validate_sealed_result(sealed(), "evaluate", "claude", PACKET))

    def test_semantic_tamper_is_rejected(self):
        record = sealed()
        record["semantic"]["summary"] = "tampered"
        self.assertIn(
            "SEALED_RESULT_HASH_MISMATCH",
            validate_sealed_result(record, "evaluate", "claude", PACKET),
        )

    def test_envelope_hash_tamper_is_rejected(self):
        record = sealed()
        digest = record["envelope"]["result_sha256"]
        record["envelope"]["result_sha256"] = ("b" if digest[0] != "b" else "c") + digest[1:]
        self.assertIn(
            "SEALED_RESULT_HASH_MISMATCH",
            validate_sealed_result(record, "evaluate", "claude", PACKET),
        )


if __name__ == "__main__":
    unittest.main()
