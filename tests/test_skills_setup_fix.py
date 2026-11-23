"""dev 문서와 README에 준비 데이터 정정(C13)이 적혀 있는지 보는 문서 내용 테스트.

tests/test_skills_preflight.py처럼 문서 전체에 낱말이 있는지만 보지 않는다. 먼저 범위를 좁힌다
(절 -> "그 밖의 규칙"의 **준비 데이터 정정** 항목 -> 할 일 갈래 / 바탕 갈래, "멈췄을 때" 표의 한 행).
그 안의 한 줄(문서의 한 문장, 목록 항목, 표의 한 행) 안에 뜻을 이루는 핵심 구절이 함께 있는지 본다.
정확한 문구는 고정하지 않고, 뜻이 같은 몇 가지 표현을 함께 받는다.
기존 규칙(테스트 정정, 세 번 제한, 멈췄을 때의 기존 줄)이 그대로인지도 본다.
문서가 아직 없을 때도 가져오기 오류가 아니라 단언 실패로 끝나도록, 찾지 못하면 빈 문자열을 돌려준다.
실행: <python> -m pytest tests/test_skills_setup_fix.py -rA
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))


def w(word):
    """영문 낱말 하나. 한글 조사가 바로 붙어도 맞도록(예: before를) 영문자 경계만 본다."""
    return r"(?<![A-Za-z_])" + re.escape(word) + r"(?![A-Za-z_])"


# 뜻이 같은 표현 묶음 (정규식)
UNCHANGED = r"그대로|바뀌지\s*않|바꾸지\s*않|달라지지\s*않"
REVERT = r"되돌"
TEST_FIX = r"테스트\s*정정"
ASK_USER = r"사용자에게\s*(묻|물|확인)"
STOP = r"멈"
NOT_ACCEPT = r"인정하지\s*않|인정\s*안\s*(함|한)|인정되지\s*않|받아들이지\s*않"


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def lines_matching(text, *patterns):
    """모든 정규식이 같은 줄 안에서 맞는 줄들을 (줄 번호, 줄) 목록으로 돌려준다."""
    found = []
    for no, line in enumerate(text.splitlines(), 1):
        if all(re.search(p, line) for p in patterns):
            found.append((no, line))
    return found


def section(text, title_re):
    """'## ' 제목이 title_re에 맞는 절 하나(제목 줄 포함, 다음 '## ' 앞까지). 없으면 ''."""
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = bool(re.search(title_re, line[3:]))
        if inside:
            out.append(line)
    return "\n".join(out)


def top_items(sec):
    """절 안의 맨 바깥 목록 항목들 [(첫 줄, 항목 전체)]. 항목은 '- '로 시작하는 줄부터,
    다음에 0열에서 시작하는 줄 앞까지(들여 쓴 하위 항목과 빈 줄 포함)다."""
    items, cur = [], None
    for line in sec.splitlines():
        if re.match(r"^[-*]\s", line):
            if cur:
                items.append(cur)
            cur = [line]
        elif cur is not None and (not line.strip() or line[0] in " \t"):
            cur.append(line)
        else:
            if cur:
                items.append(cur)
            cur = None
    if cur:
        items.append(cur)
    return [(it[0], "\n".join(it)) for it in items]


def indent(line):
    return len(line) - len(line.lstrip(" \t"))


def sub_block(text, head_re):
    """들여 쓴 하위 항목 가운데 첫 줄이 head_re에 맞는 첫 항목과 그 아래(더 깊이 들여 쓴) 줄들. 없으면 ''."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if indent(line) > 0 and re.match(r"^\s+([-*]|\d+\.)\s+(\*\*)?\s*(" + head_re + r")", line):
            out, n = [line], indent(line)
            for nxt in lines[i + 1:]:
                if nxt.strip() and indent(nxt) <= n:
                    break
                out.append(nxt)
            return "\n".join(out)
    return ""


def table_rows(sec):
    """절 안 표의 데이터 행 [(행 전체, [칸, ...])]. 머리 행과 구분 행은 뺀다."""
    rows = []
    for line in sec.splitlines():
        s = line.strip()
        if not s.startswith("|") or re.match(r"^\|[\s:|-]+\|$", s):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and cells[0] in ("`reason`의 내용",):
            continue
        rows.append((s, cells))
    return rows


TASK_BRANCH = r"할\s*일(의)?\s*갈래"
BASE_BRANCH = r"바탕(\s*검사)?(의)?\s*갈래"


