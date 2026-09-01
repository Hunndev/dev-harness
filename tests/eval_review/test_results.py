import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review.finalize import finalize
from hb_eval_review.result_validation import (
    validate_execution_envelope,
    validate_sealed_result,
    validate_semantic_result,
)


PACKET = {"packet_id": "p1", "source_snapshot_id": "s1", "evidence_bundle_id": "e1"}


def semantic(stage="evaluate", status="PASS"):
    return {
        "schema_version": "2.0", "stage": stage, "status": status,
        "blocking": [], "findings": [], "evidence_refs": ["gate:test"],
    }


def envelope(stage="evaluate", engine="claude"):
    return {
        "schema_version": "2.0", "stage": stage, "engine": engine,
        "provider": engine, "run_id": f"run-{stage}-{engine}",
        "started_at": "2026-08-26T00:00:00Z", "finished_at": "2026-08-26T00:00:01Z",
        "exit_code": 0, "timed_out": False, "fresh_process": True,
        "session_resumed": False, "isolation_mode": "macos-sandbox-exec",
        "source_snapshot_before": "s1", "source_snapshot_after": "s1",
        "packet_id": "p1", "evidence_bundle_id": "e1",
        "repository_mutated": False, "result_sha256": "a" * 64,
        "status": "PASS", "error_code": None,
    }


def sealed(stage="evaluate", engine="claude", status="PASS"):
    return {"semantic": semantic(stage, status), "envelope": envelope(stage, engine)}


class SemanticValidationTests(unittest.TestCase):
    def test_model_self_attestation_is_rejected(self):
        data = semantic()
        data.update({"fresh": True, "read_only": True, "repository_mutated": False})
        errors = validate_semantic_result(data, "evaluate")
        self.assertIn("SEMANTIC_SELF_ATTESTATION_FORBIDDEN", errors)

    def test_clean_semantic_payload_passes(self):
        self.assertEqual([], validate_semantic_result(semantic(), "evaluate"))

    def test_empty_evidence_is_rejected(self):
        data = semantic()
        data["evidence_refs"] = []
        self.assertIn("SEMANTIC_EVIDENCE_MISSING", validate_semantic_result(data, "evaluate"))


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
        records[0]["semantic"]["blocking"] = ["AC-1"]
        self.assertEqual("BLOCKED", finalize(records, PACKET)["status"])

    def test_high_risk_disagreement_requires_human(self):
        records = self.clean_records()
        records[2]["semantic"]["findings"] = [{"risk": "HIGH", "disposition": "BLOCK"}]
        records[3]["semantic"]["findings"] = [{"risk": "HIGH", "disposition": "PASS"}]
        self.assertEqual("NEEDS_HUMAN_REVIEW", finalize(records, PACKET)["status"])


if __name__ == "__main__":
    unittest.main()
