import errno
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review import run_provider
from hb_eval_review.redaction import REDACTED
from hb_eval_review.result_validation import (
    canonical_bytes,
    validate_execution_envelope,
    validate_sealed_result,
)
from hb_eval_review.run_provider import run_provider_stage

PACKET = {"packet_id": "p" * 64, "source_snapshot_id": "s" * 64, "evidence_bundle_id": "e" * 64}
# Distinct per-variable literals so a test can prove which injected value leaked.
# None of them match a vendor prefix pattern; only the parent's own inventory can redact them.
AUTH_LITERALS = {
    "CLAUDE_CODE_OAUTH_TOKEN": "fixture-oauth-XYZ12345",
    "ANTHROPIC_API_KEY": "fixture-apikey-QRS67890",
    "ANTHROPIC_AUTH_TOKEN": "fixture-authtok-LMN24680",
}
OAUTH_LITERAL = AUTH_LITERALS["CLAUDE_CODE_OAUTH_TOKEN"]
CODEX_AUTH_LITERAL = "fixture-codex-leaf-98765"


def semantic_payload(stage="evaluate", trailing=""):
    return {
        "schema_version": "2.0", "stage": stage, "status": "PASS",
        "blocking": [], "evidence_refs": ["gate:test"],
        "findings": [{
            "finding_id": "F1", "risk": "LOW", "disposition": "PASS",
            "evidence_ref": "gate:test", "blocking": False,
            "message": "reviewed token=" + trailing,
        }],
    }


def passing_envelope(stage, engine, stdout):
    return {
        "schema_version": "2.0", "stage": stage, "engine": engine, "provider": engine,
        "run_id": "run-1", "started_at": "a", "finished_at": "b",
        "exit_code": 0, "timed_out": False, "fresh_process": True,
        "session_resumed": False, "isolation_mode": "macos-sandbox-exec",
        "source_snapshot_before": PACKET["source_snapshot_id"],
        "source_snapshot_after": PACKET["source_snapshot_id"],
        "packet_id": PACKET["packet_id"], "evidence_bundle_id": PACKET["evidence_bundle_id"],
        "repository_mutated": False,
        "result_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
        "status": "PASS", "error_code": None,
    }


def blocked_envelope(stage, engine, stdout, error_code, timed_out=False):
    envelope = passing_envelope(stage, engine, stdout)
    envelope.update({"status": "BLOCKED", "error_code": error_code, "timed_out": timed_out})
    if timed_out:
        envelope["exit_code"] = None
    return envelope


class ProviderStageTestCase(unittest.TestCase):
    """Runs run_provider_stage with a stubbed child process.

    shutil.rmtree is fenced to the test tree so a defect in the stage cleanup
    cannot delete anything outside it while the test is running.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        self.source = self.base / "source"
        self.source.mkdir()
        (self.source / "a.txt").write_text("a\n")
        self.output = self.base / "out"
        self.refused_removals = []
        real_rmtree = shutil.rmtree

        def fenced(path, *args, **kwargs):
            resolved = Path(str(path)).resolve()
            if resolved == self.base or self.base in resolved.parents:
                return real_rmtree(path, *args, **kwargs)
            self.refused_removals.append(str(resolved))
            return None

        patcher = patch.object(shutil, "rmtree", fenced)
        patcher.start()
        self.addCleanup(patcher.stop)

    def stub_claude(self, raw_stdout, raw_stderr=""):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            return {
                "stdout": raw_stdout, "stderr": raw_stderr,
                "envelope": passing_envelope(stage, engine, raw_stdout),
            }
        return execute

    def stub_codex(self, semantic, raw_stdout="", raw_stderr=""):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            (Path(output_root) / "semantic-result.json").write_text(json.dumps(semantic))
            return {
                "stdout": raw_stdout, "stderr": raw_stderr,
                "envelope": passing_envelope(stage, engine, raw_stdout),
            }
        return execute

    def shared_temp_root(self):
        """A stand-in for /tmp/claude-<uid> holding another session's scratchpad."""
        root = self.base / "shared-claude-temp"
        (root / "parent-session").mkdir(parents=True)
        (root / "parent-session" / "scratch.txt").write_text("do not delete\n")
        return root

    def run_claude(
        self, raw_stdout, raw_stderr="", env=None, temp_root=None, execute=None,
        auth_key="CLAUDE_CODE_OAUTH_TOKEN", auth_value=None,
    ):
        environ = {auth_key: auth_value or AUTH_LITERALS[auth_key]}
        environ.update(env or {})
        stub = execute or self.stub_claude(raw_stdout, raw_stderr)
        stack = [
            patch.dict(os.environ, environ, clear=False),
            patch.object(run_provider, "run_isolated_process", stub),
        ]
        if temp_root is not None:
            stack.append(patch.object(run_provider, "_claude_temp_root", lambda: temp_root))
        for item in stack:
            item.start()
            self.addCleanup(item.stop)
        # patch.dict restores the whole mapping on stop, so removing the sibling auth
        # variables here proves each one alone reaches the inventory.
        for key in AUTH_LITERALS:
            if key != auth_key and key not in (env or {}):
                os.environ.pop(key, None)
        return run_provider_stage(
            "claude", "evaluate", PACKET, self.source, self.output, "prompt"
        )

    def run_codex(self, semantic=None, raw_stdout="", raw_stderr="", execute=None):
        auth = self.base / "auth.json"
        auth.write_text(json.dumps({"tokens": {"access": CODEX_AUTH_LITERAL}}))
        stub = execute or self.stub_codex(semantic, raw_stdout, raw_stderr)
        with patch.dict(
            os.environ, {"HB_CODEX_AUTH_FILE": str(auth)}, clear=False
        ), patch.object(run_provider, "run_isolated_process", stub):
            return run_provider_stage(
                "codex", "evaluate", PACKET, self.source, self.output, "prompt"
            )

    def victim(self, name="victim.json", content='{"auths":{"registry":{"auth":"dXNlcjpwYXNz"}}}'):
        """A user file outside the stage output root that the parent must never touch."""
        path = self.base / name
        path.write_text(content)
        os.chmod(str(path), 0o600)
        return path

    def assert_untouched(self, path, content):
        self.assertTrue(path.is_file())
        self.assertEqual(content, path.read_text())

    def peer_stage(self):
        """Another stage's output root, with its own credential and its own result."""
        peer = self.base / "evaluate-claude"
        (peer / ".provider-home").mkdir(parents=True)
        (peer / ".provider-home" / "auth.json").write_text('{"peer":"credential"}')
        (peer / "semantic-result.json").write_text('{"peer":"result"}')
        return peer

    def disk_contains(self, literal):
        """The first stage file whose bytes still hold the literal, or None."""
        for path in self.output.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                text = path.read_text(errors="ignore")
            except OSError:
                continue
            if literal in text:
                return path
        return None


class SharedTempPreservationTests(ProviderStageTestCase):
    def test_claude_temp_root_derives_from_the_current_uid(self):
        self.assertEqual(
            Path("/tmp/claude-{}".format(os.getuid())), run_provider._claude_temp_root()
        )
        # A hardcoded uid would pass the line above on a uid-501 machine only.
        with patch.object(run_provider.os, "getuid", lambda: 4242):
            self.assertEqual(Path("/tmp/claude-4242"), run_provider._claude_temp_root())

    def test_stage_never_removes_the_shared_claude_temp_root(self):
        root = self.shared_temp_root()
        payload = semantic_payload()
        self.run_claude(json.dumps({"structured_output": payload}), temp_root=root)
        self.assertTrue(root.is_dir())
        self.assertEqual("do not delete\n", (root / "parent-session" / "scratch.txt").read_text())
        self.assertEqual([], self.refused_removals)

    def test_claude_stage_still_removes_its_own_provider_home(self):
        root = self.shared_temp_root()
        payload = semantic_payload()
        self.run_claude(json.dumps({"structured_output": payload}), temp_root=root)
        self.assertFalse((self.output / ".provider-home").exists())

    def test_codex_stage_only_cleans_its_own_provider_home(self):
        payload = semantic_payload()
        self.run_codex(payload)
        self.assertFalse((self.output / ".provider-home").exists())
        self.assertEqual([], self.refused_removals)

    def test_leftover_session_temp_paths_are_reported_not_deleted(self):
        root = self.shared_temp_root()
        payload = semantic_payload()
        leftover = root / "run-session"

        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            leftover.mkdir()
            (leftover / "state").write_text("session state\n")
            raw = json.dumps({"structured_output": payload})
            return {
                "stdout": raw, "stderr": "",
                "envelope": passing_envelope(stage, engine, raw),
            }

        record = self.run_claude("", temp_root=root, execute=execute)
        self.assertTrue(leftover.is_dir())
        self.assertIn(str(leftover), record["diagnostics"]["leftover_temp_paths"])
        self.assertNotIn(
            str(root / "parent-session"), record["diagnostics"]["leftover_temp_paths"]
        )


