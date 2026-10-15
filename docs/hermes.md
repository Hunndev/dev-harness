# Hermes Agent에서 hb 쓰기

- 확인 상태(2026-10-15): Hermes Agent에서 직접 돌려 보지 않았다. 아래 내용은 Hermes Agent의 공식 문서와 소스 코드(커밋 `450ad50`)에서 확인했다(맨 아래 "근거"). Hermes가 바뀌면 이름이나 동작이 달라질 수 있다.
- 처음 쓸 때는 작은 버그 하나로 계획부터 검수까지 한 번 끝까지 돌려 보고, 막힌 곳을 이 문서에 더한다.

## 한눈에

창은 모두 제품 저장소 폴더에서 연다(`cd <제품 저장소>`). `<hb>`는 hb 저장소를 받아 둔 폴더의 절대 경로다. 첫 메시지는 단계마다 이 꼴이다.

```
<hb>/docs/hermes.md를 먼저 읽고, 그 규칙대로 <hb>/skills/<단계>/SKILL.md를 따라 해. <덧붙일 것>
```

| 단계 | 여는 창 | `<단계>` | `<덧붙일 것>` |
|---|---|---|---|
| 계획 | `hermes chat` | `plan` | 하고 싶은 일 |
| 개발 | `hermes chat` (계획과 같은 창이어도 된다) | `dev` | 작업 이름 |
| 평가 | 새 창 `hermes chat --ignore-rules` | `eval` | 작업 이름 |
| 검수 | 또 새 창 `hermes chat --ignore-rules` | `review` | 작업 이름 |

단계 문서에는 이 문서를 읽으라는 말이 없다. 그래서 첫 메시지에서 이 문서를 함께 읽게 한다. 첫 메시지는 창을 열면서 `hermes chat -q "…"`로 보내도 된다.

평가와 검수는 앞 세션을 모르는 "새 눈"으로 한다. Hermes는 세션을 시작할 때 `~/.hermes/memories/`의 `MEMORY.md`와 `USER.md`를 읽는다. `--ignore-rules`로 열면 이 메모와 저장소의 지침 파일(`AGENTS.md`, `CLAUDE.md` 등), 미리 불러 둔 스킬을 모두 빼고 시작한다.

## 사람이 할 준비 (한 번)

1. Hermes가 도는 컴퓨터에 hb 저장소 전체를 받는다. 이 문서 한 장만으로는 안 된다. 단계 문서(`skills/`), 보조 AI 지침(`agents/`), 검사 프로그램(`bin/hb.py`)을 함께 쓴다.

   ```bash
   git clone https://github.com/Hunndev/dev-harness.git <hb>
   ```

2. Hermes 설정(`~/.hermes/config.yaml`)의 `terminal.backend`가 `local`(기본값)인지 본다. docker 같은 컨테이너에서 명령이 돌면 그 안에서 `<hb>`와 제품 저장소가 보이지 않을 수 있다.
3. 제품 저장소에 `.harness/README.md`, `.harness/docs/checks.json`을 두고, `.gitignore`에 `logs/`를 넣는다(README의 "제품 저장소에 있어야 하는 것").

hb를 Hermes의 스킬로 등록하지 않는다(`skills.external_dirs`에 넣지 않는다). 이유는 둘이다.

- `/plan`과 `/review`는 Hermes에 원래 있는 명령이고, 같은 이름의 스킬보다 먼저 불린다. `/plan`은 `.hermes/plans/`에 Hermes의 계획을 쓰고, `/review`는 Hermes의 검토 보조 AI를 띄운다. 둘 다 hb가 아니다.
- Hermes는 등록된 스킬을 스스로 고칠 수 있다. 공식 문서에 따르면 `external_dirs`에 둔 스킬도 그 자리에서 고친다.

그래서 위 표처럼 문서 파일의 경로를 주고 따르게 한다.

## 이 문서를 읽는 Hermes에게

hb의 단계 문서(`<hb>/skills/*/SKILL.md`)는 몇 군데가 Claude Code의 말로 적혀 있다. 아래 표대로 바꿔 읽고, 표에 없는 것은 문서에 적힌 그대로 따른다. 바꿀 방법이 없는 단계가 나오면 건너뛰지 말고 멈춘 뒤 사용자에게 알린다.

**네 단계 모두, 시작할 때 저장소 맨 위의 `AGENTS.md`와 `CLAUDE.md`를 직접 읽고, 거기 적힌 금지 사항(비밀 파일을 열지 않기 등)을 지킨다.** Hermes는 지침 파일을 한 종류만 붙이고(`AGENTS.md`가 있으면 `CLAUDE.md`는 붙지 않는다), `--ignore-rules`로 연 창에는 하나도 붙이지 않는다. 이 둘은 저장소의 파일이므로 평가와 검수에서 읽어도 된다.

