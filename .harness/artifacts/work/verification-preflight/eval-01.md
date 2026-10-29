# 평가 01: verification-preflight

- 날짜: 2026-10-29
- 도구: Claude Code (claude-opus-5-5, high), 새 컨텍스트 서브에이전트
- 자동 메모: 이 세션의 맥락에 앞 세션의 자동 메모가 보이지 않음
- 시작 커밋(state.json `baseline.head`): dae8b745efed1afcb64ca8b20bc52dc82a28019c
- 평가 대상 커밋(`git rev-parse HEAD`): 09281d420cf808cfdbc7801547215e6399353646
- 본 변경: `git diff dae8b74 09281d4 -- . ':(exclude).harness/artifacts/work/verification-preflight'`
  README.md, bin/hb.py, skills/{dev,eval,plan,review}/SKILL.md, tests/test_hb_preflight.py(새), tests/test_hb_review.py, tests/test_skills_preflight.py(새)
- 기준 잡기: 할 일 01, 02 모두 완료(INDEX.md 48, 49줄, state.json `tasks.*.done`). 시작 시 `git status --porcelain` 비어 있음.
- 읽은 것: spec.md, tasks.json, tasks/01·02, INDEX.md, state.json, checks/001·007·008·011·012, .harness/README.md, .harness/docs/checks.json, README.md. 이전 평가 기록 없음(첫 평가).
- 시작 전 검증 기록: 이 작업의 개발은 preflight가 생기기 전 흐름이라 진행표에 preflight 결과가 없다. 완료 증거로는 프로그램 기록만 읽었다: 01 green ok(checks/007 25개 통과, checks/008 120개 통과, 건너뜀 0), 02 green ok(checks/011 18개, checks/012 138개 통과, 건너뜀 0). 바탕 95개 + 25 + 18 = 138로 맞고, 건너뜀 0이라 pytest가 없어 건너뛴 묶음은 없다(.harness/README.md 7줄).

## 영향 지도

