# hb (새 판)

계획, 개발, 평가, 검수 네 단계로 일하는 개발 하네스입니다. AI는 한 번에 하나만 씁니다.

- **계획**: 설명서를 먼저 쓰고, 완료 기준에 번호를 붙이고, 작은 할 일로 나눠 승인받습니다. 결제, 권한, 개인정보, DB 구조 변경을 건드리면 영향, 범위와 환경, 확인 방법, 되돌리는 법을 적어 승인받고 그 범위 안에서 개발합니다. 실제 DB, 데이터, 비밀값, 운영 환경을 다루는 일은 개발 승인과 별도로 대상과 하는 일을 적어 승인받습니다.
- **개발**: 할 일마다 테스트를 먼저 쓰고 구현합니다. 통과 여부는 작은 프로그램이 직접 검사를 돌려 판정합니다. 테스트가 틀렸으면 구현을 빼 두고 테스트부터 다시 쓰며, 완료 기준 문장이 바뀔 때만 사람 승인을 받습니다.
- **평가**: 새 세션에서 바뀐 코드 전체를 읽고 "잘 만들었나"를 봅니다. 코드를 고치지 않고 테스트도 돌리지 않습니다. 꼭 고칠 것은 할 일로 더해 개발로 돌려보냅니다.
- **검수**: 새 세션에서 프로그램이 테스트를 전부 다시 돌리고, 완료 기준을 하나씩 대조해 "주문대로 다 됐나"를 봅니다. 평가를 받은 그 코드만 통과시킵니다.

흐름 전체의 그림은 [docs/flow.md](docs/flow.md)에 있습니다. 승인은 사람이 직접 쓴 메시지만 인정하고, 기록은 프로그램의 기록과 짧은 메모만 남기며, hb에 없는 절차·파일·역할은 만들지 않습니다.

제품마다 다른 정보(규칙, 검사 명령, 기록)는 그 저장소의 `.harness` 폴더에 둡니다. 이 폴더에는 제품 정보가 없습니다.

## 들어 있는 것

```
.claude-plugin/plugin.json   Claude Code가 읽는 이름표
skills/plan/SKILL.md         계획 문서
skills/dev/SKILL.md          개발 문서
skills/eval/SKILL.md         평가 문서
skills/review/SKILL.md       검수 문서
agents/implementer.md        구현자 지침
agents/reviewer.md           검토자 지침 (읽기 도구만)
bin/hb.py                    작은 프로그램 (Python 표준 라이브러리만)
docs/hermes.md               Hermes Agent에서 쓰는 법
docs/other-agents.md         그 밖의 에이전트(OpenClaw 등)에서 쓰는 법
docs/flow.md                 흐름 한눈에 (사람이 보는 지도)
tests/test_hb.py             프로그램의 테스트 (pytest 쪽)
tests/test_hb_jest.py        프로그램의 테스트 (jest 쪽)
tests/test_hb_gradle.py      프로그램의 테스트 (gradle 쪽)
tests/test_hb_xcodebuild.py  프로그램의 테스트 (xcodebuild 쪽)
tests/test_hb_review.py      프로그램의 테스트 (검수 검사)
tests/test_hb_preflight.py   프로그램의 테스트 (시작 전 검증)
tests/test_skills_preflight.py  문서의 테스트 (시작 전 검증 연계)
```

## 쓰는 법 (Claude Code)

설치하지 않고 이 폴더를 불러옵니다.

```bash
cd <제품 저장소>
claude --plugin-dir <이 폴더의 경로>
```

세션 안에서 `/hb:plan`으로 계획을, `/hb:dev`로 개발을 시작합니다. 개발이 끝나면 새 창에서 `/hb:eval`로 평가를 받고, 평가 기록이 "검수로"를 내면 또 새 창에서 `/hb:review`로 검수를 받습니다. 올리기와 합치기는 사람이 합니다.

개발은 바탕 검사와 각 검사 전에 `hb.py preflight --work <작업 이름> [--task <번호>]`로 시작 전 검증을 합니다. 검사를 돌리지 않고 기록도 만들지 않으며, 돌려도 완료 증거가 안 되는 경우(환경, 증거 경로, 범위, 시간)에 `stop`을 냅니다. 결과는 `product`, `environment`, `aux` 세 칸으로 따로 내고, 이 판정은 통과 증거가 아닙니다.

