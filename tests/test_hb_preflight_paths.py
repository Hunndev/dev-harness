"""hb preflight의 경로 해석 테스트 (할 일 03).

- C4: --aux 경로를 저장소 기준 상대 경로로 정리한 뒤 범위를 본다. 저장소 밖으로 나가는 경로는 막는다.
- C2: 비pytest runner의 명령을 PATH에서 찾을 때, PATH의 상대 항목은 hb를 부른 폴더가 아니라 저장소 기준으로 푼다.

상황마다 임시 git 저장소에 작은 가짜 제품을 만들고, 실제 hb.py를 subprocess로 부른다.
실행: <pytest가 깔린 python> -m pytest tests/test_hb_preflight_paths.py -rA
"""
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HB = os.path.abspath(os.environ.get("HB_PATH") or os.path.join(HERE, "..", "bin", "hb.py"))
WORK = "w1"
WORK_DIR = ".harness/artifacts/work/" + WORK

CHECKS = {
    "version": 1,
    "runner": "pytest",
    "full_args": ["-q"],
    "timeout_seconds": 120,
    "test_globs": ["test_*.py", "conftest.py"],
}
# 경로 없는 이름. 실제 PATH에 같은 이름이 있으면 안 된다.
FAKE_JEST = "hb-preflight-fake-jest-5k2q"


def task(allowed):
    return {
        "id": "01",
        "title": "보조검증 경로",
        "kind": "feature",
        "criteria": ["C4"],
        "allowed_files": allowed,
        "check_args": ["tests/test_app.py"],
    }


