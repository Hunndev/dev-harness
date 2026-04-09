# 신규개발 파이프라인 (T1 standard)

새 기능을 **lightweight** 흐름으로 설계·구현·리뷰까지 끌고 간다.

> **Tier 선택**
> - `/hb-be:feature:auto` — **이 문서.** 일반 기능 기본값. F3 유사 구현 조사, F5 평가기준 재생성, F9 PR본문 Fork를 생략한다.
> - `/hb-be:feature:deep` — F1~F11 full ceremony. 복잡 기능, 모듈 간 상호작용이 크거나 PR 문서화가 중요할 때 사용.

## 사전 조건

- `.harness/docs/code-convention.yaml`과 `.harness/docs/adr.yaml`이 작성되어 있어야 한다.
- 요구사항이 확정되어 있어야 한다. 확정되지 않았으면 `/hb-be:planning:auto` 또는 `:deep`으로.
- feature branch 또는 새로 생성할 branch.

## 식별자

`git branch --show-current`로 resolve. 없으면 `feature/{issue}-{short-desc}` 형식으로 생성.

## 핵심 원칙

- **(deep의) F3 유사 구현 조사 없음**: 명백한 재사용 대상이 없거나 소규모 모듈 추가 시 사용. 기존 코드 분석이 중요하면 `:deep`.
- **(deep의) F5 평가기준 재생성 없음**: 기존 `code-convention.yaml` + 관련 ADR을 (deep의) F10 리뷰 시점에 직접 참조한다. 과거에 같은 영역의 `code-quality-guide.md`가 있으면 그대로 재사용.
- **(deep의) F9 PR본문 Fork 없음**: PR 본문은 (deep의) F11 완료 보고 시점에 간단 템플릿으로 바로 생성한다.
- **Agent Team 없음**: (deep도 동일)

## 파이프라인

### [F1] 상태 점검 (메인)

1. **Pre-flight 점검**: `commands/shared/tdd.md`의 "Pre-flight 점검" 섹션을 수행한다:
   - `pytest --collect-only -q` → exit 0 확인 (아니면 중단 + 사용자 보고)
   - 아티팩트 디렉토리의 stale `tdd-red-debug.md`, `tdd-red-revisions.md` 삭제
2. `git branch --show-current`로 현재 branch를 확인한다.
3. `git diff main...HEAD --stat`으로 변경 파일 목록을 확인한다 (있으면).
4. 사용자에게 다음을 확인한다:
   - branch명
   - base branch (기본: `main`)
   - 변경 파일 수 (있으면)
5. `.harness/artifacts/feature/{branch-name}/` 디렉토리를 생성한다.
6. 기존 `code-quality-guide.md`가 같은 영역에 이미 있는지 확인하고, 있으면 재사용 후보로 표시한다.

### [F2] 요구사항 정리 (Fork)

1. worktree(fork)를 생성한다.
2. planning 트랙의 산출물이 있으면 가져온다:
   - `requirements-interview.md` 또는 `feasibility.md` → 요약
   - `decision-draft.md` 또는 관련 `.harness/docs/adr.yaml` 항목 → 참조
3. 없으면 사용자에게 질문하여 수집한다.
4. 요구사항을 MUST / SHOULD / NICE로 분류한다.
5. `requirements.md`를 저장한다.
6. worktree를 정리한다.

### [F3] 설계의도 작성 (Fork) _(deep의 F4에 해당)_

1. worktree(fork)를 생성한다.
2. 아래 내용을 포함하는 문서를 작성:
   - 작업 개요
   - 핵심 설계 결정과 트레이드오프
   - 의도적으로 제외한 것
   - 주의사항
3. 초안과 **모호한 논의점**을 사용자에게 제시한다.
4. 사용자 피드백을 반영하여 `design-intent.md`를 확정한다.
5. worktree를 정리한다.

### [F4] [TDD Red] 실패 테스트 작성 (Fork) _(deep의 F6에 해당)_

1. worktree(fork)를 생성한다.
2. `requirements.md`의 MUST 수용기준을 실행 가능한 pytest 테스트로 변환한다.
   - 테스트 파일: `tests/test_{module}_feature_{branch-name}.py` (factory_boy 활용)
   - 하나의 수용기준(AC) = 하나의 테스트 함수
3. `pytest {app}/tests/test_{module}_feature_*.py -v`로 실행하여 FAIL을 확인한다.
4. FAIL 출력 tail 30줄을 `.harness/artifacts/feature/{branch-name}/tdd-baseline-log.txt`에 저장한다.
5. 실패 이유가 "올바른 이유"인지 검증한다. 자세한 검증 규칙과 재작성 루프(최대 3회)는 `commands/shared/tdd.md` 참조:
   - 구현 부재로 인한 FAIL → 올바른 Red → F5로 진행
   - syntax / import / fixture 오류 → Red 아님. 테스트를 수정 후 재실행 (최대 3회). 3회 후에도 올바르지 않으면 `tdd-red-debug.md`에 기록하고 사용자에게 보고.
6. worktree를 정리한다.

### [F5] [TDD Green] 최소 구현 (Fork) _(deep의 F7에 해당)_

1. worktree(fork)를 생성한다.
2. F4에서 작성한 테스트가 PASS되도록 **최소한의 코드만** 작성한다.
   - 범위 폭주 금지: Red 테스트가 요구하지 않는 코드 추가 금지
