# TDD (Red-Green-Refactor) 프로토콜

모든 feature/maintenance 커맨드가 참조하는 공통 테스트 우선 개발 프로토콜.
기본 사이클은 **Red → Green → Refactor** 순서로 수행한다. maintenance의 refactor는 **PASS baseline → Design 검수 → Refactor → PASS·Sensitivity 검수** 순서를 따른다.
프레임워크: **Django + pytest** (Django 테스트 러너 `manage.py test`가 아니라 **pytest**를 사용한다).

---

## Pre-flight 점검 (모든 TDD 트랙의 F1/M1/H1 시작 시 필수)

각 트랙이 TDD 사이클에 진입하기 전에 **반드시** 다음 2가지를 확인한다. 실패 시 사이클을 시작하지 않고 사용자에게 명확한 원인과 함께 중단을 보고한다. 이 체크는 "Red가 구현 부재 때문인가, 환경 설정 때문인가"를 사전에 구별해 false-escalation을 방지한다.

### 1. 테스트 러너 사전 검증 (fail-fast)

```bash
pytest --collect-only -q
```

- exit 0 → pytest 및 pytest-django 설치됨, `DJANGO_SETTINGS_MODULE` 정상 resolve → 사이클 진행
- exit ≠ 0 → 즉시 중단하고 사용자에게 보고:
  - "pytest가 설치되지 않았습니다. `pip install pytest pytest-django` 필요" OR
  - "`pytest.ini` 또는 `conftest.py`에 `DJANGO_SETTINGS_MODULE` 설정 누락" OR
  - 실제 에러 메시지 그대로 전달

### 2. 이전 TDD 아티팩트 정리 (stale counter 방지)

새 작업을 시작할 때 아티팩트 디렉토리(`.harness/artifacts/{track}/{identifier}/`)의 이전 작업 잔존 카운터를 정리한다. 이미 수용된 baseline으로 진행 중인 작업을 재개할 때는 아래 정리를 실행하지 않는다. revision 카운터와 부모가 고정한 run을 유지해야 한다:

```bash
rm -f {artifacts-dir}/tdd-red-debug.md
rm -f {artifacts-dir}/tdd-red-revisions.md
```

`tdd-baseline-log.txt`, `tdd-green-log.txt`는 부모 실행이 기록하고 `tdd-refactor-notes.md`는 해당 단계가 작성한다. 고정된 Design·run 기록을 삭제하거나 수동으로 덮어써 새 baseline을 만들지 않는다. 동일 identifier의 수용된 baseline을 바꾸려면 아래 승인된 Red 재작성 절차를 따른다.

---

## 사이클 정의

### Red: 실패하는 테스트 작성 (또는 Green baseline 고정)

1. 테스트가 실행되면 FAIL해야 함 (구현이 없거나 기존 동작이 버그이므로)
   - 단, **maintenance의 refactor 이슈 유형**만 `PASS_TO_PASS` 예외를 사용한다. 현재 동작의 characterization test가 실제 PASS하는 baseline을 고정한다. 그 밖의 유형은 `RED_TO_GREEN`이며, JSON의 baseline 값만 바꿔 작업 유형을 refactor로 취급하지 않는다.
2. 테스트 범위: 하나의 수용기준(AC) 또는 하나의 버그 재현
3. 아래 Test Design 항목을 검수하고 `tdd-design-metadata.json` 입력을 준비한 뒤 부모 CLI로 baseline을 직접 실행한다. `--test-file`은 실제 테스트 파일의 저장소 상대 경로다. `--issue-type`에는 실제 작업 유형(`feature`, `bug`, `performance`, `refactor`, `hotfix`)을 넣는다.

   ```bash
   <플러그인 설치 경로>/bin/hb-eval-review tdd-check red --repo <root> --test-file {test-file} --cmd 'pytest {app}/tests/test_{module}.py -v' --design {artifacts-dir}/tdd-design-metadata.json --out {artifacts-dir} --issue-type {issue-type}
   ```

   부모가 `tdd-baseline-log.txt`와 schema 1.2 `tdd-test-design-result.json`을 생성한다. `--cmd` 안에 파이프·리다이렉션·셸 조합을 넣지 않는다. 로그 tail이나 exit code만으로 Red를 인정하지 않고, 스택 리포트에서 선택된 테스트가 1개 이상 실제 실행됐으며 assertion 때문에 실패했는지 확인한다. `refactor`는 선택된 테스트의 실제 PASS baseline을 요구한다.

