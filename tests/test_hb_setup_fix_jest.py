"""할 일의 준비 데이터 정정(setup-fix)을 Jest 쪽에서 확인하는 테스트 (C11, 할 일 갈래).

tests/test_hb_jest.py처럼 진짜 Jest 대신 같은 모양의 보고서(--json)를 내는 작은 가짜 실행기를 쓴다.
가짜 실행기의 "both-contain" 항목은 구현 파일과 준비 데이터 파일이 둘 다 정해진 글자를 담을 때 통과한다.
큰 주문의 입력 파일(tests/data/order_big.json)에 수량("qty")이 빠져 있어 구현을 마친 뒤에도 실패하는 상황이다.
test_hb_setup_fix.py(pytest)와 같은 갈래에서 같은 판정과 같은 칸이 나오는지 본다.
실행: <테스트 환경의 python> -m pytest tests/test_hb_setup_fix_jest.py
"""
import copy
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HB = os.environ.get("HB_PATH") or os.path.join(HERE, "..", "bin", "hb.py")
WORK = "w1"
WORK_DIR = ".harness/artifacts/work/" + WORK

FAKE_JEST = r'''
import json, os, sys

args = sys.argv[1:]
out = [a.split("=", 1)[1] for a in args if a.startswith("--outputFile=")][0]
patterns = [a for a in args if not a.startswith("--")]
root = os.path.realpath(os.getcwd())


def contains(rel, text):
    target = os.path.join(root, rel)
    return os.path.exists(target) and text in open(target, encoding="utf-8").read()


results = []
for base, dirs, files in os.walk(root):
    dirs[:] = [d for d in dirs if d not in (".git", ".harness")]
    for name in sorted(files):
        if not name.endswith(".test.txt"):
            continue
        path = os.path.join(base, name)
        rel = os.path.relpath(path, root)
        if patterns and not any(p in rel for p in patterns):
            continue
        items, crashed = [], None
        for line in open(path, encoding="utf-8").read().splitlines():
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split("|")]
            if parts[1] == "requires":  # 파일을 불러올 때 필요한 것. 없으면 파일이 통째로 실행되지 못한다
                if not contains(parts[2], parts[3]):
                    crashed = "  ● Test suite failed to run\n\n    TypeError: %s is not a function" % parts[3]
                continue
            if parts[1] == "both-contain":
                missing = [(f, t) for f, t in ((parts[2], parts[3]), (parts[4], parts[5])) if not contains(f, t)]
                items.append((parts[0], "failed" if missing else "passed",
                              ["Error: expected %s to contain %s\n    at body" % missing[0]] if missing else []))
            elif parts[1] == "file-contains":
                ok = contains(parts[2], parts[3])
                items.append((parts[0], "passed" if ok else "failed",
                              [] if ok else ["Error: expected %s to contain %s\n    at body" % (parts[2], parts[3])]))
            else:
                items.append((parts[0], {"skip": "pending"}.get(parts[1], parts[1]), []))
        if crashed:
            results.append({"name": path, "status": "failed", "message": crashed, "assertionResults": []})
            continue
        failed = any(s == "failed" for _, s, _ in items)
        results.append({"name": path, "status": "failed" if failed else "passed", "message": "",
                        "assertionResults": [{"ancestorTitles": [], "title": n, "fullName": n, "status": s,
                                              "failureMessages": m} for n, s, m in items]})
total = sum(len(r["assertionResults"]) for r in results)
with open(out, "w", encoding="utf-8") as f:
    json.dump({"success": True, "numTotalTests": total, "numPassedTests": total, "numFailedTests": 0,
               "numFailedTestSuites": 0, "numRuntimeErrorTestSuites": 0, "testResults": results}, f)
sys.exit(0)
'''

TASK = {
    "id": "01", "title": "배송비", "kind": "feature", "criteria": ["C1"],
    "allowed_files": ["app.txt", "tests/new.test.txt", "tests/data/*.json"],
    "check_args": ["tests/new.test.txt"],
}
LINE_FREE = "free shipping over limit | both-contain | app.txt | shipping | tests/data/order_big.json | \"qty\"\n"
LINE_FEE = "shipping fee under limit | both-contain | app.txt | shipping | tests/data/order_small.json | \"qty\"\n"
LINE_EXTRA = "fee without items | file-contains | app.txt | shipping\n"
NEW_TEST = LINE_FREE + LINE_FEE
NEW_TEST_EXTRA = NEW_TEST + LINE_EXTRA
NEW_TEST_SKIP_FREE = "free shipping over limit | skip\n" + LINE_FEE   # before의 실패에 건너뛰기 표시만 붙임
# 파일을 불러올 때 구현의 add가 있어야 한다. 없으면 파일이 통째로 실행되지 못한다(FILE_FAILED)
NEW_TEST_REQUIRES = "load | requires | app.txt | add\n" + NEW_TEST

