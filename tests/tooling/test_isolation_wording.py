"""dev-13 acceptance test: shared docs describe the real isolation contract in the canonical file and all six copies."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ("BE", "CM", "FE", "CHAT", "AOS", "IOS")


def documents():
    yield ROOT / "SHARED" / "commands" / "evaluate.md"
    yield ROOT / "SHARED" / "commands" / "review.md"
    for plugin in PLUGINS:
        yield ROOT / plugin / "commands" / "shared" / "evaluate.md"
        yield ROOT / plugin / "commands" / "shared" / "review.md"


class IsolationWordingTests(unittest.TestCase):
    def test_no_document_promises_a_read_only_container(self) -> None:
        for path in documents():
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("read-only container", text, path)

    def test_every_document_states_the_isolation_unavailable_contract(self) -> None:
        for path in documents():
            text = path.read_text(encoding="utf-8")
            self.assertIn("ISOLATION_UNAVAILABLE", text, path)
            self.assertIn("sandbox-exec", text, path)


if __name__ == "__main__":
    unittest.main()