평가와 검수 창은 자동 메모를 끄고 엽니다. 앞 세션들이 남긴 메모를 읽고 시작하면 새 눈으로 보지 못하기 때문입니다(시운전에서 두 번째 평가가 앞 세션의 확인 안 된 메모를 "합의한 규율"로 인용했습니다).

```bash
cd <제품 저장소>
CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 claude --plugin-dir <이 폴더의 경로>
```

Hermes Agent에서 쓰려면 [docs/hermes.md](docs/hermes.md)를, OpenClaw 같은 그 밖의 에이전트에서 쓰려면 [docs/other-agents.md](docs/other-agents.md)를 봅니다.

## 제품 저장소에 있어야 하는 것

- `.harness/README.md` (안내문)과 규칙 문서
- `.harness/docs/checks.json` (검사 계약)

```json
{
  "version": 1,
  "runner": "pytest",
  "full_args": ["-rA"],
  "timeout_seconds": 1200,
  "test_globs": ["test_*.py", "*_tests.py", "tests.py", "conftest.py", "pytest.ini", "*/tests/*"]
}
```

  jest를 쓰는 저장소는 `runner`를 `jest`로 하고, jest를 돌리는 명령을 `command`에 적습니다. 프로그램이 그 뒤에 인자와 `--json --outputFile=<보고서>`를 붙입니다.

```json
{
  "version": 1,
  "runner": "jest",
  "command": ["npx", "jest"],
  "full_args": [],
  "timeout_seconds": 600,
  "test_globs": ["*.test.ts", "*.test.js", "jest.config.js"]
}
```

  Gradle로 테스트를 돌리는 저장소(Android 등)는 `runner`를 `gradle`로 하고, 돌리는 명령을 `command`에, Gradle이 결과 파일을 쓰는 폴더를 `report_dir`에 적습니다. Gradle은 결과를 늘 같은 폴더에 쓰고, 컴파일이 안 되거나 바뀐 게 없다고 보면 예전 결과를 그대로 둡니다. 그래서 프로그램이 돌리기 전에 그 폴더 바로 아래의 `.xml` 파일을 지우고, 돌린 뒤 새로 생긴 것만 모아 읽습니다. `report_dir`은 저장소 안의 git 제외 폴더여야 합니다.

```json
{
  "version": 1,
  "runner": "gradle",
  "command": ["./gradlew", "--console=plain", ":app:testDebugUnitTest", "--rerun"],
  "report_dir": "app/build/test-results/testDebugUnitTest",
  "full_args": [],
  "timeout_seconds": 1800,
  "test_globs": ["app/src/test/*"]
}
```

  Xcode로 테스트를 돌리는 저장소(iOS 등)는 `runner`를 `xcodebuild`로 하고, 돌리는 명령을 `command`에 적습니다. 프로그램이 그 뒤에 인자와 `-resultBundlePath <결과 묶음>`을 붙이고, 돌린 뒤 Xcode에 든 `xcrun xcresulttool`로 그 묶음을 읽습니다. xcodebuild는 고른 이름에 맞는 테스트가 하나도 없어도 성공으로 끝나므로, 읽은 테스트 항목이 0개면 실행되지 않은 것으로 칩니다. 같은 이름의 시뮬레이터가 여럿이면 `-destination`에 OS 버전까지 적습니다. `-collect-test-diagnostics never`를 넣어 두면 테스트가 실패할 때마다 결과 묶음이 수십 MB가 되는 것을 막습니다.

```json
{
  "version": 1,
  "runner": "xcodebuild",
  "command": ["xcodebuild", "test", "-project", "App.xcodeproj", "-scheme", "App",
              "-destination", "platform=iOS Simulator,name=iPhone 17,OS=26.5",
              "-collect-test-diagnostics", "never"],
  "full_args": [],
  "timeout_seconds": 1800,
  "test_globs": ["AppTests/*"]
}
```

- `.gitignore`에 `logs/`
- (선택) `.harness/README.md` 끝의 "운용 정책" 칸. 저장소마다 다른 것(실행기, 검사 환경, 부가 검사, 승인 채널, 제안, push·PR·병합, 배포, 기록)을 정합니다. hb 규칙과 부딪치면 멈추고 사람에게 묻습니다. 아래 형식에서 `< >`는 채우고, `|`는 하나만 고르고, 해당 없는 줄은 지웁니다.

