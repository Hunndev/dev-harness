# 기획 파이프라인

"무엇을, 왜 만들 것인가"를 결정한다. 코드는 아직 손대지 않는다.

## 사전 조건

- 사용자가 만들고 싶은 것의 대략적인 방향을 제시해야 한다. 확정되지 않아도 된다.
- 코드가 아직 없을 수 있다 → 코드 기반 단계는 skip 가능.

## 식별자

branch가 없을 수 있으므로 `plan-YYYYMMDD-slug` 형식을 사용한다.
예: `plan-20260406-tour-booking-redesign`

## 파이프라인

### [P1] 스코프 + 이해관계자 맵 (Fork)

1. 사용자가 제시한 방향을 정리한다.
2. 다음을 사용자와 함께 확정한다:
   - 이 기획의 범위 (무엇을 결정할 것인가)
   - 범위 밖 (무엇은 이번에 결정하지 않는가)
   - 이해관계자 맵 (누가 이 결정에 영향을 받는가)
     - 사용자 유형별 (프리다이버, 강사, 관리자)
     - 시스템 유형별 (프론트엔드, 백엔드, 인프라, 외부 서비스)
   - **모호한 논의점** 제시
3. 식별자를 생성한다: `plan-YYYYMMDD-{slug}`
4. `.harness-artifacts/planning/{identifier}/` 디렉토리를 생성한다.
5. `scope.md`와 `stakeholders.md`를 저장한다.

### [P2] 요구사항 인터뷰 정리 (Fork)

1. 사용자에게 구조화된 질문을 던져 요구사항을 수집한다.
2. 질문 프레임:
   - "이 기능이 없으면 누가 어떤 문제를 겪는가?"
   - "가장 단순한 형태로 만든다면 어떤 모습인가?"
   - "반드시 있어야 하는 것(MUST)과 있으면 좋은 것(NICE)은?"
   - "기존 시스템과 어떻게 연결되어야 하는가?"
   - "성능/규모 요구사항은?" (동시 사용자, 데이터 양)
3. 수집된 요구사항을 MUST / SHOULD / NICE로 분류한다.
4. `docs/module-registry.yaml`이 있으면 읽고, 기존 모듈과의 관계를 파악한다.
5. **모호한 요구사항**과 **충돌하는 요구사항**을 명시적으로 정리한다.
6. `requirements-interview.md`를 저장한다.

### [P3] 외부 사례/문서 조사 (Sub-agent)

1. **sub-agent를 호출**하여 외부 조사를 수행한다.
2. sub-agent에게 다음을 전달한다:
   - `scope.md`
   - `requirements-interview.md`
3. sub-agent는 다음을 조사한다:
   - 유사 서비스/기능의 구현 사례
   - 관련 기술 문서, 라이브러리, API
   - 알려진 함정이나 안티패턴
   - BucclApp 스택(Django/DRF)에서의 구현 가능성
4. `external-research.md`를 저장한다.
5. **사용자 확인 없이 자동으로 진행한다.**

### [P4] 대안 분석 — 3관점 병렬 (Agent Team) ★

1. **Agent Team을 호출**하여 3개 관점에서 동시에 대안을 분석한다.
2. 각 에이전트는 독립적으로 작업한다:

#### Agent A: 기술 실현성
```
다음 요구사항과 외부 조사 결과를 바탕으로, 기술적 대안을 분석하라.

분석 항목:
1. 각 대안의 구현 방법 (Django/DRF 기준)
2. 기존 모듈(module-registry.yaml)과의 호환성
3. 기술적 위험 요소와 복잡도
4. 의존성 추가 필요 여부

[scope.md]
[requirements-interview.md]
[external-research.md]
[module-registry.yaml] (있으면)
[architecture.yaml] (있으면)
```

#### Agent B: UX/제품 관점
```
다음 요구사항을 바탕으로, 사용자 경험 관점에서 대안을 분석하라.

분석 항목:
1. 각 대안이 사용자(프리다이버/강사/관리자)에게 미치는 영향
2. WebView 하이브리드 앱에서의 UX 제약
3. 기존 사용 흐름과의 일관성
4. 학습 비용과 전환 비용

[scope.md]
[requirements-interview.md]
[stakeholders.md]
```

#### Agent C: 비용/일정/리스크
```
다음 요구사항을 바탕으로, 비용·일정·리스크 관점에서 대안을 분석하라.

분석 항목:
1. 각 대안의 예상 구현 공수 (1인 개발 기준)
2. Azure 인프라 비용 변동
3. 외부 서비스(Innopay 등) 연동 비용/계약 변경
4. 각 대안의 실패 리스크와 되돌리기 비용

[scope.md]
[requirements-interview.md]
[architecture.yaml] (있으면)
```

3. **메인이 3개 결과를 병합**한다:
   - 관점 간 충돌/모순을 식별한다.
   - 대안별로 3관점 평가를 통합 정리한다.
   - 충돌이 있으면 사용자에게 제시하고 판단을 요청한다.
4. `alternatives.md`를 저장한다.

### [P5] 타당성 리포트 (Fork)

1. 지금까지의 산출물을 종합하여 타당성 리포트를 작성한다.
2. 리포트에 포함할 내용:
   - 추천 대안과 근거
   - 각 대안의 장단점 비교표
   - Go/No-Go 판단 기준
   - 남은 불확실성과 해소 방법
3. 초안을 사용자에게 제시하고 피드백을 반영한다.
4. `feasibility.md`를 저장한다.

### [P6] ADR 드래프트 (Fork)

1. 확정된 대안을 `docs/adr.yaml` 형식의 드래프트로 작성한다.
2. ADR context 작성 가이드라인을 따른다:
   - context만 읽고도 "왜 이 결정이 필요했는가"를 연상할 수 있어야 한다.
   - 당시 어떤 문제가 있었는지, 어떤 대안을 검토했는지, 왜 이 선택이 최적인지를 구체적으로 서술한다.
3. **이 단계에서 adr.yaml에 자동 편입하지 않는다.**
4. `decision-draft.md`를 저장한다.
5. 사용자에게 드래프트를 제시하고, adr.yaml 편입 여부를 확인한다.

### [P7] ADR 편입 (메인, 사용자 승인)

1. 사용자가 명시적으로 승인한 경우에만 실행한다.
2. `/buccl:update-docs adr`을 호출하여 `decision-draft.md` 내용을 `docs/adr.yaml`에 편입한다.
3. 기존 ADR/convention과의 충돌을 체크한다.
4. 편입 결과를 사용자에게 보고한다.

### 완료

파이프라인이 완료되면 `INDEX.md`를 생성하여 다음을 기록한다:
- 산출물 목록과 각 파일의 상태 (초안/확정)
- 결정 사항 요약
- 후속 작업 (feature 트랙으로 이동 여부)

## 산출물

```
.harness-artifacts/planning/{identifier}/
  scope.md
  stakeholders.md
  requirements-interview.md
  external-research.md
  alternatives.md              ← Team 3명이 섹션별 작성 → 메인이 병합
  feasibility.md
  decision-draft.md            ← adr.yaml 후보. 자동 편입 금지.
  INDEX.md
```
