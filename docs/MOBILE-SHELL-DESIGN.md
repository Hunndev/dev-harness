# MOBILE-SHELL-DESIGN — hb-aos·hb-ios 설계 (2026-07-08)

> BUCCL 모바일 웹뷰 앱 2종(buccl-aos, ios-buccl)을 dev-harness 체계에 편입하기 위한 설계.
> 전례: `docs/SHARED-CORE-DESIGN.md`(방법론 코어), hb-chat 신설 절차.

## 1. 배경과 진단 (실측 2026-07-08)

- **buccl-aos**: Kotlin 38파일, Gradle KTS. WebView shell — JS 브리지(`bridge/WebAppInterface.kt`), 인증 쿠키 동기화(`WebViewCookieJar`, `AuthCookieSyncDecisions`), Firebase 푸시(8파일), 딥링크(intent-filter 10), 권한(CAMERA·POST_NOTIFICATIONS 등), 테스트 8개(JUnit).
- **ios-buccl**: Swift 앱 소스 27파일(`bucclapp/bucclapp.xcodeproj`, `Lib/` 벤더 별도). `WebViewContainer.swift` + `WebViewBridge.swift`, FCM(가이드 2종), `bucclappTests`(XCTest — DeepLinkPresentationTests 등), `scripts/` 검증 스크립트.
- 두 앱은 FE(React)를 웹뷰로 싣는 **기능 패리티 쌍둥이**. 패리티 유지가 이미 수작업 실무다 — 근거: AOS 커밋 `fix/login-30day-aos-parity`·"bridge 동기화", iOS 루트의 `AOS_SWIPE_BACK_SPEC.md`.
- 문제: 하네스 밖 ad-hoc 운영 — 주문서·검사·리뷰 관문 없음, 쌍둥이 드리프트 방지 장치 없음, 브리지 계약이 문서화되지 않음.

## 2. 결정

- **D1 — 플러그인 2개 신설 (`hb-aos`, `hb-ios`)**: 레포·언어·빌드가 다르면 플러그인도 다르다(hb-be/hb-cm 전례). 통합 플러그인(hb-app)은 Gradle/Xcode 명령이 한 매뉴얼에 섞여 기각.
- **D2 — 베이스는 hb-fe 복사**: 가장 가까운 클라이언트 플러그인. prefix·스택 치환으로 신설(정석 절차: cp 베이스 → 치환 → 마켓 2곳 → 린터 확장 → 음성테스트).
- **D3 — hb-shared 방법론 재사용**: seed·evaluate·review·evolve 복제 금지. 파이프라인 스텝에 겸직 앵커만 배선(F2=seed, QA=evaluate, 리뷰=review 5관문).
- **D4 — 골격 완전 미러 + 린터 대칭**: 두 플러그인의 커맨드 파일 세트·스텝 구조는 동일(스택 어휘만 차이). 린터 R3에 AOS↔IOS 엄격 쌍 추가(BE↔CM 방식).
- **D5 — cross-repo 직접 수정 금지**: 형제 플랫폼 반영은 기록·제안만(CHAT 경계 규칙 이식). 상대 레포 작업은 상대 플러그인으로 전환.
- **D6 — 기존 앱 레포 문서 불변**: 두 레포의 CLAUDE.md·AGENTS.md는 건드리지 않는다(opt-in 모드 — `/hb-aos:…` 호출 시에만 작동, 자동 연결 없음).

## 3. 작업 두 모드 (FE 두 모드의 웹뷰 앱 대응)

seed 시점에 분류한다. 혼합이면 둘 다 적용.

| 모드 | 무엇 | 완료기준·증거 산출물 |
|---|---|---|
| **① shell 기능** | WebView 설정·푸시·딥링크·권한·쿠키/세션·스토어 릴리즈 | `device-check.md`(기기/OS 확인 기록) · `permission-check.md` · `release-check.md`(버전·서명·심사 항목) |
| **② 브리지 계약** | 웹→네이티브 API (`WebAppInterface.kt` ↔ `WebViewBridge.swift`) | `bridge-check.md`(계약 일치·형제 반영 여부) + `.harness/docs/bridge-contract.yaml` 갱신 |

리뷰 렌즈: ①은 권한 과다·푸시 수신 경로·딥링크 충돌·WebView 보안 설정(JS 인터페이스 노출 범위), ②는 함수 시그니처·메시지 포맷·에러 처리·**형제 플랫폼과의 계약 동일성**.

## 4. 스택 정의