class _DevDoc(unittest.TestCase):
    def setUp(self):
        self.text = read("skills/dev/SKILL.md")
        self.rules = section(self.text, r"그\s*밖의\s*규칙")
        found = [body for head, body in top_items(self.rules)
                 if re.match(r"^[-*]\s+\*\*\s*준비\s*데이터\s*정정", head)]
        self.item = found[0] if found else ""
        self.task = sub_block(self.item, TASK_BRANCH)
        self.base = sub_block(self.item, BASE_BRANCH)
        # 항목 첫머리(첫 갈래 앞까지). 할 일 갈래로 들어가는 조건은 여기에 적어도 받는다.
        intro = []
        for line in self.item.splitlines():
            if re.match(r"^\s+([-*]|\d+\.)\s+(\*\*)?\s*(" + TASK_BRANCH + "|" + BASE_BRANCH + ")", line):
                break
            intro.append(line)
        self.intro = "\n".join(intro)
        self.stops = table_rows(section(self.text, r"멈췄을\s*때"))


class DevCommandList(_DevDoc):
    def setUp(self):
        super().setUp()
        self.calls = "\n".join(l for l in section(self.text, r"프로그램\s*부르는\s*법").splitlines()
                               if re.search(r"hb\.py", l))

    def test_setup_fix_before_command(self):
        # C13: 명령 목록에 setup-fix --task <번호> --phase before [-- <인자> ...]
        hits = lines_matching(self.calls, r"--repo", r"setup-fix", r"--work", r"--task\s+<",
                              r"--phase\s+before", r"\[\s*--\s+<[^>]+>")
        self.assertTrue(hits, "프로그램 부르는 법에 'setup-fix --task <번호> --phase before [-- <인자> ...]'가 없음")

    def test_setup_fix_after_command(self):
        # C13: 명령 목록에 setup-fix --task <번호> --phase after (인자 없음)
        hits = [h for h in lines_matching(self.calls, r"--repo", r"setup-fix", r"--work", r"--task\s+<",
                                          r"--phase\s+after")
                if not re.search(r"\[\s*--\s+<", h[1])]
        self.assertTrue(hits, "프로그램 부르는 법에 'setup-fix --task <번호> --phase after'가 없음")

    def test_setup_fix_baseline_command(self):
        # C13: 명령 목록에 setup-fix --baseline (--task, --phase 없이)
        hits = [h for h in lines_matching(self.calls, r"--repo", r"setup-fix", r"--work", r"--baseline")
                if not re.search(r"--task|--phase", h[1])]
        self.assertTrue(hits, "프로그램 부르는 법에 'setup-fix --work <작업 이름> --baseline'이 없음")

    def test_existing_commands_kept(self):
        # 기존 명령 줄은 그대로 있다
        for pats in ([w("preflight"), r"--work"], [w("baseline"), r"--work"],
                     [w("check"), r"--phase\s+red"], [w("check"), r"--phase\s+green"], [w("done"), r"--task"]):
            self.assertTrue(lines_matching(self.calls, *pats), "기존 명령 줄이 없어짐: %r" % (pats,))


class DevSetupFixItem(_DevDoc):
    def test_item_next_to_test_correction(self):
        # C13: "그 밖의 규칙"의 "테스트 정정" 바로 옆(앞이나 뒤)에 **준비 데이터 정정** 항목이 있다
        heads = [head for head, _ in top_items(self.rules)]
        fix = [i for i, h in enumerate(heads) if re.match(r"^[-*]\s+\*\*\s*준비\s*데이터\s*정정", h)]
        corr = [i for i, h in enumerate(heads) if re.match(r"^[-*]\s+\*\*\s*테스트\s*정정", h)]
        self.assertTrue(fix, "그 밖의 규칙에 **준비 데이터 정정** 항목이 없음")
        self.assertTrue(corr, "그 밖의 규칙에 **테스트 정정** 항목이 없음")
        self.assertIn(abs(fix[0] - corr[0]), (1,), "준비 데이터 정정 항목이 테스트 정정 바로 옆에 있지 않음")

    def test_item_has_two_branches(self):
        # C13: 할 일 갈래와 바탕 갈래 두 하위 항목이 있다
        self.assertTrue(self.task.strip(), "준비 데이터 정정 항목에 '할 일 갈래' 하위 항목이 없음")
        self.assertTrue(self.base.strip(), "준비 데이터 정정 항목에 '바탕 갈래' 하위 항목이 없음")


