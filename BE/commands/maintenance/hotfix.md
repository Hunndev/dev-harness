# 긴급 수정 (hotfix, T0)

**재현 테스트 → 수정 → 단위 테스트** 3단계만 수행한다.
오타·한 줄 버그·긴급 hotfix 전용.

> **Tier 선택**
> - `/hb-be:maintenance:hotfix` — **이 문서.** 최소 ceremony. 영향도 분석, RCA, convention 충돌 체크 등은 전부 생략.
> - `/hb-be:maintenance:auto` — 일상 유지보수. RCA 포함.
> - `/hb-be:maintenance:deep` — full ceremony, 3방향 영향 Team 포함.

## 사전 조건

- **수정 범위가 명확**해야 한다. "이 파일의 이 라인"처럼 지목 가능해야 한다.
- 프로덕션 장애 대응이거나, 오타·한 줄 수정처럼 영향 범위가 단일 모듈 이하여야 한다.
- 사용자가 재현 방법을 알고 있어야 한다 (재현 테스트를 1단계에서 바로 작성해야 하므로).

## 핵심 원칙

- **범위 폭주 금지**: 사용자가 지정한 파일·라인 이외는 절대 수정하지 않는다. "옆에 있는 코드도 같이 정리"는 금지.
- **재현 테스트 필수**: 수정 전에 반드시 현재 상태에서 FAIL하는 테스트를 남긴다. 이게 없으면 "진짜 고쳐졌나?"를 증명할 수 없다.
- **새 ADR/convention 금지**: 이 경로에서 어떤 설계 결정도 새로 만들지 않는다. 필요하면 중단하고 planning으로 에스컬레이션.
- **3단계 외에는 아무것도 하지 않는다**: RCA, 영향도, 리뷰, 전체 회귀 모두 스킵. 의심되면 `:auto`로 전환.
- **TDD 사이클 부분 적용**: H1=Red, H2=Green. Refactor는 hotfix 범위를 벗어나므로 의도적으로 제외. 자세한 프로토콜은 `commands/shared/tdd.md` 참조.

## 식별자

이슈 ID가 있으면 그대로. 없으면 `hotfix-YYYYMMDD-slug`.
예: `BUCCL-99` 또는 `hotfix-20260408-typo-login`

## 파이프라인

### [H1] 재현 테스트 [TDD Red] (Fork)

1. **Pre-flight 점검**: `commands/shared/tdd.md`의 "Pre-flight 점검" 섹션을 수행한다:
   - `pytest --collect-only -q` → exit 0 확인 (아니면 중단 + 사용자 보고)
   - 아티팩트 디렉토리의 stale `tdd-red-debug.md` 삭제 (hotfix는 Green→Red 재작성이 없으므로 `tdd-red-revisions.md`는 해당 없음)
2. worktree(fork)를 생성한다.
3. 사용자가 제시한 증상을 **FAIL로 입증하는 최소 테스트**를 작성한다.
   - 파일: `tests/test_{module}_hotfix_{identifier}.py`
   - 가장 좁은 범위(단일 함수/뷰/모델)로 한정
3. `pytest {app}/tests/test_{module}_hotfix_{identifier}.py -v` 로 **FAIL**을 확인한다.
4. FAIL 출력을 `.harness/artifacts/maintenance/{identifier}/hotfix-red-log.txt`에 저장한다. 실패가 **'올바른 이유'(버그 때문)**인지 확인한다 (syntax error나 import error로 fail하면 Red가 아님).
5. 재현 불가 시 즉시 중단하고 사용자에게 추가 정보를 요청한다. **재현 안 되는데 고치지 않는다.**
6. `.harness/artifacts/maintenance/{identifier}/hotfix-reproduction.md`에 기록한다:
   - 재현 단계
   - 테스트 파일 경로
   - FAIL 출력 요약

### [H2] 수정 [TDD Green] (Fork)

1. **Red 테스트(H1)가 PASS가 되는 '최소 수정'만** 수행한다. 사용자가 지정한 파일·라인 이외는 수정하지 않는다.
   - **판정 기준**: 이 수정이 아래 "Refactor 금지" 정의의 **허용** 범주인가? "이 변경을 되돌렸을 때 H1 테스트가 다시 FAIL하는가?"의 답이 YES이면 허용, NO이면 Refactor이므로 금지.
   - 금지 범주에 해당하면 즉시 중단하고 `/hb-be:maintenance:auto`로 에스컬레이션한다.
