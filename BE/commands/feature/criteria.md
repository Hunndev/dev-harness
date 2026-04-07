# 평가기준 수립

code-convention + ADR 관련 항목을 병합하여 이 작업의 평가기준을 생성한다.

## 실행 방식

이 skill은 Fork에서 실행된다. ADR 분석은 Sub-agent에게 위임한다.

## 절차

1. **Sub-agent를 호출**하여 `.harness/docs/adr.yaml`에서 관련 항목을 추출한다.
2. `.harness/docs/code-convention.yaml`에서 이번 작업의 stacks와 관련된 항목을 필터링한다.
3. convention(공통) + ADR(작업별)을 병합하여 초안을 작성한다.
4. 초안과 **기준 적용 범위 논의점**을 사용자에게 제시한다.
5. 사용자 피드백을 반영하여 확정한다.

## Sub-agent 프롬프트

```
다음 작업 설계를 분석하고, adr.yaml에서 이 작업과 관련된 항목만 추출하라.
stacks 필드를 1차 필터로, context/decision 내용을 2차 판단으로 활용하라.
관련 없는 항목은 제외하라.
관련된 항목은 이 작업에 구체적으로 어떻게 적용되는지 설명하라.

[design-intent.md]
[.harness/docs/adr.yaml 전문]
```

## 산출물: code-quality-guide.md

```markdown
# 평가기준

## 공통 기준 (Code Convention)
(.harness/docs/code-convention.yaml에서 필터링된 항목)

| ID | 규칙 | 적용 대상 |
|----|------|---------|

## 이 작업에 적용되는 ADR

### ADR-XXX: {제목}
- 적용 방법: (이 작업에서 구체적으로 어떻게 준수해야 하는지)

## 추가 기준 (이 작업 고유)
(convention/ADR에 없지만 이 작업에서 특별히 확인해야 할 기준)
```
