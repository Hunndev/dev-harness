# -*- coding: utf-8 -*-
"""Documentation contract for the iOS (hb-ios) command documents (dev-28).

The iOS documents were derived from the Android ones and kept Gradle/JUnit
forms that xcodebuild does not accept (``--tests "*Foo*"``, ``--dry-run``,
``--version``), plus JDK/jacoco/OkHttp/Robolectric wording. These tests pin
the corrected xcodebuild forms so the drift cannot come back, and pin the
Jest version statement in the CM/CHAT/FE TDD documents (the
``--testPathPattern`` -> ``--testPathPatterns`` rename happened in Jest 30).
"""
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
IOS_COMMANDS = REPO / "IOS" / "commands"

PREFLIGHT_DOCS = [
    "shared/tdd.md",
    "feature/auto.md",
    "feature/deep.md",
    "maintenance/auto.md",
    "maintenance/deep.md",
    "maintenance/hotfix.md",
]
SELECTOR_DOCS = PREFLIGHT_DOCS + [
    "shared/verify.md",
    "feature/reflect.md",
    "maintenance/reproduce.md",
]
LINT_POLICY_DOCS = [
    "shared/verify.md",
    "feature/auto.md",
    "feature/deep.md",
    "feature/reflect.md",
    "maintenance/auto.md",
    "maintenance/deep.md",
]
JEST_DOCS = [
    "CM/commands/shared/tdd.md",
    "CHAT/commands/shared/tdd.md",
    "FE/commands/shared/tdd.md",
]

# Gradle / JUnit / Android forms that must not appear in any iOS command document.
FORBIDDEN = [
    ("Gradle --dry-run flag", re.compile(r"--dry-run")),
    ("Gradle --version flag on xcodebuild", re.compile(r"xcodebuild --version")),
    ("Gradle --tests wildcard filter", re.compile(r'--tests\s+"\*')),
    ("Gradle --tests option", re.compile(r"(?<![\w-])--tests(?![\w-])")),
    ("jacoco coverage", re.compile(r"jacoco", re.IGNORECASE)),
    ("JDK wording", re.compile(r"\bJDK\b")),
    ("OkHttp test harness", re.compile(r"OkHttp", re.IGNORECASE)),
    ("android.* package", re.compile(r"android\.\*|\bandroid\.[a-z]")),
    ("Robolectric", re.compile(r"Robolectric", re.IGNORECASE)),
    ("Gradle assembleDebug task", re.compile(r"assembleDebug")),
    ("Kotlin not-null assertion", re.compile(r"`!!`")),
    ("Kotlin @Suppress", re.compile(r"@Suppress\b")),
    ("duplicated build line labelled as lint", re.compile(r"\(iOS Lint\)")),
    ("build command repeated on one line", re.compile(
        r"xcodebuild -scheme bucclapp build[^\n]*xcodebuild -scheme bucclapp build")),
    ("pipe to tail hides the xcodebuild exit code", re.compile(
        r"xcodebuild[^\n]*\|\s*tail\s+(?:-\d+|-n\s*\d+)\s*>")),
]
PIPE_TO_TAIL = FORBIDDEN[-1][1]

# XCTest-only executed-count wording must not come back into the track documents; the
# framework-neutral rule lives in shared/tdd.md (Swift Testing prints "Executed 0 tests" too).
FORBIDDEN_OUTSIDE_TDD = [
    ("XCTest-only executed-count criterion", re.compile(r"`Executed N tests`의 N")),
    ("XCTest-only zero-executed criterion", re.compile(r"`Executed N tests`가 0")),
    ("XCTest-only report template", re.compile(r"\(Executed N tests, N ≥ 1\)")),
]
PREFLIGHT_ENUMERATE = re.compile(r"xcodebuild[^\n`]*-scheme bucclapp[^\n`]*\btest\b[^\n`]*-enumerate-tests")
PREFLIGHT_VERSION = re.compile(r"xcodebuild(?: [^\n`]*)? -version\b")

XCRESULT_PER_ATTEMPT = re.compile(r"-resultBundlePath\s+\S*[{<]attempt[}>]/test\.xcresult")
XCODEBUILD_HELP_FLAGS = (
    "-enumerate-tests",
    "-only-testing",
    "-resultBundlePath",
    "-enableCodeCoverage",
    "-version",
)


def ios_docs():
    return sorted(IOS_COMMANDS.rglob("*.md"))


def read(path):
    return Path(path).read_text(encoding="utf-8")


class ForbiddenFormsTests(unittest.TestCase):
    def test_ios_command_docs_exist(self):
        self.assertGreaterEqual(len(ios_docs()), 9)

    def test_no_gradle_or_android_forms_in_ios_docs(self):
        offenders = []
        for path in ios_docs():
            for number, line in enumerate(read(path).splitlines(), 1):
                for label, pattern in FORBIDDEN:
                    if pattern.search(line):
                        offenders.append("%s:%d [%s] %s" % (
                            path.relative_to(REPO), number, label, line.strip()))
        self.assertEqual(offenders, [], "\n" + "\n".join(offenders))

    def test_pipe_to_tail_pattern_catches_every_tail_spelling(self):
        # Codex v3 review: the v2 pattern lost the plain `tail -30` spelling.
        for bad in ('xcodebuild -scheme bucclapp test | tail -30 > out.txt',
                    'xcodebuild -scheme bucclapp test 2>&1 | tail -n 30 > out.txt',
                    'xcodebuild -scheme bucclapp test 2>&1 |tail -n30 > out.txt'):
            with self.subTest(line=bad):
                self.assertIsNotNone(PIPE_TO_TAIL.search(bad))
        for good in ('tail -30 {artifacts-dir}/xcodebuild-red.log > {artifacts-dir}/tdd-baseline-log.txt',
                     'xcodebuild -scheme bucclapp test > {artifacts-dir}/xcodebuild-red.log 2>&1; echo "xcodebuild exit=$?" >> {artifacts-dir}/xcodebuild-red.log'):
            with self.subTest(line=good):
                self.assertIsNone(PIPE_TO_TAIL.search(good))

    def test_track_docs_do_not_restate_the_xctest_only_criterion(self):
        offenders = []
        for path in ios_docs():
            if path.relative_to(IOS_COMMANDS).as_posix() == "shared/tdd.md":
                continue
            for number, line in enumerate(read(path).splitlines(), 1):
                for label, pattern in FORBIDDEN_OUTSIDE_TDD:
                    if pattern.search(line):
                        offenders.append("%s:%d [%s] %s" % (
                            path.relative_to(REPO), number, label, line.strip()))
        self.assertEqual(offenders, [], "\n" + "\n".join(offenders))


