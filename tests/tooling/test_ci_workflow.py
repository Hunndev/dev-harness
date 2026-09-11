"""dev-13 acceptance test: the CI workflow actually runs the runtime suites on both OSes and audits skips."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "lint-harness.yml"


class CiWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_tests_job_runs_both_suites_with_explicit_start_dirs(self) -> None:
        self.assertIn("python3 -m unittest discover -s tests/eval_review -v", self.text)
        self.assertIn("python3 -m unittest discover -s tests/tdd_quality -v", self.text)
        self.assertIn("python3 -m unittest discover -s tests/tooling -v", self.text)
        self.assertNotIn("unittest discover -s tests -v", self.text, "-s tests collects 0 tests")

    def test_matrix_covers_ubuntu_and_macos(self) -> None:
        self.assertIn("ubuntu-24.04", self.text)
        self.assertIn("macos-14", self.text)
        self.assertIn("actions/checkout@v4", self.text)
        self.assertIn("actions/setup-python@v5", self.text)

    def test_darwin_only_skips_are_audited(self) -> None:
        self.assertIn("macOS sandbox required", self.text)
        self.assertIn("macOS filesystem semantics required", self.text)
        self.assertIn("expected_sandbox=7", self.text)
        self.assertIn("expected_fs=9", self.text)
        self.assertIn("expected_sandbox=0; expected_fs=0", self.text)

    def _audit_script(self) -> str:
        start = self.text.index("- name: Audit macOS-only skips")
        block = self.text[start:]
        block = block[block.index("run: |") + len("run: |"):]
        lines = []
        for line in block.splitlines()[1:]:
            if line.strip().startswith("- name:") or (line.strip() and not line.startswith("          ")):
                break
            lines.append(line[10:])
        return "\n".join(lines)

    def _run_audit(self, runner_os: str, darwin_skips: int, fs_skips: int = 0, other_skips: int = 1) -> int:
        import os, subprocess, tempfile
        script = self._audit_script()
        self.assertIn("grep -c", script)
        with tempfile.TemporaryDirectory() as tmp:
            log = ["test_x (m.C) ... ok"] + ["test_y (m.C) ... skipped 'macOS sandbox required'"] * darwin_skips
            log += ["test_w (m.C) ... skipped 'macOS filesystem semantics required'"] * fs_skips
            log += ["test_z (m.C) ... skipped 'root reads a 0o000 file'"] * other_skips
            (Path(tmp) / "eval_review.log").write_text("\n".join(log) + "\n", encoding="utf-8")
            return subprocess.run(["bash", "-c", script], cwd=tmp, env=dict(os.environ, RUNNER_OS=runner_os),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode

    def test_audit_step_logic_with_sample_logs(self) -> None:
        self.assertEqual(0, self._run_audit("macOS", 0, 0))
        self.assertNotEqual(0, self._run_audit("macOS", 7, 9))
        self.assertNotEqual(0, self._run_audit("macOS", 0, 1))
        self.assertEqual(0, self._run_audit("Linux", 7, 9))
        self.assertNotEqual(0, self._run_audit("Linux", 7, 0))
        self.assertNotEqual(0, self._run_audit("Linux", 6, 9))
        self.assertNotEqual(0, self._run_audit("Linux", 0, 0))

    def test_lint_job_is_kept(self) -> None:
        self.assertIn("./scripts/lint-harness.sh", self.text)


if __name__ == "__main__":
    unittest.main()