4. **실패 이유 검증 (bug/feature 유형)**:
   - 구현 부재 / assertion fail → **올바른 Red** → Green 단계로 진행
   - syntax / import / fixture 오류 → **올바르지 않은 Red**
     - (a) 테스트 코드를 수정하고 재실행 (최대 3회)
     - (b) 3회 후에도 올바르지 않은 Red면: 원인을 `tdd-red-debug.md`에 기록하고 사용자에게 보고 (스택/fixture 혼란 가능성)
     - (c) 부모의 `tdd-check red` 재시도가 `tdd-baseline-log.txt`를 기록한다. 올바르지 않은 Red는 수용된 고정 baseline을 만들지 않는다.
     - (d) **재시도 카운터 persistence**: 재시도 횟수는 `tdd-red-debug.md`의 attempt 라인 수(`attempt N: {reason}`)로 결정한다. 파일이 없으면 0부터 시작. 워크플로우 재개 시에도 카운터가 유지된다.

### Test Design Check: 변경 구현 전 테스트 코드 검수

**구현 코드를 작성하기 전에** 다음을 검사해 `tdd-design-metadata.json`에 의미 검수 결과를 작성한다. `tdd-check red`가 이 입력과 직접 실행한 baseline을 결합해 schema 1.2 `tdd-test-design-result.json`을 생성해야 Design 검수가 완료된다. `RED_TO_GREEN`은 올바른 Red 실패, maintenance의 refactor만 `PASS_TO_PASS`의 실제 PASS baseline을 요구한다. RED에서는 `red_failure_kind`가 필수이고, PASS baseline에서는 해당 필드를 넣지 않는다. 생성된 Design의 관측값이나 status를 모델이 수정하지 않는다.

1. 테스트 하나가 하나의 실제 AC 또는 하나의 재현 버그에 연결되는가.
2. 이름과 assertion이 내부 메서드 호출이 아니라 사용자가 관찰할 행동·상태·부작용·오류 계약을 검증하는가.
3. 성공·실패·경계 경로 중 해당 위험과 repository 정책이 요구하는 경로가 포함됐는가.
4. 외부 네트워크·시간·결제사 같은 불가피한 경계만 mock하며, **System Under Test 자체를 mock하지 않았는가**.
5. 순서·실시간·실제 네트워크에 불필요하게 의존하는 flaky 구조가 아닌가.
6. T2/high-risk는 구현 context와 분리된 read-only Sub-agent/Team lens가 테스트 설계를 독립 확인했는가.

검사 실패 시 변경 구현을 시작하지 않는다. 수용된 baseline이 아직 없다면 테스트를 수정하고 `tdd-check red`로 해당 baseline(RED의 올바른 실패 또는 PASS)을 다시 실행한다. 이미 고정된 baseline의 테스트를 바꿔야 하면 아래 승인된 Red 재작성 절차를 거친다.

### Green: 최소 구현으로 통과

`RED_TO_GREEN`의 단계다. `PASS_TO_PASS`는 Design 검수 후 Refactor로 이동하고, 변경 후 PASS 실행을 `tdd-green-log.txt`에 기록한다.

1. Red 테스트가 PASS가 되도록 **최소한의 코드만** 작성
2. 범위 폭주 금지: Red 테스트가 요구하지 않는 코드 추가 금지
3. 다른 기존 테스트가 깨지면 즉시 수정 (새로운 회귀 만들지 말 것)
4. 관련 회귀·위험도 검수를 마치고 `tdd-sensitivity-metadata.json`을 준비한 뒤 부모 CLI로 변경 후 테스트를 실행한다. `--design`에는 Red에서 생성된 **동일한 고정 Design 파일**을 전달한다.

   ```bash
   <플러그인 설치 경로>/bin/hb-eval-review tdd-check green --repo <root> --test-file {test-file} --cmd 'pytest {app}/tests/test_{module}.py -v' --design {artifacts-dir}/tdd-test-design-result.json --sensitivity {artifacts-dir}/tdd-sensitivity-metadata.json --out {artifacts-dir} --issue-type {issue-type}
   ```

   부모가 `tdd-green-log.txt`와 schema 1.2 `tdd-sensitivity-result.json`을 생성한다. exit 0이고 Red에서 선택된 테스트 ID 전체가 실제 실행·PASS해야 한다. argv의 문자열 동일성이나 테스트 파일 경로 포함 여부로 이를 대신하지 않는다.

5. 추가 검증 (Django 레이어 오류 조기 포착):

   ```bash
   python manage.py check
   ```

#### Green 단계에서 Red이 틀렸음을 발견한 경우

Green 구현 중 수용기준(AC) 자체가 잘못 서술되었거나 Red 테스트가 잘못된 대상을 검증한다는 증거가 나오면:

