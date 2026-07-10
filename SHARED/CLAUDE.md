# BUCCL Shared Harness (hb-shared)

dev-harness 공통 개발 방법론 코어. BE/CM/FE/CHAT/AOS/IOS 플러그인이 함께 쓰는 **스택 무관 공통 명령**을 제공한다.

## 방법론 순서표 (한 바퀴)

| 명령 | 단계 | 용도 |
|------|------|------|
| `/hb-shared:seed` | ② | 주문서 — 목표·범위·완료기준 한 장 (ambiguity 점검 내장) |
| `/hb-shared:evaluate` | ④ | 검사 — seed 기준 증거 확인 |
| `/hb-shared:review` | ⑤ | 리뷰 관문 — 자동검사·관점별·Codex 교차·반박·게이트 |
| `/hb-shared:evolve` | ⑥ | 개선 제안 — 반복 문제 → 메모리(제안만) |

빌드(③)는 각 도메인 플러그인(BE/CM/FE/CHAT/AOS/IOS)이, interview(①)는 필요 시 진행한다.

## 공통 단계 명령 (스택 무관)

| 명령 | 용도 |
|------|------|
| `/hb-shared:feature:requirements` | 요구사항 정리 |
| `/hb-shared:feature:criteria` | 완료기준(acceptance) 정의 |
| `/hb-shared:feature:design-intent` | 설계 의도 기록 |
| `/hb-shared:feature:prior-art` | 선행 사례·자료 조사 |
| `/hb-shared:maintenance:convention-check` | 컨벤션/ADR 충돌 점검 |
| `/hb-shared:planning:feasibility` | 타당성 검토 |

> **지위**: `requirements`·`criteria`는 seed 주문서에 **흡수**되어 기본 흐름에서는 seed가 대신한다. 나머지는 각 도메인 파이프라인이 인라인으로 수행하는 스텝의 **스택 중립 canonical 정의**이며, 파이프라인 밖에서 그 단계만 따로 돌릴 때 opt-in으로 호출한다.

## 원칙

- 이 플러그인의 명령은 **"어떻게 일하나"(방법)** 만 다룬다. 실제 빌드·테스트 명령과 스택 규칙은 BE/CM/FE/CHAT/AOS/IOS 각 플러그인에 있다.
- 산출물은 작업 레포의 `.harness/artifacts/{track}/{identifier}/`에 남긴다.
- 진실의 원천 문서는 작업 레포의 `.harness/docs/*.yaml`이다.
- 무거운 읽기·조사는 서브에이전트로 내려 메인 컨텍스트를 아끼고, **결론과 산출물 경로만** 회수한다.

> 설계 전문: `docs/SHARED-CORE-DESIGN.md` (dev-harness 레포 루트 기준 — 플러그인 배포본에는 미포함). 이 플러그인은 순서표(seed→evaluate→review→evolve)와 공통 단계 명령을 제공하고, 스택별 빌드·테스트·규칙은 BE/CM/FE/CHAT/AOS/IOS 각 플러그인에 둔다.
