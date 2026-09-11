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

### 2. 린트 (SwiftLint — 설치·설정된 경우만)
```bash
if command -v swiftlint >/dev/null 2>&1 && [ -f .swiftlint.yml ]; then
  swiftlint lint --strict
else
  echo "SwiftLint 미구성 — 린트 N/A"
fi
```
SwiftLint 실행 파일이 있고 저장소 루트에 `.swiftlint.yml`이 있을 때만 실행하고 위반을 차단한다. 둘 중 하나라도 없으면 결과를 `N/A (SwiftLint 미구성)`으로 기록하고 PASS로 적지 않는다. 빌드 명령(`xcodebuild build`)을 린트 결과로 대신 세지 않는다.

### 3. 테스트 실행
```bash
xcodebuild -scheme bucclapp test -only-testing:bucclappTests/{TestClass}    # 대상 클래스 — 로그의 "Executed N tests"에서 N ≥ 1 확인 (0개 실행은 PASS 아님)
xcodebuild -scheme bucclapp test -enableCodeCoverage YES -resultBundlePath .harness/artifacts/{track}/{identifier}/verify/{attempt}/test.xcresult    # 전체 (회귀 확인) + 커버리지
xcrun xccov view --report --only-targets .harness/artifacts/{track}/{identifier}/verify/{attempt}/test.xcresult    # 타깃별 line coverage
```
`{attempt}`는 이 검증의 회차(1, 2, 3…)다. `-resultBundlePath`는 이미 존재하는 경로를 거부하므로(`Existing file at -resultBundlePath`, exit 64) 회차마다 새 경로를 쓰고, 커버리지는 그 회차의 실제 bundle을 `xccov`에 넘겨 읽는다. `xcrun xccov view --report`가 `No coverage data in result bundle`을 내면 그 실행은 커버리지가 수집되지 않은 것이다 — 수치 없이 PASS로 적지 않고 새 회차로 다시 실행한다.

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
- 커버리지 임계 미달 (TEST-003 — `xcrun xccov view --report`의 line coverage 기준, 저장소가 임계를 정한 경우만)

### 6. 결과 판정
- 전체 PASS → 통과
- 실패 → 수정 루프 (최대 3회)
- 3회 초과 → 사용자에게 보고하고 판단 요청

## 보고 형식

```markdown
## 검증 결과

### 빌드 (xcodebuild build): PASS | FAIL (에러 목록)
### 린트 (SwiftLint): PASS | FAIL (위반 목록) | N/A (미구성)
### 테스트
- 대상 클래스: {N} 통과 / {M} 실패 (Executed N tests, N ≥ 1)
- 전체: {N} 통과 / {M} 실패
- 커버리지: xccov line coverage {X}% (타깃 bucclapp — `xcrun xccov view --report --only-targets …/verify/{attempt}/test.xcresult`)
### 기기/계약 검증: PASS | FAIL | N/A
### Convention 위반: {N}건
### 최종: PASS | FAIL
```
