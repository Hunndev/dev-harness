# BUCCL FE 개발 하네스

3-track 개발 자동화 파이프라인. 기획 → 신규개발 → 유지보수를 구조화된 워크플로우로 수행한다.

이 플러그인은 **BUCCL 프론트엔드(React) 레포 전용**이다.
메인 백엔드(Django) 레포 작업은 `hb-be` 플러그인을 사용한다.

## 프로젝트 스택

- Runtime: Node.js 18+
- Language: JavaScript/JSX + optional TypeScript
- Framework: React 18 (Create React App)
- API: Axios clients under src/api and src/utils/api.js
- Client state: Zustand, React state, local/session storage
- UI: MUI + Bootstrap 혼용 (새 화면은 주변 화면이 쓰는 라이브러리를 따른다)
- Runtime targets: Web browser + Capacitor mobile shell
- Auth: JWT (메인 BE와 공유)
- Testing: React Testing Library + Jest
- Linter: ESLint
- Build: react-scripts build
- Infra: Docker Swarm on Azure VM

## 트랙 목록 (tier 체계)

각 트랙은 **tier**로 운용된다. 기본값은 `:auto` (T1 standard, lightweight).
더 가벼운 것이 필요하면 `:hotfix` (maintenance 전용), 더 깊은 분석이 필요하면 `:deep`을 명시적으로 호출한다.

| 커맨드 | tier | 트랙 | 언제 쓰나 | 코드 수정 |
|--------|------|------|----------|----------|
| `/hb-fe:planning:auto`      | T1 | 기획     | 간이 기획 (스코프 → 타당성 → ADR 드래프트 → 편입) | 없음 |
| `/hb-fe:planning:deep`      | T2 | 기획     | 인터뷰 + 외부조사 + 3관점 Team 포함 full ceremony | 없음 |
| `/hb-fe:feature:auto`       | T1 | 신규개발 | 일반 화면/컴포넌트 (요구사항 → 설계의도 → 시각·바인딩 검증 → 리뷰 → QA) | 있음 |
| `/hb-fe:feature:deep`       | T2 | 신규개발 | prior-art + quality-guide 재생성 + PR본문 Fork 포함 | 있음 |
| `/hb-fe:maintenance:hotfix` | T0 | 유지보수 | 오타·한 줄 fix·긴급 (재현 테스트 → 수정 → 단위 테스트) | 있음 (최소) |
| `/hb-fe:maintenance:auto`   | T1 | 유지보수 | 일상 유지보수 (RCA → 수정 → 회귀) | 있음 (범위 제한) |
| `/hb-fe:maintenance:deep`   | T2 | 유지보수 | 영향도 3방향 Team + ADR 충돌 체크 포함 | 있음 |
| `/hb-fe:shared:update-docs` | —  | 공통     | convention / ADR / architecture / module-registry 갱신 | 문서만 |

### tier 선택 기준

- **T0 hotfix** — 수정 범위가 한 파일·한 라인으로 명확하고, 재현 테스트 + 수정 + 단위 테스트만으로 충분한 경우
- **T1 auto** (기본값) — 일상 작업. 사용자 핑퐁 최소화, Agent Team 없음
- **T2 deep** — 아키텍처급 결정, 다중 모듈 영향, 기존 ADR 위반 의심 등 full ceremony가 필요한 경우

## 산출물 경로

모든 산출물은 `.harness/artifacts/{track}/{identifier}/` 하위에 저장한다.

- planning: `.harness/artifacts/planning/{plan-YYYYMMDD-slug}/`
- maintenance: `.harness/artifacts/maintenance/{issue-id}/`
- feature: `.harness/artifacts/feature/{branch-name}/`

## 참조 문서

플러그인은 작업 디렉토리의 `.harness/docs/` 하위 4개 YAML 파일을 진실의 원천으로 사용한다.

- `.harness/docs/code-convention.yaml` — 코딩 컨벤션 (React/CRA/React Testing Library + Jest 특화)
- `.harness/docs/adr.yaml` — Architecture Decision Records
- `.harness/docs/architecture.yaml` — 시스템 구조 맵
- `.harness/docs/module-registry.yaml` — route/page/component/hook/API/state/style 레지스트리

## FE 작업 두 모드 (디자인 구현 / API 바인딩)

FE 작업은 성격이 다른 두 모드로 나뉜다. **작업 시작(seed) 시 이 작업이 어느 모드인지 먼저 분류**하고, 그에 맞는 완료기준·증거·리뷰 렌즈를 적용한다. "테스트 통과"만으로 FE를 완료하지 않는다 — 디자인 모드는 화면이 실제로 맞는지, 바인딩 모드는 데이터가 실제로 흐르고 실패가 처리되는지까지 확인한다. 대부분의 화면 작업은 둘이 섞인 **혼합**이다.

