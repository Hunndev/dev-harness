# 기획 파이프라인 (T1 standard)

"무엇을, 왜 만들 것인가"를 빠르게 결정하는 **lightweight** 기획 흐름.

> **Tier 선택**
> - `/hb-be:planning:auto` — **이 문서.** 일상 기획 기본값. 인터뷰/외부 조사/3관점 대안 분석 없음.
> - `/hb-be:planning:deep` — 인터뷰(P2) + 외부 조사(P3) + 3관점 Agent Team 대안 분석(P4)까지 포함하는 full ceremony. 아키텍처급 결정에 사용.
>
> 어느 쪽이든 최종 산출물은 `decision-draft.md` → 사용자 승인 → `/hb-be:shared:update-docs adr`로 `.harness/docs/adr.yaml`에 편입된다.

## 사전 조건

- 사용자가 만들고 싶은 것의 대략적인 방향을 제시해야 한다.
- 코드가 아직 없어도 된다.

## 식별자

`plan-YYYYMMDD-slug` 형식.
예: `plan-20260408-tour-booking-redesign`

## 핵심 원칙

- **간이 기획**: 대안이 1~2개로 명확하거나, 사용자가 이미 방향을 굳힌 경우에 사용.
- **3관점 Team 없음**: 기술·UX·비용 3관점 병렬 분석이 필요한 수준이면 `:deep`으로 전환한다.
- **ADR 자동 편입 금지**: P4(P7 in deep)의 편입은 이 tier에서도 반드시 사용자 승인 게이트를 거친다.

## 파이프라인

### [P1] 스코프 + 이해관계자 맵 (Fork)

1. 사용자가 제시한 방향을 정리한다.
2. 다음을 사용자와 함께 확정한다:
   - 이 기획의 범위 (무엇을 결정할 것인가)
   - 범위 밖 (무엇은 이번에 결정하지 않는가)
   - 이해관계자 맵 (간략: 영향받는 사용자 유형 + 시스템 컴포넌트)
   - **모호한 논의점** 명시
3. 식별자를 생성한다: `plan-YYYYMMDD-{slug}`
4. `.harness/artifacts/planning/{identifier}/` 디렉토리를 생성한다.
5. `scope.md`와 `stakeholders.md`를 저장한다.

### [P2] 타당성 판단 (Fork) _(deep의 P5에 해당)_

`auto` tier는 deep의 P2 인터뷰 · P3 외부 조사 · P4 3관점 Team을 전부 건너뛰고 **P1 정보만으로 바로 타당성 판단**으로 들어간다.

1. P1 산출물만으로 다음을 결정한다:
   - 추천 방향과 근거 (1~2개 대안 중 선택)
   - Go/No-Go 판단
   - 남은 불확실성과 **해소를 위해 deep 모드가 필요한지 여부**
2. 불확실성이 크고 3관점 분석이 필요하면 여기서 중단하고 `/hb-be:planning:deep`으로 전환을 제안한다.
3. 사용자 피드백 반영 후 `feasibility.md`를 저장한다.

### [P3] ADR 드래프트 (Fork) _(deep의 P6에 해당)_

1. 확정된 방향을 `.harness/docs/adr.yaml` 형식의 드래프트로 작성한다.
2. ADR context 작성 가이드라인:
   - "왜 이 결정이 필요했는가"를 구체적으로 서술
   - 당시 문제, 대안, 선택 이유를 포함
3. **이 단계에서 adr.yaml에 자동 편입하지 않는다.**
4. `decision-draft.md`를 저장한다.
5. 사용자에게 드래프트를 제시하고 편입 여부를 확인한다.

### [P4] ADR 편입 (메인, 사용자 승인) _(deep의 P7에 해당)_

1. 사용자가 명시적으로 승인한 경우에만 실행한다.
2. `/hb-be:shared:update-docs adr`을 호출하여 `decision-draft.md` 내용을 `.harness/docs/adr.yaml`에 편입한다.
3. 기존 ADR/convention과의 충돌을 체크한다.
4. 편입 결과를 사용자에게 보고한다.

### 완료

`INDEX.md`를 생성하여 다음을 기록한다:
- 산출물 목록과 각 파일의 상태 (초안/확정)
- 결정 사항 요약
- tier 정보 (`tier: auto`)
- 후속 작업 (feature 트랙으로 이동 여부)

## 산출물

```
.harness/artifacts/planning/{identifier}/
  scope.md
  stakeholders.md
  feasibility.md
  decision-draft.md            ← adr.yaml 후보. 자동 편입 금지.
  INDEX.md
```

> `auto` tier 산출물은 `deep` tier 산출물의 **부분집합**이다.
> `requirements-interview.md`, `external-research.md`, `alternatives.md`는 deep에서만 생성된다.

## 언제 deep으로 전환해야 하는가

다음 중 하나라도 해당하면 P2에서 중단하고 `/hb-be:planning:deep`으로 재시작한다:
- 대안이 3개 이상이고 우열이 명확하지 않다.
- 기존 ADR과 충돌 가능성이 있다.
- 스택 선택, DB 스키마 재설계 등 **한번 결정하면 되돌리기 어려운** 사안이다.
- UX/제품 관점과 기술 관점이 충돌할 가능성이 있다.
