# ADR 신규 등록 (adr:new)

설계 결정을 ADR(Architecture Decision Record) 후보로 등록하고, **사용자 승인 후** `adr.yaml`에 편입한다.

> chat은 결정이 계속 쌓인다(DB 분리, 읽음 모델, 이벤트 버전, scale-out, 첨부 저장 등). planning에서 나온 `decision-draft.md`를 바로 넣지 않고 이 트랙으로 정식 편입한다.

## 언제 쓰나 (ADR 후보 트리거)

아래 변경은 무조건 ADR 후보다:

- DB 테이블 구조 변경 / chat 전용 DB 경계
- 메시지 읽음·안읽음(receipt) 정책 변경
- Socket.io event naming / versioning 정책 변경
- Redis adapter scale-out 전략 변경
- 첨부파일 저장 방식 / 권한 모델 변경
- BE integration boundary 변경 (BE DB 직접 접근 금지 등)
- 권한 모델(room owner/member/운영자) 변경

## 사전 조건

- 결정의 맥락이 있어야 한다 (planning 산출물 `decision-draft.md` 또는 직접 입력).
- 기존 `.harness/docs/adr.yaml`을 읽어 충돌·중복·supersede 대상을 확인한다.

## 식별자

다음 ADR 번호를 `adr.yaml`에서 채번한다 (예: 마지막이 ADR-0007이면 `ADR-0008`). 산출물: `.harness/artifacts/adr/{ADR-id}/`.

## 파이프라인

### [D1] 컨텍스트 수집 (메인)

1. `decision-draft.md`(있으면) 또는 사용자 입력에서 결정 내용을 가져온다.
2. `adr.yaml`에서 관련/충돌 ADR을 찾는다. 기존 결정을 뒤집으면 **supersede 대상**으로 표시.

### [D2] ADR 초안 작성 (메인)

표준 ADR 형식으로 작성한다:

- **id**: ADR-XXXX
- **title**: 한 줄 결정 제목
- **status**: `proposed` (승인 전)
- **context**: 왜 이 결정이 필요한가 (문제·제약)
- **decision**: 무엇을 결정했는가 (명확·단정형)
- **consequences**: 긍정/부정 결과, 트레이드오프
- **alternatives**: 고려했으나 기각한 대안과 이유
- **affects**: 영향 받는 모듈/계약 (websocket-events / api-contract / database-schema / integration-boundary)
- **supersedes**: (있으면) 대체하는 기존 ADR id

`adr-draft.md`로 저장하고, **모호한 논의점**을 사용자에게 제시한다.

### [D3] 승인 게이트 (사용자)

1. 사용자에게 초안과 트레이드오프를 제시하고 승인을 받는다.
2. **승인 없이 `adr.yaml`에 편입하지 않는다.**
3. 거부 시 피드백 반영 후 D2 반복.

### [D4] 편입 (메인)

1. 승인된 ADR을 `status: accepted`로 바꿔 `/hb-chat:shared:update-docs adr`로 `adr.yaml`에 편입한다.
2. supersede 대상이 있으면 해당 ADR `status: superseded by ADR-XXXX`로 갱신.
3. `affects`에 적힌 계약 문서(websocket/api/database/integration) 갱신이 필요하면 후속 작업으로 표시.

## 산출물

```
.harness/artifacts/adr/{ADR-id}/
  adr-draft.md     # 초안 (proposed)
  INDEX.md         # 승인 상태, supersede 관계, 후속 계약 갱신 목록
```

## 원칙

- ADR은 **결정의 why를 남기는 것**이 목적이다. 구현 디테일이 아니라 결정과 근거.
- maintenance/feature 트랙은 ADR을 만들지 않는다. 이 트랙(또는 planning)에서만.
