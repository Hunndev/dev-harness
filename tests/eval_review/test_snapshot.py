import json
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review.materialize import materialize_source_packet
from hb_eval_review.snapshot import (
    PacketPolicyError,
    compute_evidence_bundle_id,
    compute_packet_id,
    compute_source_snapshot,
    iter_packet_entries,
    validate_packet_bindings,
)


class SnapshotTests(unittest.TestCase):
    def make_repo(self):
        td = tempfile.TemporaryDirectory()
        repo = Path(td.name)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        (repo / "tracked.txt").write_text("one\n")
        subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
        return td, repo

    def test_untracked_content_changes_snapshot(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        before = compute_source_snapshot(repo)["source_snapshot_id"]
        (repo / "new file.txt").write_text("new\n")
        after = compute_source_snapshot(repo)["source_snapshot_id"]
        self.assertNotEqual(before, after)

    def test_staged_and_unstaged_changes_are_bound(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        base = compute_source_snapshot(repo)["source_snapshot_id"]
        (repo / "tracked.txt").write_text("two\n")
        unstaged = compute_source_snapshot(repo)["source_snapshot_id"]
        subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
        staged = compute_source_snapshot(repo)["source_snapshot_id"]
        self.assertNotEqual(base, unstaged)
        self.assertNotEqual(unstaged, staged)

    def test_generated_eval_results_do_not_self_invalidate(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        out = repo / ".harness" / "artifacts" / "x" / "eval-review"
        out.mkdir(parents=True)
        before = compute_source_snapshot(repo)["source_snapshot_id"]
        (out / "evaluate-result.json").write_text("{}")
        after = compute_source_snapshot(repo)["source_snapshot_id"]
        self.assertEqual(before, after)

    def test_snapshot_and_materialize_share_one_byte_set(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        (repo / "src").mkdir()
        (repo / "src" / "main.py").write_text("print(1)\n")
        (repo / "link").symlink_to("tracked.txt")
        (repo / ".gitignore").write_text("ignored.txt\n")
        (repo / "ignored.txt").write_text("ignored\n")
        (repo / "untracked.txt").write_text("untracked\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "more"], cwd=repo, check=True)
        packet = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(str(packet), ignore_errors=True))
        manifest = materialize_source_packet(repo, packet / "packet")
        snapshot = {
            (entry["path"], entry["kind"], entry["sha256"])
            for entry in compute_source_snapshot(repo)["manifest"]["files"]
        }
        materialized = {
            (entry["path"], entry["kind"], entry["sha256"])
            for entry in manifest["materialized"]["entries"]
        }
        self.assertEqual(snapshot, materialized)
        self.assertIn(("src/main.py", "file", hashlib.sha256(b"print(1)\n").hexdigest()), snapshot)
        self.assertNotIn("ignored.txt", {path for path, _, _ in snapshot})

    def test_files_named_like_cache_directories_stay_in_the_packet(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        for relative in ("scripts/build", "tools/target", "lib/dist"):
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("#!/bin/sh\necho hi\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "cache-named files"], cwd=repo, check=True)
        (repo / "node_modules").mkdir()
        (repo / "node_modules" / "pkg.js").write_text("x")

        before = compute_source_snapshot(repo)
        paths = {entry["path"] for entry in before["manifest"]["files"]}
        self.assertLessEqual({"scripts/build", "tools/target", "lib/dist"}, paths)
        self.assertNotIn("node_modules/pkg.js", paths)

        (repo / "scripts" / "build").write_text("#!/bin/sh\necho changed\n")
        after = compute_source_snapshot(repo)["source_snapshot_id"]
        self.assertNotEqual(before["source_snapshot_id"], after)

    def test_tracked_sources_under_cache_named_directories_stay_in_the_packet(self):
        # The cache deny-list exists to drop machine-local build output. A tracked
        # file is part of the change under review no matter which directory holds it.
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        tracked = ("dist/index.js", "tools/build/release.sh", "src/target/Model.kt")
        for relative in tracked:
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("source content\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "tracked cache-named sources"], cwd=repo, check=True)
        (repo / "dist" / "generated.js").write_text("machine output\n")
        (repo / "node_modules").mkdir()
        (repo / "node_modules" / "pkg.js").write_text("x")

        before = compute_source_snapshot(repo)
        paths = {entry["path"] for entry in before["manifest"]["files"]}
        self.assertLessEqual(set(tracked), paths)
        self.assertNotIn("dist/generated.js", paths)
        self.assertNotIn("node_modules/pkg.js", paths)

        (repo / "dist" / "index.js").write_text("edited source\n")
        self.assertNotEqual(
            before["source_snapshot_id"], compute_source_snapshot(repo)["source_snapshot_id"]
        )

    def test_tracked_cache_named_sources_reach_the_materialized_packet(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        (repo / "dist").mkdir()
        (repo / "dist" / "index.js").write_text("source content\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "tracked dist"], cwd=repo, check=True)
        (repo / "dist" / "generated.js").write_text("machine output\n")
        packet = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(str(packet), ignore_errors=True))
        manifest = materialize_source_packet(repo, packet / "packet")
        paths = {entry["path"] for entry in manifest["materialized"]["entries"]}
        self.assertIn("dist/index.js", paths)
        self.assertNotIn("dist/generated.js", paths)

    def test_symlinked_parent_component_is_refused_before_any_copy(self):
        # A stale index entry under a directory that has become a symlink would let
        # the copier write through that link; the enumerator refuses it outright.
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        (repo / "data").mkdir()
        (repo / "data" / "file").write_text("tracked payload\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "data dir"], cwd=repo, check=True)
        __import__("shutil").rmtree(str(repo / "data"))
        (repo / "outside").mkdir()
        (repo / "outside" / "file").write_text("other content\n")
        (repo / "data").symlink_to("outside")

        with self.assertRaises(PacketPolicyError) as caught:
            iter_packet_entries(repo)
        self.assertEqual("PACKET_PATH_UNSAFE", caught.exception.code)
        self.assertIn("data/file", caught.exception.paths)
        self.assertNotIn("tracked payload", str(caught.exception))
        with self.assertRaises(PacketPolicyError):
            compute_source_snapshot(repo)

    def test_ignored_files_do_not_affect_the_snapshot(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        (repo / ".gitignore").write_text("secret-notes.txt\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "ignore"], cwd=repo, check=True)
        before = compute_source_snapshot(repo)["source_snapshot_id"]
        (repo / "secret-notes.txt").write_text("changed\n")
        self.assertEqual(before, compute_source_snapshot(repo)["source_snapshot_id"])

    def test_tracked_secret_blocks_the_snapshot(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        (repo / ".env").write_text("password=hunter2\n")
        subprocess.run(["git", "add", ".env"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "secret"], cwd=repo, check=True)
        with self.assertRaises(PacketPolicyError) as caught:
            compute_source_snapshot(repo)
        self.assertEqual("PACKET_SECRET_MATERIAL_PRESENT", caught.exception.code)
        errors = validate_packet_bindings(
            {"packet_id": "p" * 64, "source_snapshot_id": "s" * 64,
             "evidence_bundle_id": "e" * 64, "request": {}, "evidence_entries": []},
            repo,
        )
        self.assertIn("PACKET_SECRET_MATERIAL_PRESENT", errors)
        self.assertNotIn("SOURCE_SNAPSHOT_UNAVAILABLE", errors)

    def test_a_secret_named_directory_component_blocks_the_snapshot(self):
        """R4-03: the deny rules are a fail-closed barrier, not a leaf-name convention."""
        cases = {
            "env_suffix_directory": ".env.local/credentials.txt",
            "pem_directory": "certs.pem/server.txt",
            "key_directory": "release.key/notes.txt",
            "uppercase_env_directory": ".ENV.Local/creds.txt",
            "uppercase_pem_directory": "Certs.PEM/server.txt",
            "bare_env_directory": ".env/value.txt",
            "local_properties_directory": "local.properties/gradle.txt",
            "nested_deeper": "app/certs.p12/inner/leaf.txt",
        }
        for name, relative in cases.items():
            with self.subTest(case=name):
                td, repo = self.make_repo()
                self.addCleanup(td.cleanup)
                target = repo / relative
                target.parent.mkdir(parents=True)
                target.write_text("password=hunter2\n")
                subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
                subprocess.run(["git", "commit", "-qm", "secret"], cwd=repo, check=True)
                with self.assertRaises(PacketPolicyError) as caught:
                    compute_source_snapshot(repo)
                self.assertEqual("PACKET_SECRET_MATERIAL_PRESENT", caught.exception.code)
                self.assertIn(relative, caught.exception.paths)

    def test_a_component_that_is_itself_a_secret_suffix_blocks_the_snapshot(self):
        """E4: the deny list names the suffix, and a hidden file's whole name is one.

        `os.path.splitext(".pem")` reports no extension at all, so a component named
        exactly `.pem` — a file, or the directory a credential sits in — passed a rule
        written to refuse `.pem` everywhere. Same six suffixes as before; no new pattern.
        """
        cases = {
            "hidden_pem_file": ".pem",
            "hidden_key_file": ".key",
            "hidden_keystore_file": ".keystore",
            "hidden_p12_file": ".p12",
            "hidden_pfx_file": ".pfx",
            "hidden_jks_file": ".jks",
            "uppercase_hidden_pem": ".PEM",
            "hidden_pem_under_a_directory": "config/.pem",
            "hidden_pem_directory": ".pem/notes.txt",
            "hidden_key_directory_nested": "app/.key/inner/leaf.txt",
        }
        for name, relative in cases.items():
            with self.subTest(case=name):
                td, repo = self.make_repo()
                self.addCleanup(td.cleanup)
                target = repo / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("password=hunter2\n")
                subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
                with self.assertRaises(PacketPolicyError) as caught:
                    compute_source_snapshot(repo)
                self.assertEqual("PACKET_SECRET_MATERIAL_PRESENT", caught.exception.code)
                self.assertIn(relative, caught.exception.paths)

    def test_a_component_with_extra_leading_dots_blocks_the_snapshot(self):
        """E4/F4: the rule is the suffix, and extra leading dots do not remove it.

        `os.path.splitext("..pem")` reports no extension, and `"..pem"` is not the bare
        suffix either, so a name with one dot too many walked past both halves of the
        check while `x.pem` and `.pem` were refused. Real repositories hold these files:
        `..pem`, `...p12` and `dir/..PEM/x` were created on disk and reached both the
        snapshot and the materialized packet. Same six suffixes, same case folding.
        """
        cases = {
            "double_dot_pem": "..pem",
            "triple_dot_p12": "...p12",
            "double_dot_key": "..key",
            "double_dot_jks": "..jks",
            "double_dot_keystore": "..keystore",
            "double_dot_pfx": "..pfx",
            "uppercase_double_dot_pem_directory": "dir/..PEM/x",
            "uppercase_multi_dot_p12_directory": "app/...P12/inner/leaf.txt",
            "multi_dot_leaf_under_a_directory": "config/..key",
        }
        for name, relative in cases.items():
            with self.subTest(case=name):
                td, repo = self.make_repo()
                self.addCleanup(td.cleanup)
                target = repo / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("password=hunter2\n")
                subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
                with self.assertRaises(PacketPolicyError) as caught:
                    compute_source_snapshot(repo)
                self.assertEqual("PACKET_SECRET_MATERIAL_PRESENT", caught.exception.code)
                self.assertIn(relative, caught.exception.paths)

    def test_names_that_are_not_the_denied_suffixes_still_enter_the_packet(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        for relative in ("dir/x.txt", "pem/readme.md", "key/notes.txt", ".pemx/leaf.txt",
                         "keystore.md", ".env-sample/readme.md"):
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("clean\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        paths = {entry["path"] for entry in iter_packet_entries(repo)}
        for relative in ("dir/x.txt", "pem/readme.md", "key/notes.txt", ".pemx/leaf.txt",
                         "keystore.md", ".env-sample/readme.md"):
            self.assertIn(relative, paths)

    def test_near_misses_of_the_multi_dot_rule_still_enter_the_packet(self):
        """The suffix has to end the component; carrying it in the middle is not a match."""
        controls = (
            "..pemx/leaf.txt",
            "..keystorex.md",
            "notes..pem.txt",
            "..p12-notes.md",
            "dir/...pfxy/readme.md",
            "..secrets-review.md",
        )
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        for relative in controls:
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("clean\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        paths = {entry["path"] for entry in iter_packet_entries(repo)}
        for relative in controls:
            self.assertIn(relative, paths)

    def test_the_materialized_packet_refuses_the_same_component_rule(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        target = repo / ".env.local" / "credentials.txt"
        target.parent.mkdir(parents=True)
        target.write_text("password=hunter2\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        with tempfile.TemporaryDirectory() as out:
            with self.assertRaises(PacketPolicyError) as caught:
                materialize_source_packet(repo, Path(out) / "packet")
        self.assertEqual("PACKET_SECRET_MATERIAL_PRESENT", caught.exception.code)

    def test_ordinary_paths_that_only_look_similar_still_enter_the_packet(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        for relative in (
            "docs/environment/setup.md",
            "src/keyboard/index.js",
            "certificates/readme.md",
            "app/secretsmanager/client.py",
        ):
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("clean\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        paths = {entry["path"] for entry in iter_packet_entries(repo)}
        self.assertIn("docs/environment/setup.md", paths)
        self.assertIn("src/keyboard/index.js", paths)
        self.assertIn("certificates/readme.md", paths)
        self.assertIn("app/secretsmanager/client.py", paths)

    def test_evidence_and_packet_ids_change_with_inputs(self):
        e1 = compute_evidence_bundle_id([{"command": "pytest", "exit_code": 0, "sha256": "a" * 64}])
        e2 = compute_evidence_bundle_id([{"command": "pytest", "exit_code": 1, "sha256": "a" * 64}])
        self.assertNotEqual(e1, e2)
        p1 = compute_packet_id({"request": "x", "acceptance": ["A"]}, "s" * 64, e1)
        p2 = compute_packet_id({"request": "x", "acceptance": ["B"]}, "s" * 64, e1)
        self.assertNotEqual(p1, p2)

    def bound_packet(self, repo):
        evidence = repo / ".harness" / "artifacts" / "x" / "eval-review" / "gate.txt"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("gate pass\n")
        entries = [{
            "path": evidence.relative_to(repo).as_posix(),
            "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        }]
        source_id = compute_source_snapshot(repo)["source_snapshot_id"]
        evidence_id = compute_evidence_bundle_id(entries)
        request = {"text": "review this change", "acceptance_refs": ["tracked.txt"]}
        return {
            "packet_id": compute_packet_id(request, source_id, evidence_id),
            "source_snapshot_id": source_id,
            "evidence_bundle_id": evidence_id,
            "request": request,
            "evidence_entries": entries,
        }

    def test_packet_bindings_are_recomputed_from_source_and_evidence(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        packet = self.bound_packet(repo)
        self.assertEqual([], validate_packet_bindings(packet, repo))

        (repo / "tracked.txt").write_text("tampered\n")
        self.assertIn("SOURCE_SNAPSHOT_MISMATCH", validate_packet_bindings(packet, repo))

    def test_evidence_and_request_tampering_are_rejected(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        packet = self.bound_packet(repo)
        evidence = repo / packet["evidence_entries"][0]["path"]
        evidence.write_text("fabricated pass\n")
        self.assertIn("EVIDENCE_ENTRY_MISMATCH", validate_packet_bindings(packet, repo))

        evidence.write_text("gate pass\n")
        packet["request"] = {"text": "changed request"}
        self.assertIn("PACKET_ID_MISMATCH", validate_packet_bindings(packet, repo))


class GitlinkPacketTests(unittest.TestCase):
    """A gitlink is a nested repository, and the enumerator can only read files.

    `git ls-files` reports the gitlink under its own path, but the working-tree entry is
    a directory, so the "file or symlink" filter dropped it without a word: every byte
    inside the nested repository, and every later edit to it, left the source snapshot
    byte-for-byte identical. Recursing into submodules is out of scope, so the packet
    refuses the layout instead of pretending to have covered it.
    """

    def git(self, repo, *args):
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout.decode().strip()

    def commit(self, repo, message):
        self.git(
            repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "commit", "-qm", message,
        )

    def make_repo(self):
        td = tempfile.TemporaryDirectory()
        repo = Path(td.name)
        self.addCleanup(td.cleanup)
        self.git(repo, "init", "-q")
        (repo / "tracked.txt").write_text("one\n")
        self.git(repo, "add", "tracked.txt")
        self.commit(repo, "init")
        return repo

    def add_gitlink(self, repo, name="module"):
        """Record a real initialized nested repository at `name`, exactly as git does."""
        child = repo / name
        child.mkdir()
        self.git(child, "init", "-q")
        (child / "source.py").write_text("BASE = 0\n")
        self.git(child, "add", "source.py")
        self.commit(child, "fixture")
        sha = self.git(child, "rev-parse", "HEAD")
        self.git(repo, "update-index", "--add", "--cacheinfo", "160000,{},{}".format(sha, name))
        self.commit(repo, "record gitlink")
        return child

    def assert_refused(self, repo, path="module"):
        with self.assertRaises(PacketPolicyError) as caught:
            iter_packet_entries(repo)
        self.assertEqual("PACKET_GITLINK_UNSUPPORTED", caught.exception.code)
        self.assertIn(path, caught.exception.paths)
        with self.assertRaises(PacketPolicyError) as sealed:
            compute_source_snapshot(repo)
        self.assertEqual("PACKET_GITLINK_UNSUPPORTED", sealed.exception.code)

    def test_an_unchanged_initialized_gitlink_is_refused(self):
        repo = self.make_repo()
        self.add_gitlink(repo)
        self.assert_refused(repo)

    def test_a_dirty_gitlink_can_never_snapshot_as_unchanged_content(self):
        repo = self.make_repo()
        child = self.add_gitlink(repo)
        (child / "source.py").write_text("BASE = 1\n")
        self.assert_refused(repo)
        # The defect was two different working trees agreeing on one snapshot id; with
        # the refusal neither side can produce an id to agree on.
        (child / "source.py").write_text("BASE = 2\n")
        self.assert_refused(repo)

    def test_an_uninitialized_gitlink_is_refused(self):
        repo = self.make_repo()
        child = self.add_gitlink(repo)
        shutil.rmtree(str(child))
        self.assert_refused(repo)

    def test_a_gitlink_under_a_subdirectory_is_refused_under_its_own_path(self):
        repo = self.make_repo()
        (repo / "vendor").mkdir()
        self.add_gitlink(repo, "vendor/dependency")
        self.assert_refused(repo, "vendor/dependency")

    def test_packet_bindings_report_the_gitlink_instead_of_a_recomputed_id(self):
        repo = self.make_repo()
        self.add_gitlink(repo)
        errors = validate_packet_bindings(
            {"packet_id": "p" * 64, "source_snapshot_id": "s" * 64,
             "evidence_bundle_id": "e" * 64, "request": {}, "evidence_entries": []},
            repo,
        )
        self.assertIn("PACKET_GITLINK_UNSUPPORTED", errors)

    def test_the_materialized_packet_refuses_the_same_layout(self):
        repo = self.make_repo()
        self.add_gitlink(repo)
        with tempfile.TemporaryDirectory() as out:
            with self.assertRaises(PacketPolicyError) as caught:
                materialize_source_packet(repo, Path(out) / "packet")
        self.assertEqual("PACKET_GITLINK_UNSUPPORTED", caught.exception.code)

    def test_an_untracked_embedded_repository_is_refused(self):
        """The same boundary, reached without an index entry.

        An inner repository that was never `git add`-ed has no gitlink; `git ls-files
        --others` reports it as the single name `nested/`, which is a directory, so the
        file/symlink filter dropped it. Two different inner working trees then produced
        one identical `compute_source_snapshot` result.
        """
        repo = self.make_repo()
        inner = repo / "nested"
        inner.mkdir()
        self.git(inner, "init", "-q")
        (inner / "source.py").write_text("BASE = 0\n")
        self.git(inner, "add", "source.py")
        self.commit(inner, "fixture")
        with self.assertRaises(PacketPolicyError) as caught:
            iter_packet_entries(repo)
        self.assertEqual("PACKET_EMBEDDED_REPOSITORY_UNSUPPORTED", caught.exception.code)
        self.assertIn("nested", caught.exception.paths)
        with self.assertRaises(PacketPolicyError):
            compute_source_snapshot(repo)
        (inner / "source.py").write_text("BASE = 1\n")
        with self.assertRaises(PacketPolicyError):
            compute_source_snapshot(repo)

    def test_an_untracked_embedded_repository_is_reported_by_packet_bindings(self):
        repo = self.make_repo()
        inner = repo / "nested"
        inner.mkdir()
        self.git(inner, "init", "-q")
        (inner / "source.py").write_text("BASE = 0\n")
        self.git(inner, "add", "source.py")
        self.commit(inner, "fixture")
        errors = validate_packet_bindings(
            {"packet_id": "p" * 64, "source_snapshot_id": "s" * 64,
             "evidence_bundle_id": "e" * 64, "request": {}, "evidence_entries": []},
            repo,
        )
        self.assertIn("PACKET_EMBEDDED_REPOSITORY_UNSUPPORTED", errors)
        self.assertNotIn("SOURCE_SNAPSHOT_UNAVAILABLE", errors)

    def test_an_ignored_embedded_repository_never_reaches_the_packet(self):
        # Gitignored content is out of the packet by policy, so it is not a boundary the
        # enumerator has to refuse; the snapshot must still be computable.
        repo = self.make_repo()
        (repo / ".gitignore").write_text("vendor/\n")
        self.git(repo, "add", ".gitignore")
        self.commit(repo, "ignore vendor")
        inner = repo / "vendor" / "dependency"
        inner.mkdir(parents=True)
        self.git(inner, "init", "-q")
        (inner / "source.py").write_text("BASE = 0\n")
        self.git(inner, "add", "source.py")
        self.commit(inner, "fixture")
        paths = {entry["path"] for entry in iter_packet_entries(repo)}
        self.assertIn("tracked.txt", paths)
        self.assertNotIn("vendor/dependency", paths)

    def test_an_ordinary_nested_directory_of_files_still_enters_the_packet(self):
        repo = self.make_repo()
        nested = repo / "module"
        nested.mkdir()
        (nested / "source.py").write_text("BASE = 0\n")
        self.git(repo, "add", "-A")
        paths = {entry["path"] for entry in iter_packet_entries(repo)}
        self.assertIn("module/source.py", paths)
        before = compute_source_snapshot(repo)["source_snapshot_id"]
        (nested / "source.py").write_text("BASE = 1\n")
        self.assertNotEqual(before, compute_source_snapshot(repo)["source_snapshot_id"])


if __name__ == "__main__":
    unittest.main()
