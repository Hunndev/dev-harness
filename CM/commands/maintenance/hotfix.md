# 긴급 수정 (hotfix, T0)

**재현 테스트 → 수정 → 단위 테스트** 3단계만 수행한다.
오타·한 줄 버그·긴급 hotfix 전용.

> **Tier 선택**
> - `/hb-cm:maintenance:hotfix` — **이 문서.** 최소 ceremony. 영향도 분석, RCA, convention 충돌 체크 등은 전부 생략.
> - `/hb-cm:maintenance:auto` — 일상 유지보수. RCA 포함.
> - `/hb-cm:maintenance:deep` — full ceremony, 3방향 영향 Team 포함.

## 사전 조건

- **수정 범위가 명확**해야 한다. "이 파일의 이 라인"처럼 지목 가능해야 한다.
- 프로덕션 장애 대응이거나, 오타·한 줄 수정처럼 영향 범위가 단일 모듈 이하여야 한다.
- 사용자가 재현 방법을 알고 있어야 한다 (재현 테스트를 1단계에서 바로 작성해야 하므로).

## 핵심 원칙

- **범위 폭주 금지**: 사용자가 지정한 파일·라인 이외는 절대 수정하지 않는다. "옆에 있는 코드도 같이 정리"는 금지.
- **재현 테스트 필수**: 수정 전에 반드시 현재 상태에서 FAIL하는 테스트를 남긴다. 이게 없으면 "진짜 고쳐졌나?"를 증명할 수 없다.
- **새 ADR/convention 금지**: 이 경로에서 어떤 설계 결정도 새로 만들지 않는다. 필요하면 중단하고 planning으로 에스컬레이션.
- **3단계 외에는 아무것도 하지 않는다**: RCA, 영향도, 리뷰, 전체 회귀 모두 스킵. 의심되면 `:auto`로 전환.

## 식별자

이슈 ID가 있으면 그대로. 없으면 `hotfix-YYYYMMDD-slug`.
예: `BUCCL-CM-99` 또는 `hotfix-20260408-socket-nullref`

## 파이프라인

### [H1] 재현 테스트 (Fork)

1. worktree(fork)를 생성한다.
2. 사용자가 제시한 증상을 **FAIL로 입증하는 최소 테스트**를 작성한다.
   - 파일: `src/__tests__/{module}.hotfix.{identifier}.test.ts`
   - 가장 좁은 범위(단일 함수/핸들러/repository)로 한정
3. `npm test -- --testPathPattern={module}.hotfix.{identifier}` 로 **FAIL**을 확인한다.
4. 재현 불가 시 즉시 중단하고 사용자에게 추가 정보를 요청한다. **재현 안 되는데 고치지 않는다.**
5. `.harness-artifacts/maintenance/{identifier}/hotfix-reproduction.md`에 기록한다:
   - 재현 단계
   - 테스트 파일 경로
   - FAIL 출력 요약

### [H2] 수정 (Fork)

1. 사용자가 지정한 파일·라인만 수정한다.
2. 수정 즉시 H1 테스트가 **PASS**가 되는지 확인한다.
3. PASS가 아니면 원인을 추정해 다시 시도한다. **2회 실패 시 중단하고 `:auto` 또는 `:deep`으로 전환 제안**.
4. 수정 내용과 예상되는 side effect를 사용자에게 한 줄로 보고한다.

### [H3] 단위 테스트 (Sub-agent)

`auto`와 달리 **전체 스위트를 돌리지 않는다**. 수정된 모듈의 단위 테스트만 실행한다.

1. `npm run typecheck` (수정 파일 범위)
2. `npm test -- --testPathPattern={module}`
3. 결과 확인:
   - H1 재현 테스트: **PASS**여야 함
   - 기존 단위 테스트 중 **새로 실패한 것이 있는지** 확인
4. 새로 실패한 테스트가 있으면:
   - **단위 테스트 범위 내**라면 → H2로 돌아가 수정 루프
   - **다른 모듈의 테스트가 실패**라면 → hotfix 범위를 벗어남. 즉시 중단하고 **에스컬레이션** (아래 참조)
5. `.harness-artifacts/maintenance/{identifier}/hotfix-summary.md`에 기록:
   - 수정된 파일 목록
   - H1 재현 테스트 파일 경로
   - 단위 테스트 통과/실패 요약

### 완료

`INDEX.md`를 생성하여 다음을 기록한다:
- `tier: hotfix`
- 수정된 파일 목록 (범위 제한 준수 여부 명시)
- H1 재현 테스트 파일 경로
- 단위 테스트 결과 요약
- **에스컬레이션 여부**: 범위 초과로 hotfix가 중단됐는지, auto/deep으로 넘겨졌는지

## 산출물

```
.harness-artifacts/maintenance/{identifier}/
  hotfix-reproduction.md
  hotfix-summary.md
  INDEX.md
```

> `hotfix` tier는 `root-cause.md`, `impact-analysis.md`, `convention-check.md`, `fix-plan.md`, `regression-report.md`, `review-comments.md`를 생성하지 않는다.
> 이 중 하나라도 필요하다고 판단되면 hotfix가 아니다 → `:auto` 또는 `:deep`으로.

## 에스컬레이션 규칙

다음 경우에는 hotfix를 **즉시 중단**하고 적절한 tier로 넘긴다:

| 상황 | 전환 대상 |
|---|---|
| 수정 범위가 2개 이상 모듈에 걸친다 | `/hb-cm:maintenance:auto` |
| 기존 ADR/convention 위반이 의심된다 | `/hb-cm:maintenance:deep` |
| 회귀가 단위 테스트 범위를 벗어난다 | `/hb-cm:maintenance:auto` (전체 회귀 필요) |
| 새 설계 결정이 필요하다 | `/hb-cm:planning:auto` 또는 `:deep` |
| H2 수정이 2회 연속 실패 | `/hb-cm:maintenance:auto` (RCA 필요) |
| Socket.io 이벤트 흐름 변경이 필요하다 | `/hb-cm:maintenance:deep` (이벤트 흐름은 hotfix 범위 아님) |
| SQL 스키마 변경이 필요하다 | `/hb-cm:maintenance:auto` (마이그레이션은 hotfix 범위 아님) |

에스컬레이션 시 `INDEX.md`에 "hotfix에서 시작해 {대상}으로 전환" 명시하고, 이미 작성한 `hotfix-reproduction.md`는 새 tier에서 `reproduction.md` 역할로 재사용된다.