### ① 디자인 구현 (Claude 디자인 → 화면)

- 무엇: 시안·디자인을 React 컴포넌트/화면으로 구현
- 완료기준·증거: `design-source.md`(무엇을 기준으로 삼았는지), `visual-check.md`(desktop/mobile 주요 viewport 캡처·관찰), `responsive-check.md`(375/768/1440 레이아웃·겹침), `accessibility-notes.md`(alt·label·keyboard focus·contrast)
- 리뷰 렌즈: 시각 일관성, 시각 계층, 반응형, 접근성, 디자인 의도 대비 정합

### ② API 바인딩 (화면 → BE 데이터)

- 무엇: 컴포넌트를 BE API에 연결하고 상태·데이터 흐름을 처리
- 완료기준·증거: `api-binding-check.md` — API 계약 일치(엔드포인트·요청/응답 형태), **loading/empty/error/success 상태 처리**, API 실패·타임아웃 처리, **mock/더미 데이터가 production path에 안 남음**, 호출이 `src/api`·`src/utils/api.js` 계층 경유
- 리뷰 렌즈: 계약 적합성, 상태 처리 누락, 에러 핸들링, mock 잔재, baseURL·토큰 흩뿌림

### 혼합

- 대부분의 화면 작업. 두 모드의 산출물·기준·리뷰 렌즈를 **모두** 적용한다.

## E2E 검증 렌즈 (Playwright)

E2E는 제3의 작업 모드가 아니라 두 모드 공용의 **검증 렌즈**다. 변경이 다화면 사용자 흐름(라우팅·인증·핵심 과업 완주)을 관통하거나, 혼합 작업에서 화면과 데이터 흐름이 함께 바뀔 때 이 렌즈를 건다. 단일 컴포넌트의 국소 수정에는 걸지 않는다(N/A). 이 렌즈는 **웹 FE 한정**이다 — 모바일 shell 실기기 E2E는 미도입 상태를 유지한다(dev-harness repo `docs/MOBILE-SHELL-DESIGN.md`의 관찰 기록 철학).

### 자산 소재와 spec 재사용

- Playwright dependency·config·spec의 **소유·보관 위치는 FE 제품 repo**다 — dev-harness plugin source repo에는 자산을 두지 않는다. 이 플러그인은 실행·판정·증거 규칙만 정의한다. 사용자가 승인한 FE 제품 구현에서 setup/변경이 필요하면 **hb-fe 구현 스텝이 FE 제품 repo 안의 dependency/config/spec을 생성·수정할 수 있다**.
- **기존 spec 재사용 우선**: 기존 spec이 대상 시나리오를 덮으면 재실행만 한다. 새 route·새 흐름·기존 spec이 검증하지 않는 상태 전이 등 **갭이 확인될 때만** 신규 spec을 제품 repo의 기존 구조·관례에 맞춰 추가한다. 재사용/신규 구분을 `e2e-check.md`에 기록한다. 신규 spec 추가는 검증 스텝이 아니라 **구현 스텝에서** 수행한다 — 검증 Fork는 산출물만 생성한다(공통 규칙 1). 검증 스텝(F7/F9)에서 **spec 갭을 발견하면 구현 스텝으로 복귀**하고, 구현 단계가 신규 spec 작성·검증을 담당한다(이때 spec 추가는 TDD Red 범위 제한의 예외로 허용). maintenance 트랙에서 갭이 발견되면 해당 트랙의 수정(구현) 스텝에서 같은 예외로 수행한다.

### 실행 환경 3구분과 데이터 안전경계

| 환경 | 무엇 | 데이터 변경 허용 범위 |
|------|------|----------------------|
| `local-mock` (기본값) | 로컬 앱 + mock API | 제약 없음 (mock 데이터이므로 — 아래 게이트는 실데이터·실인프라 대상) |
| `local-dev-api` | 로컬 앱 + dev API 서버 | 쓰기는 dev 전용 테스트 계정 데이터에 한정 |
| `actual-dev` | 배포된 dev 환경 | dev 전용 테스트 계정에 한해 **최소 mutation 허용** — 예: 고유 실행 ID를 붙인 테스트 메시지 생성(사용자가 사전 승인한 user-inst 채팅 realtime E2E 시나리오). 생성 범위와 cleanup 가능 여부를 `e2e-check.md`에 기록 |

