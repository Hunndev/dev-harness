"""hb 프로그램의 테스트: Gradle이 남긴 결과를 읽는 쪽.

진짜 Gradle 대신 같은 모양의 결과를 남기는 작은 가짜 실행기를 쓴다. 가짜 실행기는 진짜와 같이
- 결과를 늘 같은 폴더(build/test-results)에 테스트 클래스마다 한 파일씩 쓰고,
- 컴파일이 안 되면 아무것도 쓰지 않고 예전 결과도 그대로 둔다.
- 바뀐 게 없다고 보면 테스트를 돌리지 않고 성공으로 끝낸다(환경 변수 FAKE_GRADLE_UP_TO_DATE로 흉내 낸다).
그리고 일부러 예전 결과를 치우지 않고, 테스트가 실패해도 "BUILD SUCCESSFUL"과 종료 코드 0을 낸다.
hb는 그 폴더에 남아 있던 것을 이번 결과로 읽으면 안 되고, 항목만 읽어야 한다.
실행: python3 -m unittest discover -s tests -v   (이 파일은 pytest가 없어도 된다)
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
REPORT_DIR = "build/test-results"

FAKE_GRADLE = r'''
import os, sys
from xml.sax.saxutils import quoteattr

args = sys.argv[1:]
wanted = [args[i + 1] for i, a in enumerate(args) if a == "--tests"]
root = os.path.realpath(os.getcwd())
out_dir = os.path.join(root, "build", "test-results")
classes = {}
for base, dirs, files in os.walk(root):
    dirs[:] = [d for d in dirs if d not in (".git", ".harness", "build")]
    for name in sorted(files):
        if name.endswith(".test.txt"):
            classes[name[:-len(".test.txt")]] = os.path.join(base, name)
texts = {c: open(p, encoding="utf-8").read() for c, p in classes.items()}
if os.environ.get("FAKE_GRADLE_UP_TO_DATE"):
    print("> Task :test UP-TO-DATE\nBUILD SUCCESSFUL")
    sys.exit(0)
app = open(os.path.join(root, "app.txt"), encoding="utf-8").read()
if any("!compile-error" in t for t in [app, *texts.values()]):
    print("e: Unresolved reference\nFAILURE: Build failed with an exception.\nBUILD FAILED")
    sys.exit(1)
picked = [c for c in sorted(classes) if not wanted or c in wanted]
if not picked:
    print("No tests found for given includes\nBUILD FAILED")
    sys.exit(1)
os.makedirs(out_dir, exist_ok=True)
for cls in picked:
    rows = []
    for line in texts[cls].splitlines():
        parts = [p.strip() for p in line.split("|")]
        if not line.strip():
            continue
        name = quoteattr(parts[0])
        if parts[1] == "file-contains":
            target = os.path.join(root, parts[2])
            ok = os.path.exists(target) and parts[3] in open(target, encoding="utf-8").read()
            body = "" if ok else "<failure message=%s type=\"java.lang.AssertionError\">at body</failure>" % quoteattr(
                "java.lang.AssertionError: expected %s to contain %s" % (parts[2], parts[3]))
        elif parts[1] == "throws":
            body = "<failure message=%s type=\"x\">at body</failure>" % quoteattr(parts[2])
        elif parts[1] == "skip":
            body = "<skipped/>"
        else:
            body = ""
        rows.append("  <testcase name=%s classname=%s time=\"0.0\">%s</testcase>" % (name, quoteattr(cls), body))
    with open(os.path.join(out_dir, "TEST-%s.xml" % cls), "w", encoding="utf-8") as f:
        f.write("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<testsuite name=%s tests=\"%d\" skipped=\"0\" "
                "failures=\"0\" errors=\"0\">\n%s\n</testsuite>\n" % (quoteattr(cls), len(rows), "\n".join(rows)))
print("BUILD SUCCESSFUL")
sys.exit(0)
'''

TASK = {
    "id": "01",
    "title": "빼기 기능",
    "kind": "feature",
    "criteria": ["C1"],
    "allowed_files": ["app.txt", "tests/New.test.txt"],
    "check_args": ["--tests", "New"],
}
NEW_TEST = "빼기를 한다 (음수 포함) | file-contains | app.txt | sub\n"
NEW_ID = "New::빼기를 한다 (음수 포함)"
PASSING_NEW = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <testsuite name="New" tests="1" skipped="0" failures="0" errors="0">
      <testcase name="빼기를 한다 (음수 포함)" classname="New" time="0.0"/>
    </testsuite>
    """)
FAILING_NEW = PASSING_NEW.replace(
    'time="0.0"/>', 'time="0.0"><failure message="java.lang.AssertionError: old" type="x">old</failure></testcase>')