class DevTaskBranch(_DevDoc):
    def test_condition_implementer_stops_and_reports(self):
        # C13 조건: 준비 데이터 때문이라는 근거가 나오면 구현자는 멈추고 보고한다
        scope = self.intro + "\n" + self.task
        hits = lines_matching(scope, r"근거", r"구현자", STOP, r"보고")
        self.assertTrue(hits, "할 일 갈래에 '근거가 나오면 구현자는 멈추고 보고한다'가 없음")

    def test_condition_leader_decides_branch(self):
        # C13 조건: 완료 기준 문장, 기대값, 검사 조건이 그대로일 것으로 보이면 이 갈래, 아니면 테스트 정정
        scope = self.intro + "\n" + self.task
        hits = lines_matching(scope, r"지휘", r"완료\s*기준\s*문장", r"기대값", r"검사\s*조건", UNCHANGED, TEST_FIX)
        self.assertTrue(hits, "할 일 갈래에 '완료 기준 문장·기대값·검사 조건이 그대로면 이 갈래, 아니면 테스트 정정'이 없음")

    def _steps(self):
        steps = [
            # 1. before를 돌린다. 구현은 빼 두지 않는다
            [w("before"), r"빼\s*두지\s*않|빼지\s*않"],
            # 2. 구현자에게 준비 데이터만 고치고 멈추게, 기대값·검사 조건·구현은 바꾸지 않게
            [r"구현자", r"준비\s*데이터만", r"고치", STOP, r"기대값", r"검사\s*조건", r"구현(은|을|도)?", r"바꾸지\s*않"],
            # 3. after. ok가 아니면 구현자의 변경을 되돌리고 테스트 정정으로
            [w("after"), w("ok"), r"아니면|않으면|못하면", REVERT, TEST_FIX],
            # 4. 검토자를 새로 불러 diff 기록을 주고, 세 명령의 출력을 견준다
            [r"검토자", r"새로", r"diff|변경\s*기록", r"세\s*명령"],
            # 5. "꼭 고칠 것"이 없으면 원래 하던 단계로
            [r"꼭\s*고칠\s*것", r"없으면", r"원래|하던", r"단계|통과\s*확인"],
        ]
        lines = self.task.splitlines()
        found = []
        for pats in steps:
            idx = [i for i, l in enumerate(lines) if all(re.search(p, l) for p in pats)]
            found.append(idx[0] if idx else None)
        return found

    def test_steps_present(self):
        # C13 순서 1–5가 할 일 갈래 안에 있다
        names = ["1 before, 구현을 빼 두지 않음", "2 구현자에게 준비 데이터만 고치고 멈춤(기대값·검사 조건·구현은 그대로)",
                 "3 after, ok가 아니면 되돌리고 테스트 정정", "4 검토자를 새로 불러 diff 기록, 세 명령 비교",
                 "5 꼭 고칠 것이 없으면 원래 단계로"]
        missing = [n for n, i in zip(names, self._steps()) if i is None]
        self.assertFalse(missing, "할 일 갈래에 없는 순서: %s" % missing)

    def test_steps_in_order(self):
        # C13 순서: 1 → 2 → 3 → 4 → 5
        found = self._steps()
        self.assertNotIn(None, found, "할 일 갈래의 순서 1–5 가운데 빠진 것이 있음")
        self.assertEqual(found, sorted(found), "할 일 갈래의 순서 1–5가 차례대로가 아님")
        self.assertEqual(len(set(found)), 5, "할 일 갈래의 순서 1–5가 서로 다른 줄이 아님")

    def test_reviewer_checks_three(self):
        # C13: 검토자가 보는 셋(기대값 그대로, 검사 조건 그대로, 바뀐 것이 준비 데이터뿐)
        # 할 일 갈래 머리 줄보다 깊이 들여 쓴, "검토자"가 나오는 줄과 그 아래 더 들여 쓴 줄들을 한 덩어리로 보고,
        # 셋이 각각 그 안의 한 줄에 있는지 본다. 구현자에게 주는 지시(순서 2)나 갈래 조건(완료 기준 문장)의 줄은 세지 않는다.
        lines = self.task.splitlines()
        head_n = indent(lines[0]) if lines else 0
        skip = r"구현자에게|완료\s*기준\s*문장"
        ok = False
        for i, line in enumerate(lines):
            if i == 0 or indent(line) <= head_n or not re.search(r"검토자", line):
                continue
            block, n = [line], indent(line)
            for nxt in lines[i + 1:]:
                if nxt.strip() and indent(nxt) <= n:
                    break
                block.append(nxt)
            block = "\n".join(l for l in block if not re.search(skip, l))
            if (lines_matching(block, r"기대값", UNCHANGED) and lines_matching(block, r"검사\s*조건", UNCHANGED)
                    and lines_matching(block, r"준비\s*데이터\s*(뿐|만)")):
                ok = True
                break
        self.assertTrue(ok, "할 일 갈래의 검토자 덩어리에 셋(기대값 그대로, 검사 조건 그대로, 준비 데이터뿐)이 함께 없음")

    def test_path_alone_not_accepted(self):
        # C13: 파일 이름이나 경로만으로 준비 데이터라고 인정하지 않는다
        hits = lines_matching(self.task, r"파일\s*이름|경로", r"만으로", r"준비\s*데이터", NOT_ACCEPT)
        self.assertTrue(hits, "할 일 갈래에 '파일 이름이나 경로만으로 준비 데이터라고 인정하지 않는다'가 없음")

    def test_limit_two_with_test_correction(self):
        # C13 한도: 테스트 정정과 합쳐 할 일 하나에 두 번
        hits = lines_matching(self.task, TEST_FIX, r"합쳐|합해|합하여|더해|함께", r"할\s*일\s*하나", r"두\s*번")
        self.assertTrue(hits, "할 일 갈래에 '테스트 정정과 합쳐 할 일 하나에 두 번'이 없음")

    def test_record(self):
        # C13 기록: INDEX.md에 이유 한 줄, before·after의 summary, 바뀐 파일 목록, 검토 결과
        hits = lines_matching(self.task, r"INDEX\.md", r"이유", w("before"), w("after"), w("summary"),
                              r"바뀐\s*파일", r"검토\s*결과")
        self.assertTrue(hits, "할 일 갈래에 INDEX.md 기록(이유, before·after summary, 바뀐 파일, 검토 결과)이 없음")

    def test_no_human_approval(self):
        # C13: 완료 기준 문장이 그대로이므로 사람 승인은 받지 않는다
        hits = lines_matching(self.task, r"사람\s*승인", r"받지\s*않|없이", r"완료\s*기준\s*문장", UNCHANGED)
        self.assertTrue(hits, "할 일 갈래에 '완료 기준 문장이 그대로이므로 사람 승인은 받지 않는다'가 없음")

    def test_out_of_scope_asks_user(self):
        # C13: 고친 파일이 바꿔도 되는 파일 밖이면 통과 확인이 멈추고, 범위를 고칠지 사용자에게 묻는다
        hits = lines_matching(self.task, r"바꿔도\s*되는\s*파일\s*밖|범위\s*밖|allowed_files", r"통과\s*확인", STOP,
                              r"범위", ASK_USER)
        self.assertTrue(hits, "할 일 갈래에 '바꿔도 되는 파일 밖이면 통과 확인이 멈추고 범위를 사용자에게 묻는다'가 없음")

    def test_new_red_leaves_unfinished_fix_as_record(self):
        # C13: 끝나지 않은 before가 남은 채 실패 확인을 새로 받으면 앞 정정은 기록으로만 남는다
        hits = lines_matching(self.task, r"끝나지\s*않은", w("before"), r"실패\s*확인", r"새로",
                              r"기록(으로)?만")
        self.assertTrue(hits, "할 일 갈래에 '끝나지 않은 before가 남은 채 실패 확인을 새로 받으면 앞 정정은 기록으로만'이 없음")