| | hb-aos | hb-ios |
|---|---|---|
| 언어/빌드 | Kotlin · Gradle KTS | Swift · Xcode(`bucclapp` scheme) |
| 테스트 러너 | JUnit (`./gradlew testDebugUnitTest`) | XCTest (`xcodebuild test`) |
| verify (shared/verify) | `./gradlew testDebugUnitTest lint assembleDebug` | `xcodebuild -scheme bucclapp build test` + `scripts/` 보조 |
| TDD | Red→Green→Refactor 동일 적용 (증거: tdd-baseline/green-log) | 동일 |

## 5. 트랙·티어·산출물 경로

4도메인과 동일: `planning`/`feature`/`maintenance` × `hotfix`/`auto`/`deep`.
명령: `/hb-aos:{track}:{tier}`, `/hb-ios:{track}:{tier}`, `/hb-aos:shared:update-docs` 등.
산출물: `.harness/artifacts/{track}/{identifier}/` (feature=branch명, maintenance=issue-id, planning=plan-YYYYMMDD-slug).

## 6. 진실의 원천 (`.harness/docs` — 각 앱 레포, 5종)

- 공통 4종: `code-convention.yaml` / `adr.yaml` / `architecture.yaml` / `module-registry.yaml`
- **+ `bridge-contract.yaml`**: 브리지 함수·메시지 포맷·에러 계약. **양 레포가 동일 내용을 유지**한다 — 브리지 계약 모드 작업은 이 파일 갱신을 동반하고, 형제 레포 반영 필요를 기록한다.
- 플러그인은 템플릿을 싣지 않는다 — 각 레포에서 update-docs로 작성 (기존 규칙).
- iOS `Lib/`(벤더 코드)는 module-registry 대상에서 제외한다.

## 7. 패리티 장치 (3중)

1. **골격 미러**: 커맨드 파일 세트·스텝 ID·산출물 목록이 hb-aos ↔ hb-ios 동일. 감사 4바퀴의 교훈("동일 문구 형제 좌표") — 수정은 항상 두 플러그인에 한 커밋으로.
2. **린터 강제**: `TARGET_DIRS`에 AOS/IOS 추가, R3에 AOS↔IOS 엄격 쌍(planning·maintenance 완전 대칭, feature 동일 기준), R5/R6/R7/R9/R10/R11 확장. 확장 전 green 측정 → 확장 → 음성테스트(가짜 위반 → ❌ → 커밋 후 원복).
3. **파이프라인 스텝**: 모든 트랙 완료(INDEX.md)에 **"형제 플랫폼 반영 필요 여부"** 기록 항목. 브리지·푸시·딥링크·UX 규칙 변경 시 상대 플랫폼용 제안(이슈 초안)을 산출물로 남긴다 — 직접 수정은 금지(D5).

## 8. 구현 단계

- **Phase 1 — 플러그인 신설** (dev-harness PR 1개): AOS/·IOS/ 디렉토리(hb-fe 복사·치환), codex-plugin 페어, 마켓플레이스 2곳 등록, 린터 확장+음성테스트, 버전 0.1.0. 완료 게이트: R1~R11 green + 음성테스트 실검출.
- **Phase 2 — 장부 초판** (각 앱 레포에서 1회): `/hb-aos:shared:update-docs`, `/hb-ios:shared:update-docs`로 5종 작성. **bridge-contract.yaml은 현재 브리지 소스를 읽어 초판 작성 후 양 레포 대조** — 첫 대조에서 발견되는 어긋남이 이 단계의 수확이다.
- **Phase 3 — 시운전**: 작은 수정 1건을 `/hb-aos:maintenance:auto`로 완주 — 패리티 기록(형제 반영 여부)까지 산출되는지 확인 후 일상 사용 전환.
- 이후: 신설 플러그인 대상 검수(감사) 1회 권장.

단계 분리 이유: 각 단계의 검증 대상이 다르다 — P1=규격(린터), P2=현실 정합(대조), P3=실전(시운전). 한 번에 하면 실패 원인이 섞인다.

## 9. 주의·보류

- **서명키**: `buccl-aos/buccl-release.jks`가 레포 루트에 존재 — 하네스 밖 보안 사안이나 분리 보관 권장.
- 스토어 심사·릴리즈 자동화는 스코프 밖 — `release-check.md`는 문서 산출물만.
- 실기기 E2E 자동화 미도입 — `device-check.md`는 관찰 기록 방식(FE visual-check와 동일 철학).
- 웹(FE) 쪽 브리지 호출부와의 계약 대조는 FE 레포 작업(hb-fe) 몫 — 필요 시 hb-fe의 api-binding-check에 브리지 렌즈 추가를 후속 과제로 남긴다.
