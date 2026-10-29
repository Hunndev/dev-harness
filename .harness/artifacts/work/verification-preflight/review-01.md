# 검수 01: verification-preflight

- 날짜: 2026-10-29
- 도구: Claude Code (claude-opus-5-5, high), 새 컨텍스트 서브에이전트
- 자동 메모: 이 세션의 맥락에 앞 세션의 자동 메모가 보이지 않음
- 시작 커밋(state.json `baseline.head`): dae8b745efed1afcb64ca8b20bc52dc82a28019c
- 평가 대상 커밋(eval-01.md 7줄): 09281d420cf808cfdbc7801547215e6399353646
- 검수 대상 커밋(`git rev-parse HEAD`): c88acf7b982ed429cfcaf3a1dac99566d5b13c74
- 결과: **검수 통과** (프로그램 검사 ok, 대조 끝, 사람 확인 항목 없음)

## 프로그램 검수 검사

- 명령: `/Users/yunhunbin/dev/oss-agent/.venv/bin/python bin/hb.py --repo <저장소> review --work verification-preflight --since 09281d420cf808cfdbc7801547215e6399353646` (앞에서 한 번 실행)
- rc=0, `verdict`: `ok`
- summary(그대로): "검수 검사 통과. 할 일 2개 모두 완료, 평가 뒤 바뀐 것 없음, 바뀐 파일 9개 모두 허락된 파일 안, 새로 깨진 것 없음"
- record: checks/013-review-full.json (전체 138개 통과, 실패 0, 오류 0, 건너뜀 0, 63초), 보고서 logs/review-full-20261029T050620Z-89476.xml
- baseline_record: checks/001-baseline.json
- 바뀐 파일(paths): README.md, bin/hb.py, skills/dev/SKILL.md, skills/eval/SKILL.md, skills/plan/SKILL.md, skills/review/SKILL.md, tests/test_hb_preflight.py, tests/test_hb_review.py, tests/test_skills_preflight.py
- 대조 전후 값: HEAD c88acf7b982ed429cfcaf3a1dac99566d5b13c74, `git status --porcelain`은 프로그램이 쓴 `state.json`(M)과 `checks/013-review-full.json`(??) 두 줄. 대조 끝에도 같음.

## 원래 깨져 있던 테스트

없음(`still_broken` 빈 목록, 바탕 검사 `broken` 빈 목록).

## 테스트 수

| | 전체 | 건너뜀 |
|---|---|---|
| 바탕(checks/001) | 95 | 0 |
| 이번(checks/013) | 138 | 0 |

전체가 43개 늘었다: tests/test_hb_preflight.py 25개(할 일 01) + tests/test_skills_preflight.py 18개(할 일 02, 그중 기준 증거로 묶인 것 16개와 기존 규칙 유지 테스트 2개). 줄어든 것, 건너뛴 것 없음.

## 시작 전 검증의 기록

이 작업의 개발은 preflight가 생기기 전 흐름이라 진행표와 이번 출력에 `preflight`의 `outcome`이 없다. 완료 증거로는 쓰지 않았고, 아래 표의 증거는 모두 이번 실행(checks/013)에서 통과한 테스트다.

## 완료 기준표

할 일 테스트는 출력의 `tasks`에 있고, 모두 이번 실행 보고서에 실패·오류·건너뜀 없이 들어 있다. 행동 테스트(tests/test_hb_preflight.py)는 상황마다 임시 git 저장소에 가짜 제품(app.py, pytest 계약 timeout_seconds 120, 할 일 01 allowed_files app.py·tests/test_new.py)을 만들고 실제 hb.py를 subprocess로 부른다. green이 필요한 상황은 실제 hb의 baseline → check red → check green으로 만든다.