class DevBaselineBranch(_DevDoc):
    def test_condition(self):
        # C13 조건: 바탕 검사에서 원래 깨져 있던 것이 준비 데이터 때문이라는 근거, 아직 할 일 기록이 없음
        hits = lines_matching(self.base, r"바탕\s*검사", r"원래\s*깨져\s*있던", r"준비\s*데이터", r"근거",
                              r"할\s*일\s*기록", r"없")
        self.assertTrue(hits, "바탕 갈래에 조건(원래 깨져 있던 것이 준비 데이터 때문이라는 근거, 할 일 기록 없음)이 없음")

    def test_commit_then_baseline_command(self):
        # C13: 준비 데이터만 고쳐 커밋한 뒤 setup-fix --baseline
        hits = lines_matching(self.base, r"준비\s*데이터만", r"커밋", r"뒤|다음", r"setup-fix\s+(--work\s+<[^>]+>\s+)?--baseline")
        self.assertTrue(hits, "바탕 갈래에 '준비 데이터만 고쳐 커밋한 뒤 setup-fix --baseline'이 없음")

    def test_before_is_baseline_record_and_same_args(self):
        # C13: 원래 바탕 검사 기록이 '고치기 전'이고, 같은 인자로 전체 검사를 다시 돌린다
        self.assertTrue(lines_matching(self.base, r"바탕\s*검사\s*기록", r"고치기\s*전"),
                        "바탕 갈래에 '원래 바탕 검사 기록이 고치기 전'이 없음")
        self.assertTrue(lines_matching(self.base, r"같은\s*인자", r"전체\s*검사", r"다시"),
                        "바탕 갈래에 '같은 인자로 전체 검사를 다시 돌린다'가 없음")

    def test_once_per_work(self):
        # C13 한도: 작업에 한 번
        hits = lines_matching(self.base, r"작업(에|마다|\s*하나에)\s*한\s*번")
        self.assertTrue(hits, "바탕 갈래에 '작업에 한 번'이 없음")

    def test_review_with_diff_log(self):
        # C13: 인정되면 검토자를 새로 불러 logs/baseline-setup-fix.diff.log를 주고 할 일 갈래와 같은 셋을 본다
        hits = lines_matching(self.base, r"검토자", r"새로", r"baseline-setup-fix\.diff\.log",
                              r"같은\s*셋|할\s*일\s*갈래와\s*같|기대값")
        self.assertTrue(hits, "바탕 갈래에 '검토자를 새로 불러 baseline-setup-fix.diff.log로 같은 셋을 본다'가 없음")

    def test_must_fix_means_not_accepted(self):
        # C13: "꼭 고칠 것"이 나오면 인정하지 않은 것으로 보고 INDEX.md에 적는다
        # 그때 준비 데이터 변경을 되돌린다(spec.md 54줄)
        hits = lines_matching(self.base, r"꼭\s*고칠\s*것", NOT_ACCEPT, REVERT, r"INDEX\.md")
        self.assertTrue(hits, "바탕 갈래에 '꼭 고칠 것이 나오면 인정하지 않은 것으로 보고, 준비 데이터 변경을 되돌리며, "
                              "INDEX.md에 적는다'가 없음")

    def test_verdicts_unchanged(self):
        # C13: 인정돼도 통과 확인과 검수의 판정은 그대로다
        self.assertTrue(lines_matching(self.base, r"통과\s*확인", r"검수", r"판정", UNCHANGED),
                        "바탕 갈래에 '인정돼도 통과 확인과 검수의 판정은 그대로'가 없음")
        self.assertTrue(lines_matching(self.base, r"원래\s*깨져\s*있던\s*것", r"바탕\s*검사", UNCHANGED),
                        "바탕 갈래에 '원래 깨져 있던 것은 바탕 검사 그대로'가 없음")
        self.assertTrue(lines_matching(self.base, r"바꿔도\s*되는\s*파일", r"검수", STOP),
                        "바탕 갈래에 '고친 파일이 바꿔도 되는 파일에 없으면 검수는 멈춘다'가 없음")

    def test_record(self):
        # C13 기록: 할 일 갈래와 같다 (또는 같은 항목을 직접 적음)
        same = lines_matching(self.base, r"기록", r"할\s*일\s*갈래와\s*같")
        direct = lines_matching(self.base, r"INDEX\.md", w("summary"), r"바뀐\s*파일", r"검토\s*결과")
        self.assertTrue(same or direct, "바탕 갈래에 기록(할 일 갈래와 같음)이 없음")


