"""할 일 갈래 setup-fix after: UTF-8이 아닌 준비 데이터를 고쳤을 때의 인정과 변경 기록 테스트.

test_hb_setup_fix.py처럼 임시 git 저장소에 작은 가짜 제품(이름과 도시 목록)을 만들고 진짜 pytest로 검사를 돌린다.
준비 데이터는 latin-1로 쓴 입력 파일(tests/data/names.txt)이고, 검사 계약의 test_globs에 들어 있다.
한 줄의 도시 칸이 비어 있어, 구현을 마친 뒤 테스트 본문에서 실패하는 상황이다. 파일에는 NUL이 없어 git은 글자 파일로 본다.
- C4: 세 인정 조건을 만족하면 UTF-8이 아닌 준비 데이터를 고친 것도 인정한다(판정 줄을 낸다).
- C6: 인정되면 테스트 쪽 변경(git에 없는 새 파일 포함)이 logs/에 바이트 그대로 남고, 사용자의 인덱스는 그대로다.
실행: <테스트 환경의 python> -m pytest tests/test_hb_setup_fix_nonutf8.py   (pytest가 깔린 파이썬이어야 함)
"""
import copy
import glob
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
    "test_globs": ["test_*.py", "conftest.py", "tests/data/*.txt"],
}
TASK = {
    "id": "01", "title": "도시 없는 이름", "kind": "feature", "criteria": ["C1"],
    "allowed_files": ["app.py", "tests/test_names.py", "tests/data/*.txt"], "check_args": ["tests/test_names.py"],
}
BASE_APP = "def add(a, b):\n    return a + b\n"
APP_STUB = BASE_APP + textwrap.dedent("""


    def missing_city(rows):
        return None
""")
APP_IMPL = BASE_APP + textwrap.dedent("""


    def missing_city(rows):
        return [r["name"] for r in rows if not r["city"]]
""")

# 테스트가 latin-1 입력 파일을 읽는다. 도시 칸이 비어 있는 줄이 있으면 본문의 단언에서 실패한다.
NAMES_TEST = textwrap.dedent("""\
    import os

    import pytest

    from app import missing_city

    DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


    @pytest.fixture
    def rows():
        with open(os.path.join(DATA, "names.txt"), encoding="latin-1") as f:
            lines = f.read().splitlines()[1:]
        return [dict(zip(("name", "city"), line.split(";"))) for line in lines]


    def test_every_row_has_city(rows):
        assert missing_city(rows) == []


    def test_every_row_has_name(rows):
        assert rows and all(r["name"] for r in rows)
""")
NAMES_BROKEN = b"name;city\nAnna;Berlin\nJos\xe9;\n"
NAMES_FIXED = b"name;city\nAnna;Berlin\nJos\xe9;Montr\xe9al\n"
CITIES = b"city\nMontr\xe9al\nQu\xe9bec\n"  # git에 없는 새 latin-1 준비 데이터 파일

NAMES_DATA = "tests/data/names.txt"
CITIES_DATA = "tests/data/cities.txt"
CITY = "tests.test_names::test_every_row_has_city"
NAME = "tests.test_names::test_every_row_has_name"


def values(d):
    return list(d.values())


