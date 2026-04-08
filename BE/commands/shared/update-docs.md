# 문서 업데이트

`.harness/docs/` 하위 문서를 갱신한다. 모든 트랙의 마지막 단계에서 호출된다.

## 사용법

```
/hb-be:shared:update-docs                — 전체 문서 대상으로 변경 필요 항목 분석
/hb-be:shared:update-docs convention     — code-convention.yaml만
/hb-be:shared:update-docs adr            — adr.yaml만
/hb-be:shared:update-docs architecture   — architecture.yaml만
/hb-be:shared:update-docs modules        — module-registry.yaml만
```

## 공통: 컨텍스트 분석 우선 원칙

1. `.harness/docs/` 하위 4개 문서를 **모두** 읽는다.
2. 현재 작업의 변경 내용과 기존 항목을 대조하여 다음을 판단한다:
   - **충돌 항목**: 이번 변경이 기존 항목과 모순되는가?
   - **연쇄 수정**: 한 문서의 변경이 다른 문서에도 영향을 미치는가?
   - **폐기 대상**: 이번 변경으로 더 이상 유효하지 않은 항목이 있는가?
   - **누락 항목**: 이번 변경에서 새로 확립된 패턴/결정이 문서에 없는가?
3. 분석 결과를 **변경 제안 목록**으로 정리한다:
   - `MUST` — 반드시 반영 (충돌, 사실 오류)
   - `RECOMMENDED` — 반영 권장 (개선, 누락 보완)
4. 사용자에게 제안 목록을 제시하고, 최종 결정을 받는다.

## 트랙별 주요 갱신 대상

| 트랙 | 주요 갱신 문서 | 비고 |
|------|-------------|------|
| planning | adr.yaml | decision-draft.md 편입. 자동 편입 금지 — 사용자 승인 필수 |
| maintenance | code-convention.yaml | 새 패턴 발견 시. ADR 생성은 planning으로 에스컬레이션 |
| feature | module-registry.yaml, adr.yaml | 새 모듈/모델/API 반영. 새 ADR은 planning 거쳐야 함 |

## ADR 편입 시 특별 규칙

planning 트랙의 `decision-draft.md`를 adr.yaml에 편입할 때:
1. `decision-draft.md`의 `편입 상태`가 `미승인`이면 편입 불가.
2. 사용자가 이 대화에서 명시적으로 승인해야 한다.
3. 기존 ADR과의 충돌을 반드시 체크한다.
4. 충돌 시 기존 ADR의 status를 `superseded`로 변경할지 사용자에게 확인한다.

## code-convention.yaml 스키마

```yaml
- id: {카테고리}-{번호}    # GEN, DJ, DRF, DOCK, TEST, GIT
  rule: ...                 # 명확하고 실행 가능한 규칙
  stacks: [...]             # django, drf, docker, all 등
```

## adr.yaml 스키마

```yaml
- id: ADR-{번호}
  title: ...
  status: adopted | deprecated | superseded
  date: YYYY-MM-DD
  stacks: [...]
  context: |
    (구체적 상황 서술 — 문제, 고통, 검토한 대안 포함)
  decision: ...
  consequence: ...
```

## context 작성 가이드라인

- 나쁜 예: "DB 연결이 불안정해서 설정을 변경"
- 좋은 예: "Docker Swarm 환경에서 MariaDB 연결이 wait_timeout 이후 끊어지면서 'MySQL server has gone away' 에러가 간헐적으로 발생했다. Django 기본값(CONN_MAX_AGE=0)은 매 요청마다 연결을 새로 맺어 성능 저하가 있었다."
- context가 불충분하면 사용자에게 구체화를 요청한다.

## architecture.yaml 갱신

변경 대상: services, external_services, request_flow, deploy 섹션.
인프라 관련 maintenance 후에는 반드시 갱신한다.

## module-registry.yaml 갱신

변경 대상: modules 목록.
feature 트랙 후에는 반드시 갱신한다.

```yaml
- name: ...
  path: apps/{name}/
  purpose: ...
  models: [...]
  depends_on: [...]
  api_prefix: /api/{name}/
  notes: |
    ...
```
