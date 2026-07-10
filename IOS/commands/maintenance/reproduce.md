# 이슈 재현 (iOS)

이슈를 재현하는 테스트 케이스를 작성하여 수정의 기준점을 확보한다.

## 실행 방식

이 skill은 Fork에서 실행된다.

## 절차

> 이 skill은 TDD 사이클의 **Red 단계** 역할을 한다. 자세한 사이클 정의는 `commands/shared/tdd.md` 참조.

### bug 유형
1. 에러 로그(logcat)/재현 절차/스크린샷/재현 기기 정보를 분석한다.
2. 버그를 재현하는 XCTest 테스트를 작성한다:
   - 파일: `bucclapp/bucclappTests/{package}/{Module}Maint{Identifier}Tests.swift` (identifier는 CamelCase로 변환)
   - 외부 의존성은 target repo의 기존 fake/mock 패턴을 우선 사용
   - 네트워크는 OkHttp MockWebServer, 인터페이스 fake 중 적합한 것 선택 (iOS 프레임워크 의존은 인터페이스로 격리)
   - 현재 상태에서 **FAIL** 확인 (`xcodebuild -scheme bucclapp test --tests "*{Module}Maint{Identifier}*"`)
3. FAIL 출력을 `.harness/artifacts/maintenance/{identifier}/tdd-baseline-log.txt`에 캡처한다. 실패 이유가 **'올바른 이유'(버그 때문)**인지 확인한다. Swift 컴파일/import/mock 오류이면 Red 재작성 (최대 3회, 자세한 규칙은 `commands/shared/tdd.md` 참조).
4. 재현 불가 시 가능한 원인과 추가 필요 정보를 보고한다.

### refactor 유형
1. 리팩토링 대상 코드의 현재 동작을 캡처한다.
2. characterization test를 작성한다:
   - 현재 동작을 "정답"으로 간주하고, 그대로 캡처
   - 리팩토링 후에도 이 테스트가 PASS해야 함
3. 테스트 커버리지가 부족한 영역을 식별한다.
4. **TDD 관점**: characterization test는 '현재 동작'을 Green baseline으로 고정하는 역할. 리팩토링 후에도 이 테스트가 PASS해야 하며, 이는 Refactor 단계의 안전망이다.

### performance 유형
1. 성능 기준선을 측정한다:
   - WebView 로드 시간, 콜드 스타트 시간, 메모리 사용량
   - iOS Studio Profiler 또는 logcat 타이밍 관찰
   - 앱 크기(APK/AAB), ANR/프레임 드랍 여부
2. 기준선을 `reproduction.md`에 기록한다.
3. **TDD 관점**: 기준선과 목표치를 명확히 기록하여 Green 단계의 수용기준으로 사용한다.

## iOS 특화 재현 체크리스트

- [ ] 로그인/쿠키·세션 동기화(WebViewContainer·WebViewContainer) 관련인가?
- [ ] 브리지 함수(WebViewBridge) 시그니처·메시지 포맷 관련인가?
- [ ] WebView 설정(JS 허용·domStorage·mixed content·User-Agent) 관련인가?
- [ ] FCM 푸시 수신 경로(포그라운드/백그라운드, 알림 채널) 관련인가?
- [ ] 딥링크 Universal Link·커스텀 스킴 매칭·딥링크 재진입(presentation) 처리 관련인가?
- [ ] 런타임 권한(카메라·알림(UNUserNotificationCenter) 등) 요청·거부 흐름 관련인가?
- [ ] WKScriptMessageHandler 등록·노출 관련인가?
- [ ] 기기/OS 버전별 WebView 구현 차이 관련인가?
- [ ] 메인 BE(hb-be) 연동 / JWT 공유 관련인가?
- [ ] 웹(FE) 배포 변경(브리지 호출부·쿠키 도메인) 관련인가?
- [ ] App Store 릴리즈/서명/versionCode 관련인가?

## 산출물: reproduction.md

```markdown
# 이슈 재현

## 이슈 요약
- 유형: bug | refactor | performance | dependency | device
- 증상: ...
- 관련 모듈: ...

## 재현 방법
(단계별 재현 절차 — device 이슈면 재현 기기/OS 버전 명시)

## 재현 테스트
- 파일: bucclapp/bucclappTests/{package}/{Module}Maint{Identifier}Tests.swift
- 테스트명: {class} > {method}
- 결과: FAIL (expected) | 재현 불가
- 연관 아티팩트: tdd-baseline-log.txt (FAIL 출력 캡처)

## 성능 기준선 (performance 유형)
| 항목 | 현재 값 | 목표 값 |
|------|--------|--------|
| WebView 로드 시간 | ... | ... |
| 콜드 스타트 | ... | ... |
| 메모리 | ... | ... |
| 앱 크기 (APK/AAB) | ... | ... |
| ANR/프레임 드랍 | ... | ... |

## 추가 필요 정보 (재현 불가 시)
- ...
```