@unittest.skipUnless(importlib.util.find_spec("pytest"), "pytest가 깔린 파이썬으로 돌려야 함")
class PreflightPathsCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="hb-preflight-paths-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.write(".gitignore", "logs/\n__pycache__/\n.pytest_cache/\nnode_modules/\n")
        self.write("conftest.py", "")
        self.write("app.py", "def add(a, b):\n    return a + b\n")
        self.write("tests/test_app.py", "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n")
        self.write(".harness/docs/checks.json", json.dumps(CHECKS))
        self.write_tasks(task(["app.py"]))
        self.commit("start")

    # --- 도우미 ---
    def git(self, *args):
        r = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def write(self, rel, text, base=None):
        path = os.path.join(base or self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(text))
        return path

    def write_tasks(self, *tasks):
        self.write(WORK_DIR + "/tasks.json", json.dumps({"work": WORK, "tasks": list(tasks)}, ensure_ascii=False))

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def use_allowed(self, allowed):
        self.write_tasks(task(allowed))
        self.commit("할 일 범위")

    def use_jest_contract(self, command):
        self.write(".harness/docs/checks.json", json.dumps({
            "version": 1, "runner": "jest", "command": command, "full_args": [],
            "timeout_seconds": 60, "test_globs": ["*.test.txt"]}))
        self.commit("jest 계약")

    def make_executable(self, folder, name):
        """folder 안에 실행 가능한 가짜 명령을 만든다. 실제로 돌지는 않는다(preflight는 돌리지 않음)."""
        path = self.write(os.path.join("node_modules", ".bin", name), "#!/bin/sh\nexit 0\n", base=folder)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def other_folder(self):
        """저장소가 아닌 폴더 (hb를 부를 cwd)."""
        folder = tempfile.mkdtemp(prefix="hb-preflight-elsewhere-")
        self.addCleanup(shutil.rmtree, folder, True)
        return folder

    def _read_out(self, r):
        try:
            out = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            self.fail("hb가 판정을 내지 않음: rc=%s out=%r err=%r" % (r.returncode, r.stdout[-300:], r.stderr[-300:]))
        return r.returncode, out

    def preflight(self, *args, cwd=None, path_front=None):
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if path_front is not None:
            env["PATH"] = path_front + os.pathsep + env.get("PATH", "")
        r = subprocess.run([sys.executable, HB, "--repo", self.root, "preflight", "--work", WORK, *args],
                           capture_output=True, text=True, cwd=cwd, env=env)
        return self._read_out(r)

    def assertStop(self, rc, out):
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(out["verdict"], "stop", out)

    def assertBlocked(self, out, kind, *texts):
        self.assertIn(kind, out.get("blocked") or {}, out)
        self.assertTrue(out["blocked"][kind], out)
        text = json.dumps(out["blocked"][kind], ensure_ascii=False)
        for t in texts:
            self.assertIn(t, text, out)

    def assertOk(self, rc, out):
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertEqual(out["blocked"], {}, out)

    # --- C4: --aux 정규화 ---
    def test_c4_glob_does_not_let_dotdot_reach_file_outside_allowed(self):
        """tools/*는 tools/../app.py와 글자로는 맞지만 실제 대상 app.py는 범위 밖이다."""
        self.use_allowed(["tools/*"])
        rc, out = self.preflight("--task", "01", "--aux", "tools/../app.py", "--aux", "tools/aux_check.py")
        self.assertStop(rc, out)
        self.assertBlocked(out, "scope", "app.py", "경로 변경 필요")
        self.assertEqual(set(out["blocked"]), {"scope"}, out)
        scope = json.dumps(out["blocked"]["scope"], ensure_ascii=False)
        self.assertNotIn("aux_check.py", scope, out)  # 범위 안인 것은 적지 않는다
        self.assertEqual(len(out["blocked"]["scope"]), 1, out)
        self.assertEqual(out["outcome"]["aux"], "incomplete", out)

    def test_c4_glob_inside_allowed_after_normalizing_is_not_blocked(self):
        """대조: 정리해도 tools/ 안이면 막지 않는다."""
        self.use_allowed(["tools/*"])
        rc, out = self.preflight("--task", "01", "--aux", "tools/aux_check.py", "--aux", "tools/./other.py")
        self.assertOk(rc, out)
        self.assertEqual(out["outcome"]["aux"], "incomplete", out)

    def test_c4_dot_slash_path_to_allowed_file_is_not_blocked(self):
        rc, out = self.preflight("--task", "01", "--aux", "./app.py")
        self.assertOk(rc, out)
        self.assertEqual(out["outcome"]["aux"], "incomplete", out)

    def test_c4_absolute_path_inside_repo_to_allowed_file_is_not_blocked(self):
        rc, out = self.preflight("--task", "01", "--aux", os.path.join(self.root, "app.py"))
        self.assertOk(rc, out)
        self.assertEqual(out["outcome"]["aux"], "incomplete", out)

    def test_c4_absolute_real_path_inside_repo_to_allowed_file_is_not_blocked(self):
        """임시 폴더가 심볼릭 링크 아래에 있어도(macOS의 /var -> /private/var) 같은 파일이면 범위 안."""
        rc, out = self.preflight("--task", "01", "--aux", os.path.join(os.path.realpath(self.root), "app.py"))
        self.assertOk(rc, out)

    def test_c4_absolute_path_to_disallowed_file_inside_repo_is_still_blocked(self):
        """대조: 절대 경로로 줘도 범위 밖 파일은 막는다."""
        rc, out = self.preflight("--task", "01", "--aux", os.path.join(self.root, "tests", "test_app.py"))
        self.assertStop(rc, out)
        self.assertBlocked(out, "scope", "test_app.py")
        self.assertEqual(set(out["blocked"]), {"scope"}, out)

    def test_c4_path_escaping_repo_stops_as_scope(self):
        rc, out = self.preflight("--task", "01", "--aux", "../outside.txt")
        self.assertStop(rc, out)
        self.assertBlocked(out, "scope", "outside.txt")
        self.assertEqual(set(out["blocked"]), {"scope"}, out)

    def test_c4_glob_does_not_let_path_escape_repo(self):
        """tools/*는 tools/../../outside.txt와 글자로는 맞지만 저장소 밖이다."""
        self.use_allowed(["tools/*"])
        rc, out = self.preflight("--task", "01", "--aux", "tools/../../outside.txt")
        self.assertStop(rc, out)
        self.assertBlocked(out, "scope", "outside.txt")
        self.assertEqual(set(out["blocked"]), {"scope"}, out)

    def test_c4_absolute_path_outside_repo_stops_as_scope(self):
        elsewhere = self.other_folder()
        target = self.write("outside.txt", "x\n", base=elsewhere)
        self.use_allowed(["*"])  # 글자로는 무엇이든 맞는 범위여도 저장소 밖은 막는다
        rc, out = self.preflight("--task", "01", "--aux", target)
        self.assertStop(rc, out)
        self.assertBlocked(out, "scope", "outside.txt")
        self.assertEqual(set(out["blocked"]), {"scope"}, out)

    # --- C2: PATH의 상대 항목은 저장소 기준 ---
    def test_c2_relative_path_entry_finds_command_in_repo_when_called_from_elsewhere(self):
        self.make_executable(self.root, FAKE_JEST)
        self.use_jest_contract([FAKE_JEST, "--ci"])
        elsewhere = self.other_folder()  # 여기에는 node_modules가 없다
        rc, out = self.preflight(cwd=elsewhere, path_front=os.path.join("node_modules", ".bin"))
        self.assertOk(rc, out)
        self.assertEqual(out["outcome"]["environment"], "ok", out)

    def test_c2_relative_path_entry_does_not_find_command_only_in_calling_folder(self):
        self.use_jest_contract([FAKE_JEST, "--ci"])
        elsewhere = self.other_folder()
        self.make_executable(elsewhere, FAKE_JEST)  # 부른 폴더에만 있고 저장소에는 없다
        self.assertFalse(os.path.exists(os.path.join(self.root, "node_modules", ".bin", FAKE_JEST)))
        rc, out = self.preflight(cwd=elsewhere, path_front=os.path.join("node_modules", ".bin"))
        self.assertStop(rc, out)
        self.assertBlocked(out, "environment", FAKE_JEST)
        self.assertEqual(set(out["blocked"]), {"environment"}, out)
        self.assertEqual(out["outcome"]["environment"], "blocked", out)

    def test_c2_absolute_path_entry_is_used_as_is(self):
        """대조: PATH의 절대 항목은 그대로 쓴다(저장소 밖 폴더여도)."""
        self.use_jest_contract([FAKE_JEST, "--ci"])
        elsewhere = self.other_folder()
        self.make_executable(elsewhere, FAKE_JEST)
        rc, out = self.preflight(cwd=self.other_folder(),
                                 path_front=os.path.join(elsewhere, "node_modules", ".bin"))
        self.assertOk(rc, out)
        self.assertEqual(out["outcome"]["environment"], "ok", out)

    def test_c2_command_missing_everywhere_still_stops(self):
        """대조: 상대 항목이 있어도 어디에도 없으면 막는다."""
        self.use_jest_contract([FAKE_JEST, "--ci"])
        rc, out = self.preflight(cwd=self.other_folder(), path_front=os.path.join("node_modules", ".bin"))
        self.assertStop(rc, out)
        self.assertBlocked(out, "environment", FAKE_JEST)


if __name__ == "__main__":
    unittest.main()
