"""할 일의 준비 데이터 정정(setup-fix --phase before|after)과 통과 확인 조건 테스트.

test_hb.py처럼 임시 git 저장소에 작은 가짜 제품(주문 배송비)을 만들고 진짜 pytest로 검사를 돌린다.
준비 데이터는 테스트가 읽는 입력 JSON(tests/data/*.json)이고, 검사 계약의 test_globs에 들어 있다.
큰 주문의 입력 파일에 수량(qty)이 빠져 있어, 구현을 마친 뒤 준비 단계(fixture)에서 오류가 나는 상황이다.
- C3: before는 조건을 만족할 때만 기록을 남기고, 아니면 테스트를 돌리지 않거나 멈춘다.
- C4: after는 before의 인자로 돌리고, 세 인정 조건을 모두 만족할 때만 인정한다. 아니면 칸별로 이름을 낸다.
- C5: after는 커밋이나 test_globs 밖 파일이 before와 다르거나 테스트 쪽이 그대로면 테스트를 돌리지 않는다.
- C6: 인정되면 테스트 쪽 변경(git에 없는 새 파일 포함)이 logs/에 남고, 사용자의 인덱스는 그대로다.
- C7: 통과 확인은 인정된 정정이 있을 때만 바뀐 테스트 지문을 받아들인다.
모든 멈춤에서 state.json은 바이트 그대로다.
실행: <테스트 환경의 python> -m pytest tests/test_hb_setup_fix.py   (pytest가 깔린 파이썬이어야 함)
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
    "test_globs": ["test_*.py", "conftest.py", "tests/data/*.json"],
}
TASK = {
    "id": "01", "title": "배송비", "kind": "feature", "criteria": ["C1"],
    "allowed_files": ["app.py", "tests/test_new.py", "tests/data/*.json"], "check_args": ["tests/test_new.py"],
}
BASE_APP = "def add(a, b):\n    return a + b\n"
APP_STUB = BASE_APP + textwrap.dedent("""


    def make_order(data):
        return data


    def shipping(items):
        return None
""")
# 준비 단계(fixture)에서 make_order가 수량을 읽는다. 입력에 수량이 없으면 준비 단계 오류가 난다.
APP_IMPL = BASE_APP + textwrap.dedent("""


    def make_order(data):
        return [{"price": i["price"], "qty": i["qty"]} for i in data["items"]]


    def shipping(items):
        return 0 if sum(i["price"] * i["qty"] for i in items) >= 50 else 3
""")
# 테스트 본문(shipping)에서 수량을 읽는다. 입력에 수량이 없으면 본문에서 실패한다.
APP_IMPL_BODY = BASE_APP + textwrap.dedent("""


    def make_order(data):
        return data["items"]


    def shipping(items):
        return 0 if sum(i["price"] * i["qty"] for i in items) >= 50 else 3
""")
# 다른 구현은 그대로 두고 배송비만 틀리게 계산한다.
APP_IMPL_WRONG_FEE = APP_IMPL.replace("else 3", "else 4")
# 수량이 빠진 항목은 1개로 본다. 입력 파일을 고치지 않아도 통과한다.
APP_IMPL_DEFAULT_QTY = APP_IMPL.replace('i["qty"]', 'i.get("qty", 1)')
# 구현이 이름을 바꿔 테스트가 가져오지 못한다.
APP_RENAMED = BASE_APP + textwrap.dedent("""


    def make_order(data):
        return data["items"]


    def shipping_fee(items):
        return 3
""")

TEST_HEAD = textwrap.dedent("""\
    import json
    import os

    import pytest

    from app import make_order, shipping

    DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


    def load(name):
        with open(os.path.join(DATA, name), encoding="utf-8") as f:
            return make_order(json.load(f))


    @pytest.fixture
    def big_order():
        return load("order_big.json")


    @pytest.fixture
    def small_order():
        return load("order_small.json")


    def test_free_shipping_over_limit(big_order):
        assert shipping(big_order) == 0
""")
TEST_SMALL = textwrap.dedent("""


    def test_shipping_fee_under_limit(small_order):
        assert shipping(small_order) == 3
""")
TEST_SMALL_SKIPPED = textwrap.dedent("""


    @pytest.mark.skip(reason="later")
    def test_shipping_fee_under_limit(small_order):
        assert shipping(small_order) == 3
""")
TEST_EXTRA = textwrap.dedent("""


    def test_fee_without_items():
        assert shipping([]) == 3
