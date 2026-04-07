# 기존 ADR/convention 충돌 체크

수정 방향이 기존 설계 결정과 충돌하지 않는지 확인한다.

## 실행 방식

이 skill은 Sub-agent가 실행한다.

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
| DJ-001 | 없음 / 있음 | ... |

## ESCALATION: {불필요 | 필요}
(필요한 경우)
- 이유: ...
- 제안: planning 트랙에서 ADR-XXX을 결정한 후 돌아오기
```
