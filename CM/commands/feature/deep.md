# 신규개발 파이프라인 (CM)

새 기능을 설계·구현·리뷰까지 끌고 간다.

## 사전 조건

- `docs/code-convention.yaml`과 `docs/adr.yaml`이 작성되어 있어야 한다.
- 요구사항이 확정되어 있어야 한다. 확정되지 않았으면 planning 트랙으로.
- 구현이 완료된 feature branch이거나, 새로 생성할 branch.

## 식별자

`git branch --show-current`로 resolve한다.
branch가 없으면 `feature/{issue}-{short-desc}` 형식으로 생성한다.

## 핵심 원칙

- Agent Team 없음: 설계의도가 한 줄기로 모이는 순차 작업이라 병렬 관점이 오히려 발산을 만든다.
- 새 ADR이 필요하면 planning 트랙으로 넘겨서 결정 후 돌아온다.
- TypeScript strict 모드 유지. any 금지.
- Controller/Service/Repository 레이어 분리 원칙 유지.

## 파이프라인

### [F1] 상태 점검 (메인)

1. **Pre-flight 점검**: `commands/shared/tdd.md`의 "Pre-flight 점검" 섹션을 수행한다:
   - `npx jest --listTests --silent` → exit 0 확인 (아니면 중단 + 사용자 보고)
   - `npx jest --version`으로 Jest 버전 확인 → 플래그 선택 (`--testPathPattern` vs `--testPathPatterns`)
   - 아티팩트 디렉토리의 stale `tdd-red-debug.md`, `tdd-red-revisions.md` 삭제
2. `git branch --show-current`로 현재 branch를 확인한다.
3. `git diff main...HEAD --stat`으로 변경 파일 목록을 확인한다 (기존 코드가 있으면).
4. 사용자에게 다음을 확인한다:
   - branch명
   - base branch (기본: `main`)
   - 변경 파일 수 (있으면)
5. `.harness-artifacts/feature/{branch-name}/` 디렉토리를 생성한다.

### [F2] 요구사항 정리 (Fork)

1. **worktree(fork)를 생성**하여 요구사항을 정리한다.
2. planning 트랙의 산출물이 있으면 가져온다:
   - `requirements-interview.md` → 요약
   - `decision-draft.md` 또는 관련 `docs/adr.yaml` 항목 → 참조
3. 없으면 사용자에게 질문하여 수집한다.
4. 요구사항을 MUST / SHOULD / NICE로 분류한다.
5. `requirements.md`를 저장한다.
6. worktree를 정리한다.

### [F3] 유사 구현 조사 (Sub-agent)

1. **sub-agent를 호출**하여 기존 코드베이스에서 유사 구현을 조사한다.
2. sub-agent에게 전달:
   - `requirements.md`
   - `docs/module-registry.yaml`
   - 기존 코드 (관련 controllers/services/repositories)
3. sub-agent는 다음을 조사:
   - 기존 코드에 비슷한 패턴이 이미 있는가? (재사용 가능성)
   - 기존 service/repository를 확장할 수 있는가?
   - 기존 코드와 충돌할 가능성이 있는 부분은? (route 충돌, 이벤트 이름 충돌, DB 스키마 충돌)
   - 기존 ApiError 계층 / response 헬퍼를 어떻게 활용할 것인가?
4. `prior-art.md`를 저장한다.
5. **사용자 확인 없이 자동 진행.**

### [F4] 설계의도 작성 (Fork)

1. **worktree(fork)를 생성**하여 설계의도 문서를 작성한다.
2. 아래 내용을 포함:
   - 작업 개요
   - 핵심 설계 결정과 트레이드오프 (어떤 레이어에 로직을 둘지, 동기/비동기, 트랜잭션 경계)
   - 의도적으로 제외한 것
   - 주의사항 (race condition, EventLoop blocking 등)
