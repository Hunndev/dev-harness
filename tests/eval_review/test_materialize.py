import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review.materialize import (
    materialize_source_packet,
    remove_materialized_packet,
    verify_materialized_packet,
)
from hb_eval_review.snapshot import PacketPolicyError


def git(repo, *args):
    subprocess.run(["git", *args], cwd=str(repo), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class MaterializeTestCase(unittest.TestCase):
    def make_repo(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        source = base / "source"
        source.mkdir()
        git(source, "init", "-q")
        git(source, "config", "user.email", "test@example.invalid")
        git(source, "config", "user.name", "Test")
        return base, source

    def commit(self, source):
        git(source, "add", "-A")
        git(source, "commit", "-qm", "fixture")


class MaterializeContractTests(MaterializeTestCase):
    def test_materialized_source_is_content_verified_and_symlink_safe(self):
        base, source = self.make_repo()
        packet = base / "packet"
        (source / "normal.txt").write_text("hello")
        (source / "space 이름.txt").write_text("world")
        (source / "link").symlink_to("normal.txt")
        self.commit(source)
        (source / ".git" / "extra").write_text("private metadata")
        manifest = materialize_source_packet(source, packet)
        self.assertTrue(verify_materialized_packet(packet, manifest))
        self.assertFalse((packet / "source/.git").exists())
        self.assertTrue((packet / "source" / "link").is_symlink())
        self.assertEqual("normal.txt", (packet / "source" / "link").readlink().as_posix())
        self.assertTrue((packet / "source" / "space 이름.txt").is_file())

    def test_tamper_is_detected(self):
        base, source = self.make_repo()
        packet = base / "packet"
        (source / "a.txt").write_text("a")
        self.commit(source)
        manifest = materialize_source_packet(source, packet)
        (packet / "source" / "a.txt").chmod(0o600)
        (packet / "source" / "a.txt").write_text("tampered")
        self.assertFalse(verify_materialized_packet(packet, manifest))

    def test_read_only_packet_has_explicit_cleanup(self):
        base, source = self.make_repo()
        packet = base / "packet"
        (source / "a.txt").write_text("a")
        self.commit(source)
        materialize_source_packet(source, packet)
        remove_materialized_packet(packet)
        self.assertFalse(packet.exists())


class PacketPathSafetyTests(MaterializeTestCase):
    """A stale index entry under a symlinked directory must never reach the copier."""

    def escaping_repo(self):
        """Depth-matched fixture: `data` resolves to a different victim on each side.

        The link text `../../victim` resolves to `<base>/a/victim` from the source
        repository and to `<base>/victim` from the materialized packet, so a copier
        that follows the link writes outside the destination entirely.
        """
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name).resolve()
        (base / "a" / "victim").mkdir(parents=True)
        (base / "a" / "victim" / "file").write_text("source side payload\n")
        (base / "victim").mkdir()
        victim = base / "victim" / "file"
        victim.write_text("ORIGINAL CONTENT\n")
        source = base / "a" / "b" / "src"
        source.mkdir(parents=True)
        git(source, "init", "-q")
        git(source, "config", "user.email", "test@example.invalid")
        git(source, "config", "user.name", "Test")
        (source / "main.py").write_text("print(1)\n")
        (source / "data").mkdir()
        (source / "data" / "file").write_text("tracked payload\n")
        self.commit(source)
        shutil.rmtree(str(source / "data"))
        (source / "data").symlink_to("../../victim")
        return base, source, victim

    def test_materialize_refuses_a_symlinked_parent_and_writes_nothing_outside(self):
        base, source, victim = self.escaping_repo()
        packet = base / "pk"
        with self.assertRaises(PacketPolicyError) as caught:
            materialize_source_packet(source, packet)
        self.assertEqual("PACKET_PATH_UNSAFE", caught.exception.code)
        self.assertEqual("ORIGINAL CONTENT\n", victim.read_text())
        self.assertFalse((packet / "source").exists())

    def test_copier_refuses_an_entry_whose_destination_parent_escapes(self):
        # Second, independent defence: even if the enumerator handed these entries
        # over, the copier must not write through a link it just created.
        base, source, victim = self.escaping_repo()
        packet = base / "pk"
        entries = [
            {"path": "data", "kind": "symlink", "mode": 0o755, "sha256": "0" * 64},
            {"path": "data/file", "kind": "file", "mode": 0o644, "sha256": "1" * 64},
            {"path": "main.py", "kind": "file", "mode": 0o644, "sha256": "2" * 64},
        ]
        with patch("hb_eval_review.materialize.iter_packet_entries", return_value=entries):
            with self.assertRaises(PacketPolicyError) as caught:
                materialize_source_packet(source, packet)
        self.assertEqual("PACKET_PATH_UNSAFE", caught.exception.code)
        self.assertIn("data/file", caught.exception.paths)
        self.assertEqual("ORIGINAL CONTENT\n", victim.read_text())
        self.assertFalse((packet / "source").exists())


class PacketSecretPolicyTests(MaterializeTestCase):
    def test_secret_material_fails_closed_before_any_copy(self):
        cases = {
            "dotenv": ".env",
            "dotenv_variant": ".env.local",
            "dotenv_example": ".env.example",
            "keystore_jks": "release.jks",
            "keystore": "upload.keystore",
            "pkcs12": "key.p12",
            "pfx": "key.pfx",
            "pem": "cert.pem",
            "private_key": "id.key",
            "secrets_dir": "secrets/db.txt",
            "local_properties": "local.properties",
        }
        for name, relative in cases.items():
            with self.subTest(case=name):
                base, source = self.make_repo()
                (source / "src").mkdir()
                (source / "src" / "main.py").write_text("print(1)\n")
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("password=hunter2\n")
                self.commit(source)
                packet = base / "packet"
                with self.assertRaises(PacketPolicyError) as caught:
                    materialize_source_packet(source, packet)
                self.assertEqual("PACKET_SECRET_MATERIAL_PRESENT", caught.exception.code)
                self.assertIn(relative, caught.exception.paths)
                self.assertNotIn("hunter2", str(caught.exception))
                self.assertFalse((packet / "source").exists())

    def test_secret_material_matching_is_case_insensitive(self):
        cases = {
            "dotenv_upper": ".ENV",
            "dotenv_variant_mixed": "app/.Env.local",
            "keystore_jks_upper": "RELEASE.JKS",
            "pem_mixed": "Cert.PEM",
            "secrets_dir_capitalized": "Secrets/db.txt",
        }
        for name, relative in cases.items():
            with self.subTest(case=name):
                base, source = self.make_repo()
                (source / "src").mkdir()
                (source / "src" / "main.py").write_text("print(1)\n")
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("password=hunter2\n")
                self.commit(source)
                packet = base / "packet"
                with self.assertRaises(PacketPolicyError) as caught:
                    materialize_source_packet(source, packet)
                self.assertEqual("PACKET_SECRET_MATERIAL_PRESENT", caught.exception.code)
                self.assertIn(relative, caught.exception.paths)
                self.assertNotIn("hunter2", str(caught.exception))
                self.assertFalse((packet / "source").exists())

    def test_ignored_and_cache_paths_are_not_materialized(self):
        base, source = self.make_repo()
        (source / ".gitignore").write_text(".env\nnode_modules/\n")
        (source / "src").mkdir()
        (source / "src" / "main.py").write_text("print(1)\n")
        (source / ".env").write_text("password=hunter2\n")
        (source / "node_modules").mkdir()
        (source / "node_modules" / "pkg.js").write_text("x")
        gate = source / ".harness" / "artifacts" / "x"
        (gate / "eval-review").mkdir(parents=True)
        (gate / "eval-review" / "gate.json").write_text("{}")
        (gate / "gate-result.json").write_text("{}")
        self.commit(source)
        (source / "build").mkdir()
        (source / "build" / "out.o").write_text("o")
        (source / ".gradle").mkdir()
        (source / ".gradle" / "c").write_text("c")
        (source / "__pycache__").mkdir()
        (source / "__pycache__" / "m.pyc").write_text("p")

        manifest = materialize_source_packet(source, base / "packet")
        paths = {entry["path"] for entry in manifest["materialized"]["entries"]}
        self.assertIn("src/main.py", paths)
        self.assertIn(".harness/artifacts/x/gate-result.json", paths)
        for absent in (
            ".env", "node_modules/pkg.js", "build/out.o", ".gradle/c",
            "__pycache__/m.pyc", ".harness/artifacts/x/eval-review/gate.json",
        ):
            self.assertNotIn(absent, paths)
        self.assertFalse((base / "packet" / "source" / ".env").exists())


class SymlinkModePortabilityTests(MaterializeTestCase):
    """A symlink's own mode is platform noise; the packet identity must not carry it."""

    def linked_repo(self):
        base, source = self.make_repo()
        (source / "main.py").write_text("print(1)\n")
        os.symlink("main.py", str(source / "link.py"))
        self.commit(source)
        return base, source

    def test_a_tracked_symlink_materializes_under_a_restrictive_umask(self):
        base, source = self.linked_repo()
        previous = os.umask(0o077)
        self.addCleanup(os.umask, previous)
        manifest = materialize_source_packet(source, base / "pk")
        self.assertTrue(verify_materialized_packet(base / "pk", manifest))

    def test_a_symlink_entry_carries_link_text_but_no_mode(self):
        base, source = self.linked_repo()
        manifest = materialize_source_packet(source, base / "pk")
        links = [
            entry for entry in manifest["materialized"]["entries"]
            if entry["kind"] == "symlink"
        ]
        self.assertEqual(1, len(links))
        self.assertIsNone(links[0]["mode"])
        self.assertEqual(hashlib.sha256(b"main.py").hexdigest(), links[0]["sha256"])

    def test_materializing_never_changes_the_mode_of_a_link_target(self):
        base, source = self.linked_repo()
        os.chmod(str(source / "main.py"), 0o640)
        previous = os.umask(0o077)
        self.addCleanup(os.umask, previous)
        materialize_source_packet(source, base / "pk")
        self.assertEqual(0o640, stat.S_IMODE(os.lstat(str(source / "main.py")).st_mode))


if __name__ == "__main__":
    unittest.main()
