"""바탕 검사의 준비 데이터 정정(setup-fix --baseline)을 Jest 쪽에서 확인하는 테스트 (C11, 바탕 갈래).

tests/test_hb_setup_fix_jest.py처럼 진짜 Jest 대신 같은 모양의 보고서(--json)를 내는 작은 가짜 실행기를 쓴다.
가짜 실행기의 "both-contain" 항목은 구현 파일과 준비 데이터 파일이 둘 다 정해진 글자를 담을 때 통과한다.
처음 커밋부터 큰 주문의 입력 파일(tests/data/order_big.json)에 수량("qty")이 빠져 있어 바탕 검사에서 실패하는 상황이다.
test_hb_setup_fix_baseline.py(pytest)와 같은 갈래에서 같은 판정과 같은 칸이 나오는지 본다.
실행: <테스트 환경의 python> -m pytest tests/test_hb_setup_fix_baseline_jest.py
"""
import copy
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
        items = []
        for line in open(path, encoding="utf-8").read().splitlines():
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split("|")]
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
    "id": "01", "title": "할인", "kind": "feature", "criteria": ["C1"],
    "allowed_files": ["app.txt", "tests/new.test.txt", "tests/data/*"],
    "check_args": ["tests/new.test.txt"],
}
LINE_FREE = "free shipping over limit | both-contain | app.txt | shipping | tests/data/order_big.json | \"qty\"\n"
LINE_FEE = "shipping fee under limit | both-contain | app.txt | shipping | tests/data/order_small.json | \"qty\"\n"
LINE_EXTRA = "fee without items | file-contains | app.txt | shipping\n"
ORDER_TEST = LINE_FREE + LINE_FEE
ORDER_TEST_EXTRA = ORDER_TEST + LINE_EXTRA
ORDER_TEST_NO_FEE = LINE_FREE                                               # 테스트가 하나 줄어듦
ORDER_TEST_SKIP_FREE = "free shipping over limit | skip\n" + LINE_FEE   # 깨졌던 테스트에 건너뛰기 표시만 붙임

APP = "add\nshipping\n"

BIG_BROKEN = '{"items": [{"price": 30}, {"price": 25}]}\n'           # 수량이 빠짐
BIG_FIXED = '{"items": [{"price": 30, "qty": 1}, {"price": 25, "qty": 1}]}\n'
BIG_STILL = '{"items": [{"price": 35}, {"price": 25}]}\n'            # 고쳤지만 수량은 여전히 없음
SMALL = '{"items": [{"price": 10, "qty": 2}]}\n'
SMALL_BROKEN = '{"items": [{"price": 10}]}\n'

BIG_DATA = "tests/data/order_big.json"
SMALL_DATA = "tests/data/order_small.json"
ORDER_FILE = "tests/order.test.txt"
FREE = "tests/order.test.txt::free shipping over limit"
FEE = "tests/order.test.txt::shipping fee under limit"
EXTRA = "tests/order.test.txt::fee without items"
DIFF_LOG = "logs/baseline-setup-fix.diff.log"
FIELDS = ("added", "removed", "still_failing", "regressed")


