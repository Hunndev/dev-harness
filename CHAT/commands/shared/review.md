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
- reviewer는 content-verified packet copy만 보며, source는 macOS `sandbox-exec`로 OS 수준 쓰기 차단하고 실행 전후 digest도 비교한다. 그 외 환경은 현재 런타임이 격리를 제공하지 않으므로 provider를 실행하지 않고 `ISOLATION_UNAVAILABLE`로 BLOCKED한다(컨테이너 격리는 미구현).
- provider별 내부 Team은 T2·대형·고위험에 선택적으로 사용할 수 있다.
- provider는 finding·근거만 담은 semantic result를 낸다. 부모 runner가 fresh process, timeout, packet binding, isolation, 실행 전후 digest를 parent-owned execution envelope로 기록한다 — 별도 파일이 아니라 `sealed-results/{stage}-{engine}.json`의 `envelope` 필드다.
- 부모는 정상 종료·timeout·예외 모든 경로에서 자식 process group을 bounded reap한다. 살아남은 자손은 `PROVIDER_DESCENDANTS_ALIVE`로 BLOCKED다. 단 `setsid`로 group을 벗어난 자손은 포획할 수 없으므로 격리 범위는 diagnostics `descendant_containment: "process-group-only"`로 그대로 공개한다.
- 모델의 `fresh/read_only/repository_mutated` 자기주장은 금지하며 `semantic`과 `envelope` 두 필드가 모두 있어야 sealed result가 된다.

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
- blocking finding과 status 모순 없음 — 모순은 `SEMANTIC_STATUS_CONTRADICTS_FINDINGS`, `blocking` ID가 findings에 없으면 `SEMANTIC_BLOCKING_ID_UNKNOWN`
- `findings`/`blocking`/`evidence_refs`/`status`와 finding의 `finding_id`/`blocking`/`disposition`/`risk` 타입이 schema대로 — 이탈은 `SEMANTIC_SCHEMA_INVALID`
- stage cleanup 완주 — `.provider-home` 잔존은 `PROVIDER_HOME_NOT_REMOVED`, credential scan·이름 제거를 마치지 못한 항목은 `PURGE_INCOMPLETE`, 단계 자체가 예외로 끝나면 `PROVIDER_HOME_CLEANUP_FAILED`·`RAW_RESULT_CLEANUP_FAILED`·`PURGE_FAILED`. `ENOENT`만 "이미 없음"으로 인정하며, 부모가 봉인한 결과 파일이 purge되면 `SEALED_RESULT_PURGED`
- 자격증명은 파일 **내용과 entry 이름** 양쪽에서 exact literal로 제거한다. 재인코딩한 값과 group을 벗어난 자손의 사후 쓰기는 이 보장 밖이며, cleanup을 pin당해 BLOCKED가 된 stage의 output_root에는 자격증명 사본이 남아 있을 수 있으므로 운영자가 폐기한다.
- packet에 secret material 유입 없음 — deny 이름 규칙은 모든 경로 성분에 대소문자 무관 적용하며 있으면 provider 기동 전 `PACKET_SECRET_MATERIAL_PRESENT`, entry 상위 성분이 symlink면 `PACKET_PATH_UNSAFE`
- provider 결과 파일이 자기 정규 파일 — 아니면 `RESULT_PATH_UNSAFE`; stage output_root 삭제·교체는 `OUTPUT_ROOT_TAMPERED`
- envelope `result_sha256`가 semantic canonical JSON에서 재계산한 값과 일치 — 불일치는 `SEALED_RESULT_HASH_MISMATCH`

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

`hb-eval-review run`이 `--output-root`(README 실행 예시와 같은 위치, `.harness/artifacts/{track}/{identifier}/eval-review/run-{n}/`) 아래에 만드는 파일은 다음이 전부다. `gate-result.json`(사전조건 2가 확인), packet JSON(`--packet`), packet source 디렉토리(`--packet-source`), stage별 prompt 파일(`--evaluate-prompt`·`--review-prompt`)은 부모가 run 전에 준비하는 입력이며 run이 만들지 않는다. envelope의 stage/engine이 두 enum 밖이면 sealed 파일명은 `unknown-{index}.json`이다. provider 작업 디렉토리의 내용은 provider별로 다르며 봉인 결과의 정본은 `sealed-results/`다.

```text
.harness/artifacts/{track}/{identifier}/eval-review/run-{n}/    ← `--output-root`. run마다 새 빈 디렉토리(`eval-review/` 자체는 `qa-snapshot.json` 등 기록이 있어 쓸 수 없다), packet source 밖
  execution-manifest.json      ← 영속: packet·source·evidence ID, prompt/effective prompt digest, model ID, isolation policy. packet·prompt·model·materialized 검증 또는 source 재검증 실패로 조기 BLOCKED되면 없다
  materialized-packet/         ← 임시: content-verified packet copy(manifest.json + source/). 복사 직후 source 재검증이 실패하거나(`SOURCE_CHANGED_BEFORE_MATERIALIZE`·`SOURCE_SNAPSHOT_UNAVAILABLE`) 재계산 자체가 거부되면 run이 지우고(제거 실패는 `MATERIALIZED_PACKET_REMOVE_FAILED`로 함께 보고하며 복사본은 남는다), 그 밖에는 run이 지우지 않지만 보관 대상이 아니다
  evaluate-claude/             ← 임시: Evaluate provider 작업 디렉토리. Review 시작 전 삭제(Evaluate가 BLOCKED면 남는다)
  evaluate-codex/              ← 임시: Evaluate provider 작업 디렉토리. Review 시작 전 삭제(Evaluate가 BLOCKED면 남는다)
  review-claude/               ← 임시: Review provider 작업 디렉토리. Review가 실행됐을 때만
  review-codex/                ← 임시: Review provider 작업 디렉토리. Review가 실행됐을 때만
  final-result.json            ← 영속: run 결과(PASS/BLOCKED). packet·prompt·model·materialized 검증 또는 source 재검증 실패로 조기 BLOCKED되면 없다
  sealed-results/              ← 영속: stage·engine별 sealed result. 한 파일에 semantic + envelope
  sealed-results/evaluate-claude.json
  sealed-results/evaluate-codex.json
  sealed-results/review-claude.json    ← Review가 실행됐을 때만
  sealed-results/review-codex.json     ← Review가 실행됐을 때만
```

최종 상태는 `PASS`, `BLOCKED`, `NEEDS_HUMAN_REVIEW` 중 하나다. commit/push/PR/merge/install/deploy 승인은 이 결과와 별도다.
