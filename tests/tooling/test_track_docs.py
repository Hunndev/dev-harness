# -*- coding: utf-8 -*-
"""Documentation contract for check-log reuse (D4) and runtime artifact names (dev-10a).

The 24 track documents used to say "reuse the previous check log when HEAD is the
same".  HEAD does not see uncommitted changes, so that rule could reuse a log taken
from different code.  The runtime already binds source content (``source_snapshot_id``,
snapshot.py) and excludes ``.harness/artifacts/**/eval-review/**`` from that binding,
which is the only place a reuse record can be written without invalidating itself.
These tests pin the corrected wording in every copy and prove the exclusion with a
real repository fixture.  They also pin the artifact names of ``hb-eval-review run``
in the shared Evaluate/Review documents and the lint rule that keeps them honest.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGINS = ("BE", "CM", "FE", "CHAT", "AOS", "IOS")
TRACK_DOCS = [
    REPO / plugin / "commands" / track / (tier + ".md")
    for plugin in PLUGINS
    for track in ("feature", "maintenance")
    for tier in ("auto", "deep")
]
TDD_DOCS = [REPO / plugin / "commands" / "shared" / "tdd.md" for plugin in PLUGINS]
CLAUDE_DOCS = [REPO / plugin / "CLAUDE.md" for plugin in PLUGINS]
SHARED_DOCS = [REPO / "SHARED" / "commands" / "evaluate.md", REPO / "SHARED" / "commands" / "review.md"] + [
    REPO / plugin / "commands" / "shared" / name for plugin in PLUGINS for name in ("evaluate.md", "review.md")
]
README = REPO / "README.md"
LINT = REPO / "scripts" / "lint-harness.sh"

POLICY_TITLE = "검사 로그 재사용 정책"
POLICY_HEADING = "## " + POLICY_TITLE
REUSE_RECORD = "`eval-review/qa-snapshot.json`"
BIN = "`<플러그인 설치 경로>/bin/hb-eval-review snapshot <작업 트리>`"
RETIRED_ARTIFACT_NAMES = (
    "execution-envelope.<",
    "execution-envelope.evaluate.",
    "execution-envelope.review.",
    "-join-result.json",
    "evaluate-result.claude.json",
    "evaluate-result.codex.json",
    "review-result.claude.json",
    "review-result.codex.json",
)


def read(path):
    return path.read_text(encoding="utf-8")


def section(text, heading, stop_prefix="\n## "):
    """Return the body of a markdown section from *heading* to the next section."""
    start = text.find("\n" + heading + "\n")
    if start < 0:
        return None
    body_start = start + len(heading) + 2
    end = text.find(stop_prefix, body_start)
    return text[body_start:end if end >= 0 else len(text)]


class ReuseRuleWordingTests(unittest.TestCase):
    def test_track_documents_no_longer_reuse_logs_by_head(self):
        for path in TRACK_DOCS:
            text = read(path)
            self.assertNotIn("같은 HEAD", text, path)
            self.assertNotIn("검사 시점 HEAD", text, path)

    def test_each_track_document_states_the_reuse_rule_once(self):
        required = (
            "기본 재사용 금지",
            "`reuse: allowed`",
            BIN,
            "`source_snapshot_id`",
            "argv",
            "cwd",
            "selection",
            "toolchain",
            "Gate",
            "쓰기 전에",
            REUSE_RECORD,
            "snapshot 제외 경로",
            "`INDEX.md`에는 완료 절에서 1회만",
            "`commands/shared/tdd.md`",
            POLICY_TITLE,
        )
        for path in TRACK_DOCS:
            line = self.reuse_sentence(path)
            for phrase in required:
                self.assertIn(phrase, line, (path, phrase))
            # The blind provider stage never writes the record; the parent Gate does.
            self.assertNotIn("[R1]", line, path)

    @staticmethod
    def reuse_sentence(path):
        lead = "> **이 QA = " if path.parent.name == "feature" else "> **이 회귀 = "
        lines = [line for line in read(path).splitlines() if line.startswith(lead)]
        assert len(lines) == 1, (path, len(lines))
        return lines[0]

    def test_review_step_compares_or_records_the_reuse_key(self):
        """The review step (where the Gate runs) says when to compare and when to record, and who does it."""
        for path in TRACK_DOCS:
            lines = [line for line in read(path).splitlines() if line.startswith("> **이 리뷰 = mandatory dual Review의 stack lens**")]
            self.assertEqual(1, len(lines), (path, len(lines)))
            line = lines[0]
            for phrase in ("코드 수정이 끝난 뒤 산출물을 쓰기 전에 재사용 키를 비교", "로그를 다 쓴 뒤 마지막에", REUSE_RECORD, POLICY_TITLE, "blind provider"):
                self.assertIn(phrase, line, (path, phrase))

    def test_completion_section_records_the_snapshot_id_once(self):
        for path in TRACK_DOCS:
            text = read(path)
            completion = section(text, "### 완료")
            self.assertIsNotNone(completion, path)
            self.assertIn("`source_snapshot_id`", completion, path)
            self.assertIn(REUSE_RECORD, completion, path)
            self.assertIn("1회만", completion, path)
            # Before the completion section, INDEX.md is named only by the reuse sentence
            # (which says "완료 절에서 1회"); no step writes it mid-track any more.
            before = text.split("\n### 완료\n", 1)[0]
            mentions = [line for line in before.splitlines() if "INDEX.md" in line]
            self.assertEqual([self.reuse_sentence(path)], mentions, path)


class ReusePolicySectionTests(unittest.TestCase):
    def test_tdd_reuse_policy_section_identical_across_six(self):
        sections = {}
        for path in TDD_DOCS:
            body = section(read(path), POLICY_HEADING)
            self.assertIsNotNone(body, path)
            sections[path] = body
        distinct = set(sections.values())
        self.assertEqual(1, len(distinct), "the reuse policy must be byte-identical in all six tdd.md")
        body = distinct.pop()
        for phrase in (
            "기본 재사용 금지",
            "selection",
            "설치 상태·환경변수",
            "`.harness/docs/check-reuse.yaml`",
            "`reuse: allowed`",
            BIN,
            "`source_snapshot_id`",
            "argv",
            "cwd",
            "selection",
            "선택 범위",
            "toolchain",
            "stdout 첫 줄",
            REUSE_RECORD,
            "snapshot 계산에서 제외",
            "`INDEX.md`",
            "완료 절에서 1회",
            "영구히 0회",
            "reuse_decision",
            "output root",
            "run-<n>",
            "worktree",
            "fork",
            "blind provider",
            "코드 수정",
            "통째로 ignore",
        ):
            self.assertIn(phrase, body, phrase)
        self.assertNotIn("같은 HEAD", body)

    def test_every_tdd_document_forbids_unproven_reuse(self):
        for path in TDD_DOCS:
            forbidden = section(read(path), "## 금지 사항")
            self.assertIsNotNone(forbidden, path)
            self.assertIn("재사용 키", forbidden, path)
            self.assertIn(POLICY_TITLE, forbidden, path)


class MethodologyWordingTests(unittest.TestCase):
    def test_claude_md_states_qa_is_reverification_after_review(self):
        for path in CLAUDE_DOCS:
            text = read(path)
            self.assertNotIn("리뷰 스텝 뒤에 올 수 있다", text, path)
            self.assertIn("리뷰 반영 후의 재검증", text, path)
            self.assertIn(POLICY_TITLE, text, path)

    def test_readme_says_gates_are_mandatory_and_defines_shadow(self):
        status_lines = [line for line in read(README).splitlines() if "Shadow 및 설치 전" in line]
        self.assertEqual(1, len(status_lines))
        self.assertIn("생략 불가", status_lines[0])
        self.assertIn("승격되기 전", status_lines[0])


class SnapshotRecordLocationTests(unittest.TestCase):
    """Prove the location rule with the real snapshot function, not by reading docs."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO / "SHARED" / "runtime"))
        from hb_eval_review.snapshot import compute_source_snapshot

        cls.snapshot = staticmethod(compute_source_snapshot)

    def make_repo(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(root)], check=False))
        repo = root / "repo"
        repo.mkdir()
        git = ["git", "-c", "init.defaultBranch=main", "-c", "user.name=Test", "-c", "user.email=test@example.invalid"]
        subprocess.run(git + ["init", "-q"], cwd=repo, check=True)
        (repo / "tracked.txt").write_text("v1\n")
        subprocess.run(git + ["add", "tracked.txt"], cwd=repo, check=True)
        subprocess.run(git + ["commit", "-qm", "init"], cwd=repo, check=True)
        return repo

    def identity(self, repo):
        return self.snapshot(repo)["source_snapshot_id"]

    def test_recording_snapshot_into_excluded_path_keeps_snapshot_stable(self):
        repo = self.make_repo()
        before = self.identity(repo)
        record = repo / ".harness" / "artifacts" / "feature" / "x" / "eval-review" / "qa-snapshot.json"
        record.parent.mkdir(parents=True)
        record.write_text('{"reuse_key": {"source_snapshot_id": "%s"}}\n' % before)
        self.assertEqual(before, self.identity(repo))
        # Control group (Codex v2 reproduction): the same value written to INDEX.md,
        # one level up, changes the snapshot and would make every later comparison fail.
        index = record.parents[1] / "INDEX.md"
        index.write_text("source_snapshot_id: %s\n" % before)
        self.assertNotEqual(before, self.identity(repo))

    def test_check_logs_beside_index_md_change_the_snapshot_so_record_after_writing_them(self):
        repo = self.make_repo()
        before = self.identity(repo)
        log = repo / ".harness" / "artifacts" / "feature" / "x" / "tdd-green-log.txt"
        log.parent.mkdir(parents=True)
        log.write_text("PASS\n")
        self.assertNotEqual(before, self.identity(repo))


