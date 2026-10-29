"""skills 문서와 README에 preflight 연계(C9)가 적혀 있는지 보는 문서 내용 테스트.

문서 전체에 낱말이 있는지만 보지 않고, 한 줄(문서의 한 문장, 목록 항목, 표의 한 행) 안에
핵심 낱말이 함께 있는지를 본다. 정확한 문구는 고정하지 않고, 뜻이 같은 몇 가지 표현을 함께 받는다.
기존 규칙(예: dev의 "권장"은 진행표에 적고 넘어간다)만으로 통과하지 않도록 preflight 연계와 묶어 본다.
실행: <python> -m pytest tests/test_skills_preflight.py -rA
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))


def w(word):
    """영문 낱말 하나. 한글 조사가 바로 붙어도 맞도록(예: preflight를) 영문자 경계만 본다."""
    return r"(?<![A-Za-z_])" + re.escape(word) + r"(?![A-Za-z_])"


# 뜻이 같은 표현 묶음 (정규식)
NOT_START = r"시작하지\s*않|시작\s*안\s*(한|함)|돌리지\s*않|실행하지\s*않|부르지\s*않|넘어가지\s*않"
SEPARATE = r"따로|나눠|나누어|섞지\s*않|합치지\s*않|구분"
NOT_PROMOTE = (r"올리지\s*않|승격(하지|시키지)\s*않|격상하지\s*않|바꾸지\s*않|"
               r"(로|으로)\s*(보지|치지|다루지|취급하지)\s*않")
NOT_PASS = r"통과(로|가|라고)?\s*(읽지|보지|치지|판정하지|여기지|적지|쓰지)?\s*않|통과가\s*아니|통과\s*아님"


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


def sections(text):
    """'## ' 제목으로 나눈 절들의 목록. 첫 제목 앞 부분도 한 절로 친다."""
    parts, cur = [], []
    for line in text.splitlines():
        if line.startswith("## ") and cur:
            parts.append("\n".join(cur))
            cur = []
        cur.append(line)
    if cur:
        parts.append("\n".join(cur))
    return parts


class DevSkillPreflight(unittest.TestCase):
    def setUp(self):
        self.text = read("skills/dev/SKILL.md")

    def test_dev_runs_preflight_before_baseline(self):
        # C9: baseline 전에 preflight를 돌린다
        hits = lines_matching(self.text, w("preflight"), w("baseline") + r"|바탕\s*검사", r"전에|먼저|앞서")
        self.assertTrue(hits, "dev 문서에 'baseline 전에 preflight'를 적은 줄이 없음")

    def test_dev_runs_preflight_before_each_check(self):
        # C9: 각 check 전에 preflight를 돌린다
        hits = lines_matching(self.text, w("preflight"), w("check") + r"|실패\s*확인|통과\s*확인", r"전에|먼저|앞서")
        self.assertTrue(hits, "dev 문서에 'check 전에 preflight'를 적은 줄이 없음")

    def test_dev_preflight_command_documented(self):
        # C9: dev가 preflight를 돌리려면 부르는 법이 있어야 한다 (hb.py preflight --work)
        hits = lines_matching(self.text, r"hb\.py", w("preflight"), r"--work")
        self.assertTrue(hits, "dev 문서의 프로그램 부르는 법에 preflight 명령이 없음")

    def test_dev_preflight_stop_does_not_start_check(self):
        # C9: preflight가 stop이면 검사를 시작하지 않는다
        # stop이 조건이어야 한다: 같은 줄에서 stop 뒤에 조건 표현(이면/면/일 때/이 나오면 등)이 오고,
        # 그 뒤에 '시작하지 않는다'류가 나와야 한다. ("검사를 돌리지 않고 ok 또는 stop을 낸다" 같은 소개 줄은 맞지 않는다.)
        stop_then_not_start = (w("stop") + r"[`'\"]?\s*"
                               r"(이면|면|이라면|라면|일\s*때|인\s*경우|(이|가|을|를)\s*(나오|내|돌려주|받)\S*?면)"
                               r".*?(" + NOT_START + r")")
        hits = lines_matching(self.text, w("preflight"), stop_then_not_start)
        self.assertTrue(hits, "dev 문서에 'preflight가 stop이면 검사를 시작하지 않는다'를 적은 줄이 없음")

    def test_dev_reports_three_outcomes_separately(self):
        # C9: product / environment / aux 세 칸을 따로 보고한다
        hits = lines_matching(self.text, w("product"), w("environment"), w("aux"), SEPARATE)
        self.assertTrue(hits, "dev 문서에 product, environment, aux를 한 줄에서 따로 보고한다고 적은 곳이 없음")

    def test_dev_does_not_promote_recommendation_with_preflight(self):
        # C9: "권장" 지적을 필수로 올리지 않는다 (preflight 연계가 있는 절 안에서)
        # 기존 줄('"권장"은 진행표에 적고 넘어간다')은 '올리지 않는다'류의 표현이 없어 여기서 맞지 않는다.
        hits = []
        for sec in sections(self.text):
            if not re.search(w("preflight"), sec):
                continue
            hits += lines_matching(sec, r"권장", r"필수|꼭\s*고칠", NOT_PROMOTE)
        self.assertTrue(hits, "dev 문서의 preflight 연계 절에 '권장을 필수로 올리지 않는다'를 적은 줄이 없음")

    def test_dev_aux_out_of_scope_stops_and_reports_path_change(self):
        # C9: 보조검증이 할 일 범위 밖이면 멈추고 경로 변경을 보고한다
        hits = lines_matching(self.text, w("aux") + r"|보조\s*검증",
                              r"범위\s*밖|allowed_files|바꿔도\s*되는\s*파일\s*밖|" + w("scope"),
                              r"멈|" + w("stop") + r"|중단", r"경로\s*변경")
        self.assertTrue(hits, "dev 문서에 '보조검증이 범위 밖이면 멈추고 경로 변경을 보고'를 적은 줄이 없음")

    def test_dev_existing_rules_not_weakened(self):
        # 기존 문장의 규칙을 완화하지 않는다: 진행을 막는 지적은 "꼭 고칠 것"뿐, not_run/timeout은 통과가 아님
        self.assertTrue(lines_matching(self.text, r"진행을\s*막는\s*지적", r"꼭\s*고칠\s*것"))
        self.assertTrue(lines_matching(self.text, r"`not_run`", r"통과가\s*아니"))
        self.assertTrue(lines_matching(self.text, r"`timeout`", r"통과가\s*아니"))


class PlanSkillPreflight(unittest.TestCase):
    def setUp(self):
        self.text = read("skills/plan/SKILL.md")

    def test_plan_checks_environment_with_preflight(self):
        # C9: 계획 끝에 preflight로 환경을 확인한다
        hits = lines_matching(self.text, w("preflight"), r"환경")
        self.assertTrue(hits, "plan 문서에 preflight로 환경을 확인한다고 적은 줄이 없음")

    def test_plan_preflight_comes_after_step_9(self):
        # C9: 계획 끝(9번 작업 브랜치와 첫 커밋 뒤)
        lines = self.text.splitlines()
        step9 = [i for i, l in enumerate(lines) if re.match(r"\s*9\.\s", l)]
        self.assertTrue(step9, "plan 문서에 9번 단계가 없음")
        pre = [i for i, l in enumerate(lines) if re.search(w("preflight"), l) and "환경" in l]
        self.assertTrue(pre, "plan 문서에 preflight로 환경을 확인한다고 적은 줄이 없음")
        self.assertTrue(any(i > step9[0] for i in pre), "plan 문서의 preflight 환경 확인이 9번 뒤에 없음")


class _ReadsOnlyProduct:
    PATH = None

    def setUp(self):
        self.text = read(self.PATH)

    def test_product_only_is_completion_evidence(self):
        # C9: preflight의 product만 완료 증거로 읽는다
        hits = lines_matching(self.text, w("product"), r"증거")
        self.assertTrue(hits, self.PATH + "에 'product만 완료 증거'를 적은 줄이 없음")

    def test_aux_incomplete_is_not_pass(self):
        # C9: aux: incomplete를 통과로 읽지 않는다
        hits = lines_matching(self.text, w("aux"), w("incomplete"), NOT_PASS)
        self.assertTrue(hits, self.PATH + "에 'aux: incomplete는 통과가 아니다'를 적은 줄이 없음")

    def test_environment_blocked_is_not_pass(self):
        # C9: environment: blocked를 통과로 읽지 않는다
        hits = lines_matching(self.text, w("environment"), w("blocked"), NOT_PASS)
        self.assertTrue(hits, self.PATH + "에 'environment: blocked는 통과가 아니다'를 적은 줄이 없음")


class EvalSkillPreflight(_ReadsOnlyProduct, unittest.TestCase):
    PATH = "skills/eval/SKILL.md"


class ReviewSkillPreflight(_ReadsOnlyProduct, unittest.TestCase):
    PATH = "skills/review/SKILL.md"

    def test_review_existing_evidence_rule_not_weakened(self):
        # 기존 문장의 규칙을 완화하지 않는다: 증거는 이번 실행에서 통과한 테스트만
        self.assertTrue(lines_matching(self.text, r"증거", r"이번\s*실행에서\s*통과한\s*테스트만"))


class ReadmePreflight(unittest.TestCase):
    def test_readme_describes_preflight_command(self):
        # C9: README의 명령 설명에 preflight가 있다
        # "들어 있는 것" 목록의 파일 경로 줄(예: "tests/test_hb_preflight.py  프로그램의 테스트 (preflight 검사)")은
        # 빼고, 같은 줄에 preflight와 명령 모양(hb.py 또는 --work)이 함께 있는 줄을 찾는다.
        text = read("README.md")
        file_list_line = re.compile(r"^\s*[\w.\-]+(/[\w.\-]+)+\s{2,}\S")
        kept = "\n".join(l for l in text.splitlines() if not file_list_line.match(l))
        hits = lines_matching(kept, w("preflight"), r"hb\.py|--work")
        self.assertTrue(hits, "README에 preflight 명령을 설명한 줄이 없음")


if __name__ == "__main__":
    unittest.main()
