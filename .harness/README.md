# 하네스 자체 개발 안내

이 저장소(hb 하네스)를 hb 절차로 고칠 때 쓰는 최소 계약이다. 사용자가 B 경로로 승인했다.

- 검사 계약: `docs/checks.json` (runner pytest, `tests/` 전체).
- `bin/hb.py`는 자신을 실행한 파이썬으로 `-m pytest`를 돌린다. 그래서 pytest가 이미 깔린 파이썬으로 실행한다. 설치하지 않는다.
  pytest가 없는 파이썬에서는 `tests/test_hb.py`의 묶음이 건너뛰어지므로, 그 결과를 통과로 치지 않는다.
- 별도 규칙 문서는 없다. 저장소 `README.md`의 원칙(표준 라이브러리만, 기존 판정과 안전 관문 유지)을 따른다.
- 작업 기록은 `artifacts/work/<작업 이름>/`에만 쓴다. `logs/`는 git에 넣지 않는다.