def strings(obj):
    """출력이나 기록 안의 모든 문자열(사전의 키 포함)."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for k, v in obj.items() for s in [k] + strings(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in strings(v)]
    return []


@unittest.skipUnless(importlib.util.find_spec("pytest"), "pytest가 깔린 파이썬으로 돌려야 함")
class NonUtf8AfterTest(unittest.TestCase):
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
        self.write(".harness/docs/checks.json", json.dumps(CHECKS))
        self.write(WORK_DIR + "/tasks.json", json.dumps({"work": WORK, "tasks": [TASK]}, ensure_ascii=False))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "start")

    # --- 도우미 ---
    def git(self, *args):
        r = subprocess.run(["git", *args], cwd=self.root, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout  # 바이트 그대로

    def write(self, rel, content):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content if isinstance(content, bytes) else content.encode("utf-8"))

    def read_bytes(self, path):
        with open(path, "rb") as f:
            return f.read()

    def hb(self, *args):
        # 크기가 같은 변경이 같은 초에 쓰이면 옛 .pyc가 쓰여 깨진 동작이 가려지므로 바이트코드를 쓰지 않는다.
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, HB, "--repo", self.root, *args], capture_output=True, env=env)
        stdout = r.stdout.decode("utf-8", "replace")
        try:
            out = json.loads(stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            self.fail("hb가 판정을 내지 않음: rc=%s out=%r err=%r"
                      % (r.returncode, stdout[-300:], r.stderr.decode("utf-8", "replace")[-600:]))
        return r.returncode, out

    def state(self):
        with open(os.path.join(self.root, WORK_DIR, "state.json"), encoding="utf-8") as f:
            return json.load(f)

    def fixes(self):
        return self.state()["tasks"]["01"].get("setup_fixes") or []

    def diff_logs(self):
        return sorted(glob.glob(os.path.join(self.root, WORK_DIR, "logs", "01-setup-fix-*.diff.log")))

    def status(self):
        out = self.git("status", "--porcelain=v1", "--untracked-files=all")
        return [line for line in out.splitlines() if not line[3:].startswith(b".harness/")]

    def assert_ok(self, rc, out):
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        return out

    def before(self):
        return self.hb("setup-fix", "--work", WORK, "--task", "01", "--phase", "before")

    def after(self):
        return self.hb("setup-fix", "--work", WORK, "--task", "01", "--phase", "after")

    def prepared(self):
        """바탕 검사 -> 테스트와 (도시가 빠진) latin-1 입력 파일을 쓰고 실패 확인 -> 구현 -> before까지 한 상태."""
        self.assert_ok(*self.hb("baseline", "--work", WORK))
        self.write("tests/test_names.py", NAMES_TEST)
        self.write(NAMES_DATA, NAMES_BROKEN)
        self.write("app.py", APP_STUB)
        self.assert_ok(*self.hb("check", "--work", WORK, "--task", "01", "--phase", "red"))
        self.write("app.py", APP_IMPL)
        self.assert_ok(*self.before())
        before = self.fixes()[-1]["before"]
        self.assertIn({CITY: "failure", NAME: "passed"}, values(before), "고치기 전에는 도시 테스트가 실패해야 함")

    # --- 테스트 ---
    def test_after_accepts_latin1_setup_data_fix(self):
        """C4: 세 인정 조건을 만족하면 UTF-8이 아닌 준비 데이터를 고친 것도 ok로 인정하고 after를 남긴다."""
        self.prepared()
        item = copy.deepcopy(self.fixes()[-1])
        self.write(NAMES_DATA, NAMES_FIXED)
        out = self.assert_ok(*self.after())
        self.assertIn([NAMES_DATA], values(out), "바뀐 파일 목록을 내야 함")
        logs = self.diff_logs()
        self.assertEqual(len(logs), 1, logs)
        name = os.path.basename(logs[0])
        self.assertEqual(name, "01-setup-fix-1.diff.log")
        self.assertTrue(any(s.endswith(name) for s in strings(out)), "변경 기록 경로를 내야 함: %s" % out)
        fixes = self.fixes()
        self.assertEqual(len(fixes), 1)
        self.assertEqual(fixes[-1]["red_record"], item["red_record"])
        self.assertEqual(fixes[-1]["before"], item["before"], "before 기록은 그대로여야 함")
        self.assertIn("after", fixes[-1], "인정되면 after가 남아 before가 끝나야 함")
        after = fixes[-1]["after"]
        self.assertIn([NAMES_DATA], values(after))
        self.assertTrue(any(s.endswith(name) for s in strings(after)), "after에 변경 기록 경로가 있어야 함: %s" % after)

    def test_after_keeps_latin1_lines_as_bytes_and_index_untouched(self):
        """C6: 변경 기록에 고치기 전·고친 뒤 줄이 바이트 그대로 있고, 사용자의 인덱스와 작업 트리는 그대로다."""
        self.prepared()
        self.git("add", "app.py")  # 사용자가 올려 둔 것이 있는 인덱스
        cached = self.git("diff", "--cached")
        self.assertIn(b"app.py", cached)
        self.write(NAMES_DATA, NAMES_FIXED)
        status = self.status()
        self.assertIn(b"?? " + NAMES_DATA.encode(), status)
        self.assert_ok(*self.after())
        self.assertEqual(self.git("diff", "--cached"), cached, "사용자의 인덱스가 바뀌면 안 됨")
        self.assertEqual(self.status(), status, "작업 트리 상태가 바뀌면 안 됨")
        self.assertEqual(self.read_bytes(os.path.join(self.root, NAMES_DATA)), NAMES_FIXED, "준비 데이터 파일은 그대로여야 함")

        logs = self.diff_logs()
        self.assertEqual(len(logs), 1, logs)
        diff = self.read_bytes(logs[0])
        lines = diff.splitlines()
        self.assertIn(NAMES_DATA.encode(), diff)
        self.assertIn(b"-Jos\xe9;", lines, "고치기 전 줄이 latin-1 바이트 그대로 있어야 함")
        self.assertIn(b"+Jos\xe9;Montr\xe9al", lines, "고친 뒤 줄이 latin-1 바이트 그대로 있어야 함")
        self.assertNotIn(b"-Anna;Berlin", lines, "바뀌지 않은 줄은 빠지거나 더해진 줄로 나오면 안 됨")
        self.assertNotIn(b"+Anna;Berlin", lines)
        self.assertNotIn(b"app.py", diff, "테스트 쪽 밖은 변경 기록에 없어야 함")

    def test_after_records_new_untracked_latin1_file(self):
        """C6: git에 없는 새 latin-1 준비 데이터 파일도 함께 인정되고 변경 기록에 바이트 그대로 남는다."""
        self.prepared()
        cached = self.git("diff", "--cached")
        self.write(NAMES_DATA, NAMES_FIXED)
        self.write(CITIES_DATA, CITIES)
        status = self.status()
        self.assertIn(b"?? " + CITIES_DATA.encode(), status)
        out = self.assert_ok(*self.after())
        self.assertEqual(self.git("diff", "--cached"), cached, "사용자의 인덱스가 바뀌면 안 됨")
        self.assertEqual(self.status(), status, "작업 트리 상태가 바뀌면 안 됨")
        lists = [sorted(v) for v in values(out) if isinstance(v, list) and all(isinstance(x, str) for x in v)]
        self.assertIn(sorted([NAMES_DATA, CITIES_DATA]), lists, "바뀐 파일 목록을 내야 함")
        self.assertIn("after", self.fixes()[-1])
        self.assertIn(sorted([NAMES_DATA, CITIES_DATA]), [sorted(v) for v in values(self.fixes()[-1]["after"])
                                                          if isinstance(v, list)])
        logs = self.diff_logs()
        self.assertEqual(len(logs), 1, logs)
        diff = self.read_bytes(logs[0])
        lines = diff.splitlines()
        self.assertIn(CITIES_DATA.encode(), diff)
        self.assertIn(b"+Montr\xe9al", lines)
        self.assertIn(b"+Qu\xe9bec", lines)
        self.assertIn(b"+Jos\xe9;Montr\xe9al", lines)


if __name__ == "__main__":
    unittest.main()
