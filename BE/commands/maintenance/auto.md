# 유지보수 파이프라인

이미 돌아가는 코드의 문제를 고치거나 개선한다. 회귀를 만들지 않는 것이 최우선.

## 사전 조건

- 사용자가 이슈(버그, 리팩토링, 성능, 의존성)를 제시해야 한다.
- 에러 로그, 재현 절차, 스크린샷 등이 있으면 제공한다.

## 식별자

이슈 ID가 있으면 그대로 사용. 없으면 `maint-YYYYMMDD-slug` 형식.
예: `BUCCL-42` 또는 `maint-20260406-conn-reset`

## 핵심 원칙

- 회귀 방지가 최우선
- 수정 범위 폭주 방지 → fix-plan.md에서 범위 명시
- 신규 ADR 생성 금지 → 새 결정이 필요하면 planning 트랙으로 에스컬레이션

## 파이프라인

### [M1] 상태 점검 (메인)

1. 사용자가 제시한 이슈를 정리한다.
2. 이슈 유형을 분류한다:
   - `bug` — 서버 에러, 예외, 잘못된 동작
   - `refactor` — 코드 구조 개선, 기술 부채 해소
   - `performance` — 느린 응답, 타임아웃, 메모리
   - `dependency` — 패키지 업그레이드, 보안 패치
3. `docs/module-registry.yaml`을 읽고, 관련 모듈을 식별한다.
4. 사용자에게 다음을 확인한다:
   - 이슈 유형
   - 관련 모듈
   - 긴급도 (hotfix 여부)
   - 재현 가능 여부
5. `.harness-artifacts/maintenance/{identifier}/` 디렉토리를 생성한다.

### [M2] 이슈 재현 (Fork)

1. **worktree(fork)를 생성**하여 이슈를 재현한다.
2. 재현 테스트 케이스를 작성한다:
   - 테스트 파일: `tests/test_{module}_maint_{identifier}.py`
   - factory_boy로 테스트 데이터 생성
   - 현재 상태에서 테스트가 **FAIL** 하는 것을 확인한다. (bug인 경우)
   - refactor인 경우, 기존 동작을 캡처하는 characterization test를 작성한다.
3. 재현 불가 시 사용자에게 보고하고 추가 정보를 요청한다.
4. `reproduction.md`를 저장한다.
5. worktree를 정리한다.

### [M3] 근본 원인 추적 — RCA (Sub-agent)

1. **sub-agent를 호출**하여 근본 원인을 분석한다.
2. sub-agent에게 전달:
   - `reproduction.md`
   - 관련 모듈 코드 (models.py, views.py, serializers.py, signals.py)
   - `docs/adr.yaml`
   - `docs/architecture.yaml`
3. sub-agent는 tracer 스타일로 분석:
   - traceback에서 발생 지점 특정
   - request flow를 따라 문제 지점 추적
   - 근본 원인(root cause) 추정 (가능성 순 나열)
   - 관련 ADR 결정과의 관계 확인
4. `root-cause.md`를 저장한다.
5. 분석 결과를 사용자에게 제시하고 원인 추정에 대한 동의를 구한다.

### [M4] 영향도 조사 — 병렬 탐색 (Agent Team) ★

1. **Agent Team을 호출**하여 3개 방향에서 동시에 영향 범위를 탐색한다.

#### Agent A: 모듈/레이어 방향
```
다음 근본 원인을 기준으로, 수직 방향(Model → Serializer → View → URL)으로
영향받는 코드를 추적하라.

분석:
1. 이 원인이 다른 모델의 FK/관계에 영향을 미치는가?
2. 이 원인과 같은 Serializer를 사용하는 다른 View가 있는가?
3. 이 원인이 다른 앱(module-registry의 다른 모듈)에 전파되는가?

[root-cause.md]
[관련 모듈 코드]
[module-registry.yaml]
```

#### Agent B: 호출자 방향
```
다음 근본 원인의 코드를 호출하는 모든 경로를 역추적하라.

분석:
1. 이 함수/메서드를 호출하는 곳은 어디인가? (grep/import 추적)
2. Signal로 연결된 트리거가 있는가?
3. Celery task에서 호출되는 경우가 있는가?
4. 테스트에서 이 코드를 커버하는 케이스는 몇 개인가?

[root-cause.md]
[관련 모듈 코드]
```

#### Agent C: 데이터 흐름 방향
```
다음 근본 원인이 데이터 무결성에 미치는 영향을 분석하라.

분석:
1. 이 원인이 DB 데이터의 일관성에 영향을 미치는가?
2. 이미 잘못된 데이터가 쌓여 있을 가능성은?
3. 외부 서비스(Innopay, Azure Blob)에 잘못된 데이터가 전달되었을 가능성은?
4. 마이그레이션으로 데이터 보정이 필요한가?

[root-cause.md]
[관련 모듈 코드]
[architecture.yaml]
```

