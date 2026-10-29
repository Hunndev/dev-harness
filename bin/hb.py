#!/usr/bin/env python3
"""hb: 검사를 직접 돌려 판정하고 기록하는 작은 프로그램.

명령은 다섯이다.
  preflight 시작 전 검증. 검사를 돌리지 않고, 돌려도 완료 증거가 안 되는 경우(환경, 증거 경로, 범위, 시간)를
            미리 막는다. 제품 결과, 환경, 보조검증을 따로 적는다. 기록을 만들거나 고치지 않는다.
  baseline  바탕 검사. 작업 트리가 깨끗한지 보고, 전체 검사를 돌려 원래 깨져 있는 테스트를 적는다. 작업마다 한 번.
  check     할 일의 검사. --phase red 는 "제대로 실패하는가", green 은 "통과했고 새로 깨진 것이 없는가".
  done      완료. 통과한 그 코드가 그대로 커밋에 올라가 있을 때만 완료로 표시한다.
  review    검수 검사. 할 일이 모두 완료됐고, 평가 뒤에 바뀐 것이 관리 기록뿐이고, 바탕 검사 뒤에 바뀐 파일이
            할 일들의 허락된 파일 안이고, 전체 검사를 새로 돌려 새로 깨진 것이 없고 할 일마다의 테스트가 통과하는지 본다.

판정은 테스트 도구가 낸 보고서 파일의 테스트 항목을 이름으로 읽어서 한다.
합계 숫자, 종료 코드, 화면 출력은 읽지 않는다. 뜻이나 품질은 판단하지 않는다.

테스트 도구는 검사 계약의 runner로 고른다.
  pytest  이 프로그램을 돌리는 파이썬의 pytest를 쓴다. 보고서는 JUnit.
  jest    계약의 command(명령 목록) 뒤에 인자와 --json --outputFile 을 붙여 돌린다.
  gradle  계약의 command 뒤에 인자를 붙여 돌린다. 결과는 Gradle이 늘 같은 폴더(계약의 report_dir)에
          클래스마다 한 파일씩 쓰므로, 돌리기 전에 그 폴더의 결과 파일을 치우고 돌린 뒤 모아 읽는다.
  xcodebuild  계약의 command 뒤에 인자와 -resultBundlePath 를 붙여 돌린다. 결과 묶음(.xcresult)은
          Xcode에 든 xcresulttool로 읽는다.
Python 표준 라이브러리만 쓴다.
"""
import argparse
import datetime
import fnmatch
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

WORK_ROOT = ".harness/artifacts/work"
CONTRACT = ".harness/docs/checks.json"
CONTRACT_KEYS = ("runner", "full_args", "timeout_seconds", "test_globs")
TASK_KEYS = ("id", "kind", "allowed_files", "check_args")
RUNNERS = ("pytest", "jest", "gradle", "xcodebuild")
RANK = {"passed": 0, "skipped": 1, "failure": 2, "error": 3}
JEST_KIND = {"passed": "passed", "failed": "failure", "pending": "skipped", "skipped": "skipped",
             "todo": "skipped", "disabled": "skipped"}
XC_KIND = {"Passed": "passed", "Failed": "failure", "Skipped": "skipped", "Expected Failure": "skipped"}
XC_BUNDLES = ("Unit test bundle", "UI test bundle")
FILE_FAILED = "(파일 실행 실패)"
SETUP_ERRORS = ("ImportError", "ModuleNotFoundError", "SyntaxError", "Error: Cannot find module")
NOT_RAN = {
    "not_run": "검사가 실행되지 않음 (이번 실행에서 새 보고서가 나오지 않았거나 실행된 테스트가 0개)",
    "timeout": "검사가 제한 시간을 넘김",
}


class Stop(Exception):
    """판정이 ok가 아닐 때. out이 그대로 출력된다."""

    def __init__(self, verdict, reason, **extra):
        super().__init__(reason)
        self.out = dict(verdict=verdict, reason=reason, **extra)


# --- git과 지문 ---
def git(repo, *args):
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        raise Stop("stop", "git 명령이 실패함: git " + " ".join(args[:2]))
    return r.stdout


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(repo, rel):
    try:
        with open(os.path.join(repo, rel), "rb") as f:
            return sha(f.read())
    except (FileNotFoundError, IsADirectoryError):
        return "없음"


def changed(ctx):
    """마지막 커밋과 다른 파일(새 파일 포함). 이 작업의 작업 폴더는 뺀다."""
    out = git(ctx.repo, "status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=all")
    paths = {e[3:] for e in out.split("\0") if len(e) > 3}
    return sorted(p for p in paths if not p.startswith(ctx.work_rel + "/"))


