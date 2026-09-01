# BUCCL Shared Harness (hb-shared)

dev-harness 공통 개발 방법론 코어. BE/CM/FE/CHAT/AOS/IOS 플러그인이 함께 쓰는 **스택 무관 공통 명령**을 제공한다.

## 방법론 순서표 (한 바퀴)

| 명령 | 단계 | 용도 |
|------|------|------|
| `/hb-shared:seed` | ② | 주문서 — 목표·범위·완료기준 한 장 (ambiguity 점검 내장) |
| `/hb-shared:evaluate` | ④ | 검사(Evaluate) — 같은 packet에서 실제 AC·증거·scope·운영 완료 판정 |
| `/hb-shared:review` | ⑤ | 평가(Review) — 같은 packet에서 구현·보안·회귀·테스트 품질 독립 검토 |
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
- 진실의 원천은 작업 repository가 주제별로 선언한다. `AGENTS.md`/`CLAUDE.md`/`.harness/README.md`가 `.harness/docs/*.yaml`을 canonical로 지정하면 해당 규칙·ADR·architecture·계약의 진실의 원천으로 사용한다. 실제 CI·manifest·source와 충돌하면 어느 한쪽을 자동으로 무시하지 않고 `BLOCKED`한다. 외부 repository에 선언되지 않은 architecture 복사본을 강제하지 않는다.
- 무거운 읽기·조사는 서브에이전트로 내려 메인 컨텍스트를 아끼고, **결론과 산출물 경로만** 회수한다.
- Evaluate와 Review는 각각 구현 context와 분리된 fresh process/session에서 수행한다. 모든 환경에서 blind fresh Claude+Codex Evaluate를 먼저 완료하고, 그 뒤 blind fresh Claude+Codex Review를 수행한다.
- Gate·Evaluate·Review·Finalize는 하나의 `packet_id`/`source_snapshot_id`/`evidence_bundle_id`에 묶인다. timeout·auth 실패·malformed result·provider 누락·snapshot mismatch·repository mutation은 PASS가 아니라 `BLOCKED`다.

> 설계 전문: `docs/SHARED-CORE-DESIGN.md` (dev-harness 레포 루트 기준 — 플러그인 배포본에는 미포함). 이 플러그인은 순서표(seed→evaluate→review→evolve)와 공통 단계 명령을 제공하고, 스택별 빌드·테스트·규칙은 BE/CM/FE/CHAT/AOS/IOS 각 플러그인에 둔다.
