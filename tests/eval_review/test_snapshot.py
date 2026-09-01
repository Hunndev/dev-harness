import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review.snapshot import (
    compute_evidence_bundle_id,
    compute_packet_id,
    compute_source_snapshot,
    validate_packet_bindings,
)


class SnapshotTests(unittest.TestCase):
    def make_repo(self):
        td = tempfile.TemporaryDirectory()
        repo = Path(td.name)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        (repo / "tracked.txt").write_text("one\n")
        subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
        return td, repo

    def test_untracked_content_changes_snapshot(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        before = compute_source_snapshot(repo)["source_snapshot_id"]
        (repo / "new file.txt").write_text("new\n")
        after = compute_source_snapshot(repo)["source_snapshot_id"]
        self.assertNotEqual(before, after)

    def test_staged_and_unstaged_changes_are_bound(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        base = compute_source_snapshot(repo)["source_snapshot_id"]
        (repo / "tracked.txt").write_text("two\n")
        unstaged = compute_source_snapshot(repo)["source_snapshot_id"]
        subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
        staged = compute_source_snapshot(repo)["source_snapshot_id"]
        self.assertNotEqual(base, unstaged)
        self.assertNotEqual(unstaged, staged)

    def test_generated_eval_results_do_not_self_invalidate(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        out = repo / ".harness" / "artifacts" / "x" / "eval-review"
        out.mkdir(parents=True)
        before = compute_source_snapshot(repo)["source_snapshot_id"]
        (out / "evaluate-result.json").write_text("{}")
        after = compute_source_snapshot(repo)["source_snapshot_id"]
        self.assertEqual(before, after)

    def test_evidence_and_packet_ids_change_with_inputs(self):
        e1 = compute_evidence_bundle_id([{"command": "pytest", "exit_code": 0, "sha256": "a" * 64}])
        e2 = compute_evidence_bundle_id([{"command": "pytest", "exit_code": 1, "sha256": "a" * 64}])
        self.assertNotEqual(e1, e2)
        p1 = compute_packet_id({"request": "x", "acceptance": ["A"]}, "s" * 64, e1)
        p2 = compute_packet_id({"request": "x", "acceptance": ["B"]}, "s" * 64, e1)
        self.assertNotEqual(p1, p2)

    def bound_packet(self, repo):
        evidence = repo / ".harness" / "artifacts" / "x" / "eval-review" / "gate.txt"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("gate pass\n")
        entries = [{
            "path": evidence.relative_to(repo).as_posix(),
            "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        }]
        source_id = compute_source_snapshot(repo)["source_snapshot_id"]
        evidence_id = compute_evidence_bundle_id(entries)
        request = {"text": "review this change", "acceptance_refs": ["tracked.txt"]}
        return {
            "packet_id": compute_packet_id(request, source_id, evidence_id),
            "source_snapshot_id": source_id,
            "evidence_bundle_id": evidence_id,
            "request": request,
            "evidence_entries": entries,
        }

    def test_packet_bindings_are_recomputed_from_source_and_evidence(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        packet = self.bound_packet(repo)
        self.assertEqual([], validate_packet_bindings(packet, repo))

        (repo / "tracked.txt").write_text("tampered\n")
        self.assertIn("SOURCE_SNAPSHOT_MISMATCH", validate_packet_bindings(packet, repo))

    def test_evidence_and_request_tampering_are_rejected(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        packet = self.bound_packet(repo)
        evidence = repo / packet["evidence_entries"][0]["path"]
        evidence.write_text("fabricated pass\n")
        self.assertIn("EVIDENCE_ENTRY_MISMATCH", validate_packet_bindings(packet, repo))

        evidence.write_text("gate pass\n")
        packet["request"] = {"text": "changed request"}
        self.assertIn("PACKET_ID_MISMATCH", validate_packet_bindings(packet, repo))


if __name__ == "__main__":
    unittest.main()
