"""hb preflight 명령의 테스트.

상황마다 임시 git 저장소에 작은 가짜 제품을 만들고, 실제 hb.py를 subprocess로 부른다.
green 기록이 필요한 상황은 실제 hb의 baseline -> check red -> check green으로 만든다(기록을 손으로 만들지 않는다).
pytest를 찾을 수 없는 상황은 설치/삭제 없이, hb.py를 실행하는 파이썬 안에서 pytest 가져오기를 막아 만든다.
실행: <pytest가 깔린 python> -m pytest tests/test_hb_preflight.py -rA
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
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

# hb.py를 실행하는 파이썬 안에서 pytest를 찾지 못하게 막는다. 설치된 pytest는 건드리지 않는다.
BLOCK_PYTEST = textwrap.dedent("""
    import sys

    _BLOCKED = ("pytest", "_pytest")


    def _blocked(name):
        return any(name == b or name.startswith(b + ".") for b in _BLOCKED)


    class _Hide:
        def __init__(self, inner):
            self.inner = inner

        def find_spec(self, name, path=None, target=None):
            if _blocked(name):
                return None
            find = getattr(self.inner, "find_spec", None)
            return find(name, path, target) if find else None

        def __getattr__(self, attr):
            return getattr(self.inner, attr)


    for _name in list(sys.modules):
        if _blocked(_name):
            del sys.modules[_name]
    sys.meta_path[:] = [_Hide(f) for f in sys.meta_path]
    for _name in _BLOCKED:
        sys.modules[_name] = None
""")
PROBE = BLOCK_PYTEST + textwrap.dedent("""
    import importlib.util
    try:
        import pytest  # noqa: F401
        imported = True
    except ImportError:
        imported = False
    print(importlib.util.find_spec("pytest") is None and not imported)
""")
RUN_HB_WITHOUT_PYTEST = BLOCK_PYTEST + textwrap.dedent("""
    import runpy
    hb_path = sys.argv[1]
    sys.argv = [hb_path] + sys.argv[2:]
    runpy.run_path(hb_path, run_name="__main__")
