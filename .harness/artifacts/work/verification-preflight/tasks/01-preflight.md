# 01 preflight 명령

- 완료 기준: C1–C8 (spec.md)
- 먼저 끝나야 하는 할 일: 없음
- 모양: `def cmd_preflight(ctx, args)`. 서브파서 `preflight`에 `--task`, `--aux`(여러 개), `--deadline`, `--margin`(기본 120).
  결과는 `{"verdict", "blocked", "outcome", "reuse"?, "review_paths"?, "time"?, "summary"}`.
- pytest 확인은 실행 중인 파이썬 기준(`importlib.util.find_spec("pytest")`). run_check가 `sys.executable -m pytest`를 쓰기 때문.
  테스트에서 pytest가 없는 상황은 `-c`로 sys.modules/meta_path를 막는 래퍼 같은 방식으로 만든다. 설치/삭제하지 않는다.
- 명령 확인은 `shutil.which(command[0])`.
- 재사용 판단은 기존 `snapshot(ctx)`와 green 기록의 `snapshot`/`paths`를 비교한다. 기록을 고치지 않는다.
- 테스트: `tests/test_hb_preflight.py`. 기존 `tests/test_hb.py`처럼 임시 git 저장소에 가짜 제품을 만들고 실제 hb.py를 subprocess로 부른다.
  pytest가 없으면 건너뛰는 묶음은 통과 근거로 쓰지 않는다(.harness/README.md).
- 지킬 것: 기존 판정·지문·안전 관문 변경 금지. preflight가 state.json, checks/, logs/를 만들지 않음.