class ProviderHomeLifecycleTests(ProviderStageTestCase):
    """AC-1b: the ephemeral HOME is gone on success, on failure, and on exception."""

    def claude_failure(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            return {
                "stdout": "", "stderr": "boom",
                "envelope": blocked_envelope(stage, engine, "", "PROCESS_NONZERO"),
            }
        return execute

    def codex_failure(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            (Path(output_root) / "semantic-result.json").write_text("not json at all")
            return {
                "stdout": "", "stderr": "boom",
                "envelope": blocked_envelope(stage, engine, "", "PROCESS_NONZERO"),
            }
        return execute

    def raising(self, error):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            raise error
        return execute

    def test_provider_home_is_removed_on_a_failing_run(self):
        for engine, run in (
            ("claude", lambda: self.run_claude("", execute=self.claude_failure())),
            ("codex", lambda: self.run_codex(execute=self.codex_failure())),
        ):
            with self.subTest(engine=engine):
                self.setUp()
                record = run()
                self.assertEqual("BLOCKED", record["envelope"]["status"])
                self.assertFalse((self.output / ".provider-home").exists())
                self.assertEqual([], self.refused_removals)

    def test_provider_home_is_removed_when_the_child_call_raises(self):
        cases = {
            "claude_oserror": ("claude", OSError("spawn failed")),
            "claude_valueerror": ("claude", ValueError("bad command")),
            "codex_oserror": ("codex", OSError("spawn failed")),
            "codex_valueerror": ("codex", ValueError("bad command")),
        }
        for name, (engine, error) in cases.items():
            with self.subTest(case=name):
                self.setUp()
                shared = self.shared_temp_root()
                with self.assertRaises(type(error)):
                    if engine == "claude":
                        self.run_claude("", temp_root=shared, execute=self.raising(error))
                    else:
                        self.run_codex(execute=self.raising(error))
                self.assertFalse((self.output / ".provider-home").exists())
                self.assertTrue(self.output.is_dir())
                self.assertTrue(shared.is_dir())
                self.assertEqual(
                    "do not delete\n", (shared / "parent-session" / "scratch.txt").read_text()
                )
                self.assertEqual([], self.refused_removals)

    def test_codex_auth_copy_never_survives_an_exception(self):
        with self.assertRaises(OSError):
            self.run_codex(execute=self.raising(OSError("spawn failed")))
        remaining = [
            path for path in self.output.rglob("*")
            if path.is_file() and CODEX_AUTH_LITERAL in path.read_text(errors="ignore")
        ]
        self.assertEqual([], remaining)


class SemanticRedactionTests(ProviderStageTestCase):
    def test_claude_semantic_is_parsed_from_raw_then_redacted(self):
        payload = semantic_payload(trailing="abc123secret")
        raw = json.dumps({"structured_output": payload})
        record = self.run_claude(raw)
        self.assertEqual("PASS", record["envelope"]["status"])
        self.assertEqual("evaluate", record["semantic"]["stage"])
        self.assertNotIn("abc123secret", json.dumps(record["semantic"]))
        self.assertIn("[REDACTED]", record["semantic"]["findings"][0]["message"])

    def test_envelope_hash_matches_the_redacted_semantic(self):
        payload = semantic_payload(trailing="abc123secret")
        record = self.run_claude(json.dumps({"structured_output": payload}))
        self.assertEqual(
            hashlib.sha256(canonical_bytes(record["semantic"])).hexdigest(),
            record["envelope"]["result_sha256"],
        )
        self.assertEqual(
            [], validate_sealed_result(record, "evaluate", "claude", PACKET)
        )

    def test_injected_claude_auth_literal_never_appears(self):
        # AC-3c: each of the three auth variables is injected on its own so a
        # regression that only collects the first key cannot hide behind a sibling.
        for key, literal in AUTH_LITERALS.items():
            with self.subTest(env_key=key):
                self.setUp()
                payload = semantic_payload(trailing=literal)
                raw = json.dumps({"structured_output": payload})
                record = self.run_claude(
                    raw, raw_stderr="auth header " + literal, auth_key=key
                )
                serialized = json.dumps(record, ensure_ascii=False, sort_keys=True)
                self.assertNotIn(literal, serialized)
                self.assertNotIn(literal, record["diagnostics"]["stderr_tail"])
                self.assertNotIn(literal, record["diagnostics"]["stdout_tail"])
                self.assertIn("[REDACTED]", record["semantic"]["findings"][0]["message"])

    def test_codex_result_file_on_disk_is_rewritten_redacted(self):
        payload = semantic_payload(trailing=CODEX_AUTH_LITERAL)
        record = self.run_codex(payload, raw_stdout="wrote result " + CODEX_AUTH_LITERAL)
        result_path = self.output / "semantic-result.json"
        on_disk = result_path.read_text()
        self.assertNotIn(CODEX_AUTH_LITERAL, on_disk)
        self.assertNotIn(CODEX_AUTH_LITERAL, json.dumps(record, ensure_ascii=False))
        self.assertEqual(
            hashlib.sha256(canonical_bytes(record["semantic"])).hexdigest(),
            record["envelope"]["result_sha256"],
        )
        self.assertEqual(json.loads(on_disk), record["semantic"])
        self.assertEqual(0o600, stat.S_IMODE(os.stat(str(result_path)).st_mode))

    def test_claude_semantic_survives_a_secret_at_the_end_of_a_json_string(self):
        payload = semantic_payload(trailing="abc123secret")
        raw = json.dumps({"result": json.dumps(payload)})
        record = self.run_claude(raw)
        self.assertEqual("PASS", record["envelope"]["status"])
        self.assertNotEqual("RESULT_MALFORMED", record["envelope"]["error_code"])


class CodexResultPathSafetyTests(ProviderStageTestCase):
    """The result path belongs to an untrusted child; only a plain regular file is read."""

    def plant(self, maker):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            maker(Path(output_root) / "semantic-result.json")
            return {
                "stdout": "", "stderr": "",
                "envelope": passing_envelope(stage, engine, ""),
            }
        return execute

    def test_symlinked_result_file_is_refused_and_the_victim_is_untouched(self):
        content = '{"auths":{"registry":{"auth":"dXNlcjpzdXBlci1zZWNyZXQ="}}}'
        victim = self.victim(content=content)
        record = self.run_codex(
            execute=self.plant(lambda path: os.symlink(str(victim), str(path)))
        )
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("RESULT_PATH_UNSAFE", record["envelope"]["error_code"])
        self.assertEqual({}, record["semantic"])
        self.assert_untouched(victim, content)
        self.assertNotIn("dXNlcjpzdXBlci1zZWNyZXQ=", json.dumps(record, ensure_ascii=False))
        self.assertEqual(0o600, stat.S_IMODE(os.stat(str(victim)).st_mode))

    def test_relative_symlinked_result_file_is_refused(self):
        content = '{"kept":"original"}'
        victim = self.victim(name="peer-result.json", content=content)
        record = self.run_codex(
            execute=self.plant(lambda path: os.symlink("../peer-result.json", str(path)))
        )
        self.assertEqual("RESULT_PATH_UNSAFE", record["envelope"]["error_code"])
        self.assert_untouched(victim, content)

    def test_fifo_result_file_is_refused_without_blocking(self):
        record = self.run_codex(execute=self.plant(lambda path: os.mkfifo(str(path))))
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("RESULT_PATH_UNSAFE", record["envelope"]["error_code"])
        self.assertFalse((self.output / "semantic-result.json").exists())

    def test_directory_at_the_result_path_is_refused(self):
        record = self.run_codex(execute=self.plant(lambda path: path.mkdir()))
        self.assertEqual("RESULT_PATH_UNSAFE", record["envelope"]["error_code"])

    def test_hardlinked_result_file_is_refused_and_the_victim_is_untouched(self):
        content = '{"kept":"original"}'
        victim = self.victim(name="hardlink-victim.json", content=content)
        record = self.run_codex(
            execute=self.plant(lambda path: os.link(str(victim), str(path)))
        )
        self.assertEqual("RESULT_PATH_UNSAFE", record["envelope"]["error_code"])
        self.assert_untouched(victim, content)

    def test_oversized_result_file_is_refused_even_when_it_parses(self):
        # Valid JSON, so only the size ceiling can stop it.
        limit = run_provider._MAX_RESULT_BYTES
        payload = semantic_payload()
        payload["summary"] = "a" * (limit + 1024)

        def maker(path):
            path.write_text(json.dumps(payload))

        record = self.run_codex(execute=self.plant(maker))
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("RESULT_MALFORMED", record["envelope"]["error_code"])
        self.assertEqual({}, record["semantic"])


class ProviderOutputHygieneTests(ProviderStageTestCase):
    """REQ-M05: no injected credential survives on disk on any exit path."""

    def codex_leaving(self, payload_text, envelope_maker):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            (Path(output_root) / "semantic-result.json").write_text(payload_text)
            return {
                "stdout": "", "stderr": "",
                "envelope": envelope_maker(stage, engine),
            }
        return execute

    def test_raw_result_never_survives_a_non_pass_run(self):
        raw = json.dumps({"note": "leaked " + CODEX_AUTH_LITERAL})
        cases = {
            "nonzero": lambda stage, engine: blocked_envelope(stage, engine, "", "PROCESS_NONZERO"),
            "timeout": lambda stage, engine: blocked_envelope(
                stage, engine, "", "PROCESS_TIMEOUT", timed_out=True
            ),
            "mutation": lambda stage, engine: blocked_envelope(
                stage, engine, "", "REPOSITORY_MUTATION"
            ),
        }
        for name, maker in cases.items():
            with self.subTest(case=name):
                self.setUp()
                record = self.run_codex(execute=self.codex_leaving(raw, maker))
                self.assertEqual("BLOCKED", record["envelope"]["status"])
                self.assertFalse((self.output / "semantic-result.json").exists())
                self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))
                self.assertNotIn(
                    CODEX_AUTH_LITERAL, json.dumps(record, ensure_ascii=False)
                )

    def test_unsealed_raw_result_is_dropped_even_with_no_secret_to_scan_for(self):
        # Independent of the credential scan: an unsealed provider result is not kept.
        raw = json.dumps({"note": "nothing injected here"})
        record = self.run_codex(
            execute=self.codex_leaving(
                raw, lambda stage, engine: blocked_envelope(stage, engine, "", "PROCESS_NONZERO")
            )
        )
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertFalse((self.output / "semantic-result.json").exists())
        self.assertEqual([], record["diagnostics"]["purged_secret_files"])

    def test_raw_result_never_survives_a_malformed_pass_run(self):
        raw = "not json at all " + CODEX_AUTH_LITERAL
        record = self.run_codex(
            execute=self.codex_leaving(raw, lambda stage, engine: passing_envelope(stage, engine, ""))
        )
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("RESULT_MALFORMED", record["envelope"]["error_code"])
        self.assertFalse((self.output / "semantic-result.json").exists())
        self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))

    def test_extra_provider_files_holding_an_injected_secret_are_purged(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            (root / "notes.txt").write_text("copied auth " + CODEX_AUTH_LITERAL + "\n")
            (root / "nested").mkdir()
            (root / "nested" / "copy.json").write_text(
                json.dumps({"tokens": {"access": CODEX_AUTH_LITERAL}})
            )
            (root / "harmless.txt").write_text("nothing sensitive\n")
            return {
                "stdout": "", "stderr": "",
                "envelope": passing_envelope(stage, engine, ""),
            }

        record = self.run_codex(execute=execute)
        self.assertEqual("PASS", record["envelope"]["status"])
        self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))
        self.assertTrue((self.output / "harmless.txt").is_file())
        purged = record["diagnostics"]["purged_secret_files"]
        self.assertIn("notes.txt", purged)
        self.assertIn("nested/copy.json", purged)
        self.assertNotIn(CODEX_AUTH_LITERAL, json.dumps(record, ensure_ascii=False))

    def test_claude_stage_purges_files_holding_the_injected_token(self):
        payload = semantic_payload()
        raw = json.dumps({"structured_output": payload})

        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            (Path(output_root) / "session.log").write_text("token " + OAUTH_LITERAL + "\n")
            return {"stdout": raw, "stderr": "", "envelope": passing_envelope(stage, engine, raw)}

        record = self.run_claude(raw, execute=execute)
        self.assertIsNone(self.disk_contains(OAUTH_LITERAL))
        self.assertIn("session.log", record["diagnostics"]["purged_secret_files"])

    def test_purge_never_follows_a_symlink_out_of_the_stage_root(self):
        content = "external file holding " + CODEX_AUTH_LITERAL + "\n"
        victim = self.victim(name="outside.txt", content=content)

        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            os.symlink(str(victim), str(root / "linked.txt"))
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        self.assert_untouched(victim, content)
        self.assertEqual([], self.refused_removals)
        self.assertNotIn("linked.txt", record["diagnostics"]["purged_secret_files"])


