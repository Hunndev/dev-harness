# 긴급 수정 (hotfix, T0)

**재현 테스트 → 최소 수정 → 단위 테스트**로 개발 부담을 줄이되, 마지막 Gate → 검사(Evaluate) → 평가(Review)는 생략하지 않는다.
오타·한 줄 버그·긴급 hotfix 전용.

> **Tier 선택**
> - `/hb-ios:maintenance:hotfix` — **이 문서.** 최소 ceremony. 영향도 분석, RCA, convention 충돌 체크 등은 전부 생략.
> - `/hb-ios:maintenance:auto` — 일상 유지보수. RCA 포함.
> - `/hb-ios:maintenance:deep` — full ceremony, 3방향 영향 Team 포함.

## 사전 조건

- **수정 범위가 명확**해야 한다. "이 파일의 이 라인"처럼 지목 가능해야 한다.
- 프로덕션 장애 대응이거나, 오타·한 줄 수정처럼 영향 범위가 단일 모듈 이하여야 한다.
- 사용자가 재현 방법을 알고 있어야 한다 (재현 테스트를 1단계에서 바로 작성해야 하므로).

## 핵심 원칙

- **범위 폭주 금지**: 사용자가 지정한 파일·라인 이외는 절대 수정하지 않는다. "옆에 있는 코드도 같이 정리"는 금지.
- **재현 테스트 필수**: 수정 전에 반드시 현재 상태에서 FAIL하는 테스트를 남긴다. 이게 없으면 "진짜 고쳐졌나?"를 증명할 수 없다.
- **새 ADR/convention 금지**: 이 경로에서 어떤 설계 결정도 새로 만들지 않는다. 필요하면 중단하고 planning으로 에스컬레이션.
- **개발 ceremony 최소화**: RCA, 광범위 영향도 분석, 리팩터링, 전체 회귀는 생략한다. 단, H4 Gate와 blind fresh Dual Evaluate/Review는 생략하지 않는다. 의심되면 `:auto`로 전환.
- **TDD 사이클 부분 적용**: H1=Red, H2=Green. Refactor는 hotfix 범위를 벗어나므로 의도적으로 제외. 자세한 프로토콜은 `commands/shared/tdd.md` 참조.

## 식별자

이슈 ID가 있으면 그대로. 없으면 `hotfix-YYYYMMDD-slug`.
예: `BUCCL-iOS-99` 또는 `hotfix-20260408-cookie-nullref`

## 파이프라인

### [H1] 재현 테스트 [TDD Red] (메인)

1. **Pre-flight 점검**: `commands/shared/tdd.md`의 "Pre-flight 점검" 섹션을 수행한다:
   - `xcodebuild -scheme bucclapp test -enumerate-tests` → exit 0 확인 (아니면 중단 + 사용자 보고)
   - `xcodebuild -version`으로 Xcode 버전 확인(정보용). target test는 `-only-testing:bucclappTests/{TestClass}` 식별자로 지정 (와일드카드 없음, 0개 실행은 PASS 아님 — 실행 수 판정 규칙은 `commands/shared/tdd.md`)
   - 아티팩트 디렉토리의 stale `tdd-red-debug.md` 삭제 (hotfix는 Green→Red 재작성이 없으므로 `tdd-red-revisions.md`는 해당 없음)
2. 메인의 현재 branch에서 직접 수행한다 — T0는 fork를 생략한다 (한 파일·한 라인 수정에 격리 이득이 없다).
3. 사용자가 제시한 증상을 **FAIL로 입증하는 최소 테스트**를 작성한다.
   - 파일: `bucclapp/bucclappTests/{package}/{Module}Hotfix{Identifier}Tests.swift` (identifier는 CamelCase로 변환)
   - 가장 좁은 범위(단일 함수/클래스 — 브리지 함수 하나, 결정 로직 하나)로 한정
4. `commands/shared/tdd.md`의 **T0 Test Design Check**로 완료기준·행동 assertion·mock 경계를 확인하고 `tdd-design-metadata.json`을 준비한다. 부모 CLI로 선택한 재현 테스트를 실행한다. `--test-file`에는 3번에서 만든 파일의 저장소 상대 경로를 넣는다.

   ```bash
   <플러그인 설치 경로>/bin/hb-eval-review tdd-check red --repo <root> --test-file {test-file} --cmd 'xcodebuild -project bucclapp/bucclapp.xcodeproj -scheme bucclapp test -only-testing:bucclappTests/{Module}Hotfix{Identifier}Tests' --design {artifacts-dir}/tdd-design-metadata.json --out <root>/.harness/artifacts/maintenance/{identifier} --issue-type hotfix && \
   cp {artifacts-dir}/hotfix-red-log.txt {artifacts-dir}/xcodebuild-red.log && \
   tail -30 {artifacts-dir}/xcodebuild-red.log > {artifacts-dir}/hotfix-red-log.txt
   ```

   `&&` 뒤의 복사·tail은 부모 CLI가 Red를 수용해 exit 0으로 끝난 경우에만 실행한다. 전체 redacted 출력은 `xcodebuild-red.log`, 요약은 `hotfix-red-log.txt`에 남긴다. CLI가 실패하면 후처리하지 않고 생성된 로그를 진단용으로만 사용한다. 실제 xcodebuild의 실패 exit를 부모 CLI의 수용 여부와 혼동하지 않는다.

