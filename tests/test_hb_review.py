"""검수 검사(review)와 할 일을 뒤에 더하는 흐름의 테스트.

test_hb.py처럼 임시 git 저장소에 작은 가짜 제품을 만들고 진짜 pytest로 검사를 돌린다.
할 일은 개발 문서의 순서대로(실패 확인 → 통과 확인 → 완료 → 커밋) 끝낸 뒤 검수를 부른다.
평가는 AI가 하므로 여기서는 "평가 대상 커밋"(--since)만 정해서 넘긴다.
실행: <테스트 환경의 python> -m unittest discover -s tests -v   (pytest가 깔린 파이썬이어야 함)
"""
import importlib.util
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

CHECKS = {
    "version": 1,
    "runner": "pytest",
    "full_args": ["-q"],
    "timeout_seconds": 120,
    "test_globs": ["test_*.py", "conftest.py"],
}
SUB = {
    "id": "01", "title": "빼기", "kind": "feature", "criteria": ["C1"],
    "allowed_files": ["app.py", "tests/test_sub.py"], "check_args": ["tests/test_sub.py"],
}
MUL = {
    "id": "02", "title": "곱하기", "kind": "feature", "criteria": ["C2"],
    "allowed_files": ["app.py", "tests/test_mul.py"], "check_args": ["tests/test_mul.py"],
}
BASE_APP = "def add(a, b):\n    return a + b\n"


