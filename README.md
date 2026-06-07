# BUCCL Dev Harness

BUCCL의 네 레포(메인 BE / 커뮤니티 CM / 프론트엔드 FE / 채팅 CHAT)를 위한 Claude Code 기반 개발 자동화 파이프라인.
하나의 마켓플레이스에 **다섯 플러그인**이 들어 있다 — 레포별 4개와 공통 방법론 코어 `hb-shared`.

## 다섯 플러그인

| 플러그인 | 대상 레포 | 스택 | 슬래시 prefix |
|---------|----------|------|--------------|
| `hb-be` | `BE/` (메인 백엔드) | Django 5.2 + DRF + MySQL + Celery + Redis + Azure Blob | `/hb-be:...` |
| `hb-cm` | `CM/` (커뮤니티) | Node 18 + TS 5.3 + Express + MySQL + Redis + Socket.io + Jest | `/hb-cm:...` |
| `hb-fe` | `FE/` (프론트엔드) | React 18 + CRA + React Router + Zustand + MUI/Bootstrap + Capacitor | `/hb-fe:...` |
| `hb-chat` | `CHAT/` (채팅 MSA) | Node 18 + TS + Express + Socket.io + MySQL + Redis + Azure Blob + Jest | `/hb-chat:...` |
| `hb-shared` | (공통) | 스택 무관 방법론 코어 — 4개 플러그인이 공유 | `/hb-shared:...` |

`hb-be`/`hb-cm`/`hb-fe`는 **3-track 구조**(기획/신규개발/유지보수)를 공유한다.
`hb-chat`은 여기에 chat 특성상 **ADR 트랙·Contract 트랙·dual review gate**를 더한다 (계약이 깨지면 FE/BE/앱이 동시에 깨지므로). 스택별로 명령(테스트 명령, 레이어 용어, 컨벤션 ID)이 다르다.
`hb-shared`는 4팀 공통 **방법론 순서표**(seed → evaluate → review → evolve)와 공통 보조 명령을 제공한다 (아래 "일하는 순서").

## 일하는 순서 (hb-shared 공통 방법론)

| 단계 | 명령 | 하는 일 |
|------|------|--------|
| ② seed | `/hb-shared:seed` | 주문서 — 목표·범위·제외·완료기준·검증법 한 장 (크기별 약식~전체, 빈틈 점검 내장) |
| ④ evaluate | `/hb-shared:evaluate` | 주문서 완료기준 충족을 증거로 검사 (자동검사 → 반박) |
| ⑤ review | `/hb-shared:review` | 머지 전 5단계 관문: 자동검사 → 관점별 → Codex∥Claude 교차 → 반박 → 게이트 |
| ⑥ evolve | `/hb-shared:evolve` | 반복 문제 → 개선 제안 (제안만, 자동 수정 X) |

- ①interview는 필요 시, ③build는 각 도메인 플러그인(feature/maintenance)이 담당한다.
- **완료기준·증거·리뷰 렌즈는 각 스택을 따른다.** FE는 **디자인 구현 / API 바인딩** 두 모드로 나뉘어 기준이 다르다.
- 무거운 읽기·검증은 Sub-agent로 내려 메인 컨텍스트를 아끼고 결론·경로만 회수한다. 울트라코드(워크플로우)가 켜지면 병렬+반박으로 더 정밀해지고, 꺼져도 가볍게 작동한다.
- 공통 보조 명령: `requirements`·`criteria`·`design-intent`·`prior-art`(feature), `convention-check`(maintenance), `feasibility`(planning) 가 `hb-shared`로 모여 있다.

> **제품 레포 적용:** 플러그인 `CLAUDE.md`는 스킬 활성화 시에만 읽히므로, 제품 레포의 always-read 문서(`CLAUDE.md`/`AGENTS.md`)에 이 방법론을 명시해야 트랙 호출 없이도 기본 적용된다. 캐논 스니펫·절차 → [docs/PRODUCT-REPO-ADOPTION.md](docs/PRODUCT-REPO-ADOPTION.md).

## 트랙 비교 (공통)

| 트랙 | 언제 쓰나 | 코드 수정 | 최종 출력 |
|------|----------|----------|---------|
| `planning` | 무엇을 만들지 확정 전 | 없음 (문서만) | ADR 드래프트 → adr.yaml 편입 |
| `maintenance` | 버그, 리팩토링, 성능 개선 | 있음 (범위 제한적) | 수정 커밋 + 회귀 리포트 |
| `feature` | 새 기능/서비스 추가 | 있음 (범위 큼) | PR + 리뷰 반영 완료 코드 |