1. 구현을 **즉시 중단**하고 사용자에게 이유와 구체적인 수정안을 제시한다. 승인 없이 테스트를 수정해 Green을 만드는 것은 금지다.
2. 실제 사용자 승인 뒤 `tdd-red-revisions.md`에 `revision {N}: {reason}` 한 줄을 append한다. 파일의 revision 라인 수가 카운터이며 최대 2회만 허용한다. 파일이 없으면 0이고 한 번 복귀할 때 한 줄만 추가하며 reset하지 않는다. 3번째 요청은 중단하고 deep 트랙 또는 사용자 개입으로 에스컬레이션한다.
3. 부모/controller가 사용자 승인 메시지를 근거로 **저장소 밖의 승인 기록 JSON**을 준비한다. 모델·source·provider가 `approved_by`나 승인 사실을 스스로 만들어서는 안 된다. 기존 revision 라인이나 `approved_red_revision: true`만으로는 승인되지 않는다.
4. 이전 Red retry 카운터인 `tdd-red-debug.md`만 truncate한다. 새 테스트와 검수 metadata를 준비하고 Red 명령에 `--approval-record <controller-owned-external-json>`을 추가해 다시 실행한다. 부모는 기존 baseline을 보존하고 승인에 결속된 새 run을 만든다. Green은 새 Red의 `tdd-test-design-result.json`을 사용한다.

외부 승인 기록 형식은 다음과 같다. 아래는 필드 설명을 위한 예시이며, 실제 사용자 승인 없이 복사해 승인 기록으로 사용하지 않는다.

```json
{
  "schema_version": "1.0",
  "kind": "tdd-red-revision-approval",
  "repo": "<canonical absolute repo>",
  "git_dir": "<canonical absolute gitdir>",
  "artifacts": "<canonical absolute artifact output dir>",
  "run_id": "<기존 Design의 observed.run_id>",
  "test_file": "<저장소 상대 테스트 파일 경로>",
  "old_sha256": "<기존 baseline의 64자리 SHA-256>",
  "new_sha256": "<승인된 변경 후 64자리 SHA-256>",
  "revision": 1,
  "revision_line": "revision 1: <승인된 수정 사유>",
  "approved_by": "user",
  "approval_source": "<실제 사용자 승인 메시지 참조>",
  "recorded_at": "<UTC ISO timestamp ending Z>"
}
```

`--approval-record`는 부모/controller가 명시적으로 전달한다. 부모는 canonical repository·gitdir·artifact output·기존 run·test-file·old/new hash·revision 번호와 파일의 정확한 `revision_line`을 대조하고, 호출 전후 승인 기록의 bytes hash를 확인한다. 저장소 안의 기록, symlink 또는 `..`를 사용한 경로는 거부한다. `approval_source`는 사용자 승인 출처를 기록하는 값이며 암호학적 사용자 신원 검증을 뜻하지 않는다. 직접 Green에 승인 기록을 전달하는 경우에도 이 결속과 선택된 테스트 전체의 PASS 검사는 생략되지 않는다. 부모/controller가 명시적으로 전달한 형식이 맞는 외부 기록을 신뢰 입력으로 취급한다. 같은 세션이 기록을 작성하고 명령을 호출할 수 있으므로 사용자 승인 출처의 진위 확인은 절차적 책임이다.

### Test Sensitivity Check: Green 이후 회귀 검출력 확인

`RED_TO_GREEN`은 Green 이후 Refactor 전에, `PASS_TO_PASS`는 주 변경인 Refactor 완료 후 아래 의미 검수를 수행한다. 회귀·위험도·mutation 결과를 `tdd-sensitivity-metadata.json` 입력으로 준비하고 위 `tdd-check green`을 실행해 schema 1.2 `tdd-sensitivity-result.json`을 생성한다. 부모가 Design과 같은 `baseline`, 관측한 실행 결과와 hash를 기록한다.

1. 같은 test identity와 test-file hash에 대해 `RED_TO_GREEN`은 `red_outcome=FAIL` → `green_outcome=PASS`, `PASS_TO_PASS`는 `red_outcome=PASS` → `green_outcome=PASS`를 확인한다. 필드 이름은 두 경우 모두 유지한다.
2. 로컬 상태가 온전할 때 hash가 달라지면 `tdd-red-revisions.md`의 해당 라인과 변경 전후 hash 등에 결속된 형식이 맞는 외부 기록이 필요하다. `approved_red_revision: true` 자기보고나 저장소 내부 파일만으로는 통과하지 않으며 `TDD_TEST_IDENTITY_CHANGED`로 `BLOCKED`다. 실제 사용자 승인에 근거해 기록을 작성하는 것은 부모/controller의 절차적 책임이다. 승인된 Red 재작성은 새 baseline부터 다시 검수한다.
3. repository가 정의한 관련 회귀 suite가 PASS인지 확인한다.
4. 인증·권한·결제·DB 무결성·API contract 등 T2/high-risk에서 안전하고 지원되는 경우 격리 worktree의 targeted mutation/revert로 핵심 결함을 되살렸을 때 테스트가 FAIL하는지 확인한다.
5. 필요한 mutation을 실행할 수 없으면 사유를 명시하고 `BLOCKED` 또는 `NEEDS_HUMAN_REVIEW`로 보낸다. 조용히 PASS하지 않는다.

