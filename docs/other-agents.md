# 다른 에이전트에서 hb 쓰기 (OpenClaw 등)

- 확인 상태(2026-10-15): hb는 Claude Code에서만 시운전했다. OpenClaw에서는 돌려 보지 않았다. 아래의 경로, 설정 이름, 도구 이름은 각 도구의 공식 문서(맨 아래 "근거")에서 옮겼다.
- 처음 쓸 때는 작은 버그 하나로 계획부터 검수까지 한 번 끝까지 돌려 보고, 막힌 곳을 이 문서에 더한다.
- Hermes Agent는 이 문서 대신 [hermes.md](hermes.md)를 본다.

## 이 문서를 읽는 AI에게

hb의 스킬 문서(`skills/*/SKILL.md`)는 몇 군데가 Claude Code의 말로 적혀 있다. 아래 "바꿔 읽기" 표대로 바꿔 읽고, 표에 없는 것은 문서에 적힌 그대로 따른다. 바꿀 방법이 없는 단계가 나오면 건너뛰지 말고 멈춘 뒤 사용자에게 알린다.

## 필요한 것

- 이 저장소 전체. 스킬은 `../../bin/hb.py`(검사 프로그램)와 `agents/*.md`(보조 AI 지침)를 함께 쓴다. 스킬 폴더만 따로 복사하면 이 둘을 찾지 못한다. 그래서 저장소를 한 곳에 받아 두고 스킬은 **제자리에서** 읽게 한다.
- Python 3(표준 라이브러리만)과 git.
- 일할 제품 저장소에 `.harness/docs/checks.json`(검사 계약), `.harness/README.md`(안내문), `.gitignore`의 `logs/`. 자세한 것은 README.

## 바꿔 읽기 (모든 에이전트 공통)

| 문서에 적힌 것 | 뜻 | 바꿔 하는 법 |
|---|---|---|
| `/hb:plan`, `/hb:dev`, `/hb:eval`, `/hb:review` | 스킬 `plan`, `dev`, `eval`, `review`를 부른다 | 그 에이전트의 스킬 부르는 법(아래 도구별 절) |
| "이 문서 폴더에서 두 단계 위의 `bin/hb.py`" | 검사 프로그램의 위치 | 그 에이전트가 알려 주는 스킬 폴더에서 두 단계 위가 이 저장소다 |
| "새 보조 AI `hb:implementer`" | 대화를 물려받지 않는 새 보조 AI에게 `agents/implementer.md`를 지침으로 주고 할 일 하나를 맡긴다 | 그 에이전트의 보조 AI(하위 에이전트) 기능. 지침 파일의 내용과 읽을 파일 경로를 함께 준다 |
| "새 보조 AI `hb:reviewer`"(읽기 도구만) | 위와 같고, 읽기만 한다(`agents/reviewer.md`) | 도구를 읽기만으로 줄일 수 있으면 줄인다. 못 줄이면 개발 문서의 "검토자를 부르기 전과 후에 세 명령의 출력이 같은지 본다"가 읽기만 했는지를 확인한다 |
| "새 창에서", "새 세션에서"(평가, 검수) | 앞의 대화를 모르는 새 세션 | 그 에이전트에서 새 세션을 연다 |
| "셸 도구의 제한 시간을 넉넉하게 주어 앞에서 돌린다" | 몇 분 걸리는 전체 검사를 끝까지 기다린다 | 명령마다 제한 시간을 검사 시간보다 길게 준다. 앞에서 못 기다리면 백그라운드로 돌리고 끝날 때까지 다음 단계로 가지 않는다 |
| "다른 플러그인의 skill을 부르지 않는다" | hb를 따르는 동안 다른 계획·개발·검토 스킬을 쓰지 않는다 | 같다 |

평가와 검수는 "새 눈"이 중요해서, 두 문서는 자동 메모를 끈 세션에서 하라고 한다. 그 에이전트가 세션을 시작할 때 앞 세션의 메모를 자동으로 읽고 이를 끌 수 없다면, 문서의 규칙대로 사용자에게 알리고, 사용자가 그대로 하라고 하면 메모를 판단 근거로 쓰지 않고 기록 첫머리에 그렇게 적는다. 도구별 절의 "메모"를 본다.

## Hermes Agent

[hermes.md](hermes.md)를 본다.

## OpenClaw

**설치**