3. 기존 테스트 회귀를 확인한다: `pytest {app}/tests/ -v`
4. 추가 검증: `python manage.py check`
5. PASS 로그를 `.harness/artifacts/feature/{branch-name}/tdd-green-log.txt`에 저장한다.
6. **Red이 틀렸음을 발견한 경우**: Green 구현 중 수용기준 자체가 잘못되었다는 증거가 나오면 구현을 즉시 중단하고 사용자에게 Red 재작성을 제안. 승인 시 F4로 복귀. 테스트를 임의로 수정 금지. 자세한 프로토콜은 `commands/shared/tdd.md` 참조.
7. worktree를 정리한다.

### [F6] [TDD Refactor] 코드 정리 (Fork) _(deep의 F8에 해당)_

1. worktree(fork)를 생성한다.
2. Green 상태를 확인한 후 시작한다 (모든 테스트 PASS 상태여야 함).
3. 중복 제거, 네이밍 개선, 구조 정리를 수행한다.
   - **새 기능 금지, 테스트 변경 금지**
4. 각 리팩토링 후 `pytest {app}/tests/ -v`로 전체 그린을 확인한다. 깨지면 즉시 revert.
5. 변경 내용을 `.harness/artifacts/feature/{branch-name}/tdd-refactor-notes.md`에 요약한다.
   - 리팩토링할 내용이 없으면: "skipped: no refactoring needed — baseline clean"
6. worktree를 정리한다.

### [F7] 코드리뷰 (Sub-agent) _(deep의 F10에 해당)_

1. sub-agent를 호출하여 코드리뷰를 수행한다.
2. 입력:
   - `design-intent.md` (의도)
   - **F4 Red 테스트 파일** (`tests/test_{module}_feature_{branch-name}.py`)
   - **F5 Green 구현** (`git diff main...HEAD`)
   - **TDD 증거 파일**: `.harness/artifacts/feature/{branch-name}/tdd-baseline-log.txt` (Red FAIL 증거) + `tdd-green-log.txt` (Green PASS 증거). 리뷰어는 이 두 파일이 실제로 F4 Red 테스트와 F5 Green diff에 대응하는지 **교차검증**한다 — test 이름, module 경로, FAIL→PASS 전환 방향. 불일치 시 [p1] 이슈로 보고.
   - **기준 선택 로직**:
     - 기존 `code-quality-guide.md`가 있으면 그대로 사용
     - 없으면 `.harness/docs/code-convention.yaml` + `.harness/docs/adr.yaml`에서 관련 stacks로 1차 필터
3. 리뷰 원칙:
   - 모든 코멘트는 convention/ADR에 근거
   - 의도적 결정은 존중, 의도-구현 불일치는 지적
   - **테스트-구현 정합성 확인**: 테스트가 의도한 동작을 실제로 검증하는지 확인
   - 우선순위: [p1] 필수 / [p2] 강력 권장 / [p3] 권장 / [p4] 사소
   - side effect가 있으면 반드시 설명
4. `review-comments.md`를 저장한다.
5. **사용자 확인 없이 자동 진행.**

### [F8] 리뷰 반영 + QA (Fork) _(deep의 F11에 해당)_

1. worktree(fork)를 생성한다.
2. 각 코멘트의 수용/거부 판단을 사용자에게 제시:
   - [p1]: 기본 수용. 거부 시 명확한 근거 필수.
   - [p2]: 판단과 근거 제시, 사용자 확인.
   - [p3]: 사용자 재량.
   - [p4]: 일괄 처리.
3. 사용자 확인 후 코드를 수정한다.
4. QA 수행:
   - `python manage.py check`
   - `python manage.py makemigrations --check`
   - `pytest {app}/tests/ -v`
   - `tdd-green-log.txt`가 여전히 PASS 상태인지 재확인한다.
5. 버그 발견 시 수정 루프.
6. 간이 PR 본문을 생성하여 사용자에게 제시:
   - Summary (1~3문장)
   - Changes (모듈 단위)
   - Test Plan
   - Related (ADR, 설계 문서)
7. `pr-body.md`를 저장한다.

### 완료

`INDEX.md`를 생성하여 다음을 기록:
- 산출물 목록
- 생성/변경된 파일 목록
- 마이그레이션 파일 목록 (있으면 별도 리뷰 대상)
- 테스트 결과 요약
- 커밋 메시지 제안
- tier 정보 (`tier: auto`)

## 산출물

```
.harness/artifacts/feature/{branch-name}/
  requirements.md
  design-intent.md
  tdd-baseline-log.txt
  tdd-green-log.txt
  tdd-refactor-notes.md
  tdd-red-revisions.md     (선택: Green→Red 복귀가 발생했을 때만 생성)
  tdd-red-debug.md         (선택: Red 재시도가 발생했을 때만 생성)
  review-comments.md
  pr-body.md
  INDEX.md
```

> `auto` tier는 `prior-art.md`, `code-quality-guide.md`를 생성하지 않는다.
> 이 두 파일이 필요하면 `:deep`으로 재시작하거나, 수동으로 생성 후 F7이 재사용하도록 한다.

## 언제 deep으로 전환해야 하는가

- 기존 코드베이스의 유사 구현과 충돌 위험이 크다 → F3 prior-art 필요
- 이번 feature 특유의 품질 기준이 많다 → F5 code-quality-guide 재생성 필요
- PR 본문이 외부 stakeholder에게 전달되어야 한다 → F9 PR본문 Fork 필요
- 여러 모듈을 동시에 건드리는 대형 변경이다
