# 평가 03: verification-preflight

- 날짜: 2026-10-29
- 도구: Claude Code (claude-opus-5-5, high), 새 컨텍스트 서브에이전트
- 자동 메모: 이 세션의 맥락에 앞 세션의 자동 메모가 보이지 않음
- 시작 커밋(state.json `baseline.head`): dae8b745efed1afcb64ca8b20bc52dc82a28019c
- 평가 대상 커밋(`git rev-parse HEAD`): 067a75d1b534ae49ea79faa76acb818323df1a1e
- 평가 02 대상 커밋(INDEX.md 평가 절): a3e62cf765387ad601aa110b02ccfdcf31092ffa
- 이번 범위(감독 지시): 평가 02의 구현 오류 1(C7)을 고친 할 일 04의 변경분. 중심은 `git diff a3e62cf 067a75d -- . ':(exclude).harness/artifacts/work/verification-preflight'` = bin/hb.py(+12/−2), tests/test_hb_preflight_reuse.py(새, 203줄). a3e62cf..4e6269a(평가 02 커밋)는 작업 폴더만 바꿈. 할 일 04 개발 중 spec.md, tasks.json, tasks/는 바뀌지 않음. 일반 review #1·#2·#3·#6·#7은 평가 02에서 판정되어 다시 심의하지 않음.
- 전체 변경(참고): `git diff dae8b74 067a75d -- . ':(exclude)…'` = README.md, bin/hb.py, skills/{dev,eval,plan,review}/SKILL.md, tests/test_hb_preflight.py, tests/test_hb_preflight_paths.py, tests/test_hb_preflight_reuse.py, tests/test_hb_review.py, tests/test_skills_preflight.py (11개, 모두 할 일들의 allowed_files 안).
- 기준 잡기: 할 일 01–04 모두 완료(INDEX.md 49·50·63·75줄, state.json `tasks.{01,02,03,04}.done`). 시작 때 `git status --porcelain` 빈 값.
- 읽은 것: skills/eval/SKILL.md, spec.md, tasks.json, tasks/04, INDEX.md, state.json, checks/017·018·019, .harness/README.md, .harness/docs/checks.json, bin/hb.py 전체, tests/test_hb_preflight_reuse.py 전체, tests/test_hb_preflight.py의 C7·C8 부분(185–209, 348–392), skills/dev/SKILL.md 57줄(git grep). 이전 기록 eval-02.md는 점검표를 끝낸 뒤 읽음.
- 명령: 읽기용 git(status, rev-parse, diff, log, show, ls-files)에 더해, 감독이 정한 목록 밖이지만 읽기만 하는 `git grep`, `git check-ignore`, `ls`, `cat`, `grep`을 씀(파일을 쓰거나 바꾸지 않음). 테스트, pytest, hb.py, python은 돌리지 않음.
- 시작 전 검증 기록: 진행표에 할 일 04의 red 전(76줄)·green 전(80줄) `preflight` 결과가 verdict와 세 칸으로 적혀 있음(product not_run / environment ok / aux none, blocked 없음). 완료 증거로는 프로그램 기록만 읽음: 04 red ok(checks/017, 본문 실패 3, 통과 2, head 4e6269a), 04 green ok(checks/018 5개 통과, checks/019 전체 156개 통과, 건너뜀 0, head 4e6269a). state.json `tasks.04.green.ok` true, `done.head` 4e6269a. 156 = 평가 02 시점 151 + 새 테스트 5로 맞음.

## 영향 지도

줄 번호는 067a75d의 bin/hb.py 기준.

