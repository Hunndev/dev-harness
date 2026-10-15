"""hb 프로그램의 테스트: Jest 보고서를 읽는 쪽.

진짜 Jest 대신 같은 모양의 보고서(--json)를 내는 작은 가짜 실행기를 쓴다.
가짜 실행기는 합계 숫자와 종료 코드를 일부러 "전부 통과"로 낸다. hb는 항목만 읽어야 한다.
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
FILE_FAILED = "(파일 실행 실패)"

FAKE_JEST = r'''
import json, os, sys

args = sys.argv[1:]
out = [a.split("=", 1)[1] for a in args if a.startswith("--outputFile=")][0]
patterns = [a for a in args if not a.startswith("--")]
root = os.path.realpath(os.getcwd())
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
        items, load_error = [], None
        for line in open(path, encoding="utf-8").read().splitlines():
            parts = [p.strip() for p in line.split("|")]
            if not line.strip():
                continue
            if parts[0].startswith("!load-error"):
                load_error = parts[0][len("!load-error"):].strip()
            elif parts[0].startswith("!requires"):
                need = parts[0][len("!requires"):].strip()
                if not os.path.exists(os.path.join(root, need)):
                    load_error = "Cannot find module './%s' from '%s'" % (need, rel)
            elif parts[1] == "file-contains":
                target = os.path.join(root, parts[2])
                ok = os.path.exists(target) and parts[3] in open(target, encoding="utf-8").read()
                items.append((parts[0], "passed" if ok else "failed",
                              [] if ok else ["Error: expected %s to contain %s\n    at body" % (parts[2], parts[3])]))
            elif parts[1] == "throws":
                items.append((parts[0], "failed", [parts[2] + "\n    at body"]))
            else:
                items.append((parts[0], {"skip": "pending"}.get(parts[1], parts[1]), []))
        if load_error is not None:
            results.append({"name": path, "status": "failed", "assertionResults": [],
                            "message": "  ● Test suite failed to run\n\n    " + load_error + "\n"})
        else:
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
    "id": "01",
    "title": "빼기 기능",
    "kind": "feature",
    "criteria": ["C1"],
    "allowed_files": ["app.txt", "helper.txt", "tests/new.test.txt"],
    "check_args": ["tests/new.test.txt"],
}
NEW_TEST = "subtracts | file-contains | app.txt | sub\n"


def load_hb():
    spec = importlib.util.spec_from_file_location("hb", HB)
    hb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hb)
    return hb


class JestCase(unittest.TestCase):
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
        self.write("app.txt", "add\n")
        self.write("helper.txt", "helper\n")
        self.write("tests/app.test.txt", "!requires helper.txt\nadds | file-contains | app.txt | add\n")
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
            f.write(textwrap.dedent(text))

    def write_contract(self, **changes):
        contract = {
            "version": 1,
            "runner": "jest",
            "command": [sys.executable, self.fake],
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

    def hb(self, *args):
        r = subprocess.run([sys.executable, HB, "--repo", self.root, *args], capture_output=True, text=True)
        try:
            out = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            self.fail("hb가 판정을 내지 않음: rc=%s out=%r err=%r" % (r.returncode, r.stdout[-300:], r.stderr[-300:]))
        return r.returncode, out

    def state(self):
        with open(os.path.join(self.root, WORK_DIR, "state.json"), encoding="utf-8") as f:
            return json.load(f)

    def baseline(self):
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertEqual(out["verdict"], "ok", out)
        return out

    def red(self, test=NEW_TEST):
        self.write("tests/new.test.txt", test)
        return self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")

    def green(self, app="add\nsub\n"):
        self.write("app.txt", app)
        return self.hb("check", "--work", WORK, "--task", "01", "--phase", "green")

    # --- 정상 흐름 ---
    def test_happy_path_red_green_done(self):
        out = self.baseline()
        self.assertIn("테스트 1개", out["summary"])
        rc, out = self.red()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertEqual(out["failed"], ["tests/new.test.txt::subtracts"])
        rc, out = self.green()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertIn("새로 깨진 것 없음", out["summary"])
        self.git("add", "app.txt", "tests/new.test.txt")
        rc, out = self.hb("done", "--work", WORK, "--task", "01")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)

    # --- 파일이 통째로 실행되지 못한 경우 (항목이 0개로 나온다) ---
    def test_green_stops_when_another_test_file_no_longer_loads(self):
        """구현이 다른 테스트 파일을 못 읽게 만들면, 그 파일의 항목이 0개여도 새로 깨진 것으로 잡는다."""
        self.baseline()
        rc, out = self.red()
        self.assertEqual(out["verdict"], "ok", out)
        os.remove(os.path.join(self.root, "helper.txt"))
        rc, out = self.green()
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertEqual(out["new_broken"], ["tests/app.test.txt::" + FILE_FAILED])

    def test_red_is_not_accepted_when_the_test_file_does_not_load(self):
        self.baseline()
        rc, out = self.red("!requires not-yet.txt\n" + NEW_TEST)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("준비 단계", out["reason"])

    def test_file_that_never_loaded_is_known_broken_and_not_counted_as_new(self):
        self.write("tests/old.test.txt", "!load-error boom\n")
        self.commit("원래부터 못 읽는 테스트 파일")
        self.baseline()
        self.assertEqual(self.state()["baseline"]["broken"], ["tests/old.test.txt::" + FILE_FAILED])
        rc, out = self.red()
        self.assertEqual(out["verdict"], "ok", out)
        rc, out = self.green()
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        self.assertIn("원래 깨져 있던 것 1건", out["summary"])

    # --- 실패 확인이 받아들이지 않는 것 ---
    def test_red_is_not_accepted_when_test_already_passes(self):
        self.baseline()
        self.write("app.txt", "add\nsub\n")
        rc, out = self.red()
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("실패한 테스트가 없음", out["reason"])

    def test_red_is_not_accepted_when_everything_is_pending_or_todo(self):
        self.baseline()
        rc, out = self.red("later | skip\nsomeday | todo\n")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("건너뜀", out["reason"])

    def test_red_is_not_accepted_when_body_fails_on_a_missing_module(self):
        self.baseline()
        rc, out = self.red("subtracts | throws | Error: Cannot find module './sub' from 'tests/new.test.txt'\n")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("가져오기", out["reason"])

    def test_green_stops_when_implementation_breaks_another_test(self):
        self.baseline()
        self.red()
        rc, out = self.green(app="sub\n")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertEqual(out["new_broken"], ["tests/app.test.txt::adds"])

    # --- 실행되지 않은 것은 통과가 아니다 ---
    def test_no_matching_test_is_not_run(self):
        self.baseline()
        self.write_tasks(dict(TASK, check_args=["tests/no-such-file"]))
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)

    def test_command_that_writes_no_report_is_not_run(self):
        self.write_contract(command=[sys.executable, "-c", "pass"])
        self.commit("보고서를 쓰지 않는 명령")
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)

    def test_command_that_does_not_exist_is_not_run(self):
        self.write_contract(command=["no-such-command-93417"])
        self.commit("없는 명령")
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "not_run", out)

    # --- 계약 ---
    def test_jest_contract_without_command_stops_before_running(self):
        self.write_contract(command=None)
        self.commit("명령이 없는 계약")
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("command", out["reason"])
        self.assertFalse(os.path.exists(os.path.join(self.root, WORK_DIR, "logs")))

    def test_unknown_runner_stops(self):
        self.write_contract(runner="mocha")
        self.commit("모르는 실행기")
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)

    def test_baseline_stops_when_only_log_files_are_ignored(self):
        """보고서는 .json이다. *.log만 제외하는 저장소에서는 보고서가 git에 들어갈 수 있으므로 시작하지 않는다."""
        self.write(".gitignore", "*.log\n")
        self.commit("로그 파일만 제외")
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertIn("logs", out["reason"])
        self.assertFalse(os.path.exists(os.path.join(self.root, WORK_DIR, "logs")))

    # --- 기록에 남기는 것 ---
    def test_records_use_repo_relative_names_and_keep_messages_out(self):
        self.write("tests/old.test.txt", "leaky | throws | Error: MARKER_IN_MESSAGE_93417\n")
        self.commit("메시지에 표지가 든 깨진 테스트")
        self.baseline()
        self.assertEqual(self.state()["baseline"]["broken"], ["tests/old.test.txt::leaky"])
        work = os.path.join(self.root, WORK_DIR)
        kept = [os.path.join(work, "state.json")]
        kept += [os.path.join(work, "checks", f) for f in os.listdir(os.path.join(work, "checks"))]
        self.assertGreaterEqual(len(kept), 2)
        for path in kept:
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertNotIn("MARKER_IN_MESSAGE_93417", text, path)
            self.assertNotIn(os.path.realpath(self.root), text, path)
            self.assertNotIn(self.root, text, path)
        with open(os.path.join(work, "checks", "001-baseline.json"), encoding="utf-8") as f:
            record = json.load(f)
        self.assertEqual(record["runner"], "jest")
        self.assertTrue(record["report"].endswith(".json"), record["report"])


class ParseJestReport(unittest.TestCase):
    def parse(self, results, **top):
        hb = load_hb()
        d = os.path.realpath(tempfile.mkdtemp(prefix="hb-test-"))
        self.addCleanup(shutil.rmtree, d, True)
        for r in results:
            r["name"] = os.path.join(d, r["name"])
        path = os.path.join(d, "report.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dict({"testResults": results}, **top), f)
        return sorted((c[0], c[1]) for c in hb.parse_jest(path, d))

    def item(self, name, status, messages=()):
        return {"ancestorTitles": [], "title": name, "fullName": name, "status": status,
                "failureMessages": list(messages)}

    def test_reads_entries_by_name_not_the_totals(self):
        """합계가 '전부 통과'라고 해도 항목을 읽는다."""
        cases = self.parse(
            [{"name": "src/a.test.js", "status": "passed", "message": "", "assertionResults": [
                self.item("outer adds", "passed"),
                self.item("outer breaks", "failed", ["Error: expect(received).toBe(expected)\n    at x"]),
                self.item("outer later", "pending"),
                self.item("outer someday", "todo"),
            ]}],
            success=True, numTotalTests=4, numPassedTests=4, numFailedTests=0)
        self.assertEqual(cases, [
            ("src/a.test.js::outer adds", "passed"),
            ("src/a.test.js::outer breaks", "failure"),
            ("src/a.test.js::outer later", "skipped"),
            ("src/a.test.js::outer someday", "skipped"),
        ])

    def test_file_that_failed_to_run_becomes_one_error_entry(self):
        cases = self.parse([
            {"name": "src/ok.test.js", "status": "passed", "message": "", "assertionResults": [self.item("ok", "passed")]},
            {"name": "src/broken.test.js", "status": "failed", "assertionResults": [],
             "message": "  ● Test suite failed to run\n\n    Cannot find module './x' from 'src/broken.test.js'\n"},
        ])
        self.assertEqual(cases, [
            ("src/broken.test.js::" + FILE_FAILED, "error"),
            ("src/ok.test.js::ok", "passed"),
        ])

    def test_failed_file_with_only_passing_entries_also_gets_an_error_entry(self):
        """항목은 다 통과인데 파일이 실패로 끝난 경우(예: 정리 단계 오류)도 놓치지 않는다."""
        cases = self.parse([
            {"name": "a.test.js", "status": "failed", "message": "  ● Test suite failed to run\n\n    boom\n",
             "assertionResults": [self.item("ok", "passed")]},
        ])
        self.assertEqual(cases, [("a.test.js::" + FILE_FAILED, "error"), ("a.test.js::ok", "passed")])

    def test_failed_file_with_a_failed_entry_gets_no_extra_entry(self):
        cases = self.parse([
            {"name": "a.test.js", "status": "failed", "message": "x",
             "assertionResults": [self.item("bad", "failed", ["Error: no"])]},
        ])
        self.assertEqual(cases, [("a.test.js::bad", "failure")])

    def test_same_name_twice_in_a_file_keeps_the_worse_result(self):
        for order in (("passed", "failed"), ("failed", "passed")):
            cases = self.parse([
                {"name": "a.test.js", "status": "failed", "message": "x", "assertionResults": [
                    self.item("same name", order[0], ["Error: no"] if order[0] == "failed" else []),
                    self.item("same name", order[1], ["Error: no"] if order[1] == "failed" else []),
                ]},
            ])
            self.assertEqual(cases, [("a.test.js::same name", "failure")], order)

    def test_unknown_status_is_not_treated_as_passed(self):
        cases = self.parse([
            {"name": "a.test.js", "status": "passed", "message": "",
             "assertionResults": [self.item("odd", "some-new-status")]},
        ])
        self.assertEqual(cases, [("a.test.js::odd", "error")])


if __name__ == "__main__":
    unittest.main()
