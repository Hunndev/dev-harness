# 검수 02: verification-preflight

- 날짜: 2026-10-29
- 도구: Claude Code (claude-opus-5-5, high), 새 컨텍스트 서브에이전트
- 자동 메모: 이 세션의 맥락에 앞 세션의 자동 메모가 보이지 않음
- 시작 커밋(state.json `baseline.head`): dae8b745efed1afcb64ca8b20bc52dc82a28019c
- 평가 대상 커밋(eval-03.md 7줄): 067a75d1b534ae49ea79faa76acb818323df1a1e
- 검수 대상 커밋(`git rev-parse HEAD`): 3bf2672fa0528540ccad271942bd34c7f702a076 (067a75d 뒤 바뀐 것은 작업 폴더의 INDEX.md, eval-03.md뿐)
- 결과: **자동 검수 통과 · 사람 확인 대기** (프로그램 검사 ok, 대조 끝. 남은 것은 평가 03 검수 확인 항목 3(선택)의 사람 확인 하나)

## 프로그램 검수 검사

- 명령: `/Users/yunhunbin/dev/oss-agent/.venv/bin/python <저장소>/bin/hb.py --repo <저장소> review --work verification-preflight --since 067a75d1b534ae49ea79faa76acb818323df1a1e` (앞에서 한 번 실행, 셸 제한 시간 600초)
- rc=0, `verdict`: `ok`
- summary(그대로): "검수 검사 통과. 할 일 4개 모두 완료, 평가 뒤 바뀐 것 없음, 바뀐 파일 11개 모두 허락된 파일 안, 새로 깨진 것 없음"
- record: checks/020-review-full.json (전체 156개 통과, 실패 0, 오류 0, 건너뜀 0, 71초, head 3bf2672), 보고서 logs/review-full-20261029T055905Z-47258.xml
- baseline_record: checks/001-baseline.json
- 바뀐 파일(paths): README.md, bin/hb.py, skills/dev/SKILL.md, skills/eval/SKILL.md, skills/plan/SKILL.md, skills/review/SKILL.md, tests/test_hb_preflight.py, tests/test_hb_preflight_paths.py, tests/test_hb_preflight_reuse.py, tests/test_hb_review.py, tests/test_skills_preflight.py
- 대조 전후 값: HEAD 3bf2672fa0528540ccad271942bd34c7f702a076, `git status --porcelain`은 프로그램이 쓴 `state.json`(M)과 `checks/020-review-full.json`(??) 두 줄. 대조 끝에도 같음.
- 검수 시작 때(프로그램 실행 전) `git status --porcelain`은 빈 값.

## 원래 깨져 있던 테스트

없음(`still_broken` 빈 목록, 바탕 검사 checks/001의 `broken` 빈 목록).

## 테스트 수

| | 전체 | 건너뜀 |
|---|---|---|
| 바탕(checks/001) | 95 | 0 |
| 이번(checks/020) | 156 | 0 |

전체가 61개 늘었다: tests/test_hb_preflight.py 25(할 일 01) + tests/test_skills_preflight.py 18(할 일 02) + tests/test_hb_preflight_paths.py 13(할 일 03) + tests/test_hb_preflight_reuse.py 5(할 일 04). 보고서에서 네 파일의 testcase 61개가 모두 실패·오류·건너뜀 없이 들어 있음을 셈. 줄어든 것, 건너뛴 것 없음. tests/test_hb_review.py 17개도 모두 통과.

## 시작 전 검증의 기록

- 진행표 76·80줄: 할 일 04의 red 전·green 전 `preflight`가 verdict ok, blocked 없음, outcome product `not_run` / environment `ok` / aux `none`. `aux: incomplete`나 `environment: blocked`는 없다.
- 할 일 03은 red·green 전에 preflight를 돌리지 않았다고 진행표 56줄에 적혀 있다(사후로 채우지 않음). 01·02는 preflight가 생기기 전 흐름.
- `product`는 모두 `not_run`이라 완료 증거로 읽을 칸이 없다. 아래 표의 증거는 모두 이번 실행(checks/020)에서 통과한 테스트다.

