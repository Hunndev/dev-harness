# hb (새 판)

계획과 개발, 두 가지만 하는 개발 하네스입니다. AI는 한 번에 하나만 씁니다.

- **계획**: 설명서를 먼저 쓰고, 완료 기준에 번호를 붙이고, 작은 할 일로 나눠 승인받습니다.
- **개발**: 할 일마다 테스트를 먼저 쓰고 구현합니다. 통과 여부는 작은 프로그램이 직접 검사를 돌려 판정합니다.

제품마다 다른 정보(규칙, 검사 명령, 기록)는 그 저장소의 `.harness` 폴더에 둡니다. 이 폴더에는 제품 정보가 없습니다.

## 들어 있는 것

```
.claude-plugin/plugin.json   Claude Code가 읽는 이름표
skills/plan/SKILL.md         계획 문서
skills/dev/SKILL.md          개발 문서
agents/implementer.md        구현자 지침
agents/reviewer.md           검토자 지침 (읽기 도구만)
bin/hb.py                    작은 프로그램 (Python 표준 라이브러리만)
tests/test_hb.py             프로그램의 테스트 (pytest 쪽)
tests/test_hb_jest.py        프로그램의 테스트 (jest 쪽)
tests/test_hb_gradle.py      프로그램의 테스트 (gradle 쪽)
tests/test_hb_xcodebuild.py  프로그램의 테스트 (xcodebuild 쪽)
```

## 쓰는 법 (Claude Code)

설치하지 않고 이 폴더를 불러옵니다.

```bash
cd <제품 저장소>
claude --plugin-dir <이 폴더의 경로>
```

세션 안에서 `/hb:plan`으로 계획을, `/hb:dev`로 개발을 시작합니다.

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

## 프로그램의 테스트

pytest가 깔린 파이썬으로 돌립니다(가짜 제품을 만들어 진짜 pytest로 검사합니다). jest, gradle, xcodebuild 쪽은 같은 모양의 결과를 내는 가짜 실행기로 검사하므로 Node, JDK, Android SDK, Xcode가 없어도 됩니다.

```bash
<파이썬> -m unittest discover -s tests
```

## 이번 판에 없는 것

Codex 입구, 검수와 평가 도구, 코드 정리와 손으로 확인하는 할 일, 결제·권한·데이터를 건드리는 일의 추가 확인, 끊긴 뒤 자동 대조, 횟수 자동 집계. 이것들은 문서의 절차로 대신하며, 실제로 막히면 그때 만듭니다.
