# 계약 점검 (feature:contract-check)

기능 구현 **전·후**에 chat의 계약·경계가 깨지지 않는지 점검한다. feature 파이프라인(auto/deep)에서 호출된다.

> chat은 계약이 깨지면 FE/BE/앱이 동시에 깨진다. 구현 전 계약을 확정하고, 구현 후 실제 코드가 계약과 일치하는지 검증한다.

## 점검 체크리스트

구현 대상 기능에 대해 아래 7개 경계를 점검한다:

1. **REST API 계약** — 새/변경 엔드포인트가 `.harness/docs/api-contract.yaml`에 명세됐는가? (method·path·auth·request·response·error)
2. **Socket.io 이벤트 계약** — 새/변경 이벤트가 `.harness/docs/websocket-events.yaml`에 등록됐는가? (name·direction·payload·ack·error·version)
3. **DB 변경** — 테이블/인덱스 변경이 `.harness/docs/database-schema.yaml`에 반영됐고 migration이 동반되는가?
4. **Redis 사용** — pub/sub·adapter·캐시 키 규약이 `operations.yaml`과 일치하는가?
5. **첨부파일** — 원본은 Object Storage, 메타만 DB인가? 접근 권한 모델이 명확한가?
6. **BE 연동 경계** — BE DB 직접 접근이 없는가? 신청자 등 검증 데이터는 BE API 경유인가? (`integration-boundary.yaml`)
7. **FE 영향** — FE가 의존하는 계약을 breaking하게 바꾸지 않는가? 바꾼다면 cross-repo 경계상 `hb-fe` 전환 제안 대상인가?

## 절차

### 구현 전 (pre)

1. 위 7개 중 이번 기능이 건드리는 항목을 식별한다.
2. 각 항목의 현행 계약을 해당 yaml에서 읽는다. **없으면 먼저 계약을 정의**한다(필요 시 `/hb-chat:contract:websocket` 또는 `:api`).
3. breaking 변경이면 → ADR 후보(`/hb-chat:adr:new`) 및/또는 버전 전략을 표시.
4. 결과를 `contract-check.md`에 기록 (pre 섹션).

### 구현 후 (post)

1. 실제 코드(라우터·소켓 핸들러·migration)가 계약 문서와 **일치**하는지 교차검증한다.
2. 불일치 = **[p1]**. 코드를 계약에 맞추거나, 승인된 계약 변경이면 문서를 갱신(`/hb-chat:shared:update-docs`).
3. 결과를 `contract-check.md`에 기록 (post 섹션).

## 산출물: contract-check.md

```markdown
# Contract Check

## 대상 경계
(7개 중 이번 기능이 건드리는 항목)

## Pre (구현 전)
- REST: 계약 상태 / 변경 필요 / breaking 여부
- WebSocket: ...
- DB / Redis / 첨부 / BE연동 / FE영향: ...
- ADR 후보: (있으면)

## Post (구현 후)
- 코드 ↔ 계약 일치: PASS | FAIL (불일치 시 [p1])
- 문서 갱신 필요 항목:
```

## 게이트

- 계약 미등록 이벤트/엔드포인트가 코드에 있으면 → **[p1]** (review-gates에서 차단).
- BE DB 직접 접근 → **[p1]**.
