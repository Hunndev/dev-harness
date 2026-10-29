# 평가 02: verification-preflight

- 날짜: 2026-10-29
- 도구: Claude Code (claude-opus-5-5, high), 새 컨텍스트 서브에이전트
- 자동 메모: 이 세션의 맥락에 앞 세션의 자동 메모가 보이지 않음
- 시작 커밋(state.json `baseline.head`): dae8b745efed1afcb64ca8b20bc52dc82a28019c
- 평가 대상 커밋(`git rev-parse HEAD`): a3e62cf765387ad601aa110b02ccfdcf31092ffa
- 본 변경: `git diff dae8b74 a3e62cf -- . ':(exclude).harness/artifacts/work/verification-preflight'`
  README.md, bin/hb.py, skills/{dev,eval,plan,review}/SKILL.md, tests/test_hb_preflight.py(새), tests/test_hb_preflight_paths.py(새), tests/test_hb_review.py, tests/test_skills_preflight.py(새)
- 기준 잡기: 할 일 01, 02, 03 모두 완료(INDEX.md 48·49·60줄, state.json `tasks.{01,02,03}.done`). 시작 때 `git status --porcelain` 빈 값.
- 이번 평가의 더한 일(감독 지시): 검수 01 뒤 Claude 일반 review(/code-review high, f4f61ab..72c79ed)의 #1·#2·#3·#5·#6·#7을 spec.md 정의로 독립 판정. 아래 "일반 review 지적 독립 판정".
- 읽은 것: spec.md, tasks.json, tasks/01·03, INDEX.md, state.json, checks/014·015·016, .harness/README.md, .harness/docs/checks.json, bin/hb.py 전체, tests/test_hb_preflight.py, tests/test_hb_preflight_paths.py, 문서 diff. 이전 기록(eval-01.md, review-01.md)은 점검표를 끝낸 뒤 읽음.
- 명령: 읽기용 git, 파일 읽기(ls, grep)만 씀. 한 번 실수로 아무 일도 하지 않는 `python3 -c "pass"`가 다른 읽기 명령 앞에 붙어 돌았다(저장소 파일을 읽거나 쓰지 않음, 테스트·hb.py 아님).
- 시작 전 검증 기록: 진행표에 할 일 03의 `preflight` 결과가 적혀 있지 않다(권장 4). 완료 증거로는 프로그램 기록만 읽었다: 03 red ok(checks/014, 본문 실패 8, 통과 5), 03 green ok(checks/015 13개 통과, checks/016 전체 151개 통과, 건너뜀 0). 151 = 검수 01의 138 + 13으로 맞고 건너뜀 0.

## 영향 지도

줄 번호는 a3e62cf의 bin/hb.py 기준.

