import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "hb-eval-review"


class CliTests(unittest.TestCase):
    def test_snapshot_emits_content_bound_json(self):
        cp = subprocess.run([str(CLI), "snapshot", str(ROOT)], text=True, capture_output=True)
        self.assertEqual(0, cp.returncode, cp.stderr)
        data = json.loads(cp.stdout)
        self.assertEqual(64, len(data["source_snapshot_id"]))

    def test_finalize_missing_results_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            packet = Path(td) / "packet.json"
            packet.write_text(json.dumps({
                "packet_id": "p" * 64,
                "source_snapshot_id": "s" * 64,
                "evidence_bundle_id": "e" * 64,
            }))
            cp = subprocess.run([str(CLI), "finalize", str(packet)], text=True, capture_output=True)
        self.assertEqual(2, cp.returncode)
        self.assertEqual("BLOCKED", json.loads(cp.stdout)["status"])

    def test_run_command_is_exposed_for_full_dual_workflow(self):
        cp = subprocess.run([str(CLI), "run", "--help"], text=True, capture_output=True)
        self.assertEqual(0, cp.returncode, cp.stderr)
        self.assertIn("--packet-source", cp.stdout)
        self.assertIn("--evaluate-prompt", cp.stdout)
        self.assertIn("--review-prompt", cp.stdout)
        self.assertIn("--output-root", cp.stdout)
        self.assertIn("--claude-model", cp.stdout)
        self.assertIn("--codex-model", cp.stdout)

    def test_run_recomputes_packet_bindings_before_provider_launch(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = base / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=source, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
            (source / "a.txt").write_text("a\n")
            subprocess.run(["git", "add", "a.txt"], cwd=source, check=True)
            subprocess.run(["git", "commit", "-qm", "init"], cwd=source, check=True)
            packet = base / "packet.json"
            packet.write_text(json.dumps({
                "packet_id": "p" * 64,
                "source_snapshot_id": "s" * 64,
                "evidence_bundle_id": "e" * 64,
            }))
            evaluate = base / "evaluate.md"; evaluate.write_text("evaluate")
            review = base / "review.md"; review.write_text("review")
            output = base / "output"
            cp = subprocess.run([
                str(CLI), "run", "--packet", str(packet), "--packet-source", str(source),
                "--evaluate-prompt", str(evaluate), "--review-prompt", str(review),
                "--output-root", str(output), "--claude-model", "sonnet",
                "--codex-model", "gpt-5.6-sol-900k",
            ], text=True, capture_output=True)
            result = json.loads(cp.stdout)
            output_created = output.exists()
        self.assertEqual(2, cp.returncode)
        self.assertEqual("BLOCKED", result["status"])
        self.assertIn("PACKET_REQUEST_MISSING", result["errors"])
        self.assertFalse(output_created)


if __name__ == "__main__":
    unittest.main()