class DiagnosticsPathRedactionTests(ProviderStageTestCase):
    """REQ-M05: a credential encoded in a *name* must not be sealed by diagnostics."""

    def test_a_purged_path_naming_the_codex_credential_is_redacted(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            (root / (CODEX_AUTH_LITERAL + ".txt")).write_text("holds " + CODEX_AUTH_LITERAL + "\n")
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        purged = record["diagnostics"]["purged_secret_files"]
        self.assertEqual(1, len(purged))
        self.assertIn(REDACTED, purged[0])
        self.assertNotIn(CODEX_AUTH_LITERAL, json.dumps(record, ensure_ascii=False))

    def test_a_purged_directory_component_naming_the_credential_is_redacted(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            nested = root / ("dir-" + CODEX_AUTH_LITERAL)
            nested.mkdir()
            (nested / "copy.json").write_text(json.dumps({"access": CODEX_AUTH_LITERAL}))
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        self.assertNotIn(CODEX_AUTH_LITERAL, json.dumps(record, ensure_ascii=False))

    def test_a_noted_path_naming_the_credential_is_redacted(self):
        # Not every stage entry can be purged; the ones only reported must be redacted too.
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            holder = root / ("dir-" + CODEX_AUTH_LITERAL)
            holder.mkdir()
            os.mkfifo(str(holder / "pipe.sock"))
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        notes = record["diagnostics"]["purge_notes"]
        self.assertEqual(1, len(notes))
        self.assertTrue(all(REDACTED in key for key in notes))
        self.assertNotIn(CODEX_AUTH_LITERAL, json.dumps(record, ensure_ascii=False))

    def test_an_unscanned_path_naming_the_credential_is_redacted(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            holder = root / ("dir-" + CODEX_AUTH_LITERAL)
            holder.mkdir()
            locked = holder / "locked.bin"
            locked.write_text("opaque\n")
            os.chmod(str(locked), 0o000)
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        unscanned = record["diagnostics"]["unscanned_paths"]
        self.assertEqual(1, len(unscanned))
        self.assertIn(REDACTED, unscanned[0])
        self.assertNotIn(CODEX_AUTH_LITERAL, json.dumps(record, ensure_ascii=False))

    def test_a_leftover_temp_path_naming_the_oauth_token_is_redacted(self):
        root = self.shared_temp_root()
        raw = json.dumps({"structured_output": semantic_payload()})

        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            (root / ("session-" + OAUTH_LITERAL)).mkdir()
            return {"stdout": raw, "stderr": "", "envelope": passing_envelope(stage, engine, raw)}

        record = self.run_claude(raw, temp_root=root, execute=execute)
        leftover = record["diagnostics"]["leftover_temp_paths"]
        self.assertEqual(1, len(leftover))
        self.assertIn(REDACTED, leftover[0])
        self.assertNotIn(OAUTH_LITERAL, json.dumps(record, ensure_ascii=False))

    def test_a_leftover_temp_path_with_a_vendor_shaped_name_is_redacted(self):
        # Vendor-shaped names are redacted by pattern, not by the injected inventory.
        vendor = "sk-ant-ABCD1234EFGH5678"
        root = self.shared_temp_root()
        raw = json.dumps({"structured_output": semantic_payload()})

        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            (root / vendor).mkdir()
            return {"stdout": raw, "stderr": "", "envelope": passing_envelope(stage, engine, raw)}

        record = self.run_claude(raw, temp_root=root, execute=execute)
        self.assertNotIn(vendor, json.dumps(record, ensure_ascii=False))


class ProviderHomeRemovalHardeningTests(ProviderStageTestCase):
    """AC-1b: a child cannot pin its own HOME in place and keep the auth copy on disk."""

    def stripped_home(self, extra=None):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            (root / "stray.txt").write_text("copied auth " + CODEX_AUTH_LITERAL + "\n")
            home = root / ".provider-home"
            (home / "deep").mkdir()
            (home / "deep" / "pinned.txt").write_text("pinned\n")
            if extra is not None:
                extra(home)
            os.chmod(str(home / "deep"), 0o000)
            os.chmod(str(home), 0o000)
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}
        return execute

    def test_a_mode_stripped_provider_home_is_still_removed(self):
        record = self.run_codex(execute=self.stripped_home())
        self.assertFalse((self.output / ".provider-home").exists())
        self.assertEqual("PASS", record["envelope"]["status"])

    def test_cleanup_after_a_mode_stripped_home_still_purges_the_stage(self):
        self.run_codex(execute=self.stripped_home())
        self.assertFalse((self.output / "stray.txt").exists())
        self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))

    def test_home_cleanup_never_restores_bits_through_a_symlink(self):
        outside = self.base / "outside-dir"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep\n")
        os.chmod(str(outside), 0o500)

        def extra(home):
            os.symlink(str(outside), str(home / "escape"))

        self.run_codex(execute=self.stripped_home(extra))
        self.assertEqual(0o500, stat.S_IMODE(os.lstat(str(outside)).st_mode))
        self.assert_untouched(outside / "keep.txt", "keep\n")
        self.assertEqual([], self.refused_removals)

    def test_home_cleanup_never_follows_a_component_swapped_mid_walk(self):
        outside = self.base / "outside-dir"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep\n")
        os.chmod(str(outside), 0o500)
        real_lstat = os.lstat
        swapped = []

        def lstat_then_swap(path, *args, **kwargs):
            info = real_lstat(path, *args, **kwargs)
            if not swapped and path == "swap" and kwargs.get("dir_fd") is not None:
                swapped.append(True)
                home = self.output / ".provider-home"
                os.rename(str(home / "swap"), str(self.base / "swap-detached"))
                os.symlink(str(outside), str(home / "swap"))
            return info

        def extra(home):
            (home / "swap").mkdir()
            (home / "swap" / "inner.txt").write_text("inner\n")

        with patch.object(run_provider.os, "lstat", lstat_then_swap):
            self.run_codex(execute=self.stripped_home(extra))

        self.assertTrue(swapped)
        self.assertEqual(0o500, stat.S_IMODE(os.lstat(str(outside)).st_mode))
        self.assert_untouched(outside / "keep.txt", "keep\n")
        self.assertEqual([], self.refused_removals)

    def test_a_provider_home_that_survives_removal_blocks_the_stage(self):
        with patch.object(run_provider, "_remove_home_tree", lambda *a, **k: None):
            record = self.run_codex(semantic_payload())
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("PROVIDER_HOME_NOT_REMOVED", record["envelope"]["error_code"])
        self.assertIn(
            "PROVIDER_HOME_NOT_REMOVED", record["diagnostics"]["cleanup_errors"]
        )


class PurgeDirectoryIdentityTests(ProviderStageTestCase):
    """REQ-M01: the purge resolves names through held directory descriptors only."""

    def swapping_unlink(self, basename, replacement):
        """Replace the stage subdirectory the moment the parent unlinks that name."""
        real_unlink = os.unlink
        state = []

        def unlink(path, *args, **kwargs):
            if not state and os.path.basename(str(path)) == basename:
                state.append(True)
                decoy = self.output / "decoy"
                os.rename(str(decoy), str(self.base / "decoy-detached"))
                os.symlink(str(replacement), str(decoy))
            return real_unlink(path, *args, **kwargs)

        return unlink

    def decoy_stage(self, name):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            (root / "decoy").mkdir()
            (root / "decoy" / name).write_text("stage copy " + CODEX_AUTH_LITERAL + "\n")
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}
        return execute

    def test_a_directory_swapped_before_unlink_cannot_redirect_the_delete(self):
        outside = self.base / "outside"
        outside.mkdir()
        content = "victim holding " + CODEX_AUTH_LITERAL + "\n"
        victim = outside / "leak.json"
        victim.write_text(content)

        with patch.object(run_provider.os, "unlink", self.swapping_unlink("leak.json", outside)):
            record = self.run_codex(execute=self.decoy_stage("leak.json"))

        self.assert_untouched(victim, content)
        self.assertFalse((self.base / "decoy-detached" / "leak.json").exists())
        self.assertEqual(1, len(record["diagnostics"]["purged_secret_files"]))

    def lstat_then_replace(self, target_name, replacement):
        """Swap a stage directory the instant the parent has classified it as one."""
        real_lstat = os.lstat
        state = []

        def lstat(path, *args, **kwargs):
            info = real_lstat(path, *args, **kwargs)
            if not state and path == target_name and kwargs.get("dir_fd") is not None:
                state.append(True)
                replacement()
            return info

        return lstat, state

    def outside_holder(self, name):
        """A needle-bearing directory outside the stage root that must survive."""
        holder = self.base / name
        holder.mkdir()
        (holder / "held.json").write_text("outside " + CODEX_AUTH_LITERAL + "\n")
        return holder

    def test_a_directory_swapped_for_a_link_after_classification_is_not_descended(self):
        holder = self.outside_holder("linked-holder")

        def replace():
            decoy = self.output / "decoy"
            os.rename(str(decoy), str(self.base / "decoy-detached"))
            os.symlink(str(holder), str(decoy))

        lstat, state = self.lstat_then_replace("decoy", replace)
        with patch.object(run_provider.os, "lstat", lstat):
            record = self.run_codex(execute=self.decoy_stage("leak.json"))

        self.assertTrue(state)
        self.assert_untouched(holder / "held.json", "outside " + CODEX_AUTH_LITERAL + "\n")
        self.assertIn("decoy", record["diagnostics"]["unscanned_paths"])
        self.assertEqual("BLOCKED", record["envelope"]["status"])

    def test_a_directory_swapped_for_another_directory_is_refused_by_identity(self):
        holder = self.outside_holder("moved-holder")

        def replace():
            decoy = self.output / "decoy"
            os.rename(str(decoy), str(self.base / "decoy-detached"))
            os.rename(str(holder), str(decoy))

        lstat, state = self.lstat_then_replace("decoy", replace)
        with patch.object(run_provider.os, "lstat", lstat):
            record = self.run_codex(execute=self.decoy_stage("leak.json"))

        self.assertTrue(state)
        self.assert_untouched(
            self.output / "decoy" / "held.json", "outside " + CODEX_AUTH_LITERAL + "\n"
        )
        self.assertIn("decoy", record["diagnostics"]["unscanned_paths"])
        self.assertEqual("BLOCKED", record["envelope"]["status"])

    def test_a_file_swapped_for_a_link_after_classification_is_not_read(self):
        content = "external file holding " + CODEX_AUTH_LITERAL + "\n"
        victim = self.victim(name="outside.txt", content=content)

        def replace():
            plain = self.output / "plain.txt"
            os.unlink(str(plain))
            os.symlink(str(victim), str(plain))

        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            (root / "plain.txt").write_text("nothing sensitive\n")
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        lstat, state = self.lstat_then_replace("plain.txt", replace)
        with patch.object(run_provider.os, "lstat", lstat):
            record = self.run_codex(execute=execute)

        self.assertTrue(state)
        self.assert_untouched(victim, content)
        self.assertEqual([], record["diagnostics"]["purged_secret_files"])
        self.assertIn("plain.txt", record["diagnostics"]["unscanned_paths"])
        self.assertEqual("BLOCKED", record["envelope"]["status"])

    def test_a_stage_file_is_never_scanned_through_a_link(self):
        content = "external file holding " + CODEX_AUTH_LITERAL + "\n"
        victim = self.victim(name="outside.txt", content=content)

        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            os.symlink(str(victim), str(root / "linked.txt"))
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        # The link text holds no needle, so the link stays and its target is never read.
        self.assert_untouched(victim, content)
        self.assertTrue((self.output / "linked.txt").is_symlink())
        self.assertEqual([], record["diagnostics"]["purged_secret_files"])
        self.assertEqual("PASS", record["envelope"]["status"])

    def test_a_symlink_whose_link_text_holds_the_credential_is_unlinked(self):
        content = "external " + CODEX_AUTH_LITERAL + "\n"
        victim = self.victim(name="pointed-at.txt", content=content)
        target = self.base / (CODEX_AUTH_LITERAL + "-dir") / "x"

        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            os.symlink(str(target), str(root / "named.lnk"))
            os.symlink(str(victim), str(root / "plain.lnk"))
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        self.assertFalse((self.output / "named.lnk").is_symlink())
        self.assertTrue((self.output / "plain.lnk").is_symlink())
        self.assert_untouched(victim, content)
        self.assertNotIn(CODEX_AUTH_LITERAL, json.dumps(record, ensure_ascii=False))


