# hb 흐름 한눈에

사람이 보는 지도입니다. 규칙의 원본은 `skills/*/SKILL.md`이고, 이 문서와 다르면 스킬 문서가 맞습니다. 에이전트는 이 문서를 새로 쓰거나 고치지 않습니다.

모양: `{ }` 사람 · `[[ ]]` hb·git이 판정하고 기록 · `[ ]` AI(지휘·구현자·검토자·평가자·검수자) · 점선은 되돌아가는 길

평가와 검수는 사람이 새 세션을 열어 시작합니다. 저장소의 운용 정책(`.harness/README.md`)에서 지휘에게 맡길 수 있습니다.

## 단계

```mermaid
flowchart TD
  P["계획<br/>spec · 완료 기준 · 할 일"] --> A{"사람 승인"}
  A -.->|"반려"| P
  A -->|"승인"| S[["작업 브랜치 · 계획 커밋<br/>hb preflight"]]
  S --> D["개발<br/>할 일마다 아래 사이클"]
  D -->|"모든 할 일 커밋"| E["평가<br/>새 세션 · 메모 off<br/>읽기만, 테스트는 안 돌림"]
  E -->|"검수로"| R["검수<br/>또 새 세션 · 메모 off<br/>hb review → 완료 기준 대조"]
  R -->|"기준 충족"| Z(["검수 통과"])
  R -->|"사람 확인 항목"| H{"사람 확인"}
  H -->|"일치"| Z
  Z --> M{"push · PR · 병합"}

  E -.->|"구현 오류 → 할 일 추가"| D
  E -.->|"질문 · 범위 밖 · 필수 테스트 누락"| A
  R -.->|"평가 뒤 바뀐 것 있음"| E
  R -.->|"코드 문제 → 할 일 추가"| D
  H -.->|"불일치 → 할 일 추가"| D
```

## 할 일 하나 (개발)

구현 검토는 모든 할 일에 합니다. 테스트가 틀리면 구현은 logs에 빼 두고 되돌린 뒤 1부터 다시 합니다. 1~3에서는 빼 둔 구현을 보지 않습니다. 완료 기준 문장이 바뀔 때만 사람 승인을 받습니다.

```mermaid
flowchart TD
  S0[["시작 · 작업에 한 번<br/>hb preflight<br/>hb baseline<br/>state.json 있으면 생략"]] --> T1
  T1["1 테스트 쓰기<br/>새 구현자 · 빈 뼈대까지"] --> T2[["2 실패 확인<br/>hb preflight<br/>hb check --phase red"]]
  T2 -->|"ok"| T3["3 테스트 읽기<br/>새 검토자<br/>전후 3지문 비교"]
  T3 -->|"꼭 고칠 것 없음"| T4["4 구현<br/>새 구현자 · 테스트는 안 고침"]
  T4 --> T5[["5 통과 확인<br/>hb preflight<br/>hb check --phase green"]]
  T5 -->|"ok"| T6["6 구현 검토<br/>새 검토자 · diff 로그"]
  T6 -->|"꼭 고칠 것 없음"| C1["8 커밋 ①<br/>부가 검사<br/>lint · typecheck · build"]
  C1 -->|"통과"| C2[["8 커밋 ②<br/>INDEX 짧게 기록<br/>→ git add 할 일 파일<br/>→ hb done"]]
  C2 -->|"ok"| C3[["8 커밋 ③<br/>git add 작업 폴더<br/>→ git commit"]]
  C3 --> N(["다음 할 일은 1부터"])

  T2 -.->|"stop: 준비 오류 · 전부 건너뜀 · 실패 없음"| T1
  T3 -.->|"꼭 고칠 것"| T1
  T4 -.->|"테스트가 틀림 → 구현 빼 두고 1부터"| T1
  T5 -.->|"stop: 미통과 · 새로 깨짐"| T4
  T6 -.->|"7 지적 반영"| T4
  C1 -.->|"실패"| T4
```

## 그림에 없는 것

- hb 판정(`ok`·`stop`·`not_run`·`timeout`)과 멈췄을 때 할 일: `skills/dev/SKILL.md`의 "프로그램 부르는 법"·"멈췄을 때", `skills/review/SKILL.md`의 "막혔을 때"
- 한도와 테스트 정정: `skills/dev/SKILL.md`의 "그 밖의 규칙", `skills/eval/SKILL.md`의 "다음 단계"
- 결제·권한·개인정보·DB 구조 변경, 실제 DB·운영 작업의 승인: `skills/plan/SKILL.md`의 "이번 판이 다루는 범위"
- 승인과 제안의 규칙(사람의 원문만, hb 안팎의 일은 따로): `skills/plan/SKILL.md`의 8번, `skills/dev/SKILL.md`의 "승인 기록"·"제안", `docs/hermes.md`, 그 저장소의 `.harness/README.md` 운용 정책
- 실행기별 부르는 법: `README.md`의 "쓰는 법 (Claude Code)", `docs/hermes.md`
- 저장소마다 다른 것(검사 환경, 부가 검사 명령, push·PR·병합, 배포 등): 그 저장소의 `.harness/README.md`