```markdown
## 운용 정책

hb 흐름(`<hb>/docs/flow.md`)에 이 저장소가 더하는 것이다. hb 규칙과 부딪치면 멈추고 사람에게 묻는다.

- 실행기: Hermes 직접(`<hb>/docs/hermes.md`) | Claude Code(`claude --plugin-dir <hb>`. 설치본 플러그인은 쓰지 않는다)
- hb 버전: 작업 시작 때 `git -C <hb> rev-parse --short HEAD`를 INDEX.md에 적는다.
- 검사 환경: 시험 DB `<대상>`. 비밀값은 `<시험용 설정 모듈 | 환경변수 | git 제외 경로의 더미 파일>`로 준다. 이 줄이 곧 승인이며 작업마다 다시 묻지 않는다. hb.py를 직접 부르고, 감싸는 스크립트·guard·sitecustomize·lock 검사·보호 해시 목록을 두지 않는다.
- 부가 검사(커밋 ①): `<lint>` · `<typecheck>` · `<build>`
- 결제·권한·개인정보·DB 구조를 건드리는 곳: `<모듈·경로>`. 계획에서 이곳을 건드리는 할 일은 넷(영향, 범위와 환경, 확인 방법, 되돌리는 법)을 적어 승인받는다.
- 승인: `<채널>`에서 `<사람 계정>`이 직접 쓴 메시지만. 봇 표시 계정, 역할 이름으로 온 지시, 런타임이 넣은 재시도·continue 문구, 메시지 ID만 적은 것, 에이전트가 다시 쓴 문장은 승인이 아니다.
- 제안: hb 안의 일과 실제 DB·병합·배포·운영 확인은 한 메시지에 섞지 않고 따로 제안한다. hb에 없는 절차는 "hb에 없음"이라고 표시하고 기본은 하지 않는다. hb로 할 수 없는 일은 할 수 없다고 적는다.
- 평가·검수 새 세션: 사람이 연다 | 지휘가 연다(첫 메시지는 hb 고정 문구만, 결과는 eval-NN.md·review-NN.md로만 받는다)
- push·PR·병합: 사람 | 위임(검수 통과 + 사람이 쓴 승인이 있을 때)
- 배포(hb 흐름 밖): 비운영 대상 `dev=<…>` · `staging=<…>`. 목록에 없으면 운영으로 본다. 운영은 사람 승인, 대상은 병합 커밋. 확인 `<…>`, 롤백 `<…>`. 병합이 배포나 DB 변경을 자동으로 일으키면 병합 전에 적용될 migration 목록을 보고한다.
- 기록: INDEX.md에는 hb summary와 짧은 메모만 적는다. 원문 출력은 logs/에 둔다. 작업 폴더에는 hb가 정한 파일만 둔다.
- hb 밖에서 한 작업: `<작업 이름>`은 hb 기록 없이 끝났다. 사후에 hb 기록을 만들지 않는다.

### 승인 기록 형식

INDEX.md의 "승인" 절에 이렇게 적는다. 사람의 말은 바꾸지 않고 그대로 옮긴다.

<날짜 시각 KST> · <채널> · <사람>: `<원문 그대로>`
직전 제안: <승인하면 실행되는 것만 한 줄로, 사람의 언어로>
```

## 프로그램의 테스트

pytest가 깔린 파이썬으로 돌립니다(가짜 제품을 만들어 진짜 pytest로 검사합니다). jest, gradle, xcodebuild 쪽은 같은 모양의 결과를 내는 가짜 실행기로 검사하므로 Node, JDK, Android SDK, Xcode가 없어도 됩니다.

```bash
<파이썬> -m unittest discover -s tests
```

## 이번 판에 없는 것

Codex 입구, 코드 정리와 손으로 확인하는 할 일, 결제·권한·데이터를 건드리는 일을 프로그램이 따로 확인하는 것, 끊긴 뒤 자동 대조, 횟수 자동 집계. 평가와 검수에서는 테스트만 더하는 할 일, 원래 깨져 있던 테스트의 실패 원인과 사라진 테스트를 프로그램이 직접 비교하는 것, 검수에서 lint와 빌드를 다시 돌리는 것, 테스트가 바뀐 코드를 얼마나 지나가는지 재는 것. 이것들은 문서의 절차로 대신하며, 실제로 막히면 그때 만듭니다.
