"""Keep the public TDD contract within the observed runtime trust boundary."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STACKS = ("BE", "CM", "FE", "CHAT", "AOS", "IOS")
TDD_DOCS = tuple(Path(stack) / "commands/shared/tdd.md" for stack in STACKS)
HOTFIX_DOCS = tuple(Path(stack) / "commands/maintenance/hotfix.md" for stack in STACKS)
SUMMARY_DOCS = (Path("README.md"), Path("SHARED/commands/evaluate.md"))


class ObservationLimitsDocumentationTests(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_consumers_document_observed_pair_and_immediate_migration(self):
        for relative in TDD_DOCS + HOTFIX_DOCS + SUMMARY_DOCS:
            text = self.read(relative)
            with self.subTest(doc=str(relative)):
                self.assertIn("TDD_OBSERVATION_REQUIRED", text)
                self.assertRegex(text, r"Gate.{0,12}pack.{0,12}run")
                self.assertRegex(text, r"1\.2.{0,20}관측 쌍")
                self.assertIn("진행 중인 작업", text)
                self.assertIn("즉시", text)
                self.assertIn("tdd-check", text)
                self.assertIn("재실행", text)

    def test_docs_explain_state_deletion_resets_baseline_without_external_ledger(self):
        # The behavioral state-deletion guard lives with the runtime tests.
        # These statements must remain visible where users learn the guarantee.
        for relative in TDD_DOCS + SUMMARY_DOCS:
            text = self.read(relative)
            with self.subTest(doc=str(relative)):
                self.assertIn("eval-review/tdd-check/", text)
                self.assertIn("tdd-test-design-result.json", text)
                self.assertRegex(text, r"삭제[^\n.]*초기화")
                self.assertRegex(text, r"외부 원장[^\n.]*없")
                self.assertRegex(text, r"절차[^\n.]*금지")

    def test_docs_limit_digest_and_approval_claims_to_local_state_checks(self):
        for relative in TDD_DOCS + SUMMARY_DOCS:
            text = self.read(relative)
            with self.subTest(doc=str(relative)):
                self.assertIn("로컬 상태가 온전", text)
                self.assertIn("형식이 맞는 외부 기록", text)
                self.assertRegex(text, r"digest[^\n.]*재계산")
                self.assertRegex(text, r"암호학[^\n.]*신원[^\n.]*보장하지")

    def test_docs_distinguish_inline_rejection_from_repository_report_forgery(self):
        for relative in TDD_DOCS + (Path("README.md"),):
            text = self.read(relative)
            with self.subTest(doc=str(relative)):
                self.assertIn("TDD_COMMAND_INVALID", text)
                for inline_form in ("bash -c", "python -c", "node -e"):
                    self.assertIn(inline_form, text)
                self.assertIn("conftest", text)
                self.assertIn("npm script", text)
                self.assertIn("reporter", text)
                self.assertRegex(text, r"위조[^\n.]*막지 못")

    def test_jest_docs_explain_phase_fallback_and_accepted_async_hook_risk(self):
        for relative in TDD_DOCS + (Path("README.md"),):
            text = self.read(relative)
            with self.subTest(doc=str(relative)):
                self.assertIn("--testLocationInResults", text)
                self.assertIn("_callCircusHook", text)
                self.assertIn("TDD_JEST_PHASE_UNSUPPORTED", text)
                self.assertRegex(text, r"async hook[^\n.]*통과할 수")
                self.assertIn("noStackTrace", text)
                self.assertIn("jasmine", text)
                self.assertIn("testEnvironment", text)
                self.assertIn("testRunner", text)


if __name__ == "__main__":
    unittest.main()
