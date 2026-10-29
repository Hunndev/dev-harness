# 04 preflight reuse: green 뒤 커밋으로 바뀐 파일 (bug)

- 맡은 완료 기준: C7 (spec.md 30줄, 16줄의 `reuse`/`review_paths` 정의)
- 먼저 끝나야 하는 할 일: 01, 03
- 출처: 평가 02 구현 오류 1 (Claude 일반 review #5 (a)를 spec 정의로 판정한 결과)

## 지적 그대로
**green 뒤 커밋으로 바뀐 파일이 `review_paths`에 나오지 않음.** 코드에서 도출한 예상 실패(실행하지 않음).
- 입력: 실제 hb로 할 일의 baseline → red → green(green paths 예: `app.py`, `tests/test_new.py`). 그 뒤 green paths 밖의 파일을 커밋으로 바꾼다. 예: 새 파일 `extra.py`를 더해 커밋하거나, 이미 추적되는 `tests/test_app.py`를 고쳐 커밋한다. 작업 트리는 깨끗. `preflight --work <작업> --task <번호>`.
- 기대 결과(spec C7, 16줄): `reuse`는 `changed`, `review_paths`에 그 파일(`extra.py` 또는 `tests/test_app.py`)이 들어 있다. 커밋하지 않고 바꾼 경우(tests/test_hb_preflight.py 366–371)와 같은 결과.
- 지금 코드가 낼 결과: `reuse: changed`(HEAD가 바뀌어 스냅숏이 다름), `review_paths`는 green paths뿐. `changed()`(bin/hb.py 84–88)가 커밋 안 된 경로만 내므로 cmd_preflight 455줄의 합집합에 green paths만 남는다.
- 근거: bin/hb.py 84–96, 449–455; spec.md 16·30·35줄; tests/test_hb_preflight.py 351–371(커밋 경우 없음).

## 기대 결과로 함께 지킬 것
- 기존 C7 세 경우(소스 같음 → `same_source`·review_paths 없음, 커밋 안 한 수정, 커밋 안 한 새 파일)는 결과가 그대로다.
- green 기록 뒤 커밋도 없고 작업 트리도 같으면 여전히 `same_source`. 커밋 뒤에는 `changed`(spec 16줄, 스냅숏에 HEAD 포함)이고, 그 커밋들로 바뀐 파일과 지금 커밋 안 된 경로가 review_paths에 들어간다.
- 이 작업의 작업 폴더(`.harness/artifacts/work/<작업 이름>/`)의 기록 파일은 review_paths에 넣지 않는다(`changed()`와 같은 기준).

## 모양
- `cmd_preflight`의 재사용 판단만 고친다. 작은 도우미 함수를 둘 수 있다.
- 테스트는 새 파일 `tests/test_hb_preflight_reuse.py`. tests/test_hb_preflight.py처럼 임시 git 저장소의 가짜 제품과 실제 hb.py subprocess로, green은 실제 hb의 baseline → red → green으로 만든다(기록을 손으로 만들지 않는다).

## 지킬 것
- spec 18·35줄: preflight는 state.json, checks/, logs/를 만들거나 고치지 않는다. 기존 판정·지문·안전 관문과 다른 명령(baseline/check/done/review)을 바꾸지 않는다. green 기록의 모양을 바꾸지 않는다. 기존 테스트 파일을 고치지 않는다.
- 이번에 안 할 것: 일반 review #1·#2·#3·#6·#7(평가 02에서 spec 정의대로이며 비차단으로 판정).