| 기준 | 증거: 테스트 이름과 입증하는 조건 | 이번 실행 | 판정 |
|---|---|---|---|
| C1 pytest를 찾을 수 없으면 stop, environment | `test_c1_pytest_not_importable_by_running_python_stops_as_environment`: hb.py를 실행하는 파이썬 안에서 meta_path로 pytest 가져오기를 막고(막기가 듣는지 PROBE로 먼저 확인) `preflight` → rc≠0, `stop`, `blocked`는 `environment` 하나이고 이유에 "pytest", `outcome.environment`=`blocked`. `test_c1_pytest_not_needed_when_runner_is_not_pytest`: 같은 막기 + jest 계약 → `ok`, environment 막힘 없음 | 통과 | 충족 |
| C2 pytest 아닌 runner의 command[0]이 없으면 stop, environment | `test_c2_missing_command_for_non_pytest_runner_stops_as_environment`: jest 계약 command `hb-preflight-no-such-command-8731` → `stop`, `blocked.environment`에 그 이름, `outcome.environment`=`blocked`. `test_c2_existing_command_for_non_pytest_runner_is_not_blocked`: command가 실행 중인 파이썬 → `ok`, `blocked` 빈 사전 | 통과 | 충족 |
| C3 logs/가 git 제외가 아니면 stop, evidence | `test_c3_logs_not_ignored_stops_as_evidence`: .gitignore에서 `logs/`를 빼고 커밋 → `stop`, `blocked.evidence`에 "logs", environment는 `ok`. `test_c3_only_log_files_ignored_still_stops_as_evidence`: `*.log`만 제외 → `stop`, evidence | 통과 | 충족 |
| C4 aux가 allowed_files 밖이면 stop, scope + 경로와 "경로 변경 필요"; task 없이 aux면 stop, scope | `test_c4_aux_outside_allowed_files_stops_as_scope_with_path`: `--task 01 --aux app.py --aux tools/aux_check.py` → `stop`, `blocked`는 `scope` 하나, 그 안에 `tools/aux_check.py`와 "경로 변경 필요", 범위 안인 app.py는 없음, `aux`=`incomplete`. `test_c4_aux_without_task_stops_as_scope`: `--aux app.py`만 → `stop`, `blocked`는 `scope` 하나. `test_c4_aux_inside_allowed_files_is_not_blocked`: 범위 안 두 경로 → `ok` | 통과 | 충족 |
| C5 (deadline − 지금) < timeout + margin이면 stop, time; 여유가 있으면 막지 않음 | `test_c5_past_deadline_stops_as_time`: `2000-01-01T00:00:00Z` → `stop`, `blocked.time`, needed 240(=120+120), remaining<0. `test_c5_far_future_deadline_is_not_blocked`: `2999-01-01T00:00:00Z` → `ok`, time 막힘 없음, remaining>needed. `test_c5_margin_counts_toward_needed_time`: 약 600초 뒤 + `--margin 600` → `stop`(needed 720), `--margin 60` → `ok`(needed 180) | 통과 | 충족 |
| C6 세 칸이 따로: green ok + aux → pass/incomplete; aux가 product를 바꾸지 않음; product pass여도 environment blocked면 stop | `test_c6_green_ok_with_aux_reports_product_pass_and_aux_incomplete`: 실제 green 뒤 `--task 01 --aux app.py` → `ok`, outcome = `{product: pass, environment: ok, aux: incomplete}`. `test_c6_product_pass_with_environment_blocked_is_still_stop`: 실제 green 뒤 pytest를 막고 같은 호출 → `stop`, outcome = `{pass, blocked, incomplete}`. `test_c6_product_not_run_without_green_record`(red까지만 → `not_run`), `test_c6_product_not_run_when_task_not_given_even_after_green`(task 없음 → `not_run`) | 통과 | 충족 |
| C7 green 뒤 소스가 같으면 same_source, 파일을 바꾸면 changed + 그 파일이 review_paths에 | `test_c7_unchanged_source_after_green_is_same_source`: green 직후 → `reuse`=`same_source`, review_paths 없음. `test_c7_modified_file_after_green_is_changed_with_review_path`: green 뒤 app.py에 주석 한 줄 → `changed`, review_paths에 app.py, product는 `pass` 그대로. `test_c7_new_file_after_green_is_changed_with_review_path`: green 뒤 extra.py 추가 → `changed`, review_paths에 extra.py | 통과 | 충족 (수정 테스트의 app.py는 green paths에도 있어 합집합과 "지금 바뀐 경로"를 가리지 못함. 새 파일 테스트가 그 몫을 함. 평가 권장 7) |
| C8 실행 뒤 state.json 내용과 checks/, logs/ 파일 목록이 같음 | `test_c8_preflight_leaves_state_checks_and_logs_untouched`: green 뒤 소스를 바꾸고 state.json 바이트와 두 폴더 목록을 저장 → ok/stop 섞인 preflight 네 번(aux, 범위 밖 aux + 지난 deadline, 먼 deadline, pytest 막기) → verdict `[ok, stop, ok, stop]`, 저장한 값과 같음. `test_c8_preflight_before_baseline_creates_no_records`: 바탕 검사 전 → state.json·checks/·logs/ 모두 없음 그대로, `git status --porcelain` 빈 값 | 통과 | 충족 |
| C9 dev/plan/eval/review/README 문서 연계 | tests/test_skills_preflight.py(문서 내용 테스트, 설명서가 정한 증거 방식). 한 줄 안에 핵심 낱말이 함께 있는지 본다. dev: `test_dev_runs_preflight_before_baseline`(preflight + baseline + 전에), `..._before_each_check`(preflight + check + 전에), `..._preflight_command_documented`(hb.py + preflight + --work), `..._preflight_stop_does_not_start_check`(stop 조건 뒤 "시작하지 않"류), `..._reports_three_outcomes_separately`(product·environment·aux + 따로), `..._does_not_promote_recommendation_with_preflight`(preflight 절 안에서 권장 + 필수 + 올리지 않), `..._aux_out_of_scope_stops_and_reports_path_change`. plan: `test_plan_checks_environment_with_preflight`, `test_plan_preflight_comes_after_step_9`(9번 줄 뒤). eval·review 각각: `test_product_only_is_completion_evidence`(product + 증거), `test_aux_incomplete_is_not_pass`, `test_environment_blocked_is_not_pass`. README: `test_readme_describes_preflight_command`(파일 목록 줄을 빼고 preflight + hb.py/--work). 테스트가 찾는 줄을 직접 읽어 뜻도 맞음을 봄: dev 51·52·54·56·58·65·71·74, plan 42, eval 28–31, review 55–57, README 45 | 통과 | 충족 |

