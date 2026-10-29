# 02 skills와 README 연계

- 완료 기준: C9 (spec.md)
- 먼저 끝나야 하는 할 일: 01 (preflight의 출력 이름을 그대로 쓴다)
- 고칠 곳: skills/dev (baseline·check 전 preflight, `stop`이면 시작 안 함, 세 칸 따로 보고, 권장 승격 금지, 보조검증 범위 밖이면 멈추고 경로 변경 보고),
  skills/plan (9번 뒤 preflight로 환경 확인), skills/eval·review (`product`만 완료 증거, `aux: incomplete`/`environment: blocked`는 통과 아님), README 명령 설명.
- 테스트: `tests/test_skills_preflight.py`가 각 문서에 위 문장의 핵심 낱말(`preflight`, `product`, `aux`, `environment`, "권장")이 있는지 본다.
- 기존 문장의 규칙을 완화하지 않는다.
