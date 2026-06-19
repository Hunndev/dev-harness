# 리뷰 트랙 설계 (REVIEW-DESIGN)

> 상태: **DRAFT — 검토용**. 구현 전 합의 문서.
> 대상: `hb-be` / `hb-cm` / `hb-fe` 공통.
> 작성 맥락: 현행 인라인 리뷰(F7/F10 + verify)를 1급 트랙으로 승격하고, 멀티모델 합의·적대적 검증·게이트를 티어에 비례해 얹는다.

---

## 1. 배경 · 목표

현재 리뷰는 `feature`/`maintenance` 파이프라인 안의 한 단계(F7/F10 코드리뷰 sub-agent + F8/M6 verify)로만 존재한다. 이미 근거 기반·[p1]~[p4] severity·TDD 증거 교차검증까지 갖춰 수준이 높지만, 다음이 빠져 있다:

- **단일 모델** — Claude sub-agent 1개. Codex를 이미 운용하는데 리뷰에 미참여.
- **건설적 일변도** — 발견을 반박(refute)하는 적대적 패스 없음 → 거짓 양성 통과.
- **차원 미분리** — correctness/convention 중심. security·performance 축 부재.
- **게이트 아님** — [p1] 잔존해도 자동 차단 없음(사람 판단에만 의존).
- **재사용 불가** — 리뷰 로직이 feature/maintenance 안에 박혀 있어 임의 PR/diff에 단독 실행 불가.

**목표**: 리뷰를 독립 트랙으로 추출(DRY) + 티어에 비례하는 레이어 구조로 깊이 조절 + 이미 가진 Claude·Codex 2모델을 합의에 활용.

**비목표**: 외부 CI 플랫폼 교체, 새 런타임 추가, 기존 [p1]~[p4]/TDD 교차검증 체계 폐기(유지·계승).

---

## 2. 설계 원칙

1. **DRY** — 리뷰 로직은 `review` 트랙 한 곳. feature/maintenance는 이를 *호출*한다.
2. **티어 비례** — 리뷰 깊이를 기존 hotfix/auto/deep에 매핑(하네스 철학 계승).
3. **근거 강제 계승** — 모든 코멘트는 `.harness/docs/*.yaml` 기준 인용. 취향 리뷰 금지(현행 유지).
4. **증거·재현성** — 리뷰 결과는 model별·dimension별·verdict로 기록 → 감사 가능(경량 ledger).
5. **거짓 양성 최소화** — 발견은 "확정"이 아니라 "검증 후 확정". 적대적 패스로 강등 경로 마련.
6. **이식성보다 정합성** — BUCCL 3레포 특화는 유지하되, 세 플러그인 간 리뷰 구조는 린터로 대칭 강제.

---

## 3. 아키텍처 — 독립 `review` 트랙 + 5레이어

```
새 트랙:  /hb-<x>:review:{hotfix|auto|deep}     (x = be|cm|fe)
호출처:  feature(F7/F10), maintenance(M6/M-review) 가 review 트랙을 호출

 Layer 0  구조 린터 R1~R9 (CI)              [이미 있음] 플러그인 자체 정합성
 Layer 1  차원 분리 리뷰                     [현행 강화] 축별 병렬 sub-agent
            ├─ correctness/convention  (현행 review.md 계승)
            ├─ security                (신규 축)
            ├─ performance             (신규 축)
            └─ test-integrity          (현행 TDD 증거 교차검증 승격)
 Layer 2  멀티모델 합의                      [차용: ouroboros] Claude ∥ Codex 독립 리뷰 → 병합
 Layer 3  적대적 검증 (doubt-driven)         [차용: agent-skills] 각 [p1] 반박 패스 → 강등
 Layer 4  게이트 + anti-rationalization      [신규] [p1] 잔존 시 차단 + 핑계·반박 표
```

### 3.1 티어 매핑 (리뷰 깊이)

| 커맨드 | 활성 레이어 | 실행 모드 | 용도 |
|---|---|---|---|
| `review:hotfix` | L0 + L1(correctness만) | Sub-agent 1 | 빠른 단일 패스, 긴급 |
| `review:auto` | L0 + L1(전 차원 병렬) + L4 게이트 | Team(차원별) | 일상 기본값 |
| `review:deep` | L0~L4 전부 | Team + Codex + refute Fork | 고위험·릴리스·민감 변경 |