class DevStopTable(_DevDoc):
    def rows(self, reason_pats, action_pats=()):
        """'멈췄을 때' 표에서 이유 칸이 reason_pats에 모두 맞고, 행 나머지가 action_pats에 모두 맞는 행."""
        hits = []
        for row, cells in self.stops:
            reason, rest = cells[0], " | ".join(cells[1:])
            if all(re.search(p, reason) for p in reason_pats) and all(re.search(p, rest) for p in action_pats):
                hits.append(row)
        return hits

    def test_commit_after_before_or_baseline(self):
        # C13: 실패 확인 뒤(또는 before 뒤) 커밋, 바탕 검사 커밋이 지금 커밋의 조상이 아님
        self.assertTrue(self.rows([w("before"), r"커밋"]), "멈췄을 때 표에 'before 뒤 커밋' 행이 없음")
        self.assertTrue(self.rows([r"바탕\s*검사", r"조상"]),
                        "멈췄을 때 표에 '바탕 검사 커밋이 지금 커밋의 조상이 아님' 행이 없음")

    def test_tests_already_changed(self):
        # C13: 테스트 쪽 파일이 이미 바뀜 -> 테스트 정정
        self.assertTrue(self.rows([r"테스트\s*쪽", r"이미\s*바뀌|이미\s*바뀜"], [TEST_FIX]),
                        "멈췄을 때 표에 '테스트 쪽이 이미 바뀜 -> 테스트 정정' 행이 없음")

    def test_unfinished_before(self):
        # C13: 끝나지 않은 before -> after를 끝내거나, 되돌린 뒤 테스트 정정으로 실패 확인을 새로. 되돌리기만으로는 안 풀림
        self.assertTrue(self.rows([r"끝나지\s*않은", w("before")],
                                  [w("after"), REVERT, TEST_FIX, r"실패\s*확인", r"새로"]),
                        "멈췄을 때 표에 '끝나지 않은 before -> after 또는 되돌리고 테스트 정정으로 실패 확인을 새로' 행이 없음")
        self.assertTrue(self.rows([r"끝나지\s*않은", w("before")],
                                  [r"되돌리기만으로|되돌리는\s*것만으로|되돌려도", r"풀리지\s*않|안\s*풀|남"]),
                        "멈췄을 때 표의 '끝나지 않은 before' 행에 '되돌리기만으로는 풀리지 않는다'가 없음")

    def test_nothing_to_fix(self):
        # C13: 바로잡을 실패가 없음
        self.assertTrue(self.rows([r"바로잡을\s*실패"]), "멈췄을 때 표에 '바로잡을 실패가 없음' 행이 없음")

    def test_import_or_syntax_error(self):
        # C13: 가져오기·문법 오류
        self.assertTrue(self.rows([r"가져오기", r"문법"]), "멈췄을 때 표에 '가져오기·문법 오류' 행이 없음")

    def test_outside_test_globs(self):
        # C13: test_globs 밖이 바뀜
        self.assertTrue(self.rows([r"test_globs", r"밖"]), "멈췄을 때 표에 'test_globs 밖이 바뀜' 행이 없음")

    def test_tests_not_changed(self):
        # C13: 테스트 쪽이 안 바뀜
        pat = (r"바뀐\s*테스트\s*쪽\s*파일이?\s*(하나도\s*)?없|"
               r"테스트\s*쪽(\s*파일)?(이|은)?\s*(하나도\s*)?(안\s*바뀜|안\s*바뀌|바뀌지\s*않)")
        self.assertTrue(self.rows([pat]), "멈췄을 때 표에 '테스트 쪽이 안 바뀜' 행이 없음")

    def test_not_accepted_reverts_and_test_correction(self):
        # C13: 이름 목록이 다름 / 아직 실패 / 나빠짐 -> 변경을 되돌리고 테스트 정정
        # 이유 칸은 프로그램의 reason 문구("…인정하지 않음 (…실패가 남았거나…)")로 찾을 수 있어야 한다
        for name, pat in (("이름 목록이 다름", r"(이름|테스트)\s*목록[^|]*(다름|다르)"),
                          ("아직 실패", r"실패가\s*남|통과하지\s*않|아직\s*실패|still_failing"),
                          ("나빠짐", r"나빠짐|나빠진|나빠졌")):
            self.assertTrue(self.rows([pat, r"인정하지\s*않"], [REVERT, TEST_FIX]),
                            "멈췄을 때 표에 '인정하지 않음(%s) -> 되돌리고 테스트 정정' 행이 없음" % name)

    def test_baseline_branch_conditions(self):
        # C13: 바탕 갈래의 조건(할 일 기록 있음, 이미 정정함, 커밋되지 않은 변경, 보고서를 읽을 수 없음)
        self.assertTrue(self.rows([r"할\s*일\s*기록"]), "멈췄을 때 표에 '할 일 기록이 있음' 행이 없음")
        # '이미 정정함'은 bin/hb.py의 "바탕 검사의 준비 데이터 정정을 이미 인정받았음 (한 작업에 한 번)" 행이다.
        # "테스트 쪽 파일이 이미 바뀌어 있음 … 테스트 정정", "할 일 기록이 이미 있음. 바탕 검사의 정정은 …" 행으로는 맞지 않게 한다.
        already = [r for r, cells in self.stops
                   if re.search(r"이미\s*(인정|정정)|정정을\s*이미|한\s*작업에\s*한\s*번", cells[0])
                   and not re.search(r"테스트\s*쪽|할\s*일\s*기록", cells[0])]
        self.assertTrue(already, "멈췄을 때 표에 '이미 정정함(한 작업에 한 번)' 행이 없음")
        commit = [r for r in self.rows([r"커밋되지\s*않은"])
                  if re.search(r"작업\s*폴더\s*밖|바탕|--baseline|setup-fix|커밋한\s*뒤|커밋하고", r)]
        self.assertTrue(commit, "멈췄을 때 표에 바탕 갈래의 '커밋되지 않은 변경' 행이 없음")
        self.assertTrue(self.rows([r"보고서", r"읽을\s*수\s*없|없음|없다"]),
                        "멈췄을 때 표에 '보고서를 읽을 수 없음' 행이 없음")

    def test_existing_rows_kept(self):
        # 기존 줄은 그대로: 이유 칸 그대로, 할 일 칸의 핵심 구절 그대로
        existing = [
            ("커밋되지 않은 변경이 있음", r"건드리지\s*않고\s*사용자에게\s*알린다"),
            ("시작 전 검증에서 막힘", r"검사를\s*시작하지\s*않는다"),
            ("준비 단계 오류, 전부 건너뜀, 실패한 테스트가 없음", r"구현자가\s*테스트를\s*고친다.*세\s*번\s*제한에\s*셈"),
            ("테스트가 바뀜", r"테스트를\s*되돌리거나.*테스트\s*정정.*1번부터\s*다시"),
            ("새로 깨진 테스트가 있음", r"구현을\s*고친다.*테스트를\s*약하게\s*고치지\s*않는다"),
            ("바꿔도 되는 파일 밖을 고침", r"되돌리게\s*하거나.*범위를\s*고칠지\s*사용자에게\s*묻는다"),
            ("실패 확인 뒤에 커밋이 생김", r"멈추고\s*사용자에게\s*알린다"),
            ("통과 확인 뒤에 코드가 바뀜", r"5번부터\s*다시\s*한다"),
        ]
        for reason, action in existing:
            hits = [row for row, cells in self.stops
                    if cells[0] == reason and re.search(action, " | ".join(cells[1:]))]
            self.assertTrue(hits, "멈췄을 때 표의 기존 줄이 바뀜: %s" % reason)


