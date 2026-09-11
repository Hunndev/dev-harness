"""dev-25a acceptance tests: scripts/check-install.sh is a read-only install inventory.

Fixtures imitate ~/.claude and ~/.codex so the script never reads the real ones.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-install.sh"
CLAUDE_MKT = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
CODEX_MKT = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
EXPECTED = {plugin["name"]: plugin["version"] for plugin in CLAUDE_MKT["plugins"]}
PLUGINS = list(EXPECTED)


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            stat = path.stat()
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(str(stat.st_mtime_ns).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


class Fixture:
    def __init__(self, base: Path) -> None:
        self.claude_home = base / "claude-home"
        self.codex_home = base / "codex-home"
        self.claude_home.mkdir()
        self.codex_home.mkdir()

    def claude(self, installed, enabled=None, cached=None) -> None:
        registry = {"version": 2, "plugins": {}}
        for name, version in installed.items():
            if version is None:
                continue
            key = f"{name}@{CLAUDE_MKT['name']}"
            install_path = self.claude_home / "plugins" / "cache" / CLAUDE_MKT["name"] / name / version
            registry["plugins"][key] = [{
                "scope": "user", "installPath": str(install_path), "version": version,
                "installedAt": "2026-01-01T00:00:00.000Z", "lastUpdated": "2026-01-01T00:00:00.000Z",
            }]
        (self.claude_home / "plugins").mkdir(exist_ok=True)
        shutil.rmtree(self.claude_home / "plugins" / "cache", ignore_errors=True)
        (self.claude_home / "plugins" / "installed_plugins.json").write_text(json.dumps(registry), encoding="utf-8")
        flags = {f"{name}@{CLAUDE_MKT['name']}": value for name, value in (enabled or {}).items()}
        (self.claude_home / "settings.json").write_text(json.dumps({"enabledPlugins": flags}), encoding="utf-8")
        for name, versions in (cached or {}).items():
            for version in versions:
                folder = self.claude_home / "plugins" / "cache" / CLAUDE_MKT["name"] / name / version / ".claude-plugin"
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "plugin.json").write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")

    def codex(self, cached, enabled=None) -> None:
        lines = [f"[marketplaces.{CODEX_MKT['name']}]", 'source_type = "git"', 'source = "https://example.invalid/dev-harness.git"', ""]
        for name, value in (enabled or {}).items():
            lines += [f'[plugins."{name}@{CODEX_MKT["name"]}"]', f"enabled = {'true' if value else 'false'}", ""]
        (self.codex_home / "config.toml").write_text("\n".join(lines), encoding="utf-8")
        shutil.rmtree(self.codex_home / "plugins" / "cache", ignore_errors=True)
        for name, versions in cached.items():
            for version in versions:
                folder = self.codex_home / "plugins" / "cache" / CODEX_MKT["name"] / name / version / ".codex-plugin"
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "plugin.json").write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")

    def run(self, *args):
        env = dict(os.environ, HB_CLAUDE_HOME=str(self.claude_home), HB_CODEX_HOME=str(self.codex_home))
        return subprocess.run(["bash", str(SCRIPT), *args], cwd=str(ROOT), env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class CheckInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fx = Fixture(Path(self.tmp.name))

    def all_match(self) -> None:
        self.fx.claude(installed=dict(EXPECTED), enabled={n: True for n in PLUGINS}, cached={n: [EXPECTED[n]] for n in PLUGINS})
        self.fx.codex(cached={n: [EXPECTED[n]] for n in PLUGINS}, enabled={n: True for n in PLUGINS})

    def test_script_exists_and_is_executable_shell(self) -> None:
        self.assertTrue(SCRIPT.is_file(), SCRIPT)
        self.assertTrue(os.access(SCRIPT, os.X_OK), "scripts/check-install.sh must be executable")

    def test_all_versions_match_exit_zero_with_seven_rows(self) -> None:
        self.all_match()
        result = self.fx.run("--json")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(7, len(payload["rows"]))
        self.assertEqual(sorted(PLUGINS), sorted(row["plugin"] for row in payload["rows"]))
        for row in payload["rows"]:
            self.assertEqual(EXPECTED[row["plugin"]], row["expected"])
            self.assertEqual("MATCH", row["claude"]["status"], row)
            self.assertEqual("MATCH", row["codex"]["status"], row)
            self.assertIsNone(row["claude"]["loaded"])
            self.assertIsNone(row["codex"]["loaded"])
            self.assertTrue(row["claude"]["enabled"])
            self.assertTrue(row["codex"]["enabled"])

    def test_version_mismatch_exits_one_and_is_marked(self) -> None:
        self.all_match()
        stale = dict(EXPECTED)
        stale["hb-be"] = "0.5.0"
        self.fx.claude(installed=stale, enabled={n: True for n in PLUGINS}, cached={n: [stale[n]] for n in PLUGINS})
        result = self.fx.run("--json")
        self.assertEqual(1, result.returncode)
        rows = {row["plugin"]: row for row in json.loads(result.stdout)["rows"]}
        self.assertEqual("MISMATCH", rows["hb-be"]["claude"]["status"])
        self.assertEqual("0.5.0", rows["hb-be"]["claude"]["installed"])
        self.assertEqual("MATCH", rows["hb-cm"]["claude"]["status"])
        self.assertEqual("MATCH", rows["hb-be"]["codex"]["status"])

    def test_missing_plugin_is_not_installed_and_only_required_ones_fail(self) -> None:
        partial = {n: EXPECTED[n] for n in PLUGINS if n not in ("hb-aos", "hb-ios")}
        self.fx.claude(installed=partial, enabled={n: True for n in partial}, cached={n: [partial[n]] for n in partial})
        self.fx.codex(cached={n: [partial[n]] for n in partial}, enabled={n: True for n in partial})
        result = self.fx.run("--json")
        self.assertEqual(0, result.returncode, result.stderr)
        rows = {row["plugin"]: row for row in json.loads(result.stdout)["rows"]}
        self.assertEqual("NOT_INSTALLED", rows["hb-aos"]["claude"]["status"])
        self.assertEqual("NOT_INSTALLED", rows["hb-aos"]["codex"]["status"])
        strict = self.fx.run("--json", "--require", "hb-aos,hb-be")
        self.assertEqual(1, strict.returncode)
        payload = json.loads(strict.stdout)
        self.assertIn("hb-aos", payload["required_missing"])
        self.assertNotIn("hb-be", payload["required_missing"])

    def test_unknown_required_name_fails_instead_of_passing_silently(self) -> None:
        self.all_match()
        result = self.fx.run("--json", "--require", "hb-nope")
        self.assertEqual(1, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual(["hb-nope"], payload["required_unknown"])
        self.assertEqual([], payload["required_missing"])

    def test_multiple_registry_scopes_match_when_any_entry_matches(self) -> None:
        self.all_match()
        registry_path = self.fx.claude_home / "plugins" / "installed_plugins.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        key = f"hb-be@{CLAUDE_MKT['name']}"
        stale = dict(registry["plugins"][key][0], scope="project", version="0.1.0")
        registry["plugins"][key] = [stale, registry["plugins"][key][0]]
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        result = self.fx.run("--json")
        self.assertEqual(0, result.returncode, result.stderr)
        row = {r["plugin"]: r for r in json.loads(result.stdout)["rows"]}["hb-be"]
        self.assertEqual("MATCH", row["claude"]["status"])
        self.assertEqual(["0.1.0", EXPECTED["hb-be"]], row["claude"]["installed_all"])
        self.assertIn("0.1.0", self.fx.run().stdout)

    def test_enabled_flag_absent_is_null_and_local_settings_are_merged(self) -> None:
        self.all_match()
        (self.fx.claude_home / "settings.json").write_text(json.dumps({"enabledPlugins": {}}), encoding="utf-8")
        (self.fx.claude_home / "settings.local.json").write_text(
            json.dumps({"enabledPlugins": {f"hb-cm@{CLAUDE_MKT['name']}": False}}), encoding="utf-8")
        rows = {r["plugin"]: r for r in json.loads(self.fx.run("--json").stdout)["rows"]}
        self.assertIsNone(rows["hb-be"]["claude"]["enabled"])
        self.assertIs(False, rows["hb-cm"]["claude"]["enabled"])

    def test_dict_registry_entry_is_read_and_unknown_shape_is_not_not_installed(self) -> None:
        self.all_match()
        registry_path = self.fx.claude_home / "plugins" / "installed_plugins.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        mkt = CLAUDE_MKT["name"]
        registry["plugins"][f"hb-be@{mkt}"] = registry["plugins"][f"hb-be@{mkt}"][0]  # single dict, not list
        registry["plugins"][f"hb-cm@{mkt}"] = "0.8.3"  # unknown shape
        registry["plugins"][f"hb-fe@{mkt}"] = [{"scope": "user", "version": 1}]  # non-string version
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        result = self.fx.run("--json")
        self.assertIn(result.returncode, (0, 1), result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        rows = {r["plugin"]: r for r in json.loads(result.stdout)["rows"]}
        self.assertEqual("MATCH", rows["hb-be"]["claude"]["status"])
        self.assertEqual("UNKNOWN", rows["hb-cm"]["claude"]["status"])
        self.assertEqual("MISMATCH", rows["hb-fe"]["claude"]["status"])
        self.assertEqual(["1"], rows["hb-fe"]["claude"]["installed_all"])

    def test_codex_cache_mismatch_and_marketplace_note(self) -> None:
        self.all_match()
        stale = {n: [EXPECTED[n]] for n in PLUGINS}
        stale["hb-be"] = ["0.5.0"]
        self.fx.codex(cached=stale, enabled={n: True for n in PLUGINS})
        result = self.fx.run("--json")
        self.assertEqual(1, result.returncode)
        rows = {r["plugin"]: r for r in json.loads(result.stdout)["rows"]}
        self.assertEqual("MISMATCH", rows["hb-be"]["codex"]["status"])
        self.assertEqual("MATCH", rows["hb-be"]["claude"]["status"])

    def test_toml_variants_are_parsed(self) -> None:
        self.all_match()
        mkt = CODEX_MKT["name"]
        text = "\n".join([
            f"[marketplaces.{mkt}]", 'source = "x"', "",
            f'[plugins."hb-be@{mkt}"]  # trailing comment', "enabled = true", "",
            f"[plugins.'hb-cm@{mkt}']", 'enabled = "false"', "",
            f'[plugins."hb-fe@{mkt}"]', "# no flag here", "",
            "[plugins]", f'"hb-chat@{mkt}" = {{ enabled = true }}', "",
        ])
        (self.fx.codex_home / "config.toml").write_text(text, encoding="utf-8")
        rows = {r["plugin"]: r for r in json.loads(self.fx.run("--json").stdout)["rows"]}
        self.assertIs(True, rows["hb-be"]["codex"]["enabled"])
        self.assertIs(False, rows["hb-cm"]["codex"]["enabled"])
        self.assertIsNone(rows["hb-fe"]["codex"]["enabled"])
        self.assertIs(True, rows["hb-chat"]["codex"]["enabled"])
        self.assertIs(True, rows["hb-fe"]["codex"]["registered"])
        self.assertIs(False, rows["hb-aos"]["codex"]["registered"])

    def test_examples_inside_multiline_strings_are_not_registrations(self) -> None:
        self.all_match()
        mkt = CODEX_MKT["name"]
        dq, sq = '"' * 3, "'" * 3
        text = "\n".join([
            "developer_instructions = " + dq, "Example config:", f'[plugins."hb-aos@{mkt}"]', "enabled = true",
            f"[plugins.'hb-ios@{mkt}']", "enabled = true", dq, "",
            "notes = " + sq, f'[plugins."hb-chat@{mkt}"]', "enabled = false", sq, "",
            f"[marketplaces.{mkt}]", 'source = "x"', "",
            f'[plugins."hb-be@{mkt}"]  # real', "enabled = true", "",
        ])
        (self.fx.codex_home / "config.toml").write_text(text, encoding="utf-8")
        rows = {r["plugin"]: r for r in json.loads(self.fx.run("--json").stdout)["rows"]}
        self.assertIs(True, rows["hb-be"]["codex"]["registered"])
        self.assertIs(True, rows["hb-be"]["codex"]["enabled"])
        for name in ("hb-aos", "hb-ios", "hb-chat"):
            self.assertIs(False, rows[name]["codex"]["registered"], name)
            self.assertIs(False, rows[name]["codex"]["enabled"], name)

    def test_unparseable_plugin_config_is_unknown_not_false(self) -> None:
        self.all_match()
        mkt = CODEX_MKT["name"]
        text = "\n".join([f'[plugins."hb-be@{mkt}"]', "enabled = true", "", "[plugins.weird.form]", "enabled = true", ""])
        (self.fx.codex_home / "config.toml").write_text(text, encoding="utf-8")
        rows = {r["plugin"]: r for r in json.loads(self.fx.run("--json").stdout)["rows"]}
        self.assertIs(True, rows["hb-be"]["codex"]["registered"])
        self.assertIsNone(rows["hb-cm"]["codex"]["registered"])
        self.assertIsNone(rows["hb-cm"]["codex"]["enabled"])
        unterminated = "\n".join(["developer_instructions = " + '"' * 3, f'[plugins."hb-be@{mkt}"]', "enabled = true"])
        (self.fx.codex_home / "config.toml").write_text(unterminated, encoding="utf-8")
        rows = {r["plugin"]: r for r in json.loads(self.fx.run("--json").stdout)["rows"]}
        self.assertIsNone(rows["hb-be"]["codex"]["registered"])

    def test_non_utf8_config_is_unknown_not_a_traceback(self) -> None:
        self.all_match()
        (self.fx.codex_home / "config.toml").write_bytes(b"\xff\xfe[plugins.\"x\"]\nenabled = true\n")
        (self.fx.claude_home / "settings.json").write_bytes(b"\xff\xfe{")
        result = self.fx.run("--json")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        rows = {r["plugin"]: r for r in json.loads(result.stdout)["rows"]}
        self.assertIsNone(rows["hb-be"]["codex"]["registered"])
        self.assertIsNone(rows["hb-be"]["codex"]["enabled"])
        self.assertEqual("MATCH", rows["hb-be"]["codex"]["status"])
        self.assertIsNone(rows["hb-be"]["claude"]["enabled"])

    def test_unreadable_marketplace_exits_two(self) -> None:
        import shutil
        fake_repo = Path(self.tmp.name) / "not-a-harness"
        (fake_repo / "scripts").mkdir(parents=True)
        shutil.copy(ROOT / "scripts" / "check_install.py", fake_repo / "scripts" / "check_install.py")
        shutil.copy(SCRIPT, fake_repo / "scripts" / "check-install.sh")
        env = dict(os.environ, HB_CLAUDE_HOME=str(self.fx.claude_home), HB_CODEX_HOME=str(self.fx.codex_home))
        result = subprocess.run(["bash", str(fake_repo / "scripts" / "check-install.sh"), "--json"], env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(2, result.returncode)
        self.assertIn("marketplace", result.stderr)

    def test_missing_registries_are_unknown_not_a_crash(self) -> None:
        result = self.fx.run("--json")
        self.assertEqual(0, result.returncode, result.stderr)
        for row in json.loads(result.stdout)["rows"]:
            self.assertEqual("UNKNOWN", row["claude"]["status"], row)
            self.assertEqual("UNKNOWN", row["codex"]["status"], row)

    def test_script_is_read_only(self) -> None:
        self.all_match()
        before = (tree_digest(self.fx.claude_home), tree_digest(self.fx.codex_home))
        self.fx.run()
        self.fx.run("--json", "--require", "hb-be")
        after = (tree_digest(self.fx.claude_home), tree_digest(self.fx.codex_home))
        self.assertEqual(before, after)

    def test_text_table_lists_every_plugin_with_expected_version(self) -> None:
        self.all_match()
        result = self.fx.run()
        self.assertEqual(0, result.returncode, result.stderr)
        for name in PLUGINS:
            self.assertIn(name, result.stdout)
            self.assertIn(EXPECTED[name], result.stdout)
        self.assertIn("loaded", result.stdout)
        self.assertIn("UNKNOWN", result.stdout)


if __name__ == "__main__":
    unittest.main()
