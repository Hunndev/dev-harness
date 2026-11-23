"""실패 확인 기록 보존(red_history)과 검사 기록의 이름·결과 목록(cases) 테스트.

test_hb.py처럼 임시 git 저장소에 작은 가짜 제품을 만들고 진짜 pytest로 검사를 돌린다.
- C1: 실패 확인을 다시 받으면 앞 기록이 tasks.<번호>.red_history 끝에 값 그대로 남고, 판정은 지금과 같다.
      멈추는 갈래에서는 상태 파일이 바뀌지 않는다.
- C2: 모든 checks/*.json에 cases([[이름, 결과], ...])가 있고, 보고서를 따로 읽은 결과와 맞으며, 기존 칸은 그대로다.
실행: <테스트 환경의 python> -m pytest tests/test_hb_red_history.py   (pytest가 깔린 파이썬이어야 함)
"""
import copy
import glob
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

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
    "id": "01", "title": "빼기", "kind": "feature", "criteria": ["C1"],
    "allowed_files": ["app.py", "tests/test_new.py"], "check_args": ["tests/test_new.py"],
}
BASE_APP = "def add(a, b):\n    return a + b\n"
APP_WITH_SUB_STUB = BASE_APP + "\n\ndef sub(a, b):\n    return None\n"
APP_WITH_SUB = BASE_APP + "\n\ndef sub(a, b):\n    return a - b\n"

# 실패 확인을 한 번, 두 번, 세 번 받을 때마다 실패하는 테스트가 하나씩 늘어난다.
NEW_TEST_1 = "from app import sub\n\n\ndef test_sub():\n    assert sub(5, 3) == 2\n"
NEW_TEST_2 = NEW_TEST_1 + "\n\ndef test_sub_negative():\n    assert sub(3, 5) == -2\n"
NEW_TEST_3 = NEW_TEST_2 + "\n\ndef test_sub_zero():\n    assert sub(0, 0) == 0\n"

RECORD_KEYS = {"label", "runner", "args", "ran", "exit_code", "total", "counts", "broken", "report",
               "log_sha256", "head", "seconds", "at"}
KINDS = ("passed", "skipped", "failure", "error")
RANK = {k: i for i, k in enumerate(KINDS)}


def junit_cases(path):
    """JUnit 보고서를 hb와 따로 읽어 {이름: 결과}로 낸다. 같은 이름이면 나쁜 쪽을 남긴다."""
    found = {}
    for c in ET.parse(path).getroot().iter("testcase"):
        tid = "%s::%s" % (c.get("classname", ""), c.get("name", ""))
        kind = "passed"
        for ch in c:
            if ch.tag in RANK and RANK[ch.tag] > RANK[kind]:
                kind = ch.tag
        if tid not in found or RANK[kind] > RANK[found[tid]]:
            found[tid] = kind
    return found


@unittest.skipUnless(importlib.util.find_spec("pytest"), "pytest가 깔린 파이썬으로 돌려야 함")
class RedHistoryBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="hb-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.write(".gitignore", "logs/\n__pycache__/\n.pytest_cache/\n")
        self.write("conftest.py", "")
        self.write("app.py", BASE_APP)
        self.write("tests/test_app.py", "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n")
        # 바탕 검사에 통과, 실패, 건너뜀이 모두 들어가도록
        self.write("tests/test_old.py", "def test_old_broken():\n    assert 1 == 2\n")
        self.write("tests/test_skip.py",
                   "import pytest\n\n\n@pytest.mark.skip(reason='later')\ndef test_later():\n    assert False\n")
        self.write(".harness/docs/checks.json", json.dumps(CHECKS))
        self.write_tasks(TASK)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "start")

    # --- 도우미 ---
    def git(self, *args):
        r = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def write_tasks(self, *tasks):
        self.write(WORK_DIR + "/tasks.json", json.dumps({"work": WORK, "tasks": list(tasks)}, ensure_ascii=False))

    def hb(self, *args):
        # 크기가 같은 변경이 같은 초에 쓰이면 옛 .pyc가 쓰여 깨진 동작이 가려지므로 바이트코드를 쓰지 않는다.
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, HB, "--repo", self.root, *args], capture_output=True, text=True, env=env)
        try:
            out = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            self.fail("hb가 판정을 내지 않음: rc=%s out=%r err=%r" % (r.returncode, r.stdout[-300:], r.stderr[-300:]))
        return r.returncode, out

    def state_path(self):
        return os.path.join(self.root, WORK_DIR, "state.json")

    def state(self):
        with open(self.state_path(), encoding="utf-8") as f:
            return json.load(f)

    def state_bytes(self):
        with open(self.state_path(), "rb") as f:
            return f.read()

    def entry(self):
        return self.state()["tasks"]["01"]

    def head(self):
        return self.git("rev-parse", "HEAD").strip()

    def baseline(self):
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        return out

    def red_cmd(self):
        return self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")

    def red(self, test_text):
        self.write("tests/test_new.py", test_text)
        self.write("app.py", APP_WITH_SUB_STUB)
        rc, out = self.red_cmd()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        return out

    def read_record(self, rel):
        return self.read_json(os.path.join(self.root, WORK_DIR, rel))

    @staticmethod
    def read_json(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)