- 환경 승격 기준: mock으로 검증 불가한 실제 API 계약·인증·realtime 시나리오에 한해 상위 환경으로 승격하며, `actual-dev`는 배포 환경 고유 동작 검증이 필요할 때만 쓴다.
- 고위험·파괴적 변경(예약·차단·신고·결제·티켓, 기존 데이터 수정/삭제, DB 직접 조작, secret 변경)은 **별도 사용자 승인 없이는 금지**한다. 이 게이트는 실데이터·실인프라를 대상으로 한다 — `local-mock`에서 mock 데이터만 오가는 시나리오 실행은 게이트 대상이 아니며, 실데이터·실인프라에 닿는 순간 적용된다. **production 실행은 전면 금지.**
- **user-inst 독립 context**: `user`·`inst` **양 계정이 참여하는 시나리오**에서는 `user` 계정용 browser context와 `inst` 계정용 browser context를 **각각 독립 생성**하고, cookie·localStorage·sessionStorage·auth 상태(토큰/세션)를 context 간 격리한다. **단일 역할 시나리오는 필요한 계정의 context만** 독립 생성한다 — 격리 원칙은 동일하게 적용한다. 두 계정 모두 dev 전용 테스트 계정만 쓰며, 실사용자 세션·개인 데이터를 사용하지 않는다.

### 증거와 판정 (e2e-check.md)

- 증거: 시나리오별 screenshot은 판정 근거로 **필수**이며, **모든 시나리오의 screenshot을 `.harness/artifacts/{track}/{identifier}/e2e-evidence/`로 복사해 보존**한다. video 또는 trace(**하나 이상**)는 `비정상`·`미확인` 시나리오에 **필수**이고 **해당 건만 보존**한다 — `정상` 시나리오의 video/trace는 선택이며 기본적으로 보존하지 않는다. 실행 중 증거 파일은 제품 repo의 Playwright 기본 출력 디렉토리에 생성되지만 worktree 정리로 사라질 수 있으므로, `e2e-check.md`에는 **worktree 정리 후에도 유효한 보존 사본 경로만** 기록한다. 실행 자체가 불가해 증거가 생성되지 않은 `미확인` 건은 screenshot·video/trace 대신 **실패 로그와 "증거 없음" 사유**를 `e2e-check.md`에 기록한다 — 이 경우 video/trace 필수 요건도 함께 면제된다.
- 판정은 2계층: 시나리오별 **`정상 / 비정상 / 미확인`**, verify 최종 판정은 기존 `PASS | FAIL` 유지. `비정상`이 1건이라도 있으면 FAIL, `미확인`이 남아 있으면 최종 PASS 불가 — 이때 최종 판정은 **FAIL로 기록**하고 사유를 "미확인 잔존(환경/데이터 사유)"으로 명시한 뒤 사용자 판단을 받는다. `미확인` = 환경 불안정·데이터 부재·외부 의존으로 정상/비정상을 판단할 수 없는 상태(실패로 단정하지 않되 통과로도 치지 않는다).
- 산출물: `.harness/artifacts/{track}/{identifier}/e2e-check.md` — **검사 시점 HEAD SHA와 E2E 대상 source/spec 파일의 content fingerprint**(재사용 가드 판별 기준), 실행 환경, 사용 계정·context, 시나리오 표(판정·증거 경로), 재사용/신규 spec 구분, 생성 데이터 범위·cleanup 여부.
- maintenance deep의 `regression-e2e.md`(전체 Jest 회귀)와는 **별개**다. Playwright E2E를 실제 실행한 경우 그 결과는 `e2e-check.md` 형식(3판정)을 따른다.

## 실행 모드 정의

| 모드 | 설명 | 사용자 상호작용 |
|------|------|----------------|
| Fork | worktree 격리 실행. 사용자와 핑퐁이 많은 구간 | 있음 (피드백 루프) |
| Sub-agent | 단일 에이전트 위임. 고정 형식 분석/판단 | 없음 (자동) |
| Agent Team | 다관점 병렬 분석. **Claude Code 네이티브 Teams** (`TeamCreate` + `Agent` + `SendMessage`)로 tmux 패널에 팀원을 스폰하여 동시 작업 후 메인이 병합. 표준 절차는 `commands/shared/team-protocol.md` | 없음 (자동) |

## 트랙 간 전이 규칙

```
기획 (planning)
   │  decision-draft.md
   ▼
/hb-fe:shared:update-docs adr  ← 사용자 승인 게이트
   │  .harness/docs/adr.yaml
   ▼
신규개발 (feature)       ← 새 ADR을 평가기준으로 흡수
   │  review-comments.md
   ▼
유지보수 (maintenance)   ← 기존 ADR 준수 체크 (convention-check.md)
```

전이 규칙:
1. 유지보수 중 새 설계 결정이 필요하면 → planning 트랙으로 에스컬레이션
2. 신규개발 중 요구사항이 흔들리면 → planning 트랙으로 되돌아감
3. planning 결과물은 자동으로 코드에 반영되지 않음 → 반드시 `/hb-fe:shared:update-docs adr`로 사용자 승인 게이트 통과
4. 새 ADR 생성은 planning 트랙에서만 허용. maintenance 트랙에서 자체적으로 ADR을 만들지 않는다.
5. 다른 레포(메인 BE) 작업이 필요하면 `hb-be` 플러그인으로 전환한다.