| 바뀐 것 | 종류 | 직접 쓰는 곳 | 영향받을 수 있는 기존 동작 | 더 따라간 경로 | 못 따라간 곳 | 테스트 |
|---|---|---|---|---|---|---|
| `cmd_preflight` (419–467), 서브파서 (680–685), 실행 표 (688–689) | 함수, API 응답 모양(새 명령) | main | 다른 네 명령의 인자와 실행 | 서브파서는 기존 for 루프 밖. `Stop` 출력에 `blocked`, `summary`, `outcome`, `reuse`, `review_paths`, `time`을 실음(465–466) | 없음 | 있음: test_hb_preflight.py 25개, test_hb_preflight_paths.py 13개 |
| 제품 결과 칸 `product` (443–448) | 함께 쓰는 데이터(state.json green 읽기) | cmd_preflight | 없음(읽기만) | green은 check_green 547줄에서만 쓰이고 늘 `ok: True`. 실패한 green은 534–546줄의 `Stop`으로 앞 green을 지우지 않음. check_red 510줄은 할 일 항목을 통째로 바꿔 green을 지움 | 없음 | 있음: C6 네 개. `fail` 갈래 없음(만들 수 없음) |
| 재사용 판단 `reuse`, `review_paths` (449–455) | 함께 쓰는 데이터 | cmd_preflight | state.json을 고치지 않아야 함 | `snapshot`(91–96) = HEAD + `changed()`(84–88, 커밋 안 된 경로만). green 기록에는 `snapshot`, `paths`만 있고 HEAD가 없음(547). green 때 HEAD는 red.head와 같음(525 관문) | 없음 | 허술함: C7 세 개 모두 커밋 없는 경우. green 뒤 커밋으로 바뀐 파일은 테스트 없음(구현 오류 1) |
| 시간 판단 (456–461) | 함수 안 계산 | cmd_preflight | 없음 | needed = 계약 `timeout_seconds` + margin. green은 run_check를 두 번 부름(532, 537), 각 실행 제한 timeout_seconds(261), xcodebuild는 xcresulttool도 같은 제한(271) | 없음 | 있음: C5 세 개. 음수 margin 없음 |
| `repo_relative` (366–373) | 함수(새, 할 일 03) | cmd_preflight 436 | 없음 | 상대 경로는 저장소 기준(부른 폴더 기준 아님), `normpath`로 `..`를 접고 abspath/realpath 두 기준으로 저장소 안인지 봄. 저장소 안 심볼릭 링크는 풀지 않음 | `--repo` 없이 Ctx.repo가 실제 경로(git toplevel)이고 `--aux`가 링크 쪽 절대 경로면 저장소 밖으로 막힘(권장 5) | 있음: paths C4 여덟 개 |
| `environment_problems` (386–405) | 함수(새, 할 일 03에서 고침) | cmd_preflight 424 | 없음(검사를 돌리지 않음) | pytest는 hb를 돌리는 파이썬의 find_spec(run_check 256과 같은 파이썬). 그 밖은 구분자 있으면 저장소 기준, 없으면 PATH 각 항목을 저장소 기준으로 풀어 which(run_check cwd=repo, 260과 같음) | 빈 PATH 항목(테스트 없음) | 있음: C1 두 개, C2 두 개 + paths C2 네 개 |
| `logs_not_ignored` (376–382) | 함수(cmd_baseline에서 떼어 냄) | cmd_baseline 476, cmd_preflight 427 | baseline의 logs 검사 판정과 문구 | 옛 코드와 같은 두 이름·같은 문구 | 없음 | 있음: test_hb.py·test_hb_jest.py의 기존 logs 테스트, C3 두 개 |
| `parse_deadline` (408–416) | 함수(새) | cmd_preflight 421 | 없음 | `Z`는 `+00:00`으로, 시간대 없으면 UTC, 틀리면 blocked 없는 stop | 없음 | 있음: 형식 테스트 하나, C5 세 개 |
| import 셋, 머리 설명 | 모듈 | hb.py 전체 | 표준 라이브러리만 | datetime, importlib.util, shutil 모두 표준 | 없음 | 전체 묶음(checks/016) |
| tests/test_hb_review.py `ReviewCase.hb` | 테스트 도우미 | ReviewCase 전체 | 기존 검수 테스트 판정 | `PYTHONDONTWRITEBYTECODE=1`만 더함, 단언 그대로 | 없음 | checks/016에서 통과 |
| skills/dev 28, 47–60, 65, 71, 74, 121 / plan 42 / eval 28–31 / review 55–57 / README 30–31, 45 | 문서 | 지휘, 평가자, 검수자, 사용자 | 기존 절차 | dev 57줄이 review_paths를 "green 때 경로와 지금 바뀐 경로의 합집합"으로 적음 | 없음 | 있음: test_skills_preflight.py 18개 |

## 점검표

