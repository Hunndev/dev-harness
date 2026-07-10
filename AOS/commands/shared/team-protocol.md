# Team 실행 프로토콜 (Claude Code 네이티브 Teams)

커맨드에서 "**Agent Team**" 또는 "(Team) ★" 표시가 있는 스텝은 **Claude Code 네이티브 Teams**로 실행한다.
`Agent` 툴 단독 병렬 호출과 구분됨 — 네이티브 Teams는 tmux 패널에 팀원이 가시화되고, 팀원끼리 `SendMessage`로 조율할 수 있다.

## 사전 조건

- `~/.claude/settings.json`에 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
- `teammateMode: "tmux"` (tmux 가시화용, 선택)

## 표준 절차

### 1. 팀 생성 — `TeamCreate`

- `team_name`: `{track}-{skill}-{identifier}` 형식
  - 예: `planning-alt-plan-20260411-multi-tenant`, `maint-impact-BUCCL-42`, `maint-regression-maint-20260410-review`
  - 재실행 시 충돌하면 `-r2`, `-r3` 접미어
- `description`: 1-2줄 요약

### 2. 팀원 스폰 — `Agent` 툴 **병렬** N회

**⚠️ 병렬 실행 필수 조건**: N개의 `Agent` 호출을 **단일 응답(메시지) 안에 여러 tool_use 블록으로 동시에** 발행해야 한다.
응답을 나눠 Agent를 하나씩 호출하면 **순차 실행**이 되어 병렬의 이점이 사라진다.

```
✅ 올바른 병렬 호출 (한 응답에 tool_use 3개)
   응답:
     Agent(name="tech-analyst", ...)
     Agent(name="ux-analyst", ...)
     Agent(name="cost-analyst", ...)

❌ 순차 호출 (응답 분리)
   응답 1: Agent(name="tech-analyst", ...)
   응답 2: Agent(name="ux-analyst", ...)
   응답 3: Agent(name="cost-analyst", ...)
```

각 호출에 공통:
- `team_name`: 1단계에서 만든 이름
- `name`: 팀원 이름 (스킬 문서가 지정하는 역할명)
- `subagent_type`: `general-purpose` (특수 역할이 필요하지 않으면 기본값)
- `prompt`: 아래 "팀원 프롬프트 템플릿"을 채운 전문

`TeamCreate`는 Agent 스폰보다 **먼저** 실행되어야 한다 (team_name이 등록돼야 팀원이 가입 가능). 따라서 실행 순서는:
1. **응답 A**: `TeamCreate` 1회
2. **응답 B**: `Agent` × N개를 한 응답에 동시 발행 (병렬 스폰)

### 3. 산출물 규칙 (중요)

팀원은 **결과를 채팅 메시지로 돌려주지 말고 지정된 파일에 직접 쓴다.**
동시 쓰기 충돌을 피하기 위해 팀원별 파일명을 분리한다.
- 예: `alternatives-tech.md`, `alternatives-ux.md`, `alternatives-cost.md`
- 메인은 이 부분 파일들을 읽어 최종 파일(`alternatives.md` 등)로 병합한다.

### 4. 완료 대기

- 팀원이 턴을 마치면 idle 알림이 메인에 자동 전달된다.
- 모든 팀원이 담당 파일을 생성했는지 메인이 확인한다.
- 누락/불완전하면 해당 팀원에게 `SendMessage`로 후속 지시 (팀은 유지).

### 5. 병합

메인이 각 부분 산출물을 읽고 최종 파일을 작성한다.
관점 간 충돌/모순은 최종 파일에 명시하고 사용자에게 판단을 요청한다.

### 6. 정리

1. 모든 팀원에게 `SendMessage({type: "shutdown_request"})` 전송
2. 모든 팀원이 종료된 것을 확인
3. `TeamDelete` 호출
4. 잔존 시 강제 정리: `rm -rf ~/.claude/teams/{team_name} ~/.claude/tasks/{team_name}`

## 팀원 프롬프트 템플릿

```
당신은 `{team_name}` 팀의 `{member_name}` 입니다.

## 과제
{이 팀원의 고유 과제 — 각 스킬 문서의 "Agent A/B/C" 블록 프롬프트 본문}

## 입력 (직접 Read로 열 것)
- {파일 경로 1}
- {파일 경로 2}
- ...

## 출력
- 작성 대상 파일 (절대 경로): `{팀원별 분리된 경로}`
- 완료 후 채팅으로는 `done: {작성 파일 경로}` 한 줄만 답장.
- 요약·해설 금지. 결과는 파일에만 남긴다.

## 범위 제약
- 본인 담당 관점 외(다른 팀원의 관점)는 평가하지 않는다.
- 다른 팀원의 파일은 읽지도 쓰지도 않는다.
```

## Fallback

Teams 기능이 비활성화됐거나 tmux가 없는 환경에서는 `Agent` 툴 병렬 호출로 대체 가능.
가시화는 없지만 **산출물 파일 분리 + 메인 병합** 원칙은 동일하게 유지한다.