def snapshot(ctx):
    """지금 코드 상태의 지문: 마지막 커밋 + 바뀐 파일마다 내용의 지문."""
    head = git(ctx.repo, "rev-parse", "HEAD").strip()
    paths = changed(ctx)
    body = json.dumps([head] + [[p, file_hash(ctx.repo, p)] for p in paths])
    return sha(body.encode()), paths, head


def test_fingerprint(ctx, check_args):
    """테스트 관련 파일과 확인 명령의 지문."""
    files = set(git(ctx.repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0"))
    globs = ctx.contract["test_globs"]
    picked = sorted(f for f in files if f and any(
        fnmatch.fnmatch(f, g) or fnmatch.fnmatch(os.path.basename(f), g) for g in globs))
    body = json.dumps([list(check_args)] + [[p, file_hash(ctx.repo, p)] for p in picked])
    return sha(body.encode())


# --- 보고서 읽기와 검사 실행 ---
def parse_junit(path):
    """보고서의 테스트 항목을 (이름, 결과, 메시지 첫 줄) 목록으로 낸다. 합계 숫자는 읽지 않는다."""
    cases = {}
    for c in ET.parse(path).getroot().iter("testcase"):
        tid = "%s::%s" % (c.get("classname", ""), c.get("name", ""))
        kind, msg = "passed", ""
        for ch in c:
            if ch.tag in RANK and RANK[ch.tag] > RANK[kind]:
                kind = ch.tag
                msg = ((ch.get("message") or "").strip().splitlines() or [""])[0]
        if tid not in cases or RANK[kind] > RANK[cases[tid][1]]:
            cases[tid] = (tid, kind, msg)
    return list(cases.values())


def first_line(text):
    return ((text or "").strip().splitlines() or [""])[0]


def parse_jest(path, repo):
    """Jest의 --json 보고서를 (이름, 결과, 메시지 첫 줄) 목록으로 낸다. 합계 숫자는 읽지 않는다.

    이름은 "저장소 기준 파일 경로::테스트 전체 이름"이다. 한 파일에 같은 이름이 둘이면 나쁜 쪽을 남긴다.
    파일이 통째로 실행되지 못하면 항목이 0개로 나오므로, 실패한 파일에 실패 항목이 없으면
    그 파일 몫의 오류 항목을 하나 만든다.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    root = os.path.realpath(repo)
    cases = {}

    def put(tid, kind, msg):
        if tid not in cases or RANK[kind] > RANK[cases[tid][1]]:
            cases[tid] = (tid, kind, msg)

    for suite in data.get("testResults", []):
        rel = os.path.relpath(os.path.realpath(suite.get("name", "")), root)
        items = suite.get("assertionResults") or []
        for item in items:
            kind = JEST_KIND.get(item.get("status"), "error")  # 모르는 결과는 통과로 치지 않는다
            put("%s::%s" % (rel, item.get("fullName", "")), kind, first_line((item.get("failureMessages") or [""])[0]))
        if suite.get("status") == "failed" and not any(i.get("status") == "failed" for i in items):
            put("%s::%s" % (rel, FILE_FAILED), "error", first_line(suite.get("message")))
    return list(cases.values())


def xcresult_cases(data):
    """xcresulttool이 낸 테스트 나무에서 "Test Case" 마디를 (이름, 결과, 메시지 첫 줄) 목록으로 낸다.

    이름은 "테스트 묶음 이름/묶음 안의 식별자"로, -only-testing 에 적는 모양과 같다. 화면에 보이는 이름은
    서로 겹칠 수 있어 쓰지 않는다. 인자가 여럿인 테스트는 테스트 하나로 읽는다. 같은 이름이 둘이면 나쁜 쪽을 남긴다.
    """
    cases = {}

    def message(node):
        for child in node.get("children") or []:
            found = first_line(child.get("name")) if child.get("nodeType") == "Failure Message" else message(child)
            if found:
                return found
        return ""

    def walk(node, bundle, suites):
        node_type, name = node.get("nodeType"), node.get("name") or ""
        if node_type == "Test Case":
            tid = "%s/%s" % (bundle, node.get("nodeIdentifier") or "/".join(suites + [name]))
            kind = XC_KIND.get(node.get("result"), "error")  # 모르는 결과는 통과로 치지 않는다
            if tid not in cases or RANK[kind] > RANK[cases[tid][1]]:
                cases[tid] = (tid, kind, message(node))
            return
        for child in node.get("children") or []:
            walk(child, name if node_type in XC_BUNDLES else bundle,
                 suites + [name] if node_type == "Test Suite" else suites)

    for node in data.get("testNodes") or []:
        walk(node, "", [])
    return list(cases.values())


def parse_xcresult(bundle, timeout):
    """결과 묶음(.xcresult)을 Xcode에 든 xcresulttool로 읽는다. 뽑은 것은 파일로 남기지 않는다."""
    r = subprocess.run(["xcrun", "xcresulttool", "get", "test-results", "tests", "--path", bundle, "--compact"],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise ValueError("xcresulttool이 실패함")
    return xcresult_cases(json.loads(r.stdout))


def junit_files(folder):
    """폴더 바로 아래의 결과 파일(.xml). 하위 폴더는 보지 않는다."""
    try:
        names = sorted(os.listdir(folder))
    except FileNotFoundError:
        return []
    return [p for p in (os.path.join(folder, n) for n in names if n.endswith(".xml")) if os.path.isfile(p)]


def gather_junit(folder, report):
    """폴더의 결과 파일들을 보고서 한 파일로 모은다. 하나도 없으면 보고서를 만들지 않는다(미실행으로 읽힌다)."""
    files = junit_files(folder)
    if files:
        root = ET.Element("testsuites")
        for p in files:  # extend에 넘기면 읽기 오류가 다른 오류로 바뀌어 나온다
            root.append(ET.parse(p).getroot())
        ET.ElementTree(root).write(report, encoding="utf-8", xml_declaration=True)


def broken_ids(cases):
    return sorted(c[0] for c in cases if c[1] in ("failure", "error"))


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def report_ext(ctx):
    return {"jest": ".json", "xcodebuild": ".xcresult"}.get(ctx.contract["runner"], ".xml")


def run_check(ctx, label, args):
    """검사를 새 보고서 파일로 돌린다. (테스트 항목, 기록 파일 이름)을 낸다.

    보고서 이름은 실행마다 새로 짓는다. 실행 뒤 그 파일이 없으면 "미실행"이다.
    """
    logs = os.path.join(ctx.work, "logs")
    checks = os.path.join(ctx.work, "checks")
    os.makedirs(logs, exist_ok=True)
    os.makedirs(checks, exist_ok=True)
    stamp = "%s-%s-%d" % (label, time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()), os.getpid())
    runner = ctx.contract["runner"]
    report_name = stamp + report_ext(ctx)
    report = os.path.join(logs, report_name)
    log = os.path.join(logs, stamp + ".log")
    if os.path.exists(report):
        raise Stop("stop", "같은 이름의 보고서가 이미 있음. 잠시 뒤 다시 실행")
    start = time.time()
    ran, exit_code, cases = "ran", None, []
    if runner == "jest":
        command = [*ctx.contract["command"], *args, "--json", "--outputFile=" + report]
        env = dict(os.environ, CI="true")  # 지켜보기(watch) 모드로 들어가 멈춰 있지 않게
    elif runner == "gradle":
        command, env = [*ctx.contract["command"], *args], None
        for old in junit_files(ctx.report_dir):  # 남아 있던 결과를 이번 결과로 읽지 않게
            os.remove(old)
    elif runner == "xcodebuild":
        command, env = [*ctx.contract["command"], *args, "-resultBundlePath", report], None
    else:
        command, env = [sys.executable, "-m", "pytest", *args, "--junitxml=" + report], None
    try:
        with open(log, "wb") as f:
            exit_code = subprocess.run(
                command, cwd=ctx.repo, stdout=f, stderr=subprocess.STDOUT, env=env,
                timeout=ctx.contract["timeout_seconds"]).returncode
    except subprocess.TimeoutExpired:
        ran = "timeout"
    except OSError:
        ran = "not_run"  # 명령을 찾지 못했거나 실행할 수 없음
    if ran == "ran":
        try:
            if runner == "gradle":
                gather_junit(ctx.report_dir, report)
            if runner == "xcodebuild":
                cases = parse_xcresult(report, ctx.contract["timeout_seconds"])
            else:
                cases = parse_jest(report, ctx.repo) if runner == "jest" else parse_junit(report)
        except (FileNotFoundError, ValueError, ET.ParseError, subprocess.TimeoutExpired):
            cases = []
        if not cases:
            ran = "not_run"
    with open(log, "rb") as f:
        log_sha = sha(f.read())
    name = "%03d-%s.json" % (len(os.listdir(checks)) + 1, label)
    record = {
        "label": label, "runner": runner, "args": list(args), "ran": ran, "exit_code": exit_code,
        "total": len(cases), "counts": {k: sum(1 for c in cases if c[1] == k) for k in RANK},
        "broken": broken_ids(cases), "report": "logs/" + report_name, "log_sha256": log_sha,
        "head": git(ctx.repo, "rev-parse", "HEAD").strip(), "seconds": round(time.time() - start), "at": now(),
    }
    save_json(os.path.join(checks, name), record)
    if ran != "ran":
        raise Stop(ran, NOT_RAN[ran], record="checks/" + name)
    return cases, "checks/" + name


# --- 상태 파일 ---
def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def load_json(path, what):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise Stop("stop", "%s 파일이 없음: %s" % (what, os.path.basename(path)))
    except ValueError:
        raise Stop("stop", "%s 파일을 읽을 수 없음: %s" % (what, os.path.basename(path)))


class Ctx:
    def __init__(self, args):
        self.repo = os.path.abspath(args.repo) if args.repo else git(os.getcwd(), "rev-parse", "--show-toplevel").strip()
        self.contract = load_json(os.path.join(self.repo, CONTRACT), "검사 계약")
        missing = [k for k in CONTRACT_KEYS if k not in self.contract]
        if missing:
            raise Stop("stop", "검사 계약에 빠진 항목: " + ", ".join(missing))
        runner = self.contract["runner"]
        if runner not in RUNNERS:
            raise Stop("stop", "이번 판은 pytest, jest, gradle, xcodebuild의 결과만 읽음")
        command = self.contract.get("command")
        if runner != "pytest" and not (
                isinstance(command, list) and command and all(isinstance(c, str) for c in command)):
            raise Stop("stop", "검사 계약에 빠진 항목: command (테스트를 돌리는 명령 목록)")
        if runner == "gradle":
            self.report_dir = self.safe_report_dir()
        self.work_rel = WORK_ROOT + "/" + args.work
        self.work = os.path.join(self.repo, self.work_rel)
        if not os.path.isdir(self.work):
            raise Stop("stop", "작업 폴더가 없음: " + self.work_rel)
        self.state_path = os.path.join(self.work, "state.json")

    def safe_report_dir(self):
        """Gradle이 결과를 쓰는 폴더. 그 안의 결과 파일을 지우므로, 저장소 안의 git 제외 폴더일 때만 받는다."""
        rel = self.contract.get("report_dir")
        if not isinstance(rel, str) or not rel:
            raise Stop("stop", "검사 계약에 빠진 항목: report_dir (Gradle이 테스트 결과를 쓰는 폴더)")
        full = os.path.realpath(os.path.join(self.repo, rel))
        inside = full.startswith(os.path.realpath(self.repo) + os.sep)  # git도 밖의 경로를 거절하지만 지우는 일이라 한 번 더 본다
        if not inside or subprocess.run(["git", "check-ignore", "-q", os.path.join(rel, "x.xml")],
                                        cwd=self.repo, capture_output=True).returncode != 0:
            raise Stop("stop", "검사 계약의 report_dir이 저장소 안의 git 제외 폴더가 아님")
        return full

    def state(self):
        if not os.path.exists(self.state_path):
            raise Stop("stop", "바탕 검사를 먼저 돌려야 함")
        return load_json(self.state_path, "상태")

    def task(self, task_id):
        tasks = load_json(os.path.join(self.work, "tasks.json"), "할 일 목록").get("tasks", [])
        found = [t for t in tasks if t.get("id") == task_id]
        if len(found) != 1:
            raise Stop("stop", "할 일 목록에서 찾을 수 없음: " + task_id)
        missing = [k for k in TASK_KEYS if k not in found[0]]
        if missing:
            raise Stop("stop", "할 일에 빠진 항목: " + ", ".join(missing))
        if found[0]["kind"] not in ("feature", "bug"):
            raise Stop("stop", "이번 판은 새 기능(feature)과 버그(bug)만 다룸")
        return found[0]


def outside_allowed(paths, allowed):
    return [p for p in paths if not any(p == a or fnmatch.fnmatch(p, a) for a in allowed)]


def logs_not_ignored(ctx):
    """작업 폴더의 logs/가 git 제외가 아니면 그 이유를 낸다. 제외면 None."""
    for name in ("x.log", "x" + report_ext(ctx)):  # 화면 기록과 보고서 둘 다 git에 들어가면 안 된다
        ignored = subprocess.run(["git", "check-ignore", "-q", ctx.work_rel + "/logs/" + name], cwd=ctx.repo)
        if ignored.returncode != 0:
            return "작업 폴더의 logs/가 git 제외 목록에 없음 (%s 파일이 git에 들어갈 수 있음)" % name[1:]
    return None


# --- 명령 ---
def environment_problems(ctx):
    """검사를 돌릴 수 없는 환경이면 그 이유 목록. 실제로 돌리지는 않는다."""
    runner = ctx.contract["runner"]
    if runner == "pytest":  # run_check는 이 프로그램을 돌리는 파이썬으로 pytest를 부른다
        try:
            found = importlib.util.find_spec("pytest") is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            return ["이 파이썬에서 pytest를 찾을 수 없음: " + sys.executable]
        return []
    command = ctx.contract["command"][0]
    if not shutil.which(os.path.join(ctx.repo, command) if os.sep in command else command):  # 검사는 저장소에서 돈다
        return ["검사 명령을 찾을 수 없음: " + command]
    return []


def parse_deadline(text):
    """UTC ISO 8601 시각을 초로 낸다. 시간대가 없으면 UTC로 읽는다."""
    try:
        when = datetime.datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text)
    except ValueError:
        raise Stop("stop", "deadline 형식이 틀림")
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    return when.timestamp()


def cmd_preflight(ctx, args):
    """시작 전 검증. 검사를 돌리지 않고, state.json, checks/, logs/를 만들거나 고치지 않는다."""
    deadline = parse_deadline(args.deadline) if args.deadline is not None else None
    task = ctx.task(args.task) if args.task else None
    blocked = {}
    env = environment_problems(ctx)
    if env:
        blocked["environment"] = env
    problem = logs_not_ignored(ctx)
    if problem:
        blocked["evidence"] = [problem + ". 이 경로로 낸 결과는 완료 증거가 될 수 없음"]
    if args.aux:
        if task is None:
            blocked["scope"] = ["--aux는 --task와 함께 줘야 함 (어느 할 일의 범위인지 알 수 없음)"]
        else:
            outside = outside_allowed(args.aux, task["allowed_files"])
            if outside:
                blocked["scope"] = ["%s: 할 일 %s의 바꿔도 되는 파일 밖. 경로 변경 필요" % (p, task["id"])
                                    for p in outside]
    out = {"outcome": {"product": "not_run", "environment": "blocked" if env else "ok",
                       "aux": "incomplete" if args.aux else "none"}}
    if task is not None and os.path.exists(ctx.state_path):  # 바탕 검사 전이면 제품 결과는 없음
        green = ctx.state().get("tasks", {}).get(task["id"], {}).get("green")
        if green:
            out["outcome"]["product"] = "pass" if green.get("ok") else "fail"
        if green and green.get("ok"):
            snap, paths, _ = snapshot(ctx)
            if snap == green["snapshot"]:
                out["reuse"] = "same_source"
            else:  # green 기록에는 파일마다의 지문이 없어 어느 파일이 바뀌었는지 가릴 수 없다. 지금 바뀐 것과 사라진 것 전부
                out["reuse"] = "changed"
                out["review_paths"] = sorted(set(paths) | set(green["paths"]))
    if deadline is not None:
        remaining = int(deadline - time.time())
        needed = ctx.contract["timeout_seconds"] + args.margin
        out["time"] = {"remaining_seconds": remaining, "needed_seconds": needed}
        if remaining < needed:
            blocked["time"] = ["남은 시간 %d초가 필요한 시간 %d초(검사 제한 시간 + 여유)보다 짧음" % (remaining, needed)]
    outcome = out["outcome"]
    summary = "제품 %s, 환경 %s, 보조검증 %s" % (outcome["product"], outcome["environment"], outcome["aux"])
    if blocked:
        raise Stop("stop", "시작 전 검증에서 막힘: " + ", ".join(sorted(blocked)),
                   blocked=blocked, summary=summary, **out)
    return {"verdict": "ok", "blocked": {}, "summary": "시작 전 검증 통과. " + summary, **out}


def cmd_baseline(ctx, args):
    if os.path.exists(ctx.state_path):  # 다시 돌리면 완료 기록과 "원래 깨져 있던 것"이 지워진다
        raise Stop("stop", "바탕 검사는 이 작업에서 이미 했음. 다시 하지 않고 이어서 하면 됨")
    dirty = changed(ctx)
    if dirty:
        raise Stop("stop", "작업 트리에 커밋되지 않은 변경이 있음. 깨끗한 상태에서 시작해야 함", dirty=dirty)
    problem = logs_not_ignored(ctx)
    if problem:
        raise Stop("stop", problem)
    cases, record = run_check(ctx, "baseline", ctx.contract["full_args"])
    broken = broken_ids(cases)
    state = {
        "version": 1, "work": args.work, "tool": args.tool, "tasks": {},
        "baseline": {
            "head": git(ctx.repo, "rev-parse", "HEAD").strip(),
            "branch": git(ctx.repo, "rev-parse", "--abbrev-ref", "HEAD").strip(),
            "broken": broken, "total": len(cases), "record": record, "at": now(),
        },
    }
    save_json(ctx.state_path, state)
    return {"verdict": "ok", "broken": broken, "record": record,
            "summary": "바탕 검사 끝. 테스트 %d개, 원래 깨져 있던 것 %d건" % (len(cases), len(broken))}


def check_red(ctx, state, task):
    cases, record = run_check(ctx, task["id"] + "-red", task["check_args"])
    known = set(state["baseline"]["broken"])
    cases = [c for c in cases if c[0] not in known]  # 원래 깨져 있던 것은 이 할 일의 실패로 치지 않는다
    kinds = [c[1] for c in cases]
    if "error" in kinds:
        raise Stop("stop", "테스트를 읽어 들이는 단계나 준비 단계에서 오류가 남. 테스트 본문에서 실패해야 함", record=record)
    if kinds and all(k == "skipped" for k in kinds):
        raise Stop("stop", "고른 테스트가 전부 건너뜀", record=record)
    failed = [c for c in cases if c[1] == "failure"]
    if not failed:
        raise Stop("stop", "실패한 테스트가 없음. 구현 전에는 실패해야 함", record=record)
    setup = [c[0] for c in failed if c[2].startswith(SETUP_ERRORS)]
    if setup:
        raise Stop("stop", "가져오기나 문법 오류로 실패함. 준비 단계 오류는 실패 확인으로 인정하지 않음",
                   tests=setup, record=record)
    state["tasks"][task["id"]] = {"red": {
        "ok": True, "head": git(ctx.repo, "rev-parse", "HEAD").strip(),
        "test_fp": test_fingerprint(ctx, task["check_args"]),
        "failed": sorted(c[0] for c in failed), "record": record, "at": now(),
    }}
    save_json(ctx.state_path, state)
    return {"verdict": "ok", "failed": sorted(c[0] for c in failed), "record": record,
            "summary": "실패 확인 됨. 본문에서 실패한 테스트 %d개" % len(failed)}


def check_green(ctx, state, task):
    entry = state["tasks"].get(task["id"], {})
    red = entry.get("red")
    if not red or not red.get("ok"):
        raise Stop("stop", "이 할 일은 실패 확인 기록이 없음. 실패 확인을 먼저 받아야 함")
    if git(ctx.repo, "rev-parse", "HEAD").strip() != red["head"]:
        raise Stop("stop", "실패 확인 뒤에 커밋이 생김. 커밋은 지휘만 하고, 완료 뒤에 함")
    if test_fingerprint(ctx, task["check_args"]) != red["test_fp"]:
        raise Stop("stop", "실패 확인 뒤에 테스트가 바뀜. 테스트를 고치려면 승인받고 실패 확인부터 다시")
    outside = outside_allowed(changed(ctx), task["allowed_files"])
    if outside:
        raise Stop("stop", "바꿔도 되는 파일 밖을 고침", outside=outside)
    cases, rec_task = run_check(ctx, task["id"] + "-green-task", task["check_args"])
    result = {c[0]: c[1] for c in cases}
    still = [t for t in red["failed"] if result.get(t) != "passed"]
    if still:
        raise Stop("stop", "실패 확인 때 실패했던 테스트가 아직 통과하지 않음", tests=still, record=rec_task)
    cases, rec_full = run_check(ctx, task["id"] + "-green-full", ctx.contract["full_args"])
    now_broken = set(broken_ids(cases))
    known = set(state["baseline"]["broken"])
    new_broken = sorted(now_broken - known)
    if new_broken:
        raise Stop("stop", "새로 깨진 테스트가 있음", new_broken=new_broken, record=rec_full)
    snap, paths, _ = snapshot(ctx)
    outside = outside_allowed(paths, task["allowed_files"])
    if outside:
        raise Stop("stop", "검사 중에 바꿔도 되는 파일 밖이 바뀜", outside=outside)
    entry["green"] = {"ok": True, "snapshot": snap, "paths": paths, "records": [rec_task, rec_full], "at": now()}
    entry.pop("done", None)
    save_json(ctx.state_path, state)
    still_known = len(now_broken & known)
    summary = "통과 확인 됨. 새로 깨진 것 없음"
    if still_known:
        summary += ", 원래 깨져 있던 것 %d건" % still_known
    return {"verdict": "ok", "summary": summary, "paths": paths, "records": [rec_task, rec_full]}


def cmd_check(ctx, args):
    state, task = ctx.state(), ctx.task(args.task)
    return (check_red if args.phase == "red" else check_green)(ctx, state, task)


def cmd_done(ctx, args):
    state, task = ctx.state(), ctx.task(args.task)
    entry = state["tasks"].get(task["id"], {})
    green = entry.get("green")
    if not green or not green.get("ok"):
        raise Stop("stop", "이 할 일은 통과 확인 기록이 없음")
    snap, paths, head = snapshot(ctx)
    if snap != green["snapshot"]:
        raise Stop("stop", "통과 확인 뒤에 코드가 바뀜. 통과 확인부터 다시",
                   added_after=sorted(set(paths) - set(green["paths"])))
    unstaged = set(git(ctx.repo, "diff", "--name-only", "-z", "--no-renames").split("\0"))
    unstaged |= set(git(ctx.repo, "ls-files", "-z", "--others", "--exclude-standard").split("\0"))
    not_staged = [p for p in paths if p in unstaged]
    if not_staged:
        raise Stop("stop", "통과한 파일 가운데 커밋에 올리지 않은 것이 있음", not_staged=not_staged)
    entry["done"] = {"at": now(), "head": head, "paths": paths}
    save_json(ctx.state_path, state)
    if subprocess.run(["git", "check-ignore", "-q", ctx.work_rel + "/INDEX.md"], cwd=ctx.repo).returncode == 0:
        return {"verdict": "ok", "add": [],
                "summary": "완료로 표시함. 이 저장소는 작업 폴더가 git 제외라 올리지 않음. 그대로 커밋하면 됨"}
    return {"verdict": "ok", "add": [ctx.work_rel],
            "summary": "완료로 표시함. 작업 폴더의 기록을 올린 뒤 커밋하면 됨"}


RECORD_FILES = ("INDEX.md", "state.json")
RECORD_DIRS = ("checks/", "logs/")
RECORD_GLOBS = ("eval-*.md", "review-*.md")


def is_record(ctx, path):
    """작업 폴더의 관리 기록인가. 설명서(spec.md), 할 일 목록, 할 일 본문은 관리 기록이 아니다."""
    if not path.startswith(ctx.work_rel + "/"):
        return False
    rel = path[len(ctx.work_rel) + 1:]
    return rel in RECORD_FILES or rel.startswith(RECORD_DIRS) or (
        "/" not in rel and any(fnmatch.fnmatch(rel, g) for g in RECORD_GLOBS))


def is_ancestor(repo, older, newer):
    return subprocess.run(["git", "merge-base", "--is-ancestor", older, newer],
                          cwd=repo, capture_output=True).returncode == 0


def cmd_review(ctx, args):
    """검수 검사. 오래 걸리는 전체 검사는 다른 조건을 모두 본 뒤에 돌린다."""
    state = ctx.state()
    tasks = load_json(os.path.join(ctx.work, "tasks.json"), "할 일 목록").get("tasks", [])
    out = git(ctx.repo, "status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=all")
    dirty = sorted(p for p in {e[3:] for e in out.split("\0") if len(e) > 3} if not is_record(ctx, p))
    if dirty:  # 작업 폴더의 설명서와 할 일 목록도 커밋돼 있어야 한다
        raise Stop("stop", "커밋되지 않은 변경이 있음. 검수는 커밋된 것으로만 함", dirty=dirty)
    if not tasks:
        raise Stop("stop", "할 일 목록이 비어 있음")
    not_done = [t.get("id") for t in tasks if not state["tasks"].get(t.get("id"), {}).get("done")]
    if not_done:
        raise Stop("stop", "끝나지 않은 할 일이 있음", tasks=not_done)
    base = state["baseline"]["head"]
    since = "" if args.since.startswith("-") else subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", args.since + "^{commit}"],
        cwd=ctx.repo, capture_output=True, text=True).stdout.strip()
    if not since:
        raise Stop("stop", "평가 대상 커밋을 찾을 수 없음: " + args.since)
    if not is_ancestor(ctx.repo, base, since) or not is_ancestor(ctx.repo, since, "HEAD"):
        raise Stop("stop", "바탕 검사 커밋 → 평가 대상 커밋 → 지금 커밋으로 이어지지 않음")
    after = git(ctx.repo, "diff", "--name-only", "-z", "--no-renames", since, "HEAD").split("\0")
    after = sorted(p for p in after if p and not is_record(ctx, p))
    if after:
        raise Stop("stop", "평가 뒤에 바뀐 것이 있음. 평가부터 다시", changed=after)
    paths = git(ctx.repo, "diff", "--name-only", "-z", "--no-renames", base, "HEAD").split("\0")
    paths = sorted(p for p in paths if p and not p.startswith(ctx.work_rel + "/"))
    outside = outside_allowed(paths, [a for t in tasks for a in t.get("allowed_files", [])])
    if outside:
        raise Stop("stop", "바탕 검사 뒤에 할 일들의 허락된 파일 밖이 바뀜", outside=outside)
    head = git(ctx.repo, "rev-parse", "HEAD").strip()
    cases, record = run_check(ctx, "review-full", ctx.contract["full_args"])
    if changed(ctx) or git(ctx.repo, "rev-parse", "HEAD").strip() != head:
        raise Stop("stop", "검사하는 동안 파일이나 커밋이 바뀜", record=record)
    known = set(state["baseline"]["broken"])
    now_broken = set(broken_ids(cases))
    new_broken = sorted(now_broken - known)
    if new_broken:
        raise Stop("stop", "새로 깨진 테스트가 있음", new_broken=new_broken, record=record)
    result = {c[0]: c[1] for c in cases}
    proof = {t["id"]: state["tasks"][t["id"]]["red"]["failed"] for t in tasks}
    not_passing = {k: [x for x in v if result.get(x) != "passed"] for k, v in proof.items()}
    not_passing = {k: v for k, v in not_passing.items() if v}
    if not_passing:  # 건너뜀이나 사라짐도 통과가 아니다
        raise Stop("stop", "할 일의 테스트가 마지막 검사에서 통과하지 않음", tests=not_passing, record=record)
    before = load_json(os.path.join(ctx.work, state["baseline"]["record"]), "바탕 검사 기록")
    counts = {"baseline": {"total": before["total"], "skipped": before["counts"]["skipped"]},
              "now": {"total": len(cases), "skipped": sum(1 for c in cases if c[1] == "skipped")}}
    state["review"] = {"base": base, "since": since, "head": head, "record": record, "at": now()}
    save_json(ctx.state_path, state)
    summary = "검수 검사 통과. 할 일 %d개 모두 완료, 평가 뒤 바뀐 것 없음, 바뀐 파일 %d개 모두 허락된 파일 안, 새로 깨진 것 없음" % (
        len(tasks), len(paths))
    if now_broken & known:
        summary += ", 원래 깨져 있던 것 %d건" % len(now_broken & known)
    return {"verdict": "ok", "summary": summary, "base": base, "since": since, "head": head, "paths": paths,
            "record": record, "baseline_record": state["baseline"]["record"], "tests": counts,
            "still_broken": sorted(now_broken & known),
            "tasks": {t["id"]: {"criteria": t.get("criteria", []), "tests": proof[t["id"]]} for t in tasks}}


def main(argv=None):
    p = argparse.ArgumentParser(prog="hb", description="검사를 직접 돌려 판정하고 기록한다.")
    p.add_argument("--repo", default=None, help="제품 저장소 (기본: 지금 폴더의 저장소)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("baseline", "check", "done", "review"):
        s = sub.add_parser(name)
        s.add_argument("--work", required=True, help="작업 이름")
        if name == "baseline":
            s.add_argument("--tool", default="claude-code", help="어느 도구로 하는지 (기록용)")
        elif name == "review":
            s.add_argument("--since", required=True, help="마지막 평가의 대상 커밋")
        else:
            s.add_argument("--task", required=True, help="할 일 번호")
        if name == "check":
            s.add_argument("--phase", required=True, choices=("red", "green"))
    s = sub.add_parser("preflight")
    s.add_argument("--work", required=True, help="작업 이름")
    s.add_argument("--task", default=None, help="할 일 번호 (주면 그 할 일의 통과 기록과 범위를 본다)")
    s.add_argument("--aux", action="append", default=[], help="보조검증이 쓸 경로 (여러 번 줄 수 있음)")
    s.add_argument("--deadline", default=None, help="결과를 회수해야 하는 시각 (UTC ISO 8601)")
    s.add_argument("--margin", type=int, default=120, help="검사 제한 시간에 더할 여유 초 (기본 120)")
    args = p.parse_args(argv)
    try:
        out = {"baseline": cmd_baseline, "check": cmd_check, "done": cmd_done,
               "review": cmd_review, "preflight": cmd_preflight}[args.cmd](Ctx(args), args)
    except Stop as e:
        out = e.out
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["verdict"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