class RequiredFormsTests(unittest.TestCase):
    def test_preflight_uses_enumerate_tests_and_dash_version(self):
        # Regexes, not literal commands: a document may add -project/-destination later.
        for rel in PREFLIGHT_DOCS:
            text = read(IOS_COMMANDS / rel)
            with self.subTest(doc=rel):
                self.assertRegex(text, PREFLIGHT_ENUMERATE)
                self.assertRegex(text, PREFLIGHT_VERSION)

    def test_target_tests_use_only_testing_identifier(self):
        for rel in SELECTOR_DOCS:
            text = read(IOS_COMMANDS / rel)
            with self.subTest(doc=rel):
                self.assertIn("-only-testing:bucclappTests/", text)

    def test_tdd_doc_explains_zero_executed_tests(self):
        text = read(IOS_COMMANDS / "shared/tdd.md")
        self.assertIn("실행 수 판정 규칙", text)
        self.assertRegex(text, r"Executed N tests")          # XCTest summary line
        self.assertRegex(text, r"Test run with N tests")     # Swift Testing summary line
        self.assertIn("-enumerate-tests", text)
        self.assertNotIn("와일드카드 패턴을 사용한다", text)

    def test_tdd_doc_saves_full_log_before_tail(self):
        text = read(IOS_COMMANDS / "shared/tdd.md")
        self.assertRegex(text, r"tail -30 [^\n|]*\.log[^\n|]* > [^\n]*tdd-baseline-log\.txt")
        self.assertRegex(text, r"tail -30 [^\n|]*\.log[^\n|]* > [^\n]*tdd-green-log\.txt")

    def test_artifact_trees_list_the_full_xcodebuild_logs(self):
        # tdd.md makes Red/Green write the full output next to the tail files;
        # every track's artifact tree must list both so the convention stays in one piece.
        for rel in ("shared/tdd.md", "feature/auto.md", "feature/deep.md",
                    "maintenance/auto.md", "maintenance/deep.md", "maintenance/hotfix.md"):
            text = read(IOS_COMMANDS / rel)
            with self.subTest(doc=rel):
                self.assertIn("xcodebuild-red.log", text)
                self.assertIn("xcodebuild-green.log", text)

    def test_coverage_uses_xcresult_per_attempt_and_xccov(self):
        for rel in ("shared/verify.md", "maintenance/deep.md"):
            text = read(IOS_COMMANDS / rel)
            with self.subTest(doc=rel):
                self.assertIn("-enableCodeCoverage YES", text)
                self.assertRegex(text, XCRESULT_PER_ATTEMPT)
                self.assertIn("xcrun xccov view --report", text)

    def test_lint_policy_names_swiftlint_and_na(self):
        for rel in LINT_POLICY_DOCS:
            text = read(IOS_COMMANDS / rel)
            with self.subTest(doc=rel):
                self.assertIn("SwiftLint", text)
        verify = read(IOS_COMMANDS / "shared/verify.md")
        self.assertIn("swiftlint lint", verify)
        self.assertRegex(verify, r"N/A")
        self.assertRegex(verify, r"PASS로 (기록|적)지 않는다")


class JestVersionStatementTests(unittest.TestCase):
    def test_plural_flag_is_attributed_to_jest_30(self):
        for rel in JEST_DOCS:
            text = read(REPO / rel)
            with self.subTest(doc=rel):
                self.assertRegex(text, r"Jest 30 이상[^\n]*--testPathPatterns")
                self.assertRegex(text, r"Jest 29 이하[^\n]*--testPathPattern=")
                for wrong in (r"Jest 29 이상", r"Jest 29\+", r"Jest 28 이하", r"Jest 28-"):
                    self.assertIsNone(re.search(wrong, text), "%s still says %r" % (rel, wrong))


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("xcodebuild"),
                     "macOS xcodebuild required")
class XcodebuildHelpTests(unittest.TestCase):
    def test_help_lists_the_flags_the_docs_rely_on(self):
        proc = subprocess.run(["xcodebuild", "-help"], capture_output=True, text=True, timeout=120)
        # Xcode 26.5 prints the usage text on stderr with exit 0; older versions used stdout.
        usage = proc.stdout + proc.stderr
        if proc.returncode != 0 and "requires Xcode" in usage:
            # Command Line Tools only: /usr/bin/xcodebuild is a shim without Xcode behind it.
            self.skipTest("full Xcode required")
        self.assertEqual(proc.returncode, 0, usage[-2000:])
        for flag in XCODEBUILD_HELP_FLAGS:
            self.assertIn(flag, usage)


if __name__ == "__main__":
    unittest.main()
