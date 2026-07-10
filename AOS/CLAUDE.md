# BUCCL AOS 개발 하네스

3-track 개발 자동화 파이프라인. 기획 → 신규개발 → 유지보수를 구조화된 워크플로우로 수행한다.

이 플러그인은 **BUCCL Android 웹뷰 앱(buccl-aos) 레포 전용**이다. 웹 화면 자체는 hb-fe(React 레포) 몫이다.
메인 백엔드(Django) 레포 작업은 `hb-be` 플러그인을 사용한다.

## 프로젝트 스택

- Language: Kotlin (앱 소스 38파일 규모)
- Build: Gradle KTS (`build.gradle.kts`, `app/build.gradle.kts`)
- Shell: Android WebView — FE 웹을 싣는 껍데기 (`webview/BucclWebViewClient.kt`, `BucclWebChromeClient.kt`)
- 브리지: `app/src/main/kotlin/com/buccl/bucclapp/bridge/WebAppInterface.kt` (`@JavascriptInterface` — 웹→네이티브 API 단일 진입점)
- 인증: 쿠키·세션 동기화 — `network/WebViewCookieJar.kt`, `AuthCookieSyncDecisions.kt` (JWT는 메인 BE와 공유, 로그인 주체는 웹)
- 푸시: Firebase FCM (`fcm/` 8파일)
- 딥링크: intent-filter 10개 (`AndroidManifest.xml`)
- 권한: CAMERA · POST_NOTIFICATIONS · VIBRATE 등 런타임 권한 흐름
- Testing: JUnit — `app/src/test/kotlin/com/buccl/bucclapp/` (`./gradlew testDebugUnitTest`)
- Lint: Android Lint (`./gradlew lint`)
- Build 검증: `./gradlew assembleDebug`
- 배포: Play 스토어 (서명 jks — 키 파일 자체는 하네스 밖 보안 사안)

## 트랙 목록 (tier 체계)

각 트랙은 **tier**로 운용된다. 기본값은 `:auto` (T1 standard, lightweight).
더 가벼운 것이 필요하면 `:hotfix` (maintenance 전용), 더 깊은 분석이 필요하면 `:deep`을 명시적으로 호출한다.

| 커맨드 | tier | 트랙 | 언제 쓰나 | 코드 수정 |
|--------|------|------|----------|----------|
| `/hb-aos:planning:auto`      | T1 | 기획     | 간이 기획 (스코프 → 타당성 → ADR 드래프트 → 편입) | 없음 |
| `/hb-aos:planning:deep`      | T2 | 기획     | 인터뷰 + 외부조사 + 3관점 Team 포함 full ceremony | 없음 |
| `/hb-aos:feature:auto`       | T1 | 신규개발 | 일반 shell 기능/브리지 작업 (요구사항 → 설계의도 → 기기·계약 검증 → 리뷰 → QA) | 있음 |
| `/hb-aos:feature:deep`       | T2 | 신규개발 | prior-art + quality-guide 재생성 + PR본문 Fork 포함 | 있음 |
| `/hb-aos:maintenance:hotfix` | T0 | 유지보수 | 오타·한 줄 fix·긴급 (재현 테스트 → 수정 → 단위 테스트) | 있음 (최소) |
| `/hb-aos:maintenance:auto`   | T1 | 유지보수 | 일상 유지보수 (RCA → 수정 → 회귀) | 있음 (범위 제한) |
| `/hb-aos:maintenance:deep`   | T2 | 유지보수 | 영향도 3방향 Team + ADR 충돌 체크 포함 | 있음 |
| `/hb-aos:shared:update-docs` | —  | 공통     | convention / ADR / architecture / module-registry / bridge-contract 갱신 | 문서만 |

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

플러그인은 작업 디렉토리의 `.harness/docs/` 하위 5개 YAML 파일을 진실의 원천으로 사용한다.