## tier 체계 (공통)

각 트랙은 3개 tier로 운용된다. **기본값은 T1 `auto` — lightweight**.
full ceremony가 필요한 경우에만 명시적으로 `:deep`을 호출한다.

| tier | 이름 | 용도 | 사용자 핑퐁 | Agent Team |
|------|------|------|------------|------------|
| T0 | `hotfix` (maintenance 전용) | 오타, 한 줄 fix, 긴급 수정 | 최소 | 없음 |
| T1 | `auto` (기본값) | 일상 작업 | 중간 | 없음 |
| T2 | `deep` | 아키텍처급 결정, 복잡 기능, 심층 진단 | 많음 | 있음 (planning/maintenance만) |

- `auto` 산출물은 `deep` 산출물의 **부분집합**이다. 동일 트랙에서 tier 전환이 안전하다.
- `hotfix`는 독립 경로로, 다른 tier를 선행하지 않는다.
- 트랙 간 전이(planning↔feature↔maintenance)는 tier와 무관하게 동일하게 작동한다.

## 실행 모드 분포 (공통)

| 트랙 | Fork | Sub-agent | Agent Team |
|------|------|-----------|------------|
| 기획 | P1, P2, P5, P6 | P3 | P4 (대안 분석) |
| 유지보수 | M2, M6, M7 | M3, M5, M9 | M4 (영향도), M8 (회귀) |
| 신규개발 | F2, F4, F6, F8 | F3, F5, F7 | — |

## 트랙 간 전이 (각 플러그인 안에서)

```
기획 → /<plugin>:shared:update-docs adr (승인 게이트) → 신규개발 → 유지보수
                                                    ↑                |
                                                    └── 에스컬레이션 ←┘
```

## 산출물 구조 (공통)

```
.harness/artifacts/
  planning/{plan-YYYYMMDD-slug}/
    scope.md, stakeholders.md, requirements-interview.md,
    external-research.md, alternatives.md, feasibility.md,
    decision-draft.md, INDEX.md
  maintenance/{issue-id}/
    reproduction.md, root-cause.md, impact-analysis.md,
    convention-check.md, fix-plan.md, regression-report.md,
    review-comments.md, INDEX.md
  feature/{branch-name}/
    requirements.md, prior-art.md, design-intent.md,
    code-quality-guide.md, pr-body.md, review-comments.md, INDEX.md
```

FE feature/maintenance는 필요 시 design-source.md, visual-check.md,
responsive-check.md, accessibility-notes.md, visual-regression.md를 추가로 남긴다.

## 참조 문서 (각 플러그인 안에 stack-적합 템플릿 포함)

작업 레포의 `.harness/docs/`가 진실의 원천이다. 현재 플러그인 디렉토리는 템플릿을 강제 제공하지 않으므로,
각 레포에서 실제 코드 상태에 맞게 아래 4개 YAML을 직접 작성하거나 기존 문서를 갱신한다.

```
.harness/docs/             ← 작업 디렉토리의 진실의 원천 (사용자가 템플릿을 복사·편집)
  code-convention.yaml
  adr.yaml
  architecture.yaml
  module-registry.yaml
```

## Quick Start

1. 이 디렉토리(harness/)를 Claude Code 마켓플레이스로 등록한다.
2. BE 레포에서는 `hb-be`, CM 레포에서는 `hb-cm`, FE 레포에서는 `hb-fe` 플러그인을 활성화한다.
3. 각 작업 레포의 `.harness/docs/` 디렉토리를 만들고 실제 코드 상태에 맞게 4개 YAML을 작성한다.
4. 작업 레포 `.gitignore`에 아래를 추가한다 — 산출물은 제외하되 `.harness/docs/`는 팀 공유용 진실의 원천이므로 트래킹한다.
   ```
   .harness/artifacts/
   ```
   (`.harness/` 전체를 ignore하지 말 것. 만약 과거 설정이 `.harness/`이면 `!.harness/docs/`로 예외 처리한다.)
5. Claude Code에서 작업 유형에 맞는 트랙을 실행한다.