class PurgeBoundsTests(ProviderStageTestCase):
    """fail-closed: what the purge cannot read, it reports and blocks on."""

    def stage_with(self, maker):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            maker(root)
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}
        return execute

    def test_a_file_beyond_the_scan_bound_blocks_instead_of_being_read_whole(self):
        def maker(root):
            with open(str(root / "huge.bin"), "wb") as handle:
                handle.truncate(4096)

        with patch.object(run_provider, "_MAX_SCAN_BYTES", 1024):
            record = self.run_codex(execute=self.stage_with(maker))
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("PURGE_INCOMPLETE", record["envelope"]["error_code"])
        self.assertIn("huge.bin", record["diagnostics"]["unscanned_paths"])

    def test_a_file_that_grows_while_it_is_scanned_blocks_on_the_stream_bound(self):
        # A descendant appending during the scan defeats the size taken up front, so
        # the streaming bound is what actually keeps the read finite.
        real_read = os.read
        grown = []

        def maker(root):
            (root / "growing.bin").write_bytes(b"a" * 100)

        def read_then_grow(handle, size):
            chunk = real_read(handle, size)
            # Only the growing file's own bytes trigger the append, so the sealing read
            # of semantic-result.json cannot stand in for the scan.
            if chunk[:1] == b"a" and not grown:
                grown.append(True)
                with open(str(self.output / "growing.bin"), "ab") as target:
                    target.write(b"b" * 400)
            return chunk

        with patch.object(run_provider, "_MAX_SCAN_BYTES", 200), \
                patch.object(run_provider, "_READ_CHUNK", 64), \
                patch.object(run_provider.os, "read", read_then_grow):
            record = self.run_codex(execute=self.stage_with(maker))

        self.assertTrue(grown)
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("PURGE_INCOMPLETE", record["envelope"]["error_code"])
        self.assertIn("growing.bin", record["diagnostics"]["unscanned_paths"])

    def test_the_scan_bound_is_a_documented_finite_constant(self):
        self.assertIsInstance(run_provider._MAX_SCAN_BYTES, int)
        self.assertGreaterEqual(run_provider._MAX_SCAN_BYTES, run_provider._MAX_RESULT_BYTES)

    def test_an_unreadable_stage_file_blocks_instead_of_being_skipped(self):
        def maker(root):
            path = root / "locked.bin"
            path.write_text("opaque\n")
            os.chmod(str(path), 0o000)

        record = self.run_codex(execute=self.stage_with(maker))
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("PURGE_INCOMPLETE", record["envelope"]["error_code"])
        self.assertIn("locked.bin", record["diagnostics"]["unscanned_paths"])

    def test_a_credential_straddling_two_read_chunks_is_still_purged(self):
        filler = "f" * (run_provider._READ_CHUNK - 3)

        def maker(root):
            (root / "straddle.txt").write_text(filler + CODEX_AUTH_LITERAL + "\n")

        record = self.run_codex(execute=self.stage_with(maker))
        self.assertFalse((self.output / "straddle.txt").exists())
        self.assertEqual("PASS", record["envelope"]["status"])

    def test_a_file_that_disappears_mid_purge_is_reported_not_fatal(self):
        vanish = []

        def maker(root):
            (root / "a-first.txt").write_text("holds " + CODEX_AUTH_LITERAL + "\n")
            (root / "z-last.txt").write_text("holds " + CODEX_AUTH_LITERAL + "\n")
            vanish.append(root / "z-last.txt")

        real_unlink = os.unlink
        state = []

        def unlink(path, *args, **kwargs):
            result = real_unlink(path, *args, **kwargs)
            if not state and os.path.basename(str(path)) == "a-first.txt":
                state.append(True)
                real_unlink(str(vanish[0]))
            return result

        with patch.object(run_provider.os, "unlink", unlink):
            record = self.run_codex(execute=self.stage_with(maker))
        self.assertEqual(["a-first.txt"], record["diagnostics"]["purged_secret_files"])
        self.assertIn("z-last.txt", record["diagnostics"]["purge_notes"])


class ClaudeOuterDocumentTests(ProviderStageTestCase):
    """An untrusted outer document that is not an object is BLOCKED, never a traceback."""

    def test_a_non_object_outer_document_is_blocked(self):
        for raw in ("[]", "1", "true", "null", '"text"'):
            with self.subTest(raw=raw):
                self.setUp()
                record = self.run_claude(raw)
                self.assertEqual("BLOCKED", record["envelope"]["status"])
                self.assertEqual("RESULT_MALFORMED", record["envelope"]["error_code"])
                self.assertEqual({}, record["semantic"])


