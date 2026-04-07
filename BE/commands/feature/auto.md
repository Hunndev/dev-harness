# 신규개발 파이프라인

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

## 파이프라인

### [F1] 상태 점검 (메인)

1. `git branch --show-current`로 현재 branch를 확인한다.
2. `git diff main...HEAD --stat`으로 변경 파일 목록을 확인한다 (기존 코드가 있으면).
3. 사용자에게 다음을 확인한다:
   - branch명
   - base branch (기본: `main`)
   - 변경 파일 수 (있으면)
4. `.harness-artifacts/feature/{branch-name}/` 디렉토리를 생성한다.

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
   - 기존 코드 (관련 모듈)
3. sub-agent는 다음을 조사:
   - 기존 코드에 비슷한 패턴이 이미 있는가? (재사용 가능성)
   - 기존 모델/시리얼라이저/뷰를 확장할 수 있는가?
   - 기존 코드와 충돌할 가능성이 있는 부분은?
4. `prior-art.md`를 저장한다.
5. **사용자 확인 없이 자동 진행.**

### [F4] 설계의도 작성 (Fork)

1. **worktree(fork)를 생성**하여 설계의도 문서를 작성한다.
2. 아래 내용을 포함:
   - 작업 개요
   - 핵심 설계 결정과 트레이드오프
   - 의도적으로 제외한 것
   - 주의사항
3. 초안과 **모호한 논의점**을 사용자에게 제시한다.
4. 사용자 피드백을 반영하여 `design-intent.md`를 확정한다.
5. worktree를 정리한다.

### [F5] 평가기준 수립 (Fork + Sub-agent)

1. **worktree(fork)를 생성**한다.
2. **sub-agent를 호출**하여 `docs/adr.yaml`에서 관련 항목을 추출한다:
   - stacks 필드로 1차 필터
   - context/decision 내용으로 2차 판단
   - 관련 없는 항목은 제외
3. `docs/code-convention.yaml`에서 관련 규칙을 필터링한다.
4. convention(공통 기준) + ADR(작업별 기준)을 병합하여 `code-quality-guide.md` 초안을 작성한다.
5. 초안과 **기준 적용 범위 논의점**을 사용자에게 제시한다.
6. 사용자 피드백을 반영하여 확정한다.
7. worktree를 정리한다.

### [F6] PR 본문 생성 (Fork)

1. **worktree(fork)를 생성**하여 PR 본문을 작성한다.
2. `git diff main...HEAD` 기반으로 변경 내용을 분석한다.
3. PR 본문 구조:
   - Summary (1-3문장)
   - Changes (모듈 단위)
   - Breaking Changes
   - Test Plan
   - Related (이슈, ADR, 설계 문서)
4. 초안과 논의점을 사용자에게 제시한다.
5. `pr-body.md`를 확정하고 저장한다.
6. worktree를 정리한다.

### [F7] 코드리뷰 (Sub-agent)

1. **sub-agent를 호출**하여 코드리뷰를 수행한다.
2. 입력:
   - `code-quality-guide.md`
   - `design-intent.md`
   - `pr-body.md`
   - `git diff main...HEAD`
3. 리뷰 원칙:
   - 의도를 파악하고, 비판적으로 검토
   - 모든 코멘트는 code-quality-guide.md에 근거
   - 의도적 결정을 존중. 의도-구현 불일치는 지적.
   - 우선순위 분류: [p1] 필수 / [p2] 강력 권장 / [p3] 권장 / [p4] 사소
   - side effect가 있으면 반드시 설명
4. `review-comments.md`를 저장한다.
5. **사용자 확인 없이 자동 진행.**

### [F8] 리뷰 반영 + QA (Fork)

1. **worktree(fork)를 생성**하여 리뷰를 반영한다.
2. 각 코멘트의 수용/거부 판단을 사용자에게 제시:
   - [p1]: 기본 수용. 거부 시 명확한 근거 필수.
   - [p2]: 판단과 근거 제시, 사용자 확인.
   - [p3]: 사용자 재량.
   - [p4]: 일괄 처리.
3. 사용자 확인 후 코드를 수정한다.
4. QA 수행:
   - `python manage.py check`
   - `python manage.py makemigrations --check`
   - `python manage.py test {app}`
5. 버그 발견 시 수정 루프.
6. 핵심 변경사항을 사용자에게 보고한다.

### 완료

`INDEX.md`를 생성하여 다음을 기록:
- 산출물 목록
- 생성/변경된 파일 목록
- 마이그레이션 파일 목록
- 테스트 결과 요약
- 커밋 메시지 제안

## 산출물

```
.harness-artifacts/feature/{branch-name}/
  requirements.md
  prior-art.md
  design-intent.md
  code-quality-guide.md
  pr-body.md
  review-comments.md
  INDEX.md
```