""")


def utc(seconds_from_now):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + seconds_from_now))


@unittest.skipUnless(importlib.util.find_spec("pytest"), "pytest가 깔린 파이썬으로 돌려야 함")
class PreflightCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="hb-preflight-")
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

    def _read_out(self, r):
        try:
            out = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            self.fail("hb가 판정을 내지 않음: rc=%s out=%r err=%r" % (r.returncode, r.stdout[-300:], r.stderr[-300:]))
        return r.returncode, out

    def hb(self, *args):
        r = subprocess.run([sys.executable, HB, "--repo", self.root, *args], capture_output=True, text=True)
        return self._read_out(r)

    def hb_without_pytest(self, *args):
        """pytest를 찾을 수 없는 파이썬에서 hb.py를 실행한다."""
        probe = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True)
        self.assertEqual(probe.stdout.strip(), "True", "pytest 막기가 듣지 않음: %r %r" % (probe.stdout, probe.stderr))
        r = subprocess.run([sys.executable, "-c", RUN_HB_WITHOUT_PYTEST, HB, "--repo", self.root, *args],
                           capture_output=True, text=True)
        return self._read_out(r)

    def preflight(self, *args):
        return self.hb("preflight", "--work", WORK, *args)

    def use_jest_contract(self, command):
        self.write(".harness/docs/checks.json", json.dumps({
            "version": 1, "runner": "jest", "command": command, "full_args": [],
            "timeout_seconds": 60, "test_globs": ["*.test.txt"]}))
        self.commit("jest 계약")

    def state_path(self):
        return os.path.join(self.root, WORK_DIR, "state.json")

    def state(self):
        with open(self.state_path(), encoding="utf-8") as f:
            return json.load(f)

    def baseline(self):
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertEqual(out["verdict"], "ok", out)

    def red(self):
        self.write("tests/test_new.py", NEW_TEST)
        self.write("app.py", APP_WITH_SUB_STUB)
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")
        self.assertEqual(out["verdict"], "ok", out)

    def green(self):
        self.write("app.py", APP_WITH_SUB)
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "green")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertTrue(self.state()["tasks"]["01"]["green"]["ok"])

    def through_green(self):
        self.baseline()
        self.red()
        self.green()

    def records(self):
        """state.json의 바이트와 작업 폴더의 checks/, logs/ 파일 목록."""
        work = os.path.join(self.root, WORK_DIR)
        state = None
        if os.path.exists(self.state_path()):
            with open(self.state_path(), "rb") as f:
                state = f.read()

        def listing(name):
            folder = os.path.join(work, name)
            return sorted(os.listdir(folder)) if os.path.isdir(folder) else None

        return state, listing("checks"), listing("logs")

    def assertStop(self, rc, out):
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(out["verdict"], "stop", out)

    def assertBlocked(self, out, kind, *texts):
        self.assertIn(kind, out["blocked"], out)
        self.assertTrue(out["blocked"][kind], out)
        text = json.dumps(out["blocked"][kind], ensure_ascii=False)
        for t in texts:
            self.assertIn(t, text, out)

    # --- 막을 것이 없을 때 ---
    def test_nothing_blocked_is_ok_with_empty_blocked_and_no_optional_fields(self):
        rc, out = self.preflight()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertEqual(out["blocked"], {}, out)
        self.assertEqual(out["outcome"], {"product": "not_run", "environment": "ok", "aux": "none"}, out)
        self.assertNotIn("reuse", out)
        self.assertNotIn("time", out)
        self.assertIn("summary", out)

    # --- C1: pytest를 찾을 수 없음 ---
    def test_c1_pytest_not_importable_by_running_python_stops_as_environment(self):
        rc, out = self.hb_without_pytest("preflight", "--work", WORK)
        self.assertStop(rc, out)
        self.assertBlocked(out, "environment", "pytest")
        self.assertEqual(out["outcome"]["environment"], "blocked", out)
        self.assertEqual(set(out["blocked"]), {"environment"}, out)

    def test_c1_pytest_not_needed_when_runner_is_not_pytest(self):
        self.use_jest_contract([sys.executable, "-c", "pass"])
        rc, out = self.hb_without_pytest("preflight", "--work", WORK)
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertNotIn("environment", out["blocked"])
        self.assertEqual(out["outcome"]["environment"], "ok", out)

    # --- C2: 계약의 명령을 찾을 수 없음 ---
    def test_c2_missing_command_for_non_pytest_runner_stops_as_environment(self):
        self.use_jest_contract(["hb-preflight-no-such-command-8731", "--ci"])
        rc, out = self.preflight()
        self.assertStop(rc, out)
        self.assertBlocked(out, "environment", "hb-preflight-no-such-command-8731")
        self.assertEqual(out["outcome"]["environment"], "blocked", out)

    def test_c2_existing_command_for_non_pytest_runner_is_not_blocked(self):
        self.use_jest_contract([sys.executable, "-c", "pass"])
        rc, out = self.preflight()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertEqual(out["blocked"], {}, out)
        self.assertEqual(out["outcome"]["environment"], "ok", out)

    # --- C3: logs/가 git 제외가 아님 ---
    def test_c3_logs_not_ignored_stops_as_evidence(self):
        self.write(".gitignore", "__pycache__/\n.pytest_cache/\n")
        self.commit("logs 제외를 뺌")
        rc, out = self.preflight()
        self.assertStop(rc, out)
        self.assertBlocked(out, "evidence", "logs")
        self.assertNotIn("environment", out["blocked"], out)
        self.assertEqual(out["outcome"]["environment"], "ok", out)

    def test_c3_only_log_files_ignored_still_stops_as_evidence(self):
        """보고서(.xml)는 git에 들어갈 수 있으므로 baseline과 같이 막는다."""
        self.write(".gitignore", "*.log\n__pycache__/\n.pytest_cache/\n")
        self.commit("로그 파일만 제외")
        rc, out = self.preflight()
        self.assertStop(rc, out)
        self.assertBlocked(out, "evidence", "logs")

    # --- C4: 보조검증 경로가 할 일 범위 밖 ---
    def test_c4_aux_outside_allowed_files_stops_as_scope_with_path(self):
        rc, out = self.preflight("--task", "01", "--aux", "app.py", "--aux", "tools/aux_check.py")
        self.assertStop(rc, out)
        self.assertBlocked(out, "scope", "tools/aux_check.py", "경로 변경 필요")
        self.assertNotIn("app.py", json.dumps(out["blocked"]["scope"], ensure_ascii=False), out)
        self.assertEqual(set(out["blocked"]), {"scope"}, out)
        self.assertEqual(out["outcome"]["aux"], "incomplete", out)

    def test_c4_aux_inside_allowed_files_is_not_blocked(self):
        rc, out = self.preflight("--task", "01", "--aux", "app.py", "--aux", "tests/test_new.py")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertNotIn("scope", out["blocked"], out)
        self.assertEqual(out["outcome"]["aux"], "incomplete", out)

    def test_c4_aux_without_task_stops_as_scope(self):
        rc, out = self.preflight("--aux", "app.py")
        self.assertStop(rc, out)
        self.assertBlocked(out, "scope")
        self.assertEqual(set(out["blocked"]), {"scope"}, out)

    # --- C5: 시간 ---
    def test_c5_past_deadline_stops_as_time(self):
        rc, out = self.preflight("--deadline", "2000-01-01T00:00:00Z")
        self.assertStop(rc, out)
        self.assertBlocked(out, "time")
        self.assertEqual(out["time"]["needed_seconds"], CHECKS["timeout_seconds"] + 120, out)
        self.assertLess(out["time"]["remaining_seconds"], 0, out)

    def test_c5_far_future_deadline_is_not_blocked(self):
        rc, out = self.preflight("--deadline", "2999-01-01T00:00:00Z")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertNotIn("time", out["blocked"], out)
        self.assertEqual(out["time"]["needed_seconds"], CHECKS["timeout_seconds"] + 120, out)
        self.assertGreater(out["time"]["remaining_seconds"], out["time"]["needed_seconds"], out)

    def test_c5_margin_counts_toward_needed_time(self):
        deadline = utc(600)  # 남은 시간 약 600초, timeout_seconds 120
        rc, out = self.preflight("--deadline", deadline, "--margin", "600")
        self.assertStop(rc, out)
        self.assertBlocked(out, "time")
        self.assertEqual(out["time"]["needed_seconds"], 720, out)
        rc, out = self.preflight("--deadline", deadline, "--margin", "60")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertNotIn("time", out["blocked"], out)
        self.assertEqual(out["time"]["needed_seconds"], 180, out)

    # --- C6: 결과 세 칸 ---
    def test_c6_green_ok_with_aux_reports_product_pass_and_aux_incomplete(self):
        self.through_green()
        rc, out = self.preflight("--task", "01", "--aux", "app.py")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertEqual(out["outcome"], {"product": "pass", "environment": "ok", "aux": "incomplete"}, out)

    def test_c6_product_pass_with_environment_blocked_is_still_stop(self):
        self.through_green()
        rc, out = self.hb_without_pytest("preflight", "--work", WORK, "--task", "01", "--aux", "app.py")
        self.assertStop(rc, out)
        self.assertEqual(out["outcome"], {"product": "pass", "environment": "blocked", "aux": "incomplete"}, out)
        self.assertBlocked(out, "environment")

    def test_c6_product_not_run_without_green_record(self):
        self.baseline()
        self.red()
        rc, out = self.preflight("--task", "01")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertEqual(out["outcome"]["product"], "not_run", out)
        self.assertNotIn("reuse", out)

    def test_c6_product_not_run_when_task_not_given_even_after_green(self):
        self.through_green()
        rc, out = self.preflight()
        self.assertEqual(out["outcome"]["product"], "not_run", out)
        self.assertNotIn("reuse", out)

    # --- C7: 증거 재사용 ---
    def test_c7_unchanged_source_after_green_is_same_source(self):
        self.through_green()
        rc, out = self.preflight("--task", "01")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertEqual(out["reuse"], "same_source", out)
        self.assertFalse(out.get("review_paths"), out)

    def test_c7_modified_file_after_green_is_changed_with_review_path(self):
        self.through_green()
        self.write("app.py", APP_WITH_SUB + "\n# 통과 확인 뒤에 고침\n")
        rc, out = self.preflight("--task", "01")
        self.assertEqual(out["reuse"], "changed", out)
        self.assertIn("app.py", out["review_paths"], out)
        self.assertEqual(out["outcome"]["product"], "pass", out)

    def test_c7_new_file_after_green_is_changed_with_review_path(self):
        self.through_green()
        self.write("extra.py", "X = 1\n")
        rc, out = self.preflight("--task", "01")
        self.assertEqual(out["reuse"], "changed", out)
        self.assertIn("extra.py", out["review_paths"], out)

    # --- C8: 기록을 만들거나 고치지 않음 ---
    def test_c8_preflight_leaves_state_checks_and_logs_untouched(self):
        self.through_green()
        self.write("app.py", APP_WITH_SUB + "\n# 바뀐 소스\n")
        before = self.records()
        self.assertIsNotNone(before[0])
        self.assertTrue(before[1])
        self.assertTrue(before[2])
        runs = [
            self.preflight("--task", "01", "--aux", "app.py"),
            self.preflight("--task", "01", "--aux", "tools/aux_check.py", "--deadline", "2000-01-01T00:00:00Z"),
            self.preflight("--task", "01", "--deadline", "2999-01-01T00:00:00Z"),
            self.hb_without_pytest("preflight", "--work", WORK, "--task", "01"),
        ]
        self.assertEqual([out["verdict"] for _, out in runs], ["ok", "stop", "ok", "stop"], runs)
        self.assertEqual(self.records(), before)

    def test_c8_preflight_before_baseline_creates_no_records(self):
        self.assertEqual(self.records(), (None, None, None))
        rc, out = self.preflight("--task", "01", "--deadline", "2999-01-01T00:00:00Z")
        self.assertEqual(out["verdict"], "ok", out)
        self.assertEqual(out["outcome"]["product"], "not_run", out)
        self.assertNotIn("reuse", out)
        self.assertEqual(self.records(), (None, None, None))
        self.assertEqual(self.git("status", "--porcelain"), "")

    # --- 예외 상황 (spec.md) ---
    def test_bad_deadline_format_stops_without_blocked(self):
        rc, out = self.preflight("--deadline", "내일 아침")
        self.assertStop(rc, out)
        self.assertEqual(out["reason"], "deadline 형식이 틀림", out)
        self.assertFalse(out.get("blocked"), out)

    def test_unknown_task_id_stops_with_same_reason_as_check(self):
        rc, out = self.preflight("--task", "99")
        self.assertStop(rc, out)
        self.assertEqual(out["reason"], "할 일 목록에서 찾을 수 없음: 99", out)

    def test_several_blocked_kinds_are_all_reported_in_one_stop(self):
        self.write(".gitignore", "__pycache__/\n.pytest_cache/\n")
        self.commit("logs 제외를 뺌")
        rc, out = self.preflight("--aux", "app.py", "--deadline", "2000-01-01T00:00:00Z")
        self.assertStop(rc, out)
        self.assertEqual(set(out["blocked"]), {"evidence", "scope", "time"}, out)
        self.assertEqual(out["outcome"]["environment"], "ok", out)


if __name__ == "__main__":
    unittest.main()