class BaselineFixJestTest(unittest.TestCase):
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
        self.write("app.txt", APP)
        self.write("tests/app.test.txt", "adds | file-contains | app.txt | add\n")
        self.write(ORDER_FILE, ORDER_TEST)
        self.write(BIG_DATA, BIG_BROKEN)
        self.write(SMALL_DATA, SMALL)
        self.write(".harness/docs/checks.json", json.dumps({
            "version": 1, "runner": "jest", "command": [sys.executable, self.fake], "full_args": [],
            "timeout_seconds": 60, "test_globs": ["*.test.txt", "tests/data/*"],
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

    def commit(self, message, files):
        for rel, text in files.items():
            self.write(rel, text)
        self.git("add", "--", *files)
        self.git("commit", "-q", "-m", message)

    def hb(self, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, HB, "--repo", self.root, *args], capture_output=True, text=True, env=env)
        try:
            out = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            self.fail("hb가 판정을 내지 않음: rc=%s out=%r err=%r" % (r.returncode, r.stdout[-300:], r.stderr[-300:]))
        return r.returncode, out

    def setup_fix(self):
        return self.hb("setup-fix", "--work", WORK, "--baseline")

    def work_path(self, rel):
        return os.path.join(self.root, WORK_DIR, rel)

    def read_bytes(self, rel):
        with open(self.work_path(rel), "rb") as f:
            return f.read()

    def state(self):
        with open(self.work_path("state.json"), encoding="utf-8") as f:
            return json.load(f)

    def record(self, rel):
        with open(self.work_path(rel), encoding="utf-8") as f:
            return json.load(f)

    def checks_count(self):
        return len(os.listdir(self.work_path("checks")))

    def newest_record(self):
        name = sorted(os.listdir(self.work_path("checks")))[-1]
        return "checks/" + name, self.record("checks/" + name)

    def assert_ok(self, rc, out):
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        return out

    def baseline(self):
        out = self.assert_ok(*self.hb("baseline", "--work", WORK))
        self.assertEqual(out["broken"], [FREE])

    def drop_cases(self):
        rel = self.state()["baseline"]["record"]
        rec = self.record(rel)
        rec.pop("cases", None)
        with open(self.work_path(rel), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def original(self):
        state = self.state()
        rel = state["baseline"]["record"]
        report = self.record(rel)["report"]
        return {"rel": rel, "record": self.read_bytes(rel), "report_rel": report,
                "report": self.read_bytes(report) if os.path.exists(self.work_path(report)) else None,
                "baseline": copy.deepcopy(state["baseline"])}

    def assert_original_kept(self, orig):
        self.assertEqual(self.read_bytes(orig["rel"]), orig["record"], "원래 바탕 검사 기록이 바뀜")
        if orig["report"] is not None:
            self.assertEqual(self.read_bytes(orig["report_rel"]), orig["report"], "원래 바탕 검사 보고서가 바뀜")
        baseline = dict(self.state()["baseline"])
        baseline.pop("setup_fix", None)
        self.assertEqual(baseline, orig["baseline"], "baseline의 기존 칸이 바뀜")

    def assert_accepted(self, out, orig, count):
        self.assertEqual(self.checks_count(), count + 1)
        rec_path, rec = self.newest_record()
        self.assertEqual(rec["args"], self.record(orig["rel"])["args"])
        self.assertEqual(out["fixed"], [FREE])
        self.assertEqual(out["changed"], [BIG_DATA])
        self.assertEqual(out["diff"], DIFF_LOG)
        self.assertEqual(out["record"], rec_path)
        self.assertEqual(out["baseline_record"], orig["rel"])
        fix = self.state()["baseline"]["setup_fix"]
        self.assertEqual(fix["record"], rec_path)
        self.assertEqual(fix["head"], self.git("rev-parse", "HEAD").strip())
        self.assertEqual(fix["files"], {BIG_DATA: self.git("rev-parse", "HEAD:" + BIG_DATA).strip()})
        self.assertEqual(fix["fixed"], [FREE])
        diff = self.read_bytes(DIFF_LOG).decode("utf-8")
        lines = diff.splitlines()
        self.assertIn("-" + BIG_BROKEN.strip(), lines)
        self.assertIn("+" + BIG_FIXED.strip(), lines)
        heads = sorted(line[len("diff --git a/"):].split(" b/", 1)[0] for line in lines
                       if line.startswith("diff --git a/"))
        self.assertEqual(heads, [BIG_DATA], "변경 기록에는 바뀐 파일만 있어야 함")
        self.assertNotIn(WORK_DIR, diff, "작업 폴더는 변경 기록에 없어야 함")
        self.assert_original_kept(orig)

    def fix_stop(self, test=None, big=BIG_FIXED, small=None, drop=False):
        self.baseline()
        if drop:
            self.drop_cases()
        orig = self.original()
        files = {BIG_DATA: big}
        if test is not None:
            files[ORDER_FILE] = test
        if small is not None:
            files[SMALL_DATA] = small
        self.commit("준비 데이터 고침", files)
        state, count = self.read_bytes("state.json"), self.checks_count()
        rc, out = self.setup_fix()
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertEqual(self.read_bytes("state.json"), state, "멈춘 뒤 state.json이 바뀜")
        self.assertEqual(self.checks_count(), count + 1, "테스트를 돌린 뒤 멈춰야 함")
        self.assertFalse(os.path.exists(self.work_path(DIFF_LOG)))
        self.assert_original_kept(orig)
        return out

    def assert_fields(self, out, **expected):
        for field, names in expected.items():
            self.assertEqual(out.get(field), names, out)
        for field in FIELDS:
            if field not in expected:
                self.assertFalse(out.get(field), out)

    # --- 인정 ---
    def test_accepts_setup_data_fix(self):
        self.baseline()
        orig = self.original()
        self.commit("작업 기록", {WORK_DIR + "/INDEX.md": "# 작업\n"})
        self.commit("준비 데이터 고침", {BIG_DATA: BIG_FIXED})
        count = self.checks_count()
        out = self.assert_ok(*self.setup_fix())
        self.assert_accepted(out, orig, count)

    def test_record_without_cases_reads_report_and_accepts(self):
        self.baseline()
        self.drop_cases()
        orig = self.original()
        self.commit("준비 데이터 고침", {BIG_DATA: BIG_FIXED})
        count = self.checks_count()
        out = self.assert_ok(*self.setup_fix())
        self.assert_accepted(out, orig, count)

    # --- 멈춤 ---
    def test_record_without_cases_and_no_report_does_not_run(self):
        self.baseline()
        self.drop_cases()
        orig = self.original()
        os.remove(self.work_path(orig["report_rel"]))
        self.commit("준비 데이터 고침", {BIG_DATA: BIG_FIXED})
        state, count = self.read_bytes("state.json"), self.checks_count()
        rc, out = self.setup_fix()
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("보고서", out["reason"], out)
        self.assertEqual(self.read_bytes("state.json"), state)
        self.assertEqual(self.checks_count(), count, "테스트를 돌리지 않아야 함")
        self.assertEqual(self.read_bytes(orig["rel"]), orig["record"])

    def test_stops_when_broken_test_still_fails(self):
        out = self.fix_stop(big=BIG_STILL)
        self.assert_fields(out, still_failing=[FREE])

    def test_stops_when_broken_test_is_skipped(self):
        out = self.fix_stop(test=ORDER_TEST_SKIP_FREE, big=BIG_BROKEN)
        self.assert_fields(out, still_failing=[FREE])

    def test_stops_when_a_test_is_added(self):
        out = self.fix_stop(test=ORDER_TEST_EXTRA)
        self.assert_fields(out, added=[EXTRA])

    def test_stops_when_a_test_is_removed(self):
        out = self.fix_stop(test=ORDER_TEST_NO_FEE)
        self.assert_fields(out, removed=[FEE])

    def test_stops_when_passing_test_now_fails(self):
        out = self.fix_stop(small=SMALL_BROKEN)
        self.assert_fields(out, regressed=[FEE])

    def test_record_without_cases_stops_by_field(self):
        out = self.fix_stop(test=ORDER_TEST_EXTRA, drop=True)
        self.assertNotIn("cases", self.record(self.state()["baseline"]["record"]))
        self.assert_fields(out, added=[EXTRA])


if __name__ == "__main__":
    unittest.main()