5. 부모가 `hotfix-red-log.txt`와 schema 1.2 `tdd-test-design-result.json`을 생성했는지 확인한다. exit ≠ 0만으로는 부족하다. 선택된 테스트가 1개 이상 실제 실행되고 버그를 드러내는 assertion으로 실패해야 한다. 식별된 compile·collection·import·fixture 오류는 stdout/stderr 어디에 있어도 올바른 Red가 아니다.
6. 재현 불가 시 즉시 중단하고 사용자에게 추가 정보를 요청한다. **재현 안 되는데 고치지 않는다.**
7. `.harness/artifacts/maintenance/{identifier}/hotfix-reproduction.md`에 기록한다:
   - **서두 약식 seed 3줄**: 목표 / 범위(수정할 한 곳) / 완료기준(단위 테스트 PASS) — T0 예외의 seed 갈음
   - 재현 단계
   - 테스트 파일 경로
   - FAIL 출력 요약
8. 부모가 생성한 `tdd-test-design-result.json`의 Design 검수와 관측 baseline이 모두 통과해야 H2로 진행한다. 관측값·hash·status를 모델이 덮어쓰지 않는다. 하나라도 불명확하면 구현하지 않고 `:auto`로 에스컬레이션한다.

### [H2] 수정 [TDD Green] (메인)

1. **Red 테스트(H1)가 PASS가 되는 '최소 수정'만** 수행한다. 사용자가 지정한 파일·라인 이외는 수정하지 않는다.
   - **판정 기준**: 이 수정이 아래 "Refactor 금지" 정의의 **허용** 범주인가? "이 변경을 되돌렸을 때 H1 테스트가 다시 FAIL하는가?"의 답이 YES이면 허용, NO이면 Refactor이므로 금지.
   - 금지 범주에 해당하면 즉시 중단하고 `/hb-ios:maintenance:auto`로 에스컬레이션한다.
2. 수정 즉시 H1의 대상 테스트 명령으로 **PASS**가 되는지 확인한다. 최종 실행 관측과 봉인은 H3의 관련 단위 테스트 검수 후 `tdd-check green`으로 수행한다.
3. H3의 부모 실행이 생성하는 `hotfix-green-log.txt`를 최종 PASS 로그로 사용한다. 수동 출력이나 테스트 marker로 관측 증거를 대신하지 않는다.
4. PASS가 아니면 원인을 추정해 다시 시도한다. **2회 실패 시 중단하고 `:auto` 또는 `:deep`으로 전환 제안**.
5. 수정 내용과 예상되는 side effect를 사용자에게 한 줄로 보고한다.

### [H3] 단위 테스트 [Refactor 금지] (Sub-agent)

`auto`와 달리 **전체 스위트를 돌리지 않는다**. 수정된 모듈의 단위 테스트만 실행한다.

1. `xcodebuild -scheme bucclapp test -only-testing:bucclappTests/{Module}Hotfix{Identifier}Tests` + 해당 모듈의 기존 테스트 클래스(`-only-testing:` 반복). 실행 수 ≥ 1 확인(실행 수 판정 규칙은 `commands/shared/tdd.md`).
2. 필요 시 `xcodebuild -scheme bucclapp build`와 SwiftLint(설치·설정된 경우만 — `commands/shared/verify.md` 2. 린트)를 실행한다. lint 수정이 단순 포맷을 넘어가면 `:auto`로 전환한다.
3. 결과 확인:
   - H1 재현 테스트: **PASS**여야 함
   - 기존 단위 테스트 중 **새로 실패한 것이 있는지** 확인
4. 새로 실패한 테스트가 있으면:
   - **단위 테스트 범위 내**라면 → H2로 돌아가 수정 루프
   - **다른 모듈의 테스트가 실패**라면 → hotfix 범위를 벗어남. 즉시 중단하고 **에스컬레이션** (아래 참조)
5. `.harness/artifacts/maintenance/{identifier}/hotfix-summary.md`에 기록:
   - 수정된 파일 목록
   - H1 재현 테스트 파일 경로
   - 단위 테스트 통과/실패 요약