| 관점 | 확인 대상 → 근거 → 판단 |
|---|---|
| 맞는가 | C1 → 389–396, 443 → 문제없음. C2 → 397–405(상대 PATH는 저장소 기준) → 문제없음. C3 → 376–382, 427–429 → 문제없음. C4 → 430–442, 저장소 밖과 `..` 정리 → 문제없음(링크 경로 하나는 잘못 막는 쪽, 권장 5). C5 → 456–461, spec 17·28줄 공식 그대로 → 문제없음. C6 → 443–448, blocked가 있으면 product와 상관없이 stop(464) → 문제없음. C7 → 449–455: 커밋 없는 변경은 맞음. **green 뒤 커밋으로 바뀐 파일이 green paths 밖이면 review_paths에 없음** → 지적(구현 오류 1). C8 → 419–467에 save_json·makedirs·run_check 없음 → 문제없음. 예외 넷 → 421(형식이 맨 먼저), 422(`ctx.task` 문구), 445(state 없으면 not_run·reuse 없음), 464–466(여러 종류 한 stop) → 문제없음 |
| 안전한가 | `--aux`는 정리·비교만 하고 열거나 실행하지 않음(435–440). 명령은 which만(402). 저장소 밖 경로는 막음(437–438). 비밀값·개인정보 없음. 결제·권한·개인정보·DB 해당 없음(spec 38줄) → 문제없음 |
| 기존 코드와 맞는가 | `Stop`과 JSON 한 줄(690–693), `snapshot`, `outside_allowed` 재사용(spec 35줄) → 문제없음. 할 일 03은 preflight 안의 두 곳만 고침(a3e62cf의 bin/hb.py +30/−5), check/done/review/지문 불변 → 문제없음 |
| 비용 | git 몇 번(check-ignore 두 번, snapshot의 rev-parse·status), which 한 번. 반복·대기 없음 → 문제없음 |
| 저장소 규칙 | .harness/README.md 8줄(표준 라이브러리, 기존 판정과 안전 관문 유지) → 문제없음. 9줄(logs/ git 제외) → `git check-ignore`로 확인, 문제없음. dev SKILL 54줄("세 칸을 따로 진행표에 보고")은 할 일 03의 진행표에 preflight 결과가 없음 → 지적(권장 4) |
| 할 일끼리 | 03은 01의 `--aux`와 명령 찾기만 고치고 01의 테스트 파일은 그대로(tasks/03 18줄) → 문제없음. 02의 dev 57줄 "합집합" 설명은 01 구현과 같으나 spec C7과는 커밋 뒤 경우에 어긋남(구현 오류 1과 같은 뿌리) → 지적 |
| 테스트 전체 | C7 세 테스트(test_hb_preflight.py 351–371)는 모두 커밋 없는 변경만 본다. 수정 테스트의 app.py는 green paths에 이미 있어 "지금 바뀐 경로"를 가리지 못함. 테스트와 구현이 "바뀐 경로 = 커밋 안 된 경로"라는 같은 가정을 함 → 지적(구현 오류 1). needed가 timeout 한 번인 것은 spec 정의라 테스트도 같음 → 비차단(권장 1). paths의 저장소 탈출 세 테스트에 "경로 변경 필요" 단언 없음(코드 438은 냄) → 권장 6 |
| 남은 권장 | 아래 "남은 권장 다시 보기". "green 뒤 커밋에서 새로 들어온 파일은 review_paths에 안 나옴"(INDEX 41)은 지금 보니 spec C7 위반이라 꼭 고칠 것으로 올림 |

## 이전 지적 대조

평가 01의 꼭 고칠 것(구현 오류, 필수 테스트 누락, 질문)은 0건이었다(eval-01.md 50–57줄). 고쳐졌는지 볼 항목이 없다.

