import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review.process import run_isolated_process

PACKET = {"packet_id": "p1", "source_snapshot_id": "s1", "evidence_bundle_id": "e1"}


@unittest.skipUnless(sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists(), "macOS sandbox required")
class MacSandboxIsolationTests(unittest.TestCase):
    def test_repository_write_is_denied(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repository = base / "repository"
            output = base / "output"
            repository.mkdir(); output.mkdir()
            target = repository / "protected.txt"
            target.write_text("original")
            command = [sys.executable, "-c", f"from pathlib import Path; Path({str(target)!r}).write_text('changed')"]
            result = run_isolated_process(command, repository, output, PACKET, "evaluate", "claude", 10, {})
            self.assertEqual("BLOCKED", result["envelope"]["status"])
            self.assertEqual("original", target.read_text())
            self.assertFalse(result["envelope"]["repository_mutated"])

    def test_designated_output_is_writable(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repository = base / "repository"
            output = base / "output"
            repository.mkdir(); output.mkdir()
            target = output / "result.json"
            command = [sys.executable, "-c", f"from pathlib import Path; Path({str(target)!r}).write_text('{{\"status\":\"PASS\"}}')"]
            result = run_isolated_process(command, repository, output, PACKET, "evaluate", "claude", 10, {})
            self.assertEqual("PASS", result["envelope"]["status"])
            self.assertTrue(target.is_file())
            self.assertEqual("macos-sandbox-exec", result["envelope"]["isolation_mode"])

    def test_peer_provider_output_read_is_denied(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repository = base / "repository"
            output = base / "claude-output"
            peer = base / "codex-output"
            repository.mkdir(); output.mkdir(); peer.mkdir()
            secret_finding = peer / "sealed.json"
            secret_finding.write_text("peer finding")
            command = [sys.executable, "-c", f"from pathlib import Path; print(Path({str(secret_finding)!r}).read_text())"]
            result = run_isolated_process(
                command, repository, output, PACKET, "evaluate", "claude", 10, {},
                denied_read_roots=[peer],
            )
            self.assertEqual("BLOCKED", result["envelope"]["status"])
            self.assertNotIn("peer finding", result["stdout"])


if __name__ == "__main__":
    unittest.main()
