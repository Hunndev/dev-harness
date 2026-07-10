# 근본 원인 추적 — RCA (iOS)

tracer 스타일로 코드를 추적하여 근본 원인을 추정한다.

## 실행 방식

이 skill은 Sub-agent가 실행한다. 단일 가설-검증 루프가 효과적이므로 병렬로 쪼개지 않는다.

## Sub-agent 프롬프트

```
다음 이슈의 근본 원인을 추적하라.

추적 방법:
1. stack trace(logcat)가 있으면 발생 지점을 특정하라.
2. architecture.yaml의 flow를 따라 문제 지점을 역추적하라.
   - 화면: URL/딥링크 → ViewController → WebView(WebViewContainer) → bridge(WebViewBridge) → network(쿠키 동기화) → 웹(FE)
   - 푸시: FCM 수신 → Service → Notification → 딥링크/화면 진입
3. 가설을 세우고 코드에서 검증하라. 가설이 틀리면 다음 가설로.
4. 근본 원인(root cause)을 추정하라. 복수이면 가능성 순 나열.
5. adr.yaml에서 관련 결정을 찾아라.

iOS(Swift/WebView) 특화 확인 항목:
- WebView 설정 오류 (JavaScript 허용, domStorage, mixed content, User-Agent)
- @WKScriptMessageHandler 노출 범위·시그니처 불일치 (웹 호출명 ↔ WebViewBridge.swift ↔ bridge-contract.yaml)
- 쿠키/세션 동기화 누락 (WebViewContainer ↔ CookieManager, WebViewContainer 판단 로직)
- FCM 토큰 갱신/수신 경로 (포그라운드/백그라운드 분기, 알림 채널)
- 딥링크 Universal Link·커스텀 스킴 매칭 실패·중복, 딥링크 재진입(presentation) 처리
- 런타임 권한 요청 타이밍·거부 상태 처리 (카메라·알림(UNUserNotificationCenter) 등)
- WKScriptMessageHandler 등록 누락으로 인한 브리지 호출 실패
- 메인 스레드 블로킹(ANR), WebView 메모리, 생명주기 콜백 순서

인프라/릴리즈 확인 항목:
- App Store 릴리즈 트랙 / versionCode·versionName
- 서명 설정(프로비저닝 프로파일·인증서) / 빌드 variant 차이 (debug vs release)
- FCM 프로젝트 설정 (GoogleService-Info.plist)
- 웹(FE) 배포 URL·쿠키 도메인 정합 / 메인 BE(hb-be) JWT 공유 동기화

[reproduction.md]
[관련 모듈 코드]
[adr.yaml]
[architecture.yaml]
```

## 산출물: root-cause.md

```markdown
# 근본 원인 분석

## 발생 지점
- 파일: {path}
- 라인: {line}
- 함수: {function_name}
- 레이어: viewcontroller | webview | bridge | network | fcm | deeplink | permission | utils

## 근본 원인 추정

### 추정 1 (가능성: 높음)
- 원인: ...
- 근거: (코드의 어떤 부분이 이 추정을 뒷받침하는가)
- 관련 ADR: ADR-XXX (있으면)

### 추정 2 (가능성: 중간)
- 원인: ...
- 근거: ...

## 수정 방향 제안
1. ...
2. ...

## 확인 필요 사항
(사용자에게 추가 확인이 필요한 것)
```
