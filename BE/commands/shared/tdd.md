# TDD (Red-Green-Refactor) 프로토콜

모든 feature/maintenance 커맨드가 참조하는 공통 테스트 우선 개발 프로토콜.
사이클은 **Red → Green → Refactor** 순서로 엄격하게 수행한다.
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

아티팩트 디렉토리(`.harness/artifacts/{track}/{identifier}/`)에서 이전 run의 잔존 파일을 삭제한다. 이들이 남아있으면 "line count as counter" 규칙이 stale 값을 상속한다:

```bash
rm -f {artifacts-dir}/tdd-red-debug.md
rm -f {artifacts-dir}/tdd-red-revisions.md
```

`tdd-baseline-log.txt`, `tdd-green-log.txt`, `tdd-refactor-notes.md`는 덮어쓰기 대상이므로 삭제 불필요 (cycle이 재작성). 단, 동일 identifier로 재실행하는 경우 기존 아티팩트 디렉토리가 의도된 것인지 사용자 확인을 받는다.

---

## 사이클 정의

### Red: 실패하는 테스트 작성 (또는 Green baseline 고정)

1. 테스트가 실행되면 FAIL해야 함 (구현이 없거나 기존 동작이 버그이므로)
   - 단, **refactor 이슈 유형**은 예외: 현재 동작을 캡처하는 characterization test를 작성하여 **Green baseline**으로 고정한다. 이 경우 테스트는 PASS 상태로 시작한다.
2. 테스트 범위: 하나의 수용기준(AC) 또는 하나의 버그 재현
3. Baseline 로그를 아티팩트 디렉토리의 `tdd-baseline-log.txt`에 캡처:
   - 실패한 테스트 이름 (bug/feature 유형)
   - expected vs actual
   - 출력 tail 30줄

   ```bash
   pytest {app}/tests/test_{module}_*.py -v 2>&1 | tail -30 > tdd-baseline-log.txt
   ```

4. **실패 이유 검증 (bug/feature 유형)**:
   - 구현 부재 / assertion fail → **올바른 Red** → Green 단계로 진행
   - syntax / import / fixture 오류 → **올바르지 않은 Red**
     - (a) 테스트 코드를 수정하고 재실행 (최대 3회)
     - (b) 3회 후에도 올바르지 않은 Red면: 원인을 `tdd-red-debug.md`에 기록하고 사용자에게 보고 (스택/fixture 혼란 가능성)
     - (c) 각 재시도의 최종 출력만 `tdd-baseline-log.txt`에 덮어쓰기
     - (d) **재시도 카운터 persistence**: 재시도 횟수는 `tdd-red-debug.md`의 attempt 라인 수(`attempt N: {reason}`)로 결정한다. 파일이 없으면 0부터 시작. 워크플로우 재개 시에도 카운터가 유지된다.

### Green: 최소 구현으로 통과

1. Red 테스트가 PASS가 되도록 **최소한의 코드만** 작성
2. 범위 폭주 금지: Red 테스트가 요구하지 않는 코드 추가 금지
3. 다른 기존 테스트가 깨지면 즉시 수정 (새로운 회귀 만들지 말 것)
4. PASS 로그를 `tdd-green-log.txt`에 캡처:

   ```bash
   pytest {app}/tests/test_{module}_*.py -v 2>&1 | tail -30 > tdd-green-log.txt
   ```

5. 추가 검증 (Django 레이어 오류 조기 포착):

   ```bash
   python manage.py check
   ```

#### Green 단계에서 Red이 틀렸음을 발견한 경우

Green 구현 중 수용기준(AC) 자체가 잘못 서술되었거나 Red 테스트가 잘못된 대상을 검증한다는 증거가 나오면:

1. 구현을 **즉시 중단**한다. 테스트를 억지로 수정해 PASS시키지 않는다.
2. 사용자에게 Red 재작성 필요성을 제기한다 (이유 + 제안 수정).
3. 승인 시 Red 단계로 복귀한다. `tdd-baseline-log.txt`를 덮어쓰고 `tdd-red-revisions.md`에 `revision {N}: {reason}` 기록.
4. **승인 없이 테스트를 수정하여 Green을 만드는 것은 금지** (test-after 회귀로 간주).
5. **재작성 캡 — 최대 2회 복귀**: `tdd-red-revisions.md`의 라인 수가 revision 카운터 역할을 한다 (파일이 없으면 0, 한 번 복귀할 때마다 라인 +1). **3번째 복귀 요청(revision 3)**이 발생하면 즉시 중단하고 deep 트랙 에스컬레이션 또는 사용자 개입을 요청한다 — 이는 근본 원인이 테스트가 아니라 설계의도(requirements.md)에 있다는 신호다.
6. **Counter reset 규칙 (중요 — 두 카운터 상호작용 방지)**: Green→Red 복귀 시 반드시 `tdd-red-debug.md`를 **truncate**(rm -f)한다. 그렇지 않으면 이전 Red phase의 attempt 라인 수가 새 Red phase에 carry over되어 false escalation이 발생한다. 아래 3단계를 순서대로 수행:
   - (a) `tdd-red-revisions.md`에 `revision {N}: {reason}` 라인 append (revision 카운터 +1)
   - (b) `rm -f {artifacts-dir}/tdd-red-debug.md` (retry 카운터 reset to 0)
   - (c) `tdd-baseline-log.txt`를 덮어쓰기할 준비 상태로 Red 단계 진입
   `tdd-red-revisions.md`는 revision 카운터이므로 절대 reset하지 않는다 (revision 3 cap 유지).