- `.harness/docs/code-convention.yaml` — 코딩 컨벤션 (Kotlin/Android WebView/JUnit 특화)
- `.harness/docs/adr.yaml` — Architecture Decision Records
- `.harness/docs/architecture.yaml` — 시스템 구조 맵
- `.harness/docs/module-registry.yaml` — bridge/webview/network/fcm/utils 레지스트리
- `.harness/docs/bridge-contract.yaml` — 브리지 함수·메시지 포맷·에러 계약 (**양 플랫폼(AOS/iOS)이 동일 내용을 유지**)

## AOS 작업 두 모드 (shell 기능 / 브리지 계약)

AOS 작업은 성격이 다른 두 모드로 나뉜다. **작업 시작(seed) 시 이 작업이 어느 모드인지 먼저 분류**하고, 그에 맞는 완료기준·증거·리뷰 렌즈를 적용한다. "테스트 통과"만으로 AOS를 완료하지 않는다 — shell 모드는 기기에서 실제로 도는지, 브리지 모드는 계약이 실제로 일치하고 형제 플랫폼 반영 필요가 기록되었는지까지 확인한다. 두 모드가 섞이면 **혼합**이다.

### ① shell 기능

- 무엇: WebView 설정·푸시·딥링크·권한·쿠키/세션·스토어 릴리즈
- 완료기준·증거: `device-check.md`(기기/OS 확인 기록 — 주요 화면·푸시 수신·딥링크 진입·권한 흐름), `permission-check.md`(요청 권한·근거·거부 시 동작), `release-check.md`(버전·서명·심사 항목)
- 리뷰 렌즈: 권한 과다, 푸시 수신 경로, 딥링크 충돌, WebView 보안 설정(JS 인터페이스 노출 범위)

### ② 브리지 계약

- 무엇: 웹→네이티브 API (`WebAppInterface.kt`)
- 완료기준·증거: `bridge-check.md`(계약 일치·형제 반영 여부) + `.harness/docs/bridge-contract.yaml` 갱신
- 리뷰 렌즈: 함수 시그니처, 메시지 포맷, 에러 처리, **형제 플랫폼(iOS)과의 계약 동일성**

### 혼합

- 두 모드가 섞인 작업. 두 모드의 산출물·기준·리뷰 렌즈를 **모두** 적용한다.

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
/hb-aos:shared:update-docs adr  ← 사용자 승인 게이트
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
3. planning 결과물은 자동으로 코드에 반영되지 않음 → 반드시 `/hb-aos:shared:update-docs adr`로 사용자 승인 게이트 통과
4. 새 ADR 생성은 planning 트랙에서만 허용. maintenance 트랙에서 자체적으로 ADR을 만들지 않는다.
5. 다른 레포 작업이 필요하면 플러그인을 전환한다 — 메인 BE는 `hb-be`, 웹 화면(FE)은 `hb-fe`. **형제 플랫폼 ios-buccl 레포는 직접 수정 금지 — `hb-ios`로 전환**한다. 형제 반영이 필요한 변경은 `parity-proposal.md`로 제안만 남긴다.

## 공통 규칙