설명서 예외 넷도 이번 실행에서 통과: `test_bad_deadline_format_stops_without_blocked`(reason "deadline 형식이 틀림", blocked 없음), `test_unknown_task_id_stops_with_same_reason_as_check`("할 일 목록에서 찾을 수 없음: 99"), `test_c8_preflight_before_baseline_creates_no_records`(state.json 없음 → not_run, reuse 없음), `test_several_blocked_kinds_are_all_reported_in_one_stop`(evidence·scope·time 셋이 한 stop에).

## 그 밖의 대조

- 이번에 안 할 것: 보조검증 실행·완료 판정 없음(`--aux`는 `outside_allowed` 비교만, `aux`는 `none`/`incomplete` 둘뿐, hb.py 415–424). 기존 PASS 대체 없음(bin/hb.py diff는 preflight 추가, `logs_not_ignored` 떼어 내기, 서브파서·실행 표 한 줄뿐이고 check/done/review 판정 코드는 그대로. dev 59줄 "preflight의 판정은 통과 증거가 아니다"). 섞여 들어간 것 없음.
- 결제, 권한, 개인정보, DB 구조 변경: 해당 없음(spec 38줄, diff에도 없음).
- 기존 테스트 변경: tests/test_hb_review.py `ReviewCase.hb`에 `PYTHONDONTWRITEBYTECODE=1`만 더함(-1/+3, 단언·본문 그대로). spec 35줄 "기존 테스트를 고치지 않는다"와 글자로는 어긋나지만, 감독 지시 원문과 재현 근거가 INDEX 28–29줄, 범위가 tasks/01 14–15줄과 할 일 01 allowed_files에 있고, red부터 다시 받았다(checks/006). 프로그램도 허락된 파일 안으로 판정. 평가 권장 2(spec 제약 줄 정리)는 권장으로 둔다.

