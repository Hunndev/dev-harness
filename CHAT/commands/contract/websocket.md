# Socket.io 이벤트 계약 검토 (contract:websocket)

Socket.io 이벤트 계약을 검토·갱신한다. **코드 구현보다 계약 정합성 검증이 목적**이다. 계약이 깨지면 FE/앱이 동시에 깨진다.

> chat의 모든 실시간 이벤트는 `.harness/docs/websocket-events.yaml`을 단일 진실의 원천으로 한다.

## 사전 조건

- 변경/추가하려는 이벤트의 의도(누가 emit, 누가 listen, 언제)가 있어야 한다.
- 기존 `.harness/docs/websocket-events.yaml`(있으면)을 읽는다.

## 식별자

`.harness/artifacts/review/ws-{event-or-slug}/` 에 산출물을 둔다.

## 파이프라인

### [W1] 현행 계약 로드 (메인)

1. `.harness/docs/websocket-events.yaml`에서 대상 이벤트(또는 인접 이벤트군)를 읽는다.
2. 코드에서 실제 `socket.on(...)` / `io.emit(...)` / `socket.emit(...)` 사용처를 grep해 **문서와 코드의 일치 여부**를 1차 점검한다.

### [W2] 계약 명세 (메인)

각 이벤트에 대해 아래를 명시한다:

- **event name**: 네이밍 규칙 준수 (예: `domain:action`, `message:send`, `room:join`). ADR의 네이밍/버전 정책 참조.
- **direction**: client→server | server→client | bidirectional
- **payload schema**: 필드명·타입·필수여부 (TS 인터페이스로)
- **ack/response**: ack 콜백 페이로드와 에러 형태
- **error contract**: 실패 시 코드/메시지 규약
- **auth**: 이 이벤트에 필요한 인증/권한 (room 멤버십 등)
- **idempotency/ordering**: 중복 emit·순서 보장 필요 여부
- **version**: 호환성 영향 (breaking 여부)

### [W3] 호환성/영향 판정 (메인)

1. 이번 변경이 **breaking**인가? (payload 필드 제거/타입 변경/이벤트명 변경 = breaking)
2. breaking이면:
   - FE/앱에 미치는 영향 명시 → cross-repo 경계상 직접 수정 금지. **필요한 FE contract를 제안**하고 사용자 승인 후 `hb-fe`로 전환.
   - event-versioning 정책(예: `message:send` → `message:send:v2`) 적용 검토.
3. non-breaking(필드 추가 등)이면 하위호환 유지 방안을 기록.

### [W4] 계약 갱신 제안 (메인)

1. `websocket-events.yaml`에 반영할 diff를 `websocket-contract-diff.md`로 작성한다.
2. ADR이 필요한 변경(네이밍/버전 정책, 새 이벤트군 도입)이면 `/hb-chat:adr:new` 후보로 표시한다.
3. **사용자 승인 후** `/hb-chat:shared:update-docs websocket`로 편입한다 (자동 편입 금지).

## 산출물

```
.harness/artifacts/review/ws-{slug}/
  websocket-contract-diff.md   # 현행 → 제안 diff, breaking 여부, FE 영향
  INDEX.md                     # 요약, ADR 후보 여부, 승인 대기 항목
```

## 게이트

- 코드가 `websocket-events.yaml`에 없는 이벤트를 emit/listen하면 → **[p1]**. 먼저 계약 등록.
- breaking 변경이 버전 전략 없이 머지되려 하면 → **[p1]**.
