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

별도 Stack Profile이나 architecture 사본을 강제하지 않는다. 대신 repository가 선언한 주제별 ownership을 사용한다.

1. 작업 repository의 `AGENTS.md`, `CLAUDE.md`, `.harness/README.md`에서 주제별 진실의 원천을 확인
2. 코딩 규칙·ADR·architecture·제품 계약은 선언된 canonical 문서 사용 (`.harness/docs/*.yaml` 포함)
3. 실제 실행 명령·dependency는 CI workflow·checked-in script·manifest 사용
4. 현재 구현 상태는 source·migration·실제 test/lint/build 결과로 확인
5. 문서와 구현이 충돌하면 한쪽을 자동으로 무시하지 않고 `BLOCKED` 후 코드 위반인지 문서 drift인지 판정

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

Gate 실패, 필수 TDD 증거 누락, 검사 전후 source snapshot 변경은 모델 판단 전에 `BLOCKED`다. packet 검증과 source 복사 사이의 변경도 같다: `hb-eval-review run`은 복사 직후 snapshot을 다시 계산해 packet의 `source_snapshot_id`와 복사본의 tree 해시(`source_tree_sha256`) 둘 다 대조하고(검증→복사 사이 재검증), 하나라도 다르면 provider를 띄우지 않고 `SOURCE_CHANGED_BEFORE_MATERIALIZE`로 `BLOCKED`하며 잠긴 복사본을 제거한다. 재계산이 git·파일시스템 오류로 끝나면 `SOURCE_SNAPSHOT_UNAVAILABLE`, 열거기가 tree를 거부하면 그 코드로 같은 방식으로 `BLOCKED`하고, 복사본 제거가 실패하면 `MATERIALIZED_PACKET_REMOVE_FAILED`를 원인 코드 뒤에 함께 적는다. 이 정리는 output tree와 그 상위 경로를 부모 프로세스가 전용으로 소유하며 실행 중 교체되지 않는다는 전제에서 안전하다.

run은 materialize → verify → dev-27 source 재검증 이후 `materialized-packet/evidence/`의 사본 bytes hash를 packet과 대조한다. `.harness/`가 gitignore되어도 필수 증거 사본을 별도로 만들고 이후 사본만 소비한다. Gate의 source 비교는 이때 검증한 실제 저장소 ID를 사용하며 `.git`이 없는 source 사본에서 재계산하지 않는다.

## 절차

### [E0] Packet 유효성 확인 — deterministic

