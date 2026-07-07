# 검증

build로 만든 변경 코드가 "정말 통과인지" 증거 기반으로 검사한다. 자동검사(린터·테스트·빌드) → 통과 시 반박 검증까지 돌리고, 메인 컨텍스트에는 **통과/실패와 산출물 경로만** 회수한다.

## 실행 방식

이 skill은 Fork에서 실행된다. 무거운 검사·반박은 Sub-agent에게 내려 결론만 회수한다.

- **완료기준·증거·리뷰 렌즈는 각 플러그인(스택)을 따른다.** 여기서 명령으로 하드코딩하지 않는다.
  - 예: BE/CM = 테스트·lint·build 통과 (스택별 명령은 해당 플러그인의 `shared/verify`가 정의).
  - 예: FE = 시각·UX·반응형·접근성 + Claude 디자인 검증.
  - 예: CHAT = 테스트·lint·build·tsc + 계약 검증(websocket-events·api-contract 등록 여부) + dual review gate.
  - `pytest`·`npm test` 같은 특정 명령을 정답으로 박지 않는다 — 스택이 알려준 명령을 그대로 쓴다.
- **도구 선택**: 검사가 여러 갈래로 쪼개질 때만 Sub-agent로 내린다. 한두 줄짜리면 메인에서 혼자.
  - **울트라코드(워크플로우) ON**: 자동검사 → 관점별 반박 검증을 병렬로 정밀하게 돌린다(가짜 경보 제거 포함).
  - **울트라코드 OFF**: 메인이 혼자 자동검사만 순서대로 도는 가벼운 버전으로 자동 전환. 어느 쪽이든 **항상 작동**.
  - 큰 변경이 여러 개라 오래 걸릴 때만 Claude Code 네이티브 Teams를 쓴다 (드묾).

## 식별자

feature 트랙은 `git branch --show-current`, maintenance 트랙은 트랙 파이프라인의 issue-id, planning은 슬러그로 resolve한다 — **seed가 쓴 식별자와 동일**해야 한다. `{track}`은 호출 맥락(feature/maintenance/planning)을 따른다.
검사 대상 산출물은 `.harness/artifacts/{track}/{identifier}/`에 모인다.

## 절차

### [E1] 검사 대상·기준 수집 (메인)

1. `git diff main...HEAD --stat`으로 변경 파일 목록을 확인한다.
2. `.harness/artifacts/{track}/{identifier}/`에서 기준 문서를 연결한다 — **우선순위 순**:
   - `seed.md` (주문서 완료기준 표 — **있으면 1순위 기준**)
   - `code-quality-guide.md` (완료기준·적용 ADR)
   - `design-intent.md` (의도)
   - 없으면 `.harness/docs/code-convention.yaml`·`.harness/docs/adr.yaml`에서 이 작업과 관련된 항목을 추린다.
   - `seed.md`가 없어도 **중단하지 않는다** — 스택 기준 문서로 그대로 진행한다.
3. **완료기준을 어디서 가져올지 스택에게 위임**한다: 호출한 플러그인(BE/CM/FE/CHAT)의 검증 규칙을 따른다. 명령은 "무엇을 검사할지"를 박지 않고 "스택 기준으로 검사하라"만 지시한다.
4. 변경 규모를 보고 도구를 고른다 (작으면 메인, 크면 Sub-agent / 울트라코드).

### [E2] 자동검사 (Sub-agent · blocking)

1. **Sub-agent를 호출**하여 스택이 정의한 자동검사를 실행한다 (해당 플러그인의 `shared/verify` 명령):
   - BE/CM: 테스트·lint·build 등 스택 명령.
   - FE: 빌드·린트 + 시각·반응형·접근성 검사 + Claude 디자인 검증.
2. Sub-agent는 raw 로그 전문을 `.harness/artifacts/{track}/{identifier}/evaluate-auto-log.txt`에 저장하고, **메인에는 통과/실패 + 로그 경로만** 회수한다.
3. **실패 시 즉시 중단** → 실패 항목과 로그 경로만 사용자에게 보고하고 build로 되돌린다 (blocking).

### [E3] 반박 검증 (Sub-agent / 울트라코드)

1. 자동검사 통과 시에만 진행한다.
2. **울트라코드 ON**: 관점별 검사(버그·보안·성능·구조)를 병렬 Sub-agent로 돌린 뒤, "이거 진짜 문제 맞아?" 반박 라운드로 가짜 경보를 제거한다. 리뷰 렌즈·심각도 분류는 스택 기준(`code-quality-guide.md`)에 근거한다.
3. **울트라코드 OFF**: 메인이 혼자 핵심 관점만 가볍게 점검한다.
4. Sub-agent는 근거·증거를 `.harness/artifacts/{track}/{identifier}/evaluate-findings.md`에 저장하고, **메인에는 결론(통과/blocking 개수)과 경로만** 회수한다.
5. 심화 반박(적대적 라운드)은 review의 [R4]가 담당한다 — 여기서는 핵심 관점만 본다 (같은 반박을 두 번 돌리지 않는다).

### [E4] 관문 (메인)

1. blocking 항목이 있으면 → 멈추고 build로 복귀 (`### [E2]`부터 재검사).
2. 없으면 → 통과 ✅. `evaluate-report.md`를 확정한다 (검사 시점 HEAD를 기록한다 — review [R1]이 재사용 판단에 쓴다).
3. 메인 컨텍스트에는 한 줄 결론(통과/실패)과 산출물 경로만 남긴다.
4. **다음 단계**: 통과 시 `/hb-shared:review`(머지 전 5단계 관문)로 넘어간다.

## 산출물: evaluate-report.md

```markdown
# 검증 리포트

## 대상
- branch: {branch-name}
- HEAD: {git rev-parse --short HEAD}
- 변경 파일 수: {n}
- 기준 출처: {seed.md 완료기준 표 / code-quality-guide.md / .harness/docs/code-convention.yaml + .harness/docs/adr.yaml}
- 적용 스택: {BE/CM/FE/CHAT} (완료기준은 이 스택을 따름)

## 자동검사 (스택 정의)
| 검사 | 결과 | 증거 |
|------|------|------|
| {스택 명령/항목} | 통과/실패 | .harness/artifacts/{track}/{identifier}/evaluate-auto-log.txt |

## 반박 검증
- 모드: 울트라코드 ON(병렬+반박) / OFF(혼자 가볍게)
- 발견(반박 후 잔존): {n}건 — 상세는 evaluate-findings.md
  - [blocking] ...
  - [non-blocking] ...

## 관문 판정
- [ ] 통과 → review/머지로
- [ ] blocking 존재 → build로 복귀 후 재검사

## 메모
- {스택 위임으로 생략한 항목 / 가짜 경보로 제거한 항목}
```