@unittest.skipUnless(importlib.util.find_spec("pytest"), "pytest가 깔린 파이썬으로 돌려야 함")
class ReviewCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="hb-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.write(".gitignore", "logs/\n__pycache__/\n.pytest_cache/\n")
        self.write("conftest.py", "")
        self.app = BASE_APP
        self.write("app.py", self.app)
        self.write("tests/test_app.py", "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n")
        self.write(".harness/docs/checks.json", json.dumps(CHECKS))
        self.write(WORK_DIR + "/spec.md", "# 설명서\n\n- C1 빼기\n- C2 곱하기\n")
        self.write_tasks(SUB, MUL)
        self.commit_all("start")

    # --- 도우미 ---
    def git(self, *args):
        r = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def head(self):
        return self.git("rev-parse", "HEAD").strip()

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def write_tasks(self, *tasks):
        self.write(WORK_DIR + "/tasks.json", json.dumps({"work": WORK, "tasks": list(tasks)}, ensure_ascii=False))

    def commit_all(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def commit_work(self, msg):
        self.git("add", WORK_DIR)
        self.git("commit", "-q", "-m", msg)

    def hb(self, *args):
        # 크기가 같은 변경이 같은 초에 쓰이면 옛 .pyc가 쓰여 깨진 동작이 가려지므로 바이트코드를 쓰지 않는다.
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, HB, "--repo", self.root, *args], capture_output=True, text=True, env=env)
        try:
            out = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            self.fail("hb가 판정을 내지 않음: rc=%s out=%r err=%r" % (r.returncode, r.stdout[-300:], r.stderr[-300:]))
        return r.returncode, out

    def ok(self, *args):
        rc, out = self.hb(*args)
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        return out

    def state(self):
        with open(os.path.join(self.root, WORK_DIR, "state.json"), encoding="utf-8") as f:
            return json.load(f)

    def review_records(self):
        checks = os.path.join(self.root, WORK_DIR, "checks")
        return [f for f in os.listdir(checks) if "review" in f]

    def do_task(self, task, name, body):
        """할 일 하나를 개발 문서의 순서대로 끝낸다: 테스트와 빈 뼈대 → 실패 확인 → 구현 → 통과 확인 → 완료 → 커밋."""
        test = "tests/test_%s.py" % name
        self.write(test, "from app import %s\n\n\ndef test_%s():\n    %s\n" % (name, name, body))
        self.write("app.py", self.app + "\n\ndef %s(a, b):\n    return None\n" % name)
        self.ok("check", "--work", WORK, "--task", task["id"], "--phase", "red")
        self.app += "\n\ndef %s(a, b):\n    return a %s b\n" % (name, "-" if name == "sub" else "*")
        self.write("app.py", self.app)
        self.ok("check", "--work", WORK, "--task", task["id"], "--phase", "green")
        self.git("add", "app.py", test)
        self.ok("done", "--work", WORK, "--task", task["id"])
        self.commit_work("task " + task["id"])

    def finish_both(self):
        self.ok("baseline", "--work", WORK)
        self.do_task(SUB, "sub", "assert sub(5, 3) == 2")
        self.do_task(MUL, "mul", "assert mul(2, 3) == 6")

    def review(self, since=None):
        return self.hb("review", "--work", WORK, "--since=" + (since or self.head()))  # "-"로 시작하는 값도 넘기려고 = 로 붙인다

    def assert_stop(self, out, rc, words):
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn(words, out["reason"])

    # --- 정상 흐름 ---
    def test_review_passes_when_every_task_is_done_and_nothing_broke(self):
        self.finish_both()
        rc, out = self.review()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertIn("할 일 2개 모두 완료", out["summary"])
        self.assertIn("평가 뒤 바뀐 것 없음", out["summary"])
        self.assertIn("새로 깨진 것 없음", out["summary"])
        self.assertEqual(out["paths"], ["app.py", "tests/test_mul.py", "tests/test_sub.py"])
        self.assertEqual(out["tasks"], {
            "01": {"criteria": ["C1"], "tests": ["tests.test_sub::test_sub"]},
            "02": {"criteria": ["C2"], "tests": ["tests.test_mul::test_mul"]},
        })
        self.assertEqual(out["tests"], {"baseline": {"total": 1, "skipped": 0}, "now": {"total": 3, "skipped": 0}})
        self.assertEqual(out["still_broken"], [])
        self.assertEqual(self.state()["review"]["head"], self.head())

    def test_baseline_broken_tests_are_named_for_the_cause_check(self):
        self.write("tests/test_old.py", "def test_plain_broken():\n    assert 1 == 2\n")
        self.commit_all("old broken test")
        self.finish_both()
        rc, out = self.review()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertIn("원래 깨져 있던 것 1건", out["summary"])
        self.assertEqual(out["still_broken"], ["tests.test_old::test_plain_broken"])
        self.assertEqual(out["baseline_record"], "checks/001-baseline.json")

    def test_records_committed_after_evaluation_do_not_count_as_changes(self):
        """평가와 검수 기록, 진행표를 커밋하면 커밋 번호는 바뀌지만 평가받은 내용은 그대로다."""
        self.finish_both()
        since = self.head()
        self.write(WORK_DIR + "/eval-01.md", "# 평가 01\n")
        self.write(WORK_DIR + "/INDEX.md", "# 진행표\n")
        self.commit_work("평가 기록")
        self.write(WORK_DIR + "/review-01.md", "# 검수 01 (적는 중)\n")  # 커밋 안 한 관리 기록도 괜찮다
        rc, out = self.review(since)
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertEqual(out["since"], since)

    # --- 평가 뒤에 바뀐 것 ---
    def test_stops_when_code_changed_after_evaluation(self):
        self.finish_both()
        since = self.head()
        self.write("app.py", self.app + "# 평가 뒤에 고침\n")
        self.commit_all("평가 뒤 수정")
        rc, out = self.review(since)
        self.assert_stop(out, rc, "평가부터 다시")
        self.assertEqual(out["changed"], ["app.py"])
        self.assertEqual(self.review_records(), [])

    def test_stops_when_spec_changed_after_evaluation(self):
        """설명서는 관리 기록이 아니다. 평가 뒤에 바뀌면 평가부터 다시."""
        self.finish_both()
        since = self.head()
        self.write(WORK_DIR + "/spec.md", "# 설명서\n\n- C1 빼기\n- C2 곱하기\n- C3 나누기\n")
        self.commit_work("설명서 고침")
        rc, out = self.review(since)
        self.assert_stop(out, rc, "평가부터 다시")
        self.assertEqual(out["changed"], [WORK_DIR + "/spec.md"])

    def test_stops_on_uncommitted_spec_change(self):
        self.finish_both()
        self.write(WORK_DIR + "/tasks/01-sub.md", "커밋하지 않은 할 일 본문\n")
        rc, out = self.review()
        self.assert_stop(out, rc, "커밋되지 않은 변경")
        self.assertEqual(out["dirty"], [WORK_DIR + "/tasks/01-sub.md"])

    def test_stops_on_uncommitted_code_change_before_running_anything(self):
        self.finish_both()
        self.write("app.py", self.app + "# 커밋하지 않은 수정\n")
        rc, out = self.review()
        self.assert_stop(out, rc, "커밋되지 않은 변경")
        self.assertEqual(out["dirty"], ["app.py"])
        self.assertNotIn("review", self.state())
        self.assertEqual(self.review_records(), [])

    def test_stops_when_since_is_unknown_or_looks_like_an_option(self):
        self.finish_both()
        for bad in ("0123456789abcdef0123456789abcdef01234567", "--all", "no-such-ref"):
            rc, out = self.review(bad)
            self.assert_stop(out, rc, "평가 대상 커밋을 찾을 수 없음")

    def test_stops_when_since_is_older_than_baseline(self):
        before = self.head()
        self.write("notes.md", "바탕 검사 전의 커밋\n")
        self.commit_all("more")
        self.finish_both()
        rc, out = self.review(before)
        self.assert_stop(out, rc, "이어지지 않음")

    def test_stops_when_head_no_longer_descends_from_baseline(self):
        self.finish_both()
        self.git("checkout", "-q", "--orphan", "rewritten")
        self.commit_all("가지를 새로 쌓음")
        rc, out = self.review()
        self.assert_stop(out, rc, "이어지지 않음")

    # --- 프로그램 검사 ---
    def test_stops_when_a_task_is_not_done(self):
        self.ok("baseline", "--work", WORK)
        self.do_task(SUB, "sub", "assert sub(5, 3) == 2")
        rc, out = self.review()
        self.assert_stop(out, rc, "끝나지 않은 할 일")
        self.assertEqual(out["tasks"], ["02"])

    def test_stops_when_a_file_outside_every_task_changed_after_baseline(self):
        self.finish_both()
        self.write("other.py", "X = 1\n")
        self.commit_all("할 일 밖의 커밋")
        rc, out = self.review()  # 평가가 이 커밋까지 보고 넘겼다고 쳐도
        self.assert_stop(out, rc, "허락된 파일 밖")
        self.assertEqual(out["outside"], ["other.py"])

    def test_stops_when_a_commit_after_done_breaks_an_old_test(self):
        self.finish_both()
        self.write("app.py", self.app.replace("return a + b", "return a - b"))
        self.commit_all("허락된 파일이지만 기존 동작을 깸")
        rc, out = self.review()
        self.assert_stop(out, rc, "새로 깨진 테스트")
        self.assertEqual(out["new_broken"], ["tests.test_app::test_add"])

    def test_stops_when_a_tasks_test_is_skipped_in_the_final_run(self):
        """건너뛴 테스트는 깨진 것으로 세지 않지만, 할 일을 증명하던 테스트라면 통과가 아니다."""
        self.finish_both()
        self.write("tests/test_mul.py", "import pytest\n\n\n@pytest.mark.skip(reason='나중에')\ndef test_mul():\n    assert False\n")
        self.commit_all("테스트를 건너뛰게 바꿈")
        rc, out = self.review()
        self.assert_stop(out, rc, "할 일의 테스트")
        self.assertEqual(out["tests"], {"02": ["tests.test_mul::test_mul"]})

    def test_stops_before_baseline(self):
        rc, out = self.review()
        self.assert_stop(out, rc, "바탕 검사")

    # --- 평가가 할 일을 뒤에 더하는 흐름 ---
    def test_task_appended_after_baseline_goes_through_and_review_covers_it(self):
        self.write_tasks(SUB)  # 계획에는 01만 있었다고 치고
        self.commit_work("plan has 01 only")
        self.ok("baseline", "--work", WORK)
        self.do_task(SUB, "sub", "assert sub(5, 3) == 2")
        self.write_tasks(SUB, dict(MUL, kind="bug"))  # 평가가 02를 더한다
        self.commit_work("eval adds 02")
        self.do_task(dict(MUL, kind="bug"), "mul", "assert mul(2, 3) == 6")
        rc, out = self.review()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertEqual(sorted(out["tasks"]), ["01", "02"])

    def test_baseline_refuses_to_run_twice(self):
        """개발을 새 세션에서 이어 갈 때 바탕 검사를 다시 돌리면 완료 기록과 원래 깨져 있던 것이 지워진다."""
        self.ok("baseline", "--work", WORK)
        self.do_task(SUB, "sub", "assert sub(5, 3) == 2")
        before = self.state()
        rc, out = self.hb("baseline", "--work", WORK)
        self.assert_stop(out, rc, "이미 했음")
        self.assertEqual(self.state(), before)


if __name__ == "__main__":
    unittest.main()
