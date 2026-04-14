# 대안 분석 — 3관점 병렬 (CM)

3개 독립 에이전트가 각각 기술/UX/비용 관점에서 대안을 분석하고, 메인이 병합한다.

## 실행 방식

이 skill은 **Claude Code 네이티브 Teams**로 실행된다. 표준 절차는 `commands/shared/team-protocol.md` 참조.
1명이 3관점을 순차로 돌리면 뒤 관점이 앞 관점에 편향되므로 반드시 병렬 실행한다.

### 팀 스펙

- `team_name`: `planning-alt-{plan-id}` (예: `planning-alt-plan-20260411-realtime`)
- `description`: "3관점 대안 분석 (기술/UX/비용)"
- 팀원 3명 (모두 `subagent_type: general-purpose`, 병렬 스폰):

  | 팀원 이름 | 사용할 프롬프트 블록 | 산출 파일 |
  |----------|--------------------|----------|
  | `tech-analyst` | 아래 "Agent A: 기술 실현성" | `.harness-artifacts/planning/{plan-id}/alternatives-tech.md` |
  | `ux-analyst`   | 아래 "Agent B: UX/제품 관점" | `.harness-artifacts/planning/{plan-id}/alternatives-ux.md` |
  | `cost-analyst` | 아래 "Agent C: 비용/일정/리스크" | `.harness-artifacts/planning/{plan-id}/alternatives-cost.md` |

- 메인: 3개 부분 산출물을 병합하여 최종 `alternatives.md` 작성 → 팀 해체 (`TeamDelete`)
- 각 팀원 프롬프트는 `team-protocol.md`의 "팀원 프롬프트 템플릿"을 사용하되, 과제 본문에 아래 "Agent A/B/C" 블록을 그대로 넣는다.

## 입력 (3개 에이전트 공통)

- `scope.md`
- `requirements-interview.md`
- `external-research.md`
- `docs/module-registry.yaml` (있으면)
- `docs/architecture.yaml` (있으면)
- `stakeholders.md`

## Agent A: 기술 실현성

```
다음 요구사항과 외부 조사 결과를 바탕으로, 기술적 대안을 분석하라.

대안은 최소 2개, 최대 4개를 제시하라.

각 대안에 대해:
1. 구현 방법 (Node/Express/TS 기준, controller/service/repository/middleware 레이어 수준)
2. 기존 모듈(module-registry.yaml)과의 호환성
3. 기술적 위험 요소와 복잡도 (1~5)
   - EventLoop blocking 가능성
   - 메모리 사용량
   - 동시성/race condition
4. 의존성 추가 필요 여부 (npm 패키지, 외부 서비스)
5. DB 스키마 변경 / 마이그레이션 위험도 (low/medium/high)
6. Socket.io 이벤트 스키마 변경 필요 여부
7. 메인 BE(hb-be) 연동 변경 필요 여부

출력 형식: 대안별로 위 항목을 채워라. 다른 관점(UX, 비용)은 평가하지 마라.

[scope.md]
[requirements-interview.md]
[external-research.md]
[module-registry.yaml]
[architecture.yaml]
```

## Agent B: UX/제품 관점

```
다음 요구사항을 바탕으로, 사용자 경험 관점에서 대안을 분석하라.

기술 에이전트가 제시한 대안과 동일한 대안 목록을 평가하되, 기술적 판단은 하지 마라.

각 대안에 대해:
1. 사용자(커뮤니티 사용자/작성자/모더레이터)별 경험 변화
2. 실시간성/응답성 차이 (즉시 반영 vs 지연 vs polling)
3. 기존 사용 흐름과의 일관성 (높음/보통/낮음)
4. 학습 비용 (사용자가 새로 배워야 하는 것)
5. 전환 비용 (기존 방식에서 새 방식으로의 이동)
6. 모바일 클라이언트(WebView/네이티브)에서의 경험 차이

출력 형식: 대안별로 위 항목을 채워라. 기술/비용 관점은 평가하지 마라.

[scope.md]
[requirements-interview.md]
[stakeholders.md]
```

## Agent C: 비용/일정/리스크

```
다음 요구사항을 바탕으로, 비용·일정·리스크 관점에서 대안을 분석하라.

기술 에이전트가 제시한 대안과 동일한 대안 목록을 평가하되, 기술적/UX적 판단은 하지 마라.

각 대안에 대해:
1. 예상 구현 공수 (1인 개발 기준, 인일)
2. Azure 인프라 비용 변동 (Redis 메모리, Swarm replica 추가, 트래픽 증가)
3. 메인 BE(hb-be) 연동 변경 비용 (별도 레포 작업 필요)
4. 실패 리스크 (low/medium/high) — 실패 시 되돌리기 비용 포함
5. 점진적 출시 가능 여부 (feature flag, 단계적 rollout)
6. 운영 모니터링 비용 (새 메트릭, 알람)

출력 형식: 대안별로 위 항목을 채워라. 기술/UX 관점은 평가하지 마라.

[scope.md]
[requirements-interview.md]
[architecture.yaml]
```

## 메인: 병합

1. 3개 에이전트의 결과를 대안별로 통합한다.
2. 관점 간 **충돌/모순**을 식별한다:
   - 예: 기술적으로 최적인 대안이 비용이 가장 높은 경우
   - 예: UX가 좋은 대안이 기술적으로 가장 복잡한 경우
3. 충돌이 있으면 사용자에게 명시적으로 제시하고 판단을 요청한다.
4. 병합 결과를 `alternatives.md`로 저장한다.

## 산출물: alternatives.md

```markdown
# 대안 분석

## 대안 목록

### 대안 A: {이름}
#### 기술 실현성
- 구현 방법: ...
- 호환성: ...
- 복잡도: {1~5}
- 의존성: ...
- DB 마이그레이션 위험: {low|medium|high}
- Socket.io 변경: {있음|없음}
- BE 연동 변경: {있음|없음}

#### UX/제품
- 사용자 경험 변화: ...
- 실시간성: ...
- 기존 흐름 일관성: {높음|보통|낮음}
- 학습 비용: ...

#### 비용/일정/리스크
- 공수: {N}인일
- 인프라 비용 변동: ...
- BE 연동 변경 비용: ...
- 실패 리스크: {low|medium|high}
- 점진적 출시: {가능|불가}

### 대안 B: {이름}
(동일 구조)

## 관점 간 충돌
| 충돌 | 기술 | UX | 비용 | 비고 |
|------|------|-----|------|------|
| ... | ... | ... | ... | 사용자 판단 필요 |

## 추천
(메인이 3관점을 종합하여 추천. 단, 최종 결정은 사용자.)
```
