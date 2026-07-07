# 하네스 v2 설계 — 공통 코어(hb-shared) + 일하는 순서표 + 컨텍스트 절약

> 상태: **구현 완료(Phase 1~3, origin/main 머지됨).** hb-shared 코어 + seed/evaluate/review/evolve + feature 흐름 연결 반영. 기준선 = **5 플러그인**(BE/CM/FE/CHAT + hb-shared). 구현 메모: §7의 `team-protocol`·`interview`는 SHARED로 이동하지 않고 도메인 잔류(설계와 차이, 추후 정합화 대상). feature는 5단계 리뷰 인라인 연결 완료, maintenance auto/deep도 연결(hotfix 제외).

## 0. 목표
- 4팀(BE/CM/FE/CHAT)에 흩어진 공통 방법론을 **`hb-shared` 한 곳**으로 모은다.
- ouroboros식 **일하는 순서 한 바퀴**(seed→build→evaluate→review→evolve)를 도입한다.
- **메인 컨텍스트를 최대한 아낀다** — 무거운 일은 서브에이전트로 내려 결론만 회수.
- 켜고 끄든(울트라코드) **항상 작동**. 작은 일은 가볍게.

## 1. 핵심 결정 (확정)
1. **중복 명령은 흡수해 일원화** (별도 추가가 아니라 통합).
2. **evolve는 제안만** — 자동으로 코드/규칙 수정하지 않음. 사람이 채택, 출력은 기존 메모리 피드백 형식으로.
3. **팀 붙는 기준 = "일이 쪼개지나 + 값어치 있나"** — 울트라코드 ON/OFF가 아님.
4. **기본 일꾼 = 서브에이전트**. tmux 에이전트 팀은 "큰 병렬개발" 전용(드뭄).
5. **울트라코드(워크플로우) = 서브에이전트를 각본대로 굴리는 강화판**.
6. **리뷰의 Codex 교차검증은 Claude Code가 `codex` CLI를 자동 호출**(사람이 Codex 따로 안 켬).
7. **공통 = "어떻게 일하나", 팀별 = "무슨 도구로"** — 빌드/테스트 명령·스택 규칙은 팀별 유지.

## 2. 일의 흐름 (loop)
```
 [입력]
   │  ▣ 메인 = 지휘만(얇게). 무거운 건 🤖 서브에이전트로 내려 결론만 회수
 ① interview ····· 👤 메인 (애매할 때만)
 ② seed ⭐ ······· 👤 메인  목표·범위·제외·완료기준·검증법 = 한 장
   │  └[빈틈]──▶ ①                         (작은 일=3줄 / 큰 일=한 장)
 ③ build ········· 🤖 서브에이전트 (팀별 플러그인 · 테스트명령 스택별)
   │                                        ※ 큰 기능 여러 개 동시 = 👥 tmux 팀
 ④ evaluate ······ 🤖 반박 여러 명 [백그라운드] → 메인엔 통과/실패만
 ⑤ review ········ 🤖 관점별+반박 +Codex 자동호출 [백그라운드] → 결과만
   │  └[blocking]──▶ ③
 [머지/PR]
 ⑥ evolve ········ 👤 메인  개선 제안 → 메모리(사람이 채택)
   └── 한 바퀴 = 다음 작업이 더 좋아짐 ──▶ (다시 ①/②)
```

## 3. 컨텍스트 절약 원칙 (★ 최우선)
```
  ▣ 메인(얇게) ──시킴──▶ 🤖 서브에이전트 (무거운 읽기·검색·리뷰·검증)
       ▲                       │
       └──── 결론 몇 줄·경로만 ◀┘   (파일 내용은 메인에 안 올라옴)
```
- 산출물(주문서·리포트) = 파일로 저장, 메인엔 **경로만**.
- 다음 단계엔 **요약만** 넘김(인터뷰 전문 X → 주문서만).
- 무거운 단계(evaluate·review) = **백그라운드**, 메인은 결과만.