# 이번 작업 전 skills/dev/SKILL.md "그 밖의 규칙"의 기존 문장(글자 그대로). 바뀌면 안 된다.
TEST_CORRECTION_ITEM = "\n".join([
    "- **테스트 정정.** 구현 중에 테스트가 틀렸다는 근거가 나오면 구현자는 멈추고 보고한다. 지휘가 근거를 읽고 판단한다. "
    "완료 기준 문장이 그대로면 사람 승인 없이 하고, 이유를 `INDEX.md`에 한 줄 적는다. 완료 기준 문장이 바뀌어야 하면 "
    "지금처럼 이유와 수정안을 사용자에게 보여 주고, 승인받으면 `INDEX.md`에 적는다. 그런 다음 아래 순서로 한다. "
    "할 일 하나에 두 번까지다.",
    "  1. 지휘가 이 할 일의 구현 변경을 `<작업 폴더>/logs/NN-impl-<번호>.log`로 빼 둔다(`git diff HEAD -- <구현 파일> > …`. "
    "새 파일은 거기에 나오지 않으니 그 내용을 같은 로그 끝에 붙인다. `<번호>`는 이 할 일의 몇 번째 정정인지다). "
    "지금 테스트 파일도 `<작업 폴더>/logs/NN-test-before-<번호>.log`로 복사해 둔다.",
    "  2. 구현 파일만 마지막 커밋 상태로 되돌리고(`git checkout HEAD -- <구현 파일>`), 새로 만든 구현 파일은 지운다. "
    "테스트 파일은 그대로 둔다(고칠 대상이다).",
    "  3. 1번(테스트 쓰기)부터 다시 한다. 1~3번의 구현자와 검토자에게는 빼 둔 구현 로그의 경로를 주지 않는다. "
    "3번 검토자에게는 정정 전 테스트 사본의 경로와 `INDEX.md`의 이유 한 줄을 함께 준다.",
    "  4. 새 실패 확인과 새 테스트 읽기를 통과하면, 4번 구현자에게 빼 둔 구현 로그의 경로를 줄 수 있다.",
])
THREE_TIMES_LINE = ("- **세 번 제한.** 테스트를 고쳐 다시 받는 것(2번과 3번)은 할 일 하나에 합쳐 세 번까지, "
                    "지적 반영(7번)도 따로 세 번까지다. 지휘가 `INDEX.md`에 세어 적는다. 넘으면 멈추고 사용자에게 알린다.")