1. Fork에서 실행하는 단계는 산출물만 생성하고 소스코드를 수정하지 않는다. (수정 실행 단계 제외)
2. 모든 산출물 디렉토리에 `INDEX.md`를 생성하여 산출물 목록과 현재 상태, **형제 플랫폼(iOS) 반영 필요 여부**를 기록한다.
3. 사용자에게 확인을 요청할 때, 모호하여 구체화가 필요한 논의점을 반드시 함께 정리하여 전달한다.
4. Agent Team 실행 시, 각 에이전트의 결과를 메인이 병합하고 충돌/모순을 해소한 뒤 사용자에게 제시한다.
5. 브리지 계약 또는 매니페스트(권한·intent-filter)가 포함된 변경은 반드시 계약/매니페스트 변경 내역을 별도로 리뷰한다.
6. `build.gradle.kts` / `gradle.properties` / `AndroidManifest.xml`(권한·intent-filter) / ProGuard·R8 규칙 / 서명 설정(jks) / `google-services.json` 변경은 사용자 승인 없이 수행하지 않는다.
7. 웹→네이티브 진입은 `bridge/WebAppInterface.kt` 단일 계층을 유지하고, WebView 설정·쿠키 동기화·권한 처리를 Activity에 흩뿌리지 않는다.
8. **shell 기능** 작업은 `design-intent.md`(설계 의도), `device-check.md`, `permission-check.md`, `release-check.md` 중 해당 산출물을, **브리지 계약** 작업은 `bridge-check.md`(계약 일치·형제 반영 여부) + `.harness/docs/bridge-contract.yaml` 갱신을 남긴다. 혼합이면 둘 다 남긴다.
9. TDD: feature/maintenance 트랙은 Red→Green→Refactor 사이클을 따른다. 실패 테스트를 먼저 작성(Red), 최소 구현으로 PASS(Green), 테스트 녹색 유지하며 정리(Refactor). 증거 로그는 아티팩트 디렉토리의 `tdd-baseline-log.txt`(bug/feature는 FAIL, refactor는 PASS baseline) / `tdd-green-log.txt` / `tdd-refactor-notes.md`에 캡처한다. 테스트 러너는 **JUnit** (`./gradlew testDebugUnitTest`). 자세한 프로토콜은 `commands/shared/tdd.md` 참조.
10. 브리지·푸시·딥링크 계약을 바꾼 작업은 `parity-proposal.md`(ios-buccl용 반영 제안 초안)를 산출물로 남긴다. **ios-buccl 직접 수정 금지 — hb-ios로 전환.**

## 방법론 연결 (hb-shared 순서표)

feature·maintenance 작업은 hb-shared 공통 순서표를 따른다. `feature:auto`/`deep`(및 maintenance)를 호출하면 아래가 자동으로 적용된다:

1. **시작 — 주문서**: `/hb-shared:seed` 방법으로 목표·범위·완료기준을 먼저 고정한다. (작은 일은 약식 3줄, 큰 일은 한 장)
2. **구현**: 아래 트랙 명령(feature/maintenance)으로 만든다.
3. **검사**: `/hb-shared:evaluate` 방법으로 주문서 완료기준 충족을 증거로 확인한다. (feature 트랙은 QA 스텝이 검사를 겸해 리뷰 스텝 뒤에 올 수 있다 — 관문 기준은 동일)
4. **리뷰**: 머지 전 `/hb-shared:review`의 **5단계 관문**(자동검사 → 관점별 → Codex∥Claude 교차 → 반박 → 게이트)을 적용한다. **기존 코드리뷰 스텝의 단일 패스는 이 5단계로 대체**하며, 기존 스텝 절차는 그중 "관점별 리뷰([R2])"의 세부로 쓴다.
5. **개선(선택)**: `/hb-shared:evolve`로 반복 문제를 제안으로 남긴다(제안만, 자동 수정 X).

> **T0 예외**: `maintenance:hotfix`는 위 순서표의 예외다 — seed는 약식 3줄(`hotfix-reproduction.md` 서두)로 갈음하고, evaluate·review 5단계 관문은 **생략**한다 (H3 단위 테스트 게이트가 완료 조건). 5단계 관문이 필요해 보이면 그 자체가 `:auto`로의 에스컬레이션 신호다.
>
> **신선도 훅**: 트랙 완료(INDEX.md 생성) 시 이번 변경이 `.harness/docs/*.yaml`에 반영될 내용(새 모듈·브리지 계약·ADR·컨벤션 변화)을 만들었는지 확인하고, 있으면 `/hb-aos:shared:update-docs` 실행을 제안한다. 상태 점검 스텝(F1/M1)은 module-registry의 모듈 목록과 실제 소스를 가볍게 대조해 미등재 모듈 수를 한 줄 보고한다 — **차단하지 않는다** (보고만).

완료기준·증거·리뷰 렌즈는 이 플러그인 스택을 따른다. 무거운 읽기·검증은 Sub-agent로 내려 메인 컨텍스트를 아끼고 결론·경로만 회수한다.