| 바뀐 것 | 종류 | 직접 쓰는 곳 | 영향받을 수 있는 기존 동작 | 더 따라간 경로 | 못 따라간 곳 | 테스트 |
|---|---|---|---|---|---|---|
| `committed_since(ctx, base)` (99–102, 새) | 함수 | cmd_preflight 464만(git grep) | 없음(다른 명령은 부르지 않음) | `git diff --name-only -z --no-renames base HEAD`: 트리끼리 비교라 색인·작업 트리를 쓰지 않음. 지운 파일 포함, 이름 바꾸기는 옛·새 경로 둘 다. `-z`라 경로 따옴표 없음. 작업 폴더 제외 기준은 `changed()`(88)와 같은 `ctx.work_rel + "/"` 접두어. git 실패는 `git()`(65–69)의 `Stop` | base 커밋이 저장소에서 사라진 경우(gc, 얕은 복제)는 blocked/outcome 없는 stop이 됨(실행해 보지 않음, 코드로만) | 있음: test_hb_preflight_reuse.py 새 파일 커밋(163), 추적 파일 수정 커밋(178), 커밋 + 커밋 안 한 새 파일(190), 작업 폴더 기록만 커밋(151, 제외 확인). 허술함: 커밋으로 지운 파일·이름 바꾼 파일 경우 없음 |
| cmd_preflight 재사용 판단 (451–465) | 함수, API 응답 모양(`review_paths` 내용) | main → cmd_preflight | 기존 C7 세 경우(소스 같음, 커밋 안 한 수정, 커밋 안 한 새 파일), `product` 판정, C8 | base = `entry.red.head`(462). check_green은 HEAD가 red.head와 같을 때만 시작(535), check_red는 할 일 항목을 통째로 바꿔 앞 green을 지움(520) → 남아 있는 green은 늘 지금 red와 짝이고 그 HEAD는 red.head. `base == head`(커밋 없음)면 464를 건너뛰어 기존 식 그대로(465). `same_source` 갈래(458–459)는 손대지 않음. 출력 모양(키 이름, 정렬된 목록)은 그대로 | 없음 | 있음: 기존 test_hb_preflight.py 351–371(커밋 없는 세 경우, 이 파일은 a3e62cf 뒤 안 바뀜), 새 파일 144(커밋·변경 없음 → same_source, review_paths 없음). 모두 checks/018·019에서 통과 |
| `snapshot()` 반환값 세 번째 `head`를 받음 (457) | 함수 호출 | cmd_preflight | snapshot 자체 | snapshot(91–96)은 바뀌지 않음. 원래 `(지문, paths, head)`를 냈고 앞 코드는 `_`로 버렸음 | 없음 | 위와 같음 |
| C8(기록 안 고침) | 함께 쓰는 데이터 | cmd_preflight | state.json, checks/, logs/ | 새 코드에 save_json·makedirs·run_check 없음. `git diff` 트리 비교는 쓰기 없음 | 없음 | 있음: 새 파일의 모든 테스트가 `preflight_untouched`(128–137)로 state.json 바이트와 checks/, logs/ 목록을 앞뒤 비교. 기존 C8 두 개(test_hb_preflight.py 374, 390) |
| 다른 명령(baseline/check/done/review) | 함수 | main | 판정, 지문, 안전 관문 | a3e62cf..067a75d의 bin/hb.py diff는 99–103과 452–464뿐. check_green·cmd_done·cmd_review·test_fingerprint 불변 | 없음 | 전체 묶음(checks/019, 156개) |
| skills/dev/SKILL.md 57줄 "review_paths는 green 때 경로와 지금 바뀐 경로의 합집합" | 문서(이번에 안 바뀜) | 지휘 | 문서와 동작의 일치 | 이제 review_paths에는 green 뒤 커밋으로 바뀐 경로도 들어감. "지금 바뀐 경로"를 커밋 안 된 경로로만 읽으면 덜 적힌 설명 | 없음 | 문서 내용 테스트는 이 문장의 커밋 경우를 보지 않음(C9가 요구하지 않음) |

## 점검표