## 완료 기준표

할 일 테스트는 출력의 `tasks`에 있고(01: 25, 02: 16, 03: 8, 04: 3), 모두 이번 보고서에 통과로 들어 있다. 행동 테스트는 상황마다 임시 git 저장소에 가짜 제품(app.py, pytest 계약 timeout_seconds 120)을 만들고 실제 hb.py를 subprocess로 부른다. green이 필요한 상황은 실제 hb의 baseline → check red → check green으로 만든다. 대조 테스트(출력 `tasks`에는 없지만 이번 실행에서 통과)는 따로 표시했다.

| 기준 | 증거: 테스트 이름과 입증하는 조건 | 이번 실행 | 판정 |
|---|---|---|---|
| C1 pytest를 찾을 수 없으면 stop, environment | `test_c1_pytest_not_importable_by_running_python_stops_as_environment`: hb.py를 실행하는 파이썬 안에서 meta_path로 pytest 가져오기를 막고(PROBE로 막기가 듣는지 먼저 확인) `preflight` → rc≠0, `stop`, `blocked`는 `environment` 하나, 이유에 "pytest", `outcome.environment`=`blocked`. `test_c1_pytest_not_needed_when_runner_is_not_pytest`: 같은 막기 + jest 계약 → `ok` | 통과 | 충족 |
| C2 pytest 아닌 runner의 command[0]이 없으면 stop, environment | `test_c2_missing_command_for_non_pytest_runner_stops_as_environment`: jest 계약 command `hb-preflight-no-such-command-8731` → `stop`, `blocked.environment`에 그 이름, `outcome.environment`=`blocked`. `test_c2_existing_command_for_non_pytest_runner_is_not_blocked`: command가 실행 중인 파이썬 → `ok`. 할 일 03: `test_c2_relative_path_entry_finds_command_in_repo_when_called_from_elsewhere`(PATH 앞에 상대 항목 `node_modules/.bin`, 명령은 저장소에만, 다른 폴더에서 호출 → `ok`), `test_c2_relative_path_entry_does_not_find_command_only_in_calling_folder`(명령이 부른 폴더에만 → `stop`, `blocked`는 `environment` 하나). 대조: 절대 PATH 항목은 그대로 씀, 어디에도 없으면 stop | 통과 | 충족 |
| C3 logs/가 git 제외가 아니면 stop, evidence | `test_c3_logs_not_ignored_stops_as_evidence`: .gitignore에서 `logs/`를 빼고 커밋 → `stop`, `blocked.evidence`에 "logs", environment `ok`. `test_c3_only_log_files_ignored_still_stops_as_evidence`: `*.log`만 제외 → `stop`, evidence | 통과 | 충족 |
| C4 aux가 allowed_files 밖이면 stop, scope + 경로와 "경로 변경 필요"; task 없이 aux면 stop, scope | `test_c4_aux_outside_allowed_files_stops_as_scope_with_path`: `--aux app.py --aux tools/aux_check.py` → `stop`, `blocked`는 `scope` 하나, `tools/aux_check.py`와 "경로 변경 필요", 범위 안 app.py는 없음, `aux`=`incomplete`. `test_c4_aux_without_task_stops_as_scope`: `--aux`만 → `stop`, scope 하나. `test_c4_aux_inside_allowed_files_is_not_blocked` → `ok`. 할 일 03: `tools/*` 범위에서 `tools/../app.py` → scope에 app.py와 "경로 변경 필요"(한 항목만); `tools/../../outside.txt`, 저장소 밖 절대 경로(범위 `*`여도) → scope; `./app.py`, 저장소 안 절대 경로, 실제 경로(realpath) → `ok` | 통과 | 충족 |
| C5 (deadline − 지금) < timeout + margin이면 stop, time; 여유가 있으면 막지 않음 | `test_c5_past_deadline_stops_as_time`: `2000-01-01T00:00:00Z` → `stop`, `blocked.time`, needed 240, remaining<0. `test_c5_far_future_deadline_is_not_blocked`: `2999-01-01T00:00:00Z` → `ok`, remaining>needed. `test_c5_margin_counts_toward_needed_time`: 약 600초 뒤 + `--margin 600` → `stop`(needed 720), `--margin 60` → `ok`(needed 180) | 통과 | 충족 |
| C6 세 칸이 따로: green ok + aux → pass/incomplete; aux가 product를 바꾸지 않음; product pass여도 environment blocked면 stop | `test_c6_green_ok_with_aux_reports_product_pass_and_aux_incomplete`: 실제 green 뒤 `--task 01 --aux app.py` → `ok`, outcome = `{pass, ok, incomplete}`. `test_c6_product_pass_with_environment_blocked_is_still_stop`: 실제 green 뒤 pytest 막기 + 같은 호출 → `stop`, outcome = `{pass, blocked, incomplete}`. `..._product_not_run_without_green_record`, `..._product_not_run_when_task_not_given_even_after_green` | 통과 | 충족 |
| C7 green 뒤 소스가 같으면 same_source, 파일을 바꾸면 changed + 그 파일이 review_paths에 | 커밋 안 한 경우(할 일 01): `test_c7_unchanged_source_after_green_is_same_source`(green 직후 → `same_source`, review_paths 없음), `test_c7_modified_file_after_green_is_changed_with_review_path`(app.py 수정 → `changed`, app.py, product `pass`), `test_c7_new_file_after_green_is_changed_with_review_path`(extra.py 추가 → `changed`, extra.py). 커밋한 경우(할 일 04): `test_c7_new_file_committed_after_green_is_changed_with_review_path`(green 뒤 커밋 → extra.py 새 파일 커밋 → 작업 기록만 커밋, 작업 트리 깨끗 → review_paths가 정확히 green paths + extra.py, 작업 폴더 경로 없음), `test_c7_tracked_file_modified_and_committed_after_green_is_changed_with_review_path`(tests/test_app.py 수정을 커밋 → 정확히 green paths + tests/test_app.py), `test_c7_committed_and_uncommitted_changes_after_green_are_both_review_paths`(커밋한 extra.py + 커밋 안 한 notes.txt → 둘 다). 대조(이번 실행 통과): 커밋·변경 없음 → `same_source`; 기록만 커밋 → green paths만, 기록 없음. 네 행동 테스트 모두 preflight 앞뒤로 state.json 바이트와 checks/, logs/ 목록이 같음도 단언 | 통과 | 충족 (커밋으로 지운·이름 바꾼 파일 경우는 테스트 없음, 평가 03 권장 1) |
| C8 실행 뒤 state.json 내용과 checks/, logs/ 파일 목록이 같음 | `test_c8_preflight_leaves_state_checks_and_logs_untouched`: green 뒤 소스를 바꾸고 ok/stop 섞인 preflight 네 번 → verdict `[ok, stop, ok, stop]`, state.json 바이트와 두 목록 같음. `test_c8_preflight_before_baseline_creates_no_records`: 바탕 검사 전 → 셋 다 없음 그대로, `git status --porcelain` 빈 값. 할 일 04의 다섯 테스트도 `preflight_untouched`로 같은 것을 봄 | 통과 | 충족 |
| C9 dev/plan/eval/review/README 문서 연계 | tests/test_skills_preflight.py(설명서가 정한 문서 내용 테스트, 한 줄 안의 낱말 묶음). dev 7개(baseline 전, 각 check 전, 명령 모양, stop이면 시작하지 않음, 세 칸 따로, preflight 절 안에서 권장을 필수로 올리지 않음, aux 범위 밖이면 멈추고 경로 변경), plan 2개(preflight로 환경 확인, 9번 뒤), eval·review 각 3개(product + 증거, aux incomplete는 통과 아님, environment blocked는 통과 아님), README 1개(파일 목록 줄 빼고 preflight + hb.py/--work). 찾는 줄을 직접 읽어 뜻도 맞음을 봄: dev 28·51·52·54·55·56·58·65·71·74, plan 42(9번은 40줄), eval 28–31, review 55–57, README 45 | 통과 | 충족 |

