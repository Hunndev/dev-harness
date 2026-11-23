"""바탕 검사의 준비 데이터 정정(setup-fix --baseline) 테스트.

test_hb_setup_fix.py처럼 임시 git 저장소에 작은 가짜 제품(주문 배송비)을 만들고 진짜 pytest로 검사를 돌린다.
준비 데이터는 테스트가 읽는 입력 파일(tests/data/*)이고, 검사 계약의 test_globs에 들어 있다.
처음 커밋부터 큰 주문의 입력 파일에 수량(qty)이 빠져 있어, 바탕 검사에서 준비 단계(fixture) 오류가 나는 상황이다.
- C8: 돌리기 전 조건이 하나라도 어긋나면 테스트를 돌리지 않고(새 checks/ 기록 없음) 멈추며 state.json은 그대로다.
- C9: 바탕 검사 기록의 args로 돌리고, 인정 조건을 모두 만족할 때만 인정한다. 아니면 칸별로 이름을 낸다.
      cases가 없는 바탕 검사 기록은 보고서에서 이름을 읽는다. 원래 바탕 검사 기록과 보고서의 바이트는 그대로다.
- C10: 인정되면 baseline.setup_fix와 변경 기록(logs/baseline-setup-fix.diff.log)이 남고, 인덱스와 작업 트리는
       그대로다. 그 뒤 통과 확인의 "원래 깨져 있던 것"은 baseline.broken 그대로다.
실행: <테스트 환경의 python> -m pytest tests/test_hb_setup_fix_baseline.py   (pytest가 깔린 파이썬이어야 함)
"""
import copy
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
    "test_globs": ["test_*.py", "conftest.py", "tests/data/*"],
}
TASK = {
    "id": "01", "title": "할인", "kind": "feature", "criteria": ["C1"],
    "allowed_files": ["app.py", "tests/test_new.py", "tests/data/*"], "check_args": ["tests/test_new.py"],
}
APP = textwrap.dedent("""\
    def add(a, b):
        return a + b


    def make_order(data):
        return [{"price": i["price"], "qty": i["qty"]} for i in data["items"]]


    def shipping(items):
        return 0 if sum(i["price"] * i["qty"] for i in items) >= 50 else 3
""")
APP_DISCOUNT_STUB = APP + "\n\ndef discount(total):\n    return None\n"
APP_DISCOUNT = APP + "\n\ndef discount(total):\n    return total - total // 10\n"

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
ORDER_TEST = TEST_HEAD + TEST_SMALL
ORDER_TEST_EXTRA = ORDER_TEST + TEST_EXTRA          # 테스트가 하나 늘어남
ORDER_TEST_NO_SMALL = TEST_HEAD                     # 테스트가 하나 줄어듦
ORDER_TEST_SKIP_SMALL = TEST_HEAD + TEST_SMALL_SKIPPED
# 바탕 검사에서 깨졌던 테스트에 건너뛰기 표시만 붙임(입력 파일은 그대로)
ORDER_TEST_SKIP_FREE = ORDER_TEST.replace(
    "def test_free_shipping_over_limit(big_order):",
    "@pytest.mark.skip(reason=\"later\")\ndef test_free_shipping_over_limit(big_order):")
# 테스트 파일을 불러오는 중에 프로세스가 끝나 보고서가 나오지 않는다
ORDER_TEST_EXITS = "import os\n\nos._exit(0)\n" + ORDER_TEST
# 할 일의 새 테스트(바탕 정정 뒤의 실패 확인과 통과 확인에 쓴다)
NEW_TEST = "from app import discount\n\n\ndef test_discount():\n    assert discount(100) == 90\n"
# 다른 할 일 기록을 만들 때 쓰는 테스트(구현 없이 본문에서 실패)
NEW_TEST_FAILING = "from app import add\n\n\ndef test_add_more():\n    assert add(2, 2) == 5\n"

BIG_BROKEN = '{"items": [{"price": 30}, {"price": 25}]}\n'           # 수량이 빠짐
BIG_FIXED = '{"items": [{"price": 30, "qty": 1}, {"price": 25, "qty": 1}]}\n'
BIG_STILL = '{"items": [{"price": 35}, {"price": 25}]}\n'            # 고쳤지만 수량은 여전히 없음
SMALL = '{"items": [{"price": 10, "qty": 2}]}\n'
SMALL_OTHER = '{"items": [{"price": 12, "qty": 2}]}\n'               # 금액만 바뀜, 여전히 통과
SMALL_BROKEN = '{"items": [{"price": 10}]}\n'                       # 준비 단계(fixture) 오류
SMALL_OVER = '{"items": [{"price": 30, "qty": 2}]}\n'               # 준비는 되지만 본문에서 실패
CURRENCY = '{"currency": "KRW"}\n'