class OutputRootTamperTests(ProviderStageTestCase):
    """The stage root is parent-owned; a child that swaps it stops the stage."""

    def swap_for(self, peer):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            shutil.rmtree(str(root))
            os.symlink(str(peer), str(root))
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}
        return execute

    def test_stage_root_replaced_by_a_symlink_is_blocked(self):
        peer = self.peer_stage()
        record = self.run_codex(execute=self.swap_for(peer))
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("OUTPUT_ROOT_TAMPERED", record["envelope"]["error_code"])
        self.assertEqual({}, record["semantic"])

    def test_cleanup_never_reaches_through_a_replaced_stage_root(self):
        peer = self.peer_stage()
        self.run_codex(execute=self.swap_for(peer))
        self.assertTrue((peer / ".provider-home").is_dir())
        self.assertEqual('{"peer":"credential"}', (peer / ".provider-home" / "auth.json").read_text())
        self.assertEqual('{"peer":"result"}', (peer / "semantic-result.json").read_text())
        self.assertEqual([], self.refused_removals)

    def test_deleted_stage_root_is_blocked(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            shutil.rmtree(str(output_root))
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        self.assertEqual("OUTPUT_ROOT_TAMPERED", record["envelope"]["error_code"])

    def test_recreated_stage_root_is_blocked(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            shutil.rmtree(str(root))
            root.mkdir()
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        self.assertEqual("OUTPUT_ROOT_TAMPERED", record["envelope"]["error_code"])


class OutputRootTamperedAfterTheFirstCheckTests(ProviderStageTestCase):
    """H-M1: a descendant that escaped the process group swaps the root *later*.

    `run_isolated_process` returns when the parent's own child is reaped, but a
    descendant that called setsid outlives that wait — process.DESCENDANT_CONTAINMENT
    says so in as many words. Its swap can therefore land after the integrity check
    that guards the result parsing has already passed, leaving the second check, the
    one in the cleanup block, as the only one that sees it. Both checks are the same
    verdict: the stage is BLOCKED/OUTPUT_ROOT_TAMPERED and nothing is cleaned up
    through a name the parent no longer owns.
    """

    def escaped_child(self, action):
        """Let `action` run in the window between the two integrity checks.

        The stand-in for the escaped descendant is a wrapper around the redaction the
        parent performs after the first check: whatever happens there is by definition
        invisible to the check that has already run.
        """
        real = run_provider.redact_json

        def hook(value, known_secrets=()):
            result = real(value, known_secrets)
            action()
            return result

        patcher = patch.object(run_provider, "redact_json", hook)
        patcher.start()
        self.addCleanup(patcher.stop)

    def recreate_root(self):
        """A fresh directory under the same name: same path, different identity."""
        def action():
            shutil.rmtree(str(self.output))
            self.output.mkdir()
            (self.output / "stray.txt").write_text("leftover " + OAUTH_LITERAL + "\n")
        return action

    def relink_root_to(self, peer):
        def action():
            shutil.rmtree(str(self.output))
            os.symlink(str(peer), str(self.output))
        return action

    def test_a_root_recreated_after_the_first_check_still_blocks_the_stage(self):
        self.escaped_child(self.recreate_root())
        record = self.run_claude(json.dumps({"structured_output": semantic_payload()}))
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("OUTPUT_ROOT_TAMPERED", record["envelope"]["error_code"])
        self.assertEqual({}, record["semantic"])
        self.assertTrue(record["diagnostics"]["output_root_tampered"])
        # The verdict stands on the swapped root alone, not on a cleanup step that was
        # deliberately not run: reporting a cleanup error here would be inventing one.
        self.assertEqual([], record["diagnostics"]["cleanup_errors"])

    def test_a_codex_root_recreated_after_the_first_check_still_blocks_the_stage(self):
        self.escaped_child(self.recreate_root())
        record = self.run_codex(semantic_payload())
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("OUTPUT_ROOT_TAMPERED", record["envelope"]["error_code"])
        self.assertEqual({}, record["semantic"])

    def test_a_late_swap_blocks_the_stage_without_reaching_the_peer(self):
        peer = self.peer_stage()
        victim = self.victim()
        self.escaped_child(self.relink_root_to(peer))
        record = self.run_claude(json.dumps({"structured_output": semantic_payload()}))
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("OUTPUT_ROOT_TAMPERED", record["envelope"]["error_code"])
        self.assertTrue((peer / ".provider-home").is_dir())
        self.assertEqual(
            '{"peer":"credential"}', (peer / ".provider-home" / "auth.json").read_text()
        )
        self.assertEqual('{"peer":"result"}', (peer / "semantic-result.json").read_text())
        self.assert_untouched(victim, '{"auths":{"registry":{"auth":"dXNlcjpwYXNz"}}}')
        self.assertEqual([], self.refused_removals)


class PurgeNameComponentTests(ProviderStageTestCase):
    """REQ-M05: a credential encoded in a file or directory *name* is on disk too.

    The value redaction keeps the literal out of the sealed record, so a child that
    cannot get it past that can still write it as a name. These cases are Codex R3-07
    (`review-r4-repro/r3_e`) turned into fixtures.
    """

    def stage_writing(self, maker):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            maker(root)
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}
        return execute

    def named_on_disk(self, literal):
        """The first stage entry whose own name still carries the literal, or None."""
        for path in self.output.rglob("*"):
            if literal in path.name:
                return path
        return None

    def test_an_empty_file_named_after_the_credential_is_purged(self):
        def maker(root):
            (root / (CODEX_AUTH_LITERAL + ".txt")).write_text("")

        record = self.run_codex(execute=self.stage_writing(maker))
        self.assertIsNone(self.named_on_disk(CODEX_AUTH_LITERAL))
        self.assertEqual("PASS", record["envelope"]["status"])

    def test_a_clean_file_named_after_the_credential_is_purged(self):
        def maker(root):
            (root / (CODEX_AUTH_LITERAL + ".log")).write_text("nothing sensitive here\n")

        record = self.run_codex(execute=self.stage_writing(maker))
        self.assertIsNone(self.named_on_disk(CODEX_AUTH_LITERAL))
        self.assertEqual("PASS", record["envelope"]["status"])

    def test_a_claude_stage_file_named_after_the_oauth_token_is_purged(self):
        stdout = json.dumps({"structured_output": semantic_payload()})

        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            (Path(output_root) / (OAUTH_LITERAL + ".txt")).write_text("")
            return {"stdout": stdout, "stderr": "", "envelope": passing_envelope(stage, engine, stdout)}

        record = self.run_claude(stdout, execute=execute)
        self.assertIsNone(self.named_on_disk(OAUTH_LITERAL))
        self.assertEqual("PASS", record["envelope"]["status"])

    def test_an_emptied_directory_named_after_the_credential_is_removed(self):
        def maker(root):
            nested = root / ("dir-" + CODEX_AUTH_LITERAL)
            nested.mkdir()
            (nested / "x.txt").write_text("holds " + CODEX_AUTH_LITERAL + "\n")

        record = self.run_codex(execute=self.stage_writing(maker))
        self.assertIsNone(self.named_on_disk(CODEX_AUTH_LITERAL))
        self.assertFalse((self.output / ("dir-" + CODEX_AUTH_LITERAL)).exists())
        self.assertEqual("PASS", record["envelope"]["status"])

    def test_a_directory_named_after_the_credential_keeps_its_clean_contents(self):
        def maker(root):
            nested = root / ("dir-" + CODEX_AUTH_LITERAL)
            nested.mkdir()
            (nested / "x.txt").write_text("nothing sensitive\n")

        record = self.run_codex(execute=self.stage_writing(maker))
        self.assertIsNone(self.named_on_disk(CODEX_AUTH_LITERAL))
        survivors = [
            path for path in self.output.rglob("x.txt") if path.read_text() == "nothing sensitive\n"
        ]
        self.assertEqual(1, len(survivors))
        self.assertEqual("PASS", record["envelope"]["status"])
        self.assertEqual(
            ["dir-" + REDACTED], record["diagnostics"]["renamed_secret_paths"]
        )

    def test_a_symlink_named_after_the_credential_is_unlinked_without_its_target(self):
        content = "external " + CODEX_AUTH_LITERAL + "\n"
        victim = self.victim(name="pointed-at.txt", content=content)

        def maker(root):
            os.symlink(str(victim), str(root / (CODEX_AUTH_LITERAL + ".lnk")))

        record = self.run_codex(execute=self.stage_writing(maker))
        self.assertIsNone(self.named_on_disk(CODEX_AUTH_LITERAL))
        self.assert_untouched(victim, content)
        self.assertEqual("PASS", record["envelope"]["status"])

    def test_a_fifo_named_after_the_credential_is_unlinked(self):
        def maker(root):
            os.mkfifo(str(root / (CODEX_AUTH_LITERAL + ".fifo")))

        record = self.run_codex(execute=self.stage_writing(maker))
        self.assertIsNone(self.named_on_disk(CODEX_AUTH_LITERAL))
        self.assertEqual("PASS", record["envelope"]["status"])

    def test_a_named_directory_that_cannot_be_cleared_blocks_the_stage(self):
        def maker(root):
            nested = root / ("dir-" + CODEX_AUTH_LITERAL)
            nested.mkdir()
            (nested / "x.txt").write_text("nothing sensitive\n")

        # Neither removal nor the in-place rename can take the literal off disk, so the
        # stage says so instead of reporting a clean run.
        def refuse(*args, **kwargs):
            raise OSError(errno.EPERM, "refused")

        with patch.object(run_provider.os, "rename", refuse):
            record = self.run_codex(execute=self.stage_writing(maker))
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("PURGE_INCOMPLETE", record["envelope"]["error_code"])
        self.assertIn("dir-" + REDACTED, record["diagnostics"]["unscanned_paths"])

    def test_the_credential_never_reaches_the_sealed_record_through_a_name(self):
        def maker(root):
            (root / (CODEX_AUTH_LITERAL + ".txt")).write_text("")
            nested = root / ("dir-" + CODEX_AUTH_LITERAL)
            nested.mkdir()
            (nested / "keep.txt").write_text("keep\n")

        record = self.run_codex(execute=self.stage_writing(maker))
        self.assertNotIn(CODEX_AUTH_LITERAL, json.dumps(record, ensure_ascii=False))

    def test_a_name_purge_never_reaches_outside_the_stage_root(self):
        outside = self.base / ("outside-" + CODEX_AUTH_LITERAL)
        outside.mkdir()
        kept = outside / "keep.txt"
        kept.write_text("keep\n")

        def maker(root):
            os.symlink(str(outside), str(root / (CODEX_AUTH_LITERAL + ".link")))

        self.run_codex(execute=self.stage_writing(maker))
        self.assertTrue(outside.is_dir())
        self.assert_untouched(kept, "keep\n")
        self.assertEqual([], self.refused_removals)


class PurgeNoFollowBarrierTests(ProviderStageTestCase):
    """REQ-M01/EV-1: `O_NOFOLLOW` is the barrier, not the inode identity check.

    A directory that is *moved* out of the stage root keeps its inode, so a link left
    at the old name resolves to exactly the inode the identity check expects. Only the
    refusal to open a link at all stops the walk from leaving the stage root.
    """

    def decoy_stage(self, name):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            (root / "decoy").mkdir()
            (root / "decoy" / name).write_text("stage copy " + CODEX_AUTH_LITERAL + "\n")
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}
        return execute

    def lstat_then_replace(self, target_name, replacement):
        real_lstat = os.lstat
        state = []

        def lstat(path, *args, **kwargs):
            info = real_lstat(path, *args, **kwargs)
            if not state and path == target_name and kwargs.get("dir_fd") is not None:
                state.append(True)
                replacement()
            return info

        return lstat, state

    def test_a_directory_moved_outside_and_relinked_to_its_own_inode_is_not_descended(self):
        relocated = self.base / "relocated"
        content = "stage copy " + CODEX_AUTH_LITERAL + "\n"

        def replace():
            decoy = self.output / "decoy"
            # The rename keeps the inode, so the identity check would be satisfied.
            os.rename(str(decoy), str(relocated))
            os.symlink(str(relocated), str(decoy))

        lstat, state = self.lstat_then_replace("decoy", replace)
        with patch.object(run_provider.os, "lstat", lstat):
            record = self.run_codex(execute=self.decoy_stage("leak.json"))

        self.assertTrue(state)
        self.assert_untouched(relocated / "leak.json", content)
        self.assertEqual([], record["diagnostics"]["purged_secret_files"])
        self.assertIn("decoy", record["diagnostics"]["unscanned_paths"])
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("PURGE_INCOMPLETE", record["envelope"]["error_code"])
        self.assertEqual([], self.refused_removals)

    def test_a_home_directory_moved_outside_and_relinked_by_inode_is_not_descended(self):
        relocated = self.base / "home-relocated"

        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            nested = root / ".provider-home" / "swap"
            nested.mkdir()
            (nested / "inner.txt").write_text("inner\n")
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        def replace():
            swap = self.output / ".provider-home" / "swap"
            os.rename(str(swap), str(relocated))
            os.symlink(str(relocated), str(swap))

        lstat, state = self.lstat_then_replace("swap", replace)
        with patch.object(run_provider.os, "lstat", lstat):
            record = self.run_codex(execute=execute)

        self.assertTrue(state)
        self.assert_untouched(relocated / "inner.txt", "inner\n")
        self.assertIn(
            "PROVIDER_HOME_NOT_REMOVED", record["diagnostics"]["cleanup_errors"]
        )
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual([], self.refused_removals)


