# 검증 (QA)

구현/수정 완료 후 코드 품질과 동작을 검증한다.
feature(F9/F12) 및 maintenance(M6/M8) 트랙에서 사용한다.

## 실행 방식

이 skill은 Fork에서 실행된다.

## 검증 항목

### 1. 빌드
```bash
xcodebuild -scheme bucclapp build
```
Swift 컴파일 오류, 리소스/Info.plist 오류, 의존성 해석 실패를 차단한다.

### 2. 린트
```bash
xcodebuild -scheme bucclapp build
```
iOS Lint 위반(보안·성능·정합성 규칙) 차단.

### 3. 테스트 실행
```bash
xcodebuild -scheme bucclapp test --tests "*{Module}*"    # 대상 모듈
xcodebuild -scheme bucclapp test                          # 전체 (회귀 확인)
```

### 4. 기기/계약 검증
shell 기능 변경(WebView 설정·푸시·딥링크·권한·릴리즈)이 있으면 `device-check.md`, `permission-check.md`, `release-check.md` 또는 `device-regression.md`가 최신인지 확인한다.
브리지 계약 변경이 있으면 `bridge-check.md`(계약 일치·형제 반영 여부)와 `.harness/docs/bridge-contract.yaml` 갱신도 최신인지 확인한다.

### 5. Convention 체크
변경된 파일에 대해 `.harness/docs/code-convention.yaml` 위반 여부를 확인:
- Log/디버그 출력 잔재 (GEN-004)
- 50줄 초과 함수 (GEN-001)
- ViewController에 WebView 설정/쿠키/권한 로직 과도하게 집중 (WEBVIEW-001)
- 브리지 단일 계층(WebViewBridge) 우회한 웹→네이티브 진입 (BRIDGE-001)
- 쿠키/세션 동기화 판단 로직 흩뿌림 (NET-001)
- Info.plist 권한 과다·Universal Link·커스텀 스킴 중복 (PERM-001)
- WKScriptMessageHandler 등록 누락 (브리지 메서드 노출 실패 위험) (BUILD-001)
- 커버리지 임계 미달 (TEST-003 — jacoco 설정된 레포에서만)

### 6. 결과 판정
- 전체 PASS → 통과
- 실패 → 수정 루프 (최대 3회)
- 3회 초과 → 사용자에게 보고하고 판단 요청

## 보고 형식

```markdown
## 검증 결과

### 빌드 (assembleDebug): PASS | FAIL (에러 목록)
### 린트: PASS | FAIL (위반 목록)
### 테스트
- 대상 모듈: {N} 통과 / {M} 실패
- 전체: {N} 통과 / {M} 실패
- 커버리지: (jacoco 설정 시) branches {X}%, functions {Y}%, lines {Z}%, statements {W}%
### 기기/계약 검증: PASS | FAIL | N/A
### Convention 위반: {N}건
### 최종: PASS | FAIL
```