| 바뀐 것 | 종류 | 직접 쓰는 곳 | 영향받을 수 있는 기존 동작 | 더 따라간 경로 | 못 따라간 곳 | 테스트 |
|---|---|---|---|---|---|---|
| `cmd_preflight` (bin/hb.py 404–447)와 서브파서 `preflight` (660–665), 실행 표 (668–669) | 함수, API 응답 모양(새 명령) | main | 다른 네 명령의 인자 해석과 실행 표 | 서브파서는 기존 for 루프 밖에서 따로 더해 기존 네 명령의 인자는 그대로. `Stop` 출력에 `blocked`, `summary`, `outcome`, `reuse`, `review_paths`, `time`을 실어 냄(445–446). `verdict`/`reason`과 이름이 겹치지 않음 | 없음 | 있음: tests/test_hb_preflight.py 25개. 기존 명령은 test_hb*.py 전체(checks/012 138개 통과) |
| `logs_not_ignored` (366–372) | 함수(cmd_baseline에서 떼어 냄) | cmd_baseline 456–458, cmd_preflight 412 | baseline의 logs 제외 검사 판정과 문구 | 옛 코드와 같은 두 이름(x.log, x+보고서 확장자), 같은 문구. baseline은 같은 `Stop("stop", 문구)`를 냄 | 없음 | 있음: test_hb.py `test_baseline_stops_when_logs_are_not_ignored`(302) 외 311–325, test_hb_jest.py 286–292, 새 C3 두 개 |
| `environment_problems` (376–390) | 함수(새) | cmd_preflight | 없음(검사를 실제로 돌리지 않음) | pytest는 hb를 돌리는 파이썬의 `find_spec`, run_check 256줄의 `sys.executable -m pytest`와 같은 파이썬. 그 밖은 `shutil.which(command[0])`, 경로 구분자가 있으면 저장소 기준(run_check가 cwd=repo로 돎, 260) | `-m pytest`는 sys.path[0]이 저장소, find_spec은 bin/이라 저장소 안에 따로 둔 pytest 같은 경우는 갈릴 수 있음(드묾). xcodebuild의 `xcrun`은 보지 않음(설명서 C2 범위 밖) | 있음: C1 두 개, C2 두 개. 상대 경로 명령(`./gradlew` 꼴)은 없음 |
| `parse_deadline` (393–401) | 함수(새) | cmd_preflight 406 | 없음 | `Z` 끝은 `+00:00`으로 바꿔 읽음(3.12 이전 파이썬 호환), 시간대 없으면 UTC, 틀리면 `Stop("stop","deadline 형식이 틀림")`(blocked 없음) | 없음 | 있음: `test_bad_deadline_format_stops_without_blocked`, C5 세 개. 시간대 없음·`+09:00`은 없음 |
| 재사용 판단 (425–435) | 함께 쓰는 데이터(state.json의 green 읽기만) | cmd_preflight | state.json, checks/를 고치지 않아야 함 | `snapshot`(91–96)을 그대로 씀. 지문에 HEAD가 들어가므로 커밋 뒤에는 내용이 같아도 `changed`. 개발 흐름에서는 red 뒤 커밋이 막혀 있음(505) | 없음 | 있음: C7 세 개, C8 두 개 |
| 시간 판단 (436–441) | 함수 안 계산 | cmd_preflight | 없음 | needed = 계약 `timeout_seconds` + margin(설명서 17줄 그대로). green은 run_check를 두 번 부름(512, 517) | 없음 | 있음: C5 세 개 |
| 모듈 머리 import 셋(datetime, importlib.util, shutil)과 설명문 | 설정(모듈) | hb.py 전체 | 표준 라이브러리만(README 22줄) | 모두 표준 라이브러리 | 없음 | 전체 묶음이 hb.py를 돌리므로 import 오류는 전체 검사에서 드러남(checks/012) |
| tests/test_hb_review.py `ReviewCase.hb` (84–87) | 테스트 도우미 | ReviewCase의 모든 테스트 | 기존 검수 테스트들의 판정 | hb에 `PYTHONDONTWRITEBYTECODE=1`만 더함. run_check의 pytest가 env=None으로 이 환경을 물려받아 가짜 저장소에 .pyc를 쓰지 않음. 단언·본문은 그대로 | 실제 저장소에서 hb가 돌리는 pytest는 이 보정을 받지 않음(아래 권장 1) | 있음: `test_stops_when_a_commit_after_done_breaks_an_old_test`(249) 등. checks/008·012에서 통과 |
| skills/dev/SKILL.md (28, 47–59, 65, 71, 74, 121) | 문서(절차) | 개발 지휘 | 기존 순서·멈췄을 때 표 | 기존 규칙 줄(103 "진행을 막는 지적은 꼭 고칠 것뿐", not_run/timeout)은 그대로. 멈췄을 때 표의 "시작 전 검증에서 막힘"은 코드 문구(445)와 맞음 | blocked 없는 stop(deadline 형식, 없는 할 일, 계약 없음)의 처리 행은 표에 없음 | 있음: test_skills_preflight.py DevSkillPreflight 8개 |
| skills/plan/SKILL.md 42 | 문서 | 계획 9번 뒤 | 44줄 "9번이 끝나면 개발을 시작할 수 있다고 알리고 멈춘다" | 42줄이 stop이면 그렇게 말하지 않는다고 조건을 붙임. 44줄과 순서상 겹침 | 없음 | 있음: PlanSkillPreflight 2개 |
| skills/eval/SKILL.md 28–31, skills/review/SKILL.md 55–57 | 문서 | 평가자, 검수자 | 검수의 "증거는 이번 실행에서 통과한 테스트만" | review 55줄이 그 규칙을 다시 적음. 완화 없음 | 없음 | 있음: Eval/ReviewSkillPreflight 각 3개, `test_review_existing_evidence_rule_not_weakened` |
| README.md 30–31, 45 | 문서 | 사용자 | 없음 | 명령 설명 한 문단 | 없음 | 있음: `test_readme_describes_preflight_command` |

## 점검표