T0에는 routine mutation을 강제하지 않는다. 동일 테스트의 해당 baseline 전환(FAIL→PASS 또는 PASS→PASS)과 관련 회귀가 최소 조건이다. PASS baseline도 test hash·승인된 revision·회귀·필요한 mutation 검사를 생략하지 않는다.

### Refactor: 테스트 녹색 유지하며 정리

1. Green 상태에서만 시작 (모든 테스트 PASS 확인 후)
2. 중복 제거, 네이밍 개선, 구조 정리
3. **새 기능 금지**, **테스트 변경 금지**
4. 각 리팩토링 후 전체 테스트 재실행. 깨지면 즉시 revert.

   ```bash
   pytest {app}/tests/test_{module}_*.py -v
   ```

5. 변경 내용을 `tdd-refactor-notes.md`에 요약한다. 최종 코드 변경 뒤 의미 검수 metadata를 갱신하고 같은 고정 Design을 사용하는 `tdd-check green`을 다시 실행해 최종 source의 관측 증거를 남긴다.

---

## 이슈 유형별 적용

| 유형 | Baseline 의미 (Red 단계) | Green | Refactor |
|------|------------------------|-------|----------|
| feature (신규 기능) | `RED_TO_GREEN`: 수용기준에서 도출한 **FAIL** 테스트 | 최소 구현으로 PASS | 필수 |
| bug (maintenance) | `RED_TO_GREEN`: 버그 재현 **FAIL** 테스트 | 버그 수정으로 PASS | 선택 (fix-plan 범위 내) |
| refactor (maintenance) | `PASS_TO_PASS`: **PASS** characterization baseline | 변경 후 PASS 기록 | **주 단계**, 이후 Sensitivity |
| performance (maintenance) | `RED_TO_GREEN`: 임계치 미달 **FAIL** 테스트 | 임계 통과 구현 | 선택 |
| hotfix | `RED_TO_GREEN`: **FAIL** 재현 테스트 (`hotfix-red-log.txt` 사용) | 최소 수정으로 PASS | **금지** (범위 폭주 위험) |

> **`tdd-baseline-log.txt`의 의미는 이슈 유형에 따라 다르다**: bug/feature/performance는 FAIL 증거, refactor는 PASS baseline. 이는 "Refactor 단계에서 이 로그와 비교해 동작이 보존되었는가"를 판단하는 고정점이다.

> **refactor 이슈 유형 특이사항**: characterization test를 작성하여 현재 동작을 Green baseline으로 고정한다. M5 또는 M7의 "수정 실행" 단계는 실질적으로 생략되고, M5.5/M7.5 Refactor가 주 단계가 된다. baseline 테스트는 리팩토링 전후 모두 PASS여야 하며, 변경 후 로그와 두 JSON 증거도 모두 생성한다.

---

## 아티팩트 규약

Red/Green/Refactor가 적용되는 단계에서 다음 파일을 **반드시** 생성:

```
.harness/artifacts/{track}/{identifier}/
  tdd-baseline-log.txt     ← Red 단계 baseline (FAIL or PASS per issue type)
  tdd-green-log.txt        ← 변경 후 PASS 증거 (refactor 포함)
  tdd-test-design-result.json ← 부모 생성 schema 1.2·고정 baseline·Design 의미 검수·observed
  tdd-sensitivity-result.json ← 부모 생성 schema 1.2·선택된 테스트 전환·hash·회귀·mutation 증거
  tdd-refactor-notes.md    ← Refactor 내용 요약 (skip 시 "skipped: {reason}")
  tdd-red-revisions.md     ← (선택) Red 재작성 이력. 없으면 생성 안 함.
```

- `tdd-baseline-log.txt`: bug/feature는 FAIL 출력, refactor는 PASS characterization 출력 (부모가 캡처한 stdout/stderr와 실제 실행 결과)
- `tdd-green-log.txt`: 구현 또는 refactor 후 PASS 출력 (테스트 통과 증거)
- `tdd-refactor-notes.md`: 리팩토링 변경 요약 + 최종 PASS 확인. 건너뛸 때는 `skipped: {reason}` 기록.
- `tdd-red-revisions.md`: 실제 사용자 승인 후 `revision 1: {reason}` 형태로 누적하는 최대 2회의 Red 재작성 카운터다. 외부 부모/controller 승인 기록과 함께 대조하며, 이 파일 단독으로는 승인 증거가 아니다.