5. **T0 Test Sensitivity Check**를 수행한다. 위 관련 단위 테스트 결과와 위험도·mutation 판단을 `tdd-sensitivity-metadata.json`에 기록하고, H1이 생성한 **동일한 고정 Design**을 입력으로 부모 실행을 수행한다.

   ```bash
   <플러그인 설치 경로>/bin/hb-eval-review tdd-check green --repo <root> --test-file {test-file} --cmd 'xcodebuild -project bucclapp/bucclapp.xcodeproj -scheme bucclapp test -only-testing:bucclappTests/{Module}Hotfix{Identifier}Tests' --design {artifacts-dir}/tdd-test-design-result.json --sensitivity {artifacts-dir}/tdd-sensitivity-metadata.json --out <root>/.harness/artifacts/maintenance/{identifier} --issue-type hotfix && \
   cp {artifacts-dir}/hotfix-green-log.txt {artifacts-dir}/xcodebuild-green.log && \
   tail -30 {artifacts-dir}/xcodebuild-green.log > {artifacts-dir}/hotfix-green-log.txt
   ```

   부모 CLI가 Green을 수용한 뒤에만 `&&` 후처리가 전체 redacted 출력을 `xcodebuild-green.log`에 보존하고 `hotfix-green-log.txt`를 tail 30줄로 만든다. CLI 실패 시 후처리하지 않는다. 전체 로그와 tail은 진단·표시용이며 JSON 관측값을 수정하지 않는다.

   부모가 schema 1.2 `tdd-sensitivity-result.json`과 `hotfix-green-log.txt`를 생성한다. exit 0, H1에서 선택된 모든 테스트 ID의 실제 PASS, 동일 테스트 hash와 run 결속이 필요하다. 로컬 상태가 온전할 때 형식이 맞는 외부 기록 없이 테스트 hash를 바꿀 수 없으며, `approved_red_revision: true` 자기보고만으로는 통과하지 않는다. 상태 삭제 초기화·digest 재계산·승인 출처의 절차적 신뢰 한계는 `commands/shared/tdd.md`를 따른다. 테스트가 Green 과정에서 바뀌었거나 결함을 잡지 못하면 `BLOCKED`하고 `:auto`로 에스컬레이션한다. hotfix에서 승인 없는 H1 재시작으로 고정 baseline을 교체하지 않는다. H3 이후 구현이 바뀌면 Green의 `observed.sut_sha256`가 현재 source view와 달라 Gate가 차단하므로 같은 고정 Design으로 `tdd-check green`을 다시 실행한다.

> **Refactor 금지 — 조작적 정의**:
> - **허용**: H1 Red 테스트를 PASS시키는 데 **직접 필요한** 코드 변경 (새 조건, null 체크, 타입 가드, 수정된 리터럴, 올바른 분기 추가).
> - **금지**: 이름 변경, 함수 추출, 중복 제거, 형식 정리, import 재배치, 근방 코드 스타일 수정.
> - **판정 기준**: "이 변경을 되돌렸을 때 H1 테스트가 다시 FAIL하는가?" YES → 허용, NO → 금지(Refactor).
> - **Compound fix 예외**: 하나의 수정이 **여러 독립적 변경의 합집합**으로 이루어질 때 (예: 두 클래스에 동시에 null 체크를 넣어야 FAIL이 해소되는 경우), **전체 합집합을 단일 fix로 간주**한다. 개별 변경을 독립 평가하지 않는다. 단, 합집합이 2개 이상 모듈에 걸치면 hotfix 범위 밖이므로 `:auto`로 에스컬레이션한다.
> 코드 정리가 필요하면 `/hb-ios:maintenance:auto`로 전환한다.

### [H4] Gate → 검사(Evaluate) → 평가(Review) (부모 runner)

Gate·pack·run은 진행 중인 작업에도 즉시 schema 1.2 관측 쌍을 요구한다. 1.0·1.1 또는 그 버전으로 하향한 증거는 `TDD_OBSERVATION_REQUIRED`로 차단하고 provider를 실행하지 않는다. 기존 작업도 `tdd-check red`·`green`을 재실행해야 한다. 1.0·1.1의 의미 호환은 validator 층에만 남긴다.