2. 수정 즉시 H1 테스트가 **PASS**가 되는지 확인한다.
3. PASS 확인 후 출력을 `.harness/artifacts/maintenance/{identifier}/hotfix-green-log.txt`에 저장한다.
4. PASS가 아니면 원인을 추정해 다시 시도한다. **2회 실패 시 중단하고 `:auto` 또는 `:deep`으로 전환 제안**.
5. 수정 내용과 예상되는 side effect를 사용자에게 한 줄로 보고한다.

### [H3] 단위 테스트 [Refactor 금지] (Sub-agent)

`auto`와 달리 **전체 스위트를 돌리지 않는다**. 수정된 모듈의 단위 테스트만 실행한다.

1. `pytest {app}/tests/ -v`
2. 결과 확인:
   - H1 재현 테스트: **PASS**여야 함
   - 기존 단위 테스트 중 **새로 실패한 것이 있는지** 확인
3. 새로 실패한 테스트가 있으면:
   - **단위 테스트 범위 내**라면 → H2로 돌아가 수정 루프
   - **다른 모듈의 테스트가 실패**라면 → hotfix 범위를 벗어남. 즉시 중단하고 **에스컬레이션** (아래 참조)
4. `.harness/artifacts/maintenance/{identifier}/hotfix-summary.md`에 기록:
   - 수정된 파일 목록
   - H1 재현 테스트 파일 경로
   - 단위 테스트 통과/실패 요약

> **Refactor 금지 — 조작적 정의**:
> - **허용**: H1 Red 테스트를 PASS시키는 데 **직접 필요한** 코드 변경 (새 조건, null 체크, 타입 가드, 수정된 리터럴, 올바른 분기 추가).
> - **금지**: 이름 변경, 함수 추출, 중복 제거, 형식 정리, import 재배치, 근방 코드 스타일 수정.
> - **판정 기준**: "이 변경을 되돌렸을 때 H1 테스트가 다시 FAIL하는가?" YES → 허용, NO → 금지(Refactor).
> - **Compound fix 예외**: 하나의 수정이 **여러 독립적 변경의 합집합**으로 이루어질 때 (예: 두 파일에 동시에 null 체크를 넣어야 FAIL이 해소되는 경우), **전체 합집합을 단일 fix로 간주**한다. 개별 변경을 독립 평가하지 않는다. 단, 합집합이 2개 이상 모듈에 걸치면 hotfix 범위 밖이므로 `:auto`로 에스컬레이션한다.
> 코드 정리가 필요하면 `/hb-be:maintenance:auto`로 전환한다.

### 완료

`INDEX.md`를 생성하여 다음을 기록한다:
- `tier: hotfix`
- 수정된 파일 목록 (범위 제한 준수 여부 명시)
- H1 재현 테스트 파일 경로
- 단위 테스트 결과 요약
- **에스컬레이션 여부**: 범위 초과로 hotfix가 중단됐는지, auto/deep으로 넘겨졌는지

## 산출물

```
.harness/artifacts/maintenance/{identifier}/
  hotfix-reproduction.md
  hotfix-red-log.txt      ← NEW
  hotfix-green-log.txt    ← NEW
  hotfix-summary.md
  INDEX.md
```

> `hotfix` tier는 `root-cause.md`, `impact-analysis.md`, `convention-check.md`, `fix-plan.md`, `regression-report.md`, `review-comments.md`를 생성하지 않는다.
> 이 중 하나라도 필요하다고 판단되면 hotfix가 아니다 → `:auto` 또는 `:deep`으로.

## 에스컬레이션 규칙

다음 경우에는 hotfix를 **즉시 중단**하고 적절한 tier로 넘긴다:

| 상황 | 전환 대상 |
|---|---|
| 수정 범위가 2개 이상 모듈에 걸친다 | `/hb-be:maintenance:auto` |
| 기존 ADR/convention 위반이 의심된다 | `/hb-be:maintenance:deep` |
| 회귀가 단위 테스트 범위를 벗어난다 | `/hb-be:maintenance:auto` (전체 회귀 필요) |
| 새 설계 결정이 필요하다 | `/hb-be:planning:auto` 또는 `:deep` |
| H2 수정이 2회 연속 실패 | `/hb-be:maintenance:auto` (RCA 필요) |
| 마이그레이션이 필요하다 | `/hb-be:maintenance:auto` (마이그레이션은 hotfix 범위 아님) |
| 리팩토링이 필요하다 | `/hb-be:maintenance:auto` (hotfix에서는 Refactor 금지) |

에스컬레이션 시 `INDEX.md`에 "hotfix에서 시작해 {대상}으로 전환" 명시하고, 이미 작성한 `hotfix-reproduction.md`는 새 tier에서 `reproduction.md` 역할로 재사용된다.