| 문서에 적힌 것 | Hermes에서 하는 법 |
|---|---|
| `/hb:plan`, `/hb:dev`, `/hb:eval`, `/hb:review` | 사용자가 경로를 준 단계 문서를 이 표와 함께 따른다 |
| "이 문서 폴더에서 두 단계 위의 `bin/hb.py`" | `<hb>/bin/hb.py` |
| "다른 계획·개발·검토 도구(다른 플러그인의 skill 포함)를 부르지 않는다" | Hermes의 `/plan`, `/review`와 다른 스킬을 쓰지 않는다 |
| "새 보조 AI `hb:implementer`" | `delegate_task(goal=…, context=…)`로 부른다. `context`에는 `<hb>/agents/implementer.md`를 먼저 읽고 따르라는 말, 단계, 할 일 본문의 경로, 테스트 명령을 넣는다. 자식은 앞의 대화를 모르는 새 대화로 시작한다 |
| "새 보조 AI `hb:reviewer`"(읽기 도구만) | 위와 같이 `<hb>/agents/reviewer.md`로 부른다. 자식은 부모의 도구를 그대로 물려받아서 읽기만으로 줄일 수 없다. 개발 문서의 "세 명령의 출력이 같은지 본다"로 읽기만 했는지 확인한다 |
| 보조 AI를 부르는 방식 | 한 번에 하나만 부르고, 결과를 받은 뒤 다음 단계로 간다 |
| "셸 도구의 제한 시간을 넉넉하게 주어 앞에서 돌린다" | `terminal`에 `timeout`을 꼭 준다(기본 180초). `hb.py` 명령에는 검사 계약의 `timeout_seconds`의 두 배에 300초를 더해 준다(`check --phase green`은 검사를 두 번 돌린다). 600초를 넘게 주면 Hermes가 그 명령을 백그라운드로 돌리고 끝나면 알린다. 그 명령을 다시 돌리지 않는다. 끝난 것을 알림이나 `process(action="poll", session_id=…)`로 확인하기 전에는 다음 단계로 가지 않는다. 판정은 출력의 마지막 줄이다 |
| 보조 AI가 돌리는 명령 | 공식 문서에 따르면 자식이 도구 하나에서 1200초를 넘기면 멈춘 것으로 보고 버린다. 보조 AI에게 주는 테스트 명령은 할 일의 테스트(`check_args`)로 좁히고, `terminal`에 `timeout`을 주라고 `context`에 적는다. 전체 검사는 지휘가 `hb.py`로 돌린다 |
| "새 창에서", "새 세션에서" | 사용자에게 새 `hermes chat`을 열라고 알린다. 평가와 검수는 `--ignore-rules`를 붙여 연다 |
| "자동 메모를 끈 세션에서 한다" | 시스템 프롬프트에 `MEMORY (your personal notes)`나 `USER PROFILE (who the user is)` 블록이 있으면 메모가 켜진 세션이다. 문서대로 멈추고, `--ignore-rules`를 붙여 새로 열라고 알린다 |
| "대화가 아니라 저장소에 남은 것만 읽는다"(평가) | `session_search`로 지난 세션을 찾지 않는다. 검수도 같다 |

- `<hb>` 안의 파일은 고치지 않는다.
- 진행 기록은 Hermes의 메모가 아니라 작업 폴더(`INDEX.md` 등)에 적는다.

## 알려진 한계

- 읽기만 하는 검토자를 도구 설정으로 강제할 수 없다. 세 명령 비교로 확인한다.
- `--ignore-rules`가 지난 세션 검색(`session_search`)까지 막는지는 확인하지 못했다. 위의 규칙으로 막는다.
- Hermes에서 실제로 돌려 본 적이 없다.

## 근거

- 공식 문서
  - [스킬](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills): 스킬 폴더의 우선순위, `external_dirs`에 둔 스킬도 그 자리에서 고침
  - [슬래시 명령](https://hermes-agent.nousresearch.com/docs/reference/slash-commands): `/plan`, `/review`, 이름이 같으면 내장 명령이 먼저
  - [CLI 명령](https://hermes-agent.nousresearch.com/docs/reference/cli-commands): `--ignore-rules`, `-q`
  - [위임](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation): `delegate_task`, 도구를 물려받음, 멈춤 감지(1200초)
  - [메모](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory), [지침 파일](https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files), [도구](https://hermes-agent.nousresearch.com/docs/user-guide/features/tools)(`terminal.backend`, `process`)
- 소스 코드(커밋 `450ad50`)
  - [`hermes_cli/commands.py`](https://github.com/NousResearch/hermes-agent/blob/450ad5055eb3c4852d96676ee99287d618bd283a/hermes_cli/commands.py#L156-L163): 내장 명령 `review`, `plan`
  - [`tools/terminal_tool.py`](https://github.com/NousResearch/hermes-agent/blob/450ad5055eb3c4852d96676ee99287d618bd283a/tools/terminal_tool.py#L76): 앞에서 기다리는 상한 600초. 넘으면 백그라운드로 돌리고 알림([L1064](https://github.com/NousResearch/hermes-agent/blob/450ad5055eb3c4852d96676ee99287d618bd283a/tools/terminal_tool.py#L1064-L1069)), 기본 제한 시간 180초([L753](https://github.com/NousResearch/hermes-agent/blob/450ad5055eb3c4852d96676ee99287d618bd283a/tools/terminal_tool.py#L753))
  - [`hermes_cli/cli_agent_setup_mixin.py`](https://github.com/NousResearch/hermes-agent/blob/450ad5055eb3c4852d96676ee99287d618bd283a/hermes_cli/cli_agent_setup_mixin.py#L688-L689): `--ignore-rules`가 지침 파일과 메모를 뺌
  - [`agent/system_prompt.py`](https://github.com/NousResearch/hermes-agent/blob/450ad5055eb3c4852d96676ee99287d618bd283a/agent/system_prompt.py#L716-L717): 지침 파일을 빼면 하나도 붙이지 않음
  - [`agent/agent_init.py`](https://github.com/NousResearch/hermes-agent/blob/450ad5055eb3c4852d96676ee99287d618bd283a/agent/agent_init.py#L1322): 메모를 뺀 세션은 `MEMORY.md`와 `USER.md`를 읽지 않음
  - [`tools/memory_tool_store.py`](https://github.com/NousResearch/hermes-agent/blob/450ad5055eb3c4852d96676ee99287d618bd283a/tools/memory_tool_store.py#L23): 메모 블록의 제목
