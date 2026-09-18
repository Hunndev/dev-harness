import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review import run_provider
from hb_eval_review.process import run_isolated_process
import test_run_provider as provider_fixtures


class EvidenceReadScopeTests(unittest.TestCase):
    def test_provider_stage_passes_packet_read_scope_and_retains_peer_denial(self):
        for engine in ("claude", "codex"):
            with self.subTest(engine=engine), tempfile.TemporaryDirectory() as td:
                root = Path(td).resolve()
                output_root = root / "run"
                packet_root = output_root / "materialized-packet"
                source = packet_root / "source"
                source.mkdir(parents=True)
                (source / "app.py").write_text("pass\n")
                evidence = packet_root / "evidence"
                evidence.mkdir()
                diff = evidence / "diff.patch"
                diff.write_text("diff evidence\n")
                diff.chmod(0o444)
                stage_output = output_root / ("evaluate-" + engine)
                peer = output_root / ("evaluate-codex" if engine == "claude" else "evaluate-claude")
                peer.mkdir()
                (peer / "sealed.json").write_text("peer verdict\n")
                home = root / "fake-home"
                home.mkdir()
                auth = root / "fake-auth.json"
                auth.write_text(json.dumps({"tokens": {"access": provider_fixtures.CODEX_AUTH_LITERAL}}))
                auth.chmod(0o600)
                captured = []
                semantic = provider_fixtures.semantic_payload()

                def child(command, packet_source, child_output, packet, stage, child_engine, *args, **kwargs):
                    captured.append((packet_source, child_output, kwargs))
                    if child_engine == "claude":
                        stdout = json.dumps({"structured_output": semantic})
                    else:
                        (Path(child_output) / "semantic-result.json").write_text(json.dumps(semantic))
                        stdout = ""
                    return {"stdout": stdout, "stderr": "", "envelope":
                            provider_fixtures.passing_envelope(stage, child_engine, stdout)}

                env = {"HOME": str(home), "PATH": os.defpath,
                       "CLAUDE_CODE_OAUTH_TOKEN": provider_fixtures.OAUTH_LITERAL,
                       "HB_CODEX_AUTH_FILE": str(auth)}
                with patch.dict(os.environ, env, clear=True), \
                     patch.object(run_provider, "run_isolated_process", side_effect=child), \
                     patch.object(run_provider, "_claude_temp_root", return_value=root / "fake-claude-temp"):
                    result = run_provider.run_provider_stage(
                        engine, "evaluate", provider_fixtures.PACKET, source, stage_output, "review evidence",
                        peer_output_root=peer, readable_roots=[packet_root],
                    )
                self.assertEqual("PASS", result["envelope"]["status"], result)
                self.assertEqual(1, len(captured))
                protected, output, scopes = captured[0]
                self.assertEqual(source, protected)
                self.assertEqual(stage_output, output)
                reads = [Path(path).resolve() for path in scopes["readable_roots"]]
                writes = [Path(path).resolve() for path in scopes["writable_roots"]]
                denied = [Path(path).resolve() for path in scopes["denied_read_roots"]]
                self.assertIn(packet_root, reads)
                self.assertIn(peer, denied)
                # No readable ancestor may accidentally grant the whole run or a peer.
                self.assertFalse(any(path == output_root or path in output_root.parents for path in reads))
                self.assertFalse(any(path == peer or path in peer.parents for path in reads))
                self.assertFalse(any(path == packet_root or path in packet_root.parents for path in writes))
                self.assertEqual("diff evidence\n", diff.read_text())
                self.assertEqual("peer verdict\n", (peer / "sealed.json").read_text())

    @unittest.skipUnless(sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists(), "macOS sandbox required")
    def test_evidence_read_succeeds_but_write_and_peer_read_are_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            packet_root = root / "materialized-packet"
            source = packet_root / "source"
            source.mkdir(parents=True)
            (source / "app.py").write_text("pass\n")
            evidence = packet_root / "evidence"
            evidence.mkdir()
            diff = evidence / "diff.patch"
            diff.write_text("full diff fixture\n")
            diff.chmod(0o444)
            output = root / "evaluate-claude"
            output.mkdir()
            peer = root / "evaluate-codex"
            peer.mkdir()
            peer_result = peer / "sealed.json"
            peer_result.write_text("private peer finding\n")
            # These are readable/writable by the same OS user outside the sandbox.
            plain = subprocess.run(["/bin/cat", str(peer_result)], capture_output=True, text=True)
            self.assertEqual(0, plain.returncode)
            self.assertEqual("private peer finding\n", plain.stdout)
            diff.chmod(0o644)
            diff.write_text("full diff fixture\n")
            diff.chmod(0o444)

            def run(script):
                return run_isolated_process(
                    ["/bin/sh", "-c", script], source, output, provider_fixtures.PACKET,
                    "evaluate", "claude", 10, {"PATH": os.defpath},
                    readable_roots=[packet_root], denied_read_roots=[peer],
                )

            read = run("cat " + shlex.quote(str(diff)))
            self.assertEqual("PASS", read["envelope"]["status"], read)
            self.assertEqual("full diff fixture\n", read["stdout"])
            write = run("chmod u+w " + shlex.quote(str(diff)) + " && printf changed > " + shlex.quote(str(diff)))
            self.assertEqual("BLOCKED", write["envelope"]["status"], write)
            self.assertNotEqual(0, write["envelope"]["exit_code"])
            self.assertEqual("full diff fixture\n", diff.read_text())
            self.assertEqual(0o444, diff.stat().st_mode & 0o777)
            read_peer = run("cat " + shlex.quote(str(peer_result)))
            self.assertEqual("BLOCKED", read_peer["envelope"]["status"], read_peer)
            self.assertNotEqual(0, read_peer["envelope"]["exit_code"])
            self.assertNotIn("private peer finding", read_peer["stdout"])


if __name__ == "__main__":
    unittest.main()
