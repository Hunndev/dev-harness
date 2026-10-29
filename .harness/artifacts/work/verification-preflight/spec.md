# 설명서: 시작 전 검증(preflight)과 결과 구분

상태: 확정 (승인 기록은 INDEX.md)

재발방지 세 가지(approved-task.md 범위 1–3)를 한 기능 `hb.py preflight`와 skills 연계로 만든다.

## 들어가고 나오는 것
- 새 명령: `hb.py preflight --work <이름> [--task <id>] [--aux <경로> ...] [--deadline <UTC ISO 8601>] [--margin <초, 기본 120>]`
- 출력: 기존 명령과 같은 JSON 한 줄.
  - `verdict`: `ok` 또는 `stop`(아래 `blocked`가 하나라도 있으면 `stop`).
  - `blocked`: 종류별 이유 목록. 빈 종류는 빼고 낸다. 종류: `environment`, `evidence`, `scope`, `time`.
  - `outcome`: 세 칸을 따로 낸다. 하나로 합치지 않는다.
    - `product`: `pass`(그 할 일의 green 기록이 ok) / `not_run`(기록 없음) / `fail`(기록이 ok 아님). `--task`가 없으면 `not_run`.
    - `environment`: `ok` / `blocked`.
    - `aux`: `none`(`--aux` 없음) / `incomplete`(`--aux`가 있음. preflight는 보조검증을 끝났다고 판정하지 않는다).
  - `reuse`(`--task`가 있고 green 기록이 ok일 때만): `same_source`(지금 스냅숏이 green 기록과 같음) 또는 `changed`와 바뀐 경로 목록 `review_paths`.
  - `time`(`--deadline`이 있을 때): `remaining_seconds`, `needed_seconds`(= 계약의 `timeout_seconds` + margin).
- 검사를 돌리지 않는다. state.json, checks/, logs/를 만들거나 고치지 않는다. baseline/check/done/review 판정은 그대로다.

## 왜, 성공을 어떻게 아는지
실제 호출 전에 (1) 돌려도 완료 증거가 안 되는 경로, (2) 할 일 범위를 넘는 보조검증, (3) 시간 안에 결과를 회수할 수 없는 경우를 막고, 제품 통과·환경 차단·보조검증 미완을 섞지 않고 보고한다.

## 완료 기준
- C1. runner가 pytest인데 hb.py를 실행한 파이썬에서 pytest를 찾을 수 없으면 `stop`, `blocked.environment`에 이유, `outcome.environment`는 `blocked`. — 행동 테스트(pytest 찾기를 막은 실행).
- C2. runner가 pytest가 아니고 `command[0]`을 실행 경로에서 찾을 수 없으면 `stop`, `blocked.environment`. — 행동 테스트(jest 계약, 없는 명령).
- C3. 작업 폴더의 `logs/`가 git 제외가 아니면 `stop`, `blocked.evidence`(이 경로로 낸 결과는 완료 증거가 될 수 없음). — 행동 테스트.
- C4. `--aux`로 준 경로 가운데 `--task`의 `allowed_files` 밖인 것이 있으면 `stop`, `blocked.scope`에 그 경로와 "경로 변경 필요"를 적는다. `--task` 없이 `--aux`를 주면 `stop`, `blocked.scope`. — 행동 테스트 두 개.
- C5. `--deadline`이 있고 (deadline − 지금) < `timeout_seconds` + margin이면 `stop`, `blocked.time`; 여유가 있으면 time은 막지 않는다. — 행동 테스트 두 개(지난 시각, 먼 미래).
- C6. `outcome`의 세 칸이 따로 나온다: 제품 green ok + `--aux` 있음 → `product: pass`, `aux: incomplete`. `aux`가 `incomplete`여도 `product`는 바뀌지 않고, `product`가 `pass`여도 `environment`가 `blocked`면 `verdict`는 `stop`. — 행동 테스트(green까지 실제 hb로 만든 뒤 preflight).
- C7. green 기록 뒤 소스가 같으면 `reuse: same_source`, 파일을 바꾸면 `changed`와 그 파일이 `review_paths`에 나온다. — 행동 테스트.
- C8. preflight 실행 뒤 state.json의 내용과 작업 폴더의 checks/, logs/ 파일 목록이 실행 전과 같다. — 행동 테스트.
- C9. skills/dev/SKILL.md가 baseline과 각 check 전에 `preflight`를 돌리고 `stop`이면 검사를 시작하지 않는다고 적고, 세 칸을 따로 보고하며 "권장" 지적을 필수로 올리지 않는다고 적는다. skills/plan은 계획 끝에 preflight로 환경을 확인한다고, skills/eval과 skills/review는 `product`만 완료 증거로 읽고 `aux: incomplete`나 `environment: blocked`를 통과로 읽지 않는다고 적는다. README의 명령 설명에 preflight가 있다. — 문서 내용 테스트(`tests/test_skills_preflight.py`).

## 제약
표준 라이브러리만. 기존 `Stop`과 출력 모양, `snapshot`, `outside_allowed`를 재사용한다. 기존 테스트와 기존 판정, 지문, 안전 관문을 고치지 않는다. 설치, 전역 설정, push 없음.

## 이번에 안 할 것
보조검증을 실제로 실행하거나 완료로 판정하는 일. 기존 PASS를 preflight 판정으로 대체하는 일. 결제·권한·개인정보·DB 해당 없음.

## 예외 상황
- `--deadline` 형식이 틀리면 `stop`, reason "deadline 형식이 틀림", `blocked` 없음.
- `--task`의 id가 tasks.json에 없으면 기존 `ctx.task`와 같은 문구로 `stop`.
- state.json이 없으면 `product`는 `not_run`, `reuse`는 내지 않는다(멈추지 않는다).
- 여러 종류가 동시에 막히면 모두 `blocked`에 적고 `stop` 하나를 낸다.

## 기존 결정과 대조
README "이번 판에 없는 것"의 "횟수 자동 집계", "끊긴 뒤 자동 대조"와 부딪치지 않는다(preflight는 기록을 읽기만 한다). 충돌 없음.