2. **메인이 3개 결과를 병합**:
   - 영향받는 코드/데이터 전체 목록 통합
   - 중복 제거 및 우선순위 부여
   - 수정 시 연쇄 영향 정리
3. `impact-analysis.md`를 저장한다.

### [M5] 기존 ADR/convention 충돌 체크 (Sub-agent)

1. **sub-agent를 호출**하여 수정 방향이 기존 결정과 충돌하지 않는지 확인한다.
2. sub-agent에게 전달:
   - `root-cause.md`
   - `impact-analysis.md`
   - `docs/adr.yaml` 전문
   - `docs/code-convention.yaml` 전문
3. sub-agent는 다음을 확인:
   - 수정 방향이 기존 ADR 결정을 위반하는가?
   - 수정 방향이 convention 규칙을 위반하는가?
   - 새로운 설계 결정이 필요한가? → **필요하면 planning 에스컬레이션 플래그 설정**
4. `convention-check.md`를 저장한다.
5. 에스컬레이션 필요 시 사용자에게 명시적으로 알린다.

### [M6] 수정 계획 + 회귀 리스크 (Fork)

1. **worktree(fork)를 생성**하여 수정 계획을 작성한다.
2. 계획에 포함:
   - 수정 대상 파일 목록
   - 각 수정의 내용과 이유
   - 회귀 리스크 (이 수정이 깨뜨릴 수 있는 기존 기능)
   - 범위 제한 (이번에 하지 않는 것)
   - 마이그레이션 필요 여부
3. 초안과 논의점을 사용자에게 제시한다.
4. `fix-plan.md`를 저장한다.
5. worktree를 정리한다.

### [M7] 수정 실행 (Fork)

1. **worktree(fork)를 생성**하여 수정한다.
2. 수정 원칙:
   - **최소 범위**: fix-plan.md에 명시된 범위만 수정
   - **convention 준수**: code-convention.yaml 규칙 따름
   - **마이그레이션 분리**: 필요 시 별도 커밋
3. 수정 내용과 side effect를 사용자에게 보고한다.

### [M8] 회귀 테스트 리포트 — 병렬 실행 (Agent Team) ★

1. **Agent Team을 호출**하여 3개 테스트 스위트를 동시에 실행한다.

#### Agent A: 단위 테스트
```
수정된 모듈의 단위 테스트를 실행하라.
python manage.py test {app} --verbosity=2

결과를 다음 형식으로 보고하라:
- 통과: {N}개
- 실패: {N}개
- 실패 목록: [{test_name}: {에러 요약}]
- M2에서 작성한 재현 테스트: PASS | FAIL
```

#### Agent B: 통합/E2E
```
전체 테스트 스위트를 실행하라.
python manage.py test --verbosity=2

결과를 다음 형식으로 보고하라:
- 통과: {N}개
- 실패: {N}개
- 실패 목록: [{test_name}: {에러 요약}]
- 수정 전 대비 새로 실패한 테스트: [...]
```

#### Agent C: 린트/빌드
```
다음 검증을 수행하라:
1. python manage.py check
2. python manage.py makemigrations --check --dry-run
3. 수정된 파일에 대해 code-convention.yaml 위반 확인

결과를 다음 형식으로 보고하라:
- system check: PASS | FAIL
- migration check: PASS | FAIL (누락 마이그레이션 있으면 목록)
- convention 위반: [{파일}: {위반 내용}]
```

2. **메인이 3개 결과를 병합**:
   - 전체 통과/실패 요약
   - 새로 발생한 실패 (회귀) 식별
   - 회귀가 있으면 M7로 돌아가 수정 루프
3. `regression-report.md`를 저장한다.
4. 회귀 없으면 다음 단계로 진행.

### [M9] 리뷰 + 반영 (Sub-agent + Fork)

1. **sub-agent를 호출**하여 코드리뷰를 수행한다:
   - `fix-plan.md` (의도)
   - `convention-check.md` (기준)
   - `git diff` (변경 내용)
   - 리뷰 원칙: convention 근거 기반, 취향 리뷰 금지
2. `review-comments.md`를 저장한다.
3. **worktree(fork)에서** 리뷰를 반영한다:
   - 각 코멘트의 수용/거부 판단을 사용자에게 제시
   - 사용자 확인 후 수정
   - 수정 후 M8 회귀 테스트 재실행 (경량)
4. 최종 결과를 사용자에게 보고한다.

### 완료

파이프라인이 완료되면 `INDEX.md`를 생성하여 다음을 기록한다:
- 산출물 목록
- 수정된 파일 목록
- 회귀 테스트 결과 요약
- 커밋 메시지 제안
- planning 에스컬레이션 여부

## 산출물

```
.harness-artifacts/maintenance/{identifier}/
  reproduction.md
  root-cause.md
  impact-analysis.md         ← Team 병합본
  convention-check.md
  fix-plan.md
  regression-report.md       ← Team 병합본
  review-comments.md
  INDEX.md
```
