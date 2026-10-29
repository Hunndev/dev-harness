"""hb preflight의 증거 재사용 판단 테스트 (할 일 04, C7).

green 기록 뒤 커밋으로 바뀐 파일도 review_paths에 나와야 한다(spec 16줄: 스냅숏에 HEAD가 들어 있어
커밋 뒤에는 changed이고, 그때 바뀐 경로를 알려 준다). 작업 폴더의 기록 파일은 changed()와 같이 뺀다.

상황마다 임시 git 저장소에 작은 가짜 제품을 만들고, 실제 hb.py를 subprocess로 부른다.
green 기록은 실제 hb의 baseline -> check red -> check green으로 만들고, 그 뒤의 커밋은 임시 저장소에서 git으로 만든다.
실행: <pytest가 깔린 python> -m pytest tests/test_hb_preflight_reuse.py -rA
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
HB = os.path.abspath(os.environ.get("HB_PATH") or os.path.join(HERE, "..", "bin", "hb.py"))
WORK = "w1"
WORK_DIR = ".harness/artifacts/work/" + WORK
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

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
GREEN_PATHS = ["app.py", "tests/test_new.py"]
NEW_TEST = """
    from app import sub

    def test_sub():
        assert sub(5, 3) == 2
"""
APP_TEST = "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
APP_WITH_SUB_STUB = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return None\n"
APP_WITH_SUB = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"


@unittest.skipUnless(importlib.util.find_spec("pytest"), "pytest가 깔린 파이썬으로 돌려야 함")
class PreflightReuseCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="hb-preflight-reuse-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.write(".gitignore", "logs/\n__pycache__/\n.pytest_cache/\n")
        self.write("conftest.py", "")
        self.write("app.py", "def add(a, b):\n    return a + b\n")
        self.write("tests/test_app.py", APP_TEST)
        self.write(".harness/docs/checks.json", json.dumps(CHECKS))
        self.write(WORK_DIR + "/tasks.json", json.dumps({"work": WORK, "tasks": [TASK]}, ensure_ascii=False))
        self.commit("start")

    # --- 도우미 ---
    def git(self, *args):
        r = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, env=ENV)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(text))

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def hb(self, *args):
        r = subprocess.run([sys.executable, HB, "--repo", self.root, *args],
                           capture_output=True, text=True, env=ENV)
        try:
            out = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            self.fail("hb가 판정을 내지 않음: rc=%s out=%r err=%r" % (r.returncode, r.stdout[-300:], r.stderr[-300:]))
        return r.returncode, out

    def state_path(self):
        return os.path.join(self.root, WORK_DIR, "state.json")

    def records(self):
        """state.json의 바이트와 작업 폴더의 checks/, logs/ 파일 목록."""
        work = os.path.join(self.root, WORK_DIR)
        with open(self.state_path(), "rb") as f:
            state = f.read()

        def listing(name):
            folder = os.path.join(work, name)
            return sorted(os.listdir(folder)) if os.path.isdir(folder) else None

        return state, listing("checks"), listing("logs")

    def through_green(self):
        """실제 hb로 baseline -> red -> green. green paths는 app.py, tests/test_new.py (커밋 안 된 채)."""
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertEqual(out["verdict"], "ok", out)
        self.write("tests/test_new.py", NEW_TEST)
        self.write("app.py", APP_WITH_SUB_STUB)
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")
        self.assertEqual(out["verdict"], "ok", out)
        self.write("app.py", APP_WITH_SUB)
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "green")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        with open(self.state_path(), encoding="utf-8") as f:
            green = json.load(f)["tasks"]["01"]["green"]
        self.assertTrue(green["ok"], green)
        self.assertEqual(sorted(green["paths"]), GREEN_PATHS, green)

    def assertClean(self):
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), "")

    def preflight_untouched(self):
        """preflight --task 01을 돌리고, state.json 바이트와 checks/, logs/ 목록이 그대로인지 본다."""
        before = self.records()
        self.assertTrue(before[1], before)
        self.assertTrue(before[2], before)
        rc, out = self.hb("preflight", "--work", WORK, "--task", "01")
        self.assertEqual(self.records(), before)
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertEqual(out["outcome"]["product"], "pass", out)
        return out

    def assertNoWorkRecords(self, out):
        records = [p for p in out.get("review_paths", []) if p.startswith(WORK_DIR + "/")]
        self.assertEqual(records, [], out)

    # --- 대조: green 뒤 커밋도 변경도 없음 ---
    def test_c7_no_commit_and_no_change_after_green_is_same_source_without_review_paths(self):
        self.through_green()
        out = self.preflight_untouched()
        self.assertEqual(out["reuse"], "same_source", out)
        self.assertNotIn("review_paths", out)

    # --- 대조: green 파일과 작업 폴더 기록만 커밋 ---
    def test_c7_commit_of_green_files_and_records_only_lists_green_paths_without_records(self):
        self.through_green()
        self.commit("통과한 것과 기록을 커밋")  # state.json, checks/도 커밋에 들어간다 (logs/는 git 제외)
        self.write(WORK_DIR + "/INDEX.md", "# 작업 기록\n")
        self.commit("작업 기록만 커밋")
        self.assertClean()
        out = self.preflight_untouched()
        self.assertEqual(out["reuse"], "changed", out)
        self.assertEqual(sorted(out["review_paths"]), GREEN_PATHS, out)
        self.assertNoWorkRecords(out)

    # --- 커밋으로 더한 새 파일 ---
    def test_c7_new_file_committed_after_green_is_changed_with_review_path(self):
        self.through_green()
        self.commit("통과한 것과 기록을 커밋")
        self.write("extra.py", "X = 1\n")
        self.commit("green paths 밖의 새 파일")
        self.write(WORK_DIR + "/INDEX.md", "# 작업 기록\n")
        self.commit("작업 기록만 커밋")  # 마지막 커밋에는 extra.py가 없다
        self.assertClean()
        out = self.preflight_untouched()
        self.assertEqual(out["reuse"], "changed", out)
        self.assertIn("extra.py", out["review_paths"], out)
        self.assertEqual(sorted(out["review_paths"]), sorted(GREEN_PATHS + ["extra.py"]), out)
        self.assertNoWorkRecords(out)

    # --- 커밋으로 고친, 이미 추적되던 파일 ---
    def test_c7_tracked_file_modified_and_committed_after_green_is_changed_with_review_path(self):
        self.through_green()
        self.write("tests/test_app.py", APP_TEST + "\n\ndef test_add_zero():\n    assert add(0, 0) == 0\n")
        self.commit("통과한 것, 기록, green paths 밖의 수정을 한 번에 커밋")
        self.assertClean()
        out = self.preflight_untouched()
        self.assertEqual(out["reuse"], "changed", out)
        self.assertIn("tests/test_app.py", out["review_paths"], out)
        self.assertEqual(sorted(out["review_paths"]), sorted(GREEN_PATHS + ["tests/test_app.py"]), out)
        self.assertNoWorkRecords(out)

    # --- 커밋으로 바뀐 파일과 커밋 안 된 경로가 함께 ---
    def test_c7_committed_and_uncommitted_changes_after_green_are_both_review_paths(self):
        self.through_green()
        self.commit("통과한 것과 기록을 커밋")
        self.write("extra.py", "X = 1\n")
        self.commit("green paths 밖의 새 파일")
        self.write("notes.txt", "커밋 안 한 새 파일\n")
        out = self.preflight_untouched()
        self.assertEqual(out["reuse"], "changed", out)
        self.assertEqual(sorted(out["review_paths"]), sorted(GREEN_PATHS + ["extra.py", "notes.txt"]), out)
        self.assertNoWorkRecords(out)


if __name__ == "__main__":
    unittest.main()