hotfix 트랙의 실행 로그만 별도 파일명을 사용한다: `hotfix-red-log.txt`, `hotfix-green-log.txt` (Refactor 없음). 두 TDD JSON 파일은 hotfix에서도 같은 이름으로 반드시 생성한다.

---

## 부모 실행 관측과 TDD JSON (schema 1.2)

`hb-eval-review`는 플러그인에 vendored된 실행 파일이므로 `<플러그인 설치 경로>/bin/hb-eval-review`로 호출한다. `--repo`를 생략하면 현재 작업 디렉터리를 쓴다. `--out`은 `.harness/artifacts/{track}/{identifier}/`이고 `--issue-type`은 실제 작업 유형이다. 어댑터는 테스트 명령에서 추론하며 별도 `--stack` 인자는 없다.

Red의 `--design`은 아래처럼 **의미 검수만 담은 입력 파일**(`tdd-design-metadata.json`)이다. 기존 schema 1.1 형식을 입력으로 사용할 수 있으며, 이 파일은 실행 증거가 아니다. `<...>`는 실제 검수 내용으로 바꾼다.

```json
{
  "schema_version": "1.1", "baseline": "RED_TO_GREEN",
  "stage": "tdd-test-design", "tier": "T1", "status": "PASS",
  "test_id": "<실제 test ID>", "acceptance_refs": ["<실제 AC ID>"],
  "red_failure_kind": "missing_behavior",
  "assertions": [{"kind": "observable_behavior", "description": "<관찰 가능한 assertion>"}],
  "mocked_boundaries": [], "system_under_test_mocked": false,
  "paths": ["success", "failure", "boundary"],
  "reviewer": {"independent": false, "read_only": true}
}
```

Green의 `--design`은 입력 metadata가 아니라 **Red가 생성한 고정 `tdd-test-design-result.json`**이다. `--sensitivity`에는 관련 회귀·위험도·mutation을 검수한 의미 metadata 파일(`tdd-sensitivity-metadata.json`)을 전달한다.

```json
{
  "tier": "T1", "test_id": "<Design과 같은 실제 test ID>",
  "high_risk": false,
  "mutation": {"required": false, "performed": false, "outcome": "NOT_REQUIRED"},
  "regression": {"status": "PASS"}
}
```

`--sensitivity`를 생략하면 `--out/tdd-sensitivity-result.json`의 기존 의미 metadata를 읽는다. 첫 실행에서는 위 입력을 명시한다. `PASS`·`NOT_REQUIRED`는 실제 검수가 뒷받침할 때만 사용한다. 이 입력으로 실행 수·결과·hash·승인을 자기보고할 수 없으며, 부모가 해당 값과 최종 status를 계산한다. 입력 metadata의 `status: BLOCKED`, 알 수 없는 schema 버전, 해당 단계와 다른 `stage`는 테스트 실행 전에 거부한다.