### Refactor: 테스트 녹색 유지하며 정리

1. Green 상태에서만 시작 (모든 테스트 PASS 확인 후)
2. 중복 제거, 네이밍 개선, 구조 정리
3. **새 기능 금지**, **테스트 변경 금지**
4. 각 리팩토링 후 전체 테스트 재실행. 깨지면 즉시 revert.

   ```bash
   pytest {app}/tests/test_{module}_*.py -v
   ```

5. 변경 내용을 `tdd-refactor-notes.md`에 요약

---

## 이슈 유형별 적용

| 유형 | Baseline 의미 (Red 단계) | Green | Refactor |
|------|------------------------|-------|----------|
| feature (신규 기능) | 수용기준에서 도출한 **FAIL** 테스트 | 최소 구현으로 PASS | 필수 |
| bug (maintenance) | 버그 재현 **FAIL** 테스트 | 버그 수정으로 PASS | 선택 (fix-plan 범위 내) |
| refactor (maintenance) | **PASS**하는 characterization test를 Green baseline으로 고정 | N/A (baseline 유지) | **주 단계** |
| performance (maintenance) | 성능 임계치 테스트 또는 기준선 | 임계 통과 구현 | 선택 |
| hotfix | **FAIL** 재현 테스트 (`hotfix-red-log.txt` 사용) | 최소 수정으로 PASS | **금지** (범위 폭주 위험) |

> **`tdd-baseline-log.txt`의 의미는 이슈 유형에 따라 다르다**: bug/feature/performance는 FAIL 증거, refactor는 PASS baseline. 이는 "Refactor 단계에서 이 로그와 비교해 동작이 보존되었는가"를 판단하는 고정점이다.

> **refactor 이슈 유형 특이사항**: characterization test를 작성하여 현재 동작을 Green baseline으로 고정한다. M5 또는 M7의 "수정 실행" 단계는 실질적으로 생략되고, M5.5/M7.5 Refactor가 주 단계가 된다. baseline 테스트는 리팩토링 전후 모두 PASS여야 한다.

---

## 아티팩트 규약

Red/Green/Refactor가 적용되는 단계에서 다음 파일을 **반드시** 생성:

```
.harness/artifacts/{track}/{identifier}/
  tdd-baseline-log.txt     ← Red 단계 baseline (FAIL or PASS per issue type)
  tdd-green-log.txt        ← Green 단계 PASS 증거
  tdd-refactor-notes.md    ← Refactor 내용 요약 (skip 시 "skipped: {reason}")
  tdd-red-revisions.md     ← (선택) Red 재작성 이력. 없으면 생성 안 함.
```

- `tdd-baseline-log.txt`: bug/feature는 FAIL 출력, refactor는 PASS characterization 출력 (tail 30줄 + expected/actual)
- `tdd-green-log.txt`: 구현 후 PASS 출력 (테스트 통과 증거)
- `tdd-refactor-notes.md`: 리팩토링 변경 요약 + 최종 PASS 확인. 건너뛸 때는 `skipped: {reason}` 기록.
- `tdd-red-revisions.md`: Green 단계에서 Red 재작성이 필요했을 때만 생성. `revision 1: {reason}` 형태로 누적.

hotfix 트랙은 별도 파일명을 사용: `hotfix-red-log.txt`, `hotfix-green-log.txt` (Refactor 없음).

---

## 금지 사항

- 테스트 없이 구현 먼저 작성하는 것 (test-after)
- FAIL 확인 없이 Green 단계로 넘어가는 것 (bug/feature 유형)
- Red 단계에서 여러 수용기준에 대한 테스트를 동시에 작성하는 것
- Refactor 단계에서 새 기능 추가
- 실패 로그 캡처를 생략하고 "PASS 확인함"이라고만 기록
- Green 단계에서 Red 테스트를 몰래 수정하여 PASS 만들기 (test-after 회귀)
- hotfix 트랙에서 Refactor 수행 (에스컬레이션 → `:auto` 또는 `:deep`으로 전환)
- `pytest` 대신 `python manage.py test`를 사용하는 것 (BE 스택은 pytest로 통일되어 있다)

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
