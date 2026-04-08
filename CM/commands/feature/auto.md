# 신규개발 파이프라인 (T1 standard)

새 기능을 **lightweight** 흐름으로 설계·구현·리뷰까지 끌고 간다.

> **Tier 선택**
> - `/hb-cm:feature:auto` — **이 문서.** 일반 기능 기본값. F3 유사 구현 조사, F5 평가기준 재생성, F6 PR본문 Fork를 생략한다.
> - `/hb-cm:feature:deep` — F1~F8 full ceremony. 복잡 기능, 이벤트 흐름 상호작용이 크거나 PR 문서화가 중요할 때 사용.

## 사전 조건

- `docs/code-convention.yaml`과 `docs/adr.yaml`이 작성되어 있어야 한다.
- 요구사항이 확정되어 있어야 한다. 확정되지 않았으면 `/hb-cm:planning:auto` 또는 `:deep`으로.
- feature branch 또는 새로 생성할 branch.

## 식별자

`git branch --show-current`로 resolve. 없으면 `feature/{issue}-{short-desc}` 형식으로 생성.

## 핵심 원칙

- **(deep의) F3 유사 구현 조사 없음**: 명백한 재사용 대상이 없거나 소규모 모듈 추가 시 사용. 기존 코드 분석이 중요하면 `:deep`.
- **(deep의) F5 평가기준 재생성 없음**: 기존 `code-convention.yaml` + 관련 ADR을 (deep의) F7 리뷰 시점에 직접 참조한다. 과거에 같은 영역의 `code-quality-guide.md`가 있으면 그대로 재사용.
- **(deep의) F6 PR본문 Fork 없음**: PR 본문은 (deep의) F8 완료 보고 시점에 간단 템플릿으로 바로 생성한다.
- **Agent Team 없음**: (deep도 동일)

## 파이프라인

### [F1] 상태 점검 (메인)

1. `git branch --show-current`로 현재 branch를 확인한다.
2. `git diff main...HEAD --stat`으로 변경 파일 목록을 확인한다 (있으면).
3. 사용자에게 다음을 확인한다:
   - branch명
   - base branch (기본: `main`)
   - 변경 파일 수 (있으면)
4. `.harness-artifacts/feature/{branch-name}/` 디렉토리를 생성한다.
5. 기존 `code-quality-guide.md`가 같은 영역에 이미 있는지 확인하고, 있으면 재사용 후보로 표시한다.

### [F2] 요구사항 정리 (Fork)

1. worktree(fork)를 생성한다.
2. planning 트랙의 산출물이 있으면 가져온다:
   - `requirements-interview.md` 또는 `feasibility.md` → 요약
   - `decision-draft.md` 또는 관련 `docs/adr.yaml` 항목 → 참조
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
   - 주의사항 (Socket.io 이벤트 흐름 영향 포함)
3. 초안과 **모호한 논의점**을 사용자에게 제시한다.
4. 사용자 피드백을 반영하여 `design-intent.md`를 확정한다.
5. worktree를 정리한다.

### [F4] 코드리뷰 (Sub-agent) _(deep의 F7에 해당)_

1. sub-agent를 호출하여 코드리뷰를 수행한다.
2. 입력:
   - `design-intent.md` (의도)
   - **기준 선택 로직**:
     - 기존 `code-quality-guide.md`가 있으면 그대로 사용
     - 없으면 `docs/code-convention.yaml` + `docs/adr.yaml`에서 관련 stacks로 1차 필터
   - `git diff main...HEAD`
3. 리뷰 원칙:
   - 모든 코멘트는 convention/ADR에 근거
   - SQL은 parameterized(`?`)만 사용, 문자열 concatenation 금지
   - Socket.io 이벤트 흐름 누락/중복 확인
   - 우선순위: [p1] 필수 / [p2] 강력 권장 / [p3] 권장 / [p4] 사소
4. `review-comments.md`를 저장한다.
5. **사용자 확인 없이 자동 진행.**

### [F5] 리뷰 반영 + QA (Fork) _(deep의 F8에 해당)_

1. worktree(fork)를 생성한다.
2. 각 코멘트의 수용/거부 판단을 사용자에게 제시:
   - [p1]: 기본 수용. 거부 시 명확한 근거 필수.
   - [p2]: 판단과 근거 제시, 사용자 확인.
   - [p3]: 사용자 재량.
   - [p4]: 일괄 처리.
3. 사용자 확인 후 코드를 수정한다.
4. QA 수행:
   - `npm run typecheck`
   - `npm run lint`
   - `npm test`
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
- 테스트 결과 요약
- 커밋 메시지 제안
- tier 정보 (`tier: auto`)

## 산출물

```
.harness-artifacts/feature/{branch-name}/
  requirements.md
  design-intent.md
  review-comments.md
  pr-body.md
  INDEX.md
```

> `auto` tier는 `prior-art.md`, `code-quality-guide.md`를 생성하지 않는다.
> 이 두 파일이 필요하면 `:deep`으로 재시작하거나, 수동으로 생성 후 F4가 재사용하도록 한다.

## 언제 deep으로 전환해야 하는가

- 기존 코드베이스의 유사 구현과 충돌 위험이 크다 → F3 prior-art 필요
- 이번 feature 특유의 품질 기준이 많다 → F5 code-quality-guide 재생성 필요
- PR 본문이 외부 stakeholder에게 전달되어야 한다 → F6 PR본문 Fork 필요
- 여러 이벤트 흐름을 동시에 건드리는 대형 변경이다