| 관점 | 확인 대상 → 근거 → 판단 |
|---|---|
| 맞는가 | C7 커밋 경우 → 462–465: green 뒤 커밋(red.head..HEAD)으로 바뀐 경로를 `changed`일 때 더함. tasks/04 9–11줄의 입력(새 파일 `extra.py` 커밋, `tests/test_app.py` 수정 커밋)에서 둘 다 review_paths에 들어감 → 문제없음. 기존 C7 세 경우 → 커밋이 없으면 `base == head`라 464를 건너뜀, `same_source`는 459 그대로 → 문제없음(tasks/04 15·16줄). 작업 폴더 기록 제외 → 102가 changed() 88과 같은 기준 → 문제없음(tasks/04 17줄). 지운 파일·이름 바꾸기 → `--name-only --no-renames`가 지운 경로와 옛·새 경로를 냄(101) → 문제없음(테스트는 없음, 권장 1). baseline과 red 사이 커밋 → red.head 안에 들어 있어 green이 그 코드로 통과했으므로 빠지는 것이 맞음 → 문제없음. green 검사가 도는 동안 누가 커밋하면 green의 HEAD가 red.head와 달라질 수 있으나, 그 경우에도 red.head..HEAD는 그 커밋들을 포함해 더 알리는 쪽이고, 커밋은 지휘만 한다(check_green 536 문구) → 흐름 밖, 문제없음. base 커밋이 사라진 경우 → `git()`이 blocked/outcome 없는 stop을 냄. spec 예외 상황(40–44줄)에 없고 잘못 통과시키지 않는 쪽 → 권장 2 |
| 안전한가 | 새 코드는 git 읽기 하나. 입력은 state.json의 red.head(프로그램이 쓴 값)이고 git 인자 목록으로 넘겨 셸을 거치지 않음(65–66). 비밀값·개인정보 없음. 결제·권한·개인정보·DB 해당 없음(spec 38줄) → 문제없음 |
| 기존 코드와 맞는가 | `snapshot`, `changed()`의 제외 기준, `git()`의 Stop을 그대로 씀(spec 35줄 재사용). 출력 키와 모양 불변(spec 16줄). green 기록 모양 불변(557, tasks/04 24줄). 다른 명령 불변 → 문제없음 |
| 비용 | `changed`일 때만 git diff 한 번 더(463–464). 반복·대기 없음 → 문제없음 |
| 저장소 규칙 | .harness/README.md 8줄(표준 라이브러리만, 기존 판정과 안전 관문 유지) → 새 import 없음, 관문 불변 → 문제없음. 9줄(기록은 작업 폴더, logs/ git 제외) → `git check-ignore`로 logs/x.log 제외 확인 → 문제없음. 할 일 04 allowed_files(bin/hb.py, tests/test_hb_preflight_reuse.py) → a3e62cf..067a75d 제품 변경이 정확히 이 둘 → 문제없음. 기존 테스트 파일을 고치지 않음(tasks/04 24줄) → 문제없음. dev SKILL의 "각 check 전 preflight, 세 칸 보고" → INDEX 76·80줄 → 문제없음(평가 02 권장 4 반영) |
| 할 일끼리 | 04는 01의 cmd_preflight 재사용 갈래만 넓힘. 03(--aux, PATH)과 겹치지 않음. 02의 dev SKILL 57줄 설명은 04 뒤 동작보다 덜 적혀 있음(커밋 경우를 말하지 않음). 할 일 04가 그 문서를 allowed_files에 두지 않았고 C9는 review_paths 설명을 요구하지 않음 → 권장 3 |
| 테스트 전체 | 새 테스트는 green을 실제 hb로 만들고(through_green 109–123) 커밋은 임시 저장소의 git으로 만듦. 대조 두 개(커밋 없음 → same_source, 기록만 커밋 → green paths만)와 실패 확인 세 개(red 때 3개 실패, checks/017)가 "커밋 안 된 경로만"이라는 앞 가정과 다른 경우를 정확히 짚음. `assertEqual(sorted(review_paths), …)`로 정확한 목록을 단언해 작업 폴더 기록이 섞이면 실패함. 같은 잘못된 가정: 찾지 못함. 빠진 경우: 커밋으로 지운 파일·이름 바꾼 파일(권장 1). `PYTHONDONTWRITEBYTECODE=1`을 hb와 git 둘 다에 줌(24, 71, 87) → 옛 .pyc 문제를 피함 → 문제없음 |
| 남은 권장 | 아래 "남은 권장 다시 보기" |

## 이전 지적 대조

평가 02의 꼭 고칠 것은 구현 오류 1건이었다(eval-02.md 74–80줄). 필수 테스트 누락 0, 질문 0.