class CleanupPinningTests(ProviderStageTestCase):
    """A child that pins cleanup must not leave the copied credential behind.

    H-2/R3-03/bugs F-7: `chflags uchg`, a chain nested past any recursion limit, and a
    stage directory stripped of its write bit each stopped one cleanup step; the ones
    after it were skipped or the stage ended as a traceback.
    """

    def unpin(self, path):
        """Teardown for a fixture that deliberately pins a file the tests then remove."""
        def clear():
            try:
                os.chflags(str(path), 0, follow_symlinks=False)
            except (AttributeError, OSError):
                pass
        return clear

    def demolish(self, root):
        """Remove a chain deeper than the interpreter's own recursion limit."""
        def remove():
            if not root.exists():
                return
            limit = sys.getrecursionlimit()
            sys.setrecursionlimit(10000)
            try:
                shutil.rmtree(str(root), ignore_errors=True)
            finally:
                sys.setrecursionlimit(limit)
        return remove

    def test_an_immutable_auth_copy_is_unpinned_and_removed(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            auth = root / ".provider-home" / "auth.json"
            self.addCleanup(self.unpin(auth))
            os.chflags(str(auth), stat.UF_IMMUTABLE)
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        self.assertFalse((self.output / ".provider-home").exists())
        self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))
        self.assertEqual("PASS", record["envelope"]["status"])

    def test_an_immutable_stage_file_is_unpinned_only_inside_this_runs_home(self):
        outside = self.base / "outside.json"
        outside.write_text("victim " + CODEX_AUTH_LITERAL + "\n")
        os.chflags(str(outside), stat.UF_IMMUTABLE)
        self.addCleanup(self.unpin(outside))

        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            os.symlink(str(outside), str(root / ".provider-home" / "alias.json"))
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        self.run_codex(execute=execute)
        self.assertEqual(
            stat.UF_IMMUTABLE, os.lstat(str(outside)).st_flags & stat.UF_IMMUTABLE
        )
        self.assert_untouched(outside, "victim " + CODEX_AUTH_LITERAL + "\n")

    def test_unpinning_never_reaches_through_a_component_swapped_mid_walk(self):
        # os.chflags takes no dir_fd, so the walk re-checks that the descriptor it holds
        # is still the directory the path names. Without that, a child that swaps the
        # component for a link clears the flag on a file outside its own HOME.
        outside = self.base / "outside"
        outside.mkdir()
        victim = outside / "pinned.json"
        victim.write_text("victim\n")
        self.addCleanup(self.unpin(victim))
        os.chflags(str(victim), stat.UF_IMMUTABLE)

        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            nested = root / ".provider-home" / "sub"
            nested.mkdir()
            pinned = nested / "pinned.json"
            pinned.write_text("stage\n")
            self.addCleanup(self.unpin(self.base / "sub-detached" / "pinned.json"))
            os.chflags(str(pinned), stat.UF_IMMUTABLE)
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        real_lstat = os.lstat
        state = []

        def lstat_then_swap(path, *args, **kwargs):
            info = real_lstat(path, *args, **kwargs)
            if not state and path == "pinned.json" and kwargs.get("dir_fd") is not None:
                state.append(True)
                nested = self.output / ".provider-home" / "sub"
                os.rename(str(nested), str(self.base / "sub-detached"))
                os.symlink(str(outside), str(nested))
            return info

        with patch.object(run_provider.os, "lstat", lstat_then_swap):
            self.run_codex(execute=execute)

        self.assertTrue(state)
        self.assertEqual(
            stat.UF_IMMUTABLE, os.lstat(str(victim)).st_flags & stat.UF_IMMUTABLE
        )
        self.assert_untouched(victim, "victim\n")
        self.assertEqual([], self.refused_removals)

    def test_a_chain_nested_past_the_recursion_limit_does_not_skip_later_cleanup(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(
                "raw " + CODEX_AUTH_LITERAL + " unsealed\n"
            )
            (root / "stray.txt").write_text("copied auth " + CODEX_AUTH_LITERAL + "\n")
            home = root / ".provider-home" / "tmp"
            self.addCleanup(self.demolish(root / ".provider-home"))
            # Names are resolved through descriptors, so the chain goes far past any
            # path buffer as well as past the interpreter's recursion limit.
            current = os.open(str(home), os.O_RDONLY | os.O_DIRECTORY)
            try:
                for _ in range(1200):
                    os.mkdir("d", dir_fd=current)
                    nested = os.open("d", os.O_RDONLY | os.O_DIRECTORY, dir_fd=current)
                    os.close(current)
                    current = nested
            finally:
                os.close(current)
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertIn(
            "PROVIDER_HOME_NOT_REMOVED", record["diagnostics"]["cleanup_errors"]
        )
        # The steps after the one the child pinned still ran.
        self.assertFalse((self.output / "stray.txt").exists())
        self.assertFalse((self.output / "semantic-result.json").exists())
        self.assertFalse((self.output / ".provider-home" / "auth.json").exists())

    def test_a_cleanup_step_that_raises_is_reported_and_the_rest_still_run(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            (root / "stray.txt").write_text("copied auth " + CODEX_AUTH_LITERAL + "\n")
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        def explode(*args, **kwargs):
            raise RecursionError("maximum recursion depth exceeded")

        with patch.object(run_provider, "_remove_provider_home", explode):
            record = self.run_codex(execute=execute)
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertIn(
            "PROVIDER_HOME_CLEANUP_FAILED", record["diagnostics"]["cleanup_errors"]
        )
        self.assertFalse((self.output / "stray.txt").exists())
        self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))

    def test_a_read_only_stage_directory_does_not_pin_a_credential_file(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            locked = root / "locked"
            locked.mkdir()
            (locked / "leak.txt").write_text("copied auth " + CODEX_AUTH_LITERAL + "\n")
            os.chmod(str(locked), 0o555)
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))
        self.assertIn("locked/leak.txt", record["diagnostics"]["purged_secret_files"])
        self.assertEqual("PASS", record["envelope"]["status"])

    def test_a_mode_stripped_stage_directory_is_still_walked(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            hidden = root / "hidden"
            hidden.mkdir()
            (hidden / "leak.txt").write_text("copied auth " + CODEX_AUTH_LITERAL + "\n")
            os.chmod(str(hidden), 0o000)
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))
        self.assertIn("hidden/leak.txt", record["diagnostics"]["purged_secret_files"])
        self.assertEqual("PASS", record["envelope"]["status"])


class EscapedDiagnosticsTests(ProviderStageTestCase):
    r"""SEC-6 (un-deferred): raw diagnostics must not spell the literal out in \uXXXX."""

    def escaped(self, text):
        return "".join("\\u%04x" % ord(character) for character in text)

    def test_an_escaped_credential_never_reaches_the_stdout_tail(self):
        payload = semantic_payload()
        stdout = json.dumps({"structured_output": payload}) + "\ntrace " + self.escaped(
            OAUTH_LITERAL
        )
        record = self.run_claude(stdout, execute=self.stub_claude(stdout))
        tail = record["diagnostics"]["stdout_tail"]
        self.assertNotIn(self.escaped(OAUTH_LITERAL), tail)
        self.assertIn(REDACTED, tail)

    def test_an_escaped_credential_never_reaches_the_stderr_tail(self):
        payload = semantic_payload()
        stdout = json.dumps({"structured_output": payload})
        stderr = "warn " + self.escaped(OAUTH_LITERAL) + " end"
        record = self.run_claude(stdout, execute=self.stub_claude(stdout, stderr))
        self.assertNotIn(self.escaped(OAUTH_LITERAL), record["diagnostics"]["stderr_tail"])

    def test_an_ordinary_escape_in_provider_output_survives_untouched(self):
        payload = semantic_payload()
        stdout = json.dumps({"structured_output": payload}) + "\npath C:\\\\build\\\\out"
        record = self.run_claude(stdout, execute=self.stub_claude(stdout))
        self.assertIn("C:\\\\build\\\\out", record["diagnostics"]["stdout_tail"])


class DeepResultRecursionTests(ProviderStageTestCase):
    """R4-05: a nesting depth past the interpreter's limit is a BLOCKED result.

    Parsing, redacting and canonicalising an untrusted result are all recursive, so a
    child only has to nest deeply enough for RecursionError to leave the stage as a
    traceback. The stage envelope, the diagnostics and the sealed result went with it.
    """

    def nested(self, depth=None):
        # Depth relative to the interpreter limit. Verified on CPython 3.9.6 (RecursionError
        # near the 1000-frame Python limit) and 3.12.13 (only past its separate, higher C
        # recursion limit); 3.13+ unverified. A fixed 900 passed on 3.9 but parsed fine on
        # 3.12, which would have turned the CI py3.12 leg red.
        if depth is None:
            depth = sys.getrecursionlimit() * 100
        return "[" * depth + "1" + "]" * depth

    def test_a_deeply_nested_codex_result_is_a_blocked_result_not_a_traceback(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(
                '{"deep": ' + self.nested() + "}"
            )
            (root / "stray.txt").write_text("copied auth " + CODEX_AUTH_LITERAL + "\n")
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("RESULT_MALFORMED", record["envelope"]["error_code"])
        self.assertEqual({}, record["semantic"])
        # Cleanup and diagnostics still happened; they were what the traceback skipped.
        self.assertFalse((self.output / ".provider-home").exists())
        self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))
        self.assertIn("stray.txt", record["diagnostics"]["purged_secret_files"])
        self.assertEqual([], record["diagnostics"]["unscanned_paths"])

    def test_a_deeply_nested_claude_result_is_a_blocked_result_not_a_traceback(self):
        stdout = '{"structured_output": {"deep": ' + self.nested() + "}}"
        record = self.run_claude(stdout)
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("RESULT_MALFORMED", record["envelope"]["error_code"])
        self.assertFalse((self.output / ".provider-home").exists())

    def test_a_recursion_error_raised_while_redacting_is_sealed_in_the_stage(self):
        def explode(value, known_secrets=()):
            raise RecursionError("maximum recursion depth exceeded")

        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            (root / "stray.txt").write_text("copied auth " + CODEX_AUTH_LITERAL + "\n")
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        with patch.object(run_provider, "redact_json", explode):
            record = self.run_codex(execute=execute)
        self.assertEqual("RESULT_MALFORMED", record["envelope"]["error_code"])
        self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))

    def test_a_result_depth_a_provider_really_uses_still_passes(self):
        payload = semantic_payload()
        payload["findings"][0]["context"] = json.loads(self.nested(40))
        record = self.run_codex(semantic=payload)
        self.assertEqual("PASS", record["envelope"]["status"])


class SealedResultPurgeTests(ProviderStageTestCase):
    """SEC-2 (un-deferred): the parent's own sealed result is not a purge target.

    A credential the child put in a JSON *key* survived the value redaction, so the
    purge found it in the file the parent had just sealed and deleted that file — and
    the stage still answered PASS with no result at all.
    """

    def keyed_result(self):
        payload = semantic_payload()
        payload["findings"][0]["ref-" + CODEX_AUTH_LITERAL] = "clean"
        return payload

    def test_a_credential_in_a_result_key_never_reaches_the_sealed_file(self):
        record = self.run_codex(semantic=self.keyed_result())
        sealed = self.output / "semantic-result.json"
        self.assertEqual("PASS", record["envelope"]["status"])
        self.assertTrue(sealed.is_file())
        self.assertNotIn(CODEX_AUTH_LITERAL, sealed.read_text())
        self.assertNotIn(CODEX_AUTH_LITERAL, json.dumps(record["semantic"]))
        self.assertEqual([], record["diagnostics"]["purged_secret_files"])

    def test_a_purged_parent_sealed_result_blocks_the_stage(self):
        with patch.object(run_provider, "redact_json", lambda value, secrets=(): value):
            record = self.run_codex(semantic=self.keyed_result())
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertIn("SEALED_RESULT_PURGED", record["diagnostics"]["cleanup_errors"])

    def test_two_result_keys_that_collapse_to_one_are_a_malformed_result(self):
        payload = semantic_payload()
        # Two different vendor-shaped keys redact to the same name; merging them would
        # silently drop one half of a model-owned payload.
        payload["findings"][0]["sk-ant-AAAABBBBCCCC"] = 1
        payload["findings"][0]["sk-ant-DDDDEEEEFFFF"] = 2
        record = self.run_codex(semantic=payload)
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("RESULT_MALFORMED", record["envelope"]["error_code"])
        self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))