3. 초안과 **모호한 논의점**을 사용자에게 제시한다.
4. 사용자 피드백을 반영하여 `design-intent.md`를 확정한다.
5. worktree를 정리한다.

### [F5] 평가기준 수립 (Fork + Sub-agent)

1. **worktree(fork)를 생성**한다.
2. **sub-agent를 호출**하여 `docs/adr.yaml`에서 관련 항목을 추출한다:
   - stacks 필드로 1차 필터
   - context/decision 내용으로 2차 판단
   - 관련 없는 항목은 제외
3. `docs/code-convention.yaml`에서 관련 규칙을 필터링한다 (TS-, EXP-, REPO-, TEST- 등).
4. convention(공통 기준) + ADR(작업별 기준)을 병합하여 `code-quality-guide.md` 초안을 작성한다.
5. 초안과 **기준 적용 범위 논의점**을 사용자에게 제시한다.
6. 사용자 피드백을 반영하여 확정한다.
7. worktree를 정리한다.

### [F6] [TDD Red] 실패 테스트 작성 (Fork)

1. **worktree(fork)를 생성**한다.
2. `requirements.md`의 MUST 수용기준을 실행 가능한 Jest 테스트로 변환한다.
   - 테스트 파일: `src/__tests__/{module}.feature.{branch-name}.test.ts` (factory 또는 test fixture 사용)
   - 하나의 수용기준(AC) = 하나의 테스트 케이스
3. `npm test -- --testPathPattern={module}.feature.{branch-name}`으로 실행하여 FAIL을 확인한다.
4. FAIL 출력 tail 30줄을 `.harness-artifacts/feature/{branch-name}/tdd-baseline-log.txt`에 저장한다.
5. 실패 이유가 "올바른 이유"인지 검증한다. 자세한 검증 규칙과 재작성 루프(최대 3회)는 `commands/shared/tdd.md` 참조:
   - 구현 부재로 인한 FAIL → 올바른 Red → F7로 진행
   - TypeScript 컴파일 / import / mock 오류 → Red 아님. 테스트를 수정 후 재실행 (최대 3회). 3회 후에도 올바르지 않으면 `tdd-red-debug.md`에 기록하고 사용자에게 보고.
6. worktree를 정리한다.

### [F7] [TDD Green] 최소 구현 (Fork)

1. **worktree(fork)를 생성**한다.
2. F6에서 작성한 테스트가 PASS되도록 **최소한의 코드만** 작성한다.
   - 범위 폭주 금지: Red 테스트가 요구하지 않는 코드 추가 금지
3. 기존 테스트 회귀를 확인한다: `npm test` (전체 스위트)
4. 추가 검증: `npm run typecheck && npm run lint`
5. PASS 로그를 `.harness-artifacts/feature/{branch-name}/tdd-green-log.txt`에 저장한다.
6. **Red이 틀렸음을 발견한 경우**: Green 구현 중 수용기준 자체가 잘못되었다는 증거가 나오면 구현을 즉시 중단하고 사용자에게 Red 재작성을 제안. 승인 시 F6으로 복귀. 테스트를 임의로 수정 금지. 자세한 프로토콜은 `commands/shared/tdd.md` 참조.
7. worktree를 정리한다.

### [F8] [TDD Refactor] 코드 정리 (Fork)

1. **worktree(fork)를 생성**한다.
2. Green 상태를 확인한 후 시작한다 (모든 테스트 PASS 상태여야 함).
3. 중복 제거, 네이밍 개선, 구조 정리를 수행한다.
   - **새 기능 금지, 테스트 변경 금지**
4. 각 리팩토링 후 `npm test`로 전체 그린을 확인한다. 깨지면 즉시 revert.
5. 변경 내용을 `.harness-artifacts/feature/{branch-name}/tdd-refactor-notes.md`에 요약한다.
   - 리팩토링할 내용이 없으면: "skipped: no refactoring needed — baseline clean"
6. worktree를 정리한다.

### [F9] PR 본문 생성 (Fork)