| 평가 02 꼭 고칠 것 | 지금 | 판단 |
|---|---|---|
| 구현 오류 1: green 뒤 커밋으로 바뀐 파일이 `review_paths`에 없음(C7) | 462–465가 red.head..HEAD의 커밋 변경 경로를 더함. 평가 02의 두 입력(새 파일 `extra.py` 커밋, `tests/test_app.py` 수정 커밋)이 새 테스트 163·178에 그대로 있고 red에서 실패(checks/017), green에서 통과(checks/018). 평가 02가 든 이 저장소의 예(할 일 01 green 뒤 커밋된 README.md, skills/*/SKILL.md, tests/test_skills_preflight.py, tests/test_hb_preflight_paths.py)는 코드에서 도출하면 이제 `committed_since(dae8b74, HEAD)`로 모두 들어감 | **고쳐짐** |

평가 02 검수 확인 항목 1–3은 할 일 04 뒤 상태로 아래 검수 확인 항목에 다시 적었다. 평가 02 권장 4(시작 전 검증 기록)는 할 일 04에서 반영됨(INDEX 76·80줄). 그 밖의 권장은 범위 밖이라 그대로 둔다.

## 지적

### 구현 오류 (꼭 고칠 것)
없음.

### 필수 테스트 누락
없음. C7이 요구한 "파일을 바꾸면 changed와 그 파일이 review_paths"는 커밋 안 한 경우(test_hb_preflight.py 358, 366)와 커밋한 경우(test_hb_preflight_reuse.py 163, 178, 190) 모두 행동 테스트가 있다. 지운 파일·이름 바꾸기는 권장 1.

### 질문
없음.

### 검수 확인 항목
1. **전체 검사 다시 돌리기.** `review --since 067a75d1b534ae49ea79faa76acb818323df1a1e`. 기대: 새로 깨진 것 0, 건너뜀 0, 전체 156개(평가 02 시점 151 + 할 일 04의 5), 할 일 04의 red 실패 세 개 통과.
2. **기존 C7·C8 테스트가 그대로 통과.** 기대: tests/test_hb_preflight.py 25개, tests/test_hb_preflight_paths.py 13개, tests/test_hb_preflight_reuse.py 5개 모두 통과. 앞의 두 파일은 a3e62cf 뒤 바뀌지 않았음을 `git diff a3e62cf 067a75d -- tests/test_hb_preflight.py tests/test_hb_preflight_paths.py`가 빈 값인 것으로 확인.
3. **이 저장소에서의 커밋 경우(선택, 기록을 만들지 않는 명령).** 작업 트리가 깨끗할 때 pytest가 깔린 파이썬으로 `bin/hb.py --repo . preflight --work verification-preflight --task 01`. 기대: `outcome.product` pass, `reuse` changed, `review_paths`가 바탕 검사 뒤 바뀐 제품 파일 11개(README.md, bin/hb.py, skills/{dev,eval,plan,review}/SKILL.md, tests/test_hb_preflight.py, tests/test_hb_preflight_paths.py, tests/test_hb_preflight_reuse.py, tests/test_hb_review.py, tests/test_skills_preflight.py)와 같고 `.harness/artifacts/work/verification-preflight/` 경로가 없음. 실행 앞뒤로 state.json 바이트와 checks/, logs/ 목록이 같음.

### 권장
1. **커밋으로 지운 파일·이름 바꾼 파일 테스트.** 101의 `--no-renames`와 `--name-only`가 지운 경로와 옛·새 경로를 내므로 동작에는 빠진 것이 없으나 이를 지키는 테스트가 없다(할 일 04 테스트 검토 R2, 구현 검토 권장과 같음).
2. **red.head 커밋이 사라진 경우.** gc나 얕은 복제로 base 커밋이 없으면 `git diff`가 실패해 blocked/outcome 없는 stop("git 명령이 실패함")이 된다. spec 예외 상황에 없는 경우이고 기존 snapshot의 git 실패와 같은 방식이며 잘못 통과시키지 않는다. 다음 설명서에서 정할 일.
3. **dev SKILL 57줄 설명.** "green 때 경로와 지금 바뀐 경로의 합집합"에 "green 뒤 커밋으로 바뀐 경로도 들어간다"를 더하면 할 일 04 뒤 동작과 맞는다. C9가 요구한 문장은 아니다.

## 남은 권장 다시 보기

| 개발 때 남은 권장 (INDEX 줄) | 지금 판단 |
|---|---|
| 할 일 04 테스트 검토 R1: baseline과 green 사이 커밋 경우 없음 (78) | 권장으로도 두지 않음. 그 커밋은 red.head 안에 있어 green이 그 코드로 통과했고, C7은 "green 기록 뒤" 변경만 요구한다. review_paths에서 빠지는 것이 맞다 |
| 할 일 04 테스트 검토 R2·구현 검토: 커밋으로 지우기/이름 바꾸기 테스트 없음 (78, 82) | 권장 1 유지. 동작은 맞고(101) spec이 이 경우의 테스트를 따로 요구하지 않는다 |
| 할 일 04 구현 검토: red head 커밋이 사라지면 blocked/outcome 없는 stop (82) | 권장 2 유지. spec 예외 상황에 근거가 없어 꼭 고칠 것이 아니다 |
| 그 밖(01–03의 권장, 평가 02 권장 1–3·5·6) | 이번 범위 밖. 평가 02 판단 그대로 |

## 테스트로 확인되는 것과 안 되는 것

- 확인됨(행동 테스트, checks/018·019 통과): green 뒤 커밋으로 더한 새 파일, 커밋으로 고친 추적 파일, 커밋 변경과 커밋 안 한 새 파일이 함께 있는 경우의 review_paths, 커밋에 작업 폴더 기록만 있을 때 기록이 빠지는 것, 커밋·변경 없을 때 same_source, 이 모든 경우에 preflight가 state.json·checks/·logs/를 고치지 않는 것. 기존 C7 세 경우와 C8 두 경우.
- 허술함: 커밋으로 지운 파일과 이름 바꾼 파일(권장 1).
- 안 됨: red.head 커밋이 사라진 경우(권장 2), green 검사 중 커밋(흐름 밖).

## 다음 단계

**검수로.** 구현 오류, 필수 테스트 누락, 질문이 모두 없다. 사용자는 새 창(자동 메모 끔)에서 검수(`review`)를 부른다. 검수의 `--since`는 이 평가의 대상 커밋 067a75d1b534ae49ea79faa76acb818323df1a1e이다(이 기록의 커밋은 작업 폴더만 바꾼다). 검수 확인 항목 1–3은 이 기록에 남아 검수가 읽는다. 다시 받은 횟수 2(한도 3).
