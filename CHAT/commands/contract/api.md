# REST API 계약 검토 (contract:api)

REST API 계약을 검토·갱신한다. **코드 구현보다 계약 정합성 검증이 목적**이다.

> chat의 모든 REST 엔드포인트는 `.harness/docs/api-contract.yaml`을 단일 진실의 원천으로 한다.

## 사전 조건

- 변경/추가하려는 엔드포인트의 의도가 있어야 한다.
- 기존 `.harness/docs/api-contract.yaml`(있으면)과 `integration-boundary.yaml`을 읽는다.

## 식별자

`.harness/artifacts/review/api-{endpoint-or-slug}/` 에 산출물을 둔다.

## 파이프라인

### [A1] 현행 계약 로드 (메인)

1. `api-contract.yaml`에서 대상 엔드포인트(또는 인접 리소스)를 읽는다.
2. 라우터 코드(`router.get/post/...`)와 문서의 일치 여부를 1차 점검한다.

### [A2] 계약 명세 (메인)

각 엔드포인트에 대해:

- **method + path**: 예 `POST /rooms/:roomId/invite`
- **auth**: JWT 필요 여부, 권한(room owner/member, 운영자)
- **request**: path/query/body 스키마 (필드·타입·필수)
- **response**: 성공 코드 + body 스키마, 에러 코드(4xx/5xx)와 형태
- **idempotency**: 재시도 안전성 (특히 invite/메시지 생성)
- **rate/size limit**: 첨부·bulk invite 등 상한
- **BE 연동**: 이 엔드포인트가 BE API/검증에 의존하는가? (신청자 목록 등은 BE가 source of truth)

### [A3] 경계/영향 판정 (메인)

1. **BE DB 직접 접근이 없는가** 확인 (금지). 필요한 데이터는 BE API 경유인지 검증.
2. breaking 변경(필드 제거/타입 변경/경로 변경)인가? → FE/앱 영향 명시, cross-repo 경계상 `hb-fe`로 전환 제안.
3. 새 외부 연동이면 `integration-boundary.yaml` 갱신 대상으로 표시.

### [A4] 계약 갱신 제안 (메인)

1. `api-contract.yaml` 반영 diff를 `api-contract-diff.md`로 작성.
2. 권한 모델·연동 경계 변경이면 `/hb-chat:adr:new` 후보로 표시.
3. **사용자 승인 후** `/hb-chat:shared:update-docs api`로 편입.

## 산출물

```
.harness/artifacts/review/api-{slug}/
  api-contract-diff.md   # 현행 → 제안 diff, breaking 여부, BE/FE 영향
  INDEX.md               # 요약, ADR 후보 여부, 승인 대기
```

## 게이트

- 코드가 `api-contract.yaml`에 없는 엔드포인트를 노출하면 → **[p1]**.
- BE DB 직접 접근 시도 → **[p1]** (경계 위반).
- breaking 변경이 버전/하위호환 전략 없이 머지되려 하면 → **[p1]**.