1. **worktree(fork)를 생성**하여 PR 본문을 작성한다.
2. `git diff main...HEAD` 기반으로 변경 내용을 분석한다.
3. PR 본문 구조:
   - Summary (1-3문장)
   - Changes (모듈 단위: controllers/services/repositories/routes/websocket 등)
   - Breaking Changes
   - Test Plan (Jest 테스트 + 수동 시나리오)
   - Migration (DB 또는 BE 연동 변경)
   - Related (이슈, ADR, 설계 문서)
4. 초안과 논의점을 사용자에게 제시한다.
5. `pr-body.md`를 확정하고 저장한다.
6. worktree를 정리한다.

### [F10] 코드리뷰 (Sub-agent)

1. **sub-agent를 호출**하여 코드리뷰를 수행한다.
2. 입력:
   - `code-quality-guide.md`
   - `design-intent.md`
   - `pr-body.md`
   - **F6 Red 테스트 파일** (`src/__tests__/{module}.feature.{branch-name}.test.ts`)
   - **F7 Green 구현** (`git diff main...HEAD`)
   - **TDD 증거 파일**: `.harness-artifacts/feature/{branch-name}/tdd-baseline-log.txt` (Red FAIL 증거) + `tdd-green-log.txt` (Green PASS 증거). 리뷰어는 이 두 파일이 실제로 F6 Red 테스트와 F7 Green diff에 대응하는지 **교차검증**한다 — test 이름, module 경로, FAIL→PASS 전환 방향. 불일치 시 [p1] 이슈로 보고.
3. 리뷰 원칙:
   - 의도를 파악하고, 비판적으로 검토
   - 모든 코멘트는 code-quality-guide.md에 근거
   - 의도적 결정을 존중. 의도-구현 불일치는 지적.
   - **테스트-구현 정합성 확인**: 테스트가 의도한 동작을 실제로 검증하는지 확인
   - 우선순위 분류: [p1] 필수 / [p2] 강력 권장 / [p3] 권장 / [p4] 사소
   - side effect가 있으면 반드시 설명
4. `review-comments.md`를 저장한다.
5. **사용자 확인 없이 자동 진행.**

### [F11] 리뷰 반영 + QA (Fork)

1. **worktree(fork)를 생성**하여 리뷰를 반영한다.
2. 각 코멘트의 수용/거부 판단을 사용자에게 제시:
   - [p1]: 기본 수용. 거부 시 명확한 근거 필수.
   - [p2]: 판단과 근거 제시, 사용자 확인.
   - [p3]: 사용자 재량.
   - [p4]: 일괄 처리.
3. 사용자 확인 후 코드를 수정한다.
4. QA 수행:
   - `tsc --noEmit` (TypeScript strict 컴파일 검사)
   - `npm run lint` (ESLint)
   - `npm test -- src/__tests__/{module}` (관련 모듈 테스트)
   - `npm test` (전체 회귀, 필요 시)
   - `tdd-green-log.txt`가 여전히 PASS 상태인지 재확인한다.
5. 버그 발견 시 수정 루프.
6. 핵심 변경사항을 사용자에게 보고한다.

### 완료

`INDEX.md`를 생성하여 다음을 기록:
- 산출물 목록
- 생성/변경된 파일 목록
- 마이그레이션 파일 목록 (있으면)
- 테스트 결과 요약
- 커밋 메시지 제안

## 산출물

```
.harness-artifacts/feature/{branch-name}/
  requirements.md
  prior-art.md
  design-intent.md
  code-quality-guide.md
  tdd-baseline-log.txt
  tdd-green-log.txt
  tdd-refactor-notes.md
  tdd-red-revisions.md     (선택: Green→Red 복귀가 발생했을 때만 생성)
  tdd-red-debug.md         (선택: Red 재시도가 발생했을 때만 생성)
  pr-body.md
  review-comments.md
  INDEX.md
```