1. 이 저장소를 한 곳에 받는다.
2. OpenClaw 설정의 `skills.load.extraDirs`에 이 저장소의 `skills` 폴더를 더한다. 예: `extraDirs: ["<이 저장소>/skills"]`.

   `openclaw skills install ./경로`는 작업 공간의 `skills/`에 설치하는 방식이라 `bin/hb.py`가 따라오지 않는다. 그 방식으로는 설치하지 않는다. 연결(심볼릭 링크)로 바깥 폴더를 가리키게 하려면 `skills.load.allowSymlinkTargets`가 필요하다. 샌드박스로 도는 실행은 복사본을 읽으므로 `bin/hb.py`를 못 찾을 수 있다.
3. `/skill plan`이 계획 문서를 여는지 본다. `extraDirs`는 우선순위가 가장 낮아서, 같은 이름의 스킬이 작업 공간 등에 있으면 그쪽이 먼저다.

**부르기**: `/skill plan <하고 싶은 일>`, `/skill dev <작업 이름>`, `/skill eval <작업 이름>`, `/skill review <작업 이름>`. `/plan`처럼 바로 부를 수도 있지만, 이름이 다른 명령과 겹치면 뒤에 숫자가 붙는다.

**바꿔 읽기**

- 스킬 폴더: `{baseDir}`, 또는 `skills_read`가 알려 주는 위치. 그 두 단계 위가 이 저장소다.
- 보조 AI: `sessions_spawn(task=…, context="isolated")`. `task`에 지침 파일의 내용과 읽을 파일 경로를 넣는다. 자식은 시작 파일 가운데 `AGENTS.md`만 받는다.
- 읽기만 하는 검토자: 호출마다 도구를 줄일 수는 없다. 설정에서 `exec`, `process`, `write`, `edit`, `apply_patch`를 막은 에이전트를 따로 두고 `agentId`로 부르거나, `tools.subagents.tools.deny`를 쓴다. 파일 도구만 끄는 것으로는 `exec`가 읽기 전용이 되지 않는다. 둘 다 못 하면 세 명령 비교로 확인한다.
- 긴 검사: `exec`의 `timeoutSeconds`(기본 1800초)를 검사 시간보다 길게 준다. 명령은 10초 뒤에 `process`로 넘어갈 수 있으니, 결과를 기다리게(`awaitResults: true`) 하거나 `process`로 끝날 때까지 본다.
- 새 세션: 평가와 검수는 새 세션(`/new`)에서 한다.
- 지침 파일: 작업 공간의 `AGENTS.md`는 매 세션, 실행 폴더의 `AGENTS.md`는 프로젝트 맥락으로 붙는다.
- 메모: 세션을 시작할 때 작업 공간의 `MEMORY.md`와 `USER.md`를 읽는다. 세션 하나만 빼는 방법은 문서에서 찾지 못했다(`agents.defaults.contextInjection: "never"`는 `AGENTS.md`까지 뺀다). 그래서 평가와 검수는 위의 규칙대로 사용자에게 알린 뒤 진행한다(알려진 한계).

## 그 밖의 에이전트

Agent Skills(`SKILL.md` + `name`, `description`)를 읽는 에이전트라면 같은 방식으로 쓸 수 있다. 확인할 것은 다섯 가지다.

1. 스킬을 복사하지 않고 제자리에서 읽게 할 수 있는가(그래야 `bin/hb.py`와 `agents/`를 찾는다)
2. 스킬 폴더의 위치를 알 수 있는가
3. 대화를 물려받지 않는 보조 AI를 부를 수 있는가(못 하면 구현과 검토를 각각 새 세션에서 한다)
4. 몇 분 걸리는 명령을 끝까지 기다릴 수 있는가
5. 새 세션이 앞 세션의 메모를 자동으로 읽는가

## 근거

- OpenClaw: [스킬](https://docs.openclaw.ai/tools/skills), [슬래시 명령](https://docs.openclaw.ai/tools/slash-commands), [스킬 CLI](https://docs.openclaw.ai/cli/skills), [exec](https://docs.openclaw.ai/tools/exec), [백그라운드 실행](https://docs.openclaw.ai/gateway/background-process), [하위 에이전트](https://docs.openclaw.ai/tools/subagents/tool-reference), [하위 에이전트 도구 정책](https://docs.openclaw.ai/tools/subagents/tool-policy), [작업 공간](https://docs.openclaw.ai/concepts/agent-workspace), [메모](https://docs.openclaw.ai/concepts/memory).
