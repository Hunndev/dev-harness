# verification-preflight 진행표

상태: 확정
승인 날짜: 2026-10-29
승인 글(approved-task-v2.md 그대로): "승인된 하네스 자체개발 검사 계약 추가부터 재개해 재발방지3개 실제구현·테스트·Claude/Codex리뷰·커밋까지 완료. 이전작업재탐색/재승인반복금지." / "계획 승인 재요청 없이 본 범위 진행."
추가 지시(/hb:plan 인자): "세 재발방지 전체를 한 응집 기능+행동회귀+skills 연계로 승인범위 내 계획하라. 재승인 불필요. bootstrap 완료 commit 재사용. dev 완료 후 감독이 새 eval/review세션 시작하므로 여기서 자체 eval 금지. 범위 축소 불가, 시간 부족시 정확한 checkpoint 보존."

bootstrap 커밋: 0a246bb (.harness/README.md, .harness/docs/checks.json, .gitignore logs/)
검사용 파이썬: /Users/yunhunbin/dev/oss-agent/.venv/bin/python (3.12.12, pytest 9.0.3)

## 짝 맞추기
| 기준 | 할 일 |
|---|---|
| C1–C8 | 01 |
| C9 | 02 |
| C7 (green 뒤 커밋으로 바뀐 파일, 평가 02) | 04 |

## 바탕 검사
- 2026-10-29 03:44:39Z–03:45:35Z, `/Users/yunhunbin/dev/oss-agent/.venv/bin/python bin/hb.py --repo . baseline --work verification-preflight --tool claude-code`, rc=0
- summary: "바탕 검사 끝. 테스트 95개, 원래 깨져 있던 것 0건" (record checks/001-baseline.json)

