# 요구사항 정리

신규 기능의 요구사항을 수집하고 구조화한다.

## 실행 방식

이 skill은 Fork에서 실행된다.

## 절차

1. planning 트랙 산출물이 있으면 연결한다:
   - `.harness-artifacts/planning/{관련 identifier}/requirements-interview.md`
   - 관련 ADR (docs/adr.yaml에 편입된 항목)
2. 없으면 사용자에게 직접 수집한다.
3. `docs/module-registry.yaml`을 읽고 기존 모듈과의 관계를 파악한다.
4. 논의점을 사용자에게 제시한다.

## 산출물: requirements.md

```markdown
# 요구사항

## 기능 개요
(한 문장 요약)

## 기반 문서
- planning 산출물: {경로 또는 "없음"}
- 관련 ADR: {ADR-XXX 또는 "없음"}

## MUST
- REQ-M01: ...
- REQ-M02: ...

## SHOULD
- REQ-S01: ...

## NICE
- REQ-N01: ...

## 기존 모듈 연결점
| 모듈 | 연결 방식 |
|------|----------|

## 미결 사항
- ...
```
