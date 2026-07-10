# 영향도 조사 — 병렬 탐색 (iOS)

3개 방향에서 동시에 영향 범위를 탐색한다.
모듈/호출자/데이터 흐름을 동시에 훑어야 누락이 없다.

## 실행 방식

이 skill은 **Claude Code 네이티브 Teams**로 실행된다. 표준 절차는 `commands/shared/team-protocol.md` 참조.

### 팀 스펙

- `team_name`: `maint-impact-{identifier}` (예: `maint-impact-BUCCL-iOS-42`)
- `description`: "영향도 3방향 병렬 탐색 (모듈/호출자/데이터흐름)"
- 팀원 3명 (모두 `subagent_type: general-purpose`, 병렬 스폰):

  | 팀원 이름 | 사용할 프롬프트 블록 | 산출 파일 |
  |----------|--------------------|----------|
  | `layer-tracer`    | 아래 "Agent A: 모듈/레이어 방향" | `.harness/artifacts/maintenance/{identifier}/impact-layer.md` |
  | `caller-tracer`   | 아래 "Agent B: 호출자 방향"     | `.harness/artifacts/maintenance/{identifier}/impact-caller.md` |
  | `dataflow-tracer` | 아래 "Agent C: 데이터 흐름 방향" | `.harness/artifacts/maintenance/{identifier}/impact-dataflow.md` |

- 메인: 3개 부분 산출물을 병합하여 최종 `impact-analysis.md` 작성 → 팀 해체 (`TeamDelete`)

## Agent A: 모듈/레이어 방향

```
근본 원인을 기준으로, 수직 방향으로 영향받는 코드를 추적하라.

network → bridge → webview → ViewController → Info.plist 순으로:
1. 이 원인이 다른 브리지 함수 또는 쿠키/세션 동기화 판단에 영향을 미치는가?
2. 같은 WebView 설정/헬퍼를 쓰는 다른 화면(ViewController/View)이 있는가?
3. 다른 모듈(module-registry의 다른 모듈)에 전파되는가?
4. 푸시 수신 경로 또는 딥링크 진입 흐름에도 영향이 있는가?

출력: 영향받는 파일:라인 목록 + 영향 내용

[root-cause.md]
[관련 모듈 코드]
[module-registry.yaml]
```

## Agent B: 호출자 방향

```
근본 원인의 코드를 호출하는 모든 경로를 역추적하라.

1. 이 함수/메서드를 호출하는 곳 (import/grep)
2. 웹(FE)에서 이 브리지 함수를 호출하는 경로 (bridge-contract.yaml 대조)
3. 딥링크 Universal Link·커스텀 스킴 또는 푸시 핸들러에서 호출되는 경우
4. ViewController 생명주기, WKNavigationDelegate 콜백, AppDelegate/푸시 핸들러 중 어디에 끼어 있는가
5. 테스트 커버리지 (이 코드를 커버하는 테스트 수)

출력: 호출 경로 목록 + 각 경로의 영향도

[root-cause.md]
[관련 모듈 코드]
```

## Agent C: 데이터 흐름 방향

```
근본 원인이 데이터 무결성에 미치는 영향을 분석하라.

1. 쿠키/세션 데이터 일관성 영향
2. 이미 잘못된 데이터가 쌓여 있을 가능성 (stale 쿠키·토큰·FCM 토큰)
3. SharedPreferences/앱 내부 저장소/WebView 스토리지에 stale 데이터가 있을 가능성
4. 메인 BE(hb-be) 또는 웹(FE)에 잘못된 데이터 전달 가능성
5. 브리지 계약 변경으로 웹 호출부 보정·형제 플랫폼(AOS) 반영이 필요한지 여부

출력: 데이터 영향 목록 + 보정 필요 여부

[root-cause.md]
[관련 모듈 코드]
[architecture.yaml]
```

## 메인: 병합

1. 3개 팀원이 작성한 부분 산출물을 Read한다:
   - `.harness/artifacts/maintenance/{identifier}/impact-layer.md`
   - `.harness/artifacts/maintenance/{identifier}/impact-caller.md`
   - `.harness/artifacts/maintenance/{identifier}/impact-dataflow.md`
2. 영향받는 코드/데이터 전체 목록을 통합한다.
3. 중복 제거 및 우선순위 부여.
4. 수정 시 연쇄 영향을 정리한다.
5. 병합 결과를 최종 `impact-analysis.md`로 저장한다.
6. 팀 해체: `SendMessage({type: "shutdown_request"})` → `TeamDelete`.

## 산출물: impact-analysis.md

```markdown
# 영향도 분석

## 요약
- 영향받는 모듈: {N}개
- 영향받는 파일: {N}개
- 쿠키/세션·저장 데이터 보정 필요: {있음|없음}
- 브리지 계약 변경 → 형제 플랫폼(AOS) 반영 필요: {있음|없음}
- 메인 BE·웹(FE) 연동 영향: {있음|없음}

## 모듈/레이어 영향
| 파일 | 영향 내용 | 심각도 |
|------|---------|--------|

## 호출자 영향
| 호출 경로 | 영향 내용 | 테스트 커버리지 |
|----------|---------|---------------|

## 데이터 흐름 영향
| 대상 | 영향 내용 | 보정 필요 |
|------|---------|----------|

## 수정 시 연쇄 영향
(이 버그를 수정하면 추가로 변경해야 할 곳)
```