> `auto` 산출물은 `deep` 산출물의 부분집합(기존 tier 불변식 유지). hotfix는 독립 경로.

---

## 4. 레이어 상세

### Layer 1 — 차원 분리 리뷰

현행 단일 sub-agent를 **축(dimension)별 병렬 sub-agent**로 분해. 각 축은 자기 기준 파일만 본다(컨텍스트 절약 + 전문성).

| 축 | 기준 | 주요 점검 |
|---|---|---|
| correctness/convention | `code-convention.yaml`, `adr.yaml`, `design-intent.md` | 현행 review.md 그대로 계승. 의도-구현 불일치, 컨벤션 위반 |
| security | (신규) `security-checklist`(stack별) | 입력 검증, 인증/인가, 비밀·PII 로깅, SQL/주입, 의존성 |
| performance | (신규, stack별 임계) | N+1, 불필요 렌더/쿼리, 번들/메모리, 측정 우선 |
| test-integrity | `tdd-baseline-log.txt`/`tdd-green-log.txt` | **현행 TDD 증거 교차검증을 독립 축으로 승격** (로그 조작=사기 탐지) |

- 실행: `auto`/`deep`은 Agent Team(축당 1워커) 병렬 → 메인이 병합. `hotfix`는 correctness 단일.
- 산출: 축별 코멘트를 `[p1]~[p4]`로 통합 → `review-comments.md`.
- stack별 차이: security/perf 체크리스트가 Django/Node/React로 다름(각 플러그인 `commands/review/dimensions/*`에 분리).

### Layer 2 — 멀티모델 합의 (Claude ∥ Codex)

이미 두 모델을 운용 중 → **거의 공짜로 얻는 최대 차별화**.

- Claude가 L1 리뷰 수행. **동시에** Codex(`codex review` 또는 gstack-codex)에 같은 diff+기준을 던져 독립 리뷰.
- 메인이 두 결과를 **병합·합의 판정**:
  - 양쪽이 같은 위치/사안을 짚음 → `confirmed` (신뢰도↑)
  - 한쪽만 짚음 → `needs-adjudication` (메인이 기준 대조해 채택/기각, 근거 기록)
  - severity 불일치 → 높은 쪽 채택 + 사유 기록
- 산출: `review-comments.md`에 각 코멘트의 `source: claude|codex|both` 표기.
- 적용 티어: `deep`(기본), `auto`(옵션 플래그). `hotfix`는 미적용.

### Layer 3 — 적대적 검증 (doubt-driven)

각 `[p1]` 발견을 **반박 전제로** 재검토(fresh context Fork).

- 프롬프트: "이 [p1]이 거짓 양성일 근거를 찾아라. 기본값은 '반박됨'." (agent-skills doubt-driven 차용)
- 다수 반박 시 → severity 강등 또는 폐기(근거 기록). 살아남은 [p1]만 게이트로.
- 목적: 자신감 있어 보이지만 틀린 발견 제거 → 리뷰 신뢰도/수용률↑.
- 적용 티어: `deep`만(비용 큼).

### Layer 4 — 게이트 + anti-rationalization

- **게이트**: L1~L3 후 `[p1]`(미해결·미강등) 잔존 시 → **통과 실패**. tier별 엄격도:
  - `hotfix`: [p1] 중 correctness/security만 차단(속도 우선)
  - `auto`: 모든 [p1] 차단
  - `deep`: [p1] + 미해결 needs-adjudication 차단
- **anti-rationalization 표**(agent-skills 차용): `review.md`에 "리뷰 단계 건너뛰는/[p1] 무시하는 흔한 핑계 + 반박" 표 내장 → 에이전트가 스스로 스킵 못 하게.
  - 예: "테스트는 나중에" → 반박; "이 [p1]은 사소" → severity는 근거로 정해지지 사후 판단으로 내리지 않음.
- 게이트 결과는 `INDEX.md`에 `gate: PASS|BLOCKED (사유)` 기록.

---

## 5. 산출물 스키마