class RedHistoryTest(RedHistoryBase):
    """C1."""

    def assert_red_verdict_shape(self, rc, out, failed, record):
        """판정 꼴이 지금과 같다: verdict, failed, record, summary 네 칸."""
        self.assertEqual(rc, 0, out)
        self.assertEqual(set(out), {"verdict", "failed", "record", "summary"}, out)
        self.assertEqual(out["verdict"], "ok")
        self.assertEqual(out["failed"], failed)
        self.assertEqual(out["record"], record)
        self.assertEqual(out["summary"], "실패 확인 됨. 본문에서 실패한 테스트 %d개" % len(failed))

    def assert_red_entry(self, red, out):
        self.assertEqual(red["ok"], True)
        self.assertEqual(red["head"], self.head())
        self.assertEqual(red["failed"], out["failed"])
        self.assertEqual(red["record"], out["record"])
        self.assertIn("test_fp", red)
        self.assertIn("at", red)

    def two_reds(self):
        """실패 확인을 두 번 받은 상태를 만든다. 역사가 하나인 것을 먼저 확인한다."""
        self.baseline()
        self.red(NEW_TEST_1)
        first = copy.deepcopy(self.entry()["red"])
        self.red(NEW_TEST_2)
        entry = self.entry()
        self.assertEqual(entry.get("red_history"), [first], "두 번 받은 뒤 앞 기록이 red_history에 하나 있어야 함")
        return first

    def test_single_red_has_no_history(self):
        self.baseline()
        out = self.red(NEW_TEST_1)
        entry = self.entry()
        self.assertEqual(entry.get("red_history") or [], [])
        self.assert_red_entry(entry["red"], out)

    def test_second_red_keeps_first_record_in_history(self):
        self.baseline()
        self.red(NEW_TEST_1)
        first = copy.deepcopy(self.entry()["red"])
        self.write("tests/test_new.py", NEW_TEST_2)
        rc, out = self.red_cmd()
        self.assert_red_verdict_shape(
            rc, out, ["tests.test_new::test_sub", "tests.test_new::test_sub_negative"], "checks/003-01-red.json")
        entry = self.entry()
        self.assertEqual(entry.get("red_history"), [first])
        self.assertEqual(first["failed"], ["tests.test_new::test_sub"])
        self.assertEqual(first["record"], "checks/002-01-red.json")
        self.assert_red_entry(entry["red"], out)
        self.assertNotEqual(entry["red"]["test_fp"], first["test_fp"])

    def test_third_red_appends_in_order(self):
        self.baseline()
        self.red(NEW_TEST_1)
        first = copy.deepcopy(self.entry()["red"])
        self.red(NEW_TEST_2)
        second = copy.deepcopy(self.entry()["red"])
        self.write("tests/test_new.py", NEW_TEST_3)
        rc, out = self.red_cmd()
        self.assert_red_verdict_shape(rc, out, [
            "tests.test_new::test_sub", "tests.test_new::test_sub_negative", "tests.test_new::test_sub_zero",
        ], "checks/004-01-red.json")
        entry = self.entry()
        self.assertEqual(entry.get("red_history"), [first, second])
        self.assertEqual([h["record"] for h in entry["red_history"]],
                         ["checks/002-01-red.json", "checks/003-01-red.json"])
        self.assert_red_entry(entry["red"], out)

    def test_history_is_per_task(self):
        other = dict(TASK, id="02", allowed_files=["app.py", "tests/test_other.py"],
                     check_args=["tests/test_other.py"])
        self.write_tasks(TASK, other)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "할 일 둘")
        first = self.two_reds()
        self.write("tests/test_other.py", "def test_other():\n    assert False\n")
        rc, out = self.hb("check", "--work", WORK, "--task", "02", "--phase", "red")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        state = self.state()
        self.assertEqual(state["tasks"]["02"].get("red_history") or [], [])
        self.assertEqual(state["tasks"]["01"]["red_history"], [first])

    def test_red_after_done_keeps_history_and_drops_green_and_done(self):
        """실패 확인 -> 통과 확인 -> 완료 뒤에 실패 확인을 다시 받는다.
        항목은 red와 red_history만 남고, 구현을 되살려도 done은 통과 확인 기록이 없다며 멈춘다."""
        self.baseline()
        self.red(NEW_TEST_1)
        first = copy.deepcopy(self.entry()["red"])
        self.write("app.py", APP_WITH_SUB)
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "green")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.git("add", "app.py", "tests/test_new.py")
        rc, out = self.hb("done", "--work", WORK, "--task", "01")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertIn("green", self.entry())
        self.assertIn("done", self.entry())
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "01 완료")

        # 테스트를 고치고 구현을 빼 둔 뒤 실패 확인을 다시 받는다
        self.write("tests/test_new.py", NEW_TEST_2)
        self.write("app.py", APP_WITH_SUB_STUB)
        rc, out = self.red_cmd()
        self.assert_red_verdict_shape(
            rc, out, ["tests.test_new::test_sub", "tests.test_new::test_sub_negative"], "checks/005-01-red.json")
        entry = self.entry()
        self.assertEqual(entry.get("red_history"), [first])
        self.assertEqual(entry["red_history"][-1], first)
        self.assertEqual(set(entry), {"red", "red_history"}, entry)
        self.assert_red_entry(entry["red"], out)

        # 구현을 되살려 올려도 통과 확인 없이 완료로 갈 수 없다. 멈추면 상태도 그대로다.
        self.write("app.py", APP_WITH_SUB)
        self.git("add", "app.py", "tests/test_new.py")
        before = self.state_bytes()
        rc, out = self.hb("done", "--work", WORK, "--task", "01")
        self.assertEqual(rc, 1, out)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("통과 확인 기록이 없음", out["reason"])
        self.assertEqual(self.state_bytes(), before)
        self.assertEqual(set(self.entry()), {"red", "red_history"})

    # --- 멈추는 갈래: 상태 파일이 바이트 그대로 ---
    def assert_stop_keeps_state(self, expect_verdict, reason_part):
        before = self.state_bytes()
        rc, out = self.red_cmd()
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(out["verdict"], expect_verdict, out)
        if reason_part:
            self.assertIn(reason_part, out["reason"])
        self.assertEqual(self.state_bytes(), before)

    def test_stop_no_failed_tests_keeps_state(self):
        self.two_reds()
        self.write("app.py", APP_WITH_SUB)
        self.assert_stop_keeps_state("stop", "실패한 테스트가 없음")

    def test_stop_collection_error_keeps_state(self):
        self.two_reds()
        self.write("tests/test_new.py", "import no_such_module_anywhere\n\n\ndef test_sub():\n    assert False\n")
        self.assert_stop_keeps_state("stop", "준비 단계")

    def test_stop_import_error_in_body_keeps_state(self):
        self.two_reds()
        self.write("tests/test_new.py", "def test_sub():\n    from app import no_such_name\n")
        self.assert_stop_keeps_state("stop", "가져오기나 문법 오류")

    def test_stop_all_skipped_keeps_state(self):
        self.two_reds()
        self.write("tests/test_new.py",
                   "import pytest\n\n\n@pytest.mark.skip(reason='later')\ndef test_sub():\n    assert False\n")
        self.assert_stop_keeps_state("stop", "건너뜀")

    def test_not_run_keeps_state(self):
        self.two_reds()
        self.write_tasks(dict(TASK, check_args=["tests/test_new.py", "-k", "no_such_test_anywhere"]))
        self.assert_stop_keeps_state("not_run", None)

    def test_stopped_red_is_not_added_to_history(self):
        first = self.two_reds()
        second = copy.deepcopy(self.entry()["red"])
        self.write("app.py", APP_WITH_SUB)
        rc, out = self.red_cmd()
        self.assertEqual(out["verdict"], "stop", out)
        self.assertEqual(self.entry().get("red_history"), [first])
        self.write("tests/test_new.py", NEW_TEST_3)
        self.write("app.py", APP_WITH_SUB_STUB)
        rc, out = self.red_cmd()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        entry = self.entry()
        self.assertEqual(entry["red_history"], [first, second])
        self.assertEqual(entry["red"]["record"], out["record"])