- 부모가 생성하는 두 정본 파일은 `"schema_version": "1.2"`이며 명시적인 `baseline`을 가진다. `observed`의 `argv`, `cwd`, `exit_code`, `selected_tests`, `executed`, `recorded_at`, `test_file_sha256`은 직접 실행과 리포트에서 계산한다. 같은 관측에 `run_id`, `git_dir`, `artifacts`, `test_file`, `source_snapshot_id`, `sut_sha256`를 결속하고, Green에는 고정 Red JSON의 정확한 bytes hash인 `baseline_sha256`도 기록한다. 모델이 이 필드를 만들거나 덮어쓰지 않는다.
- 리포트 경로는 부모가 만든 임시 디렉터리로 고정한다. pytest의 `--junitxml`, Jest의 `--json --outputFile`, Gradle XML, xcodebuild의 `-resultBundlePath`와 `xcrun xcresulttool`을 통해 실제 테스트 ID·실행 수·결과를 읽는다. 사용자 지정 리포트 출력 경로는 거부한다. 오래된 리포트·stdout marker·exit code만으로는 실행을 증명하지 못한다.
- Jest는 부모가 소유한 `--testLocationInResults`를 추가하되 repository의 `testEnvironment`·`testRunner`를 덮어쓰지 않는다. 구체적인 matcher/assertion 실패와 완전한 source stack frame이 있고 `_callCircusHook`이 식별되지 않으면 async 본문·deep helper의 Red를 인정한다. 명시적인 `_callCircusTest` 본문 frame도 인정하며, 식별된 hook frame은 거부한다. 테스트 선언 위치는 callback 범위를 뜻하지 않으므로 실패 줄이 선언 줄보다 앞에 있다는 이유로 helper 실패를 거부하지 않는다. **승인된 한계:** hook frame을 잃은 async hook은 본문과 구분되지 않아 통과할 수 있다. 모든 source/phase frame이 없거나 잘린 경우, 명시적인 `noStackTrace`, 식별 가능한 jasmine runner 설정·frame은 `TDD_JEST_PHASE_UNSUPPORTED`로 차단한다. 실제 Jest 27.5.1·29.7.0 및 ts-jest 보고서로 확인한 범위이며 모든 Jest 설정의 호환을 보장하지 않는다.
- `RED_TO_GREEN`은 exit ≠ 0, 선택된 테스트 ≥ 1개 실행, assertion 실패를 함께 요구한다. 리포트·출력에서 식별된 collection·compile·syntax·import·fixture 오류는 stdout/stderr 어디에 있어도 `TDD_RED_REASON_INVALID`다. Green은 exit 0이며 Red에서 선택된 모든 테스트 ID가 실제 실행·PASS해야 한다. 파일 경로가 argv에 들어 있는지, 접두가 특정 문자열인지, Red/Green argv가 글자까지 같은지로 판정하지 않는다.
- maintenance의 refactor만 `--issue-type refactor`를 쓰고 두 산출물의 `baseline`은 `PASS_TO_PASS`가 된다. Design 입력도 `PASS_TO_PASS`로 작성하고 `red_failure_kind`는 생략한다. 전후 실제 PASS와 동일 테스트·hash·회귀·필요한 mutation 검수는 그대로 필요하다. 나머지 유형은 `RED_TO_GREEN`이다.
- 로컬 상태가 온전할 때 각 성공한 Red는 이전 관측을 덮어쓰지 않는 새 run으로 고정된다. Green은 같은 repository·gitdir·artifact run·test-file의 baseline에 결속돼야 한다. 보존된 로컬 상태와 맞지 않는 다른 run·저장소의 Design이나 관측 JSON 교체는 `BLOCKED`다.
- 로컬 상태가 온전할 때 제자리 baseline 덮어쓰기·교체와 형식이 맞는 외부 기록 없는 test hash 변경을 차단한다. **상태 디렉터리 삭제**로 `eval-review/tdd-check/`와 `tdd-test-design-result.json`을 함께 삭제하면 baseline이 초기화된다. 이 삭제를 감지하는 외부 원장은 없으며, 승인 없는 초기화는 절차로만 금지한다. schema 1.2의 digest는 로컬에서 재계산할 수 있다. 암호학적 변조 방지나 사용자 신원·승인 출처의 진위를 보장하지 않는다.
- `source_snapshot_id`는 각 실행의 출력 생성 전 source 관측이다. Red와 Green 사이에는 구현이 바뀌므로 두 값의 동일성을 요구하지 않으며, 이후 로그·산출물이 반영된 Gate snapshot과도 무조건 같아야 하는 값이 아니다. 각 명령을 실행하는 동안에는 source·테스트 hash·고정 baseline/state bytes가 유지돼야 한다.
- `sut_sha256`는 기존에 검증한 source manifest의 `files` 항목에서 **현재 artifact 디렉터리의 정확한 prefix만 제외한** path·kind·mode·hash 목록으로 계산한다. packet의 기존 source snapshot·열거기·제외 규칙은 변경하지 않는다. Red→Green의 SUT 변경은 허용하지만, Gate에서는 **Green의 `sut_sha256`와 현재 source view**가 일치해야 한다. Green 이후 구현이 바뀌면 오래된 증거로 Gate를 통과할 수 없고 `tdd-check green`을 다시 실행한다. run은 source 복사 후 재검증을 마친 manifest로 같은 검사를 하며 live source를 추가로 다시 읽지 않는다.
- Gate·pack·run은 진행 중인 작업에도 즉시 schema 1.2 관측 쌍을 요구한다. 1.0·1.1 또는 그 버전으로 하향한 증거는 `TDD_OBSERVATION_REQUIRED`로 차단하고 provider를 실행하지 않는다. 기존 작업도 `tdd-check red`·`green`을 재실행해야 한다. 1.0·1.1의 의미 호환은 validator 층에만 남긴다. 기존 1.0은 `RED_TO_GREEN`, 1.1은 명시적 baseline으로 의미만 해석하고 원본을 덮어쓰지 않는다. Red의 1.1 의미 metadata 입력과 소비자가 받는 1.2 실행 증거는 서로 다른 계약이다. `qa-snapshot.json`의 1.0과 provider envelope의 2.0은 변경하지 않는다.
- `tdd-check`는 셸·인터프리터 inline-code 명령(`bash -c`, `python -c`, `node -e`·`node -p` 등)을 실행 전에 `TDD_COMMAND_INVALID`로 거부한다. 해석하지 못한 옵션의 값은 script 경계로 믿지 않고 뒤의 inline-code 옵션까지 보수적으로 검사하며, 명령 문자열을 다시 실행하는 `env -S`·`npx --call`·`npm exec --call`도 거부한다. 명확한 repository script 경계와 `python -m pytest -c pytest.ini`는 유지한다. 그러나 저장소가 통제하는 conftest·npm script·reporter가 결과 리포트를 위조하는 것은 막지 못한다. 관측은 신뢰한 테스트 도구가 남긴 리포트에 근거하며, 의도적 보고서 위조를 방지하는 경계가 아니다.
- 실행 관측은 테스트의 의미 품질을 대신하지 않는다. AC 연결·행동 assertion·SUT mock 금지·T2 독립 read-only 검수와 필요한 mutation은 기존 검수 규칙을 따른다.

