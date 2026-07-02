# BUCCL Chat 개발 하네스

이 플러그인은 **BUCCL chat MSA 전용**이다. 다른 레포(메인 BE/Django, FE/React, community/Node)는 각각 `hb-be`, `hb-fe`, `hb-cm` 플러그인을 사용한다.

chat은 "코딩"보다 **설계 결정·실시간 계약·연동 경계**를 일관되게 관리하는 것이 핵심이다. 계약이 깨지면 FE/BE/앱이 동시에 깨지므로, contract-first / ADR-first / dual-review-gate를 강제한다.

## 프로젝트 스택

- Runtime: Node.js 18+
- Language: TypeScript (strict mode)
- Framework: Express
- Realtime: Socket.io
- DB: MySQL `chat_buccl_dev` (chat 전용 DB)
- Cache / Pub-Sub: Redis (Socket.io adapter scale-out)
- Storage: Azure Blob / Object Storage (첨부 원본)
- Auth: Django SimpleJWT 호환 JWT (메인 BE와 키 공유)
- Test: Jest
- Lint: ESLint
- Build: tsc

## 핵심 경계 (MUST)

1. 기존 `BE`(Django), `buccl-community`(Node), `FE`(React) 레포는 **기본적으로 수정하지 않는다**.
2. chat 서비스는 chat 작업 레포(`chat`)에서만 작업한다.
3. **BE DB를 직접 읽지 않는다.** 필요한 데이터는 BE API 경유.
4. 강습/투어 신청자 목록은 **BE API가 검증한 userId 목록만** 사용한다 (source of truth = BE).
5. 첨부파일 원본은 DB에 저장하지 않는다 (Object Storage + 메타데이터만 DB).
6. 모든 Socket.io 이벤트는 `.harness/docs/websocket-events.yaml`에 등록되어야 한다.
7. 모든 REST API 변경은 `.harness/docs/api-contract.yaml`에 반영되어야 한다.
8. DB 변경은 `.harness/docs/database-schema.yaml` 갱신 + migration review를 동반한다.
9. 설계 결정은 **planning → ADR draft → 사용자 승인 → update-docs** 순서로만 확정한다 (maintenance/feature 트랙이 자체적으로 ADR을 만들지 않는다).
10. 완료 기준은 **테스트 통과 + Codex review 통과 + Claude review 통과** (dual review gate). 자세한 기준은 `commands/shared/review-gates.md`.

cross-repo 작업이 필요하면 직접 수정하지 말고 → 필요한 contract를 제안 → 사용자 승인 → 해당 플러그인(`hb-be`/`hb-fe`/`hb-cm`)으로 전환한다.

## 트랙 / tier 체계

각 트랙은 tier로 운용된다. 기본값은 `:auto` (T1 standard, lightweight). 더 가벼우면 `:hotfix`(maintenance 전용), 더 깊으면 `:deep`.

| 커맨드 | tier | 트랙 | 언제 쓰나 | 코드 수정 |
|--------|------|------|----------|----------|
| `/hb-chat:planning:auto`      | T1 | 기획     | 일반 기능/구조 결정 (스코프 → 타당성 → ADR 드래프트) | 없음 |
| `/hb-chat:planning:deep`      | T2 | 기획     | DB/Redis/Socket/BE/FE 영향 큰 결정. 인터뷰+조사+3관점 Team | 없음 |
| `/hb-chat:feature:auto`       | T1 | 신규개발 | 단일 API/이벤트/서비스 (요구사항 → 설계의도 → contract-check → 리뷰 → QA) | 있음 |
| `/hb-chat:feature:deep`       | T2 | 신규개발 | 다중 모듈, BE/FE 연동, migration, Socket event 변경 동반 | 있음 |
| `/hb-chat:maintenance:hotfix` | T0 | 유지보수 | 오타·한 줄·긴급 (재현 → 수정 → 단위 테스트) | 있음(최소) |
| `/hb-chat:maintenance:auto`   | T1 | 유지보수 | 일반 버그/리팩터 (RCA → 수정 → 회귀) | 있음 |
| `/hb-chat:maintenance:deep`   | T2 | 유지보수 | race condition·메시지 중복·읽음 처리·성능·장애급 (3방향 영향 Team + ADR 충돌) | 있음 |
| `/hb-chat:adr:new`            | —  | ADR      | 설계 결정을 ADR 후보로 등록 → 승인 후 adr.yaml 편입 | 문서만 |
| `/hb-chat:contract:websocket` | —  | 계약     | Socket.io 이벤트 계약 검토·갱신 (websocket-events.yaml) | 문서 중심 |
| `/hb-chat:contract:api`       | —  | 계약     | REST API 계약 검토·갱신 (api-contract.yaml) | 문서 중심 |
| `/hb-chat:shared:update-docs` | —  | 공통     | adr/architecture/modules/websocket/api/database/ops 문서 갱신 | 문서만 |
| `/hb-chat:shared:verify`      | —  | 공통     | 테스트/빌드/리뷰 전 검증 (npm test/lint/build/tsc) | 없음 |
| `/hb-chat:shared:review-gates`| —  | 공통     | 완료 게이트 (Jest + lint + build + Codex review + Claude review) | 없음 |