class AllowlistTests(unittest.TestCase):
    def test_reuse_is_off_when_allowlist_empty(self):
        """Documentation contract: the runtime does not read the allowlist. This pins the rule text
        ("no file / empty checks → no candidates") and that no allowlist ships with the harness."""
        body = section(read(TDD_DOCS[0]), POLICY_HEADING)
        self.assertIn("파일이 없거나 `checks`가 비어 있으면 후보가 없다", body)
        self.assertIn("`reuse: allowed`로 표시된 검사만 후보", body)
        # The harness ships no allowlist and no repository has declared one: reuse is off.
        self.assertEqual([], [path for path in REPO.rglob("check-reuse.yaml") if ".git" not in path.parts])


class ArtifactNameTests(unittest.TestCase):
    def test_shared_documents_list_no_retired_artifact_names(self):
        for path in SHARED_DOCS:
            text = read(path)
            for name in RETIRED_ARTIFACT_NAMES:
                self.assertNotIn(name, text, (path, name))
            for name in ("execution-manifest.json", "materialized-packet/", "final-result.json", "sealed-results/"):
                self.assertIn(name, text, (path, name))
            self.assertNotIn("README 예시는", text, path)

    def test_readme_run_example_uses_a_fresh_external_directory_and_copies_reports(self):
        """`eval-review/` holds qa-snapshot.json, and `run` refuses a non-empty output root (cli.py)."""
        lines = [line for line in read(README).splitlines() if "--output-root" in line]
        self.assertEqual(1, len(lines))
        self.assertIn("${HB_EVAL_REVIEW_HOME:-~/.hb-eval-review}/<repo-slug>/<id>/run-<n>/", lines[0])
        self.assertIn("저장소 밖", lines[0])
        self.assertIn(".harness/artifacts/<track>/<id>/eval-review/run-<n>/", read(README))
        self.assertIn("실제 사본", read(README))
        self.assertIn("run-<n>", read(README))

    def test_readme_tree_reports_the_current_test_counts(self):
        lines = [line for line in read(README).splitlines() if "tests/" in line and "eval_review" in line]
        self.assertEqual(1, len(lines))
        self.assertIn("eval_review 352", lines[0])
        self.assertIn("tooling 57", lines[0])

    def test_shared_documents_describe_the_envelope_as_a_field_of_the_sealed_file(self):
        for path in SHARED_DOCS:
            text = read(path)
            self.assertIn("`sealed-results/{stage}-{engine}.json`", text, path)
            self.assertIn("`envelope` 필드", text, path)
            self.assertNotIn("두 파일이 모두 있어야", text, path)


class LintRuleTests(unittest.TestCase):
    def test_lint_r14_runs_the_output_contract_tests(self):
        text = read(LINT)
        self.assertIn("#   R14.", text)
        self.assertIn(
            "python3 -m unittest discover -s tests/eval_review -p 'test_cli.py' -k OutputContract", text
        )
        self.assertIn("python3 -m unittest discover -s tests/tooling -p 'test_track_docs.py'", text)
        self.assertIn("(R1~R14)", text)
        self.assertNotIn("(R1~R13)", text)
        readme = read(README)
        self.assertIn("R1~R14", readme)
        self.assertNotIn("R1~R13", readme)

    def test_lint_r6_knows_the_reuse_allowlist_file(self):
        r6 = [line for line in read(LINT).splitlines() if line.startswith("R6_YAMLS=")]
        self.assertEqual(1, len(r6))
        self.assertIn("check-reuse", r6[0])


if __name__ == "__main__":
    unittest.main()
