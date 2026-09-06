import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "hb-eval-review"
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review import cli


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

    def sealed_fixture(self):
        semantic = {
            "schema_version": "2.0", "stage": "evaluate", "status": "PASS",
            "blocking": [], "findings": [], "evidence_refs": ["gate:test"],
        }
        canonical = json.dumps(
            semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        envelope = {
            "schema_version": "2.0", "stage": "evaluate", "engine": "claude",
            "provider": "claude", "run_id": "run-1", "started_at": "a", "finished_at": "b",
            "exit_code": 0, "timed_out": False, "fresh_process": True,
            "session_resumed": False, "isolation_mode": "macos-sandbox-exec",
            "source_snapshot_before": "s" * 64, "source_snapshot_after": "s" * 64,
            "packet_id": "p" * 64, "evidence_bundle_id": "e" * 64,
            "repository_mutated": False,
            "result_sha256": hashlib.sha256(canonical).hexdigest(),
            "status": "PASS", "error_code": None,
        }
        return {"semantic": semantic, "envelope": envelope}

    def test_validate_detects_semantic_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            packet = base / "packet.json"
            packet.write_text(json.dumps({
                "packet_id": "p" * 64,
                "source_snapshot_id": "s" * 64,
                "evidence_bundle_id": "e" * 64,
            }))
            record = self.sealed_fixture()
            result = base / "sealed.json"
            result.write_text(json.dumps(record))
            clean = subprocess.run(
                [str(CLI), "validate", "--stage", "evaluate", "--engine", "claude",
                 str(packet), str(result)], text=True, capture_output=True)
            self.assertEqual(0, clean.returncode, clean.stdout + clean.stderr)

            record["semantic"]["summary"] = "tampered"
            result.write_text(json.dumps(record))
            tampered = subprocess.run(
                [str(CLI), "validate", "--stage", "evaluate", "--engine", "claude",
                 str(packet), str(result)], text=True, capture_output=True)
        self.assertEqual(2, tampered.returncode)
        self.assertIn("SEALED_RESULT_HASH_MISMATCH", json.loads(tampered.stdout)["errors"])

    def test_run_command_is_exposed_for_full_dual_workflow(self):
        cp = subprocess.run([str(CLI), "run", "--help"], text=True, capture_output=True)
        self.assertEqual(0, cp.returncode, cp.stderr)
        self.assertIn("--packet-source", cp.stdout)
        self.assertIn("--evaluate-prompt", cp.stdout)
        self.assertIn("--review-prompt", cp.stdout)
        self.assertIn("--output-root", cp.stdout)
        self.assertIn("--claude-model", cp.stdout)
        self.assertIn("--codex-model", cp.stdout)

    def test_run_blocks_on_secret_material_before_provider_launch(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = base / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=source, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
            (source / "a.txt").write_text("a\n")
            (source / ".env").write_text("DB_PASSWORD=hunter2\n")
            subprocess.run(["git", "add", "-A"], cwd=source, check=True)
            subprocess.run(["git", "commit", "-qm", "init"], cwd=source, check=True)
            packet = base / "packet.json"
            packet.write_text(json.dumps({
                "packet_id": "p" * 64,
                "source_snapshot_id": "s" * 64,
                "evidence_bundle_id": "e" * 64,
                "request": {}, "evidence_entries": [],
            }))
            evaluate = base / "evaluate.md"; evaluate.write_text("evaluate")
            review = base / "review.md"; review.write_text("review")
            output = base / "output"
            cp = subprocess.run([
                str(CLI), "run", "--packet", str(packet), "--packet-source", str(source),
                "--evaluate-prompt", str(evaluate), "--review-prompt", str(review),
                "--output-root", str(output), "--claude-model", "sonnet",
                "--codex-model", "gpt-5.6-sol",
            ], text=True, capture_output=True)
            result = json.loads(cp.stdout)
            output_created = output.exists()
        self.assertEqual(2, cp.returncode)
        self.assertEqual("BLOCKED", result["status"])
        self.assertIn("PACKET_SECRET_MATERIAL_PRESENT", result["errors"])
        self.assertFalse(output_created)
        self.assertNotIn("hunter2", cp.stdout)
        self.assertNotIn("hunter2", cp.stderr)

    def test_snapshot_blocks_on_secret_material(self):
        # AC-2b: the refusal names the path; the refused bytes reach no output stream.
        marker = "KEYSTORE-MARKER-hunter2-do-not-print"
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=source, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
            (source / "release.jks").write_text(marker + "\n")
            subprocess.run(["git", "add", "-A"], cwd=source, check=True)
            subprocess.run(["git", "commit", "-qm", "init"], cwd=source, check=True)
            cp = subprocess.run([str(CLI), "snapshot", str(source)], text=True, capture_output=True)
        self.assertEqual(2, cp.returncode)
        data = json.loads(cp.stdout)
        self.assertEqual("BLOCKED", data["status"])
        self.assertIn("PACKET_SECRET_MATERIAL_PRESENT", data["errors"])
        self.assertIn("release.jks", data["paths"])
        self.assertNotIn(marker, cp.stdout)
        self.assertNotIn(marker, cp.stderr)

    def test_run_blocked_on_secret_material_prints_no_file_content(self):
        marker = "ENV-MARKER-hunter2-do-not-print"
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = base / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=source, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
            (source / ".env").write_text("DB_PASSWORD=" + marker + "\n")
            subprocess.run(["git", "add", "-A"], cwd=source, check=True)
            subprocess.run(["git", "commit", "-qm", "init"], cwd=source, check=True)
            packet = base / "packet.json"
            packet.write_text(json.dumps({
                "packet_id": "p" * 64, "source_snapshot_id": "s" * 64,
                "evidence_bundle_id": "e" * 64, "request": {}, "evidence_entries": [],
            }))
            evaluate = base / "evaluate.md"; evaluate.write_text("evaluate")
            review = base / "review.md"; review.write_text("review")
            cp = subprocess.run([
                str(CLI), "run", "--packet", str(packet), "--packet-source", str(source),
                "--evaluate-prompt", str(evaluate), "--review-prompt", str(review),
                "--output-root", str(base / "output"), "--claude-model", "sonnet",
                "--codex-model", "gpt-5.6-sol",
            ], text=True, capture_output=True)
        self.assertEqual(2, cp.returncode)
        self.assertIn("PACKET_SECRET_MATERIAL_PRESENT", json.loads(cp.stdout)["errors"])
        self.assertNotIn(marker, cp.stdout)
        self.assertNotIn(marker, cp.stderr)

    def test_off_schema_provider_result_fails_closed_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            packet = base / "packet.json"
            packet.write_text(json.dumps({
                "packet_id": "p" * 64, "source_snapshot_id": "s" * 64,
                "evidence_bundle_id": "e" * 64,
            }))
            record = self.sealed_fixture()
            record["semantic"]["blocking"] = [{"id": "F1"}]
            result = base / "sealed.json"
            result.write_text(json.dumps(record))
            cp = subprocess.run(
                [str(CLI), "validate", "--stage", "evaluate", "--engine", "claude",
                 str(packet), str(result)], text=True, capture_output=True)
        self.assertEqual(2, cp.returncode)
        self.assertNotIn("Traceback", cp.stderr)
        data = json.loads(cp.stdout)
        self.assertEqual("BLOCKED", data["status"])
        self.assertIn("SEMANTIC_SCHEMA_INVALID", data["errors"])

    def test_off_schema_finalize_input_fails_closed_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            packet = base / "packet.json"
            packet.write_text(json.dumps({
                "packet_id": "p" * 64, "source_snapshot_id": "s" * 64,
                "evidence_bundle_id": "e" * 64,
            }))
            paths = []
            for index, (stage, engine) in enumerate(
                (("evaluate", "claude"), ("evaluate", "codex"),
                 ("review", "claude"), ("review", "codex"))
            ):
                record = self.sealed_fixture()
                record["semantic"]["stage"] = stage
                record["envelope"]["stage"] = stage
                record["envelope"]["engine"] = engine
                record["envelope"]["provider"] = engine
                if index == 0:
                    record["semantic"]["findings"] = {"finding_id": "F1"}
                record["envelope"]["result_sha256"] = hashlib.sha256(
                    json.dumps(
                        record["semantic"], ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                path = base / f"{stage}-{engine}.json"
                path.write_text(json.dumps(record))
                paths.append(str(path))
            cp = subprocess.run(
                [str(CLI), "finalize", str(packet)] + paths, text=True, capture_output=True)
        self.assertEqual(2, cp.returncode)
        self.assertNotIn("Traceback", cp.stderr)
        data = json.loads(cp.stdout)
        self.assertEqual("BLOCKED", data["status"])
        self.assertIn(
            "SEMANTIC_SCHEMA_INVALID", data["validation"]["evaluate:claude"]
        )

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
                "--codex-model", "gpt-5.6-sol",
            ], text=True, capture_output=True)
            result = json.loads(cp.stdout)
            output_created = output.exists()
        self.assertEqual(2, cp.returncode)
        self.assertEqual("BLOCKED", result["status"])
        self.assertIn("PACKET_REQUEST_MISSING", result["errors"])
        self.assertFalse(output_created)


class CliFailClosedTests(unittest.TestCase):
    """CLAUDE.md fail-closed: a runtime fault leaves a JSON verdict, not a traceback."""

    def invoke(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cli.main(argv)
        return code, buffer.getvalue()

    def test_an_unexpected_runtime_fault_becomes_a_blocked_document(self):
        cases = {
            "runtime": RuntimeError("boom detail"),
            "memory": MemoryError("boom detail"),
            "type": TypeError("boom detail"),
            "attribute": AttributeError("boom detail"),
        }
        for name, error in cases.items():
            with self.subTest(case=name):
                with patch.object(cli, "compute_source_snapshot", side_effect=error):
                    code, out = self.invoke(["snapshot", str(ROOT)])
                self.assertEqual(2, code)
                payload = json.loads(out)
                self.assertEqual("BLOCKED", payload["status"])
                self.assertEqual([type(error).__name__], payload["errors"])
                # The message may quote refused bytes; only the type is published.
                self.assertNotIn("boom detail", out)

    def test_an_interrupt_is_never_swallowed(self):
        for error in (KeyboardInterrupt(), SystemExit(3)):
            with self.subTest(case=type(error).__name__):
                with patch.object(cli, "compute_source_snapshot", side_effect=error):
                    with self.assertRaises(type(error)):
                        with contextlib.redirect_stdout(io.StringIO()):
                            cli.main(["snapshot", str(ROOT)])


class SealedResultPathTests(unittest.TestCase):
    """Sealed file names come from the parent envelope, never from model-owned text."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))
        from hb_eval_review import cli as cli_module
        self.cli = cli_module
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()

    def record(self, semantic_stage, envelope_stage, engine):
        return {
            "semantic": {"stage": semantic_stage, "status": "PASS"},
            "envelope": {"stage": envelope_stage, "engine": engine, "status": "PASS"},
        }

    def run_with(self, records):
        source = self.base / "source"
        source.mkdir()
        (source / "a.txt").write_text("a\n")
        prompts = {}
        for stage in ("evaluate", "review"):
            path = self.base / f"{stage}.md"
            path.write_text(stage + " prompt")
            prompts[stage] = path
        prompt_sha256 = {
            stage: hashlib.sha256(path.read_text().encode("utf-8")).hexdigest()
            for stage, path in prompts.items()
        }
        model_ids = {"claude": "sonnet", "codex": "gpt-5.6-sol"}
        packet_data = {
            "packet_id": "p" * 64, "source_snapshot_id": "s" * 64,
            "evidence_bundle_id": "e" * 64,
            "request": {"prompt_sha256": prompt_sha256, "model_ids": model_ids},
            "evidence_entries": [],
        }
        packet = self.base / "packet.json"
        packet.write_text(json.dumps(packet_data))
        output = self.base / "output"
        argv = [
            "run", "--packet", str(packet), "--packet-source", str(source),
            "--evaluate-prompt", str(prompts["evaluate"]),
            "--review-prompt", str(prompts["review"]),
            "--output-root", str(output),
            "--claude-model", "sonnet", "--codex-model", "gpt-5.6-sol",
        ]

        def fake_materialize(source_path, packet_path):
            (Path(packet_path) / "source").mkdir(parents=True)
            return {"materialized": {"entries": []}}

        with patch.object(self.cli, "validate_packet_bindings", return_value=[]), \
                patch.object(self.cli, "materialize_source_packet", fake_materialize), \
                patch.object(self.cli, "verify_materialized_packet", return_value=True), \
                patch.object(
                    self.cli, "run_dual_stages",
                    return_value={"status": "BLOCKED", "stage": "evaluate", "results": records},
                ), \
                patch("sys.stdout", new_callable=io.StringIO):
            code = self.cli.main(argv)
        return code, output

    def test_model_owned_stage_cannot_steer_the_sealed_file_path(self):
        escape = self.base / "escaped"
        escape.mkdir()
        records = [
            self.record(str(escape / "pwned"), "evaluate", "claude"),
            self.record("../../also-pwned", "evaluate", "codex"),
        ]
        code, output = self.run_with(records)
        self.assertEqual(2, code)
        sealed = sorted(path.name for path in (output / "sealed-results").iterdir())
        self.assertEqual(["evaluate-claude.json", "evaluate-codex.json"], sealed)
        self.assertEqual([], sorted(path.name for path in escape.iterdir()))
        written = {
            path.resolve() for path in self.base.rglob("*.json") if path.is_file()
        }
        outside = {
            path for path in written
            if output not in path.parents and path.name != "packet.json"
        }
        self.assertEqual(set(), outside)

    def test_unknown_envelope_stage_falls_back_to_an_indexed_name(self):
        records = [
            self.record("evaluate", "../escape", "claude"),
            self.record("evaluate", "evaluate", "not-an-engine"),
        ]
        code, output = self.run_with(records)
        self.assertEqual(2, code)
        sealed = sorted(path.name for path in (output / "sealed-results").iterdir())
        self.assertEqual(["unknown-0.json", "unknown-1.json"], sealed)


if __name__ == "__main__":
    unittest.main()
