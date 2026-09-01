import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review.run_provider import _ephemeral_environment


class EphemeralProviderHomeTests(unittest.TestCase):
    def test_claude_uses_output_scoped_home_and_only_claude_auth(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "output"
            output.mkdir()
            with patch.dict(os.environ, {
                "CLAUDE_CODE_OAUTH_TOKEN": "fixture-oauth",
                "CODEX_HOME": "/must/not/pass",
            }, clear=False):
                env = _ephemeral_environment("claude", output)
            self.assertTrue(Path(env["HOME"]).is_relative_to(output))
            self.assertEqual("fixture-oauth", env["CLAUDE_CODE_OAUTH_TOKEN"])
            self.assertNotIn("CODEX_HOME", env)
            shutil.rmtree(output / ".provider-home")

    def test_codex_copies_only_auth_into_output_scoped_home(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            output = base / "output"
            output.mkdir()
            auth = base / "auth.json"
            auth.write_text('{"fixture":"not-a-real-token"}')
            with patch.dict(os.environ, {
                "HB_CODEX_AUTH_FILE": str(auth),
                "CLAUDE_CODE_OAUTH_TOKEN": "must-not-pass",
            }, clear=False):
                env = _ephemeral_environment("codex", output)
            provider_home = Path(env["HOME"])
            self.assertTrue(provider_home.is_relative_to(output))
            self.assertEqual(provider_home, Path(env["CODEX_HOME"]))
            self.assertEqual(auth.read_text(), (provider_home / "auth.json").read_text())
            self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", env)
            self.assertEqual({"auth.json", "tmp"}, {path.name for path in provider_home.iterdir()})
            shutil.rmtree(provider_home)


if __name__ == "__main__":
    unittest.main()