```
# BE 레포에서 — 일상 기본값 (T1, lightweight)
/hb-be:planning:auto         # 간이 기획 → ADR 드래프트
/hb-be:feature:auto          # 일반 신규 기능
/hb-be:maintenance:auto      # 일반 유지보수

# BE 레포에서 — 심층 모드 (T2, full ceremony)
/hb-be:planning:deep         # 3관점 대안 분석 + 인터뷰 + 외부조사
/hb-be:feature:deep          # prior-art + quality-guide + PR본문 Fork
/hb-be:maintenance:deep      # 영향도 3방향 Team + ADR 충돌 체크

# BE 레포에서 — 긴급 수정 (T0, hotfix)
/hb-be:maintenance:hotfix    # 재현 테스트 + 수정 + 단위 테스트만

# CM 레포에서 — 동일 tier 구조
/hb-cm:planning:auto
/hb-cm:planning:deep
/hb-cm:feature:auto
/hb-cm:feature:deep
/hb-cm:maintenance:hotfix
/hb-cm:maintenance:auto
/hb-cm:maintenance:deep

# FE 레포에서 — 디자인/시각 검증 포함
/hb-fe:planning:auto
/hb-fe:planning:deep
/hb-fe:feature:auto
/hb-fe:feature:deep
/hb-fe:maintenance:hotfix
/hb-fe:maintenance:auto
/hb-fe:maintenance:deep
```

## Codex 사용

다섯 플러그인(`BE/`, `CM/`, `FE/`, `CHAT/`, `SHARED/`) 모두 Codex용 `.codex-plugin/plugin.json`과 `skills/<plugin>/SKILL.md`를 포함한다.
repo-local Codex marketplace는 `.agents/plugins/marketplace.json`에 있으며 `./BE`, `./CM`, `./FE`, `./CHAT`, `./SHARED` 다섯 플러그인을 모두 가리킨다.
Codex는 Claude slash command를 직접 실행하지 않으므로, `hb-be feature auto로 이 API 구현해줘`처럼 자연어 alias로 사용한다.
Codex skill은 각 플러그인의 `<plugin>/commands/` 문서를 source of truth로 읽고 동일한 `.harness/artifacts/` 산출물 규약을 따른다.

사용자의 `~/.codex/config.toml`에서 marketplace를 등록한 뒤 다섯 플러그인을 활성화한다:

```toml
[plugins."hb-be@buccl-dev-harness-codex"]
enabled = true

[plugins."hb-cm@buccl-dev-harness-codex"]
enabled = true

[plugins."hb-fe@buccl-dev-harness-codex"]
enabled = true

[plugins."hb-chat@buccl-dev-harness-codex"]
enabled = true

[plugins."hb-shared@buccl-dev-harness-codex"]
enabled = true
```

> marketplace를 git source로 등록한 경우 머지 직후 캐시가 stale일 수 있다.
> `~/.codex/.tmp/marketplaces/<name>` 과 `~/.codex/plugins/cache/<name>` 을 비우고 Codex를 재시작하면 다섯 플러그인이 새로 설치된다.

## 디렉토리 구조

```
harness/
├── .claude-plugin/
│   └── marketplace.json          ← 다섯 플러그인 등록
├── .agents/plugins/
│   └── marketplace.json          ← Codex용 다섯 플러그인 등록
├── BE/                           ← Django 플러그인
│   ├── .claude-plugin/plugin.json
│   ├── .codex-plugin/plugin.json
│   ├── CLAUDE.md
│   ├── commands/                 (planning/, maintenance/, feature/, shared/)
│   └── skills/hb-be/SKILL.md     (Codex 진입점)
├── CM/                           ← Node.js 플러그인
│   ├── .claude-plugin/plugin.json
│   ├── .codex-plugin/plugin.json
│   ├── CLAUDE.md
│   ├── commands/                 (planning/, maintenance/, feature/, shared/)
│   └── skills/hb-cm/SKILL.md     (Codex 진입점)
├── FE/                           ← React 프론트엔드 플러그인
│   ├── .claude-plugin/plugin.json
│   ├── .codex-plugin/plugin.json
│   ├── CLAUDE.md
│   ├── commands/                 (planning/, maintenance/, feature/, shared/)
│   └── skills/hb-fe/SKILL.md     (Codex 진입점)
├── CHAT/                         ← 채팅 MSA 플러그인 (+ADR/Contract 트랙, dual review gate)
│   ├── .claude-plugin/plugin.json
│   ├── .codex-plugin/plugin.json
│   ├── CLAUDE.md
│   ├── commands/                 (planning/, feature/, maintenance/, adr/, contract/, shared/)
│   └── skills/hb-chat/SKILL.md   (Codex 진입점)
├── SHARED/                        ← 공통 방법론 코어 (hb-shared)
│   ├── .claude-plugin/plugin.json
│   ├── .codex-plugin/plugin.json
│   ├── CLAUDE.md
│   ├── commands/                 (seed, evaluate, review, evolve + 공통 보조)
│   └── skills/hb-shared/SKILL.md (Codex 진입점)
├── scripts/lint-harness.sh       ← R1~R9 린터
└── README.md
```

## License

MIT
