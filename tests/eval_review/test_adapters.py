import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review.adapters.claude import build_claude_command, claude_environment
from hb_eval_review.adapters.codex import build_codex_command, codex_environment


class AdapterTests(unittest.TestCase):
    def test_claude_is_fresh_structured_and_read_only(self):
        command = build_claude_command("packet.md", "schema.json", model="sonnet")
        joined = " ".join(command)
        self.assertIn("--no-session-persistence", command)
        self.assertIn("--json-schema", command)
        self.assertIn("--permission-mode", command)
        self.assertNotIn("--resume", command)
        self.assertNotIn("--continue", command)
        self.assertNotIn("Edit", joined)
        self.assertNotIn("Write", joined)
        self.assertEqual("sonnet", command[command.index("--model") + 1])

    def test_codex_is_ephemeral_structured_and_defers_to_parent_sandbox(self):
        command = build_codex_command(
            Path("/repo"), Path("schema.json"), Path("result.json"), model="gpt-5.6-sol"
        )
        self.assertIn("--ephemeral", command)
        self.assertIn("danger-full-access", command)
        self.assertNotIn("read-only", command)
        self.assertIn("--output-schema", command)
        self.assertIn("--output-last-message", command)
        self.assertEqual("gpt-5.6-sol", command[command.index("--model") + 1])

    def test_codex_environment_excludes_claude_auth(self):
        source = {
            "HOME": "/tmp/home",
            "PATH": "/bin",
            "CODEX_HOME": "/tmp/codex",
            "CLAUDE_CODE_OAUTH_TOKEN": "forbidden",
            "ANTHROPIC_API_KEY": "forbidden",
        }
        env = codex_environment(source)
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", env)
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertEqual("/tmp/codex", env["CODEX_HOME"])

    def test_claude_environment_excludes_codex_auth(self):
        source = {
            "HOME": "/tmp/home",
            "PATH": "/bin",
            "CODEX_HOME": "/tmp/codex",
            "CLAUDE_CODE_OAUTH_TOKEN": "available",
        }
        env = claude_environment(source)
        self.assertNotIn("CODEX_HOME", env)
        self.assertEqual("available", env["CLAUDE_CODE_OAUTH_TOKEN"])


if __name__ == "__main__":
    unittest.main()
