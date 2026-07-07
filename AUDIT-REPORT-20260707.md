# 3차 확인 감사 — 2026-07-07

- 기준선: main @ `70ebae6` (PR #17·#18 머지 후), 린터 R1~R11 green
- 방법: 6관점 탐색 + 발견 전수 적대적 반박검증 (42 에이전트)
- 결과: **p1(치명) 0건** — 흐름을 깨는 문제 소멸. 잔존 36건(중복 제거 ~30) = p2 혼란 유발 ~11 + p3 다듬기 ~19
- 직전 수정(#17·#18)의 부작용은 p3급 4건뿐 (비대칭 한정어, 매핑 주석 누락 등) — 회귀 없음

## p2 — 혼란 유발 (유니크 ~11)

### FE 두 모드가 SHARED·검증 루프에 반쪽 반영 (3건)
1. `SHARED/commands/review.md:30` 외 8곳 — SHARED 4개 명령의 FE 렌즈가 "디자인 구현" 모드만 서술, **API 바인딩 렌즈**(계약 일치·상태 처리·mock 잔재) 누락. 수정: 8곳 두 모드 병기.
2. `FE/commands/shared/verify.md:31` + `feature auto:166`·`deep:204` — 산출물 신선도 재확인 목록에 `api-binding-check.md` 누락 → 리뷰 반영 후 stale 바인딩 증거로 QA 통과 가능.
3. `README.md:96` — FE 추가 산출물 열거에 api-binding-check.md 누락 (p3 경계).

### update-docs 예시 3차 잔재 (4건)
4. `CM/commands/shared/update-docs.md:93` + `FE:93` — module-registry 갱신 예시가 Django 골격 그대로.
5. `FE/commands/shared/update-docs.md:83` — architecture 갱신 대상 'external_hooks' = services→hooks 기계 치환 산물 (실제 FE architecture.yaml 키와 불일치).
6. `CM/commands/shared/update-docs.md:83` — architecture 갱신 대상이 BE 원문 그대로 (실제 Community 키: middleware_chain/socket_events/django_proxy 등).

### 신선도 훅 정합 (2건)
7. 4도메인 CLAUDE.md — 신선도 훅이 "F1/M1이 module-registry 대조"를 서술하지만 실제 F1/M1 스텝 본문엔 그 대조 지시 없음 (서술-정의 불일치).
8. `CHAT/CLAUDE.md:106` — 신선도 훅이 target 없는 `/hb-chat:shared:update-docs` 제안하나 CHAT update-docs는 `<target>` 필수 설계.

### 기타 (3건)
9. `CHAT/commands/maintenance/deep.md:309` — 산출물 목록에 codex-review.md 누락 + contract-check.md가 deep에 없어 auto⊂deep 위반.
10. `README.md:99` — 섹션 제목 "(각 플러그인 안에 stack-적합 템플릿 포함)"이 본문·결정#6과 정면 모순 (옛 잔재).
11. `scripts/lint-harness.sh:74` — R3 거짓음성: 대응 파일이 통째로 삭제되면 fail이 아니라 info 스킵 → green 통과.
12. `FE/commands/planning/alternatives.md:70` — UX 페르소나 CM 잔재 (작성자/모더레이터).

## p3 — 다듬기 (유니크 ~19 발췌)

- `SHARED/commands/seed.md:23`·`evaluate.md:21` — 식별자 예시 `BUCCL-BE-42`는 실존하지 않는 형식(실제: BE=`BUCCL-42`, 타=`BUCCL-CHAT-42`), planning은 `plan-YYYYMMDD-slug` 명시 필요
- `SHARED/commands/evaluate.md:42` — [E2].1 스택 열거에 CHAT 불릿 누락 (반쪽 확장)
- `CHAT/commands/contract/api.md:14` — contract 산출물이 review/ 네임스페이스인데 CLAUDE.md 경로 표에 contract 행 없음
- 4도메인 `hotfix.md` [H1] — T0 예외가 말하는 "약식 3줄 seed 서두" 기록 항목 부재
- `docs/SHARED-CORE-DESIGN.md` — §7 명령 재배치 서술이 실착지와 다름 (review-gates 잔류, evolve↛update-docs)
- FE planning 3차 잔재: `decision-draft:28` BE 예약 예문, `alternatives:49` "API 계약 변경/API 계약 변경 위험도" 중복 비문, `:50` "브라우저 이벤트 스키마", `:93` "cache 메모리", `interview:27` 기존 시스템에 자기 자신, `deep:91` CM 페르소나
- `CHAT/commands/feature/auto.md:132` — F7이 codex-review.md 저장 명시 안 함 (deep은 #18에서 수정, auto 누락)
- `CHAT/commands/maintenance/auto.md:191` — "M5 convention 충돌" 에스컬레이션 불릿에 (deep의) 한정어 누락
- `FE/commands/feature/auto.md:109` — F7 헤더만 deep 매핑 주석 없음
- `BE/commands/planning/auto.md:71`·`deep:148` — ADR 편입 후 본문 재제시 항목 BE만 보유 (본문 제시 미러의 잔여 1종)
- `README.md:79` — 산출물 구조에 TDD 증거 3종·seed.md 누락
- `CHAT/CLAUDE.md:63` — {feature-slug}/{issue-slug} 플레이스홀더가 타 도메인({branch-name}/{issue-id})과 상이

## 권장

배치 F(마무리): p2 12건 + p3 중 seed 식별자 예시·CHAT codex-review·(deep의) 한정어 등 인접 항목 일괄 — 1 PR 분량. 나머지 p3는 선택.

---

## 4차 확인 검수 (2026-07-07, 배치 F=PR #19 머지 후)

- 기준선: main @ `805e321`, 린터 R1~R11 green
- 방법: 배치 F 25항목 안착 검증(5그룹) + 부작용 3렌즈 + 발견 전수 2인 반박검증. 1차 시도는 월한도로 에이전트 5개 중단(완료분 15/15 landed) → 잔여분 재실행 22 에이전트 완주(실패 0, 반박 기각 0)
- 결과: 안착 24/25(partial 1) + 신규 잔존 5건(유니크) = **잔존 6건 — p2 1 + p3 5, 흐름 파손 없음**

### 잔존 6건 (배치 G 후보)

1. `docs/SHARED-CORE-DESIGN.md:79`·`:84` — 'SHARED로 이동 … shared/team-protocol (7개)' stale: 실제 이동은 6개(criteria·design-intent·prior-art·requirements·convention-check·feasibility), SHARED에 team-protocol은 전 이력 부재. 80행 '(실착지)'·71행 '+보조 6종'과 절 내 모순 [안착 partial 판정]
2. `BE/commands/maintenance/auto.md:190`·`CM:189`·`FE:193` — '→ M5 convention 충돌 sub-agent 필요'가 미한정(자기 파일 [M5]=수정 실행 TDD Green과 충돌). CHAT:193처럼 '→ deep의 M5(convention 충돌 sub-agent) 필요'로 3곳 미러 (3렌즈 전원 독립 발견, 반박 6/6 uphold)
3. `SHARED/commands/review.md:21` — [R1] 자동검사의 FE 괄호가 디자인 모드만 열거. 두 모드 병기 9곳 중 8곳만 수정된 마지막 1곳 — `evaluate.md:42`의 '(API 바인딩 작업은 계약·상태·mock 검사)' 패턴으로 병기
4. **p2** `FE/commands/planning/deep.md:76`·`:108` — [P4] 인라인 프롬프트에 '브라우저 이벤트 스키마'·'Azure 인프라 비용 (cache 메모리…)' 잔존. `alternatives.md:50`·`:93`은 배치 F에서 라우팅/전역 상태(store)·번들/이미지 트래픽/CDN으로 교체됨 — 같은 [P4] 분석의 쌍둥이 프롬프트가 diverge, 실행 시 팀원에게 옛 항목이 전달됨
5. `CHAT/commands/maintenance/auto.md:152` — M7이 `codex-review.md` 저장을 지시하지 않음(산출물 목록 :181에는 선언 — CHAT 4개 파이프라인 중 유일한 선언-지시 공백). feature/auto:134 수정과 동일 패턴 적용 + :181 표기 '(M7 [R3] — dual gate)' 정렬
6. `README.md:109` — 코드블록 주석 '(사용자가 템플릿을 복사·편집)' — 105-106행 현행 서술('템플릿을 강제 제공하지 않음')과 모순, '(직접 작성·갱신)' 계열로

패턴: 전부 "감사가 지목한 좌표만 수정하고 **동일 문구의 형제 좌표**를 안 훑은" 미완 전파. 배치 G 수정 시 각 항목을 repo-wide grep으로 완결할 것.
