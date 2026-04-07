# BUCCL Dev Harness

BUCCL의 두 레포(메인 BE / 커뮤니티 CM) 각각을 위한 Claude Code 기반 3-track 개발 자동화 파이프라인.
하나의 마켓플레이스에 두 개의 플러그인이 들어 있다.

## 두 플러그인

| 플러그인 | 대상 레포 | 스택 | 슬래시 prefix |
|---------|----------|------|--------------|
| `hb-be` | `BE/` (메인 백엔드) | Django 5.2 + DRF + MySQL + Celery + Redis + Azure Blob | `/hb-be:...` |
| `hb-cm` | `CM/` (커뮤니티) | Node 18 + TS 5.3 + Express + MySQL + Redis + Socket.io + Jest | `/hb-cm:...` |

두 플러그인은 **같은 워크플로우 구조**(기획/신규개발/유지보수 3-track)를 공유하지만,
스택별로 명령(테스트 명령, 레이어 용어, 컨벤션 ID)이 다르다.

## 트랙 비교 (양쪽 공통)

| 트랙 | 언제 쓰나 | 코드 수정 | 최종 출력 |
|------|----------|----------|---------|
| `planning` | 무엇을 만들지 확정 전 | 없음 (문서만) | ADR 드래프트 → adr.yaml 편입 |
| `maintenance` | 버그, 리팩토링, 성능 개선 | 있음 (범위 제한적) | 수정 커밋 + 회귀 리포트 |
| `feature` | 새 기능/서비스 추가 | 있음 (범위 큼) | PR + 리뷰 반영 완료 코드 |

## 실행 모드 분포 (양쪽 공통)

| 트랙 | Fork | Sub-agent | Agent Team |
|------|------|-----------|------------|
| 기획 | P1, P2, P5, P6 | P3 | P4 (대안 분석) |
| 유지보수 | M2, M6, M7 | M3, M5, M9 | M4 (영향도), M8 (회귀) |
| 신규개발 | F2, F4, F6, F8 | F3, F5, F7 | — |

## 트랙 간 전이 (각 플러그인 안에서)

```
기획 → /<plugin>:update-docs adr (승인 게이트) → 신규개발 → 유지보수
                                                    ↑                |
                                                    └── 에스컬레이션 ←┘
```

## 산출물 구조 (양쪽 공통)

```
.harness-artifacts/
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
    code-quality-guide.md, pr-body.md, review-comments.md,
    INDEX.md
```

## 참조 문서 (각 플러그인 안에 stack-적합 템플릿 포함)

```
{BE,CM}/docs/
  code-convention.yaml    — 코딩 컨벤션
  adr.yaml                — Architecture Decision Records
  architecture.yaml       — 시스템 구조 맵
  module-registry.yaml    — 모듈 레지스트리
```

## Quick Start

1. 이 디렉토리(harness/)를 Claude Code 마켓플레이스로 등록한다.
2. BE 레포에서는 `hb-be` 플러그인을, CM 레포에서는 `hb-cm` 플러그인을 활성화한다.
3. 각 레포의 `docs/` 하위에 플러그인 템플릿(`{BE,CM}/docs/*.yaml`)을 복사하고 실제 상태에 맞게 수정한다.
4. Claude Code에서 작업 유형에 맞는 트랙을 실행한다.

```
# BE 레포에서
/hb-be:planning      # 새 기능 결정 단계
/hb-be:feature       # 새 기능 개발
/hb-be:maintenance   # 버그/리팩토링

# CM 레포에서
/hb-cm:planning
/hb-cm:feature
/hb-cm:maintenance
```

## 디렉토리 구조

```
harness/
├── .claude-plugin/
│   └── marketplace.json          ← 두 플러그인 등록
├── BE/                           ← Django 플러그인
│   ├── .claude-plugin/plugin.json
│   ├── CLAUDE.md
│   ├── commands/                 (planning/, maintenance/, feature/, shared/)
│   └── docs/                     (4개 YAML 템플릿 — Django 컨벤션)
├── CM/                           ← Node.js 플러그인
│   ├── .claude-plugin/plugin.json
│   ├── CLAUDE.md
│   ├── commands/                 (planning/, maintenance/, feature/, shared/)
│   └── docs/                     (4개 YAML 템플릿 — Node 컨벤션)
└── README.md
```

## License

MIT