APP_STUB = "add\n"
APP_IMPL = "add\nshipping\n"

BIG_BROKEN = '{"items": [{"price": 30}, {"price": 25}]}\n'           # 수량이 빠짐
BIG_FIXED = '{"items": [{"price": 30, "qty": 1}, {"price": 25, "qty": 1}]}\n'
BIG_STILL = '{"items": [{"price": 35}, {"price": 25}]}\n'            # 고쳤지만 수량은 여전히 없음
SMALL = '{"items": [{"price": 10, "qty": 2}]}\n'
SMALL_BROKEN = '{"items": [{"price": 10}]}\n'

BIG_DATA = "tests/data/order_big.json"
SMALL_DATA = "tests/data/order_small.json"
FREE = "tests/new.test.txt::free shipping over limit"
FEE = "tests/new.test.txt::shipping fee under limit"
EXTRA = "tests/new.test.txt::fee without items"
FIELDS = ("added", "removed", "still_failing", "regressed")


def strings(obj):
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for k, v in obj.items() for s in [k] + strings(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in strings(v)]
    return []


class SetupFixJestTest(unittest.TestCase):
    def setUp(self):
        self.tools = tempfile.mkdtemp(prefix="hb-fake-jest-")
        self.addCleanup(shutil.rmtree, self.tools, True)
        self.fake = os.path.join(self.tools, "fake_jest.py")
        with open(self.fake, "w", encoding="utf-8") as f:
            f.write(FAKE_JEST)
        self.root = tempfile.mkdtemp(prefix="hb-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.write(".gitignore", "logs/\n")
        self.write("app.txt", APP_STUB)
        self.write("tests/app.test.txt", "adds | file-contains | app.txt | add\n")
        self.write(".harness/docs/checks.json", json.dumps({
            "version": 1, "runner": "jest", "command": [sys.executable, self.fake], "full_args": [],
            "timeout_seconds": 60, "test_globs": ["*.test.txt", "tests/data/*.json"],
        }))
        self.write(WORK_DIR + "/tasks.json", json.dumps({"work": WORK, "tasks": [TASK]}, ensure_ascii=False))
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

    def hb(self, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, HB, "--repo", self.root, *args], capture_output=True, text=True, env=env)
        try:
            out = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            self.fail("hb가 판정을 내지 않음: rc=%s out=%r err=%r" % (r.returncode, r.stdout[-300:], r.stderr[-300:]))
        return r.returncode, out

    def state_bytes(self):
        with open(os.path.join(self.root, WORK_DIR, "state.json"), "rb") as f:
            return f.read()

    def entry(self):
        with open(os.path.join(self.root, WORK_DIR, "state.json"), encoding="utf-8") as f:
            return json.load(f)["tasks"]["01"]

    def fixes(self):
        return self.entry().get("setup_fixes") or []

    def checks_count(self):
        return len(os.listdir(os.path.join(self.root, WORK_DIR, "checks")))

    def newest_record(self):
        folder = os.path.join(self.root, WORK_DIR, "checks")
        name = sorted(os.listdir(folder))[-1]
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            return json.load(f)

    def diff_logs(self):
        return sorted(glob.glob(os.path.join(self.root, WORK_DIR, "logs", "01-setup-fix-*.diff.log")))

    def assert_ok(self, rc, out):
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        return out

    def ready_and_before(self):
        """바탕 검사 -> 테스트와 (수량이 빠진) 입력 파일로 실패 확인 -> 구현 -> before 까지."""
        self.assert_ok(*self.hb("baseline", "--work", WORK))
        self.write("tests/new.test.txt", NEW_TEST)
        self.write(BIG_DATA, BIG_BROKEN)
        self.write(SMALL_DATA, SMALL)
        out = self.assert_ok(*self.hb("check", "--work", WORK, "--task", "01", "--phase", "red"))
        self.assertEqual(out["failed"], sorted([FREE, FEE]))
        self.write("app.txt", APP_IMPL)
        self.assert_ok(*self.hb("setup-fix", "--work", WORK, "--task", "01", "--phase", "before"))
        self.assertIn({FREE: "failure", FEE: "passed"}, list(self.fixes()[0]["before"].values()))

    def after(self):
        return self.hb("setup-fix", "--work", WORK, "--task", "01", "--phase", "after")

    def after_stop(self, test=None, big=BIG_FIXED, small=None):
        self.ready_and_before()
        if test is not None:
            self.write("tests/new.test.txt", test)
        self.write(BIG_DATA, big)
        if small is not None:
            self.write(SMALL_DATA, small)
        state = self.state_bytes()
        rc, out = self.after()
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertEqual(self.state_bytes(), state, "멈춘 뒤 state.json이 바뀜")
        self.assertNotIn("after", self.fixes()[0])
        self.assertEqual(self.diff_logs(), [])
        return out

    def assert_fields(self, out, **expected):
        for field, names in expected.items():
            self.assertEqual(out.get(field), names, out)
        for field in FIELDS:
            if field not in expected:
                self.assertFalse(out.get(field), out)

    # --- 인정 ---
    def test_after_accepts_setup_data_fix(self):
        self.ready_and_before()
        item = copy.deepcopy(self.fixes()[0])
        self.write(BIG_DATA, BIG_FIXED)
        out = self.assert_ok(*self.after())
        self.assertEqual(self.newest_record()["args"], ["tests/new.test.txt"])
        self.assertIn([BIG_DATA], list(out.values()))
        logs = self.diff_logs()
        self.assertEqual(len(logs), 1, logs)
        self.assertTrue(any(s.endswith(os.path.basename(logs[0])) for s in strings(out)), out)
        with open(logs[0], encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertIn("+" + BIG_FIXED.strip(), lines)
        fix = self.fixes()[0]
        self.assertEqual(fix["before"], item["before"])
        self.assertIn("after", fix)
        # 인정된 정정으로 통과 확인이 나머지 관문까지 간다
        self.assert_ok(*self.hb("check", "--work", WORK, "--task", "01", "--phase", "green"))

    # --- 멈춤 ---
    def test_after_stops_when_before_failure_still_fails(self):
        out = self.after_stop(big=BIG_STILL)
        self.assert_fields(out, still_failing=[FREE])

    def test_after_stops_when_a_test_is_added(self):
        out = self.after_stop(test=NEW_TEST_EXTRA)
        self.assert_fields(out, added=[EXTRA])

    def test_after_stops_when_passing_test_now_fails(self):
        out = self.after_stop(small=SMALL_BROKEN)
        self.assert_fields(out, regressed=[FEE])

    def test_after_stops_when_before_failure_is_skipped(self):
        out = self.after_stop(test=NEW_TEST_SKIP_FREE, big=BIG_BROKEN)
        self.assert_fields(out, still_failing=[FREE])

    def test_before_with_file_failed_stops(self):
        """테스트 파일이 통째로 실행되지 못함(FILE_FAILED 항목). 메시지는 가져오기 오류 꼴이 아니어도 멈춘다."""
        self.assert_ok(*self.hb("baseline", "--work", WORK))
        self.write("tests/new.test.txt", NEW_TEST_REQUIRES)
        self.write(BIG_DATA, BIG_BROKEN)
        self.write(SMALL_DATA, SMALL)
        out = self.assert_ok(*self.hb("check", "--work", WORK, "--task", "01", "--phase", "red"))
        self.assertEqual(out["failed"], sorted([FREE, FEE]))
        self.write("app.txt", "shipping\n")  # 구현이 add를 지워 파일을 불러오지 못함
        state = self.state_bytes()
        count = self.checks_count()
        rc, out = self.hb("setup-fix", "--work", WORK, "--task", "01", "--phase", "before")
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertEqual(self.state_bytes(), state, "멈춘 뒤 state.json이 바뀜")
        self.assertEqual(self.checks_count(), count + 1, "테스트를 돌린 뒤 멈춰야 함")
        rec = self.newest_record()
        self.assertEqual(rec["args"], ["tests/new.test.txt"])
        self.assertEqual(rec["cases"], [["tests/new.test.txt::(파일 실행 실패)", "error"]], rec)
        self.assertNotIn("setup_fixes", self.entry())


if __name__ == "__main__":
    unittest.main()