# 공용 준비 코드가 읽는 latin-1 입력 파일. 도시 칸이 비어 있으면 본문에서 실패한다.
NAMES_TEST = textwrap.dedent("""\
    import os

    import pytest

    DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


    @pytest.fixture
    def rows():
        with open(os.path.join(DATA, "names.txt"), encoding="latin-1") as f:
            lines = f.read().splitlines()[1:]
        return [dict(zip(("name", "city"), line.split(";"))) for line in lines]


    def test_every_row_has_city(rows):
        assert rows and all(r["city"] for r in rows)
""")
NAMES_BROKEN = b"name;city\nJos\xe9;\n"
NAMES_FIXED = b"name;city\nJos\xe9;Montr\xe9al\n"

# 표시 파일이 있으면 검사하는 동안 저장소 맨 위에 새 파일을 만들거나(touch.flag) 빈 커밋을 만드는(commit.flag) 테스트
TOUCH_TEST = textwrap.dedent("""\
    import os
    import subprocess

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


    def test_touch():
        if os.path.exists(os.path.join(ROOT, "tests", "data", "touch.flag")):
            with open(os.path.join(ROOT, "stray.txt"), "w") as f:
                f.write("x")
        if os.path.exists(os.path.join(ROOT, "tests", "data", "commit.flag")):
            subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "during check"], cwd=ROOT, check=True)
""")