1. `gate-result.json` status가 `PASS`인지 확인한다.
2. Gate schema 1.1의 source_snapshot_id가 packet 및 현재 source와 같은지 확인한다. Gate에는 evidence_bundle_id·packet_id를 넣지 않는다(순환 방지). Gate 실제 bytes의 status·비어 있지 않은 commands·모든 exit_code 0을 공통 validator로 확인한다.
3. 현재 repository snapshot을 재계산해 packet과 다르면 이전 결과를 사용하지 않는다. 재계산은 packet 검증 시점과 source 복사 직후 두 번이며(검증→복사 사이 재검증), 두 번째는 복사본의 tree 해시와도 대조한다 — 바뀐 내용이 복사된 뒤 live source가 원복된 경우도 여기서 걸린다(복사되기 전에 원복된 순간적 변경까지 항상 잡는 것은 아니다).
4. 필수 AC·제외사항·TDD 증거가 없으면 `BLOCKED`한다. design·sensitivity는 schema와 기존 의미 validator를 모두 통과해야 하고 baseline이 같아야 한다. schema 1.1의 PASS_TO_PASS는 maintenance refactor에만 허용하며 1.0은 RED_TO_GREEN으로 호환한다. `TDD_*` 오류 코드는 `GATE_*`와 구분해 보존한다.

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
- live checkout을 직접 검사하지 않고 content-verified packet copy를 사용한다. repository source는 macOS `sandbox-exec`로 OS 수준 쓰기 차단한다. 그 외 환경(Linux 등)은 현재 런타임이 격리를 제공하지 않으므로 provider를 실행하지 않고 `ISOLATION_UNAVAILABLE`로 BLOCKED한다(컨테이너 격리는 미구현).
- provider 내부 Sub-agent/Team은 규모·위험도에 따른 선택 사항이다.
- provider 내부 agent 수는 Claude/Codex 교차 독립성을 대체하지 않는다.
- 각 provider는 AC 판정·finding·근거만 담은 model-owned semantic result를 낸다. 모델은 `fresh`, `read_only`, `repository_mutated`를 자기증명할 수 없다.
- 부모 runner가 process/run ID, timeout, exit code, packet binding, 실행 전후 digest, isolation mode를 parent-owned execution envelope에 직접 기록한다. envelope는 별도 파일이 아니라 `sealed-results/{stage}-{engine}.json`의 `envelope` 필드이며, 같은 파일의 `semantic` 필드가 model-owned 결과다.
- provider 자식은 자기 process group에서 시작하며, 정상 종료·timeout·예외 모든 경로에서 부모가 그 group을 bounded reap(SIGTERM→SIGKILL)한다. 살아남은 자손이 있으면 `PROVIDER_DESCENDANTS_ALIVE`로 BLOCKED다.
- 자식 출력은 bytes로 수집한다. 유효하지 않은 UTF-8은 예외가 아니라 `PROCESS_OUTPUT_UNDECODABLE`(BLOCKED)이고, 진단용 사본만 replacement 문자로 보여준다. 파이프 자체가 실패하면 예외 클래스 이름만 남기고 `PROCESS_OUTPUT_UNAVAILABLE`(BLOCKED)이다.
- timeout 경로에서 커널이 group signal을 거부해도(EPERM·ESRCH) 그것은 진단 사실로 기록될 뿐 예외가 아니며, 마지막 출력 수집에도 상한이 있어 group을 벗어난 자손이 pipe를 쥐고 있어도 부모는 유계 시간에 `PROCESS_TIMEOUT` envelope을 낸다.
- **격리 범위(정직한 한정)**: 이 reap은 *process group* 단위다. 자식이 `setsid`로 group을 벗어나 띄운 자손은 macOS에 cgroup이 없어 포획·차단할 수 없다. diagnostics `descendant_containment: "process-group-only"`가 이 범위를 그대로 기록하며, 완전 격리를 주장하지 않는다.
- 같은 이유로 REQ-M05의 "디스크에 secret 없음" 보장은 **부모 복귀 시점의 부모 소유 아티팩트**와 **exact literal** 기준이다. group을 벗어난 자손의 사후 쓰기와 자식이 재인코딩한 값은 이 보장 밖이다.
- exact literal 판정은 **파일 내용과 entry 이름 양쪽**, 그리고 JSON **키와 값 양쪽**에 적용한다. raw 진단 텍스트는 `\uXXXX`·`\/` 같은 JSON escape로 되돌린 형태까지 같은 literal로 본다. 두 키가 redaction 후 같은 이름으로 겹치면 병합하지 않고 `RESULT_MALFORMED`(BLOCKED)이다. 자식이 자격증명을 파일명·디렉토리명으로 인코딩하면 정규 파일·symlink·FIFO는 unlink하고, 디렉토리는 하위 처리 후 `rmdir`하거나 실패 시 redaction한 이름으로 제자리 rename한다. 둘 다 못 하면 `PURGE_INCOMPLETE`(BLOCKED)이며 조용한 성공이 아니다. 모든 조작은 부모가 이미 쥔 디렉토리 descriptor 기준이라 stage root 밖으로는 나가지 않는다.
- **BLOCKED일 때의 잔존(정직한 한정)**: 자식이 cleanup을 pin하면(`chflags uchg`, mode strip, 재귀 한계를 넘는 깊이) 부모는 owner 권한으로 복구를 시도하지만 실패는 `cleanup_errors`와 함께 BLOCKED로만 보고된다. 이때 output_root에 부모가 복사한 자격증명 사본이 남아 있을 수 있으므로 **운영자는 BLOCKED 판정의 output_root를 폐기한다.**
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
- packet에 secret material 유입 없음 — 있으면 provider 기동 전 `PACKET_SECRET_MATERIAL_PRESENT`. deny 이름 규칙(`.env`·`.env.*`·`local.properties`·`secrets`·`.jks .keystore .p12 .pfx .pem .key`)은 leaf뿐 아니라 **모든 경로 성분**에 대소문자 무관하게 적용한다
- packet entry의 상위 경로 성분이 symlink가 아님 — 아니면 복사 전 `PACKET_PATH_UNSAFE`
- provider가 남긴 결과 파일이 링크·FIFO·하드링크가 아닌 자기 정규 파일 — 아니면 `RESULT_PATH_UNSAFE`
- 결과 파싱·redaction·canonical 직렬화가 자식이 정한 중첩 깊이로 `RecursionError`를 내도 stage 밖으로 나가지 않는다 — `RESULT_MALFORMED`(BLOCKED)이며 cleanup·diagnostics는 그대로 완주한다
- stage output_root가 실행 전후 같은 디렉토리 — 삭제·교체 시 `OUTPUT_ROOT_TAMPERED`
- envelope `result_sha256`가 semantic canonical JSON에서 재계산한 값과 일치 — 불일치는 `SEALED_RESULT_HASH_MISMATCH`
- findings와 top-level status 모순 없음 — 모순은 `SEMANTIC_STATUS_CONTRADICTS_FINDINGS`
- `findings`/`blocking`/`evidence_refs`/`status`와 finding의 `finding_id`/`blocking`/`disposition`/`risk` 타입이 schema대로 — 이탈은 `SEMANTIC_SCHEMA_INVALID`, `blocking` ID가 findings에 없으면 `SEMANTIC_BLOCKING_ID_UNKNOWN`
- stage cleanup 완주 — `.provider-home`이 남으면 `PROVIDER_HOME_NOT_REMOVED`, 크기 상한 초과·읽기 불가·이름 제거 불가로 마치지 못한 항목이 있으면 `PURGE_INCOMPLETE`. `ENOENT`만 "이미 없음"이며, 읽기는 되지만 탐색이 막힌 디렉토리(0400·0600)를 포함해 그 밖의 실패는 부모가 자기 descriptor로 mode를 한 번 회복해 재시도하고, 그래도 확인하지 못하면 unscanned로 보고한다. 부모가 봉인한 결과 파일 자체가 purge·rename·unscanned로 잡히면 `SEALED_RESULT_PURGED`(BLOCKED)다. cleanup 단계는 서로 격리되어 한 단계가 어떤 예외를 내도(OSError가 아니어도) 다음 단계가 실행되며, 그 실패는 `PROVIDER_HOME_CLEANUP_FAILED`·`RAW_RESULT_CLEANUP_FAILED`·`PURGE_FAILED`로 코드화된다. 전부 조용한 성공이 아니라 BLOCKED다.
- diagnostics의 경로·문자열 필드(`purged_secret_files`·`renamed_secret_paths`·`leftover_temp_paths`·`unscanned_paths`·`purge_notes`)는 자식이 정한 이름이므로 known_secrets + vendor redaction을 거친 뒤에만 sealed result·디스크에 기록한다.

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

