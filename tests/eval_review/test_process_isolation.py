import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review.process import build_macos_sandbox_profile, run_isolated_process

PACKET = {"packet_id": "p1", "source_snapshot_id": "s1", "evidence_bundle_id": "e1"}


@unittest.skipUnless(sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists(), "macOS sandbox required")
class MacSandboxIsolationTests(unittest.TestCase):
    def test_profile_is_deny_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repository = base / "repository"
            output = base / "output"
            repository.mkdir(); output.mkdir()
            profile = build_macos_sandbox_profile(repository, output)
            self.assertIn("(deny default)", profile)
            self.assertNotIn("(allow default)", profile)
            self.assertIn('(deny mach-lookup (global-name "com.apple.securityd"))', profile)

    def test_repository_write_is_denied(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repository = base / "repository"
            output = base / "output"
            repository.mkdir(); output.mkdir()
            target = repository / "protected.txt"
            target.write_text("original")
            command = ["/bin/sh", "-c", f"printf changed > {shlex.quote(str(target))}"]
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
            command = ["/bin/sh", "-c", f"printf PASS > {shlex.quote(str(target))}"]
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
            command = ["/bin/sh", "-c", f"cat {shlex.quote(str(secret_finding))}"]
            result = run_isolated_process(
                command, repository, output, PACKET, "evaluate", "claude", 10, {},
                denied_read_roots=[peer],
            )
            self.assertEqual("BLOCKED", result["envelope"]["status"])
            self.assertNotIn("peer finding", result["stdout"])

    def test_unlisted_sibling_secret_read_is_denied(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repository = base / "repository"
            output = base / "output"
            private_home = base / "private-home"
            repository.mkdir(); output.mkdir(); private_home.mkdir()
            secret = private_home / "credential.txt"
            secret.write_text("must-not-be-visible")
            command = ["/bin/sh", "-c", f"cat {shlex.quote(str(secret))}"]
            result = run_isolated_process(
                command, repository, output, PACKET, "evaluate", "claude", 10, {}
            )
            self.assertEqual("BLOCKED", result["envelope"]["status"])
            self.assertNotIn("must-not-be-visible", result["stdout"])

    def test_keychain_cli_execution_is_denied(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repository = base / "repository"
            output = base / "output"
            repository.mkdir(); output.mkdir()
            result = run_isolated_process(
                ["/usr/bin/security", "list-keychains"],
                repository, output, PACKET, "evaluate", "codex", 10, {},
            )
            self.assertEqual("BLOCKED", result["envelope"]["status"])
            self.assertNotEqual(0, result["envelope"]["exit_code"])


if __name__ == "__main__":
    unittest.main()