BIG_DATA = "tests/data/order_big.json"
SMALL_DATA = "tests/data/order_small.json"
NAMES_DATA = "tests/data/names.txt"
ORDER_FILE = "tests/test_order.py"
FREE = "tests.test_order::test_free_shipping_over_limit"
FEE = "tests.test_order::test_shipping_fee_under_limit"
EXTRA = "tests.test_order::test_fee_without_items"
NAMES = "tests.test_names::test_every_row_has_city"
DIFF_LOG = "logs/baseline-setup-fix.diff.log"
FIELDS = ("added", "removed", "still_failing", "regressed")


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
class BaselineFixBase(unittest.TestCase):
    def initial_files(self):
        """처음 커밋에 넣을 파일 {경로: 내용(문자열이나 바이트)}."""
        return {
            ".gitignore": "logs/\n__pycache__/\n.pytest_cache/\n",
            "conftest.py": "",
            "app.py": APP,
            "tests/test_app.py": "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
            ORDER_FILE: ORDER_TEST,
            BIG_DATA: BIG_BROKEN,
            SMALL_DATA: SMALL,
            ".harness/docs/checks.json": json.dumps(CHECKS),
            WORK_DIR + "/tasks.json": json.dumps({"work": WORK, "tasks": [TASK]}, ensure_ascii=False),
        }

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="hb-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        for rel, content in self.initial_files().items():
            self.write(rel, content)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "start")

    # --- 도우미 ---
    def git(self, *args):
        r = subprocess.run(["git", *args], cwd=self.root, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.decode("utf-8", "replace")

    def write(self, rel, content):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content if isinstance(content, bytes) else content.encode("utf-8"))

    def work_path(self, rel):
        return os.path.join(self.root, WORK_DIR, rel)

    def read_bytes(self, rel):
        with open(self.work_path(rel), "rb") as f:
            return f.read()

    def commit(self, message, files):
        """files {경로: 내용}을 쓰고 그 경로만 올려 커밋한다."""
        for rel, content in files.items():
            self.write(rel, content)
        self.git("add", "--", *files)
        self.git("commit", "-q", "-m", message)

    def hb(self, *args):
        # 크기가 같은 변경이 같은 초에 쓰이면 옛 .pyc가 쓰여 깨진 동작이 가려지므로 바이트코드를 쓰지 않는다.
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, HB, "--repo", self.root, *args], capture_output=True, text=True, env=env)
        try:
            out = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            self.fail("hb가 판정을 내지 않음: rc=%s out=%r err=%r" % (r.returncode, r.stdout[-300:], r.stderr[-300:]))
        return r.returncode, out

    def setup_fix(self, *extra):
        return self.hb("setup-fix", "--work", WORK, "--baseline", *extra)

    def state(self):
        with open(self.work_path("state.json"), encoding="utf-8") as f:
            return json.load(f)

    def state_bytes(self):
        return self.read_bytes("state.json")

    def head(self):
        return self.git("rev-parse", "HEAD").strip()

    def check_names(self):
        folder = self.work_path("checks")
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def checks_count(self):
        return len(self.check_names())

    def record(self, rel):
        with open(self.work_path(rel), encoding="utf-8") as f:
            return json.load(f)

    def newest_record(self):
        name = self.check_names()[-1]
        return "checks/" + name, self.record("checks/" + name)

    def save_record(self, rel, data):
        with open(self.work_path(rel), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def base_record_path(self):
        return self.state()["baseline"]["record"]

    def edit_base_record(self, drop=(), **changes):
        """바탕 검사 기록(checks/001-…json)의 칸을 지우거나 바꾼다."""
        rel = self.base_record_path()
        rec = self.record(rel)
        for key in drop:
            rec.pop(key, None)
        rec.update(changes)
        self.save_record(rel, rec)
        return rec

    def baseline(self):
        rc, out = self.hb("baseline", "--work", WORK)
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        return out

    def assert_ok(self, rc, out):
        self.assertEqual((rc, out["verdict"]), (0, "ok"), out)
        return out

    def assert_stops(self, run, no_run=False):
        """멈추고 state.json과 원래 바탕 검사 기록·보고서가 바이트 그대로인지 본다.
        no_run이면 새 checks/ 기록도 없어야 한다."""
        state = self.state_bytes()
        orig = self.original()
        count = self.checks_count()
        rc, out = run()
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(out["verdict"], "stop", out)
        self.assertEqual(self.state_bytes(), state, "멈춘 뒤 state.json이 바뀜")
        if no_run:
            self.assertEqual(self.checks_count(), count, "테스트를 돌리지 않아야 함")
        else:
            self.assertEqual(self.checks_count(), count + 1, "테스트를 돌린 뒤 멈춰야 함")
        self.assertFalse(os.path.exists(self.work_path(DIFF_LOG)), "멈췄는데 변경 기록이 남음")
        self.assert_original_kept(orig)
        return out

    def assert_reason(self, out, *words):
        """멈춤 이유에 words 가운데 하나가 들어 있다."""
        self.assertTrue(any(w in out.get("reason", "") for w in words),
                        "멈춤 이유에 %s 가운데 하나가 있어야 함: %s" % (words, out))

    def original(self):
        """원래 바탕 검사 기록 파일, 그 보고서의 바이트와 state.json의 baseline 칸."""
        state = self.state()
        rel = state["baseline"]["record"]
        rec = self.record(rel)
        report = self.work_path(rec["report"])
        report_bytes = None
        if os.path.exists(report):
            with open(report, "rb") as f:
                report_bytes = f.read()
        return {"record": self.read_bytes(rel), "report": report_bytes, "baseline": copy.deepcopy(state["baseline"]),
                "rel": rel, "report_rel": rec["report"]}

    def assert_original_kept(self, orig):
        self.assertEqual(self.read_bytes(orig["rel"]), orig["record"], "원래 바탕 검사 기록이 바뀜")
        if orig["report"] is None:
            self.assertFalse(os.path.exists(self.work_path(orig["report_rel"])))
        else:
            self.assertEqual(self.read_bytes(orig["report_rel"]), orig["report"], "원래 바탕 검사 보고서가 바뀜")
        baseline, expected = dict(self.state()["baseline"]), dict(orig["baseline"])
        baseline.pop("setup_fix", None)
        expected.pop("setup_fix", None)
        self.assertEqual(baseline, expected, "baseline의 기존 칸이 바뀜")

    def diff_files(self):
        """변경 기록(diff)의 파일 머리("diff --git a/<경로> b/<경로>")에 나온 경로 목록."""
        heads = [line for line in self.read_bytes(DIFF_LOG).splitlines() if line.startswith(b"diff --git a/")]
        return sorted(line[len(b"diff --git a/"):].split(b" b/", 1)[0].decode("utf-8") for line in heads)

    def assert_fields(self, out, **expected):
        for field, names in expected.items():
            self.assertEqual(out.get(field), names, out)
        for field in FIELDS:
            if field not in expected:
                self.assertFalse(out.get(field), out)

    def fix(self, **extra):
        """입력 파일의 수량을 채워 커밋한다."""
        self.commit("준비 데이터 고침", {BIG_DATA: BIG_FIXED, **extra})

    def accepted(self):
        self.baseline()
        self.fix()
        return self.assert_ok(*self.setup_fix())


class NotRunTest(BaselineFixBase):
    """C8: 돌리기 전 조건이 어긋나면 테스트를 돌리지 않는다."""

    def test_without_baseline_record_does_not_run(self):
        self.fix()
        rc, out = self.setup_fix()
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(out["verdict"], "stop", out)
        self.assert_reason(out, "바탕 검사")
        self.assertEqual(self.checks_count(), 0, "테스트를 돌리지 않아야 함")
        self.assertFalse(os.path.exists(self.work_path("state.json")), "state.json을 만들면 안 됨")

    def test_with_task_record_does_not_run(self):
        self.baseline()
        self.commit("고침과 새 테스트", {BIG_DATA: BIG_FIXED, "tests/test_new.py": NEW_TEST_FAILING})
        self.assert_ok(*self.hb("check", "--work", WORK, "--task", "01", "--phase", "red"))
        self.assertIn("01", self.state()["tasks"])
        out = self.assert_stops(self.setup_fix, no_run=True)
        self.assert_reason(out, "할 일")

    def test_with_empty_broken_does_not_run(self):
        self.commit("바탕 검사 전에 고침", {BIG_DATA: BIG_FIXED})
        self.baseline()
        self.assertEqual(self.state()["baseline"]["broken"], [])
        self.commit("금액 바꿈", {SMALL_DATA: SMALL_OTHER})
        out = self.assert_stops(self.setup_fix, no_run=True)
        self.assert_reason(out, "깨져", "깨진")

    def test_with_uncommitted_change_outside_work_does_not_run(self):
        self.baseline()
        self.fix()
        self.write("app.py", APP + "\n# 정리\n")
        out = self.assert_stops(self.setup_fix, no_run=True)
        self.assert_reason(out, "커밋되지 않은", "커밋하지 않은")
        self.git("checkout", "--", "app.py")
        self.write("notes.txt", "메모\n")  # git에 없는 새 파일
        out = self.assert_stops(self.setup_fix, no_run=True)
        self.assert_reason(out, "커밋되지 않은", "커밋하지 않은")

    def test_with_uncommitted_change_inside_test_globs_does_not_run(self):
        """테스트 쪽 파일(test_globs 안)의 커밋되지 않은 고침도 비교하지 않고 멈춘다."""
        self.baseline()
        self.commit("금액 바꿈", {SMALL_DATA: SMALL_OTHER})  # 커밋된 테스트 쪽 변경은 있음
        self.write(BIG_DATA, BIG_FIXED)  # 고침을 커밋하지 않음
        out = self.assert_stops(self.setup_fix, no_run=True)
        self.assert_reason(out, "커밋되지 않은", "커밋하지 않은")
        self.git("add", "--", BIG_DATA)  # 올리기만 하고 커밋하지 않음
        out = self.assert_stops(self.setup_fix, no_run=True)
        self.assert_reason(out, "커밋되지 않은", "커밋하지 않은")
        self.git("commit", "-q", "-m", "준비 데이터 고침")
        self.write("tests/data/currency.json", CURRENCY)  # git에 없는 새 준비 데이터 파일
        out = self.assert_stops(self.setup_fix, no_run=True)
        self.assert_reason(out, "커밋되지 않은", "커밋하지 않은")
        self.assertNotIn("setup_fix", self.state()["baseline"])
        # 커밋되지 않은 것을 치우면 나머지 조건은 모두 맞으므로 인정된다
        os.remove(os.path.join(self.root, "tests/data/currency.json"))
        out = self.assert_ok(*self.setup_fix())
        self.assertEqual(out["changed"], sorted([BIG_DATA, SMALL_DATA]))

    def test_when_baseline_head_is_not_an_ancestor_does_not_run(self):
        self.baseline()
        self.write(BIG_DATA, BIG_FIXED)
        self.git("add", "--", BIG_DATA)
        self.git("commit", "-q", "--amend", "--no-edit")  # 바탕 검사 커밋을 고쳐 써서 이어지지 않게 함
        out = self.assert_stops(self.setup_fix, no_run=True)
        self.assert_reason(out, "조상", "이어지지")

    def test_change_outside_test_globs_does_not_run(self):
        self.baseline()
        self.fix(**{"app.py": APP + "\n# 정리\n", "settings.py": "TIMEZONE = 'UTC'\n"})
        out = self.assert_stops(self.setup_fix, no_run=True)
        self.assertEqual(sorted(out.get("outside") or []), ["app.py", "settings.py"], out)

    def test_no_test_side_change_does_not_run(self):
        self.baseline()
        out = self.assert_stops(self.setup_fix, no_run=True)  # 커밋이 하나도 없음
        self.assert_reason(out, "바뀐", "바뀌지")
        self.assertFalse(out.get("outside"), out)
        self.commit("작업 기록", {WORK_DIR + "/INDEX.md": "# 작업\n"})  # 작업 폴더 안 커밋만 있음
        out = self.assert_stops(self.setup_fix, no_run=True)
        self.assert_reason(out, "바뀐", "바뀌지")
        self.assertFalse(out.get("outside"), out)

    def test_second_baseline_fix_does_not_run(self):
        self.accepted()
        fix = copy.deepcopy(self.state()["baseline"]["setup_fix"])
        diff = self.read_bytes(DIFF_LOG)
        os.remove(self.work_path(DIFF_LOG))  # 멈춘 뒤 새 변경 기록이 없는지 보려고 치움
        self.commit("금액 바꿈", {SMALL_DATA: SMALL_OTHER})
        out = self.assert_stops(self.setup_fix, no_run=True)
        self.assert_reason(out, "이미")
        self.assertEqual(self.state()["baseline"]["setup_fix"], fix)
        self.assertNotEqual(diff, b"")

    def test_with_task_phase_or_args_does_not_run(self):
        self.baseline()
        self.fix()
        for extra in (("--task", "01"), ("--phase", "before"), ("--task", "01", "--phase", "after"),
                      ("--", ORDER_FILE)):
            out = self.assert_stops(lambda: self.setup_fix(*extra), no_run=True)
            self.assert_reason(out, "함께")
        self.assertNotIn("setup_fix", self.state()["baseline"])
        # 조건은 모두 맞으므로 인자 없이 주면 인정된다
        self.assert_ok(*self.setup_fix())

    def test_task_branch_without_task_or_phase_stops(self):
        self.baseline()
        out = self.assert_stops(lambda: self.hb("setup-fix", "--work", WORK, "--phase", "before"), no_run=True)
        self.assert_reason(out, "--task")
        out = self.assert_stops(lambda: self.hb("setup-fix", "--work", WORK, "--task", "01"), no_run=True)
        self.assert_reason(out, "--phase")
        self.assertEqual(self.state()["tasks"], {})


class AcceptTest(BaselineFixBase):
    """C9: 인정 갈래."""

    def test_accepts_with_record_commit_between(self):
        self.baseline()
        orig = self.original()
        base_rec = self.record(orig["rel"])
        self.assertEqual(base_rec["broken"], [FREE])
        self.commit("작업 기록", {WORK_DIR + "/INDEX.md": "# 작업\n"})  # 작업 폴더 안 기록 커밋이 섞임
        self.fix()
        count = self.checks_count()
        out = self.assert_ok(*self.setup_fix())
        self.assertEqual(self.checks_count(), count + 1)
        rec_path, rec = self.newest_record()
        self.assertTrue(rec_path.endswith("-baseline-setup-fix.json"), rec_path)
        self.assertEqual(rec["args"], base_rec["args"])
        self.assertEqual(sorted(c[0] for c in rec["cases"]), sorted(c[0] for c in base_rec["cases"]))
        self.assertEqual(out["fixed"], [FREE])
        self.assertEqual(out["changed"], [BIG_DATA])
        self.assertEqual(out["diff"], DIFF_LOG)
        self.assertEqual(out["record"], rec_path)
        self.assertEqual(out["baseline_record"], orig["rel"])
        self.assertTrue(out.get("summary"), out)
        self.assertIn("setup_fix", self.state()["baseline"])
        self.assertEqual(self.diff_files(), [BIG_DATA], "변경 기록에는 바뀐 파일만 있어야 함(작업 폴더 커밋 제외)")
        self.assert_original_kept(orig)

    def test_runs_with_baseline_record_args(self):
        """검사 계약의 full_args가 아니라 바탕 검사 기록의 args로 돈다."""
        self.baseline()
        self.edit_base_record(args=["-q", "-p", "no:cacheprovider"])
        orig = self.original()
        self.fix()
        self.assert_ok(*self.setup_fix())
        _, rec = self.newest_record()
        self.assertEqual(rec["args"], ["-q", "-p", "no:cacheprovider"])
        self.assert_original_kept(orig)

    def test_record_with_cases_and_no_report_accepts(self):
        """기록에 cases가 있으면 보고서가 없어도 그것을 고치기 전 목록으로 쓴다."""
        self.baseline()
        os.remove(self.work_path(self.record(self.base_record_path())["report"]))
        orig = self.original()
        self.fix()
        out = self.assert_ok(*self.setup_fix())
        self.assertEqual(out["fixed"], [FREE])
        self.assert_original_kept(orig)


class StopTest(BaselineFixBase):
    """C9: 인정 조건이 어긋나면 돌린 뒤 칸별로 이름을 내고 멈춘다."""

    def fix_stop(self, test=None, big=BIG_FIXED, small=None):
        self.baseline()
        orig = self.original()
        files = {BIG_DATA: big}
        if test is not None:
            files[ORDER_FILE] = test
        if small is not None:
            files[SMALL_DATA] = small
        self.commit("준비 데이터 고침", files)
        out = self.assert_stops(self.setup_fix)
        self.assertNotIn("setup_fix", self.state()["baseline"])
        self.assert_original_kept(orig)
        return out

    def test_stops_when_a_test_is_added(self):
        out = self.fix_stop(test=ORDER_TEST_EXTRA)
        self.assert_fields(out, added=[EXTRA])

    def test_stops_when_a_test_is_removed(self):
        out = self.fix_stop(test=ORDER_TEST_NO_SMALL)
        self.assert_fields(out, removed=[FEE])

    def test_stops_when_broken_test_still_fails(self):
        out = self.fix_stop(big=BIG_STILL)
        self.assert_fields(out, still_failing=[FREE])

    def test_stops_when_broken_test_is_skipped(self):
        """깨졌던 테스트에 건너뛰기 표시만 붙임. 건너뜀은 통과가 아니다."""
        out = self.fix_stop(test=ORDER_TEST_SKIP_FREE, big=BIG_BROKEN)
        self.assert_fields(out, still_failing=[FREE])

    def test_stops_when_passing_test_now_fails(self):
        out = self.fix_stop(small=SMALL_OVER)
        self.assert_fields(out, regressed=[FEE])

    def test_stops_when_passing_test_now_errors(self):
        out = self.fix_stop(small=SMALL_BROKEN)
        self.assert_fields(out, regressed=[FEE])

    def test_stops_when_passing_test_now_skipped(self):
        out = self.fix_stop(test=ORDER_TEST_SKIP_SMALL)
        self.assert_fields(out, regressed=[FEE])

    def test_without_report_is_not_run(self):
        self.baseline()
        orig = self.original()
        state = self.state_bytes()
        self.fix(**{ORDER_FILE: ORDER_TEST_EXITS})
        rc, out = self.setup_fix()
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(out["verdict"], "not_run", out)
        self.assertEqual(self.state_bytes(), state, "실행되지 않았으면 state.json이 바뀌면 안 됨")
        self.assertFalse(os.path.exists(self.work_path(DIFF_LOG)))
        self.assert_original_kept(orig)

    def test_stop_keeps_way_open_for_a_later_fix(self):
        self.fix_stop(big=BIG_STILL)
        self.commit("다시 고침", {BIG_DATA: BIG_FIXED})
        out = self.assert_ok(*self.setup_fix())
        self.assertEqual(out["fixed"], [FREE])


class SkippedFromStartTest(BaselineFixBase):
    """C9: 처음 커밋부터 건너뛰던 테스트가 그대로 건너뜀이면 나빠진 것이 아니므로 인정된다."""

    def initial_files(self):
        return {**super().initial_files(), ORDER_FILE: ORDER_TEST_SKIP_SMALL}

    def test_test_skipped_from_start_stays_skipped_and_accepts(self):
        self.baseline()
        orig = self.original()
        base_rec = self.record(orig["rel"])
        self.assertEqual(base_rec["broken"], [FREE])
        self.assertIn([FEE, "skipped"], base_rec["cases"])
        self.fix()
        out = self.assert_ok(*self.setup_fix())
        self.assertEqual(out["fixed"], [FREE])
        self.assert_fields(out)
        _, rec = self.newest_record()
        self.assertIn([FEE, "skipped"], rec["cases"])
        self.assertIn([FREE, "passed"], rec["cases"])
        self.assertIn("setup_fix", self.state()["baseline"])
        self.assert_original_kept(orig)


class TouchStopTest(BaselineFixBase):
    """C9: 검사하는 동안 파일이 바뀌면 인정하지 않는다."""

    def initial_files(self):
        return {**super().initial_files(), "tests/test_touch.py": TOUCH_TEST}

    def test_stops_when_files_change_during_check(self):
        self.baseline()
        orig = self.original()
        self.fix(**{"tests/data/touch.flag": "on\n"})
        out = self.assert_stops(self.setup_fix)
        self.assertTrue(os.path.exists(os.path.join(self.root, "stray.txt")), "검사가 파일을 만들었어야 함")
        self.assert_reason(out, "검사하는 동안")
        self.assertNotIn("setup_fix", self.state()["baseline"])
        self.assert_original_kept(orig)

    def test_stops_when_commit_changes_during_check(self):
        """검사하는 동안 커밋만 바뀌고 작업 트리는 깨끗한 경우."""
        self.baseline()
        orig = self.original()
        self.fix(**{"tests/data/commit.flag": "on\n"})
        head = self.head()
        out = self.assert_stops(self.setup_fix)
        self.assertNotEqual(self.head(), head, "검사가 커밋을 만들었어야 함")
        status = self.git("status", "--porcelain=v1", "--untracked-files=all").splitlines()
        self.assertEqual([s for s in status if not s[3:].startswith(WORK_DIR + "/")], [], "작업 트리는 깨끗해야 함")
        self.assert_reason(out, "검사하는 동안")
        self.assertNotIn("setup_fix", self.state()["baseline"])
        self.assert_original_kept(orig)


class RecordWithoutCasesTest(BaselineFixBase):
    """C8 조건 8, C9: cases가 없는 바탕 검사 기록(지금 판 이전 hb가 만든 기록)."""

    def without_cases(self, **changes):
        self.baseline()
        self.edit_base_record(drop=("cases",), **changes)
        return self.original()

    def test_reads_report_and_accepts(self):
        orig = self.without_cases()
        self.assertNotIn("cases", self.record(orig["rel"]))
        self.fix()
        out = self.assert_ok(*self.setup_fix())
        self.assertEqual(out["fixed"], [FREE])
        self.assertEqual(out["changed"], [BIG_DATA])
        self.assert_original_kept(orig)

    def test_reads_report_and_stops_by_field(self):
        orig = self.without_cases()
        self.commit("준비 데이터 고침", {BIG_DATA: BIG_FIXED, ORDER_FILE: ORDER_TEST_EXTRA})
        out = self.assert_stops(self.setup_fix)
        self.assert_fields(out, added=[EXTRA])
        self.assert_original_kept(orig)

    def test_missing_report_does_not_run(self):
        orig = self.without_cases()
        os.remove(self.work_path(orig["report_rel"]))
        orig = self.original()
        self.fix()
        out = self.assert_stops(self.setup_fix, no_run=True)
        self.assert_reason(out, "보고서")
        self.assert_original_kept(orig)

    def test_unreadable_report_does_not_run(self):
        orig = self.without_cases()
        self.write(WORK_DIR + "/" + orig["report_rel"], "<testsuites><testsuite>")
        orig = self.original()
        self.fix()
        out = self.assert_stops(self.setup_fix, no_run=True)
        self.assert_reason(out, "보고서")
        self.assert_original_kept(orig)

    def test_report_and_record_total_differ_does_not_run(self):
        self.baseline()
        total = self.record(self.base_record_path())["total"]
        self.edit_base_record(drop=("cases",), total=total + 1)
        orig = self.original()
        self.fix()
        out = self.assert_stops(self.setup_fix, no_run=True)
        self.assert_reason(out, "보고서", "맞지", "다름", "다르")
        self.assert_original_kept(orig)

    def test_report_and_record_broken_differ_does_not_run(self):
        orig = self.without_cases(broken=[])
        self.assertEqual(self.state()["baseline"]["broken"], [FREE])
        self.fix()
        out = self.assert_stops(self.setup_fix, no_run=True)
        self.assert_reason(out, "보고서", "맞지", "다름", "다르")
        self.assert_original_kept(orig)


class RecordTest(BaselineFixBase):
    """C10: 인정되면 남는 것과 인정 뒤의 판정."""

    def status(self):
        out = self.git("status", "--porcelain=v1", "--untracked-files=all")
        return [line for line in out.splitlines() if not line[3:].startswith(WORK_DIR + "/checks/")]

    def test_records_setup_fix_and_diff_log_without_touching_index(self):
        self.baseline()
        orig = self.original()
        self.commit("계획", {WORK_DIR + "/plan.md": "# 계획\n"})  # 바탕 검사 뒤 작업 폴더 안 커밋
        self.fix(**{"tests/data/currency.json": CURRENCY})
        # 사용자가 작업 폴더 안에 올려 둔 것과 git에 없는 파일이 있는 상태
        self.write(WORK_DIR + "/INDEX.md", "# 작업\n")
        self.git("add", "--", WORK_DIR + "/INDEX.md")
        self.write(WORK_DIR + "/notes.md", "메모\n")
        cached, status = self.git("diff", "--cached"), self.status()
        self.assertIn("INDEX.md", cached)
        out = self.assert_ok(*self.setup_fix())
        self.assertEqual(self.git("diff", "--cached"), cached, "사용자의 인덱스가 바뀜")
        self.assertEqual(self.status(), status, "작업 트리가 바뀜")

        changed = sorted([BIG_DATA, "tests/data/currency.json"])
        self.assertEqual(out["changed"], changed)
        fix = self.state()["baseline"]["setup_fix"]
        self.assertEqual(fix["record"], out["record"])
        self.assertEqual(fix["head"], self.head())
        self.assertEqual(fix["files"], {p: self.git("rev-parse", "HEAD:" + p).strip() for p in changed})
        self.assertEqual(fix["fixed"], [FREE])
        self.assertEqual(fix["diff"], DIFF_LOG)
        self.assertIsInstance(fix["at"], str)
        self.assertTrue(fix["at"])
        self.assert_original_kept(orig)

        diff = self.read_bytes(DIFF_LOG).decode("utf-8")
        lines = diff.splitlines()
        self.assertIn("-" + BIG_BROKEN.strip(), lines)
        self.assertIn("+" + BIG_FIXED.strip(), lines)
        self.assertIn("+" + CURRENCY.strip(), lines)
        self.assertEqual(self.diff_files(), changed, "변경 기록에는 바뀐 파일만 있어야 함")
        self.assertNotIn(WORK_DIR, diff, "작업 폴더(바탕 검사 뒤 커밋한 plan.md 포함)는 변경 기록에 없어야 함")
        self.assertNotIn(SMALL_DATA, diff, "바뀌지 않은 파일은 변경 기록에 없어야 함")
        self.assertNotIn("app.py", diff)

    def test_green_after_fix_still_treats_fixed_test_as_known_broken(self):
        self.accepted()
        broken = list(self.state()["baseline"]["broken"])
        self.assertEqual(broken, [FREE])
        # 고친 테스트를 다시 깨뜨린 채 할 일을 진행한다
        self.write(BIG_DATA, BIG_BROKEN)
        self.write("tests/test_new.py", NEW_TEST)
        self.write("app.py", APP_DISCOUNT_STUB)
        self.assert_ok(*self.hb("check", "--work", WORK, "--task", "01", "--phase", "red"))
        self.write("app.py", APP_DISCOUNT)
        out = self.assert_ok(*self.hb("check", "--work", WORK, "--task", "01", "--phase", "green"))
        self.assertIn("원래 깨져 있던 것 1건", out["summary"])
        _, rec = self.newest_record()
        self.assertEqual(rec["broken"], [FREE], "전체 검사에서 다시 깨진 테스트가 보여야 함")
        state = self.state()
        self.assertEqual(state["baseline"]["broken"], broken)
        self.assertIn("green", state["tasks"]["01"])


class NonUtf8Test(BaselineFixBase):
    """C10: UTF-8이 아닌 준비 데이터 파일을 고쳐도 인정되고 변경 기록은 바이트 그대로 남는다."""

    def initial_files(self):
        return {**super().initial_files(), BIG_DATA: BIG_FIXED,
                "tests/test_names.py": NAMES_TEST, NAMES_DATA: NAMES_BROKEN}

    def test_latin1_setup_data_fix_is_accepted(self):
        self.baseline()
        self.assertEqual(self.state()["baseline"]["broken"], [NAMES])
        orig = self.original()
        self.commit("도시 채움", {NAMES_DATA: NAMES_FIXED})
        out = self.assert_ok(*self.setup_fix())
        self.assertEqual(out["fixed"], [NAMES])
        self.assertEqual(out["changed"], [NAMES_DATA])
        fix = self.state()["baseline"]["setup_fix"]
        self.assertEqual(fix["files"], {NAMES_DATA: self.git("rev-parse", "HEAD:" + NAMES_DATA).strip()})
        lines = self.read_bytes(DIFF_LOG).splitlines()
        self.assertIn(b"-Jos\xe9;", lines)
        self.assertIn(b"+Jos\xe9;Montr\xe9al", lines)
        self.assert_original_kept(orig)


if __name__ == "__main__":
    unittest.main()