설명서 예외 넷도 이번 실행에서 통과: `test_bad_deadline_format_stops_without_blocked`(reason "deadline 형식이 틀림", blocked 없음), `test_unknown_task_id_stops_with_same_reason_as_check`("할 일 목록에서 찾을 수 없음: 99"), `test_c8_preflight_before_baseline_creates_no_records`(state.json 없음 → not_run, reuse 없음), `test_several_blocked_kinds_are_all_reported_in_one_stop`(evidence·scope·time 셋이 한 stop에).

## 그 밖의 대조

- 이번에 안 할 것: 보조검증 실행·완료 판정 없음(bin/hb.py 436–450: `--aux`는 `repo_relative`와 `outside_allowed` 비교만, `aux`는 `none`/`incomplete` 둘뿐). 기존 PASS 대체 없음(cmd_preflight는 `Stop`이나 판정 사전만 내고 save_json·run_check를 부르지 않음, dev 59줄 "preflight의 판정은 통과 증거가 아니다"). 섞여 들어간 것 없음.
- 할 일 04의 새 코드(bin/hb.py 99–102, 457–465)는 git 읽기 하나와 review_paths 합치기뿐. 출력 키 모양 그대로.
- 결제, 권한, 개인정보, DB 구조 변경: 해당 없음(spec 38줄, diff에도 없음).
- 기존 테스트 변경: tests/test_hb_review.py `ReviewCase.hb`에 `PYTHONDONTWRITEBYTECODE=1`만 더함(-1/+3, 단언 그대로). 검수 01에서 본 것과 같고(진행표 28–31줄의 감독 지시와 재현 근거, 할 일 01 allowed_files), 이번에도 바뀌지 않음.

