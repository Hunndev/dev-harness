# BUCCL BE 개발 하네스

3-track 개발 자동화 파이프라인. 기획 → 신규개발 → 유지보수를 구조화된 워크플로우로 수행한다.

이 플러그인은 **BUCCL 메인 백엔드(Django) 레포 전용**이다.
커뮤니티(Node.js) 레포 작업은 `hb-cm` 플러그인을 사용한다.

## 프로젝트 스택

- Backend: Django 5.2 / DRF
- Language: Python 3.11+
- DB: MySQL (PyMySQL 드라이버)
- Async: Celery + Redis (broker)
- Storage: Azure Blob Storage
- Auth: JWT (SimpleJWT)
- Payment: Innopay
- Infra: Docker Swarm on Azure VM
- Testing: pytest

## 트랙 목록

| 커맨드 | 트랙 | 언제 쓰나 | 코드 수정 |
|--------|------|----------|----------|
| `/hb-be:planning` | 기획 | 무엇을 만들지 확정 전. 요구사항 수집, 대안 탐색, 타당성 검토 | 없음 (문서만) |
| `/hb-be:maintenance` | 유지보수 | 버그 수정, 리팩토링, 성능/의존성 업그레이드 | 있음 (범위 제한적) |
| `/hb-be:feature` | 신규개발 | 새 기능/서비스/엔드포인트 추가 | 있음 (범위 큼) |
| `/hb-be:update-docs` | 공통 | convention / ADR / architecture / module-registry 갱신 | 문서만 |

## 산출물 경로

모든 산출물은 `.harness-artifacts/{track}/{identifier}/` 하위에 저장한다.

- planning: `.harness-artifacts/planning/{plan-YYYYMMDD-slug}/`
- maintenance: `.harness-artifacts/maintenance/{issue-id}/`
- feature: `.harness-artifacts/feature/{branch-name}/`

## 참조 문서

플러그인은 작업 디렉토리의 `docs/` 하위 4개 YAML 파일을 진실의 원천으로 사용한다.

- `docs/code-convention.yaml` — 코딩 컨벤션 (Django/DRF/pytest 특화)
- `docs/adr.yaml` — Architecture Decision Records
- `docs/architecture.yaml` — 시스템 구조 맵
- `docs/module-registry.yaml` — Django 앱 모듈 레지스트리

플러그인 자체의 `docs/`는 BE 레포에 옮겨 쓸 수 있는 템플릿이다.

## 실행 모드 정의

| 모드 | 설명 | 사용자 상호작용 |
|------|------|----------------|
| Fork | worktree 격리 실행. 사용자와 핑퐁이 많은 구간 | 있음 (피드백 루프) |
| Sub-agent | 단일 에이전트 위임. 고정 형식 분석/판단 | 없음 (자동) |
| Agent Team | 다관점 병렬 분석. 각 에이전트가 독립 관점으로 동시 작업 후 메인이 병합 | 없음 (자동) |

## 트랙 간 전이 규칙

```
기획 (planning)
   │  decision-draft.md
   ▼
/hb-be:update-docs adr  ← 사용자 승인 게이트
   │  docs/adr.yaml
   ▼
신규개발 (feature)       ← 새 ADR을 평가기준으로 흡수
   │  review-comments.md
   ▼
유지보수 (maintenance)   ← 기존 ADR 준수 체크 (convention-check.md)
```

전이 규칙:
1. 유지보수 중 새 설계 결정이 필요하면 → planning 트랙으로 에스컬레이션
2. 신규개발 중 요구사항이 흔들리면 → planning 트랙으로 되돌아감
3. planning 결과물은 자동으로 코드에 반영되지 않음 → 반드시 `/hb-be:update-docs adr`로 사용자 승인 게이트 통과
4. 새 ADR 생성은 planning 트랙에서만 허용. maintenance 트랙에서 자체적으로 ADR을 만들지 않는다.
5. 다른 레포(커뮤니티) 작업이 필요하면 `hb-cm` 플러그인으로 전환한다.

## 공통 규칙

1. Fork에서 실행하는 단계는 산출물만 생성하고 소스코드를 수정하지 않는다. (수정 실행 단계 제외)
2. 모든 산출물 디렉토리에 `INDEX.md`를 생성하여 산출물 목록과 현재 상태를 기록한다.
3. 사용자에게 확인을 요청할 때, 모호하여 구체화가 필요한 논의점을 반드시 함께 정리하여 전달한다.
4. Agent Team 실행 시, 각 에이전트의 결과를 메인이 병합하고 충돌/모순을 해소한 뒤 사용자에게 제시한다.
5. DB 마이그레이션이 포함된 변경은 반드시 마이그레이션 파일을 별도로 리뷰한다.
6. Django settings(`buccl_back/settings/`) 변경은 사용자 승인 없이 수행하지 않는다.
7. Product API는 read-only — 생성/수정은 Django Admin에서만 (buccl_main 규칙).
