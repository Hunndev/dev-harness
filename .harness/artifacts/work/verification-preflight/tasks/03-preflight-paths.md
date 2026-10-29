# 03 preflight 경로 해석 (bug)

- 맡은 완료 기준: C2, C4 (spec.md)
- 먼저 끝나야 하는 할 일: 01
- 출처: 검수 01 뒤의 Codex native review(P2 두 건)와 Claude 일반 review #4. 감독 지시로 더함.

## 지적 그대로
1. **C4 --aux 정규화.** `allowed_files`에 `tools/*` 같은 glob이 있으면 `--aux tools/../app.py`가 fnmatch로 그대로 맞아 범위 검사를 통과한다. 실제 대상은 `app.py`(범위 밖)다. 반대로 `allowed_files=["app.py"]`일 때 `--aux ./app.py`나 저장소 안의 절대 경로는 같은 파일인데 범위 밖으로 막힌다.
   기대: `--aux` 경로를 저장소 기준 상대 경로로 정리한 뒤 `outside_allowed`에 넘긴다. 정리한 결과가 저장소 밖(`..`로 시작하거나 저장소 밖 절대 경로)이면 `blocked.scope`에 그 경로를 적고 막는다.
2. **C2 상대 PATH.** 비pytest runner의 `command[0]`이 경로 구분자 없는 이름이고 PATH에 상대 항목(예: `node_modules/.bin`)이 있으면, `shutil.which`는 hb를 부른 현재 폴더 기준으로 찾는다. 실제 `run_check`는 `cwd=ctx.repo`로 돈다. 그래서 저장소에만 있는 명령이 없다고 막히거나, 부른 폴더에만 있는 명령이 있다고 나온다.
   기대: PATH의 상대 항목을 `ctx.repo` 기준으로 풀어 찾는다. 절대 항목은 그대로.

## 모양
- `cmd_preflight`의 `--aux` 처리, `environment_problems`의 명령 찾기만 고친다. 작은 도우미 함수를 둘 수 있다.
- 테스트는 새 파일 `tests/test_hb_preflight_paths.py`. `tests/test_hb_preflight.py`처럼 임시 git 저장소의 가짜 제품과 실제 hb.py subprocess로 확인한다. PATH 테스트는 hb를 저장소가 아닌 cwd에서 부른다.

## 지킬 것
- 기존 판정·지문·안전 관문과 다른 명령(baseline/check/done/review)을 바꾸지 않는다. 기존 테스트 파일을 고치지 않는다.
- 이번에 안 할 것: 일반 review의 나머지 지적(#1·#2·#10 product 정의, #3 green 두 번 실행 시간, #5·#6 커밋 뒤 reuse, #7 음수 margin, #8 명령 공용화, #9 Stop 출력 모양). INDEX.md에 기록만 한다.
