# 평가 관문 (Review)

Dual Evaluate가 같은 packet에서 통과한 뒤, 구현과 테스트가 제품에 적용해도 정확하고 안전한지 독립 검토한다. Review는 완료조건 평가를 처음부터 반복하지 않는다.

## 중심 질문

> 이 `packet_id`의 구현과 테스트가 실제 제품에서 정확하고 안전하며 회귀를 막을 수 있는가?

## 역할 경계

Review가 소유한다:

- correctness와 오류 처리
- security, authentication, authorization
- regression, compatibility, API/data contract
- performance와 operational risk
- repository architecture/ADR 준수
- 테스트 코드 assertion, mock, 경계·실패 경로, 회귀 검출력, brittle/flaky 위험

Review가 소유하지 않는다:

- original request와 AC traceability를 처음부터 재작성
- Evaluate PASS 결론을 미리 보고 따라 하기
- fresh하고 유효한 Gate의 deterministic 명령을 이유 없이 반복
- 한 provider 실패를 생략하고 나머지 결과만으로 PASS

## 사전조건

1. Fresh Claude+Codex Evaluate가 모두 같은 packet에서 `PASS`다.
2. `gate-result.json`과 TDD quality evidence가 여전히 fresh하다.
3. 현재 source snapshot이 Evaluate packet과 같다.
4. repository는 reviewer에게 read-only다.

하나라도 아니면 Review를 시작하지 않고 `BLOCKED`한다.

## 절차

### [R0] Review Packet 준비

Evaluate와 같은 source/evidence/packet IDs를 사용한다. 다음을 제공한다.

- final diff와 read-only repository
- repository-owned architecture/ADR/보안·운영 정책
- Gate result와 TDD evidence
- original request와 design intent(맥락용)
- source/evidence/packet IDs

다음은 제공하지 않는다.

- implementer conversation/self-assessment
- Evaluate의 PASS 설명이나 finding
- 상대 reviewer 결과
- credential 값

### [R1] Blind Fresh Dual Review

```text
Fresh Claude Review ∥ Fresh Codex Review
```

- 각각 새 process/session이다.
- blind-first로 독립 실행한다.
- reviewer는 content-verified packet copy만 보며, source는 macOS `sandbox-exec` 또는 read-only container로 OS 수준 쓰기 차단하고 실행 전후 digest도 비교한다.
- provider별 내부 Team은 T2·대형·고위험에 선택적으로 사용할 수 있다.
- provider는 finding·근거만 담은 semantic result를 낸다. 부모 runner가 fresh process, timeout, packet binding, isolation, 실행 전후 digest를 별도 execution envelope로 기록한다.
- 모델의 `fresh/read_only/repository_mutated` 자기주장은 금지하며 semantic+envelope 두 파일이 모두 있어야 sealed result가 된다.

### [R2] 구현 품질 렌즈

repository의 stack/architecture/ADR를 기준으로 다음을 검토한다.

1. **Correctness** — 조건, 상태전이, 데이터 흐름, off-by-one, race, 누락 경로
2. **Security/Authorization** — 입력 검증, 권한 우회, secret, injection, 민감정보 노출
3. **Errors/Operations** — timeout, retry, partial failure, rollback, 관찰 가능성, 운영 완료조건과 충돌
4. **Regression/Compatibility** — 기존 계약, caller, migration, backward compatibility
5. **Performance** — N+1, unbounded work, memory/network 비용, UI/render 병목
6. **Architecture** — repository-owned architecture/ADR/convention과 구현 정합

스택별 review lens는 해당 플러그인 정책을 추가로 따른다. 예를 들어 FE의 시각·접근성·API 상태, CHAT의 websocket/API/data contract, AOS/IOS의 기기·권한·WebView·딥링크·bridge parity는 공통 Review가 임의로 단일 명령으로 환원하지 않는다.

### [R3] 테스트 코드 품질 렌즈 — 필수

다음을 명시적으로 검토한다.

- 실제 AC/버그와 테스트가 연결되는가
- Red가 올바른 이유로 실패했는가
- Green에서 같은 test identity/hash를 유지했는가
- assertion이 행동·상태·부작용·오류 계약을 충분히 검증하는가
- System Under Test를 mock으로 대체하지 않았는가
- 외부 경계 mock이 과도하거나 현실 경로를 우회하지 않는가
- 성공·실패·경계·권한·timeout 경로 중 필요한 것이 누락되지 않았는가
- 구현 세부사항에 과도하게 결합되어 정상 refactor를 깨뜨리는가
- timing/async/network/UI 특성으로 flaky할 가능성이 있는가
- 관련 회귀 suite가 충분한가
- 핵심 수정 revert/mutation 시 테스트가 실패하는가(고위험 또는 증거가 약한 경우)
- 테스트와 구현이 동일한 잘못된 가정을 공유하는가

테스트 파일 존재와 PASS만으로 테스트 품질을 통과시키지 않는다.

### [R4] Finding 근거화·자체 반박

각 finding은 다음을 포함한다.

```text
finding_id
risk/severity
file:line 또는 evidence ref
재현 가능한 설명
영향
권장 수정
blocking 여부
```

각 provider는 자기 결과를 봉인하기 전에 근거가 실제 diff/repository에 존재하는지 한 번 자체 반박한다. 상대 provider finding은 보지 않는다.

### [R5] Provider 결과 검증·Join — deterministic

`SHARED/contracts/review-result.schema.json`과 validator로 다음을 검사한다.

- 두 provider 결과 존재·schema 유효
- 두 provider의 parent-owned execution envelope 존재·유효
- fresh/read-only/same packet
- repository mutation 없음
- blocking finding과 status 모순 없음

Raw provider 결과는 수정하지 않는다. reconciliation은 별도 artifact다.

## 상태와 재실행

```text
두 Review clean                         → deterministic Finalize
Review 내용 blocker로 코드 수정         → Gate → Dual Evaluate → Dual Review
일시적 timeout/process 실패             → 같은 packet으로 fresh dual retry 최대 1회
auth/schema/malformed/missing provider   → BLOCKED
snapshot mismatch/repository mutation   → 이전 결과 전체 무효, Gate부터
고위험 중요 결론 충돌                   → NEEDS_HUMAN_REVIEW
```

Codex 또는 Claude 실패를 `생략`으로 기록하고 PASS하는 것은 금지한다.

## 산출물

```text
.harness/artifacts/{track}/{identifier}/eval-review/
  review-packet.json
  review-result.claude.json
  review-result.codex.json
  execution-envelope.review.claude.json
  execution-envelope.review.codex.json
  review-join-result.json
  final-result.json
```

최종 상태는 `PASS`, `BLOCKED`, `NEEDS_HUMAN_REVIEW` 중 하나다. commit/push/PR/merge/install/deploy 승인은 이 결과와 별도다.
