# 영향도 조사 — 병렬 탐색 (CM)

3개 방향에서 동시에 영향 범위를 탐색한다.
모듈/호출자/데이터 흐름을 동시에 훑어야 누락이 없다.

## 실행 방식

이 skill은 **Claude Code 네이티브 Teams**로 실행된다. 표준 절차는 `commands/shared/team-protocol.md` 참조.

### 팀 스펙

- `team_name`: `maint-impact-{identifier}` (예: `maint-impact-BUCCL-CM-42`)
- `description`: "영향도 3방향 병렬 탐색 (모듈/호출자/데이터흐름)"
- 팀원 3명 (모두 `subagent_type: general-purpose`, 병렬 스폰):

  | 팀원 이름 | 사용할 프롬프트 블록 | 산출 파일 |
  |----------|--------------------|----------|
  | `layer-tracer`    | 아래 "Agent A: 모듈/레이어 방향" | `.harness-artifacts/maintenance/{identifier}/impact-layer.md` |
  | `caller-tracer`   | 아래 "Agent B: 호출자 방향"     | `.harness-artifacts/maintenance/{identifier}/impact-caller.md` |
  | `dataflow-tracer` | 아래 "Agent C: 데이터 흐름 방향" | `.harness-artifacts/maintenance/{identifier}/impact-dataflow.md` |

- 메인: 3개 부분 산출물을 병합하여 최종 `impact-analysis.md` 작성 → 팀 해체 (`TeamDelete`)

## Agent A: 모듈/레이어 방향

```
근본 원인을 기준으로, 수직 방향으로 영향받는 코드를 추적하라.

Repository → Service → Controller → Route 순으로:
1. 이 원인이 다른 repository의 SQL/관계에 영향을 미치는가?
2. 같은 Service를 호출하는 다른 Controller가 있는가?
3. 다른 모듈(module-registry의 다른 모듈)에 전파되는가?
4. WebSocket 이벤트 핸들러(src/websocket/)에도 영향이 있는가?

출력: 영향받는 파일:라인 목록 + 영향 내용

[root-cause.md]
[관련 모듈 코드]
[module-registry.yaml]
```

## Agent B: 호출자 방향

```
근본 원인의 코드를 호출하는 모든 경로를 역추적하라.

1. 이 함수/메서드를 호출하는 곳 (import/grep)
2. Express 라우터에서 직접 호출하는 경로
3. Socket.io 이벤트 핸들러에서 호출하는 경우
4. 미들웨어 체인 어디에 끼어 있는가
5. 테스트 커버리지 (이 코드를 커버하는 테스트 수)

출력: 호출 경로 목록 + 각 경로의 영향도

[root-cause.md]
[관련 모듈 코드]
```

## Agent C: 데이터 흐름 방향

```
근본 원인이 데이터 무결성에 미치는 영향을 분석하라.

1. DB 데이터 일관성 영향
2. 이미 잘못된 데이터가 쌓여 있을 가능성
3. Redis 캐시에 stale 데이터가 있을 가능성
4. 메인 BE(hb-be) 또는 외부 시스템에 잘못된 데이터 전달 가능성
5. 데이터 보정 마이그레이션 필요 여부

출력: 데이터 영향 목록 + 보정 필요 여부

[root-cause.md]
[관련 모듈 코드]
[architecture.yaml]
```

## 메인: 병합

1. 3개 팀원이 작성한 부분 산출물을 Read한다:
   - `.harness-artifacts/maintenance/{identifier}/impact-layer.md`
   - `.harness-artifacts/maintenance/{identifier}/impact-caller.md`
   - `.harness-artifacts/maintenance/{identifier}/impact-dataflow.md`
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
- 데이터 보정 필요: {있음|없음}
- Redis 캐시 무효화 필요: {있음|없음}
- 메인 BE 연동 영향: {있음|없음}

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