class DevExistingRules(_DevDoc):
    def test_test_correction_rule_kept(self):
        # 기존 "테스트 정정" 항목 전체(본문 줄과 하위 1–4)가 글자 그대로이고, 그 항목에 다른 줄이 끼지 않았다
        self.assertIn(TEST_CORRECTION_ITEM, self.rules, "테스트 정정 항목의 문장이 기존과 글자 그대로가 아님")
        items = [body for head, body in top_items(self.rules) if re.match(r"^[-*]\s+\*\*\s*테스트\s*정정", head)]
        self.assertTrue(items, "그 밖의 규칙에 **테스트 정정** 항목이 없음")
        self.assertEqual(items[0].rstrip(), TEST_CORRECTION_ITEM, "테스트 정정 항목에 기존에 없던 줄이 더해지거나 바뀜")

    def test_three_times_rule_kept(self):
        # 기존 "세 번 제한" 항목 전체가 글자 그대로다(한 줄 전체가 같고, 그 항목에 다른 줄이 끼지 않았다)
        self.assertIn(THREE_TIMES_LINE, self.rules.splitlines(), "세 번 제한 줄이 기존과 글자 그대로가 아님")
        items = [body for head, body in top_items(self.rules) if re.match(r"^[-*]\s+\*\*\s*세\s*번\s*제한", head)]
        self.assertTrue(items, "그 밖의 규칙에 **세 번 제한** 항목이 없음")
        self.assertEqual(items[0].rstrip(), THREE_TIMES_LINE, "세 번 제한 항목에 기존에 없던 줄이 더해지거나 바뀜")