## 평가가 넘긴 검수 확인 항목 (eval-03.md 63–66줄)

1. 전체 검사 다시 돌리기 → **확인됨.** 새로 깨진 것 0, 건너뜀 0, 전체 156개(바탕 95 + 61, 평가 02 시점 151 + 할 일 04의 5), 할 일 04의 red 실패 세 개(출력 `tasks.04`) 통과.
2. 기존 C7·C8 테스트가 그대로 통과 → **확인됨.** 이번 보고서에 tests/test_hb_preflight.py 25개, tests/test_hb_preflight_paths.py 13개, tests/test_hb_preflight_reuse.py 5개 모두 통과. `git diff --stat a3e62cf 067a75d -- tests/test_hb_preflight.py tests/test_hb_preflight_paths.py`가 빈 값(rc 0).
3. 이 저장소에서의 커밋 경우(선택) → **이번 실행으로 확인 안 됨.** 검수에서 따로 preflight를 돌리지 않았다(감독 지시). 사람 확인으로 넘긴다.

## 사람 확인 목록

1. (선택, 평가 03 검수 확인 항목 3) 이 검수 기록을 커밋해 작업 트리가 깨끗한 상태에서, 저장소 폴더에서 `/Users/yunhunbin/dev/oss-agent/.venv/bin/python bin/hb.py --repo . preflight --work verification-preflight --task 01`을 돌린다. 기대: rc 0, `verdict` ok, `outcome.product` `pass`, `reuse` `changed`, `review_paths`가 README.md, bin/hb.py, skills/dev/SKILL.md, skills/eval/SKILL.md, skills/plan/SKILL.md, skills/review/SKILL.md, tests/test_hb_preflight.py, tests/test_hb_preflight_paths.py, tests/test_hb_preflight_reuse.py, tests/test_hb_review.py, tests/test_skills_preflight.py 11개와 정확히 같고 `.harness/artifacts/work/verification-preflight/`로 시작하는 경로가 없음. 실행 앞뒤로 state.json의 sha256과 checks/, logs/ 파일 목록이 같음. 선택 항목이라 하지 않기로 하면 그 결정을 이 기록에 적는다.

## 테스트로 확인된 것과 안 된 것