class GradleCase(unittest.TestCase):
    def setUp(self):
        self.tools = tempfile.mkdtemp(prefix="hb-fake-gradle-")
        self.addCleanup(shutil.rmtree, self.tools, True)
        self.fake = os.path.join(self.tools, "fake_gradle.py")
        with open(self.fake, "w", encoding="utf-8") as f:
            f.write(FAKE_GRADLE)
        self.root = tempfile.mkdtemp(prefix="hb-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.write(".gitignore", "logs/\nbuild/\n")
        self.write("app.txt", "add\n")
        self.write("tests/App.test.txt", "더하기를 한다 | file-contains | app.txt | add\n나중에 | skip\n")
        self.write("tests/Other.test.txt", "그대로다 | passed\n")
        self.write_contract()
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
            f.write(text)

    def exists(self, rel):
        return os.path.exists(os.path.join(self.root, rel))

    def write_contract(self, **changes):
        contract = {
            "version": 1,
            "runner": "gradle",
            "command": [sys.executable, self.fake],
            "report_dir": REPORT_DIR,
            "full_args": [],
            "timeout_seconds": 60,
            "test_globs": ["*.test.txt"],
        }
        contract.update(changes)
        contract = {k: v for k, v in contract.items() if v is not None}
        self.write(".harness/docs/checks.json", json.dumps(contract))

    def write_tasks(self, *tasks):
        self.write(WORK_DIR + "/tasks.json", json.dumps({"work": WORK, "tasks": list(tasks)}, ensure_ascii=False))

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def hb(self, *args, env=None):
        r = subprocess.run([sys.executable, HB, "--repo", self.root, *args], capture_output=True, text=True,
                           env=dict(os.environ, **env) if env else None)
        try:
            out = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            self.fail("hb가 판정을 내지 않음: rc=%s out=%r err=%r" % (r.returncode, r.stdout[-300:], r.stderr[-300:]))
        return r.returncode, out

    def state(self):
        with open(os.path.join(self.root, WORK_DIR, "state.json"), encoding="utf-8") as f:
            return json.load(f)

    def record(self, name):
        with open(os.path.join(self.root, WORK_DIR, "checks", name), encoding="utf-8") as f:
            return json.load(f)

    def baseline(self):
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertEqual(out["verdict"], "ok", out)
        return out

    def red(self, test=NEW_TEST):
        self.write("tests/New.test.txt", test)
        return self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")

    def green(self, app="add\nsub\n"):
        self.write("app.txt", app)
        return self.hb("check", "--work", WORK, "--task", "01", "--phase", "green")

    # --- 정상 흐름 ---
    def test_happy_path_reads_every_result_file(self):
        out = self.baseline()
        self.assertIn("테스트 3개", out["summary"])  # 두 클래스의 결과 파일을 모아 읽는다
        record = self.record("001-baseline.json")
        self.assertEqual((record["runner"], record["total"]), ("gradle", 3))
        self.assertEqual(record["counts"], {"passed": 2, "skipped": 1, "failure": 0, "error": 0})
        self.assertTrue(record["report"].endswith(".xml"), record["report"])
        self.assertTrue(self.exists(WORK_DIR + "/" + record["report"]))  # 읽은 것은 작업 폴더에 남는다
        rc, out = self.red()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertEqual(out["failed"], [NEW_ID])
        rc, out = self.green()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertIn("새로 깨진 것 없음", out["summary"])
        self.git("add", "app.txt", "tests/New.test.txt")
        rc, out = self.hb("done", "--work", WORK, "--task", "01")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)

    def test_green_stops_when_implementation_breaks_another_class(self):
        self.baseline()
        self.red()
        rc, out = self.green(app="sub\n")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertEqual(out["new_broken"], ["App::더하기를 한다"])

    # --- 그 폴더에 남아 있던 결과는 이번 결과가 아니다 ---
    def test_results_left_from_before_are_not_read_when_the_build_fails(self):
        """전부 통과한 결과가 폴더에 남아 있어도, 컴파일이 안 돼 이번 결과가 없으면 통과가 아니다."""
        self.baseline()
        rc, out = self.red()
        self.assertEqual(out["verdict"], "ok", out)
        rc, out = self.green()
        self.assertEqual(out["verdict"], "ok", out)
        for cls in ("App", "Other", "New"):  # 통과한 결과가 폴더에 남아 있다
            self.assertTrue(self.exists(REPORT_DIR + "/TEST-%s.xml" % cls), cls)
        rc, out = self.green(app="add\nsub\n!compile-error\n")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)

    def test_passing_result_planted_in_the_folder_is_not_accepted_as_green(self):
        """미리 들어 있던 통과 결과가 있어도, 이번 실행이 테스트를 돌리지 않았으면 통과로 치지 않는다."""
        self.baseline()
        rc, out = self.red()
        self.assertEqual(out["verdict"], "ok", out)
        self.write("app.txt", "add\nsub\n")
        self.write(REPORT_DIR + "/TEST-New.xml", PASSING_NEW)
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "green",
                          env={"FAKE_GRADLE_UP_TO_DATE": "1"})
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)

    def test_failing_result_planted_in_the_folder_is_not_accepted_as_red(self):
        self.baseline()
        self.write("tests/New.test.txt", NEW_TEST)
        self.write(REPORT_DIR + "/TEST-New.xml", FAILING_NEW)
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "red",
                          env={"FAKE_GRADLE_UP_TO_DATE": "1"})
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)

    def test_only_result_files_are_removed_from_the_folder(self):
        """치우는 것은 그 폴더 바로 아래의 결과 파일(.xml)뿐이다. 다른 파일과 하위 폴더는 건드리지 않는다."""
        self.write(REPORT_DIR + "/binary/results.bin", "keep")
        self.write(REPORT_DIR + "/notes.txt", "keep")
        self.write(REPORT_DIR + "/binary/TEST-Deep.xml", PASSING_NEW)
        self.write(REPORT_DIR + "/TEST-Gone.xml", PASSING_NEW.replace("New", "Gone"))
        self.write(REPORT_DIR + "/folder-named.xml/inner.txt", "keep")
        out = self.baseline()
        self.assertIn("테스트 3개", out["summary"])  # 남아 있던 Gone은 세지 않는다
        self.assertFalse(self.exists(REPORT_DIR + "/TEST-Gone.xml"))
        for kept in ("binary/results.bin", "notes.txt", "binary/TEST-Deep.xml", "folder-named.xml/inner.txt"):
            self.assertTrue(self.exists(REPORT_DIR + "/" + kept), kept)

    # --- 실행되지 않은 것은 통과가 아니다 ---
    def test_no_matching_test_is_not_run(self):
        self.baseline()
        self.write_tasks(dict(TASK, check_args=["--tests", "NoSuchClass"]))
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)

    def test_test_code_that_does_not_compile_is_not_run(self):
        self.baseline()
        rc, out = self.red("!compile-error\n" + NEW_TEST)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)

    def test_result_file_that_cannot_be_read_is_not_run(self):
        self.write_contract(command=[sys.executable, "-c", (
            "import os; os.makedirs('build/test-results', exist_ok=True); "
            "open('build/test-results/TEST-A.xml', 'w').write('<testsuite><testcase name=\"a\" classname=\"A\"/>')")])
        self.commit("끝이 잘린 결과 파일을 쓰는 명령")
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)

    # --- 계약 ---
    def test_contract_without_command_or_report_dir_stops_before_running(self):
        for missing in ("command", "report_dir"):
            self.write_contract(**{missing: None})
            rc, out = self.hb("baseline", "--work", WORK)
            self.assertNotEqual(rc, 0, missing)
            self.assertEqual(out["verdict"], "stop", out)
            self.assertIn(missing, out["reason"])
            self.assertFalse(self.exists(WORK_DIR + "/logs"))

    def test_report_dir_that_git_does_not_ignore_stops_and_removes_nothing(self):
        """결과 폴더를 잘못 적으면(예: 소스 폴더) 그 안의 파일을 지우게 된다. git 제외 폴더가 아니면 시작하지 않는다."""
        self.write("tests/layout.xml", "<keep/>")
        self.write_contract(report_dir="tests")
        self.commit("결과 폴더를 소스 폴더로 잘못 적음")
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("report_dir", out["reason"])
        self.assertTrue(self.exists("tests/layout.xml"))
        self.assertFalse(self.exists(WORK_DIR + "/logs"))

    def test_report_dir_outside_the_repo_stops_and_removes_nothing(self):
        outside = tempfile.mkdtemp(prefix="hb-outside-")
        self.addCleanup(shutil.rmtree, outside, True)
        victim = os.path.join(outside, "TEST-victim.xml")
        with open(victim, "w", encoding="utf-8") as f:
            f.write(PASSING_NEW)
        os.symlink(outside, os.path.join(self.root, "build"))  # git 제외인 이름이지만 실제로는 저장소 밖
        for bad in (outside, os.path.relpath(outside, self.root), "build"):
            self.write_contract(report_dir=bad)
            rc, out = self.hb("baseline", "--work", WORK)
            self.assertNotEqual(rc, 0, bad)
            self.assertEqual(out["verdict"], "stop", out)
            self.assertIn("report_dir", out["reason"])
            self.assertTrue(os.path.exists(victim), bad)


def load_hb():
    spec = importlib.util.spec_from_file_location("hb", HB)
    hb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hb)
    return hb


class GatherResults(unittest.TestCase):
    def gather(self, files):
        hb = load_hb()
        d = tempfile.mkdtemp(prefix="hb-test-")
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, "results"))
        for name, text in files.items():
            with open(os.path.join(d, "results", name), "w", encoding="utf-8") as f:
                f.write(text)
        report = os.path.join(d, "report.xml")
        hb.gather_junit(os.path.join(d, "results"), report)
        return report, hb

    def test_same_name_in_two_files_keeps_the_worse_result(self):
        for names in (("TEST-a.xml", "TEST-b.xml"), ("TEST-b.xml", "TEST-a.xml")):
            report, hb = self.gather({names[0]: PASSING_NEW, names[1]: FAILING_NEW})
            self.assertEqual([(c[0], c[1]) for c in hb.parse_junit(report)], [(NEW_ID, "failure")], names)

    def test_folder_without_result_files_makes_no_report(self):
        report, hb = self.gather({"notes.txt": "x"})
        self.assertFalse(os.path.exists(report))


if __name__ == "__main__":
    unittest.main()