> 추가 예정(실제 개발하며 확장): `adr:review`, `adr:supersede`, `contract:event-versioning`.

## 산출물 경로

모든 산출물은 chat 작업 레포의 `.harness/artifacts/{track}/{identifier}/` 하위에 저장한다.

- planning: `.harness/artifacts/planning/{plan-YYYYMMDD-slug}/`
- feature: `.harness/artifacts/feature/{feature-slug}/`
- maintenance: `.harness/artifacts/maintenance/{issue-slug}/`
- adr: `.harness/artifacts/adr/{adr-id}/`
- review: `.harness/artifacts/review/{identifier}/`

## 진실의 원천 (chat 작업 레포의 `.harness/docs/`)

플러그인은 docs 템플릿을 싣지 않는다. chat 작업 레포에서 실제 상태에 맞게 아래를 작성·갱신한다.

| 파일 | 역할 |
|---|---|
| `adr.yaml` | 확정된 아키텍처 결정 |
| `architecture.yaml` | 서비스 구조, 모듈 경계, 의존성 |
| `module-registry.yaml` | room/message/attachment/invite/presence 모듈 맵 |
| `code-convention.yaml` | Node/TS/Express/Socket.io 코딩 규칙 |
| `websocket-events.yaml` | Socket.io event name·payload·ack·error 계약 |
| `api-contract.yaml` | REST endpoint·request/response·auth |
| `database-schema.yaml` | 테이블·인덱스·migration 정책 |
| `integration-boundary.yaml` | BE/FE/community 와의 경계 |
| `operations.yaml` | Redis·배포·로그·모니터링·장애 대응 |
| `review-policy.yaml` | Claude/Codex 리뷰 기준 |

## 원칙

1. 산출물 우선: 각 단계는 아티팩트 디렉토리에 결과를 남긴다.
2. contract-first: 구현 전 REST/Socket/DB/Redis/첨부/BE연동/FE영향 계약을 먼저 확인한다.
3. ADR-first: DB 구조·읽음 정책·이벤트 네이밍/버전·scale-out·첨부 저장·연동 경계·권한 모델 변경은 무조건 ADR 후보로 올린다.
4. 새 ADR 생성은 planning/adr 트랙에서만. maintenance/feature는 기존 ADR 준수만 체크(`convention-check.md`).
5. TDD: feature/maintenance는 Red→Green→Refactor. 테스트 러너는 **Jest**. 증거는 `tdd-baseline-log.txt`/`tdd-green-log.txt`에 캡처. 프로토콜은 `commands/shared/tdd.md`.
6. dual review gate: 완료는 항상 테스트+lint+build 통과 + Codex/Claude 리뷰 blocking 0. `commands/shared/review-gates.md`.

## 방법론 연결 (hb-shared 순서표)

feature·maintenance 작업은 hb-shared 공통 순서표를 따른다. `feature:auto`/`deep`(및 maintenance)를 호출하면 아래가 자동으로 적용된다:

1. **시작 — 주문서**: `/hb-shared:seed` 방법으로 목표·범위·완료기준을 먼저 고정한다. (작은 일은 약식 3줄, 큰 일은 한 장)
2. **구현**: 아래 트랙 명령(feature/maintenance)으로 만든다.
3. **검사**: `/hb-shared:evaluate` 방법으로 주문서 완료기준 충족을 증거로 확인한다.
4. **리뷰**: 머지 전 `/hb-shared:review`의 **5단계 관문**(자동검사 → 관점별 → Codex∥Claude 교차 → 반박 → 게이트)을 적용한다. **기존 코드리뷰 스텝의 단일 패스는 이 5단계로 대체**하며, 기존 스텝 절차는 그중 "관점별 리뷰([R2])"의 세부로 쓴다.
5. **개선(선택)**: `/hb-shared:evolve`로 반복 문제를 제안으로 남긴다(제안만, 자동 수정 X).

> **T0 예외**: `maintenance:hotfix`는 위 순서표의 예외다 — seed는 약식 3줄(`hotfix-reproduction.md` 서두)로 갈음하고, evaluate·review 5단계 관문은 **생략**한다 (H3 단위 테스트 게이트가 완료 조건). 5단계 관문이 필요해 보이면 그 자체가 `:auto`로의 에스컬레이션 신호다.

완료기준·증거·리뷰 렌즈는 이 플러그인 스택을 따른다. 무거운 읽기·검증은 Sub-agent로 내려 메인 컨텍스트를 아끼고 결론·경로만 회수한다.
