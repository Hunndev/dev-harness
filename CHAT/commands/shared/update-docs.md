# 문서 갱신 (shared:update-docs)

`.harness/docs/`의 진실의 원천 YAML을 갱신한다. **승인된 변경만** 편입한다(특히 ADR).

## 사용법

```
/hb-chat:shared:update-docs <target>
```

`<target>`:

| target | 갱신 대상 | 언제 |
|--------|----------|------|
| `adr`         | `adr.yaml` | adr:new/planning에서 **승인된** 결정 편입 |
| `architecture`| `architecture.yaml` | 서비스 구조·모듈 경계·의존성 변경 시 |
| `modules`     | `module-registry.yaml` | room/message/attachment/invite/presence 모듈 추가·변경 |
| `convention`  | `code-convention.yaml` | 코딩 규칙 추가·변경 |
| `websocket`   | `websocket-events.yaml` | Socket 이벤트 계약 변경(contract:websocket 승인분) |
| `api`         | `api-contract.yaml` | REST 계약 변경(contract:api 승인분) |
| `database`    | `database-schema.yaml` | 테이블·인덱스·migration 정책 변경 |
| `integration` | `integration-boundary.yaml` | BE/FE/community 경계 변경 |
| `ops`         | `operations.yaml` | Redis·배포·로그·모니터링·장애 대응 변경 |
| `review`      | `review-policy.yaml` | Claude/Codex 리뷰 기준 변경 |

## 절차

### [U1] 현행 로드
대상 YAML을 읽고 갱신 범위를 확인한다.

### [U2] 승인 확인 (게이트)
- `adr`: 반드시 사용자 승인된 ADR만 편입. `status: proposed`는 편입 금지.
- `websocket`/`api`/`database`: 계약 변경이 승인됐는지(contract 트랙 산출물 또는 사용자 승인) 확인.
- 승인 근거가 없으면 중단하고 사용자에게 확인.

### [U3] 갱신
1. YAML 스키마를 유지하며 항목을 추가/수정한다 (기존 항목 임의 삭제 금지).
2. ADR supersede 관계가 있으면 기존 항목 status 갱신.
3. id·version·날짜 등 메타를 일관되게 유지한다.

### [U4] 정합성 확인
- 변경 후 YAML이 파싱 가능한지 확인.
- 코드와의 명백한 불일치가 남았으면 후속 작업으로 표시.

## 원칙

- 이 명령은 **문서만** 바꾼다 (코드 수정 없음).
- ADR/계약은 "승인 → 편입" 순서를 절대 건너뛰지 않는다.
- 한 번에 하나의 target만 갱신한다(추적성).
