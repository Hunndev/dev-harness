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
- `adr`: 반드시 사용자 승인된 ADR만 편입. `status: proposed`는 편입 금지. 편입 후에는 **YAML 본문 제시 (필수)** — 편입된 ADR의 yaml 본문(또는 context/decision/consequences 핵심 발췌)을 yaml 코드 블록으로 사용자에게 직접 보여준다. 단순 "편입 완료" 메시지로 끝내지 않는다.
- `websocket`/`api`/`database`: 계약 변경이 승인됐는지(contract 트랙 산출물 또는 사용자 승인) 확인.
- 승인 근거가 없으면 중단하고 사용자에게 확인.

### [U3] 갱신
1. YAML 스키마를 유지하며 항목을 추가/수정한다 (기존 항목 임의 삭제 금지).
2. ADR supersede 관계가 있으면 기존 항목 status 갱신.
3. id·version·날짜 등 메타를 일관되게 유지한다.

### [U4] 정합성 확인
- 변경 후 YAML이 파싱 가능한지 확인.
- 코드와의 명백한 불일치가 남았으면 후속 작업으로 표시.

## 신선도 교차검사 (호출 시 항상)

이 명령이 호출되면 갱신 대상 여부와 무관하게 아래를 가볍게 수행하고 결과를 한 줄 보고한다:

1. `.harness/docs/module-registry.yaml`의 모듈 목록 vs 실제 소스(`src/routes/`·`src/services/`·소켓 이벤트는 websocket-events.yaml)를 대조한다.
2. 미등재 모듈·사라진 모듈이 있으면 개수와 이름만 보고하고, 등재는 사용자 확인 후 진행한다 (자동 편입 금지).
3. `.harness/docs/` 마지막 갱신 커밋(`git log -1 --format=%ad --date=short -- .harness/docs`) 이후 코드 커밋 수를 보고한다 — 문서가 코드를 얼마나 뒤쳐졌는지의 신호.

## 원칙

- 이 명령은 **문서만** 바꾼다 (코드 수정 없음).
- ADR/계약은 "승인 → 편입" 순서를 절대 건너뛰지 않는다.
- 한 번에 하나의 target만 갱신한다(추적성).