## 평가가 넘긴 검수 확인 항목

1. 전체 검사 다시 돌리기 → **확인됨.** 새로 깨진 것 0, 전체 138개(95 + 25 + 18), 건너뜀 0, tests/test_hb_preflight.py 25개 모두 건너뛰지 않고 통과(보고서 skipped=0, 실패·오류 0).
2. `tests.test_hb_review.ReviewCase::test_stops_when_a_commit_after_done_breaks_an_old_test` → **확인됨.** 이번 실행 보고서에 실패·건너뜀 없이 들어 있음(통과).
3. 바탕 검사 뒤 바뀐 파일이 허락된 파일 안인지 → **확인됨.** 프로그램 summary "바뀐 파일 9개 모두 허락된 파일 안", paths에 tests/test_hb_review.py 포함.

## 사람 확인 목록

없음.

## 테스트로 확인된 것과 안 된 것

- 확인됨(이번 실행의 행동 테스트): C1–C8, 설명서 예외 넷, baseline의 logs 검사(기존 test_hb.py·test_hb_jest.py, 함수로 떼어 낸 뒤에도 통과), 보정한 review fixture, 기존 네 명령의 동작(전체 138개).
- 확인됨(문서 내용 테스트): C9의 문장들(한 줄 안의 낱말 묶음). 문장의 뜻은 검수자가 직접 읽어 봄.
- 허술함: C7 수정 경우(평가 권장 7), 상대 경로 명령(`./gradlew` 꼴)의 C2, 시간대 없음·다른 시간대의 deadline, `--margin` 음수(평가 권장 6).
- 안 됨: `product: fail`(실제 흐름에서 만들 수 없음), 실제 저장소에서 hb `run_check`가 옛 .pyc로 잘못 통과할 수 있는 경우(평가 권장 1, 설명서 범위 밖, 다음 작업 후보), 문서 문장이 지휘에게 실제로 그렇게 읽히는지.
- 평가 권장 1–7은 꼭 고칠 것으로 올리지 않았다.

## PR 본문 초안

```
## 무엇을

`hb.py preflight` 명령을 더하고 dev/plan/eval/review 문서와 README에 연계했습니다.

- preflight는 검사를 돌리지 않고 기록(state.json, checks/, logs/)을 만들거나 고치지 않습니다.
- 돌려도 완료 증거가 안 되는 경우를 미리 막습니다: environment(pytest/검사 명령 없음), evidence(logs/가 git 제외 아님), scope(보조검증 경로가 할 일 범위 밖), time(deadline까지 남은 시간 < 검사 제한 시간 + margin).
- 결과를 `product` / `environment` / `aux` 세 칸으로 따로 내고, green 기록 뒤 소스가 바뀌었는지(`reuse`, `review_paths`)를 알려 줍니다.
- 기존 baseline/check/done/review 판정은 그대로입니다(baseline의 logs 검사는 함수로 떼어 내 같이 씀).

## 검증

- 전체 검사 138개 통과, 건너뜀 0, 새로 깨진 것 0 (바탕 95개 + preflight 25개 + 문서 18개).
- 완료 기준 C1–C9 모두 이번 검수 실행에서 통과한 테스트로 충족.
- 평가 01: 검수로. 검수 01: 검수 통과.

## 참고

- tests/test_hb_review.py의 `ReviewCase.hb`에 `PYTHONDONTWRITEBYTECODE=1`만 더했습니다. 크기가 같은 변경이 같은 초에 쓰이면 옛 .pyc 때문에 깨진 동작이 가려지는 것을 재현으로 확인한 뒤 한 최소 보정이고, 단언은 바꾸지 않았습니다.
- 남은 권장(다음 작업 후보): 실제 저장소에서 run_check의 옛 .pyc 문제, spec 제약 줄 정리, green 전 margin 안내, `--margin` 음수 막기, C7 수정 테스트 보강, 문서 다듬기.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```