평가 01의 권장 가운데 이번 판정과 겹치는 것:
- 권장 3(green의 두 번 실행)·권장 6(음수 margin): 이번에도 spec 정의대로라 권장으로 둔다(아래 #3, #7).
- 권장 4(reuse와 커밋): 평가 01은 "red 뒤 커밋이 막혀(525) 흐름 안에서 문제가 되지 않는다"고 봤다. 그 관문은 green 전까지만 커밋을 막는다. done 뒤 커밋과 다음 할 일의 커밋은 흐름의 정상 단계이고, 그 뒤 `preflight --task <앞 할 일>`의 review_paths에서 그 커밋들의 파일이 빠진다. 앞부분(커밋 뒤 늘 changed, #6)은 spec 정의대로지만, 뒷부분(#5)은 spec C7 문언 위반으로 판단을 바꾼다(구현 오류 1).
- 할 일 03(검수 01 뒤 더함): 지적 두 건(--aux 정규화, 상대 PATH)은 tasks/03 8–11줄의 기대대로 고쳐졌다(366–373, 435–440, 397–402). paths 테스트 13개가 green에서 통과(checks/015).

## 일반 review 지적 독립 판정

판정 근거는 spec 문장, 코드 줄, 테스트뿐이다. INDEX.md의 앞선 분류와 감독 지시 문구는 근거로 쓰지 않았다.

| 지적 | spec 근거 | 코드 근거 | 판정 |
|---|---|---|---|
| #1 뒤에 실패한 green이 있어도 옛 green으로 `product: pass` | 13줄 "`pass`(그 할 일의 green 기록이 ok)". 18줄 "baseline/check/done/review 판정은 그대로", 35줄 "기존 판정을 고치지 않는다". eval SKILL 29줄: product는 check 기록(state.json, checks/)과 함께만 읽음 | check_green은 성공 때만 green을 씀(547), 실패는 534–546의 `Stop`으로 끝나 앞 green이 남음. 실패한 실행의 기록은 checks/에 남음(run_check 287). preflight는 그 green을 읽음(446–448). 소스가 바뀌었으면 `reuse: changed`가 함께 나옴(451–455) | **spec 정의대로이며 비차단.** spec이 product를 "그 할 일의 green 기록"으로 정했고, 실패를 green 기록에 남기려면 금지된 check 판정 변경이 필요하다. 권장 2(뜻을 문서에 밝히기) |
| #2 `product: fail` 갈래가 실제로 나오지 않음 | 13줄 "`fail`(기록이 ok 아님)". C6(29줄)이 요구한 행동 테스트는 pass/incomplete, environment blocked → stop 두 경우뿐 | 448 `"pass" if green.get("ok") else "fail"`가 spec 정의를 그대로 옮김. 지금 check_green은 ok가 아닌 green을 쓰지 않음(547) | **spec 정의대로이며 비차단.** 기록이 ok가 아닐 때의 출력은 정의대로다. 실제 흐름에서 그런 기록이 생기지 않는 것은 18·35줄이 지키라고 한 기존 판정 때문이다. 완료 기준이 이 경우의 테스트를 요구하지 않으므로 필수 테스트 누락도 아님 |
| #3 needed가 한 번 실행만 셈(green은 두 번, xcodebuild는 xcresulttool까지) | 17줄 "`needed_seconds`(= 계약의 `timeout_seconds` + margin)", C5(28줄) "(deadline − 지금) < `timeout_seconds` + margin이면 stop" | 458 `needed = ctx.contract["timeout_seconds"] + args.margin`. green은 run_check 두 번(532, 537), 각 제한 timeout_seconds(261), xcresulttool도 같은 제한(271) | **spec 정의대로이며 비차단.** 공식이 spec에 글자로 정해져 있고 코드가 같다. 최악 시간은 2배 이상이므로 권장 1(문서 안내, 다음 설명서 후보) |
| #5 (a) spec C7 문언 대비: green 뒤 커밋으로 바뀐 파일이 review_paths에 없음 | C7(30줄) "green 기록 뒤 소스가 같으면 `reuse: same_source`, 파일을 바꾸면 `changed`와 그 파일이 `review_paths`에 나온다". 16줄 "`same_source`(지금 스냅숏이 green 기록과 같음) 또는 `changed`와 바뀐 경로 목록 `review_paths`". 스냅숏은 HEAD를 포함(35줄이 `snapshot` 재사용을 정함, 91–96). 커밋에 대한 예외는 spec에 없음 | 455 `review_paths = sorted(set(paths) | set(green["paths"]))`, `paths`는 `changed()`(84–88)라 커밋 안 된 경로만. green 뒤 커밋으로만 바뀐 파일이 green paths 밖이면 빠짐. 테스트 351–371은 커밋 없는 경우만 | **spec 정의상 구현 오류(꼭 고칠 것).** 커밋 때문에 스냅숏이 달라져 `changed`를 내면서(16줄의 "바뀐" 기준), 그 커밋으로 바뀐 파일은 "바뀐 경로 목록"에 넣지 않는다. 덜 알리는 쪽이라 재사용 판단을 잘못 이끈다. 구현 오류 1 |
| #5 (b) 구현·문서의 합집합 정의 대비 | 해당 spec 문장 없음. 합집합은 개발 중 지휘 정정(INDEX 25·40줄)이고 dev SKILL 57줄에 적힘. spec은 고쳐지지 않음 | 455가 "green paths ∪ 지금(HEAD 대비) 바뀐 경로"를 정확히 냄 | **합집합 정의 대비로는 맞다.** 그러나 그 정의는 승인된 spec이 아니고, 커밋 뒤 경우에 C7과 어긋나므로 (a)의 판정을 바꾸지 않는다 |
| #6 done + 커밋 뒤에는 같은 코드라도 늘 `changed` | 16줄 "`same_source`(지금 스냅숏이 green 기록과 같음)", 35줄 "`snapshot`… 재사용" | snapshot은 HEAD를 지문에 넣음(93–95). 커밋하면 HEAD가 바뀌어 451이 거짓, 452가 아니라 454로 감 | **spec 정의대로이며 비차단.** spec이 같음의 기준을 스냅숏으로 정했고, 스냅숏은 HEAD를 포함한다. 바뀐 경로를 덜 알리지 않는 쪽(더 보수적)이다. 커밋 뒤 review_paths는 #5 수정의 범위 |
| #7 `--margin` 음수로 시간 막기를 끌 수 있음 | 8줄 "`--margin <초, 기본 120>`". 17줄·C5 공식. 예외 상황(40–44줄)에 margin 검사 없음 | 685 `type=int`, 하한 없음. 458 공식 그대로. `time.needed_seconds`가 출력에 늘 실림(459) | **spec 정의대로이며 비차단.** spec이 값의 범위를 정하지 않았고, 공식대로 계산하며 결과가 출력에 드러난다("몰래"가 아님). 음수를 막는 것은 새 요구라 권장 3 |

## 지적

### 구현 오류 (꼭 고칠 것)

1. **green 뒤 커밋으로 바뀐 파일이 `review_paths`에 나오지 않음** (일반 review #5 (a)). 관련 완료 기준 C7. 코드에서 도출한 예상 실패(실행하지 않음).
   - 입력: 실제 hb로 할 일 01의 baseline → red → green(green paths `app.py`, `tests/test_new.py`). 그 뒤 green paths 밖의 파일을 커밋으로 바꾼다. 예: 새 파일 `extra.py`를 더해 커밋하거나, 이미 추적되는 `tests/test_app.py`를 고쳐 커밋한다. 작업 트리는 깨끗. `preflight --work w1 --task 01`.
   - 기대 결과(spec C7, 16줄): `reuse`는 `changed`, `review_paths`에 그 파일(`extra.py` 또는 `tests/test_app.py`)이 들어 있다. 커밋하지 않고 바꾼 경우(기존 테스트 366–371)와 같은 결과.
   - 지금 코드가 낼 결과: `reuse: changed`(HEAD가 바뀌어 스냅숏이 다름, 451), `review_paths = ["app.py", "tests/test_new.py"]`. `changed()`(84–88)가 커밋 안 된 경로만 내므로 `paths`가 비고, 455의 합집합에는 green paths만 남는다.
   - 이 저장소의 예(코드에서 도출): 지금 `preflight --task 01`은 review_paths에 bin/hb.py, tests/test_hb_preflight.py, tests/test_hb_review.py만 내고, 할 일 01 green(HEAD dae8b74) 뒤 커밋된 README.md, skills/*/SKILL.md, tests/test_skills_preflight.py, tests/test_hb_preflight_paths.py는 내지 않는다.
   - 근거: bin/hb.py 84–96, 449–455; spec.md 16·30·35줄; tests/test_hb_preflight.py 351–371(커밋 경우 없음).
   - 할 일 04로 더함(tasks/04-preflight-reuse-commits.md).

### 필수 테스트 누락
없음. (`product: fail`은 C6이 테스트를 요구한 경우가 아니다. #2 판정 참조.)

### 질문
없음. 여섯 건 모두 spec 문장으로 기대 결과를 정할 수 있었다.

### 검수 확인 항목
1. 할 일 04가 끝난 뒤 전체 검사 다시 돌리기. 기대: 새로 깨진 것 0, 건너뜀 0, 전체 = 151 + 할 일 04의 새 테스트 수.
2. 할 일 04의 새 테스트가 커밋 경우(green paths 밖 파일을 커밋)와 기존 C7 세 경우를 함께 통과하는지. 기대: 기존 test_hb_preflight.py 25개, test_hb_preflight_paths.py 13개가 그대로 통과(이 둘은 고치지 않음).
3. 할 일 04 뒤에도 preflight가 기록을 만들거나 고치지 않는지(C8 테스트 두 개 통과). 기대: 통과.

### 권장
1. **시간 판단과 green의 두 번 실행** (#3, 평가 01 권장 3 유지). spec 17줄 정의대로라 오류가 아니다. dev SKILL 53줄에 green 전에는 margin을 timeout_seconds 이상 넉넉히 주라고 적거나, 다음 설명서에서 needed의 정의를 다시 본다.
2. **product의 뜻** (#1, #2). dev SKILL 시작 전 검증 절에 "product는 그 할 일의 마지막으로 성공한 green 기록을 읽는다. 그 뒤 실패한 green은 checks/에만 남는다"를 적으면 오해가 없다. `fail` 갈래는 정의대로 두고, 실제 흐름에서 나오지 않는다는 사실을 함께 적는다.
3. **`--margin` 음수** (#7, 평가 01 권장 6 유지). 0 이상만 받게 하는 것은 새 요구라 다음 작업 후보.
4. **할 일 03의 시작 전 검증 기록.** dev SKILL 51·54줄은 각 check 전에 preflight를 돌리고 세 칸을 진행표에 보고하라고 하는데, INDEX의 할 일 03(49–58줄)에 preflight 결과가 없다. 할 일 04부터는 red·green 전 preflight의 verdict와 `outcome` 세 칸을 진행표에 적는다.
5. **링크 경로의 `--aux`** (할 일 03 구현 검토의 남은 권장 유지). `--repo` 없이 Ctx.repo가 git toplevel(실제 경로)이고 `--aux`가 링크 쪽 절대 경로면(366–373) 허락된 파일인데도 "저장소 밖. 경로 변경 필요"로 막힌다. 잘못 막는 쪽이고 안내대로 상대 경로를 주면 풀린다.
6. **paths 테스트 단언.** 저장소 탈출 세 테스트(test_hb_preflight_paths.py 178–199)에 "경로 변경 필요" 단언이 없다. C4 문구(spec 27줄)를 지키는지 보려면 더한다.

## 남은 권장 다시 보기

| 개발 때 남은 권장 (INDEX 줄) | 지금 판단 |
|---|---|
| run_check의 옛 .pyc (37) | 권장 유지(평가 01 권장 1). 설명서 범위 밖 |
| green 뒤 커밋의 새 파일이 review_paths에 없음 (41) | **꼭 고칠 것으로 올림**(구현 오류 1). "지휘만 커밋하는 규칙이라 C7 범위 밖"이라는 이유는, 그 규칙이 green 전 커밋만 막고(525) done 뒤 커밋은 정상 흐름이라 성립하지 않는다 |
| 합집합이라 안 바뀐 파일도 들어감, 문서화 (41) | 반영됨(dev 57줄). 더 알리는 쪽이라 C7과 어긋나지 않음 |
| C7 같은 경로 내용 변경, C6 product: fail, C4 280줄 (47) | 권장 유지. product: fail은 #2 판정대로 |
| dev/plan/eval/review 문서 다듬기 (66, 71) | 권장 유지(평가 01 권장 5) |
| 할 일 03: 링크 경로 --aux, 빈 PATH 항목 테스트 (53) | 링크 경로는 권장 5. 빈 PATH 항목은 os.path.join(ctx.repo, "")로 저장소를 가리켜 run_check(cwd=repo)와 같은 곳을 찾음(402). 테스트 없음은 권장으로 둠 |
| 할 일 03: 탈출 테스트 "경로 변경 필요" 단언, 링크 절대 경로 테스트의 aux 단언 (56) | 권장 6. 뒤의 것은 동작에 빠진 것 없음 |

## 테스트로 확인되는 것과 안 되는 것

- 확인됨(행동 테스트, checks/015·016 통과): C1–C8의 커밋 없는 경우, 설명서 예외 넷, --aux 정규화와 저장소 탈출, 상대 PATH, baseline의 logs 검사, 보정한 review fixture.
- 확인됨(문서 내용 테스트): C9 문장.
- 허술함: C7 수정 경우(app.py가 green paths에 있음), 음수 margin, 빈 PATH 항목, 시간대 없음·다른 시간대의 deadline.
- 안 됨: **green 뒤 커밋으로 바뀐 파일의 review_paths**(구현 오류 1), `product: fail`(실제 흐름에서 못 만듦), 실패한 green 뒤의 product, 커밋 뒤 same_source가 나오지 않는 것(#6, 정의대로), `--repo` 없는 링크 경로 --aux.

## 다음 단계

**개발로.** 설명서 범위 안의 구현 오류 1건(C7)이 있어 할 일 04를 더했다(tasks.json, tasks/04-preflight-reuse-commits.md, 진행표 "대기"). 사용자는 개발(`dev`)을 불러 할 일 04를 진행하고, 끝나면 새 창(자동 메모 끔)에서 평가를 다시 받는다. 다시 받은 횟수 1(한도 3).

일반 review #1·#2·#3·#6·#7과 #5 (b)는 spec 정의대로이며 비차단이다(근거는 위 표). 권장 1·3은 spec 정의를 바꾸는 일이라 다음 설명서 후보로 사용자가 정한다.