`hb-eval-review run`이 저장소 밖 `--output-root`(기본 `${HB_EVAL_REVIEW_HOME:-~/.hb-eval-review}/{repo-slug}/{identifier}/run-{n}/`) 아래에 만드는 파일은 다음이 전부다. 완료 후 `final-result.json`·`execution-manifest.json`만 저장소의 `.harness/artifacts/{track}/{identifier}/eval-review/run-{n}/`로 실제 복사한다. `gate-result.json`([E0]이 확인), packet JSON(`--packet`), packet source 디렉토리(`--packet-source`), stage별 prompt 파일(`--evaluate-prompt`·`--review-prompt`)은 부모가 run 전에 준비하는 입력이며 run이 만들지 않는다. envelope의 stage/engine이 두 enum 밖이면 sealed 파일명은 `unknown-{index}.json`이다. provider 작업 디렉토리의 내용은 provider별로 다르며 봉인 결과의 정본은 `sealed-results/`다.

```text
${HB_EVAL_REVIEW_HOME:-~/.hb-eval-review}/{repo-slug}/{identifier}/run-{n}/    ← `--output-root`. run마다 새 빈 디렉토리(`eval-review/` 자체는 `qa-snapshot.json` 등 기록이 있어 쓸 수 없다), packet source 밖
  execution-manifest.json      ← 영속: packet·source·evidence ID, prompt/effective prompt digest, model ID, isolation policy, repo·id·output 경로, 복사 크기·소요 시간. packet·prompt·model·materialized 검증 또는 source 재검증 실패로 조기 BLOCKED되면 없다. Gate·TDD·증거 사본 검증 실패 때도 없다
  materialized-packet/         ← 임시: content-verified packet copy(manifest.json + source/ + evidence/). evidence/는 Gate·TDD·전체 diff 사본이며 사본 bytes hash를 검증한 뒤 0444로 잠근다. provider에는 packet root 읽기만 추가하고 peer output은 계속 차단한다. 증거 준비·검증 실패도 packet 전체를 정리한다. 복사 직후 source 재검증이 실패하거나(`SOURCE_CHANGED_BEFORE_MATERIALIZE`·`SOURCE_SNAPSHOT_UNAVAILABLE`) 재계산 자체가 거부되면 run이 지우고(제거 실패는 `MATERIALIZED_PACKET_REMOVE_FAILED`로 원인 코드 뒤에 함께 보고하며, 일부만 지워졌거나 권한이 바뀐 잔여물이 남을 수 있다 — 보관·재사용 대상이 아니다), 그 밖에는 run이 지우지 않지만 보관 대상이 아니다
  evaluate-claude/             ← 임시: Evaluate provider 작업 디렉토리. Review 시작 전 삭제(Evaluate가 BLOCKED면 남는다)
  evaluate-codex/              ← 임시: Evaluate provider 작업 디렉토리. Review 시작 전 삭제(Evaluate가 BLOCKED면 남는다)
  review-claude/               ← 임시: Review provider 작업 디렉토리. Review가 실행됐을 때만
  review-codex/                ← 임시: Review provider 작업 디렉토리. Review가 실행됐을 때만
  final-result.json            ← 영속: run 결과(PASS/BLOCKED). packet·prompt·model·materialized 검증 또는 source 재검증 실패로 조기 BLOCKED되면 없다. Gate·TDD·증거 사본 검증 실패 때도 없다
  sealed-results/              ← 영속: stage·engine별 sealed result. 한 파일에 semantic + envelope
  sealed-results/evaluate-claude.json
  sealed-results/evaluate-codex.json
  sealed-results/review-claude.json    ← Review가 실행됐을 때만
  sealed-results/review-codex.json     ← Review가 실행됐을 때만
```

Raw provider 결과는 봉인 후 수정하지 않는다. finding disposition이나 사람 판정은 별도 reconciliation artifact에 기록한다.