```
.harness/artifacts/review/{identifier}/
  review-input.md          # 대상 diff 범위, 기준 파일 스냅샷, tier
  dimension-correctness.md # L1 축별 (deep/auto)
  dimension-security.md
  dimension-performance.md
  dimension-test-integrity.md
  codex-review.md          # L2 Codex 독립 결과 (deep/auto-opt)
  consensus.md             # L2 병합·합의 판정
  refutation.md            # L3 적대적 검증 결과 (deep)
  review-comments.md       # 최종 통합 코멘트 (현행 스키마 확장: source/verdict 필드)
  INDEX.md                 # gate 판정, 산출물 목록, tier
```

`review-comments.md` 확장(현행 계승 + 필드 추가):

```markdown
### [p1] {파일}:{라인}
- dimension: correctness | security | performance | test-integrity
- source: claude | codex | both        # L2
- verdict: confirmed | survived-refute  # L2/L3
- 근거: {기준 파일의 어떤 항목}
- 내용 / 제안 / side effect / 제안 이유
```

`identifier`: PR/브랜치명 또는 `git rev-parse --short HEAD`. feature/maintenance가 호출 시 해당 트랙 식별자 재사용.

---

## 6. 트랙 간 통합

- **feature**: F7(현행 review sub-agent) → `review` 트랙 호출로 치환. F8은 review-comments를 입력받아 반영(현행 유지).
- **maintenance**: M-review 단계가 `review` 트랙 호출. convention-check는 L1 correctness 축으로 흡수.
- **호출 규약**: 상위 트랙이 tier를 전달(`feature:deep` → `review:deep`). 단독 실행도 가능(`/hb-be:review:auto` on 임의 PR).
- **mafia-codereview 흡수**: 설치된 `mafia-codereview` 플러그인의 유효한 룰을 L1 축 체크리스트로 이관 후, 중복 플러그인 정리(별도 결정).

---

## 7. 린터 확장 (R10 제안)

기존 R1~R9에 더해:

- **R10 — review 트랙 정합성**: 세 플러그인 모두 `commands/review/{hotfix,auto,deep}.md` + `dimensions/*` 존재, 산출물 경로 `.harness/artifacts/review/` 일관, tier 매핑 표 대칭.
- (선택) **R11 — anti-rationalization 표 존재**: `review.md`에 핑계·반박 표 섹션 필수.

---

## 8. 단계적 도입 로드맵

| Phase | 범위 | 산출 |
|---|---|---|
| **P1** | 독립 `review` 트랙 추출 + L1 차원 분리 + L4 게이트 | `review:hotfix/auto`, dimensions, 게이트, R10 |
| **P2** | L2 멀티모델 합의(Claude∥Codex) | `consensus.md`, codex 연동, `review:deep` 1차 |
| **P3** | L3 적대적 검증 + anti-rationalization 표 + mafia 흡수 | `refutation.md`, R11, 플러그인 정리 |

각 Phase는 독립 PR. P1만으로도 즉시 가치(차원+게이트). P2가 최대 차별화.

---

## 9. 미해결 결정 (검토 필요)

1. **트랙 구조**: 독립 `review` 트랙 신설(추천, DRY) vs 현행 F7/F10 in-place 강화? → 본 문서는 독립 트랙 전제.
2. **Codex 연동 방식**: `codex review` CLI 직접 호출 vs gstack-codex 경유 vs MCP? (P2 상세 설계 필요)
3. **게이트 강제력**: 권고(보고만) vs 하드 차단(통과 실패로 후속 중단)? tier별 차등 제안했으나 확정 필요.
4. **mafia-codereview**: 흡수 후 제거 vs 병존? 룰 중복도 조사 선행.
5. **security/perf 기준 출처**: 새 체크리스트 작성 vs agent-skills의 security/performance-checklist 차용·번역?
6. **적용 우선 레포**: BE 먼저 파일럿 후 CM/FE 확산 vs 동시?

---

## 10. 차용 출처 (추적)

- **멀티모델 합의 / 재현 원장** ← ouroboros (Seed/Ledger, 3-stage evaluate, multi-model consensus)
- **적대적 검증 / anti-rationalization / severity·axis** ← addyosmani/agent-skills (doubt-driven, code-review-and-quality, security/perf checklist)
- **TDD 증거 교차검증 / 근거 강제 / 티어·트랙** ← 현행 BUCCL 하네스 (계승)
```
