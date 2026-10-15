"""hb 프로그램의 테스트: xcodebuild가 남긴 결과 묶음(.xcresult)을 읽는 쪽.

진짜 xcodebuild와 xcrun 대신 같은 모양으로 움직이는 작은 가짜 둘을 쓴다. 가짜 xcodebuild는 진짜와 같이
- 결과 묶음(폴더)을 -resultBundlePath 로 받은 자리에 만들고, 그 자리에 이미 무엇이 있으면 돌지 않는다.
- 컴파일이 안 돼도, 고른 이름에 맞는 테스트가 없어도 결과 묶음은 만든다(테스트 항목만 없다).
- 맞는 테스트가 하나도 없으면 "TEST SUCCEEDED"와 종료 코드 0을 낸다.
그리고 일부러 테스트가 실패해도 "TEST SUCCEEDED"와 종료 코드 0을 낸다. hb는 항목만 읽어야 한다.
가짜 xcrun은 PATH 앞에 두며, 결과 묶음 안의 내용을 진짜 xcresulttool과 같은 모양의 JSON으로 낸다.
실행: python3 -m unittest discover -s tests -v   (이 파일은 pytest가 없어도 된다)
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

FAKE_XCODEBUILD = r'''
import json, os, sys

args = sys.argv[1:]
only = [a.split(":", 1)[1] for a in args if a.startswith("-only-testing:")]
bundle = next((args[i + 1] for i, a in enumerate(args[:-1]) if a == "-resultBundlePath"), None)
root = os.path.realpath(os.getcwd())
if bundle is None or os.environ.get("FAKE_XCODEBUILD_NO_BUNDLE"):
    print("** TEST SUCCEEDED **")
    sys.exit(0)
if os.path.exists(bundle):
    print("error: Existing file at -resultBundlePath")
    sys.exit(64)
os.makedirs(bundle)

def save(nodes):
    with open(os.path.join(bundle, "tests.json"), "w", encoding="utf-8") as f:
        json.dump({"devices": [], "testPlanConfigurations": [], "testNodes": nodes}, f, ensure_ascii=False)

suites = {}
for base, dirs, files in os.walk(root):
    dirs[:] = [d for d in dirs if d not in (".git", ".harness")]
    for name in sorted(files):
        if name.endswith(".test.txt"):
            suites[name[:-len(".test.txt")]] = open(os.path.join(base, name), encoding="utf-8").read()
app = open(os.path.join(root, "app.txt"), encoding="utf-8").read()
if any("!compile-error" in t for t in [app, *suites.values()]):
    save([])
    print("error: cannot find 'x' in scope\n** TEST FAILED **")
    sys.exit(65)

def has(path, text):
    target = os.path.join(root, path)
    return os.path.exists(target) and text in open(target, encoding="utf-8").read()

def failure(text):
    return {"nodeType": "Failure Message", "name": "AppTests.swift:3: Expectation failed: " + text}

suite_nodes = []
for suite in sorted(suites):
    cases = []
    for line in suites[suite].splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("|")]
        func, _, title = [p.strip() for p in parts[0].partition("@")]
        if only and not any(o in ("AppTests", "AppTests/" + suite, "AppTests/%s/%s" % (suite, func)) for o in only):
            continue
        case = {"nodeType": "Test Case", "name": title or func, "nodeIdentifier": "%s/%s" % (suite, func)}
        how = parts[1]
        if how == "file-contains":
            ok = has(parts[2], parts[3])
            case["result"] = "Passed" if ok else "Failed"
            if not ok:
                case["children"] = [failure("%s contains %s" % (parts[2], parts[3]))]
        elif how == "each":
            rows = []
            for value in parts[3].split(","):
                ok = has(parts[2], value)
                rows.append({"nodeType": "Arguments", "name": '"%s"' % value, "result": "Passed" if ok else "Failed",
                             "children": [] if ok else [failure("%s contains %s" % (parts[2], value))]})
            case["result"] = "Passed" if all(r["result"] == "Passed" for r in rows) else "Failed"
            case["children"] = rows
        elif how == "skip":
            case["result"] = "Skipped"
            case["children"] = [{"nodeType": "Failure Message", "name": "Test skipped"}]
        elif how == "known":
            case["result"] = "Expected Failure"
        elif how == "odd":
            case["result"] = parts[2]
        elif how != "no-result":
            case["result"] = "Passed"
        cases.append(case)
    if cases:
        suite_nodes.append({"nodeType": "Test Suite", "name": suite, "children": cases})
if suite_nodes:
    save([{"nodeType": "Test Plan", "name": "App", "result": "Passed", "children": [
        {"nodeType": "Unit test bundle", "name": "AppTests", "result": "Passed", "children": suite_nodes}]}])
else:
    save([{"nodeType": "Test Plan", "name": "App", "result": "unknown"}])
print("** TEST SUCCEEDED **")
sys.exit(0)
'''

FAKE_XCRUN = r'''
import os, sys, time

args = sys.argv[1:]
if args[:4] != ["xcresulttool", "get", "test-results", "tests"] or "--path" not in args:
    sys.stderr.write("가짜 xcrun: 모르는 호출 %r\n" % (args,))
    sys.exit(2)
mode = os.environ.get("FAKE_XCRUN")
if mode == "fail":  # 실패했는데 그럴듯한 출력이 남은 경우
    sys.stdout.write('{"testNodes": [{"nodeType": "Test Case", "name": "x()", "nodeIdentifier": "S/x()", "result": "Passed"}]}')
    sys.exit(1)
if mode == "garbage":
    sys.stdout.write("not json")
    sys.exit(0)
if mode == "hang":
    time.sleep(30)
try:
    with open(os.path.join(args[args.index("--path") + 1], "tests.json"), encoding="utf-8") as f:
        sys.stdout.write(f.read())
except OSError:
    sys.stderr.write("Error: not a result bundle\n")
    sys.exit(1)
'''

TASK = {
    "id": "01",
    "title": "빼기 기능",
    "kind": "feature",
    "criteria": ["C1"],
    "allowed_files": ["app.txt", "tests/New.test.txt"],
    "check_args": ["-only-testing:AppTests/New"],
}
NEW_TEST = "subtracts() | file-contains | app.txt | sub\n"
NEW_ID = "AppTests/New/subtracts()"


class XcodebuildCase(unittest.TestCase):
    def setUp(self):
        self.tools = tempfile.mkdtemp(prefix="hb-fake-xcode-")
        self.addCleanup(shutil.rmtree, self.tools, True)
        self.fake = os.path.join(self.tools, "fake_xcodebuild.py")
        with open(self.fake, "w", encoding="utf-8") as f:
            f.write(FAKE_XCODEBUILD)
        with open(os.path.join(self.tools, "fake_xcrun.py"), "w", encoding="utf-8") as f:
            f.write(FAKE_XCRUN)
        xcrun = os.path.join(self.tools, "xcrun")  # hb는 xcrun을 이름으로 부른다. PATH 앞에 둔 이것이 잡힌다
        with open(xcrun, "w", encoding="utf-8") as f:
            f.write('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, os.path.join(self.tools, "fake_xcrun.py")))
        os.chmod(xcrun, 0o755)
        self.root = tempfile.mkdtemp(prefix="hb-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.write(".gitignore", "logs/\n")
        self.write("app.txt", "add\n")
        self.write("tests/App.test.txt", "adds() | file-contains | app.txt | add\nlater() | skip\n")
        self.write("tests/Other.test.txt", "stays() | passed\n")
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
            "runner": "xcodebuild",
            "command": [sys.executable, self.fake, "test", "-scheme", "App"],
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
        full_env = dict(os.environ, PATH=self.tools + os.pathsep + os.environ["PATH"], **(env or {}))
        r = subprocess.run([sys.executable, HB, "--repo", self.root, *args], capture_output=True, text=True, env=full_env)
        try:
            out = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            self.fail("hb가 판정을 내지 않음: rc=%s out=%r err=%r" % (r.returncode, r.stdout[-300:], r.stderr[-300:]))
        return r.returncode, out

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
    def test_happy_path_reads_the_result_bundle(self):
        out = self.baseline()
        self.assertIn("테스트 3개", out["summary"])
        record = self.record("001-baseline.json")
        self.assertEqual((record["runner"], record["total"]), ("xcodebuild", 3))
        self.assertEqual(record["counts"], {"passed": 2, "skipped": 1, "failure": 0, "error": 0})
        self.assertTrue(record["report"].endswith(".xcresult"), record["report"])
        self.assertTrue(os.path.isdir(os.path.join(self.root, WORK_DIR, record["report"])))  # 읽은 묶음은 남는다
        rc, out = self.red()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertEqual(out["failed"], [NEW_ID])  # 이름은 -only-testing 에 적는 모양과 같다
        rc, out = self.green()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertIn("새로 깨진 것 없음", out["summary"])
        self.git("add", "app.txt", "tests/New.test.txt")
        rc, out = self.hb("done", "--work", WORK, "--task", "01")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertEqual(out["add"], [WORK_DIR])

    def test_what_is_read_from_the_bundle_is_not_left_as_a_file(self):
        """뽑아 읽은 내용을 파일로 남기지 않는다. 작업 폴더에서 git 제외가 아닌 새 파일이 생기면 안 된다."""
        self.write(".gitignore", "*.log\n*.xcresult\n")  # 결과 묶음과 화면 기록만 제외하는 저장소
        self.commit("git 제외를 좁힘")
        self.baseline()
        left = self.git("status", "--porcelain", "--untracked-files=all").splitlines()
        self.assertEqual(sorted(line[3:] for line in left),
                         [WORK_DIR + "/checks/001-baseline.json", WORK_DIR + "/state.json"])

    def test_green_stops_when_implementation_breaks_another_suite(self):
        self.baseline()
        self.red()
        rc, out = self.green(app="sub\n")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertEqual(out["new_broken"], ["AppTests/App/adds()"])

    # --- 실행되지 않은 것은 통과가 아니다 ---
    def test_code_that_does_not_compile_is_not_run(self):
        """컴파일이 안 돼도 결과 묶음은 생긴다. 그 안에 테스트 항목이 없으면 미실행이다."""
        self.baseline()
        rc, out = self.red("!compile-error\n" + NEW_TEST)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)
        rc, out = self.red()
        self.assertEqual(out["verdict"], "ok", out)
        rc, out = self.green(app="add\nsub\n!compile-error\n")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)

    def test_no_matching_test_is_not_run_even_though_the_tool_says_succeeded(self):
        self.baseline()
        self.write_tasks(dict(TASK, check_args=["-only-testing:AppTests/NoSuchSuite"]))
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)
        self.assertEqual(self.record("002-01-red.json")["exit_code"], 0)  # 도구는 성공이라고 했다

    def test_no_result_bundle_is_not_run(self):
        rc, out = self.hb("baseline", "--work", WORK, env={"FAKE_XCODEBUILD_NO_BUNDLE": "1"})
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)

    def test_result_tool_that_fails_is_not_run(self):
        """결과 묶음을 읽는 도구가 실패하거나, 읽을 수 없는 것을 내거나, 끝나지 않으면 미실행이다."""
        self.write_contract(timeout_seconds=3)
        self.commit("제한 시간을 줄임")
        for mode in ("fail", "garbage", "hang"):
            rc, out = self.hb("baseline", "--work", WORK, env={"FAKE_XCRUN": mode})
            self.assertNotEqual(rc, 0, mode)
            self.assertEqual(out["verdict"], "not_run", (mode, out))
            self.assertFalse(self.exists(WORK_DIR + "/state.json"), mode)

    # --- 결과 종류 ---
    def test_unknown_result_is_not_counted_as_passed(self):
        self.write("tests/Other.test.txt", "stays() | passed\nglitch() | odd | Glitched\nnone() | odd | unknown\n"
                                           "blank() | no-result\n")
        self.commit("모르는 결과가 섞임")
        out = self.baseline()
        self.assertEqual(out["broken"], ["AppTests/Other/blank()", "AppTests/Other/glitch()", "AppTests/Other/none()"])
        self.assertEqual(self.record("001-baseline.json")["counts"],
                         {"passed": 2, "skipped": 1, "failure": 0, "error": 3})

    def test_expected_failure_is_neither_a_pass_nor_a_failure(self):
        self.write("tests/Other.test.txt", "stays() | passed\nknown() | known\n")
        self.commit("알고 있는 실패")
        out = self.baseline()
        self.assertEqual(out["broken"], [])
        self.assertEqual(self.record("001-baseline.json")["counts"],
                         {"passed": 2, "skipped": 2, "failure": 0, "error": 0})
        rc, out = self.red("subtracts() | known\n")  # 실패하리라고 적어 둔 테스트는 실패 확인이 못 된다
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("건너뜀", out["reason"])

    def test_test_with_many_arguments_is_one_item_and_fails_if_any_argument_fails(self):
        self.baseline()
        rc, out = self.red("subtracts() | each | app.txt | add,sub\n")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertEqual(out["failed"], [NEW_ID])
        self.assertEqual(self.record("002-01-red.json")["total"], 1)
        rc, out = self.green()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)

    def test_two_tests_with_the_same_title_stay_two_items(self):
        """화면에 보이는 이름이 같아도 다른 테스트다. 통과한 쪽이 실패한 쪽을 가리면 안 된다."""
        self.write("tests/Other.test.txt", "a() @ 같은 이름 | passed\nb() @ 같은 이름 | file-contains | app.txt | none\n")
        self.commit("이름이 같은 테스트 둘")
        out = self.baseline()
        self.assertIn("테스트 4개", out["summary"])
        self.assertEqual(out["broken"], ["AppTests/Other/b()"])

    # --- 계약과 git 제외 ---
    def test_result_bundles_must_be_ignored_by_git(self):
        self.write(".gitignore", "*.log\n")
        self.commit("결과 묶음이 git 제외가 아님")
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn(".xcresult", out["reason"])
        self.assertFalse(self.exists(WORK_DIR + "/logs"))

    def test_contract_without_command_stops_before_running(self):
        self.write_contract(command=None)
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("command", out["reason"])
        self.assertFalse(self.exists(WORK_DIR + "/logs"))


def load_hb():
    spec = importlib.util.spec_from_file_location("hb", HB)
    hb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hb)
    return hb


def case(identifier, result, name=None, children=None):
    node = {"nodeType": "Test Case", "name": name or identifier.split("/")[-1], "result": result}
    if identifier:
        node["nodeIdentifier"] = identifier
    if children:
        node["children"] = children
    return node


def plan(*bundles):
    return {"devices": [], "testPlanConfigurations": [], "testNodes": [
        {"nodeType": "Test Plan", "name": "App", "result": "Failed", "children": list(bundles)}]}


def bundle(name, *suites):
    return {"nodeType": "Unit test bundle", "name": name, "children": list(suites)}


def suite(name, *children):
    return {"nodeType": "Test Suite", "name": name, "children": list(children)}


class ReadTestTree(unittest.TestCase):
    """진짜 xcresulttool이 내는 나무 모양에서 테스트 항목을 뽑는 부분."""

    def read(self, data):
        return sorted(load_hb().xcresult_cases(data))

    def test_real_shape(self):
        # 진짜 도구로 본 모양: 묶음 안의 묶음, 인자가 여럿인 테스트, 건너뜀의 사유가 "Failure Message"로 달린다
        data = plan(bundle("AppTests", suite(
            "표시 이름이 있는 묶음",
            suite("Inner", case("NamedSuite/Inner/nested()", "Passed")),
            case("NamedSuite/passes()", "Passed"),
            case("NamedSuite/each(_:)", "Failed", children=[
                {"nodeType": "Arguments", "name": "1", "result": "Passed"},
                {"nodeType": "Arguments", "name": "2", "result": "Failed", "children": [
                    {"nodeType": "Failure Message", "name": "T.swift:19: Expectation failed: (n → 2) != 2\n둘째 줄"}]}]),
            case("NamedSuite/off()", "Skipped", children=[{"nodeType": "Failure Message", "name": "Test skipped: 꺼 둠"}]),
            case("NamedSuite/known()", "Expected Failure"))))
        self.assertEqual(self.read(data), [
            ("AppTests/NamedSuite/Inner/nested()", "passed", ""),
            ("AppTests/NamedSuite/each(_:)", "failure", "T.swift:19: Expectation failed: (n → 2) != 2"),
            ("AppTests/NamedSuite/known()", "skipped", ""),
            ("AppTests/NamedSuite/off()", "skipped", "Test skipped: 꺼 둠"),
            ("AppTests/NamedSuite/passes()", "passed", ""),
        ])

    def test_plan_without_test_cases_reads_as_nothing(self):
        hb = load_hb()
        self.assertEqual(hb.xcresult_cases({"testNodes": []}), [])
        self.assertEqual(hb.xcresult_cases({"testNodes": [{"nodeType": "Test Plan", "name": "App", "result": "unknown"}]}), [])

    def test_same_identifier_twice_keeps_the_worse_result(self):
        for results in (("Passed", "Failed"), ("Failed", "Passed")):
            data = plan(bundle("AppTests", suite("S", case("S/a()", results[0]))),
                        bundle("AppTests", suite("S", case("S/a()", results[1]))))
            self.assertEqual([(c[0], c[1]) for c in self.read(data)], [("AppTests/S/a()", "failure")], results)

    def test_same_identifier_in_two_bundles_stays_two_items(self):
        data = plan(bundle("AppTests", suite("S", case("S/a()", "Passed"))),
                    bundle("OtherTests", suite("S", case("S/a()", "Failed"))))
        self.assertEqual([(c[0], c[1]) for c in self.read(data)],
                         [("AppTests/S/a()", "passed"), ("OtherTests/S/a()", "failure")])

    def test_case_without_identifier_is_named_by_its_place_in_the_tree(self):
        data = plan(bundle("AppTests", suite("S", case("", "Passed", name="같은 이름")),
                           suite("T", case("", "Failed", name="같은 이름"))))
        self.assertEqual([(c[0], c[1]) for c in self.read(data)],
                         [("AppTests/S/같은 이름", "passed"), ("AppTests/T/같은 이름", "failure")])


if __name__ == "__main__":
    unittest.main()