| 관점 | 확인 대상 → 근거 → 판단 |
|---|---|
| 맞는가 | C1: pytest 계약에서 find_spec이 None이면 environment 이유 하나 → hb.py 379–386, `outcome.environment`는 423 → 문제없음. C2: which(command[0]) → 387–389 → 문제없음. C3: baseline과 같은 두 이름 → 366–372, 412–414 → 문제없음. C4: `outside_allowed` 재사용, task 없으면 scope → 415–422 → 문제없음. C5: `int()`는 양수에서 내림이라 `remaining < needed`는 실수 비교와 같음(needed가 정수) → 437–441 → 문제없음. C6: 세 칸을 각각 정하고 blocked가 있으면 product와 상관없이 stop → 423–428, 444 → 문제없음. C7: same_source/changed와 합집합 review_paths → 429–435 → 문제없음. C8: preflight 경로에 save_json·makedirs·run_check 호출 없음 → 404–447 → 문제없음. 예외: 형식 틀린 deadline이 가장 먼저(406), 없는 할 일은 `ctx.task`의 같은 문구(353), state.json 없으면 not_run·reuse 없음(425), 여러 종류 동시 기록(445) → 문제없음. 경계: `--margin` 음수를 막지 않음(665) → 권장 6 |
| 안전한가 | `--aux` 경로는 비교만 하고 열거나 실행하지 않음(419), 계약 명령은 which만 하고 실행하지 않음(388). 비밀값·개인정보 다루지 않음. 결제·권한·개인정보·DB 해당 없음(spec 38줄) → 문제없음 |
| 기존 코드와 맞는가 | `Stop`과 JSON 한 줄 출력(670–673), `snapshot`, `outside_allowed` 재사용(spec 35줄) → 문제없음. cmd_baseline의 logs 검사 문구·순서 같음(456–458 대 옛 코드) → 문제없음. 기존 네 명령의 서브파서 불변(649–659) → 문제없음 |
| 비용 | git 호출 몇 번(check-ignore 두 번, snapshot의 rev-parse·status 한 번씩), 반복·대기 없음 → 문제없음 |
| 저장소 규칙 | .harness/README.md 8줄(표준 라이브러리만, 기존 판정과 안전 관문 유지): import 셋 모두 표준, check/done/review/지문 불변 → 문제없음. 9줄(logs/는 git에 넣지 않음): `git status --ignored`에서 logs/ 제외 확인 → 문제없음. spec 35줄 "기존 테스트를 고치지 않는다"와 test_hb_review.py 보정: 단언 불변, 감독 지시 원문과 재현 근거가 INDEX 28–29줄과 tasks/01 14–15줄에 있고 red부터 다시 받음(checks/006) → 진행은 맞으나 spec.md 제약 줄이 고쳐지지 않아 문서끼리 어긋남 → 지적(권장 2) |
| 할 일끼리 | 02 문서의 이름(product/environment/aux, environment/evidence/scope/time, same_source/changed, review_paths)이 01 출력과 같음 → dev SKILL 51–58, hb.py 411–435 → 문제없음. dev 57줄이 합집합의 뜻을 적음(01 구현 검토의 권장 반영) → 문제없음. plan 42줄과 44줄이 "9번이 끝나면"을 두 번 말함 → 권장 5 |
| 테스트 전체 | 완료 기준 C1–C9와 설명서 예외 넷에 모두 행동/문서 테스트가 있음(test_hb_preflight.py 218–417, test_skills_preflight.py 60–176) → 문제없음. 허술한 곳: C7 수정 테스트(358–364)의 app.py는 green paths에 늘 있어 "지금 바뀐 경로"를 보는지 가리지 못함(새 파일 테스트 366–371이 그 몫을 함) → 권장 7. 테스트와 구현이 같은 잘못된 가정: needed를 timeout 한 번으로 둔 것은 설명서 정의대로라 테스트도 같음 → 권장 3. pytest 없으면 PreflightCase 전체가 건너뜀(101)이나 이번 기록은 건너뜀 0 → 문제없음 |
| 남은 권장 | 아래 "남은 권장 다시 보기"에서 하나씩 봄. 꼭 고칠 것으로 올릴 근거 있는 것 없음 |

## 이전 지적 대조

첫 평가라 해당 없음.

## 지적

### 구현 오류 (꼭 고칠 것)
없음.

### 필수 테스트 누락
없음.

### 질문
없음.

### 검수 확인 항목
1. 전체 검사 다시 돌리기. pytest가 깔린 파이썬(INDEX 9줄)으로 `review`를 돌려 새로 깨진 것 0, 건너뜀 0인지. 기대: 바탕 95개 + 25 + 18 = 138개, tests/test_hb_preflight.py의 25개가 건너뛰지 않고 통과.
2. 보정한 fixture의 테스트 `tests.test_hb_review.ReviewCase::test_stops_when_a_commit_after_done_breaks_an_old_test`가 검수 실행에서도 통과하는지. 기대: 통과(바이트코드를 쓰지 않으니 수정 시각과 상관없이 같은 결과).
3. 바탕 검사 뒤 바뀐 파일이 할 일들의 허락된 파일 안인지(`review` 프로그램이 봄). 기대: tests/test_hb_review.py는 할 일 01의 allowed_files에 있어 막히지 않음.