class CheckCasesTest(RedHistoryBase):
    """C2."""

    def assert_cases_match_report(self, rel):
        """기록의 cases가 [[이름, 결과], ...] 꼴이고, 보고서를 따로 읽은 결과와 맞는다. 기록을 낸다."""
        rec = self.read_record(rel)
        self.assertIn("cases", rec, rel)
        cases = rec["cases"]
        self.assertIsInstance(cases, list)
        for item in cases:
            self.assertIsInstance(item, list, item)
            self.assertEqual(len(item), 2, item)
            self.assertIsInstance(item[0], str, item)
            self.assertIn(item[1], KINDS, item)
        names = [c[0] for c in cases]
        self.assertEqual(len(names), len(set(names)), "이름이 겹침: %s" % names)
        expected = junit_cases(os.path.join(self.root, WORK_DIR, rec["report"]))
        self.assertTrue(expected, "보고서에 테스트 항목이 있어야 함")
        self.assertEqual({c[0]: c[1] for c in cases}, expected, rel)
        return rec

    def assert_existing_fields(self, rec, label, args, ran, exit_code):
        """기존 칸의 이름과 값이 지금과 같다. 새로 더해진 칸은 cases 하나뿐이다."""
        self.assertEqual(set(rec), RECORD_KEYS | {"cases"})
        report_path = os.path.join(self.root, WORK_DIR, rec["report"])
        self.assertEqual(rec["label"], label)
        self.assertEqual(rec["runner"], "pytest")
        self.assertEqual(rec["args"], args)
        self.assertEqual(rec["ran"], ran)
        self.assertEqual(rec["exit_code"], exit_code)
        self.assertRegex(rec["report"], r"^logs/" + re.escape(label) + r"-\d{8}T\d{6}Z-\d+\.xml$")
        kinds = [c[1] for c in rec["cases"]]
        self.assertEqual(rec["total"], len(kinds))
        self.assertEqual(rec["counts"], {k: kinds.count(k) for k in KINDS})
        self.assertEqual(rec["broken"], sorted(c[0] for c in rec["cases"] if c[1] in ("failure", "error")))
        with open(report_path[:-len(".xml")] + ".log", "rb") as f:
            self.assertEqual(rec["log_sha256"], hashlib.sha256(f.read()).hexdigest())
        self.assertEqual(rec["head"], self.head())
        self.assertIsInstance(rec["seconds"], int)
        self.assertGreaterEqual(rec["seconds"], 0)
        self.assertRegex(rec["at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_baseline_record_has_cases(self):
        out = self.baseline()
        self.assertEqual(out["record"], "checks/001-baseline.json")
        rec = self.assert_cases_match_report(out["record"])
        self.assertEqual(sorted(map(tuple, rec["cases"])), [
            ("tests.test_app::test_add", "passed"),
            ("tests.test_old::test_old_broken", "failure"),
            ("tests.test_skip::test_later", "skipped"),
        ])
        self.assert_existing_fields(rec, "baseline", ["-q"], "ran", 1)
        self.assertEqual(rec["total"], 3)
        self.assertEqual(rec["counts"], {"passed": 1, "skipped": 1, "failure": 1, "error": 0})
        self.assertEqual(rec["broken"], ["tests.test_old::test_old_broken"])
        state = self.state()["baseline"]
        self.assertEqual(state["broken"], rec["broken"])
        self.assertEqual(state["total"], rec["total"])

    def test_red_record_has_cases(self):
        self.baseline()
        out = self.red(NEW_TEST_2)
        rec = self.assert_cases_match_report(out["record"])
        self.assertEqual(sorted(map(tuple, rec["cases"])), [
            ("tests.test_new::test_sub", "failure"),
            ("tests.test_new::test_sub_negative", "failure"),
        ])
        self.assert_existing_fields(rec, "01-red", ["tests/test_new.py"], "ran", 1)

    def test_stopped_red_record_has_cases(self):
        self.baseline()
        self.write("tests/test_new.py", NEW_TEST_1)
        self.write("app.py", APP_WITH_SUB)
        rc, out = self.red_cmd()
        self.assertEqual(out["verdict"], "stop", out)
        rec = self.assert_cases_match_report(out["record"])
        self.assertEqual(rec["cases"], [["tests.test_new::test_sub", "passed"]])
        self.assert_existing_fields(rec, "01-red", ["tests/test_new.py"], "ran", 0)

    def test_green_records_have_cases(self):
        self.baseline()
        self.red(NEW_TEST_1)
        self.write("app.py", APP_WITH_SUB)
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "green")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        rec_task, rec_full = out["records"]
        rec = self.assert_cases_match_report(rec_task)
        self.assertEqual(rec["cases"], [["tests.test_new::test_sub", "passed"]])
        self.assert_existing_fields(rec, "01-green-task", ["tests/test_new.py"], "ran", 0)
        rec = self.assert_cases_match_report(rec_full)
        self.assertEqual(sorted(map(tuple, rec["cases"])), [
            ("tests.test_app::test_add", "passed"),
            ("tests.test_new::test_sub", "passed"),
            ("tests.test_old::test_old_broken", "failure"),
            ("tests.test_skip::test_later", "skipped"),
        ])
        self.assert_existing_fields(rec, "01-green-full", ["-q"], "ran", 1)

    def test_every_check_record_has_cases(self):
        self.baseline()
        self.red(NEW_TEST_1)
        self.write("app.py", APP_WITH_SUB)
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "green")
        self.assertEqual(out["verdict"], "ok", out)
        files = sorted(glob.glob(os.path.join(self.root, WORK_DIR, "checks", "*.json")))
        self.assertEqual([os.path.basename(p) for p in files], [
            "001-baseline.json", "002-01-red.json", "003-01-green-task.json", "004-01-green-full.json"])
        for p in files:
            self.assert_cases_match_report("checks/" + os.path.basename(p))

    def test_not_run_record_has_empty_cases(self):
        self.baseline()
        self.write_tasks(dict(TASK, check_args=["tests/test_app.py", "-k", "no_such_test_anywhere"]))
        rc, out = self.red_cmd()
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)
        rec = self.read_record(out["record"])
        self.assertIn("cases", rec)
        self.assertEqual(rec["cases"], [])
        self.assertEqual(set(rec), RECORD_KEYS | {"cases"})
        self.assertEqual(rec["label"], "01-red")
        self.assertEqual(rec["args"], ["tests/test_app.py", "-k", "no_such_test_anywhere"])
        self.assertEqual(rec["ran"], "not_run")
        self.assertEqual(rec["exit_code"], 5)
        self.assertEqual(rec["total"], 0)
        self.assertEqual(rec["counts"], {k: 0 for k in KINDS})
        self.assertEqual(rec["broken"], [])
        self.assertEqual(rec["head"], self.head())


if __name__ == "__main__":
    unittest.main()
