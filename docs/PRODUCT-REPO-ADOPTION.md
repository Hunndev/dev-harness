# 제품 레포 도입 가이드 (Product Repo Adoption)

dev-harness 플러그인(`hb-be`/`hb-cm`/`hb-fe`/`hb-chat`)을 쓰는 제품 레포가
**항상 읽히는 거버닝 문서**(`CLAUDE.md`/`AGENTS.md`)에 hb-shared 공통 방법론을
명시하기 위한 캐논 스니펫과 절차.

## 왜 필요한가

플러그인의 `CLAUDE.md`는 **스킬이 활성화될 때만** 읽힌다 (예: `/hb-be:*` 호출 시 hb-be 스킬이 "Read CLAUDE.md first" 지시).
반면 제품 레포에서 **항상 읽히는 건 그 레포 자신의 `CLAUDE.md`(Claude)와 `AGENTS.md`(Codex)** 다.

따라서 제품 레포의 거버닝 문서가 hb-shared를 언급하지 않으면,
트랙을 명시 호출하지 않은 일반 요청("기능 추가해줘")은 방법론을 건너뛰고 옛 방식으로 흐른다.
→ **제품 레포의 always-read 문서에 아래 포인터를 둬서**, 트랙 명시 호출 없이도 hb-shared 순서가 기본 적용되게 한다.

## 캐논 스니펫 (`CLAUDE.md` + `AGENTS.md` 둘 다에 넣는다)

`<XX>` = 레포의 플러그인 prefix (`be`/`cm`/`fe`/`chat`).

```markdown
> **이 레포 개발은 hb-<XX> 트랙(`/hb-<XX>:*`)을 기본으로 한다.**
> 트랙을 명시 호출하지 않아도, 기능·수정 작업은 아래 hb-shared 공통 순서를 따른다.

## 방법론 — hb-shared 공통 순서 (트랙을 명시 호출하지 않아도 기본 적용)
1. **주문서(seed)** — 목표·범위·완료기준을 먼저 고정 (작은 일 3줄, 큰 일 한 장).
2. **구현** — `/hb-<XX>:feature:auto|deep` 또는 `/hb-<XX>:maintenance:hotfix|auto|deep`.
3. **검사(evaluate)** — 주문서 완료기준 충족을 증거로 확인.
4. **리뷰** — 머지 전 5단계 관문(자동검사 → 관점별 → Codex∥Claude 교차검증 → 반박 → 게이트). 단일 패스 코드리뷰는 이 5단계로 대체.
5. **개선(evolve, 선택)** — 반복 문제는 제안으로 남김 (자동 수정 X).
```

## 절차

1. 제품 레포 루트의 `CLAUDE.md`와 `AGENTS.md` **양쪽**에 위 스니펫을 넣는다.
   이미 트랙 표/포인터가 있으면 `## 방법론` 섹션만 추가한다 (예: `BE`).
2. `<XX>`를 레포 prefix로 치환한다. 트랙명은 **플러그인 정식 이름**과 정확히 일치해야 한다 —
   기준은 `.claude-plugin/marketplace.json`의 `name` (현재: `hb-be`/`hb-cm`/`hb-fe`/`hb-chat`).
   제품 레포가 다른 이름(예: `hb-community`)을 쓰고 있으면 정식 이름으로 **교정**한다.
3. `FE` 레포는 step 2에 **디자인 구현 / API 바인딩 두 모드**를 덧붙인다
   (디자인 구현 = 시각/반응형/a11y, API 바인딩 = 계약 일치·loading/empty/error 상태).
4. 한쪽만 있으면(예: `AGENTS.md` 없음) 신설해 **dual-runtime 패리티**를 맞춘다.

## 적용 상태 (2026-06-08)

| 레포 | 플러그인 | 비고 |
|------|---------|------|
| `BE` | `hb-be` | 트랙 표 기존 보유 → `## 방법론` 섹션만 추가 |
| `FE` | `hb-fe` | 트랙 참조 없었음 → 포인터 + 방법론 추가, `AGENTS.md` 신설 |
| `Community` | `hb-cm` | 트랙명 `hb-community` → `hb-cm` 교정 + 방법론 추가 |
| chat | `hb-chat` | 보류 (레포 위치 미확인) |