class ResultKeyCollisionTests(ProviderStageTestCase):
    """SEC-2 (un-deferred), R6 (g): redacting a key can collapse two of them into one.

    The model owns the payload, so the parent may not decide which of two names the
    reader was meant to see. A collision is therefore a malformed result on both
    engines — whether or not the two values happen to be equal, because equality is a
    property of this one payload and not evidence that dropping a key is safe.

    Keys that merely *contain* a credential are a different case and stay a PASS: the
    literal is redacted out of the name and nothing is merged, which is the contract
    the rest of this class's siblings already pin.
    """

    def literal_for(self, engine):
        return OAUTH_LITERAL if engine == "claude" else CODEX_AUTH_LITERAL

    def stage(self, engine, extra_keys):
        payload = semantic_payload()
        payload["findings"][0].update(extra_keys)
        if engine == "claude":
            return self.run_claude(json.dumps({"structured_output": payload}))
        return self.run_codex(semantic=payload)

    def assert_no_literal_survives(self, engine, record):
        literal = self.literal_for(engine)
        self.assertIsNone(self.disk_contains(literal))
        self.assertNotIn(literal, json.dumps(record["semantic"]))
        if engine == "codex":
            # The parent never sealed this file, so the child's own copy — the one
            # still holding the literal in a key — must not be left behind.
            self.assertFalse((self.output / "semantic-result.json").exists())

    def test_a_key_collision_is_a_malformed_result_on_both_engines(self):
        for engine in ("claude", "codex"):
            for label, values in (("different values", ("a", "b")), ("equal values", ("a", "a"))):
                with self.subTest(engine=engine, values=label):
                    self.setUp()
                    literal = self.literal_for(engine)
                    record = self.stage(engine, {REDACTED: values[0], literal: values[1]})
                    self.assertEqual("BLOCKED", record["envelope"]["status"])
                    self.assertEqual("RESULT_MALFORMED", record["envelope"]["error_code"])
                    self.assertEqual({}, record["semantic"])
                    self.assert_no_literal_survives(engine, record)

    def test_two_keys_that_redact_to_the_same_name_collide_on_both_engines(self):
        for engine in ("claude", "codex"):
            with self.subTest(engine=engine):
                self.setUp()
                literal = self.literal_for(engine)
                record = self.stage(engine, {"k-" + literal: 1, "k-sk-ant-AAAABBBBCCCC": 1})
                self.assertEqual("BLOCKED", record["envelope"]["status"])
                self.assertEqual("RESULT_MALFORMED", record["envelope"]["error_code"])
                self.assert_no_literal_survives(engine, record)

    def test_literal_keys_that_stay_distinct_still_pass_with_both_kept(self):
        # R6 (g) order A/B, both orders: `p-` and `q-` survive the redaction, so the
        # two keys never collapse. Nothing is merged and nothing is lost, so blocking
        # here would refuse a payload that is already safe.
        for engine in ("claude", "codex"):
            for order in ("A", "B"):
                with self.subTest(engine=engine, order=order):
                    self.setUp()
                    literal = self.literal_for(engine)
                    pair = {"p-" + literal: "1", "q-" + literal: "2"}
                    if order == "B":
                        pair = {"q-" + literal: "2", "p-" + literal: "1"}
                    record = self.stage(engine, pair)
                    self.assertEqual("PASS", record["envelope"]["status"])
                    finding = record["semantic"]["findings"][0]
                    self.assertEqual("1", finding["p-" + REDACTED])
                    self.assertEqual("2", finding["q-" + REDACTED])
                    self.assertIsNone(self.disk_contains(literal))
                    self.assertNotIn(literal, json.dumps(record["semantic"]))
                    self.assertEqual([], record["diagnostics"]["purged_secret_files"])

    def test_a_collision_never_leaves_the_stage_result_on_disk_for_a_peer(self):
        # The BLOCKED path still owes the same cleanup a PASS does.
        record = self.stage("codex", {REDACTED: "a", CODEX_AUTH_LITERAL: "a"})
        self.assertEqual("RESULT_MALFORMED", record["envelope"]["error_code"])
        self.assertFalse((self.output / ".provider-home").exists())
        self.assertEqual([], record["diagnostics"]["unscanned_paths"])
        self.assertEqual([], record["diagnostics"]["cleanup_errors"])


class ResultPathHelperTests(unittest.TestCase):
    def test_read_refuses_a_symlink_with_a_dedicated_error(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            target = base / "target.json"
            target.write_text("{}")
            link = base / "link.json"
            os.symlink(str(target), str(link))
            with self.assertRaises(run_provider._UnsafeResultPath):
                run_provider._read_regular_file(link, run_provider._MAX_RESULT_BYTES)
            self.assertTrue(target.is_file())

    def test_replace_writes_a_new_inode_at_owner_only_mode(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "result.json"
            path.write_text("original")
            before = os.stat(str(path)).st_ino
            run_provider._replace_with_canonical(path, b'{"a":1}')
            after = os.stat(str(path))
            self.assertNotEqual(before, after.st_ino)
            self.assertEqual(0o600, stat.S_IMODE(after.st_mode))
            self.assertEqual('{"a":1}', path.read_text())
            self.assertEqual(
                ["result.json"], sorted(item.name for item in Path(td).iterdir())
            )

    def test_read_accepts_a_plain_regular_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "result.json"
            path.write_text('{"ok":true}')
            self.assertEqual(b'{"ok":true}', run_provider._read_regular_file(path, 1024))

    def test_missing_result_file_raises_a_plain_os_error(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(OSError) as caught:
                run_provider._read_regular_file(Path(td) / "absent.json", 1024)
            self.assertEqual(errno.ENOENT, caught.exception.errno)


if __name__ == "__main__":
    unittest.main()


class SearchDeniedCleanupTests(ProviderStageTestCase):
    """A directory a child leaves readable but not searchable is not "already gone".

    R4-01: `lstat` inside a 0400/0600 directory fails with EACCES, and reporting that
    as GONE let the stage answer PASS with the injected credential and the copied
    provider HOME still on disk. Only ENOENT means gone; every other failure is
    recovered once through the descriptor the parent holds, and what stays unproven is
    reported instead of being passed over.
    """

    def unlock(self):
        """Teardown: a fixture that strips modes must not block the temp cleanup."""
        def restore():
            for path in [self.output] + sorted(self.output.rglob("*")):
                try:
                    if path.is_dir() and not path.is_symlink():
                        os.chmod(str(path), 0o700)
                except OSError:
                    pass
        return restore

    def hiding_stage(self, mode, directory="hidden"):
        """A codex stage that buries the credential in a directory it then locks."""
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            hidden = root / directory
            hidden.mkdir()
            (hidden / "leak.txt").write_text("copied auth " + CODEX_AUTH_LITERAL + "\n")
            os.chmod(str(hidden), mode)
            self.addCleanup(self.unlock())
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}
        return execute

    def test_a_readable_but_unsearchable_subdirectory_does_not_hide_a_credential(self):
        record = self.run_codex(execute=self.hiding_stage(0o400))
        self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))
        self.assertIn("hidden/leak.txt", record["diagnostics"]["purged_secret_files"])
        self.assertNotEqual("GONE", record["diagnostics"]["purge_notes"].get("hidden/leak.txt"))
        self.assertEqual("PASS", record["envelope"]["status"])

    def test_a_writable_but_unsearchable_subdirectory_does_not_hide_a_credential(self):
        record = self.run_codex(execute=self.hiding_stage(0o600))
        self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))
        self.assertIn("hidden/leak.txt", record["diagnostics"]["purged_secret_files"])
        self.assertEqual("PASS", record["envelope"]["status"])

    def test_an_unrecoverable_directory_blocks_the_stage_instead_of_passing(self):
        with patch.object(run_provider, "_recover_directory_write", lambda fd: False):
            record = self.run_codex(execute=self.hiding_stage(0o400))
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertIn("PURGE_INCOMPLETE", record["diagnostics"]["cleanup_errors"])
        self.assertIn("hidden/leak.txt", record["diagnostics"]["unscanned_paths"])

    def test_a_name_component_inside_an_unsearchable_directory_is_still_reported(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            hidden = root / "hidden"
            hidden.mkdir()
            (hidden / ("name-" + CODEX_AUTH_LITERAL + ".txt")).write_text("clean\n")
            os.chmod(str(hidden), 0o400)
            self.addCleanup(self.unlock())
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        self.assertEqual([], sorted(
            str(item) for item in self.output.rglob("*") if CODEX_AUTH_LITERAL in item.name
        ))
        self.assertEqual("PASS", record["envelope"]["status"])

    def locking_root_stage(self, engine_literal, stdout=""):
        """A stage that strips the search bit from the stage root the parent owns."""
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            if engine == "codex":
                (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            (root / "stray.txt").write_text("copied auth " + engine_literal + "\n")
            (root / ".provider-home" / "tmp" / "session.txt").write_text(
                "session " + engine_literal + "\n"
            )
            os.chmod(str(root), 0o400)
            self.addCleanup(self.unlock())
            return {
                "stdout": stdout, "stderr": "",
                "envelope": passing_envelope(stage, engine, stdout),
            }
        return execute

    def test_a_claude_stage_root_stripped_of_search_still_removes_the_provider_home(self):
        stdout = json.dumps({"structured_output": semantic_payload()})
        record = self.run_claude(stdout, execute=self.locking_root_stage(OAUTH_LITERAL, stdout))
        self.assertFalse((self.output / ".provider-home").exists())
        self.assertIsNone(self.disk_contains(OAUTH_LITERAL))
        self.assertEqual("PASS", record["envelope"]["status"])

    def test_a_codex_stage_root_stripped_of_search_still_removes_the_provider_home(self):
        record = self.run_codex(execute=self.locking_root_stage(CODEX_AUTH_LITERAL))
        self.assertFalse((self.output / ".provider-home").exists())
        self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))

    def test_a_provider_home_that_stays_unreachable_is_reported_not_assumed_gone(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            os.chmod(str(root), 0o400)
            self.addCleanup(self.unlock())
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        with patch.object(run_provider, "_recover_directory_write", lambda fd: False):
            record = self.run_codex(execute=execute)
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertIn(
            "PROVIDER_HOME_NOT_REMOVED", record["diagnostics"]["cleanup_errors"]
        )

    def test_a_provider_home_moved_aside_and_locked_is_still_purged(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            os.rename(str(root / ".provider-home"), str(root / "moved-home"))
            os.chmod(str(root / "moved-home"), 0o400)
            self.addCleanup(self.unlock())
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))
        self.assertEqual("PASS", record["envelope"]["status"])

    def test_the_purge_unlocks_the_stage_root_without_relying_on_an_earlier_step(self):
        """The walk restores the root's own bits itself, not as a side effect of HOME removal."""
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            (root / "stray.txt").write_text("copied auth " + CODEX_AUTH_LITERAL + "\n")
            os.chmod(str(root), 0o400)
            self.addCleanup(self.unlock())
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        with patch.object(run_provider, "_remove_provider_home", lambda home: None):
            record = self.run_codex(execute=execute)
        self.assertIsNone(self.disk_contains(CODEX_AUTH_LITERAL))
        self.assertIn("stray.txt", record["diagnostics"]["purged_secret_files"])

    def test_a_directory_whose_identity_changed_is_never_chmodded_by_name(self):
        """Recovery is for a directory the child locked, never for one it swapped."""
        class Swapped:
            def __init__(self, info):
                self.st_mode = info.st_mode
                self.st_ino = info.st_ino + 1

        real_stat = run_provider._stat_entry

        def swapping(dir_fd, name):
            info, verdict = real_stat(dir_fd, name)
            if info is not None and name == "swapped":
                return Swapped(info), None
            return info, verdict

        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            (root / "semantic-result.json").write_text(json.dumps(semantic_payload()))
            swapped = root / "swapped"
            swapped.mkdir()
            os.chmod(str(swapped), 0o500)
            self.addCleanup(self.unlock())
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        with patch.object(run_provider, "_stat_entry", swapping):
            record = self.run_codex(execute=execute)
        self.assertEqual(
            0o500, stat.S_IMODE(os.lstat(str(self.output / "swapped")).st_mode)
        )
        self.assertIn("swapped", record["diagnostics"]["unscanned_paths"])
        self.assertEqual("BLOCKED", record["envelope"]["status"])

    def test_a_raw_result_the_parent_cannot_discard_is_reported(self):
        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            root = Path(output_root)
            # A directory at the result path is never read, so it is never sealed; the
            # discard step cannot remove it and must say so rather than stay silent.
            (root / "semantic-result.json").mkdir()
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        record = self.run_codex(execute=execute)
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertIn(
            "RAW_RESULT_CLEANUP_FAILED", record["diagnostics"]["cleanup_errors"]
        )


