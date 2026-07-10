# 문서 업데이트

`.harness/docs/` 하위 문서를 갱신한다. 모든 트랙의 마지막 단계에서 호출된다.

## 사용법

```
/hb-aos:shared:update-docs                — 전체 문서 대상으로 변경 필요 항목 분석
/hb-aos:shared:update-docs convention     — code-convention.yaml만
/hb-aos:shared:update-docs adr            — adr.yaml만
/hb-aos:shared:update-docs architecture   — architecture.yaml만
/hb-aos:shared:update-docs modules        — module-registry.yaml만
/hb-aos:shared:update-docs bridge         — bridge-contract.yaml만
```

## 공통: 컨텍스트 분석 우선 원칙

1. `.harness/docs/` 하위 5개 문서를 **모두** 읽는다.
2. 현재 작업의 변경 내용과 기존 항목을 대조하여 다음을 판단한다:
   - **충돌 항목**: 이번 변경이 기존 항목과 모순되는가?
   - **연쇄 수정**: 한 문서의 변경이 다른 문서에도 영향을 미치는가?
   - **폐기 대상**: 이번 변경으로 더 이상 유효하지 않은 항목이 있는가?
   - **누락 항목**: 이번 변경에서 새로 확립된 패턴/결정이 문서에 없는가?
3. 분석 결과를 **변경 제안 목록**으로 정리한다:
   - `MUST` — 반드시 반영 (충돌, 사실 오류)
   - `RECOMMENDED` — 반영 권장 (개선, 누락 보완)
4. 사용자에게 제안 목록을 제시하고, 최종 결정을 받는다.

## 트랙별 주요 갱신 대상

| 트랙 | 주요 갱신 문서 | 비고 |
|------|-------------|------|
| planning | adr.yaml | decision-draft.md 편입. 자동 편입 금지 — 사용자 승인 필수 |
| maintenance | code-convention.yaml | 새 패턴 발견 시. ADR 생성은 planning으로 에스컬레이션 |
| feature | module-registry.yaml, adr.yaml, bridge-contract.yaml | 새 모듈/브리지 계약 반영. 새 ADR은 planning 거쳐야 함 |

## 신선도 교차검사 (호출 시 항상)

이 명령이 호출되면 갱신 대상 여부와 무관하게 아래를 가볍게 수행하고 결과를 한 줄 보고한다:

1. `.harness/docs/module-registry.yaml`의 모듈 목록 vs 실제 소스(`app/src/main/kotlin/com/buccl/bucclapp/` 하위 패키지 디렉토리 목록)를 대조한다.
2. 미등재 모듈·사라진 모듈이 있으면 개수와 이름만 보고하고, 등재는 사용자 확인 후 진행한다 (자동 편입 금지).
3. `.harness/docs/` 마지막 갱신 커밋(`git log -1 --format=%ad --date=short -- .harness/docs`) 이후 코드 커밋 수를 보고한다 — 문서가 코드를 얼마나 뒤쳐졌는지의 신호.

## ADR 편입 시 특별 규칙

planning 트랙의 `decision-draft.md`를 adr.yaml에 편입할 때:
1. `decision-draft.md`의 `편입 상태`가 `미승인`이면 편입 불가.
2. 사용자가 이 대화에서 명시적으로 승인해야 한다.
3. 기존 ADR과의 충돌을 반드시 체크한다.
4. 충돌 시 기존 ADR의 status를 `superseded`로 변경할지 사용자에게 확인한다.
5. **편입 후 YAML 본문 제시 (필수)**: 편입을 완료한 후 단순 "ADR-XXX 편입 완료" 메시지로 끝내지 않고, `.harness/docs/adr.yaml` 에 들어간 해당 ADR 의 yaml 본문 (또는 `context` / `decision` / `consequences` 핵심 발췌) 을 yaml 코드 블록으로 사용자에게 직접 보여준다. 사용자가 편입 결과를 자기 눈으로 확인 가능해야 한다.

## code-convention.yaml 스키마

```yaml
- id: {카테고리}-{번호}    # GEN, WEBVIEW, BRIDGE, NET, PUSH, PERM, BUILD, TEST, GIT
  rule: ...                 # 명확하고 실행 가능한 규칙
  stacks: [...]             # kotlin, webview, bridge, fcm, deeplink, permission, all 등
```

## adr.yaml 스키마

```yaml
- id: ADR-{번호}
  title: ...
  status: adopted | deprecated | superseded
  date: YYYY-MM-DD
  stacks: [...]
  context: |
    (구체적 상황 서술 — 문제, 고통, 검토한 대안 포함)
  decision: ...
  consequence: ...
```

## context 작성 가이드라인

- 나쁜 예: "푸시 처리가 불안정해서 설정을 변경"
- 좋은 예: "알림 클릭으로 딥링크 진입 시 쿠키 동기화가 끝나기 전에 WebView가 로드되어 로그인 화면으로 떨어지는 문의가 반복되어, 알림 → 딥링크 → 세션 복원 순서를 명문화한다."
- context가 불충분하면 사용자에게 구체화를 요청한다.

## architecture.yaml 갱신

변경 대상: runtime, entrypoints, webview, bridge, push, deeplink, release 계열 — 작업 레포 `.harness/docs/architecture.yaml`의 실제 섹션을 따른다.
매니페스트·릴리즈 설정 관련 maintenance 후에는 반드시 갱신한다.

## module-registry.yaml 갱신

변경 대상: modules 목록.
feature 트랙 후에는 반드시 갱신한다.

```yaml
- name: ...
  paths: [app/src/main/kotlin/com/buccl/bucclapp/bridge/{...}, app/src/main/kotlin/com/buccl/bucclapp/webview/{...}, app/src/main/kotlin/com/buccl/bucclapp/network/{...}, app/src/main/kotlin/com/buccl/bucclapp/utils/{...}]
  owns: [...]
  checks: [...]
  notes: |
    ...
```

## bridge-contract.yaml 갱신

브리지 함수·메시지 포맷·에러 계약의 진실의 원천. **양 플랫폼(buccl-aos ↔ ios-buccl)이 동일 내용을 유지**한다.

```yaml
functions:
  - name: ...                      # 웹이 호출하는 함수명 (WebAppInterface 메서드)
    direction: web->native | native->web
    params: {...}                  # 파라미터 이름·타입·필수 여부
    returns: ...                   # 반환/콜백 형태
    errors: [...]                  # 에러 케이스와 전달 방식
    since: ...                     # 도입 버전
```

갱신 규칙:
1. 브리지 계약 모드 작업은 이 파일 갱신을 **동반**한다 (`bridge-check.md`에 갱신 여부 기록).
2. 갱신 시 형제 레포(ios-buccl)의 동일 파일 반영 필요를 기록하고, `parity-proposal.md`(반영 제안 초안)를 산출물로 남긴다.
3. **ios-buccl 직접 수정 금지 — hb-ios로 전환.** 이 명령은 buccl-aos 레포의 파일만 갱신한다.
4. 현재 `WebAppInterface.kt` 소스와 대조하여 계약-구현 불일치가 발견되면 MUST 항목으로 보고한다.
