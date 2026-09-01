import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review.process import run_read_only_process
from hb_eval_review.snapshot import compute_source_snapshot


class ProcessTests(unittest.TestCase):
    def test_success_captures_output(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_read_only_process(
                [sys.executable, "-c", "print('OK')"], Path(td), timeout_seconds=2
            )
        self.assertEqual("PASS", result["status"])
        self.assertEqual("OK", result["stdout"].strip())

    def test_timeout_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_read_only_process(
                [sys.executable, "-c", "import time; time.sleep(2)"], Path(td), timeout_seconds=0.05
            )
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("PROCESS_TIMEOUT", result["error_code"])

    def test_nonzero_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_read_only_process(
                [sys.executable, "-c", "raise SystemExit(7)"], Path(td), timeout_seconds=2
            )
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("PROCESS_NONZERO", result["error_code"])

    def test_unrelated_secret_environment_is_not_inherited(self):
        old = os.environ.get("DATABASE_PASSWORD")
        os.environ["DATABASE_PASSWORD"] = "must-not-leak"
        try:
            with tempfile.TemporaryDirectory() as td:
                result = run_read_only_process(
                    [sys.executable, "-c", "import os; print(os.getenv('DATABASE_PASSWORD','ABSENT'))"],
                    Path(td), timeout_seconds=2
                )
            self.assertEqual("ABSENT", result["stdout"].strip())
        finally:
            if old is None:
                os.environ.pop("DATABASE_PASSWORD", None)
            else:
                os.environ["DATABASE_PASSWORD"] = old


if __name__ == "__main__":
    unittest.main()