## 4. 도구 선택 규칙
| 도구 | 언제 | 비용 |
|---|---|---|
| 👤 혼자(메인) | 작고 가벼운 일 · 지휘 | 0 |
| 🤖 서브에이전트 | 기본 일꾼 — 무거운 읽기/리뷰/검증. 이유 ①병렬 ②컨텍스트 절약 | 가벼움 |
| ⚙ 워크플로우(울트라코드) | 서브에이전트를 각본대로(동시/순서+반박검증) | 중 |
| 👥 tmux 팀 | 큰 기능 여러 개 동시·오래 (드뭄) | 무거움 |

※ 너무 잘게 내리면 손해 — "여러 파일·긴 작업·리뷰"일 때만.

## 5. 리뷰 트랙 (신규)
```
 변경 코드(diff)
 [1] 자동검사(린터·테스트·빌드) ──실패──▶ 멈춤
 [2] 관점별 리뷰어 🤖  ┌버그 ┌보안 ┌성능 ┌구조·간결성
 [3] Codex ∥ Claude 교차검증 ── Claude가 codex 자동 호출
 [4] "진짜 문제 맞아?" 반박 🤖 → 가짜 경보 제거
 [5] 관문: blocking→고치고 [1]부터 / 없으면→통과 ✅
```
- 울트라코드 OFF면 [2]를 혼자 순서대로 도는 가벼운 버전으로 자동 전환.

## 6. 구조 & 크기
```
 dev-harness/
 ├── SHARED/ ◀ 공통 순서표(새로): seed·evaluate·review·evolve (+보조 6종)
 └── BE/ CM/ FE/ CHAT/ ◀ 팀별: 빌드·테스트 명령·스택 규칙 (그대로)
```
- **hotfix**(한 줄): 주문서 3줄 · 혼자
- **auto**(일상): 주문서 짧게 · 기본 혼자
- **deep**(큰 일): 주문서 한 장 · 서브에이전트 풀가동 · 리뷰 꼼꼼

## 7. 명령 재배치 (요약)
- **SHARED로 이동(무손실, 3-way 0-diff)**: feature/criteria·design-intent·prior-art·requirements, maintenance/convention-check, planning/feasibility, shared/team-protocol (7개).
- **SHARED로 흡수(실착지)**: seed ← scope+requirements+criteria / evaluate ← verify(방법)·reflect(취지 — 두 파일은 opt-in으로 도메인 잔류) / evolve = 개선 제안 전용(update-docs는 도메인 잔류) / interview·team-protocol 도메인 잔류 / review-gates는 CHAT 잔류(스택 우선 게이트), 대신 SHARED review(5단계 관문) 신설.
- **도메인 잔류(스택 엮임)**: feature·maintenance·planning의 auto/deep, shared/verify(테스트 명령), shared/tdd 등.

## 8. 구현 단계 (다음)
- **Phase 1** 스캐폴드 + 무손실 이동(7개) + 린터 R3 동시 수정 (저위험).
- **Phase 2** 신규 방법론 작성: seed·ambiguity(seed 내장)·evaluate·evolve·review.
- **Phase 3** 컨텍스트 절약·도구 선택 규칙을 각 명령에 한 토막씩 주입(울트라코드 분기 포함).
- **Phase 4** 마켓플레이스 2곳 등록 + 린터(R5/R6/R7/R9) 확장 + 음성테스트 + 작업레포 `.harness/docs` 정비.

## 9. 주의
- 제품 코드(BE/community/FE/chat 소스)는 손대지 않음 — 하네스만.
- CLAUDE.md는 플러그인별 주입(include 불가) — 스택 MUST 규칙은 축약 금지.
- Codex 머지 후 캐시(`~/.codex/.tmp/marketplaces`, `~/.codex/plugins/cache`) 비우고 재시작.
- 분석/구현 에이전트는 canonical 경로(origin/main)에 핀, HEAD 자가검증.
