# 검사 관문 (Evaluate)

주문한 변경이 **동일한 검증 packet의 증거상 완료됐는지** 판정한다. Evaluate는 일반 코드리뷰가 아니다.

## 중심 질문

> 이 `packet_id`의 변경이 작업별 실제 Acceptance Criteria, 범위, 제외사항, 운영 완료조건을 유효한 증거로 충족했는가?

## 역할 경계

Evaluate가 소유한다:

- 실제 작업 AC별 requirement-to-evidence traceability
- Gate/TDD 증거의 존재·관련성·유효성
- 요청 범위와 제외 범위 준수
- 작업에 적용되는 운영 완료조건
- `source_snapshot_id`, `evidence_bundle_id`, `packet_id` 일치

Evaluate가 소유하지 않는다:

- 일반 버그 탐색
- 광범위한 보안·성능·architecture·스타일 리뷰
- Review의 테스트 설계 누락 탐색
- fresh하고 유효한 Gate의 test/lint/build/QA 무조건 재실행
- 상대 provider finding을 본 뒤 결론을 맞추는 rebuttal

명백히 무효인 테스트 증거(AC와 무관, assertion 없음, 다른 snapshot, 실행되지 않은 로그, System Under Test를 전부 mock)는 Evaluate에서 증거 불충분으로 차단한다. 더 넓은 assertion·mock·경계·회귀 품질은 Review가 독립 검토한다.

## Repository 진실의 원천

별도 Stack Profile이나 architecture 사본을 강제하지 않는다. 다음을 우선 사용한다.

1. 작업 repository의 `AGENTS.md`, `CLAUDE.md`, 명시적 정책
2. 실제 CI workflow와 checked-in script
3. `package.json`, `pyproject.toml`, `Makefile` 등 manifest
4. repository architecture, ADR, 운영 문서
5. 필수 정보가 없거나 충돌하면 추측하지 않고 `BLOCKED` 또는 사용자 확인

스택별 완료기준은 해당 플러그인의 `shared/verify`가 소유한다. BE/CM의 test·lint·build, FE의 시각·접근성·API 바인딩, CHAT의 websocket/API/data contract, AOS/IOS의 기기·권한·푸시·딥링크·bridge parity를 이 공통 명령에 하드코딩하거나 복제하지 않는다. 실제 test·lint·build 명령도 repository 정책과 CI가 정한 값을 그대로 사용한다.

## 사전조건 — Deterministic Gate

Evaluate 시작 전에 다음이 봉인돼야 한다.

```text
original request + 실제 AC + exclusions
source_snapshot_id
repository-defined test/lint/build/stack QA 결과
tdd-test-design-result.json
tdd-sensitivity-result.json
evidence_bundle_id
packet_id
```

Gate 실패, 필수 TDD 증거 누락, 검사 전후 source snapshot 변경은 모델 판단 전에 `BLOCKED`다.

## 절차

### [E0] Packet 유효성 확인 — deterministic

1. `gate-result.json` status가 `PASS`인지 확인한다.
2. Gate와 packet의 source/evidence/packet ID가 같은지 확인한다.
3. 현재 repository snapshot을 재계산해 packet과 다르면 이전 결과를 사용하지 않는다.
4. 필수 AC·제외사항·TDD 증거가 없으면 `BLOCKED`한다.

### [E1] 동일 packet 봉인

두 evaluator에게 정확히 같은 read-only packet을 제공한다.

포함:

- original request
- 작업별 실제 AC와 exclusions
- final diff와 read-only repository
- repository-owned architecture/ADR/CI/검증 정책
- Gate와 TDD quality evidence
- source/evidence/packet IDs

제외:

- 구현 대화·구현자의 자기평가
- 이전 evaluator/reviewer 대화
- 상대 evaluator 결론·finding
- credential 값

### [E2] Blind Fresh Dual Evaluate

```text
Fresh Claude Evaluate ∥ Fresh Codex Evaluate
```

- 각각 새 process/session이며 resume/continue를 사용하지 않는다.
- live checkout을 직접 검사하지 않고 content-verified packet copy를 사용한다. repository source는 macOS `sandbox-exec` 또는 read-only container로 OS 수준 쓰기 차단한다.
- provider 내부 Sub-agent/Team은 규모·위험도에 따른 선택 사항이다.
- provider 내부 agent 수는 Claude/Codex 교차 독립성을 대체하지 않는다.
- 각 provider는 AC 판정·finding·근거만 담은 model-owned semantic result를 낸다. 모델은 `fresh`, `read_only`, `repository_mutated`를 자기증명할 수 없다.
- 부모 runner가 process/run ID, timeout, exit code, packet binding, 실행 전후 digest, isolation mode를 `execution-envelope.<engine>.json`에 직접 기록한다.
- semantic result와 parent envelope가 모두 있어야 sealed result가 된다.

### [E3] AC별 판정

각 실제 AC에 대해 다음 matrix를 작성한다.

| 실제 AC | 완료 | 증거 | 증거 유효성 | scope/exclusion | 운영조건 | 판정 |
|---|---|---|---|---|---|---|
| AC-* | yes/no | evidence ref | valid/invalid | pass/block | pass/N/A/block | PASS/BLOCKED |

`요청 충족`, `증거 유효성`, `scope`, `제외사항`, `운영 완료조건`은 고정 AC 이름이 아니라 모든 실제 AC에 적용하는 공통 평가 관점이다.

### [E4] Provider 결과 검증·Join — deterministic

`SHARED/contracts/evaluate-result.schema.json`과 runtime validator로 다음을 검사한다.

- Claude와 Codex 결과 모두 존재
- 각 결과에 model semantic payload와 parent-owned execution envelope가 모두 존재
- stage/engine/fresh/read-only 유효
- same packet/source/evidence ID
- repository mutation 없음
- malformed/secret-shaped/forbidden context 없음

한 provider 실패를 다른 provider PASS로 보완하지 않는다.

## 상태와 재실행

```text
두 결과 clean                          → Review 시작 가능
AC·증거 내용 blocker                   → 개발/증거 보완 → Gate → Dual Evaluate
일시적 timeout/process 실패            → 같은 packet으로 fresh dual retry 최대 1회
auth/schema/malformed/missing provider  → BLOCKED, 원인 수정 전 자동 반복 금지
snapshot mismatch/repository mutation  → 이전 결과 무효, Gate부터 재실행
고위험 중요 결론 충돌                  → NEEDS_HUMAN_REVIEW 후보
```

## 산출물

```text
.harness/artifacts/{track}/{identifier}/eval-review/
  gate-result.json
  evaluate-packet.json
  evaluate-result.claude.json
  evaluate-result.codex.json
  execution-envelope.evaluate.claude.json
  execution-envelope.evaluate.codex.json
  evaluate-join-result.json
```

Raw provider 결과는 봉인 후 수정하지 않는다. finding disposition이나 사람 판정은 별도 reconciliation artifact에 기록한다.