### 권장
1. **실제 저장소의 옛 .pyc.** test_hb_review.py 보정은 가짜 저장소에서만 바이트코드를 끈다. hb.py `run_check`(256)는 실제 저장소에서 `sys.executable -m pytest`를 그대로 돌리므로, 크기가 같은 변경이 직전 실행과 같은 초에 쓰이면 옛 .pyc로 깨진 동작이 가려질 수 있다(INDEX 28줄의 재현과 같은 원리). 이번 변경이 만든 문제가 아니고 설명서 범위 밖이라 다음 작업 후보로 사용자에게 알린다.
2. **spec.md 제약 줄.** 35줄 "기존 테스트를 고치지 않는다"에 할 일 01의 fixture 보정 예외(tasks/01 14줄)를 함께 적어, 설명서만 읽는 검수자가 어긋난다고 읽지 않게 한다.
3. **시간 판단의 필요 시간.** `check --phase green`은 run_check를 두 번(할 일 검사 512, 전체 검사 517) 부르므로 최악은 timeout_seconds의 두 배다. 지금은 설명서 17줄 정의(timeout + margin)대로라 오류는 아니다. dev 54줄에 green 전에는 margin을 넉넉히 주라고 적거나 다음 설명서에서 정의를 다시 본다.
4. **reuse와 커밋.** `snapshot`에 HEAD가 들어가므로(91–96) 커밋 뒤에는 내용이 같아도 `changed`가 나오고, green 뒤 커밋에서만 바뀐 파일은 `review_paths`에 없다. 개발 흐름에서는 red 뒤 커밋이 막혀(505) 문제가 되지 않는다. dev 57줄에 "커밋 전 기준"이라고 적어 두면 오해가 없다.
5. **문서 다듬기(개발 때 남은 권장 유지).** dev 58줄 "preflight가 내는 지적"은 preflight의 stop까지 권장처럼 읽힐 수 있어 "검토의 권장"으로 좁힌다. plan 42줄과 44줄을 합친다. dev 멈췄을 때 표에 blocked 없는 stop(deadline 형식, 없는 할 일, 계약 없음)은 reason을 적고 사용자에게 알린다는 행을 더한다. eval 29줄과 review 55줄의 "product만"을 "product: pass이고 reuse가 changed가 아님"으로 밝힌다(테스트 정정으로 red를 다시 받기 전에는 옛 green 때문에 product가 pass로 나온다, 428·490).
6. **`--margin` 음수.** 665줄이 음수를 받아 needed가 제한 시간보다 작아질 수 있다. 0 이상만 받게 하면 시간 판단이 약해지지 않는다.
7. **C7 수정 테스트.** 358–364는 green paths에 이미 있는 app.py만 보므로, review_paths가 green paths만 내도 통과한다. green paths에 없던 기존 추적 파일을 고치는 경우를 더하면 합집합을 더 정확히 확인한다.

## 남은 권장 다시 보기

| 개발 때 남은 권장 (INDEX 줄) | 지금 판단 |
|---|---|
| run_check의 옛 .pyc (37) | 권장 유지(권장 1). 이번 변경이 깬 동작이 아니고 설명서 범위 밖 |
| green 뒤 커밋의 새 파일이 review_paths에 없음, 합집합 뜻 문서화 (41) | 문서화는 dev 57줄에 반영됨. 앞부분은 red 뒤 커밋을 막는 기존 관문(505) 때문에 흐름 안에서 생기지 않음. 권장 유지(권장 4) |
| C7 같은 경로 내용 변경은 "포함"만 확인, C6 product: fail은 실제 흐름에서 못 만듦, C4 280줄 assertNotIn (47) | 권장 유지. product: fail은 check_green이 ok일 때만 green을 써서(527) 만들 수 없음. 280줄은 지금 문구(421)와 맞고 막는 것 없음 |
| 테스트 검토 1의 꼭 고칠 것(state.json 없음 + --task) (46) | 고쳐짐: `test_c8_preflight_before_baseline_creates_no_records`(390–397) |
| dev 58줄, plan 44줄, eval/review "product만", blocked 없는 stop, --deadline 형식 (55) | 권장 유지(권장 5). --deadline 형식은 dev 28줄 `<UTC 시각>`, hb.py 664 도움말에 있음. plan 42줄에 파이썬 안내는 들어감 |
| eval/review "만" 미확인, 세 칸 "보고" 미확인, "각 check" 미확인, 권장 규칙 절 제한, dev 88줄 뒷문장 보호, eval 17줄 보호 (60) | 권장 유지. 문서 본문(dev 51·55, eval 29, review 55)은 그 뜻을 실제로 적고 있어 지금 동작에 빠진 것은 없음 |

## 테스트로 확인되는 것과 안 되는 것

- 확인됨(행동 테스트): C1–C8, 설명서 예외 넷, baseline의 logs 검사 문구(기존 test_hb.py·test_hb_jest.py), 문서의 C9 문장(낱말·줄 단위).
- 허술함: C7 수정 경우(권장 7), 상대 경로 명령(`./gradlew` 꼴)의 C2, 시간대 없음·다른 시간대의 deadline.
- 안 됨: product: fail(실제 흐름에서 못 만듦), 실제 저장소의 옛 .pyc(권장 1), 문서 문장이 지휘에게 실제로 그렇게 읽히는지(문서 테스트는 낱말 묶음만 봄).

## 다음 단계

검수로. 구현 오류, 필수 테스트 누락, 질문이 없다. 새 창(자동 메모 끔)에서 검수(`review`)를 부르고, `--since 09281d420cf808cfdbc7801547215e6399353646`을 준다. 위 검수 확인 항목은 검수가 읽는다. 권장 1(실제 저장소의 옛 .pyc)은 설명서 범위 밖이라 다음 작업 후보로 사용자가 정한다.
