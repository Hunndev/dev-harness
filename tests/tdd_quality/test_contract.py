import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review.tdd_quality import validate_test_design, validate_test_sensitivity


class TestDesignContract(unittest.TestCase):
    def valid_design(self):
        return {
            "schema_version": "1.0",
            "stage": "tdd-test-design",
            "tier": "T1",
            "status": "PASS",
            "test_id": "test_non_admin_cannot_delete_user",
            "acceptance_refs": ["AC-AUTH-1"],
            "red_failure_kind": "missing_behavior",
            "assertions": [{"kind": "observable_behavior", "description": "returns 403"}],
            "mocked_boundaries": ["external_identity_provider"],
            "system_under_test_mocked": False,
            "paths": ["failure", "boundary"],
            "reviewer": {"independent": False, "read_only": True},
        }

    def test_valid_t1_design_passes(self):
        self.assertEqual([], validate_test_design(self.valid_design()))

    def test_missing_ac_mapping_is_rejected(self):
        data = self.valid_design()
        data["acceptance_refs"] = []
        self.assertIn("TDD_AC_TRACE_MISSING", validate_test_design(data))

    def test_syntax_error_is_not_valid_red(self):
        data = self.valid_design()
        data["red_failure_kind"] = "syntax_error"
        self.assertIn("TDD_RED_REASON_INVALID", validate_test_design(data))

    def test_mocking_system_under_test_is_rejected(self):
        data = self.valid_design()
        data["system_under_test_mocked"] = True
        self.assertIn("TDD_SUT_MOCKED", validate_test_design(data))

    def test_non_behavior_assertion_is_rejected(self):
        data = self.valid_design()
        data["assertions"] = [{"kind": "implementation_detail", "description": "method called"}]
        self.assertIn("TDD_ASSERTION_WEAK", validate_test_design(data))

    def test_t2_requires_independent_read_only_lens(self):
        data = self.valid_design()
        data["tier"] = "T2"
        self.assertIn("TDD_T2_REVIEW_MISSING", validate_test_design(data))


class TestSensitivityContract(unittest.TestCase):
    def valid_sensitivity(self):
        return {
            "schema_version": "1.0",
            "stage": "tdd-sensitivity",
            "tier": "T1",
            "status": "PASS",
            "test_id": "test_non_admin_cannot_delete_user",
            "red_test_hash": "a" * 64,
            "green_test_hash": "a" * 64,
            "red_outcome": "FAIL",
            "green_outcome": "PASS",
            "approved_red_revision": False,
            "high_risk": False,
            "mutation": {"required": False, "performed": False, "outcome": "NOT_REQUIRED"},
            "regression": {"status": "PASS"},
        }

    def test_same_test_red_to_green_passes(self):
        self.assertEqual([], validate_test_sensitivity(self.valid_sensitivity()))

    def test_unapproved_test_change_is_rejected(self):
        data = self.valid_sensitivity()
        data["green_test_hash"] = "b" * 64
        self.assertIn("TDD_TEST_IDENTITY_CHANGED", validate_test_sensitivity(data))

    def test_wrong_transition_is_rejected(self):
        data = self.valid_sensitivity()
        data["red_outcome"] = "PASS"
        self.assertIn("TDD_TRANSITION_INVALID", validate_test_sensitivity(data))

    def test_required_high_risk_mutation_cannot_be_skipped(self):
        data = self.valid_sensitivity()
        data["tier"] = "T2"
        data["high_risk"] = True
        data["mutation"] = {"required": True, "performed": False, "outcome": "SKIPPED"}
        self.assertIn("TDD_MUTATION_EVIDENCE_MISSING", validate_test_sensitivity(data))


class WorkflowDocumentationContract(unittest.TestCase):
    def test_hotfix_keeps_lightweight_development_but_never_skips_dual_gates(self):
        for track in ("BE", "CM", "FE", "CHAT", "AOS", "IOS"):
            text = (ROOT / track / "commands" / "maintenance" / "hotfix.md").read_text()
            self.assertIn("### [H4] Gate → 검사(Evaluate) → 평가(Review)", text, track)
            self.assertIn("T0 Test Design Check", text, track)
            self.assertIn("T0 Test Sensitivity Check", text, track)
            self.assertIn("hb-eval-review run", text, track)
            self.assertNotIn("리뷰, 전체 회귀 모두 스킵", text, track)

    def test_repository_declared_canonical_docs_are_not_downgraded_to_auxiliary_cache(self):
        shared = (ROOT / "SHARED" / "CLAUDE.md").read_text()
        self.assertIn("진실의 원천은 작업 repository가 주제별로 선언", shared)
        self.assertIn("어느 한쪽을 자동으로 무시하지 않고", shared)

        for track in ("BE", "CM", "FE", "CHAT", "AOS", "IOS"):
            text = (ROOT / track / "CLAUDE.md").read_text()
            self.assertIn("진실의 원천", text, track)
            self.assertNotIn("보조 context", text, track)
            self.assertNotIn("보조 contract/context cache", text, track)

        readme = (ROOT / "README.md").read_text()
        self.assertIn("Repository 주제별 진실의 원천", readme)
        self.assertIn("충돌하면 어느 한쪽을 자동으로 무시하지 않고", readme)
        self.assertNotIn("선택적 보조 context", readme)


if __name__ == "__main__":
    unittest.main()