class PrelaunchAuthTests(ProviderStageTestCase):
    """Auth the parent injected but cannot read back must stop the stage before launch.

    `_known_secrets` answered `[]` for an `auth.json` it could not parse, and the stage
    launched the child on the very next line. The parent then held no inventory at all:
    nothing to redact out of the child's output, and nothing for the purge to look for.
    SHARED/CLAUDE.md makes an auth failure BLOCKED, so the child is never started and the
    stage answers with a complete envelope instead of a traceback.
    """

    def stage_with_auth(self, write_auth, before_secrets=None):
        launches = []

        def execute(command, packet_source, output_root, packet, stage, engine, *rest, **kwargs):
            launches.append(engine)
            (Path(output_root) / "semantic-result.json").write_text(
                json.dumps(semantic_payload())
            )
            return {"stdout": "", "stderr": "", "envelope": passing_envelope(stage, engine, "")}

        auth = self.base / "auth.json"
        write_auth(auth)
        stack = [
            patch.dict(os.environ, {"HB_CODEX_AUTH_FILE": str(auth)}, clear=False),
            patch.object(run_provider, "run_isolated_process", execute),
        ]
        if before_secrets is not None:
            stack.append(before_secrets)
        for item in stack:
            item.start()
            self.addCleanup(item.stop)
        record = run_provider_stage(
            "codex", "evaluate", PACKET, self.source, self.output, "prompt"
        )
        return record, launches

    def unreadable_after_copy(self):
        """Break the copied file, not the source: the parent owns this exact path."""
        real = run_provider._ephemeral_environment

        def wrapper(engine, output_root):
            environment = real(engine, output_root)
            target = Path(output_root) / ".provider-home" / "auth.json"
            os.chmod(str(target), 0o000)
            self.addCleanup(
                lambda: target.exists() and os.chmod(str(target), 0o600)
            )
            return environment

        return patch.object(run_provider, "_ephemeral_environment", wrapper)

    def assert_refused_before_launch(self, record, launches):
        self.assertEqual([], launches)
        self.assertEqual("BLOCKED", record["envelope"]["status"])
        self.assertEqual("PROVIDER_AUTH_UNUSABLE", record["envelope"]["error_code"])
        self.assertEqual({}, record["semantic"])
        # A stage that never launched still owes the gate every envelope field.
        self.assertNotIn(
            "ENVELOPE_REQUIRED_FIELD_MISSING",
            validate_execution_envelope(record["envelope"], "evaluate", "codex", PACKET),
        )
        # Its own HOME, with the copied credential in it, is gone.
        self.assertFalse((self.output / ".provider-home").exists())
        self.assertEqual([], self.refused_removals)

    def test_malformed_injected_auth_blocks_before_the_child_is_launched(self):
        record, launches = self.stage_with_auth(
            lambda path: path.write_text("{not json" + CODEX_AUTH_LITERAL)
        )
        self.assert_refused_before_launch(record, launches)
        # The unparsable bytes are the one thing the parent could not build an inventory
        # from, so they must not travel in the record either.
        self.assertNotIn(CODEX_AUTH_LITERAL, json.dumps(record, ensure_ascii=False))

    def test_non_object_injected_auth_blocks_before_the_child_is_launched(self):
        record, launches = self.stage_with_auth(lambda path: path.write_text(""))
        self.assert_refused_before_launch(record, launches)

    @unittest.skipIf(os.geteuid() == 0, "root reads a 0o000 file")
    def test_unreadable_injected_auth_blocks_before_the_child_is_launched(self):
        record, launches = self.stage_with_auth(
            lambda path: path.write_text(json.dumps({"tokens": {"access": CODEX_AUTH_LITERAL}})),
            before_secrets=self.unreadable_after_copy(),
        )
        self.assert_refused_before_launch(record, launches)

    def test_valid_injected_auth_still_launches_and_passes(self):
        record, launches = self.stage_with_auth(
            lambda path: path.write_text(json.dumps({"tokens": {"access": CODEX_AUTH_LITERAL}}))
        )
        self.assertEqual(["codex"], launches)
        self.assertEqual("PASS", record["envelope"]["status"])
        self.assertIsNone(record["envelope"]["error_code"])
        self.assertEqual("evaluate", record["semantic"]["stage"])
        self.assertNotIn(CODEX_AUTH_LITERAL, json.dumps(record, ensure_ascii=False))


class PurgeSymlinkReadFaultTests(unittest.TestCase):
    """A link the parent cannot read is still on disk, so it cannot be reported gone.

    `readlink` failing meant "GONE" and the entry was skipped, which threw away both
    halves of the judgement: an unreadable link stopped blocking the stage, and a link
    whose own *name* carries the credential survived a fault the child can provoke.
    Only ENOENT says the entry left the disk; every other fault is unscannable, and the
    name-based removal never needed the link text in the first place.
    """

    LINK = "plain.lnk"
    NAMED = CODEX_AUTH_LITERAL + ".lnk"

    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.base), True)
        self.stage = self.base / "stage"
        self.stage.mkdir()
        self.peer = self.base / "peer.txt"
        self.peer.write_text("peer bytes\n")

    def link(self, name, target=None):
        path = self.stage / name
        os.symlink(str(target or self.peer), str(path))
        return path

    def refusing_readlink(self, error, only):
        """Fail `readlink` for one entry name only; every other read stays real."""
        real = os.readlink

        def readlink(name, *args, **kwargs):
            if name == only:
                raise error
            return real(name, *args, **kwargs)

        return patch.object(run_provider.os, "readlink", readlink)

    def purge(self):
        return run_provider._purge_secret_files(self.stage, [CODEX_AUTH_LITERAL])

    def assert_peer_untouched(self):
        self.assertTrue(self.peer.is_file())
        self.assertEqual("peer bytes\n", self.peer.read_text())

    def test_an_unreadable_link_blocks_instead_of_being_reported_gone(self):
        for name, number in (("EACCES", errno.EACCES), ("EIO", errno.EIO), ("EPERM", errno.EPERM)):
            with self.subTest(fault=name):
                path = self.link(self.LINK)
                try:
                    with self.refusing_readlink(OSError(number, "fixture refusal"), self.LINK):
                        report = self.purge()
                    self.assertEqual([self.LINK], report["unscanned"])
                    self.assertNotIn(self.LINK, report["notes"])
                    self.assertTrue(path.is_symlink())
                    self.assert_peer_untouched()
                finally:
                    path.unlink()

    def test_a_credential_named_link_is_removed_without_reading_it(self):
        path = self.link(self.NAMED)
        with self.refusing_readlink(OSError(errno.EACCES, "fixture refusal"), self.NAMED):
            report = self.purge()
        self.assertFalse(path.is_symlink())
        self.assertEqual([self.NAMED], report["purged"])
        self.assertEqual([], report["unscanned"])
        self.assertNotIn(self.NAMED, report["notes"])
        self.assert_peer_untouched()

    def test_a_link_that_left_the_disk_is_still_reported_gone(self):
        path = self.link(self.LINK)
        self.addCleanup(path.unlink)
        with self.refusing_readlink(FileNotFoundError(errno.ENOENT, "fixture"), self.LINK):
            report = self.purge()
        self.assertEqual("GONE", report["notes"][self.LINK])
        self.assertEqual([], report["unscanned"])

    def test_a_readable_link_is_still_judged_on_its_text(self):
        carrier = self.link("carrier.lnk", self.base / (CODEX_AUTH_LITERAL + "-target.txt"))
        clean = self.link("clean.lnk")
        report = self.purge()
        self.assertFalse(carrier.is_symlink())
        self.assertTrue(clean.is_symlink())
        self.assertEqual(["carrier.lnk"], report["purged"])
        self.assertEqual([], report["unscanned"])
        self.assertEqual({}, report["notes"])
        self.assert_peer_untouched()