## 공통 규칙

1. Fork에서 실행하는 단계는 산출물만 생성하고 소스코드를 수정하지 않는다. (수정 실행 단계 제외)
2. 모든 산출물 디렉토리에 `INDEX.md`를 생성하여 산출물 목록과 현재 상태를 기록한다.
3. 사용자에게 확인을 요청할 때, 모호하여 구체화가 필요한 논의점을 반드시 함께 정리하여 전달한다.
4. Agent Team 실행 시, 각 에이전트의 결과를 메인이 병합하고 충돌/모순을 해소한 뒤 사용자에게 제시한다.
5. API 계약 또는 환경 설정이 포함된 변경은 반드시 API 계약 변경 내역을 별도로 리뷰한다.
6. `package.json` / ESLint / Jest / CRA override / Dockerfile / nginx / 환경변수 변경은 사용자 승인 없이 수행하지 않는다.
7. API 호출은 src/api 또는 src/utils/api.js 계층을 우선 사용하고, base URL·토큰·에러 처리를 화면 컴포넌트에 흩뿌리지 않는다.
8. **디자인 구현** 작업은 `design-source.md`, `design-intent.md`, `visual-check.md`, `responsive-check.md`, `accessibility-notes.md` 중 해당 산출물을, **API 바인딩** 작업은 `api-binding-check.md`(계약 일치·상태 처리·mock 잔재·api 계층 경유)를 남긴다. 혼합이면 둘 다 남긴다. **E2E 검증 렌즈**가 걸린 작업은 `e2e-check.md`(환경·판정·증거)를 추가로 남긴다.
9. TDD: feature/maintenance 트랙은 Red→Green→Refactor 사이클을 따른다. 실패 테스트를 먼저 작성(Red), 최소 구현으로 PASS(Green), 테스트 녹색 유지하며 정리(Refactor). 증거 로그는 아티팩트 디렉토리의 `tdd-baseline-log.txt`(bug/feature는 FAIL, refactor는 PASS baseline) / `tdd-green-log.txt` / `tdd-refactor-notes.md`에 캡처한다. 테스트 러너는 **React Testing Library + Jest**. 자세한 프로토콜은 `commands/shared/tdd.md` 참조.

## 방법론 연결 (hb-shared 순서표)

feature·maintenance 작업은 hb-shared 공통 순서표를 따른다. `feature:auto`/`deep`(및 maintenance)를 호출하면 아래가 자동으로 적용된다:

1. **시작 — 주문서**: `/hb-shared:seed` 방법으로 목표·범위·완료기준을 먼저 고정한다. (작은 일은 약식 3줄, 큰 일은 한 장)
2. **구현**: 아래 트랙 명령(feature/maintenance)으로 만든다.
3. **검사**: `/hb-shared:evaluate` 방법으로 주문서 완료기준 충족을 증거로 확인한다. (feature 트랙은 QA 스텝이 검사를 겸해 리뷰 스텝 뒤에 올 수 있다 — 관문 기준은 동일)
4. **리뷰**: 머지 전 `/hb-shared:review`의 **5단계 관문**(자동검사 → 관점별 → Codex∥Claude 교차 → 반박 → 게이트)을 적용한다. **기존 코드리뷰 스텝의 단일 패스는 이 5단계로 대체**하며, 기존 스텝 절차는 그중 "관점별 리뷰([R2])"의 세부로 쓴다.
5. **개선(선택)**: `/hb-shared:evolve`로 반복 문제를 제안으로 남긴다(제안만, 자동 수정 X).

> **T0 예외**: `maintenance:hotfix`는 위 순서표의 예외다 — seed는 약식 3줄(`hotfix-reproduction.md` 서두)로 갈음하고, evaluate·review 5단계 관문은 **생략**한다 (H3 단위 테스트 게이트가 완료 조건). 5단계 관문이 필요해 보이면 그 자체가 `:auto`로의 에스컬레이션 신호다.
>
> **신선도 훅**: 트랙 완료(INDEX.md 생성) 시 이번 변경이 `.harness/docs/*.yaml`에 반영될 내용(새 모듈·API·ADR·컨벤션 변화)을 만들었는지 확인하고, 있으면 `/hb-fe:shared:update-docs` 실행을 제안한다. 상태 점검 스텝(F1/M1)은 module-registry의 모듈 목록과 실제 소스를 가볍게 대조해 미등재 모듈 수를 한 줄 보고한다 — **차단하지 않는다** (보고만).

완료기준·증거·리뷰 렌즈는 이 플러그인 스택을 따른다. 무거운 읽기·검증은 Sub-agent로 내려 메인 컨텍스트를 아끼고 결론·경로만 회수한다.
