import subprocess
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ("BE", "CM", "FE", "CHAT", "AOS", "IOS")


class PackagingTests(unittest.TestCase):
    def test_vendored_core_matches_canonical(self):
        result = subprocess.run(
            [sys.executable, "scripts/sync-eval-review-core.py", "--check"],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        self.assertEqual(0, result.returncode, result.stdout)

    def test_each_plugin_contains_minimum_contract(self):
        required = (
            "contracts/evaluate-result.schema.json",
            "contracts/review-result.schema.json",
            "contracts/tdd-test-design-result.schema.json",
            "runtime/hb_eval_review/finalize.py",
            "runtime/hb_eval_review/snapshot.py",
            "bin/hb-eval-review",
            "commands/shared/evaluate.md",
            "commands/shared/review.md",
        )
        for plugin in PLUGINS:
            for relative in required:
                self.assertTrue((ROOT / plugin / relative).is_file(), f"{plugin}/{relative}")
            self.assertTrue((ROOT / plugin / "bin/hb-eval-review").stat().st_mode & 0o111)

    def test_each_isolated_plugin_executes_without_shared_or_repository_scripts(self):
        for plugin in PLUGINS:
            with self.subTest(plugin=plugin), tempfile.TemporaryDirectory() as td:
                isolated = Path(td) / plugin.lower()
                shutil.copytree(ROOT / plugin, isolated)
                repository = Path(td) / "target-repository"
                repository.mkdir()
                subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
                subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repository, check=True)
                subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
                (repository / "a.txt").write_text("a")
                subprocess.run(["git", "add", "a.txt"], cwd=repository, check=True)
                subprocess.run(["git", "commit", "-qm", "init"], cwd=repository, check=True)
                result = subprocess.run(
                    [str(isolated / "bin/hb-eval-review"), "snapshot", str(repository)],
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("source_snapshot_id", result.stdout)


if __name__ == "__main__":
    unittest.main()
