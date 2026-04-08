# 유지보수 파이프라인 (T1 standard)

이미 돌아가는 코드의 문제를 **lightweight** 흐름으로 고친다. 회귀 방지가 최우선.

> **Tier 선택**
> - `/hb-cm:maintenance:hotfix` — 오타, 한 줄 fix, 긴급 수정. 재현 테스트 + 수정 + 단위 테스트 3단계.
> - `/hb-cm:maintenance:auto` — **이 문서.** 일상 유지보수 기본값. M4 영향도 3방향 Team, M5 ADR 충돌 체크 없음.
> - `/hb-cm:maintenance:deep` — M1~M9 full ceremony. 모듈 경계가 불분명하거나 기존 ADR 위반이 의심될 때.

## 사전 조건

- 사용자가 이슈(버그, 리팩토링, 성능, 의존성)를 제시해야 한다.
- 에러 로그, 재현 절차, 스크린샷이 있으면 제공한다.

## 식별자

이슈 ID가 있으면 그대로. 없으면 `maint-YYYYMMDD-slug`.
예: `BUCCL-CM-42` 또는 `maint-20260408-socket-disconnect`

## 핵심 원칙

- 회귀 방지 최우선
- 수정 범위 폭주 방지 → `fix-plan.md`에서 범위 명시
- **신규 ADR 생성 금지** — 새 결정이 필요하면 `/hb-cm:planning:auto` 또는 `:deep`으로 에스컬레이션
- **M4 3방향 영향 Team 없음**: 간단한 버그 수정은 수직 레이어만 추적. 호출자·데이터 흐름까지 확장 필요하면 `:deep`.
- **M5 convention 충돌 sub-agent 없음**: 명백한 규칙 위반은 수정하면서 바로 체크. 기존 ADR과의 관계가 모호하면 `:deep`.

## 파이프라인

### [M1] 상태 점검 (메인)

1. 사용자가 제시한 이슈를 정리한다.
2. 이슈 유형을 분류한다:
   - `bug` — 서버 에러, 예외, 잘못된 동작
   - `refactor` — 코드 구조 개선, 기술 부채 해소
   - `performance` — 느린 응답, 타임아웃, 메모리
   - `dependency` — 패키지 업그레이드, 보안 패치
3. `docs/module-registry.yaml`을 읽고, 관련 모듈(router/service/repository/socket-handler)을 식별한다.
4. 사용자에게 다음을 확인한다:
   - 이슈 유형
   - 관련 모듈
   - 긴급도 — **hotfix면 `:hotfix`로 전환 제안**
   - 재현 가능 여부
5. `.harness-artifacts/maintenance/{identifier}/` 디렉토리를 생성한다.

### [M2] 이슈 재현 (Fork)

1. worktree(fork)를 생성하여 이슈를 재현한다.
2. 재현 테스트 케이스를 작성한다:
   - 테스트 파일: `src/__tests__/{module}.maint.{identifier}.test.ts`
   - 현재 상태에서 테스트가 **FAIL** 하는 것을 확인한다. (bug인 경우)
   - refactor인 경우, characterization test를 작성한다.
3. 재현 불가 시 사용자에게 보고하고 추가 정보를 요청한다.
4. `reproduction.md`를 저장한다.
5. worktree를 정리한다.

### [M3] 근본 원인 추적 — RCA (Sub-agent)

1. sub-agent를 호출하여 근본 원인을 분석한다.
2. sub-agent에게 전달:
   - `reproduction.md`
   - 관련 모듈 코드 (router, service, repository, socket handler)
   - `docs/adr.yaml` (간략 참조용)
3. sub-agent는 tracer 스타일로 분석:
   - stack trace에서 발생 지점 특정
   - 원인 추정(가능성 순 나열)
4. `root-cause.md`를 저장한다.
5. 분석 결과를 사용자에게 제시하고 원인 추정에 대한 동의를 구한다.

### [M4] 수정 계획 + 회귀 리스크 (Fork) _(deep의 M6에 해당)_

1. worktree(fork)를 생성하여 수정 계획을 작성한다.
2. 계획에 포함:
   - 수정 대상 파일 목록
   - 각 수정의 내용과 이유
   - 회귀 리스크 (Socket.io 이벤트 흐름 영향 포함)
   - **범위 제한** (이번에 하지 않는 것)
   - 마이그레이션 필요 여부
3. 초안과 논의점을 사용자에게 제시한다.
4. `fix-plan.md`를 저장한다.
5. worktree를 정리한다.

### [M5] 수정 실행 (Fork) _(deep의 M7에 해당)_

1. worktree(fork)를 생성하여 수정한다.
2. 수정 원칙:
   - **최소 범위**: `fix-plan.md`에 명시된 범위만 수정
   - **convention 준수**: SQL parameterized binding, 명백한 규칙 위반 즉시 체크
   - **마이그레이션 분리**: 필요 시 별도 커밋
3. 수정 내용과 side effect를 사용자에게 보고한다.

### [M6] 회귀 테스트 (Sub-agent 직렬) _(deep의 M8 경량화)_

`auto` tier는 3 스위트 병렬 Team 대신 **직렬 실행**으로 단순화한다.

1. 타입 체크: `npm run typecheck`
2. 린트: `npm run lint`
3. 단위 테스트: `npm test -- --testPathPattern={module}`
   - M2 재현 테스트가 **PASS**가 되는지 확인
4. 전체 테스트: `npm test`
   - 새로 실패한 테스트가 있는지 확인
5. 회귀 발견 시 M5로 복귀 (수정 루프).
6. `regression-report.md`를 저장한다.

### [M7] 리뷰 + 반영 (Sub-agent + Fork) _(deep의 M9에 해당)_

1. sub-agent를 호출하여 코드리뷰:
   - `fix-plan.md` (의도)
   - `docs/code-convention.yaml` (기준)
   - `git diff`
2. `review-comments.md`를 저장한다.
3. worktree에서 리뷰 반영:
   - 각 코멘트의 수용/거부를 사용자에게 제시
   - 수정 후 M6 경량 재실행

### 완료

`INDEX.md` 기록:
- 산출물 목록
- 수정된 파일 목록
- 회귀 테스트 결과 요약
- 커밋 메시지 제안
- tier 정보 (`tier: auto`)
- planning 에스컬레이션 여부

## 산출물

```
.harness-artifacts/maintenance/{identifier}/
  reproduction.md
  root-cause.md
  fix-plan.md
  regression-report.md
  review-comments.md
  INDEX.md
```

> `auto` tier는 `impact-analysis.md`, `convention-check.md`를 생성하지 않는다.
> 필요하면 `:deep`으로 재시작.

## 언제 deep으로 전환해야 하는가

- 근본 원인이 여러 모듈에 걸쳐 있다 → M4 3방향 영향 Team 필요
- 수정 방향이 기존 ADR을 위반할 가능성이 있다 → M5 convention 충돌 sub-agent 필요
- 데이터 무결성 문제 (이미 잘못된 데이터가 쌓여 있을 가능성)
- 실시간 이벤트 흐름 문제가 여러 소켓 클라이언트에 전파된 가능성

## 언제 hotfix로 전환해야 하는가

- 오타, 한 줄 수정
- 명백한 단일 모듈 버그
- 긴급 hotfix (프로덕션 장애 대응)

→ `/hb-cm:maintenance:hotfix`