---

## 검사 로그 재사용 정책

자동검사(테스트·lint·build·stack QA)를 다시 돌리지 않고 이전 실행의 로그로 대신하는 것을 **재사용**이라 한다. 트랙 문서의 QA·회귀·코드리뷰 관문이 "재사용"을 말할 때는 항상 이 절을 따른다. 기록·비교의 주체는 검사를 실제로 돌리는 부모 스텝(Gate·회귀 스텝)이며, blind provider(Evaluate [E2]·Review [R1])는 아무것도 쓰지 않는다.

1. **기본 재사용 금지.** 아래 조건을 전부 증명하지 못하면 검사를 다시 실행한다. 커밋 HEAD가 같다는 것은 근거가 아니다 — HEAD는 커밋하지 않은 변경과 untracked 파일을 모른다. lockfile은 추적 파일이라 snapshot에 포함되지만 설치 상태·환경변수는 포함되지 않으므로, 판정할 수 없으면 재실행한다.
2. **후보는 저장소가 표시한 결정적 검사뿐.** 저장소의 `.harness/docs/check-reuse.yaml`에 `reuse: allowed`로 표시된 검사만 후보다. 파일이 없거나 `checks`가 비어 있으면 후보가 없다(기본 상태). 외부 데이터·현재 시각·공유 DB·네트워크·기기 상태에 의존하는 검사는 `allowed`로 표시하지 않는다.

   ```yaml
   # .harness/docs/check-reuse.yaml — 없으면 재사용 후보 없음
   checks:
     - name: unit
       argv: ["<검사 실행 파일>", "<인자>"]   # 실제 실행과 같은 argv 전체
       cwd: "."                             # 작업 트리 기준
       reuse: allowed                       # never(기본) | allowed
   ```

3. **재사용 키.** 다음 다섯 값이 모두 같을 때만 같은 검사로 본다.
   - `source_snapshot_id`: `<플러그인 설치 경로>/bin/hb-eval-review snapshot <작업 트리>`의 출력. 플러그인에 vendored된 실행 파일이며 PATH에 없다. HEAD·index·tracked/untracked 파일 내용을 함께 묶는다.
   - argv(검사 실행 argv 전체), cwd(작업 트리 기준 상대 경로), selection(선택 범위: 테스트 파일·클래스·패턴, 전체 실행이면 빈 값), toolchain(검사 실행 파일의 버전 명령 stdout 첫 줄, 예: `xcodebuild -version` → `Xcode 26.5`).
4. **기록 위치.** 키·로그 경로·결과는 아티팩트 디렉토리의 `eval-review/qa-snapshot.json`에만 기록한다. `.harness/artifacts/**/eval-review/**`는 snapshot 계산에서 제외되므로 이 기록이 자기 snapshot을 바꾸지 않는다. `INDEX.md`나 아티팩트 디렉토리 직하의 다른 파일에 적으면 snapshot이 바뀌어 다음 비교가 항상 어긋난다(`.harness/artifacts/`를 통째로 ignore한 저장소에서는 `INDEX.md`도 snapshot 밖이지만 규칙은 같게 적용한다). `INDEX.md`에는 완료 절에서 1회만 옮겨 적는다. `eval-review/`는 `hb-eval-review run`의 output root가 아니다 — run의 output root는 비어 있어야 하므로 run마다 `eval-review/run-<n>/` 같은 새 하위 디렉토리를 쓴다.

   ```json
   {
     "schema_version": "1.0",
     "recorded_by": "F7 Gate",
     "check": "unit",
     "reuse_key": {"source_snapshot_id": "<64 hex>", "argv": ["..."], "cwd": ".", "selection": "", "toolchain": "..."},
     "log": "tdd-green-log.txt",
     "outcome": "PASS"
   }
   ```

