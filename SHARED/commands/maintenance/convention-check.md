# 기존 ADR/convention 충돌 체크

수정 방향이 기존 설계 결정과 충돌하지 않는지 확인한다.

> **지위**: **opt-in 단독 명령.** 각 도메인 파이프라인(maintenance)의 ADR 충돌 체크 스텝이 같은 일을 하며, 이 문서는 그 절차의 **스택 중립 canonical 정의**다. 파이프라인 밖에서 이 단계만 따로 돌릴 때 호출한다.

## 실행 방식

이 skill은 Sub-agent가 실행한다.

**문서 부재 fallback**: `.harness/docs/adr.yaml`·`.harness/docs/code-convention.yaml`이 없거나 빈 스캐폴드면 "검사 불가(문서 부재)"를 산출물에 명시하고 **통과로 처리하지 않는다** — 해당 플러그인의 `shared:update-docs`로 문서 생성을 먼저 제안한다.

## Sub-agent 프롬프트

```
다음 수정 방향이 기존 ADR과 convention에 충돌하는지 확인하라.

확인 항목:
1. adr.yaml의 각 항목과 수정 방향을 대조하라.
   - 수정이 기존 decision을 위반하는가?
   - 수정이 기존 consequence와 모순되는가?
2. code-convention.yaml의 각 규칙과 수정 방향을 대조하라.
   - 수정이 어떤 convention을 위반하게 되는가?
3. 새로운 설계 결정이 필요한가?
   - 기존 ADR에 없는 새로운 패턴/구조를 도입하는가?
   - 필요하면 ESCALATION 플래그를 설정하라.

[root-cause.md]
[impact-analysis.md]
[adr.yaml 전문]
[code-convention.yaml 전문]
```

## 산출물: convention-check.md

```markdown
# ADR/Convention 충돌 체크

## ADR 충돌
| ADR | 충돌 여부 | 내용 |
|-----|---------|------|
| ADR-001 | 없음 / 있음 | ... |

## Convention 위반
| 규칙 ID | 위반 여부 | 내용 |
|---------|---------|------|
| {스택 규칙 ID — 예: BE=DJ-001, CM=CM-001, FE=FE-001, CHAT=CH-001} | 없음 / 있음 | ... |

## ESCALATION: {불필요 | 필요}
(필요한 경우)
- 이유: ...
- 제안: planning 트랙에서 ADR-XXX을 결정한 후 돌아오기
```
