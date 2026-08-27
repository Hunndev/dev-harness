import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review.materialize import materialize_source_packet, remove_materialized_packet, verify_materialized_packet


class MaterializeTests(unittest.TestCase):
    def test_materialized_source_is_content_verified_and_symlink_safe(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = base / "source"
            packet = base / "packet"
            source.mkdir()
            (source / "normal.txt").write_text("hello")
            (source / "space 이름.txt").write_text("world")
            (source / "link").symlink_to("normal.txt")
            (source / ".git").mkdir()
            (source / ".git/config").write_text("private metadata")
            manifest = materialize_source_packet(source, packet)
            self.assertTrue(verify_materialized_packet(packet, manifest))
            self.assertFalse((packet / "source/.git").exists())
            self.assertTrue((packet / "source" / "link").is_symlink())
            self.assertEqual("normal.txt", (packet / "source" / "link").readlink().as_posix())

    def test_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = base / "source"
            packet = base / "packet"
            source.mkdir(); (source / "a.txt").write_text("a")
            manifest = materialize_source_packet(source, packet)
            (packet / "source" / "a.txt").chmod(0o600)
            (packet / "source" / "a.txt").write_text("tampered")
            self.assertFalse(verify_materialized_packet(packet, manifest))

    def test_read_only_packet_has_explicit_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"; packet = root / "packet"
            source.mkdir(); (source / "a.txt").write_text("a")
            materialize_source_packet(source, packet)
            remove_materialized_packet(packet)
            self.assertFalse(packet.exists())


if __name__ == "__main__":
    unittest.main()