5. **순서와 작업 트리.** 기록하는 스텝은 자기 산출물(로그·리뷰 코멘트)을 모두 쓴 뒤 마지막에 snapshot을 계산해 기록한다. 재사용하려는 스텝은 그 검사를 실행·재사용하기 직전 — 그 스텝의 코드 수정(리뷰 반영 등)이 모두 끝난 뒤, 검사 산출물을 쓰기 전 — 에 snapshot을 계산해 비교한다. 이 순서를 어기면 재사용은 영구히 0회다. 계산·기록·비교는 검사를 실제로 돌리는 작업 트리(worktree)에서 한다. 기록한 트리와 비교하는 트리가 다르면(예: 메인 트리에서 기록, fork worktree에서 비교) 재사용하지 않고 재실행한다 — 정상 동작이다. 보통은 아티팩트 유무만으로도 ID가 달라지며, `.harness/artifacts/`를 ignore해 그렇지 않은 저장소에서도 규칙은 같다.
6. **판정 기록.** 재사용 여부와 근거(다섯 값의 비교 결과)는 재사용하려던 스텝이 같은 `qa-snapshot.json`에 `reuse_decision`으로 남긴다. 재사용하지 않았으면 검사를 다시 돌리고 새 키를 기록한다.

---

## 금지 사항

- 테스트 없이 구현 먼저 작성하는 것 (test-after)
- FAIL 확인 없이 Green 단계로 넘어가는 것 (bug/feature 유형)
- Red 단계에서 여러 수용기준에 대한 테스트를 동시에 작성하는 것
- Refactor 단계에서 새 기능 추가
- 실패 로그 캡처를 생략하고 "PASS 확인함"이라고만 기록
- Green 단계에서 Red 테스트를 몰래 수정하여 PASS 만들기 (test-after 회귀)
- Test Design Check 없이 Green 구현 또는 maintenance refactor 변경을 시작하는 것
- System Under Test를 mock으로 대체하고 실제 행동을 검증했다고 주장하는 것
- 필수 sensitivity/mutation 증거를 사유 없이 생략하고 PASS로 처리하는 것
- hotfix 트랙에서 Refactor 수행 (에스컬레이션 → `:auto` 또는 `:deep`으로 전환)
- `pytest` 대신 `python manage.py test`를 사용하는 것 (BE 스택은 pytest로 통일되어 있다)
- 재사용 키(`source_snapshot_id`·argv·cwd·선택 범위·toolchain)가 같다는 증거 없이 이전 검사 로그를 재사용하는 것 ("검사 로그 재사용 정책" 참조)

---

## Django/DRF Mocking 카탈로그

feature/maintenance의 Red 단계에서 아래 패턴이 자주 필요하다. **이 패턴들이 없어서 발생하는 실패는 "올바르지 않은 Red"로 오인하기 쉽지만, 사실은 환경 설정 누락**이다. `tdd-red-debug.md`에 "환경 설정" 카테고리로 기록하고 사용자에게 fixture/settings 누락을 명시적으로 보고한다.

| 영역 | 해결책 |
|------|------|
| DB 접근 | `@pytest.mark.django_db` 데코레이터, 또는 `django_db` fixture |
| Celery task | `settings.CELERY_TASK_ALWAYS_EAGER=True` (test settings) 또는 `task.apply()` 명시 호출 |
| Celery broker | `settings.CELERY_BROKER_URL='memory://'` (test settings) |
| Azure Blob Storage | `unittest.mock.patch('azure.storage.blob.BlobClient')` 또는 stub client |
| Fernet 암호화 | 테스트 전용 고정 `FERNET_KEY`를 test settings에 주입 |
| JWT (SimpleJWT) | `rest_framework.test.APIClient` + `.credentials(HTTP_AUTHORIZATION='Bearer ...')` 또는 `force_authenticate()` |
| Django Signals | `factory_boy` + `mute_signals` 데코레이터, 또는 `post_save.disconnect()` |
| DRF ViewSet permissions | `APIClient.force_authenticate(user=...)` |
| QuerySet lazy evaluation | 명시적 `list()` 강제 평가로 타이밍 통제 |
| External HTTP (Innopay 등) | `responses` 라이브러리 또는 `unittest.mock.patch('requests.post')` |

이 패턴들이 모두 **일반적인 fixture 패턴**임을 인식하고, "Red 실패 이유"를 판단할 때 "fixture 오류"를 구현 부재로 오분류하지 말 것. 워커는 먼저 "target repo에 해당 fixture가 존재하는가?"를 확인한다.