class ReadmeSetupFix(unittest.TestCase):
    def setUp(self):
        self.text = read("README.md")

    def test_usage_has_setup_fix_line(self):
        # C13: "쓰는 법"의 개발 설명에 준비 데이터 정정 한 줄(무엇인지, 두 갈래, 판정 기준은 그대로)
        usage = section(self.text, r"쓰는\s*법")
        hits = lines_matching(usage, r"준비\s*데이터", r"setup-fix|정정",
                              r"setup-fix|고치기\s*전|고친\s*뒤|다시\s*돌려|같은\s*(명령|인자)",
                              r"할\s*일", r"바탕\s*검사", r"판정.*(그대로|바뀌지\s*않)")
        self.assertTrue(hits, "README 쓰는 법에 준비 데이터 정정(무엇인지, 할 일·바탕 두 갈래, 판정 그대로) 한 줄이 없음")

    def test_file_list_has_new_tests(self):
        # C13: "들어 있는 것" 목록에 이번 작업의 테스트 파일들
        listing = section(self.text, r"들어\s*있는\s*것")
        for name in ("tests/test_hb_red_history.py", "tests/test_hb_setup_fix.py", "tests/test_hb_setup_fix_jest.py",
                     "tests/test_hb_setup_fix_baseline.py", "tests/test_hb_setup_fix_baseline_jest.py",
                     "tests/test_skills_setup_fix.py"):
            hits = lines_matching(listing, r"^\s*" + re.escape(name) + r"\s+\S")
            self.assertTrue(hits, "README 들어 있는 것 목록에 %s(와 설명)가 없음" % name)

    def test_file_list_existing_entries_kept(self):
        # 기존 목록은 그대로 있다
        listing = section(self.text, r"들어\s*있는\s*것")
        for name in ("skills/dev/SKILL.md", "bin/hb.py", "tests/test_hb.py", "tests/test_hb_preflight.py",
                     "tests/test_skills_preflight.py"):
            self.assertTrue(lines_matching(listing, r"^\s*" + re.escape(name) + r"\s+\S"),
                            "README 들어 있는 것 목록에서 %s가 없어짐" % name)


if __name__ == "__main__":
    unittest.main()