1. Production·DB·secret·인증·권한·destructive 변경이면 구현 전에 받은 사용자 승인을 확인한다. 승인이 없으면 `BLOCKED`다.
2. H1~H3·request·AC 증거를 먼저 완성하고 `hb-eval-review gate --repo <root> --cmd '<실제 검사 argv>' --out <root>/.harness/artifacts/maintenance/{identifier}/eval-review/gate-result.json --issue-type hotfix`로 deterministic Gate를 통과시킨다.
3. `hb-eval-review pack --repo <root> --artifacts <root>/.harness/artifacts/maintenance/{identifier} --request-source hotfix-reproduction.md --base <ref> --claude-model <model> --codex-model <model> --issue-type hotfix`로 Gate·TDD·전체 diff·AC를 같은 snapshot에 결속한다.
4. 즉시 `hb-eval-review run --from <root>/.harness/artifacts/maintenance/{identifier}/eval-review/packet --claude-model <model> --codex-model <model>`을 실행한다. blind fresh Claude+Codex **검사(Evaluate)**가 모두 PASS일 때만 같은 packet으로 **평가(Review)**를 진행한다. source는 저장소 루트이며 output은 저장소 밖이다. provider 누락·timeout·schema·Gate·TDD·snapshot·사본 hash 오류는 fail-closed `BLOCKED`다.
증거를 수정했다면 `gate` → `pack`을 다시 실행하여 새 결속을 만든 뒤 run한다.

5. 부모 finalizer의 `PASS`만 완료로 인정한다. 모델의 process/timeout/mutation 자기보고는 실행 증거로 인정하지 않는다.

### 완료

`INDEX.md`를 생성하여 다음을 기록한다:
- `tier: hotfix`
- 수정된 파일 목록 (범위 제한 준수 여부 명시)
- H1 재현 테스트 파일 경로
- 단위 테스트 결과 요약
- Test Design/Sensitivity 결과와 sealed packet ID
- Dual Evaluate/Review 및 parent finalizer 결과 경로
- **형제 플랫폼(AOS) 반영 필요 여부** (한 줄 — hotfix에서 계약을 바꿨다면 그 자체가 에스컬레이션 신호)
- **에스컬레이션 여부**: 범위 초과로 hotfix가 중단됐는지, auto/deep으로 넘겨졌는지

## 산출물

```
.harness/artifacts/maintenance/{identifier}/
  hotfix-reproduction.md
  hotfix-red-log.txt      ← 수용된 Red 전체 로그의 tail 30줄
  hotfix-green-log.txt    ← 수용된 Green 전체 로그의 tail 30줄
  xcodebuild-red.log      ← 부모가 캡처한 Red 전체 redacted 출력
  xcodebuild-green.log    ← 부모가 캡처한 Green 전체 redacted 출력
  hotfix-summary.md
  tdd-test-design-result.json  ← 부모 생성 schema 1.2·고정 baseline
  tdd-sensitivity-result.json  ← 부모 생성 schema 1.2·Green 관측
  eval-review/gate-result.json
  eval-review/diff.patch
  eval-review/packet/packet.json
  eval-review/packet/evaluate-prompt.md
  eval-review/packet/review-prompt.md
  eval-review/run-{n}/final-result.json       ← 외부 run 결과의 실제 사본
  eval-review/run-{n}/execution-manifest.json ← repo·id·경로·복사 크기·소요 시간
  INDEX.md
```

> `hotfix` tier는 `root-cause.md`, `impact-analysis.md`, `convention-check.md`, `fix-plan.md`, `regression-report.md`, `review-comments.md`를 생성하지 않는다.
> 이 중 하나라도 필요하다고 판단되면 hotfix가 아니다 → `:auto` 또는 `:deep`으로.

## 에스컬레이션 규칙

다음 경우에는 hotfix를 **즉시 중단**하고 적절한 tier로 넘긴다:

| 상황 | 전환 대상 |
|---|---|
| 수정 범위가 2개 이상 모듈에 걸친다 | `/hb-ios:maintenance:auto` |
| 기존 ADR/convention 위반이 의심된다 | `/hb-ios:maintenance:deep` |
| 회귀가 단위 테스트 범위를 벗어난다 | `/hb-ios:maintenance:auto` (전체 회귀 필요) |
| 새 설계 결정이 필요하다 | `/hb-ios:planning:auto` 또는 `:deep` |
| H2 수정이 2회 연속 실패 | `/hb-ios:maintenance:auto` (RCA 필요) |
| 쿠키/세션 동기화·딥링크·푸시 흐름 변경이 필요하다 | `/hb-ios:maintenance:deep` (shell 계약 흐름은 hotfix 범위 아님) |
| 브리지 계약(함수 시그니처·메시지 포맷) 변경이 필요하다 | `/hb-ios:maintenance:auto` (브리지 계약 변경은 hotfix 범위 아님 — 형제 플랫폼 반영 기록 필요) |
| 리팩토링이 필요하다 | `/hb-ios:maintenance:auto` (hotfix에서는 Refactor 금지) |

에스컬레이션 시 `INDEX.md`에 "hotfix에서 시작해 {대상}으로 전환" 명시하고, 이미 작성한 `hotfix-reproduction.md`는 새 tier에서 `reproduction.md` 역할로 재사용된다.