## 할 일별 진행
- 01: 4번 구현 중. 테스트 동결(tests/test_hb_preflight.py sha256 c842bda486f4f572f19a291e7558d88ccbdcd096c2dbebe1d5bff38bf25c25cf). 테스트 재작성 1회, 지적 반영 0회
  - red 2: hb_rc=0, "실패 확인 됨. 본문에서 실패한 테스트 25개" (checks/003-01-red.json)
  - 테스트 검토 2(변경분): 지문 전후 같음(logs/01-pre-test-review2.log = logs/01-post-test-review2.log). 꼭 고칠 것 없음, 권장 없음.
  - 구현(bin/hb.py만). 구현자의 focused 실행: tests/test_hb_preflight.py 25 passed. C7 review_paths는 지휘 정정대로 합집합(지금 바뀐 경로 ∪ green paths).
  - green 1: hb_rc=1, verdict stop, "새로 깨진 테스트가 있음", new_broken=["tests.test_hb_review.ReviewCase::test_stops_when_a_commit_after_done_breaks_an_old_test"] (checks/005-01-green-full.json). 전체 120개 중 이 1건 실패, 할 일 테스트 25개 통과.
    - 실패 내용: review가 rc=0을 냄(새로 깨진 테스트를 못 봄). tests/test_hb_review.py:249.
    - 원인 확정(scratch 재현, /Users/yunhunbin/.hermes/profiles/developer-buccl/cache/scratch/hb-pyc-repro/repro.py, 기본 환경 venv python, repro_rc=0): "with_bytecode: first_rc=0 second_rc=0 same_size=True pycache=True" / "no_bytecode: first_rc=0 second_rc=1 same_size=True pycache=False". 크기가 같은 변경 + 같은 초 수정 시각이면 옛 .pyc 때문에 깨진 동작이 가려진다.
    - 처리(감독 지시 원문: "기존 regression fixture의 pycache 문제를 추정으로 확정하지 말고 scratch 재현으로 입증 후 assertion/guard 약화 없이 최소 fixture 보정은 승인된 완료 범위. 필요 task allowed_files에 정확한 tests/test_hb_review.py 보정범위 기록하되 새 제품범위 금지."): 할 일 01 allowed_files에 tests/test_hb_review.py 추가. 보정 범위는 ReviewCase.hb의 subprocess 환경에 PYTHONDONTWRITEBYTECODE=1만 더하는 것(tasks/01-preflight.md). 실패 원본 checks/005-01-green-full.json, logs/01-green-full-20261029T041047Z-73433.* 보존.
    - fixture 보정(구현자, native Edit): ReviewCase.hb에 env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1") 추가, 주석 1줄. -1/+3.
  - green 2: hb_rc=1, verdict stop, "실패 확인 뒤에 테스트가 바뀜. 테스트를 고치려면 승인받고 실패 확인부터 다시". 지문은 test_globs(tests/*) 전체를 보므로 fixture 변경도 테스트 변경이다. 관문은 그대로 두고 테스트 정정 1회째(한도 2).
    - 철회된 시도: 진입점(서브파서 6줄)만 떼어 red를 만들려 했으나 감독이 거부("기능진입점만 빼는 synthetic RED는 안 됨"). 6줄은 native Edit로 원래 자리에 되돌림. 되돌린 뒤 diff는 green 1 때와 같은 99+/6-, 같은 diff 줄(138–143). 이 상태로 red를 돌리지 않음.
    - 재검증 절차(감독 지시): 실제 구현을 scratch에 보존(/Users/yunhunbin/.hermes/profiles/developer-buccl/cache/scratch/hb-preimpl/hb.impl.py, sha256 43f131ef0ced0e4ac95928b4c195f6bb00b47e3351623ef8b21a21bf3e225e6f, blob 5f34cc358b689e618b5da92a718aba23060825b6). HEAD의 bin/hb.py 바이트(hb.head.py, sha256 1b76fce9eddcfc57c8448bc4211172a8c86fb328b68c4ffa68d5da674d06fbbb, blob 0b0685c1)를 native Write로 작업본에 되돌린다. 그 상태에서 보정 fixture와 신규 25개 테스트로 공식 red를 다시 받고, 변경분 테스트 검토를 한 뒤, 보존한 구현을 native Write로 되돌려 green을 받는다. 이것은 처음부터 테스트를 먼저 썼다고 새로 주장하는 것이 아니다. fixture를 바꾼 뒤 기존의 실제 구현 전 코드에서 다시 검증한 것이다.
    - 보존한 원문: red 1(checks/002), red 2(checks/003, 25개 본문 실패), green 1(checks/005, 전체 120개 중 119 통과 / 1 실패).
  - red 3(HEAD 바이트로 되돌린 상태, git diff --quiet HEAD -- bin/hb.py rc=0): hb_rc=0, "실패 확인 됨. 본문에서 실패한 테스트 25개" (checks/006-01-red.json). 테스트 정정 1회.
  - 테스트 검토 3(fixture 변경분, logs/01-fixture-diff.log): 지문 전후 같음(logs/01-pre-test-review3.log = logs/01-post-test-review3.log). 꼭 고칠 것 없음.
    - 남은 권장(진행 안 막음, 범위 밖): bin/hb.py run_check의 pytest 실행도 실제 저장소에서 같은 크기 + 같은 초 수정이면 옛 .pyc로 잘못 통과할 수 있음. 다음 작업 후보.
  - 보존한 구현을 native Write로 되돌림: bin/hb.py sha256 43f131ef0ced0e4ac95928b4c195f6bb00b47e3351623ef8b21a21bf3e225e6f (보존본과 같음, 677줄).
  - green 3: hb_rc=0, "통과 확인 됨. 새로 깨진 것 없음", paths bin/hb.py, tests/test_hb_preflight.py, tests/test_hb_review.py (checks/007-01-green-task.json 25개 통과, checks/008-01-green-full.json 120개 통과, 건너뜀 0).
  - 구현 검토: 지문 전후 같음(logs/01-pre-impl-review.log = logs/01-post-impl-review.log). 꼭 고칠 것 없음. C7 대조: review_paths = sorted(set(paths) | set(green["paths"])), 즉 합집합. "app.py 변경 + x.py 추가"에서 app.py가 포함됨을 검토자가 코드로 따라가 확인.
    - 남은 권장(진행 안 막음): green 뒤 커밋에서 새로 들어온 파일은 review_paths에 안 나옴(지휘만 커밋하는 규칙이라 C7 범위 밖); 합집합이라 green 뒤 안 바뀐 파일도 review_paths에 들어가므로 할 일 02 문서에 그 뜻을 적을 것.
  - 커밋 1번(프로그램이 돌리지 않는 검증 명령): .harness/README.md에 lint/build 등 별도 검증 명령 없음. 돌릴 것 없음.
  - 할 일 01 결과: "통과 확인 됨. 새로 깨진 것 없음". 테스트 정정 1회(fixture), 테스트 재작성 1회, 지적 반영 0회.
    - 앞의 추정(재현 전 기록): 그 테스트는 app.py의 "return a + b"를 "return a - b"로 바꿔 크기가 같다. 가짜 저장소에 바이트코드 막기(PYTHONDONTWRITEBYTECODE 등)가 없어, 앞 green이 만든 __pycache__와 수정 시각이 같은 초면 파이썬이 옛 .pyc를 쓴다(.pyc 검증은 수정 시각 초 + 크기). 이번 diff는 cmd_review, run_check, snapshot을 바꾸지 않았다(cmd_baseline의 logs 검사만 함수로 옮김).
  - red 1: rc=0, "실패 확인 됨. 본문에서 실패한 테스트 25개" (checks/002-01-red.json)
  - 테스트 검토 1: 지문 전후 같음(logs/01-pre-test-review.log = logs/01-post-test-review.log). 꼭 고칠 것 1건: state.json 없음 + --task일 때 product not_run / reuse 없음을 단언하지 않음.
  - 남은 권장(진행 안 막음): C7 경로 목록이 같고 내용만 바뀌면 green 기록만으로 파일을 가릴 수 없어 review_paths는 "바뀐 파일을 포함"만 확인; C6 product: fail은 실제 흐름에서 만들 수 없어 행동 테스트 없음; C4 280줄 assertNotIn("app.py")가 안내 문구를 막을 수 있음.
- 01: 완료. 커밋 d9993b4 (done hb_rc=0 "완료로 표시함. 작업 폴더의 기록을 올린 뒤 커밋하면 됨")
- 03: 완료. 검수 01 뒤 리뷰에서 더함
  - 구현(bin/hb.py만, native Edit): repo_relative로 --aux 정리와 저장소 밖 거부, 비pytest 명령 찾기에서 PATH 각 항목(빈 항목 포함)을 ctx.repo 기준으로 풂. 구현자의 pytest는 권한 거부로 돌지 않음(결과 없음).
  - green 1: hb_rc=0, "통과 확인 됨. 새로 깨진 것 없음" (checks/015-03-green-task.json, checks/016-03-green-full.json 전체 151개 통과, 건너뜀 0).
  - 구현 검토: 지문 전후 같음(logs/03-pre-impl-review.log = logs/03-post-impl-review.log). 꼭 고칠 것 없음. 빈 PATH 항목 대조: 버리지 않고 os.path.join(ctx.repo, "") = ctx.repo + "/"로 풀며 run_check(cwd=ctx.repo)와 같은 곳을 찾음.
    - 남은 권장(진행 안 막음): --repo 없이 git toplevel이 실제 경로이고 --aux가 링크 경로(/tmp/...)면 허락된 파일인데도 저장소 밖으로 막힘(잘못 막는 쪽); 빈 PATH 항목을 확인하는 테스트 없음(C2 문언과 할 일 본문 기대는 상대 항목까지).
  - 커밋 1번(프로그램이 돌리지 않는 검증 명령): 없음. 테스트 재작성 0회, 지적 반영 0회.(감독 지시, codex-v7-findings-owner.md). tasks/03-preflight-paths.md
  - red 1: hb_rc=0, "실패 확인 됨. 본문에서 실패한 테스트 8개" (checks/014-03-red.json). 대조 테스트 5개 통과. 테스트 동결 tests/test_hb_preflight_paths.py sha256 f36f6ae15ffb99bb21b651b42831986fc3340e084cbbc415860ca872c4b587d3.
  - 테스트 검토 1: 지문 전후 같음(logs/03-pre-test-review.log = logs/03-post-test-review.log). 꼭 고칠 것 없음. 남은 권장: 저장소 탈출 세 테스트에 "경로 변경 필요" 단언 없음; 링크를 푼 절대 경로 테스트에 outcome.aux 단언 없음. 테스트 재작성 0회, 지적 반영 0회.
  - 출처: Codex native exec review(gpt-6-astra medium, base f4f61ab..72c79ed, rc0) P2 2건과 Claude 일반 review(/code-review high, 같은 범위. 이 세션의 스킬 목록에 /review가 없어 /code-review로 실행) #4.
  - 고칠 것: --aux 경로 정규화와 저장소 탈출 거부(C4), 상대 PATH 항목을 ctx.repo 기준으로 풀기(C2).
  - 할 일 03에 넣지 않은 일반 review 지적(**통과 판정이 아님. 비차단 여부 미판정**). 감독 판정 원문(review-v7-adjudication.md): "일반review 10건의 제외는 모두 통과 판정으로 바꾸지 마세요. 현재 task03 최소2건은 계속하되 새 eval에서 #1/#2/#3/#5/#6/#7이 승인된 spec의 정확한 정의상 비차단인지 독립 확인을 맡기고 근거 남기세요(새 설계/추가 범위 요구 금지). … 특히 #5 커밋 후 변경 파일 누락이 C7 계약 위반인지 합집합 정의 대비 분리. 기존 판정/gate 변경금지. 일반리뷰 zero-findings로 보고하지 않습니다." → eval-02가 #1/#2/#3/#5/#6/#7을 spec 정의(C5, C6, C7)에 대해 독립 판정한다. #5는 C7 문언("파일을 바꾸면 changed와 그 파일이 review_paths에 나온다") 대비 위반인지, 합집합 정의(구현·문서) 대비인지를 나눠 판정. 지휘의 앞선 분류는 근거가 아님: 일반 #1 실패한 green 뒤에도 이전 green 기록으로 product: pass, #2·#10 product: fail 갈래가 나올 수 없음(C6 정의 "green 기록이 ok"대로), #3 green이 run_check를 두 번 돌려 필요한 시간이 최대 2배(평가 권장 3), #5 green 뒤 커밋으로 들어온 파일이 review_paths에 없음(개발 권장), #6 커밋 뒤에는 늘 reuse: changed(평가 권장 4), #7 음수 --margin(평가 권장 6), #8 run_check와 명령 결정 공용화·xcresulttool 미확인(새 설계), #9 Ctx/ctx.task의 Stop은 blocked/outcome 모양이 없음(새 설계).
- 02: 완료(done hb_rc=0 "완료로 표시함. 작업 폴더의 기록을 올린 뒤 커밋하면 됨"). 테스트 동결(tests/test_skills_preflight.py sha256 e7eeecb50c2dcb429e773dcf33abd3ccced17a0d6d3b38a8b37ac4c14e6e4fb1). 테스트 재작성 1회, 지적 반영 0회
  - red 2: hb_rc=0, "실패 확인 됨. 본문에서 실패한 테스트 16개" (checks/010-02-red.json)
  - 테스트 검토 2(변경분): 지문 전후 같음(logs/02-pre-test-review2.log = logs/02-post-test-review2.log). 꼭 고칠 것 없음, 권장 없음.
  - 구현(README.md, skills 4개, native Edit). 구현자의 focused 실행: tests/test_skills_preflight.py 18 passed.
  - green 1: hb_rc=0, "통과 확인 됨. 새로 깨진 것 없음" (checks/011-02-green-task.json, checks/012-02-green-full.json 전체 138개 통과).
  - 구현 검토: 지문 전후 같음(logs/02-pre-impl-review.log = logs/02-post-impl-review.log). 꼭 고칠 것 없음.
    - 남은 권장(진행 안 막음): dev 58줄 "preflight가 내는 지적" 표현을 검토의 권장으로 좁히기; plan 44줄을 preflight ok/stop 조건과 합치고 파이썬 선택 안내 더하기; eval/review "product만"을 product: pass + reuse가 changed 아님으로 밝히기; dev에 blocked 없는 stop이면 reason을 적는다 더하기; --deadline 형식(UTC ISO 8601) 적기.
  - 커밋 1번(프로그램이 돌리지 않는 검증 명령): .harness/README.md에 별도 검증 명령 없음. 돌릴 것 없음.
  - 할 일 02 결과: "통과 확인 됨. 새로 깨진 것 없음". 테스트 재작성 1회, 지적 반영 0회.
  - red 1: hb_rc=0, "실패 확인 됨. 본문에서 실패한 테스트 16개" (checks/009-02-red.json). 기존 규칙 유지 테스트 2개는 통과.
  - 테스트 검토 1: 지문 전후 같음(logs/02-pre-test-review.log = logs/02-post-test-review.log). 꼭 고칠 것 2건: (1) stop 조건 없이 "돌리지 않"만으로 통과, (2) README 테스트가 파일 목록 줄로 통과.
  - 남은 권장(진행 안 막음): eval/review "product만"의 "만" 미확인; 세 칸 "보고" 미확인; "각 check" 미확인; 권장 규칙 절 제한이 과함; dev 88줄 뒷문장 보호 빠짐; eval 17줄 "테스트를 돌리지 않는다" 보호 없음.
- 04: 대기. 평가 02에서 더함. green 뒤 커밋으로 바뀐 파일이 review_paths에 없음(C7, 일반 review #5 (a)). tasks/04-preflight-reuse-commits.md

## 막힌 곳
- 전체 deadline 2026-10-29T03:53:30Z(마진 120초).

## 평가
- 평가 01 (eval-01.md, 대상 커밋 09281d420cf808cfdbc7801547215e6399353646): 검수로. 구현 오류 0, 필수 테스트 누락 0, 질문 0, 검수 확인 항목 3, 권장 7. 다시 받은 횟수 0.
- 평가 02 (eval-02.md, 대상 커밋 a3e62cf765387ad601aa110b02ccfdcf31092ffa): 개발로. 구현 오류 1(C7: green 뒤 커밋으로 바뀐 파일이 review_paths에 없음 → 할 일 04), 필수 테스트 누락 0, 질문 0, 검수 확인 항목 3, 권장 6. 일반 review 독립 판정: #5 (a) 구현 오류, #5 (b) 합집합 정의 대비로는 맞음, #1·#2·#3·#6·#7 spec 정의대로이며 비차단(근거는 eval-02.md 표). 다시 받은 횟수 1.

## 검수
- 검수 01 (review-01.md, 검수 대상 커밋 c88acf7b982ed429cfcaf3a1dac99566d5b13c74, --since 09281d420cf808cfdbc7801547215e6399353646): 검수 통과. review rc=0 verdict ok, "검수 검사 통과. 할 일 2개 모두 완료, 평가 뒤 바뀐 것 없음, 바뀐 파일 9개 모두 허락된 파일 안, 새로 깨진 것 없음" (checks/013-review-full.json, 138개 통과, 건너뜀 0). C1–C9 충족, 검수 확인 항목 3개 확인됨, 사람 확인 없음.