- 확인됨(이번 실행의 행동 테스트): C1–C8, 설명서 예외 넷, 할 일 03의 --aux 정규화·저장소 탈출 거부와 PATH 상대 항목 풀기, 할 일 04의 green 뒤 커밋으로 더한 새 파일·커밋으로 고친 추적 파일·커밋 변경과 커밋 안 한 파일이 함께 있는 경우, 커밋에 작업 기록만 있을 때 기록이 빠지는 것, 이 모든 preflight가 state.json·checks/·logs/를 고치지 않는 것, 기존 네 명령의 동작(전체 156개).
- 확인됨(문서 내용 테스트): C9의 문장들(한 줄 안의 낱말 묶음). 문장의 뜻은 검수자가 직접 읽어 봄.
- 허술함: 커밋으로 지운 파일·이름 바꾼 파일의 review_paths(평가 03 권장 1), C7 수정 경우의 합집합 구분(평가 01 권장 7), 빈 PATH 항목, 시간대 없는 deadline, `--margin` 음수.
- 안 됨: red.head 커밋이 사라진 경우(평가 03 권장 2), green 검사 중 커밋(흐름 밖), `product: fail`(실제 흐름에서 만들 수 없음), 실제 저장소에서 run_check가 옛 .pyc로 잘못 통과할 수 있는 경우(설명서 범위 밖), 이 저장소 자체에서의 커밋 경우 preflight(사람 확인 1), dev SKILL 57줄 설명이 할 일 04 뒤 동작보다 덜 적힌 것(평가 03 권장 3, C9가 요구하지 않음).
- 평가 03 권장 1–3은 꼭 고칠 것으로 올리지 않았다.

## PR 본문 초안

```
## 무엇을

`hb.py preflight` 명령을 더하고 dev/plan/eval/review 문서와 README에 연계했습니다.

- preflight는 검사를 돌리지 않고 기록(state.json, checks/, logs/)을 만들거나 고치지 않습니다.
- 돌려도 완료 증거가 안 되는 경우를 미리 막습니다: environment(pytest/검사 명령 없음), evidence(logs/가 git 제외 아님), scope(보조검증 경로가 할 일 범위 밖이거나 저장소 밖), time(deadline까지 남은 시간 < 검사 제한 시간 + margin).
- 결과를 `product` / `environment` / `aux` 세 칸으로 따로 내고, green 기록 뒤 소스가 바뀌었는지(`reuse`, `review_paths`)를 알려 줍니다. `review_paths`에는 green 뒤 커밋으로 바뀐 파일도 들어갑니다(작업 폴더 기록은 뺌).
- `--aux` 경로는 저장소 기준으로 정리한 뒤 범위를 보고, 비pytest 명령을 찾을 때 PATH의 상대 항목은 저장소 기준으로 풉니다.
- 기존 baseline/check/done/review 판정은 그대로입니다(baseline의 logs 검사는 함수로 떼어 내 같이 씀).

## 검증

- 전체 검사 156개 통과, 건너뜀 0, 새로 깨진 것 0 (바탕 95개 + preflight 25 + 경로 13 + 재사용 5 + 문서 18).
- 완료 기준 C1–C9 모두 검수 실행에서 통과한 테스트로 충족.
- 평가 01 검수로 → 검수 01 통과 → 리뷰 지적으로 할 일 03 → 평가 02 개발로(C7 커밋 경우) → 할 일 04 → 평가 03 검수로 → 검수 02 자동 검수 통과(선택 사람 확인 1건).

## 참고

- tests/test_hb_review.py의 `ReviewCase.hb`에 `PYTHONDONTWRITEBYTECODE=1`만 더했습니다. 크기가 같은 변경이 같은 초에 쓰이면 옛 .pyc 때문에 깨진 동작이 가려지는 것을 재현으로 확인한 뒤 한 최소 보정이고, 단언은 바꾸지 않았습니다.
- 남은 권장(다음 작업 후보): 커밋으로 지운·이름 바꾼 파일 테스트, red head 커밋이 사라진 경우 처리, dev 문서의 review_paths 설명 보강, 실제 저장소에서 run_check의 옛 .pyc 문제, `--margin` 음수 막기, 문서 다듬기.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```
