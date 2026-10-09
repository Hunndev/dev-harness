"""hb 프로그램의 테스트.

상황마다 임시 git 저장소에 작은 가짜 제품을 만들고, 진짜 pytest로 검사를 돌린다.
실행: <테스트 환경의 python> -m unittest discover -s tests -v   (pytest가 깔린 파이썬이어야 함)
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HB = os.environ.get("HB_PATH") or os.path.join(HERE, "..", "bin", "hb.py")
WORK = "w1"
WORK_DIR = ".harness/artifacts/work/" + WORK

CHECKS = {
    "version": 1,
    "runner": "pytest",
    "full_args": ["-q"],
    "timeout_seconds": 120,
    "test_globs": ["test_*.py", "conftest.py"],
}
TASK = {
    "id": "01",
    "title": "빼기 기능",
    "kind": "feature",
    "criteria": ["C1"],
    "allowed_files": ["app.py", "tests/test_new.py"],
    "check_args": ["tests/test_new.py"],
}
NEW_TEST = """
    from app import sub

    def test_sub():
        assert sub(5, 3) == 2
"""
APP_WITH_SUB_STUB = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return None\n"
APP_WITH_SUB = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"


@unittest.skipUnless(importlib.util.find_spec("pytest"), "pytest가 깔린 파이썬으로 돌려야 함")
class HbCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="hb-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.write(".gitignore", "logs/\n__pycache__/\n.pytest_cache/\n")
        self.write("conftest.py", "")
        self.write("app.py", "def add(a, b):\n    return a + b\n")
        self.write("tests/test_app.py", "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n")
        self.write(".harness/docs/checks.json", json.dumps(CHECKS))
        self.write_tasks(TASK)
        self.commit("start")

    # --- 도우미 ---
    def git(self, *args):
        r = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(text))

    def write_tasks(self, *tasks):
        self.write(WORK_DIR + "/tasks.json", json.dumps({"work": WORK, "tasks": list(tasks)}, ensure_ascii=False))

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def hb(self, *args):
        r = subprocess.run([sys.executable, HB, "--repo", self.root, *args], capture_output=True, text=True)
        try:
            out = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            self.fail("hb가 판정을 내지 않음: rc=%s out=%r err=%r" % (r.returncode, r.stdout[-300:], r.stderr[-300:]))
        return r.returncode, out

    def state(self):
        with open(os.path.join(self.root, WORK_DIR, "state.json"), encoding="utf-8") as f:
            return json.load(f)

    def baseline(self):
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertEqual(out["verdict"], "ok", out)
        return out

    def red(self):
        """테스트를 먼저 쓰고(빈 뼈대 포함) 실패 확인을 받는다."""
        self.write("tests/test_new.py", NEW_TEST)
        self.write("app.py", APP_WITH_SUB_STUB)
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")
        self.assertEqual(out["verdict"], "ok", out)
        return out

    def green(self):
        self.write("app.py", APP_WITH_SUB)
        return self.hb("check", "--work", WORK, "--task", "01", "--phase", "green")

    # --- 정상 흐름 ---
    def test_happy_path_red_green_done(self):
        self.baseline()
        self.red()
        rc, out = self.green()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertIn("새로 깨진 것 없음", out["summary"])
        self.git("add", "app.py", "tests/test_new.py")
        rc, out = self.hb("done", "--work", WORK, "--task", "01")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertTrue(self.state()["tasks"]["01"]["done"])

    # --- 계획서의 상황 아홉 ---
    def test_1_zero_tests_executed_is_not_run(self):
        self.baseline()
        self.write_tasks(dict(TASK, check_args=["tests/test_app.py", "-k", "no_such_test_anywhere"]))
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)

    def test_2_import_error_is_not_accepted_as_red(self):
        self.baseline()
        self.write("tests/test_new.py", "from app import sub\n\n\ndef test_sub():\n    assert sub(5, 3) == 2\n")
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("준비 단계", out["reason"])

    def test_3_all_skipped_is_not_accepted(self):
        self.baseline()
        self.write("tests/test_new.py", "import pytest\n\n\n@pytest.mark.skip(reason='나중에')\ndef test_sub():\n    assert False\n")
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("건너뜀", out["reason"])

    def test_4_green_stops_when_test_file_changed_after_red(self):
        self.baseline()
        self.red()
        self.write("tests/test_new.py", "from app import sub\n\n\ndef test_sub():\n    assert sub(5, 3) is not None\n")
        rc, out = self.green()
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("테스트가 바뀜", out["reason"])

    def test_5_baseline_broken_tests_are_recorded_and_not_counted_as_new(self):
        self.write("tests/test_old.py", """
            import unittest


            class OldTest(unittest.TestCase):
                def test_broken_with_subtests(self):
                    for i in (1, 2):
                        with self.subTest(i=i):
                            self.assertEqual(i, 1)


            def test_plain_broken():
                assert 1 == 2
        """)
        self.commit("old broken tests")
        self.baseline()
        broken = self.state()["baseline"]["broken"]
        self.assertEqual(sorted(broken), [
            "tests.test_old.OldTest::test_broken_with_subtests",
            "tests.test_old::test_plain_broken",
        ])
        self.red()
        rc, out = self.green()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertIn("새로 깨진 것 없음", out["summary"])
        self.assertIn("원래 깨져 있던 것 2건", out["summary"])
        self.assertNotIn("전체 통과", out["summary"])

    def _old_broken_in_the_same_selection(self):
        """할 일의 확인 명령이 고르는 범위 안에 원래 깨져 있던 테스트가 들어 있는 상황."""
        self.write("tests/test_old.py", "def test_plain_broken():\n    assert 1 == 2\n")
        self.commit("old broken test")
        self.write_tasks(dict(TASK, check_args=["tests/test_old.py", "tests/test_new.py"]))
        self.commit("확인 명령이 옛 테스트 파일도 고름")
        self.baseline()

    def test_red_does_not_count_baseline_broken_tests_as_this_tasks_failures(self):
        self._old_broken_in_the_same_selection()
        out = self.red()
        self.assertEqual(out["failed"], ["tests.test_new::test_sub"])
        rc, out = self.green()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertIn("원래 깨져 있던 것 1건", out["summary"])

    def test_red_is_not_accepted_when_only_baseline_broken_tests_fail(self):
        self._old_broken_in_the_same_selection()
        self.write("tests/test_new.py", NEW_TEST)
        self.write("app.py", APP_WITH_SUB)
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("실패한 테스트가 없음", out["reason"])

    def test_6_green_stops_when_implementation_breaks_another_test(self):
        self.baseline()
        self.red()
        self.write("app.py", "def add(a, b):\n    return a - b\n\n\ndef sub(a, b):\n    return a - b\n")
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "green")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("tests.test_app::test_add", out["new_broken"])

    def test_7_green_stops_when_file_outside_allowed_changed(self):
        self.baseline()
        self.red()
        self.write("other.py", "X = 1\n")
        rc, out = self.green()
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("other.py", out["outside"])

    def test_8_stale_report_is_not_reused_when_run_produces_none(self):
        self.baseline()
        self.red()  # 이 실행의 보고서가 logs/에 남아 있다
        self.write_tasks(dict(TASK, check_args=["tests/test_new.py", "--no-such-pytest-option"]))
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)

    def test_9_done_refuses_when_other_file_is_staged(self):
        self.baseline()
        self.red()
        rc, out = self.green()
        self.assertEqual(out["verdict"], "ok", out)
        self.write("notes.txt", "사용자가 하던 메모\n")
        self.git("add", "app.py", "tests/test_new.py", "notes.txt")
        rc, out = self.hb("done", "--work", WORK, "--task", "01")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("notes.txt", json.dumps(out, ensure_ascii=False))
        self.assertFalse(self.state()["tasks"]["01"].get("done"))

    # --- 완료가 "통과한 그 코드"만 받는지 ---
    def test_done_refuses_when_code_changed_after_green(self):
        self.baseline()
        self.red()
        self.green()
        self.write("app.py", APP_WITH_SUB + "\n# 통과 확인 뒤에 고침\n")
        self.git("add", "app.py", "tests/test_new.py")
        rc, out = self.hb("done", "--work", WORK, "--task", "01")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)

    def test_done_refuses_when_a_changed_file_is_not_staged(self):
        self.baseline()
        self.red()
        self.green()
        self.git("add", "tests/test_new.py")
        rc, out = self.hb("done", "--work", WORK, "--task", "01")
        self.assertNotEqual(rc, 0)
        self.assertIn("app.py", out["not_staged"])

    # --- 순서와 전제 ---
    def test_green_requires_accepted_red(self):
        self.baseline()
        self.write("tests/test_new.py", NEW_TEST)
        rc, out = self.green()
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("실패 확인", out["reason"])

    def test_green_stops_when_someone_committed_after_red(self):
        self.baseline()
        self.red()
        self.write("app.py", APP_WITH_SUB)
        self.commit("구현자가 제멋대로 커밋")
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "green")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("커밋", out["reason"])

    def test_red_is_not_accepted_when_test_already_passes(self):
        self.baseline()
        self.write("tests/test_new.py", NEW_TEST)
        self.write("app.py", APP_WITH_SUB)
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)

    def test_baseline_refuses_dirty_tree(self):
        self.write("app.py", "def add(a, b):\n    return a + b  # 사용자가 고치던 중\n")
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("app.py", out["dirty"])

    def test_baseline_stops_when_logs_are_not_ignored(self):
        self.write(".gitignore", "__pycache__/\n.pytest_cache/\n")
        self.commit("logs 제외를 뺌")
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertNotEqual(rc, 0)
        self.assertIn("logs", out["reason"])

    def test_missing_contract_key_stops_before_running(self):
        self.write(".harness/docs/checks.json", json.dumps({k: v for k, v in CHECKS.items() if k != "full_args"}))
        self.commit("계약에서 전체 검사 명령을 뺌")
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("full_args", out["reason"])
        self.assertFalse(os.path.exists(os.path.join(self.root, WORK_DIR, "logs")))

    def test_timeout_is_recorded_separately(self):
        self.write(".harness/docs/checks.json", json.dumps(dict(CHECKS, timeout_seconds=1)))
        self.write("tests/test_slow.py", "import time\n\n\ndef test_slow():\n    time.sleep(8)\n")
        self.commit("느린 테스트")
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "timeout", out)

    # --- 기록에 남기는 것 ---
    def test_committed_records_keep_failure_messages_out(self):
        self.write("tests/test_old.py", "def test_leaky():\n    assert 'MARKER_IN_MESSAGE_93417' == ''\n")
        self.commit("메시지에 표지가 든 깨진 테스트")
        self.baseline()
        work = os.path.join(self.root, WORK_DIR)
        kept = [os.path.join(work, "state.json")]
        kept += [os.path.join(work, "checks", f) for f in os.listdir(os.path.join(work, "checks"))]
        self.assertGreaterEqual(len(kept), 2)
        for path in kept:
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertNotIn("MARKER_IN_MESSAGE_93417", text, path)
            self.assertNotIn(self.root, text, path)


class ParseReport(unittest.TestCase):
    def test_counts_test_entries_by_name_not_the_suite_total(self):
        """보고서의 합계 숫자(tests=9105)가 아니라 테스트 항목을 이름으로 읽는다."""
        spec = importlib.util.spec_from_file_location("hb", HB)
        hb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hb)
        d = tempfile.mkdtemp(prefix="hb-test-")
        self.addCleanup(shutil.rmtree, d, True)
        path = os.path.join(d, "junit.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent("""\
                <?xml version="1.0" encoding="utf-8"?>
                <testsuites><testsuite name="pytest" tests="9105" failures="1" errors="0" skipped="1">
                <testcase classname="a.test_x" name="test_ok"/>
                <testcase classname="a.test_x" name="test_bad"><failure message="AssertionError: 1 != 2">x</failure></testcase>
                <testcase classname="a.test_x" name="test_skip"><skipped message="later"/></testcase>
                </testsuite></testsuites>
            """))
        cases = hb.parse_junit(path)
        self.assertEqual(sorted((c[0], c[1]) for c in cases), [
            ("a.test_x::test_bad", "failure"),
            ("a.test_x::test_ok", "passed"),
            ("a.test_x::test_skip", "skipped"),
        ])


if __name__ == "__main__":
    unittest.main()
