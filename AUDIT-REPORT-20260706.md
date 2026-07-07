# 하네스 재검수 보고서 — 2026-07-06

- 기준선: main @ `3eaf4b0` (PR #16 머지 직후), 린터 R1~R10 green
- 방법: 회귀검증 3 에이전트(체크 16항목) + 신규탐색 6관점 + 발견 전수 적대적 반박검증 (총 61 에이전트)
- 결과: **회귀 16/16 통과** (지난 PR #13·#15·#16 전부 안착) / **신규 발견 52건 확인** (중복 제거 시 48건: p1 3, p2 28, p3 17) — 전부 문서 정합성 문제, 코드 아님

---

## 회귀 검증 — 16/16 PASS

| PR | 확인 항목 | 결과 |
|----|----------|------|
| #13 배선 | 순서표 섹션·T0 예외·seed/evaluate 앵커(16파일)·E1/E4·R1/R2/R3/R5·5단계 대체 선언 | 6/6 pass |
| #15 신선도 | 신선도 훅 4곳·update-docs 교차검사 4곳·F1/M1 스텝 실재 | 3/3 pass |
| #16 위생 | SKILL.md 경로·코어 4개 등록·(CM) 0건·R10/R8·버전 3곳 패리티·README 2개 절 | 7/7 pass |

---

## p1 — 치명 (3건, 리드 직접 재확인 완료)

### P1-1. seed 식별자 규칙이 maintenance 트랙과 구조적으로 어긋남
- `SHARED/commands/seed.md:23` — "feature/maintenance 트랙이면 `git branch --show-current`"
- 그러나 4도메인 maintenance 아티팩트 경로는 `.harness/artifacts/maintenance/{issue-id}/` (예: BUCCL-CHAT-42)
- → seed는 `{branch-name}/seed.md`에 저장, M1 앵커는 `{issue-id}/seed.md`를 찾음 — **겸직 핸드셰이크가 서로 다른 디렉토리를 봄**
- 수정안: seed [S1]을 "maintenance는 issue-id(트랙 파이프라인 식별자 규칙)를 따른다"로 분기. evaluate.md 식별자 절도 동일 점검.

### P1-2. FE feature:auto의 deep 교차참조 6곳 중 4곳이 낡은 번호
- `FE/commands/feature/auto.md:23,24,124,148,204` — FE deep은 F9(시각/반응형 검증) 삽입으로 F12까지인데, auto의 "(deep의) FN" 매핑이 BE 번호 그대로
- 실제: 리뷰=F11(표기 F10), PR본문=F10(표기 F9), 완료보고=F12(표기 F11), quality-guide 소비자=F8(표기 F7)
- 수정안: 교차참조 6곳 번호 재계산. + 같은 계열: `FE/commands/shared/verify.md:4`(F8/F11→F9/F12), `README.md:67` 실행 모드 분포 표.

### P1-3. CHAT dual gate ↔ SHARED review [R3] 생략 규칙 모순
- `CHAT/commands/shared/review-gates.md:70` "Codex 리뷰는 생략 → 금지" vs `SHARED/commands/review.md:38-39` "미설치/실패 시 생략, 50줄 미만 생략 가능"
- CHAT CLAUDE.md 방법론 연결이 SHARED 5단계 관문 적용을 지시하므로 실행 시 어느 규칙을 따를지 불명
- 수정안: SHARED review [R3]에 "스택이 더 엄격한 게이트를 정의하면(예: CHAT dual gate) 그것이 우선한다" 한 줄. CHAT review-gates에도 관계 명시.

---

## p2 — 혼란 유발 (28건, 테마별)

### B. 트랙 핸드셰이크 (wiring)
1. `SHARED/commands/review.md:22` — [R1] 재사용이 `evaluate-report.md`의 HEAD 기록을 전제하나, 도메인 evaluate 겸직 스텝(M6/M8·F8/F9/F11 QA)은 그 파일을 생성하지 않음 → 재사용 전제가 트랙 흐름에서 성립 불가. 수정안: 겸직 앵커에 "회귀/QA 통과 시 evaluate-report.md(HEAD 포함)를 남긴다" 추가 또는 R1 재사용 조건을 "QA 로그+HEAD 메모"로 완화.
2. `SHARED/commands/review.md:28` — 렌즈 매핑에 CHAT 없음("모든 스택 공통" 선언과 불일치). CHAT = 계약/경계 렌즈(Socket·REST·BE DB 금지) 추가. (seed/evaluate의 스택 열거도 동일)
3. `CHAT/CLAUDE.md:92` — 원칙 6 "완료는 **항상** dual gate"가 T0 hotfix 예외와 무단서 충돌 → "(hotfix 제외)" 단서.
4. `CHAT/commands/shared/review-gates.md:57` — 산출물 경로가 `artifacts/review/{id}/`로 지정되나 트랙 파이프라인·SHARED review는 `artifacts/{track}/{id}/` → 동일 파일 두 좌표. 단일화 필요.

### C. CHAT deep 배선 공백 (symmetry)
5. `CHAT/commands/maintenance/deep.md:320` — 최중량 tier에 dual gate·codex-review·contract-check 배선 전무 (자기 완료 기준과 모순).
6. `CHAT/commands/feature/deep.md:206` — 산출물 목록의 8개 파일(contract-check, integration-plan, migration-review, websocket/api-contract-diff, rollback-plan, release-checklist, codex-review)을 생성하는 스텝이 F1~F11에 없음.
7. `CHAT/commands/feature/deep.md:219` — auto엔 F3b 계약 점검 스텝이 명시인데 deep은 말미 블록쿼트 한 줄 (p3 경계, 게이트 비대칭).

### E. tier 포함관계 위반 (auto ⊂ deep 불변식)
8. `FE/commands/maintenance/deep.md:34,309` — auto에 있는 visual 이슈 유형·baseline·`visual-regression.md`가 deep에 없음 → 시각 이슈를 deep으로 올리면 시각 검증이 사라짐.
9. `BE/commands/maintenance/auto.md:80` — '본문 제시 (필수)' 스텝이 BE에만 존재(9곳), CM/FE/CHAT 부재.

### D. 잔재 2차분 (remnants)
10. `CHAT/commands/maintenance/rca.md:23` — 체크리스트 라벨 'CM' 잔존.
11. `CHAT/commands/maintenance/reproduce.md:39` — "## CM 특화 재현 체크리스트" 헤딩.
12. `CHAT/commands/planning/deep.md:25` — 시스템 유형 'CM 자체' 표기.
13. `CHAT/commands/planning/decision-draft.md:28` — ADR '좋은 예'가 BE 예약(세션 이중예약) 시나리오.
14. `CM/commands/planning/decision-draft.md:28` — 동일 (커뮤니티 도메인 예시로 교체 필요).
15. `CHAT/commands/feature/reflect.md:32` — 예시 경로가 CM의 post.service.ts.
16. `FE/commands/shared/update-docs.md:55` — convention 스키마 예시가 DJ/DRF 카테고리·django/drf stacks (React 예시로 교체).
17. `CM/commands/shared/update-docs.md:55` — 동일 (Node/TS 예시로).

### F. 린터 사각지대 (linter-gaps — 전부 음성테스트로 실증됨)
18. `scripts/lint-harness.sh:152` — R5/R6 검사 대상에 `skills/*/SKILL.md` 누락 (Codex 진입점의 경로 드리프트 통과).
19. `:167` — R6 yaml 화이트리스트가 4종뿐 → CHAT 1급 문서 6종(websocket-events 등) 단독 docs/ 잔재 미검출.
20. `:175` — `<plugin>/docs/` 잔재 검사가 BE/docs/ 하드코딩 (CM/FE/CHAT/SHARED 동일 유형 미검출).
21. `:243` — 마켓플레이스 name↔source 페어링 미검증 (뒤바뀌어도 통과).
22. `:85` — R3 shared/ 비교는 전 파일 0-step이라 공허 통과 (주석의 커버리지 주장 허위).

### G. 등록 표면·README (references, codex-parity)
23. `SHARED/.claude-plugin/plugin.json:3` + `.claude-plugin/marketplace.json:34` — 설명이 보조명령 6개만 서술, 코어 순서표 누락 (Codex 쪽과 불일치).
24. `README.md:113` — Quick Start가 3플러그인 시절: hb-chat/hb-shared 활성화 안내·명령 예시 누락, '4개 YAML'이 CHAT(10종)과 불일치.
25. `README.md:67` — '실행 모드 분포' 표가 TDD 삽입 전 구번호 (P1-2와 함께 수정).

### 기타
26. `CM/FE/CHAT feature/auto.md:114` — 코드리뷰 원칙에서 BE의 두 원칙(의도적 결정 존중·side effect 설명) 누락 (auto만 드리프트).
27. `CHAT/commands/feature/auto.md:114` — F7 리뷰 입력에 contract-check.md 누락 (G1 요구와 어긋남).
28. `.claude-plugin/marketplace.json:22` — hb-fe만 plugin.json과 설명 분기.

## p3 — 다듬기 (17건 발췌)

- `feature/reflect.md` 4도메인 — 어디서도 참조 안 되는 고아 명령 + 내용이 F8/F11과 중복 (설계 문서는 evaluate로 흡수됐다고 명시) → 지위 블록쿼트 또는 삭제 결정 필요
- `FE/commands/feature/reflect.md:32` — .ts 확장자(JSX 불가)·백엔드식 네이밍 예시
- `CHAT/commands/shared/verify.md:14` — plain Jest에 CRA식 --watchAll=false 주석 / `:3` 게이트 번호 1~4 vs 1~5 어긋남
- `FE/commands/planning/deep.md:24` — CM 페르소나 잔존, `research.md:27` — FE를 MSA 구성원으로 오기술
- `BE/commands/maintenance/auto.md:25` — "(deep의)" 표기 누락으로 자기 스텝 취소처럼 읽힘
- `BE/CLAUDE.md:106` — 순서표(evaluate→review)와 feature 실제 순서(F7 리뷰→F8 QA) 역전 서술
- `SHARED/CLAUDE.md:36` — `docs/SHARED-CORE-DESIGN.md` 참조가 플러그인 배포 단위에 미포함
- `docs/REVIEW-DESIGN.md` — untracked 초안이 폐기된 `/hb-x:review:*` 트랙·R1~R9 서술 (커밋 or 삭제 or .gitignore 결정 필요)
- `scripts/lint-harness.sh` 주석·메시지 5곳 3플러그인 시절 표현
- 차기 가드 후보: **R11** 슬래시 명령(`/hb-x:track:cmd`) 참조 실재성 / **R3 강화** 스텝 개수→스텝 ID 집합 비교

---

## 권장 수정 배치

| 배치 | 내용 | 성격 |
|------|------|------|
| **E1 (p1+핸드셰이크)** | P1-1/2/3 + B그룹 4건 + FE verify/README 번호 | 흐름 정확성 — 최우선 |
| **E2 (CHAT 정비)** | C그룹 3건 + CHAT 잔재 5건 + dual gate 단서 | CHAT 신뢰성 |
| **E3 (잔재·대칭)** | D그룹 나머지 + E그룹 2건 + auto 리뷰 원칙 | 청소 |
| **E4 (린터 강화)** | F그룹 5건 + R11 신설 + R3 ID 비교 + 메시지 현행화 | 재발 방지 |
| **E5 (표면)** | README Quick Start·SHARED claude 설명·reflect 지위 | 겉면 |

*수정 시 검증 규약: 선 green 카운트 → 수정 → 린터 green → 신설 가드는 음성테스트.*