""")
NEW_TEST = TEST_HEAD + TEST_SMALL
NEW_TEST_EXTRA = NEW_TEST + TEST_EXTRA          # 테스트가 하나 늘어남
NEW_TEST_NO_SMALL = TEST_HEAD                   # 테스트가 하나 줄어듦
NEW_TEST_SKIP_SMALL = TEST_HEAD + TEST_SMALL_SKIPPED
# before에서 실패하던 테스트에 건너뛰기 표시를 붙임(입력 파일은 그대로)
NEW_TEST_SKIP_FREE = NEW_TEST.replace(
    "def test_free_shipping_over_limit(big_order):",
    "@pytest.mark.skip(reason=\"later\")\ndef test_free_shipping_over_limit(big_order):")
# 테스트 파일을 불러오는 중에 프로세스가 끝나 보고서가 나오지 않는다
NEW_TEST_EXITS = "import os\n\nos._exit(0)\n" + NEW_TEST
# 본문 안에서 가져온다. 구현이 이름을 바꾸면 본문에서 가져오기 오류가 난다.
NEW_TEST_LAZY = textwrap.dedent("""\
    def test_free_shipping_over_limit():
        from app import shipping
        assert shipping([{"price": 60, "qty": 1}]) == 0
""")

BIG_BROKEN = '{"items": [{"price": 30}, {"price": 25}]}\n'           # 수량이 빠짐
BIG_FIXED = '{"items": [{"price": 30, "qty": 1}, {"price": 25, "qty": 1}]}\n'
BIG_STILL = '{"items": [{"price": 35}, {"price": 25}]}\n'            # 고쳤지만 수량은 여전히 없음
SMALL = '{"items": [{"price": 10, "qty": 2}]}\n'
SMALL_BROKEN = '{"items": [{"price": 10}]}\n'
SMALL_OVER = '{"items": [{"price": 30, "qty": 2}]}\n'               # 준비는 되지만 금액이 한도를 넘어 본문에서 실패
CURRENCY = '{"currency": "KRW"}\n'

BIG_DATA = "tests/data/order_big.json"
SMALL_DATA = "tests/data/order_small.json"
FREE = "tests.test_new::test_free_shipping_over_limit"
FEE = "tests.test_new::test_shipping_fee_under_limit"
EXTRA = "tests.test_new::test_fee_without_items"
FREE_ARG = "tests/test_new.py::test_free_shipping_over_limit"
FIELDS = ("added", "removed", "still_failing", "regressed")


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


def named(out):
    """판정 출력에서 이유 문장과 요약을 뺀 칸들의 문자열."""
    return strings({k: v for k, v in out.items() if k not in ("reason", "summary")})


@unittest.skipUnless(importlib.util.find_spec("pytest"), "pytest가 깔린 파이썬으로 돌려야 함")
class SetupFixBase(unittest.TestCase):
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
        self.write("tests/test_old.py", "def test_old_broken():\n    assert 1 == 2\n")  # 원래 깨져 있던 것
        self.write(".harness/docs/checks.json", json.dumps(CHECKS))
        self.write_tasks(TASK)
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

    def write_tasks(self, *tasks):
        self.write(WORK_DIR + "/tasks.json", json.dumps({"work": WORK, "tasks": list(tasks)}, ensure_ascii=False))

    def hb(self, *args):
        # 크기가 같은 변경이 같은 초에 쓰이면 옛 .pyc가 쓰여 깨진 동작이 가려지므로 바이트코드를 쓰지 않는다.
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, HB, "--repo", self.root, *args], capture_output=True, text=True, env=env)
        try:
            out = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            self.fail("hb가 판정을 내지 않음: rc=%s out=%r err=%r" % (r.returncode, r.stdout[-300:], r.stderr[-300:]))
        return r.returncode, out

    def state_path(self):
        return os.path.join(self.root, WORK_DIR, "state.json")

    def state(self):
        with open(self.state_path(), encoding="utf-8") as f:
            return json.load(f)

    def state_bytes(self):
        with open(self.state_path(), "rb") as f:
            return f.read()

    def entry(self):
        return self.state()["tasks"]["01"]

    def fixes(self):
        return self.entry().get("setup_fixes") or []

    def head(self):
        return self.git("rev-parse", "HEAD").strip()

    def check_names(self):
        return sorted(os.listdir(os.path.join(self.root, WORK_DIR, "checks")))

    def checks_count(self):
        return len(self.check_names())

    def newest_record(self):
        """가장 최근 checks/ 기록의 (경로, 내용)."""
        name = self.check_names()[-1]
        with open(os.path.join(self.root, WORK_DIR, "checks", name), encoding="utf-8") as f:
            return "checks/" + name, json.load(f)

    def diff_logs(self):
        return sorted(glob.glob(os.path.join(self.root, WORK_DIR, "logs", "01-setup-fix-*.diff.log")))

    def baseline(self):
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)

    def red(self):
        rc, out = self.hb("check", "--work", WORK, "--task", "01", "--phase", "red")
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        return out

    def ready(self, test=NEW_TEST, app=APP_IMPL):
        """바탕 검사 -> 테스트와 (수량이 빠진) 입력 파일을 쓰고 실패 확인 -> 구현까지 한 상태."""
        self.baseline()
        self.write("tests/test_new.py", test)
        self.write(BIG_DATA, BIG_BROKEN)
        self.write(SMALL_DATA, SMALL)
        self.write("app.py", APP_STUB)
        self.red()
        self.write("app.py", app)

    def before(self, *args):
        return self.hb("setup-fix", "--work", WORK, "--task", "01", "--phase", "before", *(["--", *args] if args else []))

    def after(self, *args):
        return self.hb("setup-fix", "--work", WORK, "--task", "01", "--phase", "after", *(["--", *args] if args else []))

    def green(self):
        return self.hb("check", "--work", WORK, "--task", "01", "--phase", "green")

    def assert_ok(self, rc, out):
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        return out

    def assert_stops(self, run, no_run=False):
        """멈추고 state.json이 바이트 그대로인지 본다. no_run이면 새 checks/ 기록도 없어야 한다."""
        state = self.state_bytes()
        count = self.checks_count()
        rc, out = run()
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertEqual(self.state_bytes(), state, "멈춘 뒤 state.json이 바뀜")
        if no_run:
            self.assertEqual(self.checks_count(), count, "테스트를 돌리지 않아야 함")
        return out

    def accepted(self):
        """before -> 입력 파일 고침 -> after 인정까지 한 상태."""
        self.ready()
        self.assert_ok(*self.before())
        self.write(BIG_DATA, BIG_FIXED)
        return self.assert_ok(*self.after())


class BeforeTest(SetupFixBase):
    """C3."""

    def test_before_records_setup_error_with_check_args(self):
        self.ready()
        red = copy.deepcopy(self.entry()["red"])
        count = self.checks_count()
        self.assert_ok(*self.before())
        self.assertEqual(self.checks_count(), count + 1)
        rec_path, rec = self.newest_record()
        self.assertEqual(rec["args"], ["tests/test_new.py"], "인자를 주지 않으면 할 일의 check_args로 돌려야 함")
        entry = self.entry()
        self.assertEqual(entry["red"], red)
        self.assertEqual(entry.get("red_history") or [], [])
        fixes = entry["setup_fixes"]
        self.assertEqual(len(fixes), 1)
        item = fixes[0]
        self.assertEqual(item["red_record"], red["record"])
        self.assertNotIn("after", item)
        before = item["before"]
        self.assertIn(["tests/test_new.py"], values(before))
        # 준비 단계(fixture) 오류는 받는다
        self.assertIn({FREE: "error", FEE: "passed"}, values(before))
        self.assertIn(self.head(), values(before))
        self.assertIn(rec_path, values(before))
        self.assertIn("app.py", strings(before), "test_globs 밖에서 바뀐 구현 파일이 남아야 함")

    def test_before_accepts_failure_in_test_body(self):
        self.ready(app=APP_IMPL_BODY)
        self.assert_ok(*self.before())
        self.assertIn({FREE: "failure", FEE: "passed"}, values(self.fixes()[0]["before"]))

    def test_before_records_given_args(self):
        self.ready()
        self.assert_ok(*self.before(FREE_ARG))
        _, rec = self.newest_record()
        self.assertEqual(rec["args"], [FREE_ARG])
        before = self.fixes()[0]["before"]
        self.assertIn([FREE_ARG], values(before))
        self.assertIn({FREE: "error"}, values(before))

    def test_before_without_red_does_not_run(self):
        self.baseline()
        self.write("tests/test_new.py", NEW_TEST)
        self.write(BIG_DATA, BIG_BROKEN)
        self.write(SMALL_DATA, SMALL)
        self.write("app.py", APP_IMPL)
        out = self.assert_stops(self.before, no_run=True)
        self.assertIn("실패 확인", out["reason"], "실패 확인 기록이 없어서 멈췄다고 알려야 함")
        self.assertEqual(self.state()["tasks"], {})

    def test_before_after_commit_since_red_does_not_run(self):
        self.ready()
        self.git("commit", "-q", "--allow-empty", "-m", "실패 확인 뒤 커밋")
        self.assert_stops(self.before, no_run=True)

    def test_before_with_test_side_already_changed_does_not_run(self):
        self.ready()
        self.write(BIG_DATA, BIG_FIXED)
        self.assert_stops(self.before, no_run=True)
        self.write(BIG_DATA, BIG_BROKEN)
        self.write("tests/data/currency.json", CURRENCY)  # git에 없는 새 테스트 쪽 파일
        self.assert_stops(self.before, no_run=True)

    def test_before_again_while_unfinished_stops(self):
        self.ready()
        self.assert_ok(*self.before())
        first = copy.deepcopy(self.fixes())
        self.assert_stops(self.before)
        self.assert_stops(lambda: self.before(FREE_ARG))
        self.assertEqual(self.fixes(), first)

    def test_before_with_no_failure_stops(self):
        self.ready()
        count = self.checks_count()
        self.assert_stops(lambda: self.before("tests/test_app.py"))
        self.assertEqual(self.checks_count(), count + 1, "테스트를 돌린 뒤 멈춰야 함")
        # 원래 깨져 있던 것은 세지 않는다
        self.assert_stops(lambda: self.before("tests/test_old.py", "tests/test_app.py"))
        self.assertEqual(self.checks_count(), count + 2, "테스트를 돌린 뒤 멈춰야 함")
        self.assertNotIn("setup_fixes", self.entry())

    def test_before_with_import_error_stops(self):
        """테스트 본문 안의 가져오기 오류(메시지가 ImportError로 시작)."""
        self.baseline()
        self.write("tests/test_new.py", NEW_TEST_LAZY)
        self.write("app.py", APP_STUB)
        self.red()
        self.write("app.py", APP_RENAMED)
        count = self.checks_count()
        self.assert_stops(self.before)
        self.assertEqual(self.checks_count(), count + 1, "테스트를 돌린 뒤 멈춰야 함")
        self.assertNotIn("setup_fixes", self.entry())

    def test_before_with_collection_failure_stops(self):
        """테스트 파일 첫머리의 가져오기가 깨져 파일을 통째로 불러오지 못함(pytest의 collection failure)."""
        self.ready(app=APP_RENAMED)  # 실패 확인은 shipping이 있는 뼈대로 받고, 구현이 이름을 바꿈
        count = self.checks_count()
        self.assert_stops(self.before)
        self.assertEqual(self.checks_count(), count + 1, "테스트를 돌린 뒤 멈춰야 함")
        _, rec = self.newest_record()
        self.assertEqual(rec["args"], ["tests/test_new.py"])
        self.assertTrue(rec["broken"], "파일을 불러오지 못한 항목이 기록에 있어야 함: %s" % rec)
        self.assertNotIn("setup_fixes", self.entry())

    def test_before_after_accepted_fix_compares_with_fixed_fingerprint(self):
        """인정된 정정 뒤의 before는 그 정정의 after 지문을 기준으로 본다."""
        self.accepted()
        count = self.checks_count()
        # 테스트 쪽이 인정된 그대로면 돌린다(고른 테스트가 모두 통과하므로 멈춘다)
        self.assert_stops(self.before)
        self.assertEqual(self.checks_count(), count + 1, "인정된 지문과 같으면 테스트를 돌려야 함")
        # 인정된 뒤 테스트 쪽이 또 바뀌면 돌리지 않는다
        self.write(SMALL_DATA, SMALL_BROKEN)
        self.assert_stops(self.before, no_run=True)


class AfterTest(SetupFixBase):
    """C4."""

    def test_after_accepts_and_reports_changed_files(self):
        self.ready()
        self.assert_ok(*self.before())
        red = copy.deepcopy(self.entry()["red"])
        item = copy.deepcopy(self.fixes()[0])
        self.write(BIG_DATA, BIG_FIXED)
        count = self.checks_count()
        out = self.assert_ok(*self.after())
        self.assertEqual(self.checks_count(), count + 1)
        _, rec = self.newest_record()
        self.assertEqual(rec["args"], ["tests/test_new.py"])
        self.assertIn([BIG_DATA], values(out), "바뀐 파일 목록을 내야 함")
        logs = self.diff_logs()
        self.assertEqual(len(logs), 1, logs)
        name = os.path.basename(logs[0])
        self.assertTrue(any(s.endswith(name) for s in strings(out)), "변경 기록 경로를 내야 함: %s" % out)
        entry = self.entry()
        self.assertEqual(entry["red"], red)
        fixes = entry["setup_fixes"]
        self.assertEqual(len(fixes), 1)
        self.assertEqual(fixes[0]["red_record"], item["red_record"])
        self.assertEqual(fixes[0]["before"], item["before"], "before 기록은 그대로여야 함")
        self.assertIn("after", fixes[0])
        self.assertIn([BIG_DATA], values(fixes[0]["after"]))
        self.assertTrue(any(s.endswith(name) for s in strings(fixes[0]["after"])))

    def test_after_runs_with_before_args(self):
        self.ready()
        self.assert_ok(*self.before(FREE_ARG))
        self.write(BIG_DATA, BIG_FIXED)
        self.assert_ok(*self.after())
        _, rec = self.newest_record()
        self.assertEqual(rec["args"], [FREE_ARG])

    def after_stop(self, test=None, big=BIG_FIXED, small=None):
        self.ready()
        self.assert_ok(*self.before())
        if test is not None:
            self.write("tests/test_new.py", test)
        self.write(BIG_DATA, big)
        if small is not None:
            self.write(SMALL_DATA, small)
        out = self.assert_stops(self.after)
        self.assertNotIn("after", self.fixes()[0])
        self.assertEqual(self.diff_logs(), [])
        return out

    def assert_fields(self, out, **expected):
        for field, names in expected.items():
            self.assertEqual(out.get(field), names, out)
        for field in FIELDS:
            if field not in expected:
                self.assertFalse(out.get(field), out)

    def test_after_stops_when_a_test_is_added(self):
        out = self.after_stop(test=NEW_TEST_EXTRA)
        self.assert_fields(out, added=[EXTRA])

    def test_after_stops_when_a_test_is_removed(self):
        out = self.after_stop(test=NEW_TEST_NO_SMALL)
        self.assertEqual(out.get("removed"), [FEE], out)
        self.assertFalse(out.get("added"), out)

    def test_after_stops_when_before_failure_still_fails(self):
        out = self.after_stop(big=BIG_STILL)
        self.assert_fields(out, still_failing=[FREE])

    def test_after_stops_when_passing_test_now_errors(self):
        out = self.after_stop(small=SMALL_BROKEN)  # 준비 단계(fixture) 오류
        self.assert_fields(out, regressed=[FEE])

    def test_after_stops_when_passing_test_now_fails(self):
        out = self.after_stop(small=SMALL_OVER)  # 본문의 단언에서 실패
        self.assert_fields(out, regressed=[FEE])

    def test_after_stops_when_passing_test_now_skipped(self):
        out = self.after_stop(test=NEW_TEST_SKIP_SMALL)
        self.assert_fields(out, regressed=[FEE])

    def test_after_stops_when_before_failure_is_skipped(self):
        """before에서 실패하던 테스트에 건너뛰기 표시만 붙임. 건너뜀은 통과가 아니다."""
        out = self.after_stop(test=NEW_TEST_SKIP_FREE, big=BIG_BROKEN)
        self.assert_fields(out, still_failing=[FREE])

    def test_after_when_all_fixes_are_finished_does_not_run(self):
        self.accepted()
        fixes = copy.deepcopy(self.fixes())
        logs = self.diff_logs()
        # 인정된 뒤 테스트 쪽을 또 고친다
        self.write(SMALL_DATA, SMALL_OVER)
        self.assert_stops(self.after, no_run=True)
        self.assertEqual(self.fixes(), fixes, "인정된 정정의 after를 덮어쓰면 안 됨")
        self.assertEqual(self.diff_logs(), logs)

    def test_after_without_report_is_not_run(self):
        self.ready()
        self.assert_ok(*self.before())
        self.write(BIG_DATA, BIG_FIXED)
        self.write("tests/test_new.py", NEW_TEST_EXITS)
        state = self.state_bytes()
        rc, out = self.after()
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(out["verdict"], "not_run", out)
        self.assertEqual(self.state_bytes(), state, "실행되지 않았으면 state.json이 바뀌면 안 됨")
        self.assertNotIn("after", self.fixes()[0])
        self.assertEqual(self.diff_logs(), [])

    def test_after_stop_keeps_before_for_a_later_after(self):
        self.after_stop(big=BIG_STILL)
        self.write(BIG_DATA, BIG_FIXED)
        self.assert_ok(*self.after())
        self.assertIn("after", self.fixes()[0])

    def test_after_with_args_stops(self):
        self.ready()
        self.assert_ok(*self.before())
        self.write(BIG_DATA, BIG_FIXED)
        self.assert_stops(lambda: self.after("tests/test_new.py"), no_run=True)
        self.assertNotIn("after", self.fixes()[0])

    def test_after_without_before_stops(self):
        self.ready()
        self.write(BIG_DATA, BIG_FIXED)
        out = self.assert_stops(self.after, no_run=True)
        self.assertIn("before", out["reason"], "끝나지 않은 before가 없어서 멈췄다고 알려야 함")
        self.assertNotIn("setup_fixes", self.entry())


class AfterDoesNotRunTest(SetupFixBase):
    """C5."""

    def prepared(self):
        self.ready()
        self.assert_ok(*self.before())
        self.write(BIG_DATA, BIG_FIXED)

    def test_commit_since_before(self):
        self.prepared()
        self.git("commit", "-q", "--allow-empty", "-m", "before 뒤 커밋")
        self.assert_stops(self.after, no_run=True)
        self.assertNotIn("after", self.fixes()[0])

    def test_implementation_changed_together(self):
        self.prepared()
        self.write("app.py", APP_IMPL + "\n# 정리\n")
        out = self.assert_stops(self.after, no_run=True)
        self.assertIn("app.py", named(out))
        self.assertNotIn("after", self.fixes()[0])

    def test_new_file_outside_test_globs(self):
        self.prepared()
        self.write("settings.py", "TIMEZONE = 'UTC'\n")
        out = self.assert_stops(self.after, no_run=True)
        self.assertIn("settings.py", named(out))

    def test_no_test_side_change(self):
        self.ready()
        self.assert_ok(*self.before())
        self.assert_stops(self.after, no_run=True)
        self.assertNotIn("after", self.fixes()[0])


class ChangeRecordTest(SetupFixBase):
    """C6."""

    def status(self):
        out = self.git("status", "--porcelain=v1", "--untracked-files=all")
        return [line for line in out.splitlines() if not line[3:].startswith(".harness/")]

    def test_diff_log_has_setup_data_changes_and_index_is_untouched(self):
        self.ready()
        self.git("add", "app.py")  # 사용자가 올려 둔 것이 있는 인덱스
        cached = self.git("diff", "--cached")
        self.assertIn("app.py", cached)
        status = self.status()
        self.assertIn("?? " + BIG_DATA, status)
        self.assert_ok(*self.before())
        self.assertEqual(self.git("diff", "--cached"), cached)
        self.assertEqual(self.status(), status)

        self.write(BIG_DATA, BIG_FIXED)
        self.write("tests/data/currency.json", CURRENCY)  # git에 없는 새 테스트 쪽 파일
        status = self.status()
        out = self.assert_ok(*self.after())
        self.assertEqual(self.git("diff", "--cached"), cached)
        self.assertEqual(self.status(), status)
        self.assertIn("?? tests/data/currency.json", status)

        lists = [sorted(v) for v in values(out) if isinstance(v, list) and all(isinstance(x, str) for x in v)]
        self.assertIn(sorted([BIG_DATA, "tests/data/currency.json"]), lists, "바뀐 파일 목록을 내야 함")
        logs = self.diff_logs()
        self.assertEqual(len(logs), 1, logs)
        with open(logs[0], encoding="utf-8") as f:
            diff = f.read()
        lines = diff.splitlines()
        self.assertIn(BIG_DATA, diff)
        self.assertIn("-" + BIG_BROKEN.strip(), lines)
        self.assertIn("+" + BIG_FIXED.strip(), lines)
        self.assertIn("tests/data/currency.json", diff)
        self.assertIn("+" + CURRENCY.strip(), lines)
        self.assertNotIn(SMALL_DATA, diff, "바뀌지 않은 파일은 변경 기록에 없어야 함")
        self.assertNotIn("app.py", diff, "테스트 쪽 밖은 변경 기록에 없어야 함")


class GreenTest(SetupFixBase):
    """C7."""

    def test_green_passes_with_accepted_fix(self):
        self.accepted()
        out = self.assert_ok(*self.green())
        self.assertIn(BIG_DATA, out["paths"])
        self.assertIn("green", self.entry())

    def test_green_goes_on_to_the_other_gates_with_accepted_fix(self):
        self.accepted()
        self.write("app.py", APP_IMPL_WRONG_FEE)
        out = self.assert_stops(self.green)
        self.assertIn("아직 통과하지 않음", out["reason"])
        self.assertEqual(out["tests"], [FEE])

    def test_green_passes_with_fix_accepted_on_given_args(self):
        """before에 인자를 주어 고른 테스트로 정정이 인정돼도, after 지문은 할 일 check_args 기준이라
        통과 확인(check_args로 지문을 냄)이 받아들인다."""
        self.ready()
        self.assert_ok(*self.before(FREE_ARG))
        self.write(BIG_DATA, BIG_FIXED)
        self.assert_ok(*self.after())
        _, rec = self.newest_record()
        self.assertEqual(rec["args"], [FREE_ARG], "after는 before의 인자로 돌려야 함")
        out = self.assert_ok(*self.green())
        self.assertIn(BIG_DATA, out["paths"])
        self.assertIn("green", self.entry())

    def test_green_stops_on_test_change_without_fix_record(self):
        self.ready()
        self.write(BIG_DATA, BIG_FIXED)
        out = self.assert_stops(self.green, no_run=True)
        self.assertIn("실패 확인 뒤에 테스트가 바뀜", out["reason"])

    def test_green_stops_with_unfinished_before_and_unchanged_tests(self):
        self.ready()
        self.assert_ok(*self.before())
        # 테스트 쪽은 실패 확인 때 그대로지만 끝나지 않은 before가 있다
        out = self.assert_stops(self.green, no_run=True)
        self.assertIn("before", out["reason"], "끝나지 않은 before 때문에 멈췄다고 알려야 함")
        self.assertNotIn("green", self.entry())

    def test_green_stops_on_test_change_while_fix_is_not_accepted(self):
        """before만 받고 after로 인정받지 않은 채 테스트 쪽을 바꿈. 인정된 정정 기록이 없는 테스트 변경이므로
        지금처럼 "실패 확인 뒤에 테스트가 바뀜"으로 멈춘다."""
        self.ready()
        self.assert_ok(*self.before())
        self.write(BIG_DATA, BIG_FIXED)
        out = self.assert_stops(self.green, no_run=True)
        self.assertIn("실패 확인 뒤에 테스트가 바뀜", out["reason"])
        self.assertNotIn("green", self.entry())

    def test_green_stops_with_unfinished_before_after_accepted_fix(self):
        """인정된 정정의 after 지문과 지금 지문이 같아도, 그 뒤 끝나지 않은 before가 있으면 받지 않는다."""
        self.accepted()
        self.write("app.py", APP_IMPL_WRONG_FEE)
        self.assert_ok(*self.before())  # 테스트 쪽은 인정된 그대로, 배송비 테스트가 실패
        self.assertEqual(len(self.fixes()), 2)
        self.assertNotIn("after", self.fixes()[1])
        self.write("app.py", APP_IMPL)
        out = self.assert_stops(self.green, no_run=True)
        self.assertIn("실패 확인 뒤에 테스트가 바뀜", out["reason"])
        self.assertNotIn("green", self.entry())

    def test_green_stops_when_tests_change_again_after_fix(self):
        self.accepted()
        self.write("tests/data/currency.json", CURRENCY)
        out = self.assert_stops(self.green, no_run=True)
        self.assertIn("실패 확인 뒤에 테스트가 바뀜", out["reason"])

    def test_fix_before_a_new_red_is_kept_but_not_used(self):
        self.accepted()
        fixes = copy.deepcopy(self.fixes())
        red = copy.deepcopy(self.entry()["red"])
        # 테스트를 고치고 구현을 빼 둔 뒤 실패 확인을 새로 받는다
        self.write("tests/test_new.py", NEW_TEST_EXTRA)
        self.write("app.py", APP_STUB)
        self.red()
        entry = self.entry()
        self.assertEqual(entry["setup_fixes"], fixes, "앞 정정은 기록으로 남아야 함")
        self.assertEqual(entry["red_history"], [red])
        self.assertEqual(set(entry), {"red", "red_history", "setup_fixes"})
        # 테스트 쪽을 앞 정정의 after 때 그대로 되돌려도 그 정정은 새 실패 확인의 근거가 아니다
        self.write("tests/test_new.py", NEW_TEST)
        self.write("app.py", APP_IMPL)
        # before도 앞 정정의 after 지문이 아니라 새 실패 확인의 지문을 기준으로 본다
        self.assert_stops(self.before, no_run=True)
        self.assertEqual(self.entry()["setup_fixes"], fixes)
        out = self.assert_stops(self.green, no_run=True)
        self.assertIn("실패 확인 뒤에 테스트가 바뀜", out["reason"])

    def unfinished_then_new_red(self):
        """before -> after가 멈춤(아직 실패) -> 입력 파일을 되돌림 -> 테스트를 하나 더하고 구현을 빼 둔 뒤
        실패 확인을 새로 받은 상태. 앞 실패 확인에 기댄 before는 끝나지 않은 채 남는다.
        (앞 정정 항목들, 앞 실패 확인 기록)을 돌려준다."""
        self.ready()
        self.assert_ok(*self.before())
        self.write(BIG_DATA, BIG_STILL)
        out = self.assert_stops(self.after)
        self.assertEqual(out.get("still_failing"), [FREE], out)
        self.assertNotIn("after", self.fixes()[0])
        fixes = copy.deepcopy(self.fixes())
        old_red = copy.deepcopy(self.entry()["red"])
        self.write(BIG_DATA, BIG_BROKEN)  # 준비 데이터 변경을 되돌림
        self.write("tests/test_new.py", NEW_TEST_EXTRA)
        self.write("app.py", APP_STUB)
        self.red()
        return fixes, old_red

    def test_unfinished_before_of_an_earlier_red_is_kept_as_record(self):
        fixes, old_red = self.unfinished_then_new_red()
        entry = self.entry()
        self.assertNotEqual(entry["red"]["record"], old_red["record"])
        self.assertEqual(entry["red_history"], [old_red])
        self.assertEqual(entry["setup_fixes"], fixes, "앞 정정은 끝나지 않았어도 그대로 남아야 함")
        self.assertEqual(len(entry["setup_fixes"]), 1)
        self.assertEqual(entry["setup_fixes"][0]["red_record"], old_red["record"])
        self.assertNotIn("after", entry["setup_fixes"][0])

    def test_green_is_not_blocked_by_unfinished_before_of_an_earlier_red(self):
        fixes, _ = self.unfinished_then_new_red()
        self.write("app.py", APP_IMPL_DEFAULT_QTY)
        out = self.assert_ok(*self.green())
        self.assertIn("app.py", out["paths"])
        entry = self.entry()
        self.assertIn("green", entry)
        self.assertEqual(entry["setup_fixes"], fixes)

    def test_after_does_not_use_before_of_an_earlier_red(self):
        fixes, _ = self.unfinished_then_new_red()
        self.write("app.py", APP_IMPL)
        self.write(BIG_DATA, BIG_FIXED)
        out = self.assert_stops(self.after, no_run=True)
        self.assertIn("before", out["reason"], "지금 실패 확인에 기댄 끝나지 않은 before가 없어서 멈췄다고 알려야 함")
        self.assertEqual(self.entry()["setup_fixes"], fixes)
        self.assertEqual(self.diff_logs(), [])

    def test_new_before_is_not_blocked_by_unfinished_before_of_an_earlier_red(self):
        fixes, _ = self.unfinished_then_new_red()
        self.write("app.py", APP_IMPL)
        count = self.checks_count()
        self.assert_ok(*self.before())
        self.assertEqual(self.checks_count(), count + 1)
        rec_path, _ = self.newest_record()
        entry = self.entry()
        new = entry["setup_fixes"]
        self.assertEqual(len(new), 2)
        self.assertEqual(new[0], fixes[0], "앞 정정 항목은 바뀌면 안 됨")
        self.assertEqual(new[1]["red_record"], entry["red"]["record"])
        self.assertNotIn("after", new[1])
        self.assertIn({FREE: "error", FEE: "passed", EXTRA: "passed"}, values(new[1]["before"]))
        self.assertIn(rec_path, values(new[1]["before"]))
        # 준비 데이터를 고치면 새 before가 인정되고, 앞 실패 확인의 끝나지 않은 항목은 그대로 남는다
        red = copy.deepcopy(entry["red"])
        new_before = copy.deepcopy(new[1]["before"])
        self.write(BIG_DATA, BIG_FIXED)
        self.assert_ok(*self.after())
        done = self.entry()["setup_fixes"]
        self.assertEqual(len(done), 2)
        self.assertEqual(done[0], fixes[0], "앞 실패 확인의 끝나지 않은 항목은 바뀌면 안 됨")
        self.assertNotIn("after", done[0])
        self.assertEqual(done[1]["red_record"], red["record"])
        self.assertEqual(done[1]["before"], new_before, "before 기록은 그대로여야 함")
        self.assertIn("after", done[1], "지금 실패 확인에 기댄 before에 after가 남아야 함")
        self.assertIn([BIG_DATA], values(done[1]["after"]))
        # 지문은 실패 확인 때와 다르지만 인정된 정정의 after 지문과 같다.
        # 앞 실패 확인의 끝나지 않은 before는 통과 확인을 막지 않는다
        out = self.assert_ok(*self.green())
        self.assertIn(BIG_DATA, out["paths"])
        entry = self.entry()
        self.assertIn("green", entry)
        self.assertEqual(entry["red"], red)
        self.assertEqual(entry["setup_fixes"], done)


if __name__ == "__main__":
    unittest.main()
