import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review.orchestrate import run_dual_stages

PACKET = {"packet_id": "p1", "source_snapshot_id": "s1", "evidence_bundle_id": "e1"}


def sealed(stage, engine, semantic_status="PASS", envelope_status="PASS"):
    return {
        "semantic": {
            "schema_version": "2.0", "stage": stage, "status": semantic_status,
            "blocking": ["x"] if semantic_status == "BLOCKED" else [],
            "findings": [], "evidence_refs": ["gate:test"],
        },
        "envelope": {
            "schema_version": "2.0", "stage": stage, "engine": engine, "provider": engine,
            "run_id": f"{stage}-{engine}", "started_at": "a", "finished_at": "b",
            "exit_code": 0 if envelope_status == "PASS" else 1, "timed_out": False,
            "fresh_process": True, "session_resumed": False,
            "isolation_mode": "macos-sandbox-exec",
            "source_snapshot_before": "s1", "source_snapshot_after": "s1",
            "packet_id": "p1", "evidence_bundle_id": "e1", "repository_mutated": False,
            "result_sha256": "a" * 64, "status": envelope_status,
            "error_code": None if envelope_status == "PASS" else "PROCESS_NONZERO",
        },
    }


class OrchestrateTests(unittest.TestCase):
    def test_review_starts_only_after_two_sealed_evaluates_pass(self):
        calls = []
        def runner(stage, engine):
            calls.append((stage, engine))
            return sealed(stage, engine)
        result = run_dual_stages(runner, PACKET)
        self.assertEqual("PASS", result["status"])
        self.assertEqual({("evaluate", "claude"), ("evaluate", "codex")}, set(calls[:2]))
        self.assertEqual({("review", "claude"), ("review", "codex")}, set(calls[2:]))

    def test_missing_envelope_prevents_review(self):
        calls = []
        def runner(stage, engine):
            calls.append((stage, engine))
            item = sealed(stage, engine)
            if stage == "evaluate" and engine == "codex":
                item.pop("envelope")
            return item
        result = run_dual_stages(runner, PACKET)
        self.assertEqual("BLOCKED", result["status"])
        self.assertFalse(any(stage == "review" for stage, _ in calls))

    def test_execution_block_prevents_review(self):
        calls = []
        def runner(stage, engine):
            calls.append((stage, engine))
            return sealed(stage, engine, envelope_status="BLOCKED" if engine == "codex" else "PASS")
        result = run_dual_stages(runner, PACKET)
        self.assertEqual("BLOCKED", result["status"])
        self.assertFalse(any(stage == "review" for stage, _ in calls))


if __name__ == "__main__":
    unittest.main()
