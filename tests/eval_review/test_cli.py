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


class OutputContractTests(unittest.TestCase):
    """The shared Evaluate/Review documents list exactly the files ``run`` creates (dev-10a).

    Real: ``cli.command_run`` — its early-return checks, the output-root rules, the execution
    manifest, the materialized copy's location, the provider directories, the pre-Review
    cleanup, final-result.json and sealed-results/. Faked, to drive each scenario
    deterministically: packet-binding validation, materialization, the provider processes and
    the orchestration (``run_dual_stages`` is replaced by a fake that calls the real runner
    closure sequentially). This is a file-layout contract, not an integration test of parallel
    provider execution.
    """

    DOC_ROOT = ".harness/artifacts/{track}/{identifier}/eval-review/run-{n}/"
    DOCS = (ROOT / "SHARED" / "commands" / "evaluate.md", ROOT / "SHARED" / "commands" / "review.md")

    @classmethod
    def documented(cls, path):
        """Parse the ``## 산출물`` fenced block into ``{relative path: annotation}``."""
        text = path.read_text(encoding="utf-8")
        block = text.split("\n## 산출물\n", 1)[1].split("```text\n", 1)[1].split("\n```", 1)[0]
        lines = block.splitlines()
        assert lines[0].split()[0] == cls.DOC_ROOT, lines[0]
        entries = {}
        for line in lines[1:]:
            if not line.strip():
                continue
            token, _, note = line.strip().partition("←")
            entries[token.strip()] = note.strip()
        return entries

    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name)
        self.source = self.base / "source"
        self.source.mkdir()
        (self.source / "a.txt").write_text("a\n")
        self.prompts = {}
        for stage in ("evaluate", "review"):
            path = self.base / (stage + ".md")
            path.write_text(stage + " prompt")
            self.prompts[stage] = path
        self.prompt_sha256 = {
            stage: hashlib.sha256(path.read_bytes()).hexdigest() for stage, path in self.prompts.items()
        }
        self.model_ids = {"claude": "sonnet", "codex": "gpt-5.6-sol"}
        self.output = self.base / "output"

    def packet(self, **request_overrides):
        data = {
            "packet_id": "p" * 64, "source_snapshot_id": "s" * 64, "evidence_bundle_id": "e" * 64,
            "request": {"prompt_sha256": self.prompt_sha256, "model_ids": self.model_ids},
            "evidence_entries": [],
        }
        data["request"].update(request_overrides)
        path = self.base / "packet.json"
        path.write_text(json.dumps(data))
        return path

    def argv(self, packet):
        return [
            "run", "--packet", str(packet), "--packet-source", str(self.source),
            "--evaluate-prompt", str(self.prompts["evaluate"]),
            "--review-prompt", str(self.prompts["review"]),
            "--output-root", str(self.output),
            "--claude-model", "sonnet", "--codex-model", "gpt-5.6-sol",
        ]

    @staticmethod
    def listing(root):
        """Top-level names (directories end with ``/``) plus the sealed-results entries."""
        if not root.exists():
            return set()
        names = set()
        for path in root.iterdir():
            names.add(path.name + ("/" if path.is_dir() else ""))
            if path.name == "sealed-results" and path.is_dir():
                names.update("sealed-results/" + child.name for child in path.iterdir())
        return names

    def run_mocked(self, packet, review=True, materialized_ok=True, binding_errors=()):
        observed = {}

        def fake_materialize(source_path, packet_path):
            (Path(packet_path) / "source").mkdir(parents=True)
            (Path(packet_path) / "manifest.json").write_text("{}\n")
            return {"materialized": {"entries": []}}

        def fake_provider(engine, stage, packet, packet_source, output_root, prompt,
                          timeout_seconds=240, peer_output_root=None, model=None):
            Path(output_root).mkdir(parents=True, exist_ok=True)
            (Path(output_root) / "provider-output.txt").write_text(stage + " " + engine + "\n")
            return {
                "semantic": {"status": "PASS", "findings": [], "blocking": []},
                "envelope": {"stage": stage, "engine": engine, "status": "PASS"},
            }

        def fake_dual(runner, packet_data):
            evaluate = [runner("evaluate", engine) for engine in ("claude", "codex")]
            observed["after_evaluate"] = self.listing(self.output)
            if not review:
                return {"status": "BLOCKED", "stage": "evaluate",
                        "errors": {"codex": ["STAGE_EXECUTION_BLOCKER"]}, "results": evaluate}
            reviews = [runner("review", engine) for engine in ("claude", "codex")]
            return {"status": "PASS", "stage": "final", "final": {"status": "PASS"},
                    "results": evaluate + reviews}

        stdout = io.StringIO()
        with patch.object(cli, "validate_packet_bindings", return_value=list(binding_errors)), \
                patch.object(cli, "materialize_source_packet", fake_materialize), \
                patch.object(cli, "verify_materialized_packet", return_value=materialized_ok), \
                patch.object(cli, "run_provider_stage", fake_provider), \
                patch.object(cli, "run_dual_stages", fake_dual), \
                patch("sys.stdout", stdout):
            observed["code"] = cli.main(self.argv(packet))
        observed["final"] = self.listing(self.output)
        observed["stdout"] = stdout.getvalue()
        return observed

    def test_documented_artifact_block_is_identical_in_both_shared_documents(self):
        evaluate_doc, review_doc = (self.documented(path) for path in self.DOCS)
        self.assertTrue(evaluate_doc)
        self.assertEqual(evaluate_doc, review_doc)

    def test_documented_outputs_match_mocked_run(self):
        documented = self.documented(self.DOCS[0])
        observed = self.run_mocked(self.packet())
        self.assertEqual(0, observed["code"], observed["stdout"])
        self.assertEqual(set(documented), observed["after_evaluate"] | observed["final"])
        deleted_before_review = {path for path, note in documented.items() if "Review 시작 전 삭제" in note}
        self.assertEqual({"evaluate-claude/", "evaluate-codex/"}, deleted_before_review)
        self.assertEqual(deleted_before_review, observed["after_evaluate"] - observed["final"])
        self.assertIn("materialized-packet/", observed["final"])
        self.assertIn("run이 지우지 않", documented["materialized-packet/"])

    def test_evaluate_blocked_run_keeps_evaluate_directories_and_writes_no_review_artifacts(self):
        documented = self.documented(self.DOCS[0])
        review_only = {path for path, note in documented.items() if "Review가 실행됐을 때만" in note}
        self.assertEqual(
            {"review-claude/", "review-codex/", "sealed-results/review-claude.json",
             "sealed-results/review-codex.json"},
            review_only,
        )
        observed = self.run_mocked(self.packet(), review=False)
        self.assertEqual(2, observed["code"])
        self.assertEqual(set(documented) - review_only, observed["final"])
        final = json.loads((self.output / "final-result.json").read_text())
        self.assertEqual("BLOCKED", final["status"])

    def test_early_validation_failure_writes_no_final_result(self):
        documented = self.documented(self.DOCS[0])
        # Both files are written after the four early-return checks, so both rows name the same four.
        for entry in ("final-result.json", "execution-manifest.json"):
            self.assertIn("packet·prompt·model·materialized 검증 실패로 조기 BLOCKED되면 없다", documented[entry], entry)
        # The three checks before mkdir (cli.command_run) leave no output root at all.
        before_mkdir = (
            ("packet", lambda: dict(packet=self.packet(), binding_errors=("SOURCE_SNAPSHOT_MISMATCH",)),
             "SOURCE_SNAPSHOT_MISMATCH"),
            ("prompt", lambda: dict(packet=self.packet(prompt_sha256={"evaluate": "0" * 64, "review": "0" * 64})),
             "PROMPT_DIGEST_MISMATCH"),
            ("model", lambda: dict(packet=self.packet(model_ids={"claude": "other", "codex": "gpt-5.6-sol"})),
             "MODEL_ID_MISMATCH"),
        )
        for name, arguments, error in before_mkdir:
            with self.subTest(check=name):
                observed = self.run_mocked(**arguments())
                self.assertEqual(2, observed["code"])
                self.assertIn(error, observed["stdout"])
                self.assertFalse(self.output.exists())
        # The materialized-packet check runs after mkdir and the copy: only that directory remains.
        with self.subTest(check="materialized"):
            observed = self.run_mocked(self.packet(), materialized_ok=False)
            self.assertEqual(2, observed["code"])
            self.assertIn("MATERIALIZED_PACKET_MISMATCH", observed["stdout"])
            self.assertEqual({"materialized-packet/"}, observed["final"])


if __name__ == "__main__":
    unittest.main()
