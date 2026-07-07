# dev-harness 플러그인 사용성 감사 보고서

- 일자: 2026-07-02
- 기준선: `origin/main` = `5be60d74a731` (PR #11 포함)
- 방법: 에이전트 11개 — 영역별 감사 7 (SHARED/BE/CM/FE/CHAT/교차정합/사용성 워크스루) → 3렌즈 심사(임팩트·실행가능성·방법론 정합) → 완결성 비평
- 산출: 마찰점 47건, 제안 48건 (2표 이상 cut 제안은 제외됨)

## 요약 — 3대 문제축

1. **seed·evaluate 배관 단절** — CLAUDE.md는 '자동 적용'이라 선언하지만 도메인 명령 본문에 seed/evaluate 문자열 0회. review만 실배선됨. seed 주문서를 evaluate/review가 입력으로 안 읽음.
2. **auto가 이름만 경량** — fork 6회/스텝, auto·deep 리뷰 blockquote 동일(Codex 교차검증 무조건), evaluate→review 자동검사 2중 실행, hotfix 예외 미명문화.
3. **죽은 참조·복붙 잔재·고아 명령** — SKILL.md 깨진 경로 3곳, 고아 보조명령 6개, SHARED 안 Django 잔재, CM/CHAT/FE 복붙 잔재 다수, 코어 4명령이 Codex 등록에 없음.

## 착수 전 선행 결정 (비평가 지적)

- **공백**: (1) '사용 습관' 개선이 전무 — 20개 제안 전부 하네스 명령 파일 편집이고, '언제 어떤 명령을 부르나'를 돕는 항목이 0건이다. 결정적 증거: git 이력에서 a9721cc가 docs/PRODUCT-REPO-ADOPTION.md(제품 레포의 always-read CLAUDE.md에 hb-shared 방법론을 거는 훅)를 추가했다가 e2cad9b로 통째로 리버트됐다. 즉 '플러그인 CLAUDE.md는 스킬 활성 시에만 읽힌다'는 구멍이 이미 인지됐고 롤백된 상태인데, 감사 제안 어디에도 이 구멍의 재해결이 없다. README.md Quick Start는 슬래시 명령 20여 개를 나열만 하고 결정 트리가 없다. 사용자 메모리의 '새 흐름은 기본 진입점에 연결' 교훈과 정확히 같은 실패 모드다.
  - **보완 제안**: ① PRODUCT-REPO-ADOPTION.md를 최소형으로 재상륙: 제품 레포 4곳의 always-read CLAUDE.md/AGENTS.md에 넣을 5~10줄 캐논 스니펫(트랙 결정 트리 + 기본 tier=auto + seed 판단 기준)만 제공하고, 1차 리버트 사유를 문서에 제약조건으로 명기(현재 리버트 이유가 어디에도 기록 안 됨). ② 진입점 단일화 명령 /hb-shared:go 신설: 작업 한 줄을 받으면 hotfix/auto/deep × planning/feature/maintenance 중 무엇을 부를지 판정만 해주는 라우터 — 107개 명령을 외우는 대신 하나만 기억. ③ 각 플러그인 CLAUDE.md에 3줄짜리 치트시트 표 추가('한 줄 fix→maintenance:hotfix / 화면 변경→feature:auto 디자인 모드 / 설계 결정→planning:auto') — UX-1~6이 흐름 내부 마찰만 줄이는 것과 보완 관계. ④ 제품 레포 .claude/settings.json SessionStart 훅으로 현재 브랜치의 .harness/artifacts 상태(seed 있음? review 미완?)를 세션 시작 시 한 줄 출력 — 습관을 기억이 아니라 시스템이 상기.
- **공백**: (2) 제품 레포 쪽 .harness/docs YAML 품질이 진짜 병목일 가능성이 검토되지 않았다. README.md 93~104행: 플러그인은 템플릿을 제공하지 않고 사용자가 4개 YAML(code-convention/adr/architecture/module-registry)을 손으로 작성해야 한다. 그런데 seed [S2], evaluate [E1], review [R2], convention-check, update-docs가 전부 이 YAML을 기준 입력으로 소비한다 — 파일이 비었거나 낡았으면 파이프라인 전체가 '일반론 리뷰'로 조용히 강등된다. scripts/lint-harness.sh R1~R9는 하네스 리포 자신만 검사하고 제품 레포 YAML은 아무도 검증하지 않는다. CM-1은 update-docs 명령 텍스트만 고칠 뿐이다. 20개 편집을 다 해도 기준 데이터가 부실하면 체감 개선은 0에 수렴한다.
  - **보완 제안**: ① 우선순위 재조정을 위한 선행 진단: 20개 편집 착수 전에 제품 레포 4곳의 .harness/docs/*.yaml 실태(존재/파싱/항목 수/최종 갱신일)를 먼저 감사 — 비어 있으면 병목은 플러그인이 아니라 여기다. ② /hb-<x>:shared:docs-bootstrap(또는 update-docs init 모드) 신설: Sub-agent가 실제 코드(Django apps/, React routes)를 스캔해 module-registry.yaml·architecture.yaml 초안을 자동 생성 — 손 작성 의존 제거. ③ harness-doctor 경량 스크립트: 4개 YAML의 존재·스키마 적합·항목 수를 리포트하고, seed [S2]/evaluate [E1]에 'docs 미비 시 generic 기준으로 강등됨을 명시 보고' 규칙 추가(조용한 강등 금지). ④ 신선도 교차검사: update-docs 또는 evolve에서 module-registry.yaml 항목 vs 실제 최상위 모듈 디렉토리를 diff해 drift를 플래그 — BE/commands/shared/update-docs.md의 'feature 후 반드시 갱신' 규칙이 현재 무집행 상태다.
- **공백**: (3) '빼기' 방향이 거의 없다. BE-3/UX-4/UX-6만 흐름을 가볍게 할 뿐 삭제·통합 제안은 0건. 규모 증거: 명령 파일이 BE/CM/FE 각 23개 + CHAT 28개 + SHARED 10개 = 107개이고, planning·maintenance는 린터 R3가 4도메인 완전 대칭을 강제하는 복붙 구조다. 감사 발견의 상당수(XC-1, XC-4, CM-1, CM-2, FE-3, FE-5)가 바로 이 복붙의 drift 증상인데, 제안들은 개별 증상만 고치고 중복이라는 원인을 안 건드린다 — 다음 변경 때 또 4~5배 편집이 필요하다. 또한 SHARED/commands/evaluate.md(E2 자동검사→E3 반박→E4 관문)는 review.md(R1→R4→R5)의 거의 부분집합이라 같은 브랜치에서 자동검사·반박이 2회 중복되는데, SH-1/XC-3/BE-1은 이 2단계를 더 깊게 배선해 결합을 늘리는 방향이다. Codex 미러(.codex-plugin×5 + .agents marketplace + SKILL.md×5 + 린터 R7/R9 절반)도 실사용이 review [R3]의 codex CLI 호출뿐이라면 통째로 삭제 후보다.
  - **보완 제안**: ① evaluate를 review에 흡수 검토: 솔로 개발자에게 별도 evaluate 관문이 필요한지 먼저 판정하고, 필요 없으면 review에 --quick 모드 하나로 통합 — SH-1/XC-3로 두 단계를 16개 파이프라인에 각각 배선하기 전에 결정해야 순서가 맞다. ② 4도메인 복붙 해소: planning·maintenance 본문(이미 기준을 스택에 위임하는 stack-agnostic 골격)을 SHARED로 올리고 도메인별 차이는 파라미터 블록 한 토막으로 — 감사 발견의 3분의 1을 만든 drift 클래스 자체를 제거. ③ Codex 미러 존폐 결정: 실제 Codex 플러그인 사용 여부를 확인하고, review [R3] CLI 호출만 쓴다면 .codex-plugin/.agents/SKILL.md/R7·R9 절반을 삭제 — 유지비 최대 절감 항목. ④ 미사용 명령 폐기 목록 워크스트림: 호출 이력 기준으로 planning/alternatives, feature/reflect(evolve와 중복), interview 4중복, deep tier의 tmux Team(사용자 메모리상 '순수 오버헤드') 등을 삭제/강등 후보로 심사 — '고치기'만 있고 '버리기' 심사가 감사에 없었다.
- **공백**: (4-a) 제안 우선순위가 실사용 데이터 없이 정적 감사 점수(avg)로만 매겨졌다. 어떤 명령이 실제로 호출됐고 어디서 파이프라인이 중도 이탈했는지 근거가 없다 — evolve는 작업 단위 opt-in이라 채택률·사용률 같은 횡단 데이터를 만들지 못한다. 20개 편집의 절반이 안 쓰는 명령을 고치는 것일 수 있다.
  - **보완 제안**: ① 편집 착수 전 ~/.claude 세션 이력에서 /hb-* 호출 빈도와 중도 이탈 지점을 한 번 추출해 20개 제안을 '실사용 경로 위/밖'으로 재정렬 — 경로 밖 제안(예: 안 쓰는 deep tier 관련)은 보류. ② evolve 산출물(evolve-suggestions.md)이 작업 레포 아티팩트에 고립되지 않게, 채택 시 하네스 리포 이슈(gh issue)로 승격하는 한 줄 규칙을 SHARED/commands/evolve.md [V3]에 추가 — 자기개선 고리가 실제로 하네스 백로그에 닿게. ③ 사용자 전역 메모리 피드백 시스템(MEMORY.md)과 evolve 출력 형식이 이미 호환된다고 명시돼 있으니(evolve.md 9행), '채택된 제안은 메모리 노트로도 1줄 등록'을 명문화해 세션 간 학습 루프를 닫기.
- **공백**: (4-b) 제안 실행 시 린터·가드와의 충돌 및 재-drift 방지가 계획에 없다. FE-2(모드 조건부 스텝), BE-3(fork 축소), XC-3(16개 파이프라인 인라인)은 scripts/lint-harness.sh R3(스텝 헤더 개수 대칭)·R8(FE 산출물 필수)과 직접 상호작용하는데 린터 co-evolution 항목이 목록에 없다 — 사용자 자신의 교훈('가드/린터 확장은 양방향 검증')과 배치된다. 또 XC-1이 고치는 깨진 참조를 다시 못 깨지게 하는 가드도 없어, 고친 drift가 재발한다.
  - **보완 제안**: ① 각 제안에 '린터 영향' 컬럼을 붙여 R3/R8 변경이 필요한 것을 같은 PR에 묶기 — 대칭 카운트가 깨지는 편집은 린터 수정 없이는 CI가 막는다. ② 신규 규칙 R10 추가: 모든 명령 문서의 /hb-*:... 상호 참조가 실제 파일로 해석되는지 검사(XC-1류 재발 방지) + seed/evaluate blockquote 앵커 존재 검사(XC-3 배선의 고정핀). ③ 확장 전 현재 데이터가 green인지 카운트로 확인하고, 확장 후 가짜 위반을 심어 ❌가 뜨는지 음성테스트 — 기존 R5~R9 확장 때 쓰던 절차를 이번 배치에도 명시 적용.
- **공백**: (4-c) 롤아웃·버전·캐시 경로가 빠졌다. 5개 플러그인을 한꺼번에 고치는데 버전 범프(R9는 패리티만 검사, 범프 강제는 없음), Codex 캐시 무효화(README 177행이 stale 캐시를 이미 경고), 제품 레포 4곳이 새 플러그인 버전을 받는 절차가 어느 제안에도 없다. 20개를 다 반영해도 제품 레포에서 옛 버전이 돌면 '아무것도 안 바뀐 것'이 된다 — 사용자가 가장 싫어하는 결과.
  - **보완 제안**: ① 20개 제안을 3~4개 배치 PR로 묶고 배치마다 5개 plugin.json version을 함께 범프하는 릴리스 체크리스트 1장 추가(린터 R9가 자동 검증). ② README에 '반영 확인' 3줄 절차 추가: 제품 레포에서 플러그인 재설치/캐시 클리어 → 버전 확인 → 대표 명령 1회 스모크 — 특히 ~/.codex 캐시 2곳 클리어를 스크립트 한 줄로. ③ 반영 후 검증은 실사용 1건으로: 제품 레포에서 feature:auto 한 바퀴를 실제로 돌려 seed→review 배선(UX-1, XC-3)이 체감되는지 확인하고 안 되면 즉시 롤백 — 정적 diff 리뷰만으로 '배선 완료' 선언 금지.

## 권장 로드맵

| 순서 | 내용 | 규모 |
|---|---|---|
| 0 | 제품 레포 4곳 `.harness/docs` 실태 진단 + evaluate→review 흡수 여부 결정 | 진단만 |
| 1 | seed·evaluate 실배선 + F2=seed 겸직 (UX-1/SH-1/XC-3) | M |
| 2 | auto 다이어트: fork 축소·검사 재사용·Codex 크기 예외·hotfix 예외 (BE-3/SH-3/UX-4/UX-5) | S×4 |
| 3 | 참조 위생 일괄 (XC-1 등 S급) + 린터 R10(참조 실재성) 신설 | S 다수 |
| 4 | 배치 PR + 5개 plugin.json 버전 동시 범프 + Codex 캐시 클리어 체크리스트 | 릴리스 |

## 순위별 제안 전체

### [UX-1] seed·evaluate를 트랙 명령 본문에 실배선 — F2가 seed를 겸하게 해 이중 질문 제거
- 점수 5.0/5 · effort M · risk low
- **무엇을**: review가 이미 배선된 방식(F7 상단 인용구)과 동일한 패턴으로: (1) 각 feature/maintenance auto·deep의 요구사항 스텝(F2 등)에 '이 스텝이 곧 /hb-shared:seed — .harness/artifacts/{track}/{identifier}/seed.md가 이미 있으면 읽고 재질문 금지, 없으면 이 스텝 산출물에 목표·범위·제외·완료기준 표를 포함해 seed를 겸한다'를 명시. (2) QA 스텝(F8.4 등)에 '이 검사가 곧 /hb-shared:evaluate — seed의 완료기준 표를 증거로 대조'를 한 줄 추가. (3) 트랙 산출물 목록과 5관문 산출물 이름을 정합(review-comments.md = [R2] 산출물, review-report.md = 관문 요약으로 관계 명시). 스텝 헤더 수는 불변으로 유지.
- **왜**: friction 1·2 해소 — CLAUDE.md 프로즈에만 있는 방법론이 실행 시 이중 질문(seed→F2 같은 질문 2회) 또는 조용한 생략으로 갈라지는 것을 막는다. '새 흐름은 기본 진입점에 연결' 교훈의 마무리.
- **파일**: `BE/commands/feature/auto.md`, `BE/commands/feature/deep.md`, `BE/commands/maintenance/auto.md`, `BE/commands/maintenance/deep.md`, `CM/commands/feature/auto.md`, `CM/commands/feature/deep.md`, `CM/commands/maintenance/auto.md`, `CM/commands/maintenance/deep.md`, `FE/commands/feature/auto.md`, `FE/commands/feature/deep.md`, `FE/commands/maintenance/auto.md`, `FE/commands/maintenance/deep.md`, `CHAT/commands/feature/auto.md`, `CHAT/commands/feature/deep.md`, `CHAT/commands/maintenance/auto.md`, `CHAT/commands/maintenance/deep.md`
- **심사 노트**: 그룹 canonical(BE-1·CM-4·XC-3 흡수): seed 이중질문 제거 + 기본 진입점 16곳 실배선 + 산출물 이름 정합 — '연결 안 하면 없는 것' 교훈의 마무리, 렌즈 정중앙. / 핵심 배선 — CLAUDE.md '자동 적용' 선언과 16개 파이프라인 본문의 괴리를 검증된 F7 blockquote 패턴으로 봉합, 이중 질문 금지 의미까지 명시. 헤더 불변 R3 안전. 단 (3) 산출물 이름은 XC-4 단일화로 대체. / 도메인 명령 16개에 seed/evaluate 참조 0건 실확인 — 검증된 review 배선 패턴 재사용 + 이중 질문 제거로 '기본 진입점에 연결' 교훈을 완성하는 최고 우선순위. 단 (3)항 이름 정합은 XC-4의 개명으로 갈음 권장.

### [XC-1] 3개 SKILL.md의 깨진 convention-check 참조를 hb-shared로 교정
- 점수 4.7/5 · effort S · risk low
- **무엇을**: BE/CM/CHAT SKILL.md의 'via `commands/maintenance/convention-check.md`'를 'via the hb-shared plugin (`SHARED/commands/maintenance/convention-check.md` when at repo root); the artifact remains `convention-check.md`'로 교체. 존재하는 경로만 남긴다.
- **왜**: Codex 진입점이 존재하지 않는 파일을 지시해 maintenance의 ADR 준수 체크 절차를 못 찾는 실동작 결함 제거. 한 줄 수정 3곳.
- **파일**: `BE/skills/hb-be/SKILL.md`, `CM/skills/hb-cm/SKILL.md`, `CHAT/skills/hb-chat/SKILL.md`
- **심사 노트**: 그룹 canonical — 3개 SKILL.md의 죽은 참조(파일 부재 확인됨)를 한 줄씩으로 제거. Codex는 CHAT dual gate의 절반이라 실동작 결함 수정. / 검증됨 — BE:37·CM:37·CHAT:46 모두 미존재 파일 참조(각 플러그인 maintenance/에 convention-check.md 없음 실측). Codex 진입점의 실동작 결함을 한 줄×3으로 제거 — 최고 효율. / BE:37·CM:37·CHAT:46 세 곳 모두 존재하지 않는 파일을 지시함을 실확인 — 3곳 1줄의 최소 수정으로 Codex 진입 경로의 실동작 결함 제거, 그룹의 canonical.

### [SH-1] seed 주문서를 evaluate/review의 1순위 기준 입력으로 연결
- 점수 4.3/5 · effort S · risk low
- **무엇을**: evaluate.md [E1] 기준 문서 목록 맨 위에 `.harness/artifacts/{track}/{identifier}/seed.md`(주문서 완료기준 표)를 추가하고, 우선순위를 seed.md → code-quality-guide.md → .harness/docs/*.yaml 순으로 명시. review.md [R2] 입력 목록에도 seed.md를 추가. 두 파일 모두에 'seed.md 없으면 스택 기준 문서로 그대로 진행(중단 금지)' 한 줄을 넣어 seed 없는 단독 호출을 graceful하게 처리. evaluate-report 템플릿의 '기준 출처'에 seed.md 선택지 추가.
- **왜**: seed.md:3의 약속('evaluate·review가 주문서를 기준으로 돈다')과 명령 본문의 단절을 봉합 — 주문서를 쓰면 실제로 검사에 쓰이므로 seed를 쓸 이유가 생기고, 안 썼을 때도 명시적 fallback으로 안 막힌다.
- **파일**: `SHARED/commands/evaluate.md`, `SHARED/commands/review.md`
- **심사 노트**: seed가 실제 검사 기준이 되게 하는 배선의 SHARED쪽 절반 — evaluate/review는 매 사이클 도는 기본 경로이고, fallback 명시로 세리머니 증가 없음. UX-1(도메인쪽)과 한 세트로 처리 권장. / 검증됨 — seed.md:3 약속과 달리 evaluate [E1]·review [R2] 입력에 seed.md 부재. graceful fallback 포함, S/low로 방법론 핵심 봉합. / seed.md:3의 약속('evaluate·review가 주문서 기준')과 evaluate[E1]/review[R2] 입력 목록의 단절을 실확인 — graceful fallback 포함이라 순서표 정합을 완성하는 핵심 봉합.

### [SH-3] review [R1] 자동검사 재사용 규칙 + [R3] Codex 크기 예외 명시
- 점수 4.3/5 · effort S · risk low
- **무엇을**: review.md [R1]에 '같은 HEAD에서 직전 evaluate가 통과했으면(evaluate-auto-log.txt 존재 + HEAD 일치) 자동검사 재실행을 생략하고 그 로그를 재사용한다' 조건 추가. [R3]에 'hotfix급·소규모 변경은 [R3]을 생략할 수 있다 — 리포트에 생략(사유) 명시' 추가(리포트 템플릿 :74는 이미 생략(사유)를 지원). evaluate.md [E3]에는 '심화 반박은 review [R4]가 담당하므로 여기선 핵심만' 1줄로 역할 경계 명시.
- **왜**: 표준 한 바퀴에서 테스트 스위트 2회 + 반박 2회 + 무조건 Codex 호출이라는 중복 세리머니가 hotfix에도 강제되는 문제 해소 — 무거우면 안 쓰게 되는 사용자가 관문을 우회하지 않고 계속 쓰게 만드는 핵심 수정. 같은-HEAD 조건이라 게이트 무력화 위험 없음.
- **파일**: `SHARED/commands/review.md`, `SHARED/commands/evaluate.md`
- **심사 노트**: 기본 관문에서 테스트 스위트 2회 + 무조건 Codex라는 중복 세리머니를 같은-HEAD 조건으로 안전하게 제거 — '무거우면 우회하게 되는' 문제의 직격탄, 렌즈 정중앙. / 검증됨 — evaluate [E2]와 review [R1]이 같은 스위트 2회 실행, [R3] Codex 무조건 호출, 템플릿 :73은 이미 생략(사유) 지원. 같은-HEAD 조건이라 게이트 무력화 없음. / evaluate→review 자동검사 2회·무조건 Codex 중복 실재 — 같은-HEAD 조건 재사용은 게이트 보존형 경량화이고 리포트 템플릿의 '생략(사유)'도 이미 지원함을 확인.

### [XC-4] 리뷰 관문 산출물 이름을 review-comments.md로 단일화
- 점수 4.3/5 · effort S · risk low
- **무엇을**: SHARED/commands/review.md의 [R5]와 산출물 템플릿에서 review-report.md를 review-comments.md로 개명(16개 도메인 문서·README·CLAUDE.md 전이 다이어그램이 이미 쓰는 이름으로 수렴). review-auto-log.txt는 유지하되 도메인 산출물 목록에도 '(review 관문 로그)'로 등재.
- **왜**: 같은 관문을 두 이름으로 스펙해 실행마다 산출물이 흔들리고 F8(리뷰 반영)이 review-comments.md를 못 찾는 구조적 위험 제거. 다수(17개 문서) 대신 1개 파일만 고치는 방향이라 최소 변경.
- **파일**: `SHARED/commands/review.md`, `README.md`
- **심사 노트**: review-report(SHARED) vs review-comments(도메인 17곳) 이름 흔들림 확인됨 — 1개 파일 수정으로 매 리뷰마다 도는 기본 경로의 산출물 참조를 안정화. / 검증됨 — review-report.md는 SHARED/commands/review.md 단독, review-comments.md는 25+개 파일 사용. 1파일 수정으로 수렴하는 최소 변경. UX-1(3)의 '두 이름 관계 명시'와 상충 — 이 단일화 방향을 우선. / SHARED review.md만 review-report.md, 도메인 문서·README·CLAUDE.md는 review-comments.md임을 실확인 — 17곳 대신 1파일만 고쳐 다수로 수렴하는 최소 변경의 모범, 산출물 규약 단일화.

### [CM-1] update-docs.md를 CM 스택으로 치환 + BE의 '편입 후 YAML 본문 제시' 규칙 포팅
- 점수 4.0/5 · effort S · risk low
- **무엇을**: (1) convention 스키마 주석을 verify.md와 일치하는 카테고리(GEN, EXP, REPO, TS, TEST, GIT)와 stacks(node, ts, express, socketio, mysql, redis, jest, all)로 교체. (2) context 좋은 예를 CM 사례(예: Socket.io 다중 replica에서 Redis adapter/sticky session 미설정으로 이벤트 유실)로 교체. (3) module-registry 스키마를 Express 레이어 구조(path: src/{controllers|services|repositories}/..., events: [...] 소켓 이벤트 필드, api_prefix 유지)로 교체하고 트랙 표의 '새 모듈/모델/API'를 '새 모듈/서비스/이벤트/API'로 수정. (4) BE update-docs.md:43의 'ADR 편입 시 특별 규칙 5. 편입 후 YAML 본문 제시 (필수)'를 그대로 추가.
- **왜**: 일상적으로 매 트랙 마지막에 호출되는 명령이 Django식 문서 항목을 생산하는 것을 차단하고, BE에서만 누리던 편입 결과 눈 확인 UX를 CM에서도 동일하게 받는다. 플러그인 내부 모순(update-docs ↔ verify/deep F5) 제거.
- **파일**: `CM/commands/shared/update-docs.md`
- **심사 노트**: 매 트랙 마지막에 자동으로 도는 update-docs가 Django 스키마·MariaDB 사례를 뿌리는 것을 차단 — 기본 경로에 연결된 실질 개선 + BE의 YAML 눈확인 UX 패리티. / 검증됨 — CM update-docs.md:47 'GEN, DJ, DRF, DOCK', :49 stacks django/drf, :69 Django/MariaDB 예시. 매 트랙 말미에 호출되는 명령의 순수 Django 잔재, S/low 고효율. / CM update-docs의 GEN/DJ/DRF 스키마·django/drf/docker stacks·MariaDB Django 예시 실확인 — verify.md 카테고리(GEN/EXP/REPO/TS)와의 플러그인 내부 모순 봉합 + BE 규칙5(:43) 포팅도 실재 확인.

### [CM-5] typecheck 명령을 한 가지로 통일
- 점수 4.0/5 · effort S · risk low
- **무엇을**: feature/auto.md F8(:133)과 maintenance/auto.md M6(:126)의 `npm run typecheck`를 deep/verify와 같은 `npx tsc --noEmit`으로 통일(또는 반대 방향으로 통일하되 tdd.md Pre-flight에 'typecheck 스크립트 존재 확인' 1줄 추가). 한 방향만 선택.
- **왜**: 대상 레포에 typecheck 스크립트가 없을 때 auto tier QA만 실패하는 비대칭 제거 — 가장 자주 쓰는 T1 경로가 환경 차이로 멈추는 일을 예방.
- **파일**: `CM/commands/feature/auto.md`, `CM/commands/maintenance/auto.md`
- **심사 노트**: 가장 자주 쓰는 T1 QA가 typecheck 스크립트 부재로 멈추는 실failure(auto:npm run typecheck vs verify:tsc --noEmit 확인됨)를 한 줄로 제거 — 저비용 고체감. / 검증됨 — auto :133/:125 npm run typecheck vs verify.md:14·deep:172 tsc --noEmit. 단 tdd.md:78·auto:85·deep:109에도 npm run typecheck가 있어 통일 범위를 약간 넓혀야 함. / auto의 npm run typecheck vs verify/deep의 tsc --noEmit 불일치 실확인 — 단 deep.md:109·tdd.md:78에도 npm run typecheck가 있어 파일 목록 보강 필요.

### [FE-1] 모드 분류(디자인/바인딩/혼합)를 feature 진입점 F1에 연결
- 점수 4.0/5 · effort S · risk low
- **무엇을**: feature auto/deep의 [F1] 사용자 확인 항목(branch명·base branch·변경 파일 수)에 '작업 모드: 디자인 구현 | API 바인딩 | 혼합(기본값)' 1줄을 추가하고, [F2] requirements.md와 완료 INDEX.md에 모드 필드를 기록하게 한다. SHARED seed.md 템플릿의 '트랙/식별자/크기' 블록에도 '작업 성격(FE=디자인|바인딩|혼합, 그 외 스택은 생략)' 한 줄을 추가한다. 새 ### 스텝 헤더는 만들지 않고 기존 스텝 내부 항목으로만 넣는다.
- **왜**: CLAUDE.md가 선언한 '시작 시 모드 분류'가 실제 파이프라인에 착지점이 없어 F7까지 모드가 암묵적이다. 진입 시 1줄 확인으로 이후 산출물 조건부(FE-2)와 리뷰 렌즈 선택이 자동으로 갈라져, 병렬로만 존재하던 모드 체계가 실사용된다.
- **파일**: `FE/commands/feature/auto.md`, `FE/commands/feature/deep.md`, `SHARED/commands/seed.md`
- **심사 노트**: 모드 분류의 F1/F2 착지는 UX-8과 중복 — seed 템플릿 필드 추가 아이디어만 UX-8에 얹어 통합. / 검증됨 — FE/CLAUDE.md:63 '시작 시 모드 분류' 선언이 F1(:35-38)에 착지점 없음. 기존 스텝 내부 항목이라 R3 안전, FE-2의 전제. / FE/CLAUDE.md:63 '시작(seed) 시 모드 분류' 선언에 파이프라인 착지점 부재 실확인 — seed 템플릿 연동까지 포함해 방법론(주문서) 정합적. UX-8의 해당 부분 흡수.

### [FE-2] F7 시각 산출물 3종을 모드 조건부로 전환 (N/A 대칭화)
- 점수 4.0/5 · effort S · risk low
- **무엇을**: feature auto [F7]·deep [F9]에서 visual-check.md/responsive-check.md/accessibility-notes.md에 api-binding-check.md와 대칭인 탈출구를 추가한다: 'API 바인딩 전용 작업(레이아웃·스타일 변경 없음)이면 각 파일에 "N/A: API 바인딩 전용" 한 줄로 표기'. 파일명 문자열은 문서에 그대로 남으므로 R8(디자인 산출물 4종 존재 검사)은 통과한다. 혼합/디자인 모드는 현행 유지.
- **왜**: 기존 화면에 API만 붙이는 작업에서 3개 viewport 반응형 체크·a11y 노트 강제는 auto tier의 lightweight 취지와 충돌하고, 실제로는 형식적으로 채워질 가능성이 높다. N/A 명시가 오히려 '검증 안 한 것'과 '해당 없는 것'을 구분해 산출물 신뢰도를 높인다.
- **파일**: `FE/commands/feature/auto.md`, `FE/commands/feature/deep.md`
- **심사 노트**: UX-8 후반부와 동일(N/A 대칭 탈출구, R8 통과 확인) — UX-8로 흡수. / 검증됨 — F7 step 6 api-binding만 N/A 탈출구 보유, 시각 3종(step 3-5)은 비대칭. R8은 파일명 grep -q라 문서 내 문자열 유지로 통과 — 정확한 린터 이해. / api-binding-check만 N/A 탈출구 보유(auto F7.6)하고 시각 3종은 없는 비대칭 실확인 — R8 grep -q 통과 설계 정확, 형식적 산출물 방지로 신뢰도 상승.

### [FE-3] update-docs.md 스키마 예시를 FE(React) 기준으로 교체
- 점수 4.0/5 · effort S · risk low
- **무엇을**: code-convention.yaml 스키마 주석을 '# GEN, COMP, HOOK, API, STYLE, A11Y, PATH, TEST' (verify.md와 일치)로, stacks 예시를 'react, cra, router, zustand, mui, capacitor, all'로 교체. module-registry.yaml 스키마를 CLAUDE.md:59가 말하는 레지스트리 구조(name/kind: route|page|component|hook|api-client|store|style, path: src/..., depends_on, api_endpoints, notes)로 교체. 트랙별 갱신 대상 표의 '새 모듈/모델/API'도 '새 route/컴포넌트/hook/API 클라이언트'로 수정. .harness/docs/ 경로 표기는 유지(R6).
- **왜**: 문서 갱신 명령이 Django 스키마를 보여주면 FE 레포의 4개 YAML이 BE 구조로 오염된다. verify.md 컨벤션 체크(COMP-/HOOK-...)와 module-registry 기반 스텝들(M1, F3 prior-art)이 실제로 동작하려면 스키마 정의가 FE와 일치해야 한다.
- **파일**: `FE/commands/shared/update-docs.md`
- **심사 노트**: CM-1과 같은 근거 — 매 트랙 도는 update-docs가 FE 레포 YAML을 BE 구조로 오염시키는 것을 차단, verify의 COMP-/HOOK- 컨벤션 체크가 실제로 동작하게 함. / 검증됨 — FE update-docs.md:47 'GEN, DJ, DRF, DOCK' vs verify.md의 COMP-/HOOK-. FE YAML의 BE 오염 차단, S/low. / FE update-docs도 GEN/DJ/DRF·django/drf/docker 스키마 그대로임을 실확인 — CM-1의 FE판, module-registry 기반 스텝이 실동작하기 위한 전제.

### [CH-3] ADR 편입 경로 단일화 — planning 승인이면 adr:new 재승인 생략 명문화
- 점수 4.0/5 · effort S · risk low
- **무엇을**: adr/new.md 5행을 'planning 승인 게이트(P4/P7)를 이미 통과한 draft는 D3 승인을 중복하지 않고 D1 충돌체크+D4 편입만 수행한다. planning을 거치지 않은 직접 등록만 D2~D3 전체를 밟는다'로 수정. planning/auto.md P4·deep.md P7에는 '이 편입 = adr:new의 D4에 해당(supersede 처리 포함)' 1줄 크로스레퍼런스 추가(스텝 헤더 수 4/7 불변 — 문장만). CLAUDE.md 31행에 두 경로의 관계 1줄 명시.
- **왜**: 이중 승인 핑퐁 제거(세리머니 축소) + 어느 문서를 따라도 같은 답이 나오게 함. lightweight 선호와 정합.
- **파일**: `CHAT/commands/adr/new.md`, `CHAT/commands/planning/auto.md`, `CHAT/commands/planning/deep.md`, `CHAT/CLAUDE.md`
- **심사 노트**: planning→ADR 기본 경로의 이중 승인 핑퐁을 명문화로 제거 — 순수 세리머니 감축, S 효트로 즉효. / 검증됨 — planning auto P4는 update-docs로 직접 편입, adr/new는 '바로 넣지 않고 이 트랙으로' — 실제 모순. 이중 승인 제거는 사용자 lightweight 선호와 정합, S/low. / planning P4 승인 게이트와 adr:new 자체 승인(D3)의 이중 승인 구조 실확인 — 어느 문서를 따라도 같은 답이 나오게 하는 세리머니 축소, 정합적.

### [XC-3] seed/evaluate를 review와 같은 방식(blockquote 앵커)으로 16개 파이프라인에 인라인 연결
- 점수 4.0/5 · effort M · risk low
- **무엇을**: 각 도메인 feature/maintenance auto·deep의 F1(상태 점검)류 스텝에 '> 시작 전 주문서 = /hb-shared:seed 방법. 산출물 `seed.md`를 이 디렉토리에 남긴다(작으면 3줄 약식)'를, QA/회귀 스텝에 '> 이 검사 = /hb-shared:evaluate 방법(증거 기반, evaluate-report.md)'를 blockquote로 추가. 새 `### [X#]` 헤더는 만들지 않는다(R3 스텝 수 불변). 각 문서의 산출물 목록에 seed.md를 '(약식 가능)'으로 추가.
- **왜**: CLAUDE.md의 '자동 적용' 주장과 실행 소스(명령 문서)의 불일치 해소. review 연결 때 검증된 패턴 재사용이라 사용자 교훈('기본 진입점에 연결') 그대로. 앵커 방식이므로 세리머니 증가 없음.
- **파일**: `BE/commands/feature/auto.md`, `BE/commands/feature/deep.md`, `BE/commands/maintenance/auto.md`, `BE/commands/maintenance/deep.md`, `CM/commands/feature/auto.md`, `CM/commands/feature/deep.md`, `CM/commands/maintenance/auto.md`, `CM/commands/maintenance/deep.md`, `FE/commands/feature/auto.md`, `FE/commands/feature/deep.md`, `FE/commands/maintenance/auto.md`, `FE/commands/maintenance/deep.md`, `CHAT/commands/feature/auto.md`, `CHAT/commands/feature/deep.md`, `CHAT/commands/maintenance/auto.md`, `CHAT/commands/maintenance/deep.md`
- **심사 노트**: UX-1과 같은 16개 파이프라인 앵커 배선 — 이중질문 제거·산출물 이름 정합까지 포함한 UX-1이 상위 호환이라 흡수. / 올바른 전 도메인 배선안이나 UX-1과 사실상 동일 — 재질문 금지 의미까지 명시한 UX-1을 대표로 흡수. / 16개 파이프라인 blockquote 앵커는 검증된 review 배선 패턴의 올바른 재사용이나, 재질문 금지·산출물 정합까지 포함한 UX-1이 상위호환 — 흡수.

### [UX-2] F1 브랜치 확인 핑퐁을 opt-out 보고로 전환
- 점수 4.0/5 · effort S · risk low
- **무엇을**: 4개 플러그인 feature auto·deep의 F1 '사용자에게 다음을 확인한다'(BE/commands/feature/auto.md:35-38)를 'resolve한 branch·base·변경 파일 수를 한 줄로 보고하고 이의가 없으면 기본값으로 진행한다(질문으로 멈추지 않는다)'로 교체. maintenance 쪽 동일 패턴도 함께 정리.
- **왜**: git으로 방금 읽은 값을 되물어보는 순수 핑퐁 1회를 전 트랙에서 제거 — '연속 질문 = 이탈 신호'인 사용자에게 즉효.
- **파일**: `BE/commands/feature/auto.md`, `BE/commands/feature/deep.md`, `CM/commands/feature/auto.md`, `CM/commands/feature/deep.md`, `FE/commands/feature/auto.md`, `FE/commands/feature/deep.md`, `CHAT/commands/feature/auto.md`, `CHAT/commands/feature/deep.md`
- **심사 노트**: git으로 방금 읽은 값을 되묻는 순수 핑퐁 제거는 즉효 — BE-3(c)와 동일하므로 BE-3 확장판으로 흡수. / 검증됨 — BE auto:35-38 (FE/CHAT 동일) git으로 방금 읽은 값 되묻기. opt-out 보고 전환은 '질문 루프 금지' 메모리 교훈과 정합, 순수 마찰 제거. / F1 '사용자에게 확인'(auto:35-38) 실확인 — git으로 방금 읽은 값 재질문 제거는 '질문 루프 금지' 교훈 직결, opt-out 보고라 관문 훼손 없음.

### [UX-4] 문서-전용 스텝의 워크트리 강제 해제 — feature:auto의 fork 6회를 3회로
- 점수 4.0/5 · effort S · risk low
- **무엇을**: F2(요구사항)·F3(설계의도)처럼 .md 산출물만 쓰는 스텝의 'worktree(fork)를 생성한다'를 '메인에서 직접 수행(코드 수정 없음). 대규모 조사가 필요할 때만 Sub-agent 위임'으로 교체. 코드 건드리는 F4~F6·F8은 fork 유지. 스텝 헤더 수·이름 불변이라 R3 안전. FE hotfix H1의 fork도 동일하게 '필요 시'로 완화.
- **왜**: friction 2의 워크트리 처닝 제거 — 엔드포인트 하나에 worktree 생성·해체 6회는 체감 지연과 실패 표면만 늘린다. seed.md도 '기본은 메인이 혼자, 얇게'가 원칙이므로 방법론과도 정합.
- **파일**: `BE/commands/feature/auto.md`, `CM/commands/feature/auto.md`, `FE/commands/feature/auto.md`, `CHAT/commands/feature/auto.md`, `FE/commands/maintenance/hotfix.md`, `BE/commands/maintenance/hotfix.md`, `CM/commands/maintenance/hotfix.md`, `CHAT/commands/maintenance/hotfix.md`
- **심사 노트**: 문서-전용 스텝의 worktree 처닝 제거(6회→3회)는 체감 지연 직격 — BE-3(a)와 동일하므로 BE-3로 흡수. / 검증됨 — F2/F3 문서-전용 스텝과 hotfix H1까지 Fork 강제(BE·FE 실측). 헤더 불변 R3 안전, seed.md '기본은 메인이 얇게' 원칙과 정합 — 체감 최대의 S 수정. / 문서 전용 F2/F3의 fork 강제 실확인 — seed.md '기본은 메인이 혼자, 얇게' 원칙과 정합하고 코드 스텝 fork는 유지라 안전한 세리머니 축소, BE-3(a)의 안전판.

### [UX-5] 방법론 연결 섹션에 T0 hotfix 예외를 명문화
- 점수 4.0/5 · effort S · risk low
- **무엇을**: 4개 CLAUDE.md '방법론 연결' 섹션에 한 줄 추가: 'T0 hotfix는 예외 — seed는 약식 3줄(hotfix-reproduction.md 서두)로 갈음하고, evaluate·review 5관문은 생략한다(H3 단위 테스트 게이트가 완료 조건). 5관문이 필요해 보이면 그 자체가 :auto 에스컬레이션 신호다.' seed.md의 'hotfix급은 3줄' 문구와 정합.
- **왜**: friction 3 해소 — hotfix.md('리뷰 전부 스킵')와 CLAUDE.md('머지 전 5관문')의 충돌로 한 줄 수정에 Codex 교차검증이 돌아버리는 최악의 세리머니 사고를 차단.
- **파일**: `BE/CLAUDE.md`, `CM/CLAUDE.md`, `FE/CLAUDE.md`, `CHAT/CLAUDE.md`
- **심사 노트**: 그룹 canonical(BE-2 흡수): 오타 수정에 Codex 교차검증이 붙는 최악의 세리머니 사고를 4개 도메인 한 줄씩으로 차단 — T0 기본 경로에 자동 효과. / 검증됨 — hotfix.md '리뷰 전부 스킵' vs 4개 CLAUDE.md '머지 전 5관문' 충돌. BE-2 상위집합, 한 줄×4로 최악의 세리머니 사고 차단. / hotfix '3단계 외 아무것도 안 함' vs CLAUDE.md '머지 전 5관문' 충돌을 4개 CLAUDE.md에서 실확인 — T0 예외 명문화는 3-tier 취지 그대로, BE-2 흡수.

### [UX-6] CHAT: F7 5관문과 F8 dual gate의 Codex 이중 호출을 단일 호출로 합치기
- 점수 4.0/5 · effort S · risk med
- **무엇을**: CHAT feature auto/deep의 F8.5와 review-gates.md G2를 수정: F7 [R3]에서 생성된 Codex 결과(codex-review.md)를 dual gate의 G2 입력으로 재사용하고, 리뷰 반영으로 코드가 바뀐 경우에만 변경분 diff로 Codex를 재실행한다고 명시. 게이트 의미(테스트+lint+build+양 엔진 blocking 0)는 그대로 유지 — 호출 횟수만 합친다.
- **왜**: friction 4의 절반 해소 — 같은 diff에 Codex가 2회 도는 것은 시간·비용 순손실이고 dual gate의 독립성 가치는 '독립 엔진'이지 '중복 실행'이 아니다. 최대 3라운드 루프와 결합하면 auto tier가 deep보다 무거워지는 역전을 막는다.
- **파일**: `CHAT/commands/feature/auto.md`, `CHAT/commands/feature/deep.md`, `CHAT/commands/shared/review-gates.md`
- **심사 노트**: 그룹 canonical(CH-7·XC-5 흡수): 같은 diff에 Codex 2회 도는 확인된 이중 구조(F7 R3 + F8.5 G2)를 1회로 — 순수 시간·비용 절감, 게이트 의미는 유지. / 검증됨 — CHAT F7 blockquote [R3] Codex + F8 dual gate G2 Codex로 같은 diff 2회 호출. 재사용+변경분만 재실행은 게이트 의미 보존 — med risk지만 정합적. / F7 [R3] Codex 자동 호출 + F8.5 dual gate G2 Codex의 같은 diff 이중 호출 실확인 — 코드 변경 시에만 재실행 조건으로 dual gate 의미(독립 엔진)를 보존하며 중복만 제거.

### [BE-1] seed/evaluate를 review처럼 스텝 본문에 blockquote로 실배선
- 점수 3.7/5 · effort S · risk low
- **무엇을**: review가 이미 쓰는 패턴(F7/M7 상단 blockquote)을 그대로 재사용한다. (1) feature/auto.md F2와 maintenance/auto.md M1 상단에 '> 이 스텝 = /hb-shared:seed: .harness/artifacts/{track}/{id}/seed.md가 있으면 그것을 요구사항 소스로 사용하고 질문을 반복하지 않는다. 없으면 이 스텝 산출물(requirements.md)이 약식 seed를 겸한다 — 별도 seed 실행 불필요' 추가. (2) F8/M6 QA 상단에 '> 이 QA = /hb-shared:evaluate [E2] 자동검사: 결과 요약을 INDEX.md에 evaluate 겸함으로 명시' 추가. deep.md 두 곳도 동일. 새 ### 스텝 헤더를 만들지 않으므로 R3 스텝 수 불변.
- **왜**: CLAUDE.md 선언과 명령 본문의 괴리를 없앤다 — seed를 쓰면 이중 질문, 안 쓰면 방법론이 없는 것과 같아지는 현재 상태를 '한 번만 묻고 겸한다'로 정리. 과거 교훈(새 흐름은 기본 진입점에 연결) 그대로.
- **파일**: `BE/commands/feature/auto.md`, `BE/commands/feature/deep.md`, `BE/commands/maintenance/auto.md`, `BE/commands/maintenance/deep.md`, `BE/CLAUDE.md`
- **심사 노트**: UX-1과 동일 목표(F2=seed 겸함, 검증된 blockquote 패턴)의 BE 부분집합 — 전 도메인판인 UX-1로 흡수. / 진단 정확(F7 blockquote 패턴 실재, seed/evaluate 미배선 확인)하나 BE 한정 — 16파일 전 도메인판 UX-1로 흡수. / 'F2가 seed를 겸함 + 재질문 금지' 설계는 4개 배선안 중 최상의 의미론이나, 16개 파이프라인 전체를 포괄하는 UX-1로 흡수 (BE-1의 겸함 문구를 UX-1 구현에 채택 권장).

### [BE-3] auto tier를 실제로 가볍게: fork 축소 + tier별 리뷰 깊이 분리 + 확인 게이트 축소
- 점수 3.7/5 · effort M · risk med
- **무엇을**: (a) feature:auto F4~F6(TDD)과 maintenance:auto M5/M5.5의 '(Fork)'를 '(메인, feature branch 직접)'으로 바꾸고 worktree 생성/정리 문장을 제거 — fork 격리는 deep 전용으로 명시. (b) F7/M7 리뷰 blockquote를 tier-aware로 수정: auto는 '울트라코드 OFF 모드 — 단일 Sub-agent 순차 리뷰, R3 Codex 교차검증은 사용자가 요청하거나 [p1] 발견 시에만', deep은 현행 full 5단계 유지(SHARED/commands/review.md:11-13의 ON/OFF 정의를 그대로 참조). (c) F1/M1의 '사용자에게 확인한다'를 '요약 보고 후 자동 진행, 이의 시 중단'으로 변경. 헤더 개수 불변이라 R3 통과, CM 대응 파일도 같은 편집을 미러링 권장.
- **왜**: auto가 문서만 lightweight이고 실행은 deep급(worktree 6회 + 매번 Codex 관문)인 현재 상태가 '실제로 안 쓰게 되는' 최대 원인. Django 레포에서 fork마다 pytest 환경을 살리는 비용이 특히 크다.
- **파일**: `BE/commands/feature/auto.md`, `BE/commands/maintenance/auto.md`, `CM/commands/feature/auto.md`, `CM/commands/maintenance/auto.md`
- **심사 노트**: auto가 문서만 lightweight이고 실행은 deep급(fork 6회 + 매번 Codex 관문 + F1 확인 핑퐁)인 최대 마찰을 3방향으로 직격 — 매일 체감이 가장 큰 제안. UX-2/UX-4를 흡수해 4도메인으로 확장 적용. / fork 6회 확인·문제 실재하나 BE/CM만 다뤄 4도메인 비대칭. (a)는 UX-4, (c)는 UX-2로 흡수, (b) tier별 리뷰 깊이(review.md ON/OFF 인용)만 고유 가치로 편입. / fork 축소는 UX-4, 확인 게이트는 UX-2와 중복이고, (b) auto의 R3 조건부화는 '머지 전 5단계 관문' 선언을 약화시키는 방법론 긴장 — 안전한 부분만 UX-2/UX-4로.

### [CM-2] planning 보조 명령 3종(scope/interview/decision-draft)의 BE 도메인 잔재를 CM 도메인으로 치환
- 점수 3.7/5 · effort S · risk low
- **무엇을**: (1) scope.md stakeholders 템플릿을 planning/deep.md P1과 일치시킴 — 사용자 유형: 커뮤니티 사용자/작성자/관리자·모더레이터, 시스템 유형: CM 자체(Express)/메인 BE(Django, hb-be)/MySQL·Redis/Socket.io 클라이언트(WebView·네이티브)/인프라(Docker Swarm/Azure). (2) interview.md '연결' 질문을 '기존 커뮤니티 기능·메인 BE와 어떻게 연결되는가' + deep P2의 실시간성 질문('Socket.io 이벤트 필요 여부', '동시 접속·이벤트 처리량')으로 교체하고 연결표 예시 모듈을 booking/payment → post/notification/websocket으로. (3) decision-draft.md 좋은 예를 커뮤니티 사례(예: 실시간 알림 중복 발송)로 교체. 스텝 헤더(### [Xn])는 추가/삭제하지 않음.
- **왜**: planning:deep 실행 시 P1/P2가 이 템플릿을 그대로 채우므로, 지금은 Node 커뮤니티 레포 기획 산출물에 프리다이버/Innopay/MariaDB가 들어간다. deep.md 본문과 보조 명령의 모순을 없애 산출물 품질과 신뢰를 회복.
- **파일**: `CM/commands/planning/scope.md`, `CM/commands/planning/interview.md`, `CM/commands/planning/decision-draft.md`
- **심사 노트**: planning deep P1/P2가 프리다이버/Innopay/booking 템플릿을 그대로 채우는 실오염(확인됨) 수정 — 실익 확실하나 planning 빈도가 feature보다 낮음. / 검증됨 — scope.md:45 프리다이버, :53-56 Django/MariaDB/Innopay, interview.md:60-61 booking/payment. planning 산출물 오염 직결, 스텝 헤더 불변으로 R3 안전. / CM planning에 프리다이버/Innopay/MariaDB(scope:45,54,56)·booking/payment(interview:60-61) 잔재 실확인 — planning:deep 산출물 오염을 막는 실질 품질 수정.

### [FE-5] CHAT/BE 복붙 잔재 정리 + 스택 선언 통일(MUI 명시)
- 점수 3.7/5 · effort S · risk low
- **무엇을**: (1) planning/deep.md:40 '(동시 접속, 메시지/이벤트 처리량)'→'(초기 로드 시간, 번들 크기, 렌더 성능)', :74와 alternatives.md:50 '브라우저 이벤트 스키마 변경'→'라우팅/전역 상태(Zustand) 구조 변경'으로 FE 의미화. (2) interview.md 연결점 예시를 booking/payment→'메인 BE API, 인증(JWT), 결제 화면' 등 FE 관점으로. (3) FE/CLAUDE.md 프로젝트 스택에 'UI: MUI (+ 일부 Bootstrap)' 항목을 추가하고 research.md:28, planning/deep.md P3의 스택 나열을 동일 문구로 통일. (4) reflect.md 예시 경로를 src/hooks/usePost.js, src/pages/PostPage.jsx 등 FE 네이밍으로 교체.
- **왜**: 기계 치환 잔재('브라우저 이벤트 스키마')는 planning 시 에이전트가 무의미한 분석 항목을 채우게 만들고, 기준 문서에 없는 MUI는 디자인 구현 모드에서 컨벤션·리뷰 렌즈가 실제 컴포넌트 라이브러리를 못 짚게 한다. R8은 hb-cm/.test.ts 문자열만 검사하므로 전부 안전한 수정.
- **파일**: `FE/commands/planning/deep.md`, `FE/commands/planning/alternatives.md`, `FE/commands/planning/interview.md`, `FE/commands/planning/research.md`, `FE/commands/feature/reflect.md`, `FE/CLAUDE.md`
- **심사 노트**: 기계 치환 잔재('브라우저 이벤트 스키마')와 MUI 누락은 planning·리뷰 산출물 품질을 깎는 실제 결함이나 빈도 보통 — CH-5류 잔재 정리와 한 PR로 묶으면 효율적. / 검증됨 — planning/deep.md:40 '메시지/이벤트 처리량', :74·alternatives.md:50 '브라우저 이벤트 스키마', interview booking/payment, FE/CLAUDE.md에 MUI 부재(research.md:28에만 존재). R8 안전. / '동시 접속·메시지/이벤트 처리량'(deep:40)·'브라우저 이벤트 스키마'(deep:74, alternatives:50) CHAT 잔재와 FE/CLAUDE.md MUI 부재 실확인 — planning 산출물 무의미 항목 제거.

### [CH-1] feature:deep을 CHAT 네이티브로 재작성 (계약 스텝 삽입 + 유령 산출물 정리)
- 점수 3.7/5 · effort M · risk low
- **무엇을**: 제목 '(CM)'→'(CHAT)'. auto의 F3b와 동일한 '계약 점검 pre' 스텝을 F4(설계의도)와 F6(Red) 사이에 신설(스텝 12개 — FE deep과 동일 수). F11에 auto F8.4-5와 같은 '계약 post 검증 + dual review gate' 절차를 기존 스텝 내부에 추가. 산출물 목록의 integration-plan/migration-review/websocket-contract-diff/api-contract-diff/rollback-plan/release-checklist는 생성 주체 스텝을 지정하거나(계약 pre 스텝과 F11에 배정) '해당 변경 동반 시에만(조건부)'로 명시해 약속-절차 불일치 해소.
- **왜**: 가장 무거운 feature 작업(BE/FE 연동·migration·Socket 변경)이 오히려 auto보다 계약 규율이 약한 역전을 해소. deep을 실제로 믿고 쓸 수 있게 됨.
- **파일**: `CHAT/commands/feature/deep.md`
- **심사 노트**: 가장 무거운 작업이 auto보다 계약 규율이 약한 역전(deep에 F3b 부재 확인)은 실결함이나, 스텝 추가 + deep 저빈도라 일상 체감은 제한적. / 검증됨 — deep 제목 '(CM)', F3b 부재(auto만 보유), 산출물 목록에 생성 주체 없는 유령 6종(integration-plan 등) 실재. R3는 CHAT feature≥BE라 스텝 추가 안전. 가장 무거운 트랙의 역전 해소. / deep '(CM)' 제목·인라인 계약 스텝 부재·생성 주체 없는 유령 산출물 6종 실확인 — 12스텝=FE deep 동수로 R3(FE·CHAT≥BE=11) 통과, 가장 무거운 트랙의 계약 역전 해소.

### [CH-2] maintenance:deep에 계약 정합성·dual gate 연결
- 점수 3.7/5 · effort S · risk low
- **무엇을**: 새 스텝 헤더 추가 없이(R3 4도메인 대칭 유지: 스텝 10개 고정) M6 수정계획에 '계약/경계 영향 시 contract-check pre 수행' 문장, M9 리뷰 입력에 contract-check(post) 추가. 산출물 목록에 contract-check.md(조건부)와 codex-review.md 추가, auto 177행과 동일한 '완료는 review-gates dual gate 통과' 하단 주석 추가. 제목 '(CM)'→'(CHAT)'.
- **왜**: 소켓 이벤트를 건드릴 확률이 가장 높은 트랙(읽음 처리·메시지 중복·장애급)에서 계약 파손이 게이트 없이 통과하는 구멍을 막음.
- **파일**: `CHAT/commands/maintenance/deep.md`
- **심사 노트**: 헤더 추가 없이 구멍만 메우는 안전한 수정이나 maintenance:deep 저빈도 — CH-1과 함께 처리하면 저렴. / 검증됨 — maint auto는 contract-check·codex-review·dual gate 주석(:177) 보유, deep은 hb-shared blockquote(:278)뿐. 헤더 불변 R3 안전, S 고효율. / maintenance deep에 contract-check/dual gate 미연결 확인 — 헤더 불변 배선이라 R3 4도메인 대칭 유지, 소켓 파손 확률 최고 트랙의 게이트 구멍을 막음.

### [CH-5] CM 잔재 일괄 치환 (~25곳 기계적 수정)
- 점수 3.7/5 · effort S · risk low
- **무엇을**: 9개 파일 제목 '(CM)'→'(CHAT)', 'BUCCL-CM-42/99'→'BUCCL-CHAT-42/99'(4곳), rca.md 'CM(Node/TS/Express) 특화'→'CHAT 스택(Node/TS/Express/Socket.io) 특화', reproduce.md 'CM 특화 재현 체크리스트'→'CHAT 특화', planning/interview.md 연결 질문·예시 모듈을 room/message/attachment/BE API 경유로, planning/scope.md 시스템 유형 표를 chat 구성(Express/Socket.io 클라이언트/MySQL chat_buccl_dev/Redis/메인 BE API/Azure Blob)으로, feature/reflect.md 판정 예시 경로를 message.service.ts류로 교체. 스텝 헤더(### [X#]) 수 불변 — R3 안전. 메모리 교훈대로 리드가 직접 편집(에이전트 팀 불필요).
- **왜**: 명령을 연 순간의 도메인 혼동 제거 + planning 인터뷰가 예약/결제 대신 chat 도메인을 묻게 됨(실질 품질 개선).
- **파일**: `CHAT/commands/feature/deep.md`, `CHAT/commands/feature/reflect.md`, `CHAT/commands/maintenance/deep.md`, `CHAT/commands/maintenance/auto.md`, `CHAT/commands/maintenance/hotfix.md`, `CHAT/commands/maintenance/rca.md`, `CHAT/commands/maintenance/reproduce.md`, `CHAT/commands/maintenance/impact-analysis.md`, `CHAT/commands/planning/alternatives.md`, `CHAT/commands/planning/deep.md`, `CHAT/commands/planning/research.md`, `CHAT/commands/planning/interview.md`, `CHAT/commands/planning/scope.md`
- **심사 노트**: '(CM)' 제목 9곳·BUCCL-CM 예시 확인됨 — 기계적 치환 중 interview가 booking/payment 대신 chat 도메인을 묻게 되는 부분만 실질 개선, 나머지는 위생. / 검증됨 — (CM) 제목 9곳·BUCCL-CM-42/99·'CM 특화' 등 잔재 다수 실측. 기계적 치환, 헤더 불변 R3 안전, 메모리 교훈(리드 직접 편집)까지 반영. / '(CM)' 제목 4파일·BUCCL-CM 식별자·booking/payment 인터뷰 잔재 실확인 — 기계 치환은 리드 직접 수행(메모리 교훈)으로 저위험 고가치, R3 안전.

### [CH-7] 게이트 어휘 단일화 — review-gates에 G↔R 매핑 + hb-shared 렌즈에 CHAT 추가
- 점수 3.7/5 · effort S · risk low
- **무엇을**: review-gates.md에 'hb-shared 5단계 관문과의 관계' 1절 추가: 1~4(verify)=R1, G1=R2, G2=R3(문구를 'Claude Code가 codex CLI를 자동 호출, 미설치 시 생략 사유 기록'으로 R3와 일치시켜 자동/수동 상충 제거), G3=R4~R5 수정 루프. SHARED/commands/review.md의 R2 렌즈 목록에 'CHAT = 계약 정합성(websocket/api/db) / 실시간 동시성 / 경계(BE DB 금지·첨부) / 구조' 추가, 완료기준 출처(61행)에 'CHAT = 테스트·lint·build + dual gate(review-gates)' 추가. SHARED/commands는 R3 대칭 검사 대상 아님 — 린터 안전.
- **왜**: 같은 관문을 두 어휘로 설명하는 혼선 제거 + chat의 핵심(계약 렌즈)이 공통 관문에서 실제로 검사되게 함. G2의 '사용자가 Codex 세션에서 수행' 같은 수동 개입 여지를 없애 핑퐁 감소.
- **파일**: `CHAT/commands/shared/review-gates.md`, `SHARED/commands/review.md`
- **심사 노트**: UX-6/XC-5와 같은 문제(이중 게이트 어휘·중복 실행) — 실행 횟수를 실제로 줄이는 UX-6를 canonical로 통합, G↔R 매핑 표는 그 안에 1절로. / 검증됨 — G2 '사용자가 Codex 세션에서 수행' vs R3 '자동 호출' 실제 상충. SHARED/commands는 R3 대칭 검사 밖(BE↔CM만 비교) — 린터 이해 정확. UX-6과 세트로. / G2 '사용자가 Codex 세션에서 수행' vs R3 '자동 호출' 상충 실확인 — 한 관문 두 어휘를 G↔R 매핑으로 봉합하고 R3의 graceful skip과도 정합, XC-5보다 우수.

### [XC-2] hb-shared 핵심 4명령을 Codex 등록 레이어에 노출 + 설치본 깨진 설계문서 포인터 수정
- 점수 3.7/5 · effort S · risk low
- **무엇을**: SHARED/skills/hb-shared/SKILL.md의 Source Of Truth·Command Mapping에 seed/evaluate/review/evolve 4개(`commands/seed.md` 등 top-level 경로)를 추가하고, .codex-plugin/plugin.json defaultPrompt에 'hb-shared review로 이 diff 리뷰해줘' 류 1~2개 추가, 양쪽 plugin.json·marketplace.json 설명에 순서표 한 줄 반영. 동시에 SHARED/CLAUDE.md:34의 docs/SHARED-CORE-DESIGN.md 참조를 'dev-harness 리포의 docs/…(설치본 미포함)'로 명시.
- **왜**: hb-shared의 존재 이유인 방법론 순서표가 Codex 쪽에서 발견 불가능한 상태 해소. 설명 필드는 어떤 린터 규칙도 검사하지 않아 안전.
- **파일**: `SHARED/skills/hb-shared/SKILL.md`, `SHARED/.codex-plugin/plugin.json`, `SHARED/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `SHARED/CLAUDE.md`
- **심사 노트**: 그룹 canonical(SH-4 흡수) — hb-shared의 존재 이유인 순서표가 Codex에서 발견 불가능한 drift 해소. 실하지만 등록 문서 수준이라 체감은 보통. / SH-4 상위집합 + SHARED/CLAUDE.md:34 docs/SHARED-CORE-DESIGN.md가 설치본에서 죽은 포인터임까지 처리. 설명 필드는 R7/R9 검사 밖 확인 — 안전. / SHARED SKILL/codex plugin.json에 seed/evaluate/review/evolve 부재 + CLAUDE.md의 docs/SHARED-CORE-DESIGN.md가 설치본 미포함 경로임을 실확인 — hb-shared 존재 이유의 발견 가능성 회복, SH-4 흡수.

### [UX-7] CHAT: 비파괴(additive) 계약 변경의 fast-path — feature:auto 안에서 계약 정의→편입 제안까지 한 번에
- 점수 3.7/5 · effort M · risk med
- **무엇을**: contract-check.md pre 절차와 feature auto/deep F3b에 추가: 변경이 additive(필드·이벤트 추가, breaking 아님)면 별도 /hb-chat:contract:* 실행을 요구하지 않고 F3b가 W2 계약 명세 형식으로 diff를 작성해 contract-check.md pre 섹션에 포함, 사용자 승인 1회로 update-docs 편입까지 이어간다. breaking이면 기존대로 contract:websocket/:api + adr:new 체인 유지. 계약 diff 산출물은 review/ws-{slug}/가 아니라 해당 feature 아티팩트 디렉토리에 남긴다. 동시에 CHAT/CLAUDE.md:63의 {feature-slug}를 명령 본문과 같은 {branch-name}으로 통일.
- **왜**: friction 4 해소 — 메시지 타입 추가마다 명령 3~5개를 수동 체인하는 대신, 위험한 경우(breaking)에만 무거운 경로를 태운다. [p1] 게이트(미등록 이벤트 차단)는 그대로라 contract-first 원칙은 유지된다.
- **파일**: `CHAT/commands/feature/contract-check.md`, `CHAT/commands/feature/auto.md`, `CHAT/commands/feature/deep.md`, `CHAT/CLAUDE.md`
- **심사 노트**: additive 계약 변경(가장 흔한 케이스)의 명령 3~5개 수동 체인을 승인 1회로 접되 breaking·[p1] 가드는 유지 — 위험 기반 차등화라 렌즈 부합. / {feature-slug}(CLAUDE.md:63) vs {branch-name} 불일치 검증됨. additive fast-path는 [p1] 게이트 유지 전제로 타당하나 계약-first 원칙의 예외 도입이라 med risk — breaking 판정 기준을 문서에 명확히 박는 조건부. / additive/breaking 분기로 계약 세리머니를 위험도에 비례시키고 [p1] 미등록 이벤트 게이트는 유지 — contract-first 원칙 보존, {feature-slug}(CLAUDE.md:63)↔{branch-name} 불일치도 실확인된 덤.

### [UX-8] FE: 모드 분류를 F2 스텝 내용에 명시하고 시각 산출물 3종에 역방향 N/A 탈출구 추가
- 점수 3.7/5 · effort S · risk low
- **무엇을**: (1) FE feature auto·deep의 F2(또는 F1) 본문에 '이 작업이 디자인 구현/API 바인딩/혼합 중 무엇인지 분류해 requirements.md 서두에 기록한다' 추가(새 스텝 헤더 없이 기존 스텝 항목으로 — R3 안전). (2) F7 스텝 3~5(visual/responsive/a11y)에 api-binding-check와 대칭인 탈출구 추가: '순수 API 바인딩 작업(화면 변화 없음)이면 "N/A: API 바인딩 전용 — 화면 diff 없음"으로 표기'. 파일명 4종은 문서에 그대로 남으므로 R8의 grep -q 검사 통과.
- **왜**: friction 5 해소 — 'FE는 디자인/바인딩 두 모드'라는 사용자 본인의 구분이 명령 레벨에서 완성된다. 순수 바인딩 작업에서 무의미한 반응형 캡처 3종을 만들다 이탈하는 것을 방지.
- **파일**: `FE/commands/feature/auto.md`, `FE/commands/feature/deep.md`
- **심사 노트**: 그룹 canonical(FE-1·FE-2 흡수): 사용자 본인이 짚은 FE 2모드 구분을 명령 레벨에 착지시키고 바인딩 작업의 무의미한 시각 산출물 3종을 N/A로 — R8 통과 확인됨. / FE-1(모드 분류)+FE-2(N/A 대칭)와 동일 내용의 축약판 — seed 템플릿·INDEX 기록까지 포함한 FE-1/FE-2 쌍으로 흡수. / FE-1(모드 착지)+FE-2(N/A 대칭)의 결합판과 사실상 동일 — seed 템플릿 연동까지 있는 FE-1/FE-2 쪽으로 흡수.

### [SH-2] 코어 4개 명령에 '다음 단계' 체이닝 한 줄씩 추가
- 점수 3.3/5 · effort S · risk low
- **무엇을**: 각 명령 절차 마지막에 다음 단계 안내 1줄 추가: seed [S4] → '다음: 해당 스택 트랙 명령으로 빌드(예: /hb-be:feature:auto)'; evaluate [E4] → '통과 시 다음: /hb-shared:review'; review [R5] → '통과 → 머지. 반복 마찰이 있었으면 /hb-shared:evolve(선택)'; seed의 'interview로 되돌린다'(:9,:26)를 '해당 스택 플러그인의 planning:interview(예: /hb-be:planning:interview)로'로 구체화.
- **왜**: 각 명령이 스스로 다음을 가리키면 CLAUDE.md 순서표를 매번 기억할 필요가 없어진다 — '새 흐름은 기본 진입점에 연결' 교훈의 명령-레벨 완성. 한 줄씩이라 세리머니 증가 없음.
- **파일**: `SHARED/commands/seed.md`, `SHARED/commands/evaluate.md`, `SHARED/commands/review.md`, `SHARED/commands/evolve.md`
- **심사 노트**: 한 줄짜리 체이닝이라 비용 제로에 가깝고 순서표 기억 부담을 줄이지만, CLAUDE.md가 이미 자동 로드되므로 체감은 보통. / seed.md:9·:26 interview 참조 실재 확인. 한 줄 체이닝이라 세리머니 증가 없고 무해하나 효과는 중간. / 명령이 스스로 다음 단계를 가리키게 하는 한 줄 체이닝 — 세리머니 증가 없이 순서표 자기안내, seed :9/:26 interview 참조 구체화도 실파일 확인.

### [SH-4] SKILL.md·codex plugin.json에 방법론 코어(seed/evaluate/review/evolve) 등록
- 점수 3.3/5 · effort S · risk low
- **무엇을**: SKILL.md Source Of Truth에 commands/seed.md·evaluate.md·review.md·evolve.md 4줄 추가, Command Mapping에 `/hb-shared:seed` 등 4개 별칭 추가. .codex-plugin/plugin.json의 description·longDescription에 순서표(seed→evaluate→review→evolve) 언급 추가, defaultPrompt에 'hb-shared seed로 주문서를 만들어줘' 류 1개 추가. name/version 키는 건드리지 않음(R9 패리티 유지).
- **왜**: 실제로 도메인 흐름에 연결된 코어 4개가 Codex 쪽과 스킬 라우팅에서 보이지 않는 drift 해소 — Codex 세션에서도 같은 방법론을 찾을 수 있게 된다.
- **파일**: `SHARED/skills/hb-shared/SKILL.md`, `SHARED/.codex-plugin/plugin.json`
- **심사 노트**: XC-2와 사실상 동일 제안(Codex 등록 레이어에 코어 4개 노출) — XC-2로 통합. / 드리프트 실재(SKILL.md·codex plugin.json에 코어 4개 부재 확인)하나 XC-2가 완전 상위집합 — XC-2로 흡수. / SHARED SKILL/plugin.json에 코어 4개 부재 실확인이나 XC-2와 동일 제안 — marketplace·죽은 설계문서 포인터까지 포괄하는 XC-2로 흡수.

### [SH-5] prior-art·convention-check의 Django 잔재를 스택 중립으로 치환
- 점수 3.3/5 · effort S · risk low · cut표 1
- **무엇을**: prior-art.md Sub-agent 프롬프트의 '기존 모델/시리얼라이저/뷰'(:16) → '기존 모듈/컴포넌트/핸들러' 류 중립 표현 + '구체 용어·검사 대상은 호출한 스택 플러그인을 따른다' 1줄 추가, 'URL 충돌, 모델 필드 충돌, signal 간섭'(:17) → '라우팅/스키마/이벤트 간섭 등 스택 해당 항목'으로. convention-check.md 산출물 예시의 DJ-001(:43) → {규칙ID}로 일반화.
- **왜**: CM/FE/CHAT에서 호출 시 Django 모양 질문이 나가는 자기모순 제거 — SKILL.md:35의 stack-agnostic 규칙과 본문을 일치시킨다.
- **파일**: `SHARED/commands/feature/prior-art.md`, `SHARED/commands/maintenance/convention-check.md`
- **심사 노트**: 도메인 파이프라인이 참조하지 않는 고아 명령(prior-art/convention-check)의 문구 수정 — 자기모순은 맞지만 실호출 빈도가 낮아 체감 미미, SH-6/XC-8 지위 결정에 종속. / 검증됨 — prior-art.md:15-17 모델/시리얼라이저/signal, convention-check.md DJ-001 실재. SKILL.md stack-agnostic 규칙과의 자기모순 제거, S/low. / prior-art.md:16-17 모델/시리얼라이저/signal, convention-check.md:43 DJ-001 실확인 — SKILL의 stack-agnostic 선언과의 자기모순 제거, S/low.

### [SH-6] 고아 보조 명령 정리 — requirements/criteria는 seed로 흡수 명시, 나머지는 진입점 연결 또는 opt-in 표기
- 점수 3.3/5 · effort M · risk med
- **무엇을**: 1안(가벼움, 권장): SHARED/CLAUDE.md 공통 단계 명령 표에 각 명령의 위치를 명시 — requirements/criteria 행에 'seed에 흡수됨(단독 호출 = seed 해당 섹션 약식)', 나머지 4개(design-intent/prior-art/convention-check/feasibility)에 '단독 opt-in — 도메인 파이프라인은 인라인 수행' 표기. 추가로 seed.md [S2]에 '조사 프롬프트는 feature/prior-art.md 참조', convention-check.md에 '단독 호출 시 root-cause/impact-analysis 없으면 사용자 설명으로 대체' fallback 1줄. 2안(정리): requirements.md·criteria.md 파일 삭제 + SKILL.md:25-26, codex plugin.json defaultPrompt(:27-28), SHARED/CLAUDE.md:20-21 동반 갱신 — 이 경우 참조 3곳을 반드시 같이 지워야 함.
- **왜**: 6개 전부 도메인에서 미참조인 현실을 문서가 인정하게 만든다 — '병렬로만 두면 없는 것과 같다'는 교훈대로, 쓰는 것(코어 4개)과 안 쓰는 것(보조)을 구분해 혼란과 seed 중복을 없앤다.
- **파일**: `SHARED/CLAUDE.md`, `SHARED/commands/seed.md`, `SHARED/commands/maintenance/convention-check.md`, `SHARED/skills/hb-shared/SKILL.md`, `SHARED/.codex-plugin/plugin.json`, `SHARED/commands/feature/requirements.md`, `SHARED/commands/feature/criteria.md`
- **심사 노트**: XC-8과 같은 문제(보조 명령 6개의 canonical 지위) — 1안(표기)만으로 팔레트 혼란·seed 중복이 줄지만 문서 수정 위주. 하나로 확정해 처리. / 고아 상태 검증(도메인 파이프라인에서 6개 보조 명령 무참조, seed.md가 requirements/criteria 흡수 명시). 1안(표기)만 채택 권장 — 2안 삭제는 참조 3곳 동반 수정 필요해 리스크↑. XC-8 흡수. / 보조 6개 명령 도메인 미참조 현실과 부합, '쓰는 것/안 쓰는 것' 구분으로 체계 단순화 — 1안(표기) 권장, 2안(삭제)은 참조 3곳 동반 수정 전제. XC-8 흡수.

### [BE-2] CLAUDE.md 방법론 연결에 hotfix(T0) 예외 1줄 명시
- 점수 3.3/5 · effort S · risk low
- **무엇을**: BE/CLAUDE.md '방법론 연결' 섹션(:102 부근)에 '단, maintenance:hotfix(T0)는 순서표 예외 — seed는 약식 3줄로 갈음하고 H1~H3만 수행하며 5단계 리뷰 관문을 적용하지 않는다(hotfix.md 원칙 우선). 리뷰가 필요해 보이면 그것 자체가 :auto 에스컬레이션 신호'를 추가한다.
- **왜**: hotfix.md의 '리뷰 스킵' 원칙과 CLAUDE.md의 '머지 전 5단계 관문' 선언이 충돌해, 오타 수정에 Codex 교차검증이 붙는 세리머니 폭주(또는 반대로 auto 리뷰 생략) 해석이 가능한 모호성을 제거.
- **파일**: `BE/CLAUDE.md`
- **심사 노트**: 실재하는 hotfix↔5관문 충돌을 정확히 짚었으나 BE 단독판 — 4개 CLAUDE.md 전체를 다루는 UX-5로 흡수. / hotfix.md:22 '리뷰 스킵' vs CLAUDE.md:107 '5단계 관문' 충돌 검증됨. 4개 CLAUDE.md 전부 다루는 UX-5로 흡수. / hotfix '리뷰 스킵' vs CLAUDE.md '머지 전 5관문' 충돌 실확인 — 동일 수정을 4개 CLAUDE.md 전체에 적용하는 UX-5로 흡수.

### [BE-5] 고아 스텝 명령 11개: 드리프트 수정 + '스텝 라이브러리' 표기, deep 인라인 중복은 참조로 대체
- 점수 3.3/5 · effort M · risk med
- **무엇을**: (1) 드리프트 난 2곳 즉시 수정: feature/review.md에 5단계 관문 blockquote와 'code-quality-guide.md 없으면 code-convention.yaml+adr.yaml fallback'(auto.md F7의 기준 선택 로직)을 반영, maintenance/fix-plan.md:11에 'auto tier는 root-cause.md만으로 진행(impact-analysis/convention-check는 deep 전용)' 명시. (2) 11개 고아 파일 상단에 '이 문서는 {pipeline} [Fx/Mx/Px] 스텝의 상세 정의 — 단독 호출 시 해당 tier 산출물 존재를 먼저 확인' 1줄 추가. (3) maintenance/deep.md M4의 인라인 팀 스펙+Agent A/B/C 프롬프트를 planning/deep.md:63과 같은 패턴('팀 스펙과 프롬프트는 commands/maintenance/impact-analysis.md 재사용')으로 대체 — 단 deep.md에 team_name/TeamDelete 언급은 남겨 R2/R4 통과 유지. 대안으로 고아 파일 전체 삭제도 가능하지만(R3는 BE 파일 기준 순회라 통과) 5개 플러그인 동시 삭제가 필요해 이번 범위에선 표기+수정을 권장.
- **왜**: 직접 호출 가능한 슬래시 명령이 파이프라인과 다른(낡은) 절차를 주는 현재 상태는 조용한 오동작 원인이고, deep.md↔impact-analysis.md 이중 사본은 다음 수정 때 반드시 어긋난다. 명령 수를 못 줄이더라도 최소한 '어느 것이 진실인가'는 한 곳으로.
- **파일**: `BE/commands/feature/review.md`, `BE/commands/maintenance/fix-plan.md`, `BE/commands/maintenance/deep.md`, `BE/commands/maintenance/impact-analysis.md`, `BE/commands/feature/pr-body.md`, `BE/commands/feature/reflect.md`, `BE/commands/maintenance/rca.md`, `BE/commands/maintenance/reproduce.md`, `BE/commands/planning/scope.md`, `BE/commands/planning/interview.md`, `BE/commands/planning/research.md`, `BE/commands/planning/decision-draft.md`
- **심사 노트**: 드리프트 난 2곳(review.md·fix-plan.md) 수정과 deep↔impact-analysis 이중 사본 제거는 실익이지만, 고아 문서 표기 11개는 저빈도 경로라 임팩트 보통. 드리프트 수정 부분만 우선해도 됨. / 검증됨 — feature/review.md에 5관문/fallback 부재, fix-plan.md:11 무조건 3파일 읽기, maint deep M4 인라인 vs impact-analysis.md 이중 사본. planning/deep P4 재사용 패턴이 R2/R4 통과를 이미 입증. M/med지만 조용한 오동작 차단. / review.md 5관문/fallback 부재, fix-plan:11의 deep 전용 입력 강제, deep M4↔impact-analysis.md 이중 사본 모두 실확인 — planning P4의 검증된 재사용 패턴으로 진실 단일화, 중복 제거형.

### [CM-4] seed/evaluate 훅을 feature·maintenance auto 파이프라인 본문에 불릿으로 명시
- 점수 3.3/5 · effort M · risk med
- **무엇을**: 새 스텝 헤더(### [Xn]) 추가 없이(R3 스텝 대칭 유지): feature/auto.md F1에 '주문서(seed) 확인 — 없으면 /hb-shared:seed 약식 3줄로 생성' 불릿, F8 QA에 '/hb-shared:evaluate — 주문서 완료기준을 증거로 확인' 불릿을 추가. maintenance/auto.md M1/M6에도 동일하게 1줄씩. BE 쌍둥이 파일에도 같은 불릿을 같은 PR에서 적용해 내용 drift 방지 (deep tier는 auto가 검증된 후 후속).
- **왜**: CLAUDE.md가 '자동 적용된다'고 선언한 seed/evaluate가 실제 실행 스펙(커맨드 문서)에는 없어 실행이 복불복 — '새 흐름은 기본 진입점에 연결해야 실제로 쓰인다'는 교훈의 나머지 절반을 완성한다. 불릿 방식이라 R3(헤더 수 대칭)를 깨지 않고 세리머니 추가도 최소(약식 3줄 허용).
- **파일**: `CM/commands/feature/auto.md`, `CM/commands/maintenance/auto.md`, `BE/commands/feature/auto.md`, `BE/commands/maintenance/auto.md`
- **심사 노트**: UX-1/XC-3과 동일 목표(seed/evaluate 훅 인라인) — 전 도메인·이중질문 제거까지 포함한 UX-1로 흡수. / 방향 옳고 R3 인식 정확하나 CM+BE만 다룸 — 16파일 전 도메인판 UX-1로 흡수. / seed/evaluate 배선 그룹의 축소판(auto만·불릿) — 16개 전체 + 재질문 금지 의미론을 갖춘 UX-1로 흡수.

### [FE-4] feature/review.md를 F8/F11 리뷰 스텝과 동기화
- 점수 3.3/5 · effort S · risk low
- **무엇을**: review.md sub-agent 프롬프트 입력에 visual-check.md/responsive-check.md/accessibility-notes.md/api-binding-check.md를 추가하고, 리뷰 원칙에 deep.md F11의 모드별 렌즈 2줄(디자인: 텍스트 겹침·터치 타깃·focus·overflow / 바인딩: 계약 일치·상태 처리·mock 잔재·api 계층 우회)을 복제한다. 기준 선택에 auto tier fallback('code-quality-guide.md 없으면 code-convention.yaml + adr.yaml stacks 필터')을 명시한다.
- **왜**: 표준 리뷰 문서가 파이프라인 인라인 정의보다 빈약해 어느 쪽이 진실인지 모호하고, auto tier에서 review.md를 그대로 따르면 존재하지 않는 code-quality-guide.md를 찾게 된다. 한 곳으로 동기화하면 리뷰 품질이 tier와 무관하게 일관된다.
- **파일**: `FE/commands/feature/review.md`
- **심사 노트**: 내부 review.md 드리프트 정리는 '어느 쪽이 진실인가' 단일화 실익이 있으나, auto는 인라인 F7을 쓰므로 체감은 간접적. / 검증됨 — feature/review.md가 시각 산출물 4종·auto fallback 미포함, code-quality-guide.md만 전제. 단독 호출 시 실패 경로 실재. BE-5(1)과 같은 패턴의 FE판. / feature/review.md에 FE 검증 산출물 4종 입력·auto fallback 부재 실확인 — F8 인라인 정의와의 진실 단일화, BE-5(1)과 같은 패턴의 FE판.

### [FE-6] F7 시각 검증에 실행·증거 프로토콜 추가
- 점수 3.3/5 · effort M · risk low
- **무엇을**: feature auto [F7]·deep [F9]에 3항목을 추가한다: (a) 실행 방법 — 기존 dev 서버 재사용 우선, 없으면 npm start (승인 게이트 규칙 6과 충돌 없음); (b) 캡처 규약 — 스크린샷은 .harness/artifacts/feature/{branch-name}/visual/ 하위에 {route}-{viewport}.png로 저장하고 visual-check.md에서 상대경로로 참조; (c) 정직성 규칙 — 브라우저 확인이 불가능하면 각 산출물에 '미검증: {사유}'를 기록하고 관찰 서술을 창작하지 않는다. shared/verify.md '4. 화면 검증'에도 동일 규칙 1줄 참조 추가.
- **왜**: SHARED seed.md가 경고하는 '시각 회귀의 텍스트 환원'을 FE 커맨드 레벨에서 실제로 막는다. 사용자가 유일한 리뷰어이므로, 캡처 경로 규약과 미검증 표시가 있어야 visual-check.md를 근거로 신뢰/불신 판단이 즉시 가능하다.
- **파일**: `FE/commands/feature/auto.md`, `FE/commands/feature/deep.md`, `FE/commands/shared/verify.md`
- **심사 노트**: 정직성 규칙('미검증 표기, 관찰 창작 금지')은 유일 리뷰어인 사용자에게 가치가 크지만, 캡처 규약·경로 규칙은 절차 추가라 렌즈와 절반만 부합 — 정직성 규칙 부분만이라도 채택 가치. / (a)는 F7:112에 이미 존재해 부분 중복. (b) 캡처 경로 규약·(c) 미검증 정직성 규칙은 신규이며 seed.md의 '시각 회귀 텍스트 환원' 경고와 정합 — (b)(c) 중심으로 축소 적용 권장. / seed.md의 '시각 회귀 텍스트 환원 금지' 경고를 캡처 경로 규약 + '미검증' 정직성 규칙으로 실행화 — 아티팩트 경로 규약 정합, 사용자=유일 리뷰어 상황에 적실.

### [FE-7] maintenance:deep에 visual 이슈 유형과 visual-regression.md 추가
- 점수 3.3/5 · effort S · risk low
- **무엇을**: maintenance/deep.md [M1] 이슈 유형 목록에 auto와 동일한 'visual — 디자인 적용 오류, responsive overflow, focus/contrast 문제'를 추가하고, [M2] baseline 기록 항목에 'visual 유형: 깨진 viewport·캡처 위치·기대 화면'을 추가, 산출물 목록에 visual-regression.md(visual/responsive 이슈일 때)를 추가한다. ### 스텝 헤더 수는 변하지 않으므로 R3(4도메인 maintenance 스텝 대칭)에 영향 없다.
- **왜**: 시각 이슈가 여러 화면·viewport에 전파돼 deep으로 에스컬레이션되는 순간 시각 유형 분류와 산출물이 사라지는 역전을 해소한다. auto→deep 에스컬레이션 시 아티팩트 연속성(visual-regression.md 재사용)도 확보된다.
- **파일**: `FE/commands/maintenance/deep.md`
- **심사 노트**: auto→deep 에스컬레이션 시 visual 유형·산출물이 사라지는 역전은 실결함이나 deep 자체가 저빈도 — 작고 안전한 수정. / 검증됨 — maint auto는 visual 유형(:43)·visual-regression.md(:134) 보유, deep은 전무. 헤더 불변으로 R3 안전. 실재 gap이나 영향 범위는 좁음. / maintenance auto에는 visual 유형·visual-regression.md 존재, deep에는 전무한 역전 실확인 — 에스컬레이션 시 아티팩트 연속성 확보, R3 안전.

### [XC-6] README 3건 드리프트 정리 (실행 모드 분포·FE 바인딩 산출물·방법론 산출물)
- 점수 3.3/5 · effort S · risk low · cut표 1
- **무엇을**: (a) '실행 모드 분포' 표를 deep 기준으로 재생성하고 '(deep tier 기준)' 캡션 명시 — feature 행을 Fork: F2,F4,F6~F9,F11 / Sub-agent: F3,F5(부분),F10으로 교정하거나 표 자체를 각 deep.md 참조 한 줄로 대체. (b) FE 추가 산출물 문단에 api-binding-check.md 추가. (c) 산출물 구조에 seed.md·evaluate-report.md·review-auto-log.txt를 '(hb-shared 방법론 산출물)'로 추가.
- **왜**: README가 유일한 전체 조감도인데 표가 어느 tier와도 안 맞고, 사용자가 중요시하는 FE 바인딩 모드의 증거 산출물이 빠져 있어 온보딩·재확인 시 혼란. R6는 .harness/docs 경로만 검사하므로 안전.
- **파일**: `README.md`
- **심사 노트**: README 조감도 정리 — 드리프트는 사실이나 온보딩용 문서 수정이라 일상 체감 없음. UX-10과 묶어 후순위. / 검증됨 — README 모드 표(feature Fork: F2,F4,F6,F8)가 deep(F2,F4~F9,F11)과도 auto와도 불일치, api-binding-check.md README 부재 실측. R6는 .harness/docs만 검사 — 안전. / 실행 모드 분포 표(F2,F4,F6,F8/F3,F5,F7)가 auto(F3=Fork)와도 deep과도 불일치함을 실확인 — 유일한 전체 조감도의 드리프트 3건 정리, R6 안전.

### [XC-7] 린터 R10(참조 실재성) 신설 + R8에 api-binding-check 확장
- 점수 3.3/5 · effort M · risk med
- **무엇을**: R10: 각 플러그인 md에서 `commands/**.md` 백틱 참조를 추출해 그 플러그인 내 파일 실재를 검사(SHARED/·hb-shared 명시 참조는 화이트리스트). R8: FE feature auto/deep 필수 산출물 목록에 api-binding-check.md 추가. 순서: XC-1 머지 후 → 현 데이터 green 카운트 확인 → 가짜 위반 심어 음성테스트(❌ 확인) 후 제거.
- **왜**: 이번에 발견된 깨진 참조 부류(SKILL.md→이동된 명령)를 구조적으로 재발 방지. R8 확장은 FE 두 모드 형식화의 절반(바인딩)이 가드 없이 방치된 갭을 메움. 기존 교훈(가드 확장은 양방향 검증) 절차 준수 전제.
- **파일**: `scripts/lint-harness.sh`
- **심사 노트**: 이번에 4개 제안이 중복 발견한 깨진 참조 부류의 구조적 재발 방지 — 한 번 넣으면 자동 효과지만 일상 체감은 간접, 양방향 검증 절차 전제로 med 리스크 감수 가치. / 이번에 실증된 결함 부류의 구조적 재발 방지 + '가드 확장 양방향 검증' 교훈 절차 준수. 단 R10 화이트리스트 설계가 까다롭고(플러그인 내 상대참조 다수) XC-1 선행 필수 — med risk 반영해 3. / 이번에 검출된 깨진 참조 부류의 구조적 재발 방지 + R8의 api-binding-check 공백 실확인 — green 카운트→음성테스트 순서 명시가 '가드 확장 양방향 검증' 교훈 그대로, XC-1 머지 후 진행.

### [BE-6] 참조 위생: SKILL.md 죽은 경로 수정 + MySQL/MariaDB 표기 통일
- 점수 3.0/5 · effort S · risk low
- **무엇을**: (1) BE/skills/hb-be/SKILL.md:37의 'commands/maintenance/convention-check.md'를 실존 대상으로 교체 — 'commands/maintenance/deep.md [M5] (convention-check.md 산출물 생성 단계)' 또는 hb-shared 플러그인의 SHARED/commands/maintenance/convention-check.md를 명시. (2) DB 표기 통일: 실제 레포 기준(CLAUDE.md의 MySQL+PyMySQL)에 맞춰 planning/scope.md:54·research.md:26의 MariaDB를 'MySQL(MariaDB 호환)'로 정정하거나, 실환경이 MariaDB면 CLAUDE.md:12를 수정 — 사용자에게 어느 쪽이 사실인지 1회 확인 후 반영.
- **왜**: Codex 경로(SKILL.md)를 따르는 세션이 죽은 파일을 찾다 실패하고, 기획 산출물에 두 가지 DB명이 섞여 들어가는 소소하지만 반복되는 마찰 제거.
- **파일**: `BE/skills/hb-be/SKILL.md`, `BE/CLAUDE.md`, `BE/commands/planning/scope.md`, `BE/commands/planning/research.md`
- **심사 노트**: SKILL 죽은 경로는 XC-1(canonical)로 통합, MySQL/MariaDB 표기는 잔여 소품으로 FE-5류 잔재 정리에 편승. / (1) SKILL.md:37 죽은 경로 확인 — XC-1과 중복이라 흡수. (2) scope.md:54·research.md:26 MariaDB vs CLAUDE.md:12 MySQL 불일치 확인 — 이 고유분만 XC-1 실행 시 함께 처리. / SKILL:37 죽은 참조는 XC-1에 흡수; MySQL(CLAUDE.md:12)↔MariaDB(scope:54·research:26) 불일치는 실확인된 고유 항목이라 XC-1 작업에 부속으로 처리.

### [CM-3] SKILL.md의 convention-check 참조를 실존 경로(hb-shared)로 수정
- 점수 3.0/5 · effort S · risk low
- **무엇을**: CM/skills/hb-cm/SKILL.md:37의 'commands/maintenance/convention-check.md'를 '/hb-shared:maintenance:convention-check (repo 루트에서는 SHARED/commands/maintenance/convention-check.md)'로 수정하고, Source Of Truth 절에 shared 방법론 명령은 SHARED/ 하위임을 한 줄 추가. (참고: BE/CHAT/FE SKILL.md에도 동일 잔재가 있으면 각 담당에서 같은 패턴으로 수정해 패리티 유지.)
- **왜**: Codex/Claude가 SKILL 지시대로 파일을 열면 존재하지 않는 경로라 절차를 즉흥 수행하게 되는 dead reference 제거. 린터는 SKILL.md 내용을 검사하지 않으므로 파괴 위험 없음.
- **파일**: `CM/skills/hb-cm/SKILL.md`
- **심사 노트**: XC-1과 동일 수정의 CM 단독판 — XC-1로 통합. / SKILL.md:37 죽은 참조 확인 — XC-1이 3개 플러그인을 한 번에 처리하므로 흡수. / CM SKILL:37 깨진 참조 실확인이나 XC-1이 3개 플러그인을 일괄 수정 — 완전 포함이라 흡수.

### [CH-4] SKILL.md 깨진 참조 수정 + dual gate alias 보강
- 점수 3.0/5 · effort S · risk low
- **무엇을**: SKILL.md 46행의 'commands/maintenance/convention-check.md'를 '`maintenance:deep` [M5] 산출물 convention-check.md (프로토콜 원문은 hb-shared 플러그인 SHARED/commands/maintenance/convention-check.md)'로 교정. CLAUDE.md 90행도 동일하게 명확화. SKILL.md Command Mapping에 'hb-chat shared review-gates', 'hb-chat feature contract-check' alias 추가, Source Of Truth 목록에 feature/contract-check.md 추가.
- **왜**: Codex(dual gate의 절반)가 SKILL.md만 보고 진입하는데, 존재하지 않는 파일 참조와 게이트 명령 누락은 dual gate 자체를 못 찾게 만든다.
- **파일**: `CHAT/skills/hb-chat/SKILL.md`, `CHAT/CLAUDE.md`
- **심사 노트**: SKILL 죽은 경로는 XC-1로 통합, dual gate alias 보강만 잔여 소득 — XC-1+XC-2 처리에 편승. / SKILL.md:46 죽은 참조 확인 — XC-1로 흡수. 고유분(review-gates/contract-check alias·Source Of Truth 추가)은 Codex 이중 등록 정합에 유효하므로 XC-1 실행 시 편입. / CHAT SKILL:46 깨진 참조는 XC-1에 흡수 — review-gates/contract-check alias·Source Of Truth 추가만 고유하므로 XC-1 구현의 부속 항목으로.

### [XC-5] CHAT 리뷰 이중 게이트를 '한 프로토콜의 특화'로 명문화
- 점수 3.0/5 · effort M · risk med
- **무엇을**: CHAT/CLAUDE.md와 review-gates.md에 관계 선언 한 단락 추가: 'review-gates = /hb-shared:review의 CHAT 인스턴스. [R3] Codex 교차검증은 CHAT에서 생략 불가(override), [G1~G4]는 [R2]~[R5]에 대응, 산출물은 .harness/artifacts/review/{identifier}/ 한 곳'. 두 벌 실행이 아니라 한 바퀴임을 못박는다.
- **왜**: CHAT에서 리뷰를 두 번 돌거나 Codex 생략 가부를 에이전트가 임의 판단하는 모순 제거. 세리머니 총량은 오히려 감소(1회 실행 명시).
- **파일**: `CHAT/CLAUDE.md`, `CHAT/commands/shared/review-gates.md`, `SHARED/commands/review.md`
- **심사 노트**: UX-6와 같은 문제의 선언판 — '한 바퀴' 명문화는 UX-6의 호출 합치기와 한 변경으로. / 문제의식 타당하나 CH-7(G↔R 매핑)+UX-6(호출 단일화)과 거의 전면 중복 — 두 건으로 흡수. / CH-7과 동일 문제의 다른 표현 — 'CHAT은 R3 생략 불가 override'는 R3의 미설치 시 graceful skip과 충돌 소지가 있어 CH-7의 문구가 방법론 정합적, 흡수.

### [XC-8] hb-shared 보조 명령 6개의 지위 명문화 (인라인 파이프라인과의 이중 유지보수 차단)
- 점수 3.0/5 · effort S · risk low
- **무엇을**: SHARED/CLAUDE.md '공통 단계 명령' 표에 '단독 실행용 — feature/maintenance 파이프라인은 같은 절차를 인라인으로 내장하며 인라인이 canonical'을 명시하거나, 반대로 도메인 deep의 F2/F3/F5에 '절차·템플릿은 hb-shared 해당 문서를 따른다' 앵커를 넣어 SHARED를 canonical로 지정. 둘 중 하나로 확정(전자가 S, 후자가 M).
- **왜**: 현재 어느 쪽도 canonical 선언이 없어 SHARED requirements.md와 인라인 F2가 이미 갈라지기 시작(기존 모듈 연결점 표). 방치하면 '옮겼는데 아무도 안 쓰는' 죽은 명령 + 드리프트 이중고.
- **파일**: `SHARED/CLAUDE.md`, `SHARED/skills/hb-shared/SKILL.md`
- **심사 노트**: SH-6와 동일 문제 — canonical 선언 방향(전자 S안)으로 하나로 확정해 이중 유지보수만 차단. / canonical 미선언 문제는 실재하나 SH-6과 같은 파일·같은 논점 — SH-6(1안)으로 흡수, 전자(S) 방향 권장. / SH-6과 동일 문제(보조 명령 canonical 미선언) — SH-6이 구체 fallback과 흡수 명시까지 제시해 그쪽으로 흡수.

### [UX-3] 플러그인별 단일 지능형 진입점 /hb-<x>:go 신설 + CLAUDE.md 기본 진입점으로 등록
- 점수 3.0/5 · effort M · risk low
- **무엇을**: 각 플러그인 commands/ 루트에 go.md 신설: 사용자 요청 한 줄을 받아 (a) 코드 수정 없음→planning / 버그·수정→maintenance / 새 기능→feature 분류, (b) hotfix 판정 기준(한 파일·한 라인 명확)과 deep 승격 기준(각 auto 문서의 '언제 deep으로' 섹션)을 적용해 tier 선택, (c) 선택 결과를 한 줄 보고 후 해당 트랙 명령 본문을 그대로 실행. CLAUDE.md 트랙 표 최상단에 '무엇을 불러야 할지 모르면 /hb-<x>:go' 한 줄 추가. R3는 planning/maintenance/shared/feature 하위만 검사하므로 commands/go.md는 린터 영향 없음(단 BE·CM·FE·CHAT 4곳 모두 추가해 문서 일관성 유지).
- **왜**: friction 6 해소 — 트랙 3×tier 3+보조 명령의 선택 부하를 '한 명령'으로 접는다. 분류가 이미 각 문서에 판정 기준으로 존재하므로 새 로직이 아니라 기존 기준의 디스패처일 뿐.
- **파일**: `BE/commands/go.md`, `CM/commands/go.md`, `FE/commands/go.md`, `CHAT/commands/go.md`, `BE/CLAUDE.md`, `CM/CLAUDE.md`, `FE/CLAUDE.md`, `CHAT/CLAUDE.md`, `README.md`
- **심사 노트**: 선택 부하를 한 명령으로 접는 발상은 매력적이나 '새로 추가' 안티패턴 + 분류 기준 이중화(drift) 리스크 — 기존 기준의 디스패처로 얇게 유지하는 조건부 채택. / R3가 planning/maintenance/shared/feature 하위만 순회해 commands/go.md 무영향 — 린터 이해 정확. 다만 SKILL.md Command Mapping·Codex 등록 갱신이 빠져 있어 이중 등록 정합 보강을 조건으로. / 선택 부하 해소 가치는 있으나 새 명령 4개 추가는 '재편>추가' 교훈과 긴장 — 각 auto의 기존 판정 기준을 참조만 하고 복제하지 않는 조건으로 낮은 우선순위 keep.

### [UX-10] README Quick Start에 CHAT·SHARED 온보딩 보완
- 점수 3.0/5 · effort S · risk low · cut표 1
- **무엇을**: (1) 2단계에 'CHAT 레포에서는 hb-chat' + 'hb-shared는 모든 레포에서 함께 활성화' 추가. (2) 3단계를 'BE/CM/FE는 4개 YAML, CHAT은 CHAT/CLAUDE.md의 10개 문서(websocket-events.yaml 등 계약 문서 포함)'로 수정. (3) 명령 예시 블록에 CHAT 예시 추가: /hb-chat:feature:auto, /hb-chat:contract:websocket, /hb-chat:maintenance:hotfix. 경로 표기는 .harness/docs/* 유지(R6 정합).
- **왜**: friction 6의 문서 절반 해소 — 세리머니가 가장 무겁고 명령이 가장 많은 CHAT이 Quick Start에 없어서, 정작 도움이 제일 필요한 레포에서 진입 장벽이 가장 높다.
- **파일**: `README.md`
- **심사 노트**: README 온보딩 보완 — 사실이지만 문서만 늘리는 수정이라 일상 체감 없음. XC-6와 묶어 후순위. / 검증됨 — README Quick Start 2단계에 hb-chat/hb-shared 부재, 3단계 '4개 YAML'은 CHAT 10개 문서와 불일치. S/low 문서 보수, 영향 범위는 온보딩 한정. / Quick Start 2단계에 CHAT·hb-shared 부재, 3단계가 4개 YAML만 언급함을 실확인 — 세리머니 최중량 레포의 온보딩 공백 해소, R6 정합.

### [CH-6] 내부 단계 문서에 '진입점 아님' 배너 + CLAUDE.md에 명령 지도 1줄
- 점수 2.7/5 · effort M · risk low · cut표 1
- **무엇을**: 15개 내부 단계 문서(feature/pr-body·reflect·review, planning/scope·interview·research·alternatives·decision-draft, maintenance/rca·reproduce·fix-plan·impact-analysis, shared/tdd·team-protocol 등) 최상단에 '> 내부 단계 문서 — {track}:{auto|deep}의 [Fx/Mx/Px] 스텝에서 자동 수행된다. 진입점은 /hb-chat:{track}:auto'를 1줄 추가. CLAUDE.md 트랙 표 아래 '위 13개 외 명령은 파이프라인 내부 단계 문서(직접 호출 불필요)' 1줄 명시. 파일 삭제는 하지 않음(4도메인 구조 대칭 유지, R3는 삭제 시 skip이라 통과하지만 다른 플러그인과의 일관성 훼손).
- **왜**: 28개 팔레트에서 '뭘 불러야 하나' 고민 시간 제거 — 진입점 13개가 명확해지고, 내부 문서를 잘못 직접 호출해 파이프라인 밖 반쪽 실행하는 사고 방지.
- **파일**: `CHAT/CLAUDE.md`, `CHAT/commands/feature/pr-body.md`, `CHAT/commands/feature/reflect.md`, `CHAT/commands/feature/review.md`, `CHAT/commands/planning/scope.md`, `CHAT/commands/planning/interview.md`, `CHAT/commands/planning/research.md`, `CHAT/commands/planning/alternatives.md`, `CHAT/commands/planning/decision-draft.md`, `CHAT/commands/maintenance/rca.md`, `CHAT/commands/maintenance/reproduce.md`, `CHAT/commands/maintenance/fix-plan.md`, `CHAT/commands/maintenance/impact-analysis.md`
- **심사 노트**: 15개 파일 배너는 '문서만 늘리는' 전형 — 팔레트 혼란 해소는 CLAUDE.md 지도 1줄로 충분하고, 그 1줄은 다른 CHAT 수정에 편승 가능. / 파일 15개 실재 확인. 28개 팔레트 선택 부하 완화는 실효 있으나 배너 15줄 추가는 M effort 대비 효과 중간 — CLAUDE.md 지도 1줄만으로도 절반은 달성. / 28개 팔레트의 진입점 혼동은 실재하나 15파일 배너는 다소 노이즈 — CLAUDE.md 명령 지도 1줄이 핵심이고 배너는 부차, 삭제 안 함(대칭 유지) 판단은 옳음.

### [UX-9] 아티팩트 재사용 인덱스 — .harness/artifacts/REGISTRY.md 한 파일로 이전 작업 조회
- 점수 2.7/5 · effort M · risk low · cut표 1
- **무엇을**: 각 트랙의 '완료' 섹션(INDEX.md 생성 지점)에 한 항목 추가: '.harness/artifacts/REGISTRY.md에 한 줄 append — {날짜} | {track}/{identifier} | 건드린 모듈/영역 | 주요 산출물(code-quality-guide 유무 포함)'. 그리고 F1.6(기존 quality-guide 탐색)·F2.2(planning 산출물 연결)·seed S1.3이 디렉토리 전체 스캔 대신 이 REGISTRY.md 한 파일을 먼저 읽도록 수정. 경로가 .harness/artifacts 하위라 R5 정합.
- **왜**: friction 7 해소 — '같은 영역 산출물 재사용'이 정의된 탐색 절차 없이 우연에 맡겨진 것을 O(1) 조회로 바꾼다. planning→feature 연결 고리(slug↔branch)도 이 인덱스가 제공.
- **파일**: `BE/commands/feature/auto.md`, `BE/commands/feature/deep.md`, `BE/commands/maintenance/auto.md`, `BE/commands/maintenance/deep.md`, `BE/commands/planning/auto.md`, `CM/commands/feature/auto.md`, `CM/commands/maintenance/auto.md`, `FE/commands/feature/auto.md`, `FE/commands/maintenance/auto.md`, `CHAT/commands/feature/auto.md`, `CHAT/commands/maintenance/auto.md`, `SHARED/commands/seed.md`, `README.md`
- **심사 노트**: 재사용 O(1) 조회는 실익이나 13개 파일 수정 + 레지스트리 신선도 유지 부담 — append 1줄이라 세리머니 증가는 최소지만 체감은 누적형. / F1.6 '기존 quality-guide 확인'에 탐색 절차가 없는 것은 사실이고 R5 정합. 다만 13개 파일 수정 + append 규약이라는 새 유지 대상 추가 — 효과 대비 effort 중간. / .harness/artifacts 루트에 {track}/{identifier} 규약 밖 전역 파일 신설 + 13문서 유지비 — artifacts는 gitignore 대상이라 지속성도 약하고, 기존 INDEX.md 재편이 먼저('재편>추가' 교훈).

## 중복 그룹 (같이 처리할 묶음)

- BE-1 + CM-4 + UX-1 + XC-3
- BE-3 + UX-2 + UX-4
- BE-2 + UX-5
- BE-6 + CH-4 + CM-3 + XC-1
- SH-4 + XC-2
- FE-1 + FE-2 + UX-8
- CH-7 + UX-6 + XC-5
- SH-6 + XC-8
- UX-10 + XC-6
- CH-7 + XC-5

## 마찰점 전체 (증거 포함)

### seed가 만든 주문서를 evaluate/review가 안 읽는다 — 순서표의 중간 고리 단절
seed.md는 '이후 build·evaluate·review가 모두 이 주문서를 기준으로 돈다'고 선언하고 완료기준(AC) 표까지 산출하지만, evaluate의 기준 수집 단계와 review의 입력 목록 어디에도 seed.md가 없다. 순서표(SHARED/CLAUDE.md:10 '검사 — seed 기준 증거 확인')가 약속한 것과 명령 본문이 다르다. 주문서를 열심히 써도 검사 단계에서 소비되지 않으니 seed를 쓸 동기가 사라진다.
- 증거: `SHARED/commands/seed.md:3 vs SHARED/commands/evaluate.md:28-31 ([E1] 기준 문서 = code-quality-guide.md/design-intent.md만) / SHARED/commands/review.md:25 ([R2] 입력에 seed.md 없음)`

### 공통 보조 명령 6개가 전부 고아 — 도메인 플러그인 어디서도 참조 안 됨
feature:requirements/criteria/design-intent/prior-art, maintenance:convention-check, planning:feasibility는 SHARED 내부 문서(CLAUDE.md, SKILL.md, codex plugin.json)에서만 언급되고 BE/CM/FE/CHAT 명령·CLAUDE.md에서 단 한 번도 참조되지 않는다. 도메인 파이프라인은 같은 일을 인라인으로 한다(BE feature:auto F2=요구사항, F3=설계의도). 특히 requirements/criteria는 seed.md:3이 '흡수했다'고 선언한 것과 중복이다. '병렬로만 두면 없는 것과 같다'는 과거 교훈 그대로.
- 증거: `grep 'hb-shared:feature|hb-shared:maintenance|hb-shared:planning' 결과가 SHARED/ 내부 3개 파일뿐 (SHARED/CLAUDE.md:20-25, SHARED/skills/hb-shared/SKILL.md:25-30, SHARED/.codex-plugin/plugin.json:27-29); BE/commands/feature/auto.md:42-63 (F2/F3 인라인 수행)`

### 스택 무관 플러그인 안에 Django 전용 문구 잔재
prior-art의 Sub-agent 프롬프트가 '기존 모델/시리얼라이저/뷰 확장', 'URL 충돌, 모델 필드 충돌, signal 간섭'을 묻고, convention-check 산출물 예시가 Django 컨벤션 ID(DJ-001)를 쓴다. CM(Node)/FE(React)/CHAT에서 부르면 Django 모양의 조사 질문이 나간다. SKILL.md:35의 'stack-agnostic — do not assume a framework' 규칙과 자기모순.
- 증거: `SHARED/commands/feature/prior-art.md:16-17, SHARED/commands/maintenance/convention-check.md:43, SHARED/skills/hb-shared/SKILL.md:35`

### 정작 매일 쓰는 코어 4개(seed/evaluate/review/evolve)가 SKILL.md·Codex 등록에 없다
SKILL.md의 Source Of Truth와 Command Mapping, codex plugin.json의 description·defaultPrompt는 고아인 보조 명령 6개만 나열한다. 실제로 도메인 흐름에 연결된 방법론 코어는 Codex 쪽과 스킬 라우팅에서 보이지 않는다 — Phase 1 시점 문서가 Phase 2/3 이후 갱신 안 된 drift.
- 증거: `SHARED/skills/hb-shared/SKILL.md:14-19,25-30 (seed/evaluate/review/evolve 부재), SHARED/.codex-plugin/plugin.json:4,26-30`

### 선행 산출물 없이 단독 호출하면 막히는 명령들 — graceful 저하 부재
convention-check의 Sub-agent 프롬프트는 maintenance 트랙 산출물 [root-cause.md][impact-analysis.md]를 입력으로 못박고 '없으면' 분기가 없다. feasibility는 절차 섹션 자체가 없고 planning 트랙이 만드는 alternatives.md에서 추출한다고만 한다. review [R2]도 code-quality-guide.md/pr-body.md를 입력으로 열거하는데 auto tier는 code-quality-guide.md를 생성하지 않는다(BE/commands/feature/auto.md:170) — fallback은 evaluate에만 있고 review에는 없다.
- 증거: `SHARED/commands/maintenance/convention-check.md:24-25, SHARED/commands/planning/feasibility.md:20 (alternatives.md 의존, 절차 부재), SHARED/commands/review.md:25 vs SHARED/commands/evaluate.md:31 (fallback 유무 비대칭)`

### evaluate와 review가 같은 자동검사+반박을 연달아 두 번 돌린다 + Codex 교차검증에 크기 예외 없음
표준 한 바퀴(evaluate→review)를 돌면 스택 전체 자동검사가 [E2]와 [R1]에서 두 번, 반박이 [E3]와 [R4]에서 두 번 실행된다. 재사용 규칙이 없다. 또 [R3] Codex CLI 호출은 울트라코드 OFF나 hotfix급에도 무조건 수행된다(생략은 '미설치/실패' 시에만). 3줄 hotfix에도 풀 세리머니 — 무거우면 안 쓰게 되는 사용자 특성상 가장 이탈 위험이 큰 지점.
- 증거: `SHARED/commands/evaluate.md:35-48 ([E2][E3]) vs SHARED/commands/review.md:17-21,33-43 ([R1][R4]), review.md:35-37 ([R3] 무조건 실행, 생략 조건은 미설치/실패뿐)`

### 명령 간 체이닝 문구가 절반만 있다
evaluate의 '다음은 review'는 리포트 템플릿(:79)에만 숨어 있고 절차 본문 [E4]에는 없다. review는 통과 후 evolve(선택)를 어디서도 언급하지 않는다. seed는 '빈틈이 크면 interview로 되돌린다'고 하지만 interview는 SHARED에 없고 각 도메인 planning 트랙(BE/commands/planning/interview.md)에 있는데 구체 명령을 안 가리킨다. 각 명령이 다음 단계를 스스로 안내하지 않으니 순서표를 CLAUDE.md에서 매번 상기해야 한다.
- 증거: `SHARED/commands/evaluate.md:50-54 ([E4]에 다음 단계 없음, :79 템플릿에만), SHARED/commands/review.md:45-49 ([R5] evolve 언급 없음), SHARED/commands/seed.md:9,26 (interview 명령 미지정)`

### seed/evaluate 연결이 명목뿐 — CLAUDE.md에만 있고 명령 본문에는 없다
BE/CLAUDE.md는 feature:auto/deep 호출 시 hb-shared 순서표(seed→구현→evaluate→review)가 '자동으로 적용된다'고 선언하지만, BE/commands/ 전체에서 'seed'와 'evaluate' 문자열은 0회 등장한다(grep 확인). feature:auto F2는 seed.md를 읽지 않고 독자적으로 요구사항을 재수집하며(planning 산출물만 참조), F8 QA는 evaluate-report.md를 생성하지 않는다. review(5단계 관문)만 스텝 본문에 배선되어 있다. 결과: seed를 먼저 쓰면 F2에서 같은 질문을 반복(이중 세리머니)하거나, 모델이 seed를 조용히 건너뛴다(없는 것과 같음).
- 증거: `BE/CLAUDE.md:100-110 (선언) vs BE/commands/feature/auto.md:42-51 (F2가 seed.md 미참조), grep -rn 'seed\|evaluate' BE/commands/ → 0건`

### auto(T1)가 문서상 lightweight일 뿐 실행 비용은 deep급
feature:auto는 8스텝 중 6개(F2,F3,F4,F5,F6,F8)가 매번 worktree 생성→정리를 요구하고, F4~F6은 그 worktree 안에서 pytest 실행을 전제한다 — Django 레포에서 fork마다 venv/DB/env가 살아있어야 하므로 실제로는 가장 비싼 부분. 또 F7 리뷰 blockquote가 deep(F10)과 한 글자도 다르지 않아 auto도 매번 R3 Codex 교차검증까지 포함한 full 5단계를 돈다 — 리뷰 깊이에서 auto/deep 차이가 0이다. CLAUDE.md는 'T1 auto — 사용자 핑퐁 최소화'라 하지만 F1(branch/base 확인), F3(설계의도 피드백), F8(코멘트별 수용/거부 확인) 3곳에서 사용자 게이트가 있다.
- 증거: `BE/commands/feature/auto.md:44,55,67,80,91,124 (worktree 생성 6회), :102 vs feature/deep.md:137 (동일 blockquote), BE/CLAUDE.md:39`

### hotfix(T0)와 방법론 연결의 모순 — 오타 수정에 5단계 관문이 붙을 수 있다
BE/CLAUDE.md:102는 'feature·maintenance 작업'(hotfix 포함으로 읽힘)에 순서표가 자동 적용되고 머지 전 5단계 리뷰 관문을 요구한다. 반면 hotfix.md:22는 'RCA, 영향도, 리뷰, 전체 회귀 모두 스킵'을 핵심 원칙으로 명시한다. 예외 조항이 없어, 모델이 한 줄 수정에 Codex 교차검증 관문을 붙이거나(세리머니 폭주) 반대로 auto에서도 리뷰를 건너뛰는 해석이 가능하다.
- 증거: `BE/CLAUDE.md:102-107 vs BE/commands/maintenance/hotfix.md:22`

### auto 문서 안에서 같은 스텝 번호가 두 가지 의미로 쓰인다
maintenance/auto.md 헤더·핵심원칙은 deep의 번호로 'M4 영향도 3방향 Team 없음, M5 convention 충돌 sub-agent 없음'이라 쓰는데, 정작 auto 자신의 파이프라인에서 M4=수정 계획, M5=수정 실행이다. 같은 파일에서 M4/M5가 '생략된 스텝'과 '실행할 스텝'을 동시에 가리킨다. feature/auto.md도 동일 패턴(원칙에선 deep의 F3/F5/F9, 본문에선 자체 F1~F8). 실행 중 '지금 M5를 하라는 건가 말라는 건가'급 혼동을 만든다.
- 증거: `BE/commands/maintenance/auto.md:7,25-26 (deep 번호) vs :81,:95 (자체 M4/M5), BE/commands/feature/auto.md:6,21-23 vs :53,:78`

### 23개 명령 중 11개가 파이프라인에서 참조되지 않는 고아 + 내용 드리프트
feature/pr-body·reflect·review, maintenance/fix-plan·impact-analysis·rca·reproduce, planning/scope·interview·research·decision-draft 11개 스텝 파일은 어떤 진입 파이프라인 본문에서도 참조되지 않고(grep 확인, alternatives.md만 planning/deep.md:63이 재사용) 내용이 auto/deep에 인라인 중복돼 있다. 이미 드리프트 발생: feature/review.md는 5단계 관문·Codex 교차검증이 없고 code-quality-guide.md를 필수 입력으로 요구하는데 auto tier는 그 파일을 생성하지 않는다(auto.md:170). fix-plan.md:11은 auto tier가 만들지 않는 impact-analysis.md·convention-check.md를 읽으라 한다. maintenance/deep.md M4는 impact-analysis.md와 동일한 팀 스펙+프롬프트를 통째로 중복 보유(양쪽 수정 시 sync 부담).
- 증거: `BE/commands/feature/review.md:32 vs BE/commands/feature/auto.md:170, BE/commands/maintenance/fix-plan.md:11 vs maintenance/auto.md:178, BE/commands/maintenance/deep.md:77-143 vs impact-analysis.md 전문`

### SKILL.md의 깨진 참조와 스택 사실 불일치
BE/skills/hb-be/SKILL.md:37이 'commands/maintenance/convention-check.md'를 가리키지만 BE에는 이 파일이 없다(convention-check.md는 deep M5가 만드는 산출물이며, 명령 파일로는 SHARED/commands/maintenance/에만 존재). SKILL.md의 경로 규칙('BE/ prefix')을 따르면 죽은 경로다. 또 CLAUDE.md:12는 'DB: MySQL(PyMySQL)'인데 planning/scope.md:54·research.md:26은 'MariaDB'로, 생성되는 기획 문서에 서로 다른 DB명이 흘러든다.
- 증거: `BE/skills/hb-be/SKILL.md:37 (존재하지 않는 BE/commands/maintenance/convention-check.md), BE/CLAUDE.md:12 vs BE/commands/planning/scope.md:54, BE/commands/planning/research.md:26`

### update-docs가 Django 스키마를 그대로 노출 — CM 자체 문서와 모순
/hb-cm:shared:update-docs를 실행하면 convention 카테고리로 'GEN, DJ, DRF, DOCK', stacks로 'django, drf'를 제시하고, module-registry 스키마는 Django 앱 레이아웃(path: apps/{name}/, models, api_prefix)이다. 같은 플러그인의 verify.md(GEN/EXP/REPO/TS/TEST 규칙 ID)와 feature/deep.md F5('TS-, EXP-, REPO-, TEST- 필터')와 정면 모순 — Node 레포에서 이 명령으로 문서를 갱신하면 Django식 항목이 만들어진다. context 좋은 예도 Django CONN_MAX_AGE 사례.
- 증거: `CM/commands/shared/update-docs.md:47 (`# GEN, DJ, DRF, DOCK, TEST, GIT`), :49 (`# django, drf, docker, all 등`), :69 (Django CONN_MAX_AGE/MariaDB 예시), :84-88 (`path: apps/{name}/`, `models:`, `api_prefix:`) ↔ CM/commands/shared/verify.md:37-46 (EXP-001, REPO-001, TS-003 등), CM/commands/feature/deep.md:84`

### planning 보조 명령 3종이 BE 원본 그대로 (byte-identical 복붙)
scope.md와 interview.md는 BE와 diff 0줄(완전 동일), decision-draft.md는 명령 prefix만 치환. stakeholders 템플릿이 '프리다이버(수강생)/강사', '백엔드 (Django/DRF)', 'DB (MariaDB)', '외부 서비스 (Innopay)'를 제시하고, interview는 '기존 시스템(예약, 결제)' + booking/payment 연결표를 묻는다. 같은 플러그인 planning/deep.md P1이 정의한 CM 이해관계자(커뮤니티 사용자/작성자/모더레이터; CM 자체/메인 BE/MySQL·Redis/Socket.io 클라이언트)와 모순되고, deep P2의 CM 질문(Socket.io 실시간성, 이벤트 처리량, 메인 BE 연동)이 interview.md에는 없다.
- 증거: `CM/commands/planning/scope.md:45,53-56 · CM/commands/planning/interview.md:27,60-61 · CM/commands/planning/decision-draft.md:28 (프리다이빙 예약 예시) ↔ CM/commands/planning/deep.md:24-25,38-40; `diff BE/commands/planning/scope.md CM/commands/planning/scope.md` = 차이 없음`

### SKILL.md의 convention-check 참조가 존재하지 않는 CM 경로를 가리킴
SKILL.md는 'Maintenance verifies conformance via commands/maintenance/convention-check.md'라고 안내하지만, SKILL.md:12의 경로 규칙(레포 루트에서는 CM/ prefix)을 적용하면 CM/commands/maintenance/convention-check.md — 존재하지 않는 파일이다. 실제 파일은 SHARED/commands/maintenance/convention-check.md(= /hb-shared:maintenance:convention-check)에 있다. Codex/Claude가 이 경로를 열려다 실패하면 M5 절차를 즉흥으로 수행하게 된다.
- 증거: `CM/skills/hb-cm/SKILL.md:37 ↔ CM/commands/maintenance/ 파일 목록(auto/deep/fix-plan/hotfix/impact-analysis/rca/reproduce만 존재), SHARED/commands/maintenance/convention-check.md 존재, SHARED/CLAUDE.md:24`

### BE에만 반영된 update-docs 개선(편입 후 YAML 본문 제시)이 CM에 미전파 — 쌍둥이 drift
BE update-docs.md에는 'ADR 편입 시 특별 규칙' 5번 항목('편입 후 YAML 본문 제시 (필수)' — 편입 결과 yaml을 사용자에게 직접 보여주기)이 있으나 CM에는 없다. 사용자가 BE에서 얻는 확인 UX를 CM에서는 못 받는다. 쌍둥이 플러그인의 개선이 한쪽에만 들어간 drift 사례.
- 증거: `diff BE/commands/shared/update-docs.md CM/commands/shared/update-docs.md → `43d42 < 5. **편입 후 YAML 본문 제시 (필수)**: ...``

### CLAUDE.md가 약속한 seed/evaluate가 트랙 파이프라인 본문에 훅이 없음
CM/CLAUDE.md 방법론 연결 절은 'feature:auto를 호출하면 seed(주문서)→구현→evaluate(검사)→review가 자동으로 적용된다'고 선언하지만, 실제 파이프라인 문서에는 review만 훅이 있고(F7/M7의 5단계 관문 주석) seed·evaluate 단계/불릿은 어디에도 없다. 명령 실행 시 조작 스펙은 커맨드 문서이므로 seed/evaluate는 실행 여부가 복불복이 된다 — '새 흐름은 기본 진입점에 연결' 교훈의 절반만 적용된 상태.
- 증거: `CM/CLAUDE.md:106-110 (seed/evaluate/review/evolve 자동 적용 선언) ↔ CM/commands/feature/auto.md F1-F8 (seed/evaluate 언급 0회, 리뷰 훅만 :103), CM/commands/maintenance/auto.md (:137 리뷰 훅만)`

### typecheck 명령이 tier마다 다름 (경미)
auto tier(feature F8, maintenance M6)와 tdd.md는 `npm run typecheck`, deep tier(F11)와 verify.md는 `tsc --noEmit`을 쓴다. 대상 레포에 typecheck 스크립트가 없으면 auto tier QA만 실패하는 비대칭이 생긴다.
- 증거: `CM/commands/feature/auto.md:133, CM/commands/maintenance/auto.md:126, CM/commands/shared/tdd.md:78 (`npm run typecheck`) ↔ CM/commands/feature/deep.md:172, CM/commands/shared/verify.md:14 (`tsc --noEmit`)`

### 모드 분류가 선언만 있고 기본 진입점(feature 파이프라인)에 미연결
FE/CLAUDE.md는 "작업 시작(seed) 시 이 작업이 어느 모드인지 먼저 분류"하라고 하지만, 실제 feature:auto의 [F1] 상태 점검·[F2] 요구사항 정리 어디에도 모드 분류 스텝/기록 필드가 없다. SHARED seed.md 주문서 템플릿에도 모드 필드가 없다. 모드는 [F7] 6번에서 "API 바인딩 작업이면"이라는 조건으로 처음 등장 — 파이프라인 후반에서야 암묵적으로 판정된다. 과거 교훈(새 흐름은 기본 진입점에 연결)이 그대로 재현된 형태.
- 증거: `FE/CLAUDE.md:63 ("작업 시작(seed) 시 이 작업이 어느 모드인지 먼저 분류") vs FE/commands/feature/auto.md:29-42 ([F1]에 모드 항목 없음), FE/commands/feature/auto.md:120 (F7에서 처음 조건 등장), SHARED/commands/seed.md:57-100 (seed.md 템플릿에 모드 필드 없음)`

### auto tier가 순수 API 바인딩 작업에도 시각 산출물 3종을 무조건 강제
[F7]에서 visual-check.md·responsive-check.md(375/768/1440)·accessibility-notes.md는 조건 없이 생성 지시인 반면, api-binding-check.md에만 "N/A: 디자인 구현 전용" 탈출구가 있다. 레이아웃 변경이 전혀 없는 순수 바인딩 작업(예: 기존 화면에 API 연결)에서도 3개 viewport 반응형 체크와 a11y 노트를 만들어야 해 lightweight 기본값 철학과 충돌. CLAUDE.md 규칙 8은 "해당 산출물을"이라고 조건부를 암시하지만 F7 본문은 무조건이다.
- 증거: `FE/commands/feature/auto.md:113-119 (3~5번 무조건) vs :120 (api-binding-check만 N/A 허용), FE/CLAUDE.md:120 (규칙 8 "해당 산출물을"), FE/commands/feature/deep.md:137-140 (deep F9 동일 비대칭)`

### shared/update-docs.md의 스키마 예시가 Django(BE) 복붙 잔재
code-convention.yaml 스키마 카테고리가 GEN, DJ, DRF, DOCK이고 stacks 예시가 django, drf, docker다. module-registry.yaml 스키마도 path: apps/{name}/, models: [...], api_prefix: /api/{name}/ 로 Django 앱 구조다. 같은 플러그인의 verify.md는 COMP-/HOOK-/API-/STYLE-/A11Y-/PATH-/TEST- 카테고리를, CLAUDE.md는 route/page/component/hook/API/state/style 레지스트리를 말하고 있어 문서 갱신 시 어느 스키마를 따라야 할지 모순된다.
- 증거: `FE/commands/shared/update-docs.md:47 (# GEN, DJ, DRF, DOCK, TEST, GIT), :49 (# django, drf, docker), :82-91 (apps/{name}/, models, api_prefix) vs FE/commands/shared/verify.md:34-43 (COMP-/HOOK-/API-/STYLE-/A11Y-), FE/CLAUDE.md:59`

### planning 커맨드에 CHAT 복붙 잔재 + 스택 표기 불일치(MUI)
planning:deep의 인터뷰 질문 "(동시 접속, 메시지/이벤트 처리량)"은 CHAT/commands/planning/deep.md:40과 문자 동일한 잔재이고, "브라우저 이벤트 스키마 변경 필요 여부"는 socket 이벤트 스키마의 기계적 치환으로 FE에서 의미 불명. interview.md 연결점 예시는 booking/payment로 FE 모듈 관점이 없다. 또한 research.md만 MUI/Bootstrap을 언급하는데 CLAUDE.md 프로젝트 스택에는 UI 라이브러리 항목 자체가 없어(planning:deep P3는 MUI 없이 나열) 실제 사용하는 MUI가 기준 문서에 부재. reflect.md 판정 예시도 src/pages/post.page.ts 등 CM/CHAT식 .ts 네이밍(FE 테스트는 .jsx).
- 증거: `FE/commands/planning/deep.md:40 (CHAT/commands/planning/deep.md:40과 동일), FE/commands/planning/deep.md:74·alternatives.md:50 (브라우저 이벤트 스키마), FE/commands/planning/interview.md:27,58-62, FE/commands/planning/research.md:28 (MUI/Bootstrap) vs FE/CLAUDE.md:8-20 (UI 라이브러리 없음), FE/commands/feature/reflect.md:32,40`

### feature/review.md(표준 리뷰 문서)가 실제 F8/F11 리뷰 스텝과 불일치
F8(auto)·F11(deep)은 리뷰 입력에 visual-check/responsive-check/accessibility-notes/api-binding-check를 포함하고 디자인/바인딩 모드별 리뷰 렌즈를 명시하지만, 재사용 문서인 review.md의 sub-agent 프롬프트에는 이 FE 산출물 입력과 모드 렌즈가 전부 빠져 있다. 또한 review.md는 code-quality-guide.md를 필수 입력으로 요구하는데 auto tier는 이 파일을 생성하지 않아(F8은 convention+ADR fallback 로직 보유) auto에서 review.md를 따르면 존재하지 않는 파일을 찾게 된다.
- 증거: `FE/commands/feature/review.md:32-37 (입력 목록에 FE 산출물 없음, code-quality-guide 필수) vs FE/commands/feature/auto.md:129-137 (F8 입력 + fallback), FE/commands/feature/deep.md:166-178 (F11 모드별 렌즈)`

### visual-check의 실행·증거 프로토콜이 없어 '텍스트 통과' 위험
F7은 "로컬 앱을 실행하거나 기존 dev 서버를 사용해 확인"이라고만 하고, 어떻게 띄우는지(npm start/기존 서버), 캡처를 어디에 저장하는지, 브라우저 확인이 불가능할 때 어떻게 기록하는지가 없다. SHARED seed.md가 명시적으로 경고하는 "시각 회귀를 텍스트 통과로 환원하지 않는다"가 FE 커맨드 레벨에서 강제되지 않아, visual-check.md가 실측 없는 그럴듯한 서술로 채워질 수 있다. 브라우저 검증 지시는 Codex용 SKILL.md에만 있다.
- 증거: `FE/commands/feature/auto.md:111-119 (실행/캡처 방법·미검증 처리 없음), SHARED/commands/seed.md:44 (경고 문구), FE/skills/hb-fe/SKILL.md:39 (Codex 규칙에만 브라우저 검증)`

### maintenance auto와 deep의 visual 이슈 유형 비대칭
maintenance:auto의 M1 이슈 유형에는 visual(디자인 적용 오류, responsive overflow)이 있고 M2 baseline·M6의 visual-regression.md 산출물도 정의돼 있지만, 더 무거운 tier인 maintenance:deep의 M1 유형 목록에는 visual이 없고 산출물 목록에도 visual-regression.md가 없다. 시각 이슈가 커서 deep으로 올라가면 오히려 시각 전용 유형·산출물이 사라지는 역전.
- 증거: `FE/commands/maintenance/auto.md:43 (visual 유형), :134 (visual-regression.md), :173 vs FE/commands/maintenance/deep.md:32-36 (visual 없음), :302-318 (산출물에 visual-regression.md 없음)`

### feature:deep이 CM 복사본 그대로 — 계약 단계 부재 + 유령 산출물 7종
CLAUDE.md는 feature:deep을 'BE/FE 연동, migration, Socket event 변경 동반' 작업용으로 지정하는데, 정작 deep 파이프라인(F1~F11)에는 계약 점검 스텝이 없다(auto에는 F3b pre + F8.4 post가 있음). 하단 주석 1줄로만 '구현 전 contract-check(pre)'를 언급. 산출물 목록에는 integration-plan.md, migration-review.md, websocket-contract-diff.md, api-contract-diff.md, rollback-plan.md, release-checklist.md, contract-check.md가 약속돼 있으나 이를 생성하는 파이프라인 스텝이 하나도 없다. F11(리뷰 반영+QA)에도 auto F8.4-5의 계약 post 검증·dual gate 스텝이 없다. 결과: 계약이 가장 중요한 대형 작업에서 가벼운 auto보다 계약 규율이 약한 역전.
- 증거: `CHAT/commands/feature/deep.md:1 (제목 '신규개발 파이프라인 (CM)'), :191-213 (산출물 목록 vs F1~F11에 생성 스텝 부재), :215 (하단 주석에만 contract-check 언급), :162-178 (F11에 계약 post/dual gate 없음) ↔ CHAT/commands/feature/auto.md:67-73(F3b), :144-145(F8.4-5)`

### maintenance:deep에 계약 점검·dual gate 산출물 연결이 전무
CLAUDE.md가 maintenance:deep을 'race condition·메시지 중복·읽음 처리·장애급' 전용으로 지정 — 소켓 이벤트 payload를 건드릴 확률이 가장 높은 트랙인데, 파일 전체에서 contract-check/websocket-events.yaml/api-contract.yaml/review-gates 언급이 0회(M9의 hb-shared 배너 1줄 제외). 산출물 목록에도 codex-review.md·contract-check.md가 없다. auto tier는 둘 다 있음(171-177행). 읽음 처리 버그를 deep으로 고치다 이벤트 계약이 바뀌어도 아무 게이트가 안 잡는다.
- 증거: `CHAT/commands/maintenance/deep.md:302-318 (산출물에 codex-review.md·contract-check.md 부재), grep 'contract|websocket-events|api-contract|review-gates|codex' 결과 278행 배너 1건뿐 ↔ CHAT/commands/maintenance/auto.md:171-177 (contract-check.md·codex-review.md 포함 + 하단 계약 주석)`

### ADR 편입 경로가 두 갈래로 상충 — planning 직행 vs adr:new 경유
planning/auto.md P4·deep.md P7은 '사용자 승인 → /hb-chat:shared:update-docs adr 직접 호출'로 편입을 끝낸다. 반면 adr/new.md는 'planning에서 나온 decision-draft.md를 바로 넣지 않고 이 트랙으로 정식 편입한다'고 선언. 같은 draft가 어느 길로 가야 하는지 문서가 서로 반대말을 한다. adr:new를 거치면 D3 승인 게이트를 한 번 더 통과 — 이미 planning에서 승인받은 사용자에게 이중 승인 핑퐁(세리머니 중복).
- 증거: `CHAT/commands/planning/auto.md:62-67 [P4] ↔ CHAT/commands/adr/new.md:5 ('바로 넣지 않고 이 트랙으로 정식 편입'), CHAT/CLAUDE.md:31 (planning→ADR draft→승인→update-docs 순서만 명시, adr:new 위치 불명)`

### SKILL.md·CLAUDE.md가 존재하지 않는 convention-check 명령 파일을 참조
SKILL.md 46행이 'commands/maintenance/convention-check.md'를 참조하지만 CHAT에는 그 파일이 없다(실체는 SHARED/commands/maintenance/convention-check.md + maintenance:deep M5가 생성하는 산출물명). CLAUDE.md 90행도 bare 파일명으로 참조. Codex가 SKILL.md의 Source Of Truth 지시대로 파일을 열면 실패. 또 SKILL.md Command Mapping(23-36행)에 chat의 시그니처인 shared:review-gates·feature:contract-check alias가 빠져 있다 — dual gate의 절반이 Codex인데 Codex 진입점 문서가 게이트 명령을 모른다.
- 증거: `CHAT/skills/hb-chat/SKILL.md:46 (깨진 경로), :23-36 (review-gates/contract-check alias 누락), CHAT/CLAUDE.md:90, 실체: SHARED/commands/maintenance/convention-check.md + CHAT/commands/maintenance/deep.md:151-164 [M5]`

### 9개 파일에 CM 잔재 — 제목·식별자·예시가 다른 레포 도메인
deep 3종(feature/planning/maintenance)·rca·reproduce·impact-analysis·alternatives·research·reflect 총 9개 파일 제목이 '(CM)'. 식별자 예시가 BUCCL-CM-42/99(4곳). planning/interview.md는 '기존 시스템(예약, 결제, 커뮤니티)'과 booking/payment 모듈 예시, planning/scope.md 이해관계자 템플릿은 '백엔드(Django/DRF)·DB(MariaDB)·Innopay'(BE 스택), feature/reflect.md 판정 예시는 post.service.ts(커뮤니티 도메인), rca.md는 'CM(Node/TS/Express) 특화'. 스택이 같아 동작은 하지만, 명령을 연 순간 '내가 어느 플러그인에 있나' 혼동 + planning 인터뷰가 chat 도메인(room/message/presence) 대신 예약/결제를 묻는 실질 오작동.
- 증거: `grep '(CM)' 결과 9개 파일 (CHAT/commands/feature/deep.md:1, feature/reflect.md:1, maintenance/deep.md:1, maintenance/rca.md:1,23, maintenance/reproduce.md:1,39, maintenance/impact-analysis.md:1, planning/alternatives.md:1, planning/deep.md:1, planning/research.md:1); BUCCL-CM: maintenance/auto.md:18, deep.md:13, hotfix.md:28, impact-analysis.md:12; CHAT/commands/planning/interview.md:27,60-61; planning/scope.md:49-56; feature/reflect.md:32,40`

### 28개 명령 중 15개가 내부 단계 문서인데 진입점과 동급으로 노출
CLAUDE.md 트랙 표는 13개 진입점만 안내하지만, 명령 팔레트에는 /hb-chat:planning:interview, :feature:pr-body, :maintenance:rca 등 내부 단계 문서 15개가 같은 층위로 뜬다. 이들은 '이 skill은 Fork에서 실행된다' 정도만 있고 어느 파이프라인의 몇 번째 스텝인지, 직접 부르면 되는지 안내가 없다. auto/deep 파이프라인이 내용을 인라인으로 중복 보유해 이미 drift 발생(예: auto/deep의 스텝 본문과 sub-step 파일 내용이 다름 — reflect.md는 CM 예시 그대로).
- 증거: `CHAT/CLAUDE.md:40-54 (13개 진입점 표) vs CHAT/commands/ 28개 파일; CHAT/commands/feature/pr-body.md:5-7, planning/scope.md:5-7 등 부모 파이프라인 미표기; 파이프라인 인라인 중복: feature/auto.md:44-53 [F2] ↔ SHARED가 아닌 자체 인라인`

### 게이트 어휘 이중화 — review-gates G1~G4 vs hb-shared R1~R5, 그리고 hb-shared 렌즈에 CHAT 부재
파이프라인 배너는 '리뷰 = /hb-shared:review 5단계(R1~R5, codex 자동 호출)'라 하고, review-gates.md는 자체 G1~G4 절차를 정의하며 G2는 'codex review 또는 사용자가 Codex 세션에서 수행'이라 해 자동/수동이 상충. 두 문서는 서로를 참조하지 않아 실행 시 어느 절차를 따를지 모호. 게다가 위임받는 SHARED/commands/review.md의 관점 렌즈(R2)와 완료기준 출처 목록에 BE/CM/FE만 있고 CHAT 항목(계약 정합성 렌즈)이 아예 없다 — chat이 가장 강조하는 계약 체크가 공통 관문 렌즈에서 누락.
- 증거: `CHAT/commands/shared/review-gates.md:19-43 (G1~G4, G2 '사용자가 Codex 세션에서 수행') ↔ CHAT/commands/feature/auto.md:112 (R1~R5 'codex 자동 호출') ↔ SHARED/commands/review.md:26-28 ('BE/CM = …, FE = …' — CHAT 렌즈 없음), :61 (완료기준 출처에 CHAT 없음)`

### 깨진 참조: 3개 SKILL.md가 존재하지 않는 convention-check 경로를 가리킴
convention-check가 SHARED로 이동(무손실 이동 7개 중 하나)했는데, BE/CM/CHAT의 Codex 진입점 SKILL.md는 여전히 자기 플러그인의 `commands/maintenance/convention-check.md`를 지시한다. 해당 파일은 세 플러그인 어디에도 없다(SHARED/commands/maintenance/convention-check.md에만 존재). Codex가 SKILL.md를 따라가면 파일을 못 찾는다. 린터 R7은 파일 존재만, R8은 FE만 봐서 이 부류를 못 잡는다.
- 증거: `BE/skills/hb-be/SKILL.md:37, CM/skills/hb-cm/SKILL.md:37, CHAT/skills/hb-chat/SKILL.md:46 — 셋 다 'via `commands/maintenance/convention-check.md`'; `find`로 BE/CM/CHAT commands/maintenance/에 해당 파일 부재 확인, docs/SHARED-CORE-DESIGN.md:79가 이동 사실 명시`

### hb-shared의 핵심(seed/evaluate/review/evolve)이 Codex 쪽 등록 메타데이터에 통째로 누락
README와 SHARED/CLAUDE.md는 hb-shared의 존재 이유를 방법론 순서표(seed→evaluate→review→evolve)라고 소개하는데, Codex 진입점인 SHARED/skills/hb-shared/SKILL.md의 Source Of Truth·Command Mapping에는 보조 명령 6개만 있고 순서표 4개 명령이 전혀 없다. .codex-plugin/plugin.json defaultPrompt와 양쪽 marketplace.json 설명도 마찬가지. Phase 2에서 추가된 명령이 Codex 레이어로 전파되지 않은 전형적 이중 등록 드리프트.
- 증거: `SHARED/skills/hb-shared/SKILL.md:14-30 (requirements~feasibility 6개만 나열), SHARED/.codex-plugin/plugin.json defaultPrompt 3종 모두 보조 명령, .claude-plugin/marketplace.json:32 설명도 보조 명령만 나열 vs SHARED/commands/{seed,evaluate,review,evolve}.md 존재`

### seed/evaluate는 반쪽 연결 — CLAUDE.md는 '자동 적용'을 주장하지만 파이프라인 문서에는 앵커가 없음
4개 도메인 CLAUDE.md '방법론 연결'은 feature:auto 호출 시 seed(주문서)→evaluate(검사)가 자동 적용된다고 서술하지만, 실제 실행 소스인 feature/maintenance auto·deep 문서 어디에도 seed·evaluate 언급이나 seed.md/evaluate-report.md 산출물이 없다(grep 0건). review만 F7 등에 인라인 앵커가 있다. SKILL.md는 명령 문서를 source of truth로 지정하므로, 스텝을 따라가는 에이전트는 주문서 없이 F1→F2로 직행한다. '병렬로만 두면 없는 것과 같다'는 사용자 교훈의 정확한 재발 지점.
- 증거: `BE/CLAUDE.md:100-110(자동 적용 주장) vs BE/commands/feature/auto.md F1~F8(seed/evaluate 0건, grep 'seed\.md' 도메인 4곳 전부 0건); README.md:73-91 산출물 구조에도 seed.md·evaluate-report.md 부재`

### 같은 리뷰 관문의 산출물 이름이 두 갈래: review-report.md vs review-comments.md
SHARED review.md는 [R5]에서 review-report.md를 병합·확정하라고 하고, 16개 도메인 파이프라인과 README·CLAUDE.md 전이 다이어그램은 전부 review-comments.md를 쓴다. 도메인 F7 헤더가 '이 리뷰 = /hb-shared:review 5단계 관문'이라고 선언하므로 에이전트는 서로 다른 두 출력 스펙을 동시에 받는다 → 실행마다 산출물 이름이 흔들리고 후속 단계(F8 '리뷰 반영'은 review-comments.md를 읽음)가 빈손이 될 수 있다.
- 증거: `SHARED/commands/review.md:47,51-53(review-report.md) vs BE/commands/feature/auto.md:119(review-comments.md 저장), grep 결과 review-report는 SHARED/commands/review.md 단 1개 파일에만 존재`

### CHAT은 리뷰 관문이 두 벌 — Codex 생략 가능 여부가 정면 모순
CHAT CLAUDE.md는 완료기준으로 review-gates.md(dual gate)를 강제하면서(32행) 동시에 '방법론 연결'로 /hb-shared:review 5단계 대체도 선언한다(101행). 두 프로토콜은 (a) Codex 생략: SHARED [R3]는 '미설치/실패 시 건너뛰되 명시' 허용 vs review-gates anti-rationalization 표는 '생략 금지', (b) 산출물 위치: .harness/artifacts/review/{identifier}/ vs {track}/{identifier}/, (c) 최대 라운드(3회) 유무가 서로 다르다. 세리머니를 싫어하는 사용자가 CHAT에서 리뷰를 사실상 두 번 돌게 되는 구조.
- 증거: `CHAT/CLAUDE.md:32 vs CHAT/CLAUDE.md:101; SHARED/commands/review.md:37('건너뛰되…명시') vs CHAT/commands/shared/review-gates.md:70('Codex 리뷰는 생략' 금지) 및 :57(.harness/artifacts/review/ 경로)`

### README 문서 드리프트 3건: 실행 모드 분포 표 오류, FE api-binding-check 누락, 방법론 산출물 누락
(a) README '실행 모드 분포'의 신규개발 행(Sub-agent: F3,F5,F7)은 auto(F3·F5=Fork, F7=Sub-agent)와 deep(F3=Sub, F5=Fork+Sub, F7=Fork[TDD Green], 리뷰는 F10) 어느 tier와도 일치하지 않는다. (b) FE 추가 산출물 목록에 api-binding-check.md가 없다 — 사용자가 중요시하는 FE 두 모드 중 바인딩 모드의 유일한 증거 산출물인데 README에는 디자인 모드 5종만 있다. (c) 산출물 구조에 seed.md·evaluate-report.md·review-auto-log.txt 등 hb-shared 산출물이 반영되지 않았다.
- 증거: `README.md:63 vs BE/commands/feature/deep.md:47-135·auto.md:53-100(스텝 헤더 모드 대조); README.md:90-91(visual-regression.md까지만) vs FE/CLAUDE.md:120·FE/commands/feature/auto.md:195(api-binding-check.md); README.md:73-91 vs SHARED/commands/seed.md:53`

### 설치된 플러그인에서 깨지는 경로 + 보조 명령 이중 유지보수
(a) SHARED/CLAUDE.md가 '설계 전문: docs/SHARED-CORE-DESIGN.md'를 가리키지만 plugin source는 ./SHARED라 설치본에는 이 파일이 없다. (b) /hb-shared:feature:requirements 등 보조 명령 6개는 도메인 파이프라인·README Quick Start 어디서도 호출되지 않고(grep 0건), 같은 절차가 F2/F3/F5에 인라인 중복되어 있다 — 이미 SHARED requirements.md에는 인라인 F2에 없는 '기존 모듈 연결점' 표가 있어 내용 드리프트가 시작됐다. team-protocol.md도 4벌 복제인데 내용 드리프트는 어떤 린터도 안 본다.
- 증거: `SHARED/CLAUDE.md:34 + .claude-plugin/marketplace.json:31(source ./SHARED, docs/는 리포 루트); grep 'hb-shared:feature|hb-shared:maintenance|hb-shared:planning' 도메인 4곳 0건; SHARED/commands/feature/requirements.md:40-42 vs BE/commands/feature/auto.md:42-51; docs/SHARED-CORE-DESIGN.md:3(team-protocol 도메인 잔류 '추후 정합화 대상')`

### seed·evaluate가 프로즈로만 연결 — 명령 본문에 0회 등장, 이중 질문 또는 조용한 생략
4개 CLAUDE.md의 '방법론 연결' 섹션은 feature/maintenance 호출 시 seed→evaluate가 '자동으로 적용된다'고 하지만, 트랙 명령 본문 어디에도 seed.md를 읽거나 쓰는 스텝이 없다(grep 'seed'·'evaluate' 결과 전 플러그인 commands/에서 0건, review만 연결됨). 실행 시 두 결말뿐이다: (1) seed에서 목표·범위·MUST/SHOULD/NICE를 물은 뒤 F2가 seed.md를 모른 채 같은 요구사항을 또 물음(S4 확정 + F2.3 질문 = 이중 핑퐁), (2) 모델이 seed를 건너뜀 — '아무것도 안 바뀐 것'처럼 보이는 과거 교훈 그대로. 또한 F7 리뷰가 5관문으로 '대체'되었다면서 트랙 산출물 목록에는 review-comments.md만 있고 5관문의 review-report.md·review-auto-log.txt(SHARED/commands/review.md:51,20)는 없어 산출물 이름도 갈라진다.
- 증거: `BE/CLAUDE.md:100-110 (방법론 연결) vs BE/commands/feature/auto.md:42-52 (F2가 planning 산출물만 참조, seed.md 미참조); SHARED/commands/seed.md:3 ('scope+requirements+criteria를 하나로 흡수한 진입점') vs BE/commands/feature/auto.md:49 (F2가 MUST/SHOULD/NICE 재분류); SHARED/commands/review.md:51 vs BE/commands/feature/auto.md:166`

### 시나리오 A: 엔드포인트 하나에 사용자 핑퐁 최대 6회 + 산출물 9~12개 + 워크트리 6회 생성·해체
BE feature:auto를 본문대로 따라가면: seed S1.2(크기 확인)+S4.1(주문서 확정) 2회, F1.4(브랜치·base 확인) 1회, F2.3(요구사항 질문) 1회, F3.3(설계의도 논의점) 1회, F8.2(리뷰 수용/거부) 1회 = 최대 6회 핑퐁. 산출물은 seed.md+requirements.md+design-intent.md+tdd 3종+review-comments.md+pr-body.md+INDEX.md(+5관문 로그 2종). worktree(fork) 생성·해체가 6회인데 그중 F2·F3은 .md 문서만 쓰는 스텝이라 격리 가치가 없다. 특히 F1.4는 git으로 방금 resolve한 branch명을 다시 확인받는 순수 핑퐁이다. '엔드포인트 하나'가 이 무게면 사용자는 하네스를 부르지 않고 그냥 시키게 된다.
- 증거: `BE/commands/feature/auto.md:35-38 (F1 사용자 확인), :44,:57,:67,:80,:91,:124 (worktree 생성 6회), :156-168 (산출물 목록); SHARED/commands/seed.md:24,:51 (사용자 확인 2회)`

### 시나리오 B: hotfix의 '리뷰 전부 스킵'과 CLAUDE.md '머지 전 5관문 적용'이 정면 충돌
hotfix.md는 'RCA, 영향도, 리뷰, 전체 회귀 모두 스킵'을 핵심 원칙으로 선언하는데, 같은 플러그인 CLAUDE.md의 방법론 연결은 'feature·maintenance 작업은'(hotfix는 maintenance T0) '머지 전 /hb-shared:review의 5단계 관문을 적용한다'고 무예외로 선언한다. 항상 읽히는 CLAUDE.md가 이기면 한 줄 수정에 Codex 교차검증 포함 5관문이 돌고, hotfix.md가 이기면 방법론 위반처럼 보인다 — 실행마다 결과가 달라질 수 있는 모호성. hotfix 자체는 잘 설계돼 있으나(핑퐁 1~2회) 이 충돌이 T0의 예측 가능성을 깎는다.
- 증거: `FE/commands/maintenance/hotfix.md:22 ('RCA, 영향도, 리뷰, 전체 회귀 모두 스킵') vs FE/CLAUDE.md:125-130 ('feature·maintenance 작업은 ... 머지 전 5단계 관문을 적용한다' — T0 예외 언급 없음)`

### 시나리오 C: 계약 변경 하나에 수동 명령 체인 3~5개 + Codex 2회 호출 + 계약 산출물 위치 단절
CHAT 메시지 타입 추가는 본문대로면: /hb-chat:contract:websocket(W4에서 승인 대기로 종료) → /hb-chat:shared:update-docs websocket(승인 게이트) → 네이밍/버전 건드리면 /hb-chat:adr:new → update-docs adr → 그제서야 feature:auto — 각 명령이 '사용자 승인 후 X로 편입'으로 끝나고 다음 명령을 자동으로 이어주지 않아 사용자가 체인을 외워서 수동 연결해야 한다. feature:auto 안에서는 F7이 5관문 [R3]로 Codex를 호출하고, F8.5의 dual review gate가 또 Codex 리뷰를 요구해(최대 3라운드 루프) 같은 diff에 Codex가 2회 돈다. 또 contract:websocket 산출물은 .harness/artifacts/review/ws-{slug}/에 남는데 feature 흐름(F3b)은 yaml만 읽고 이 diff 문서를 참조하지 않으며, CLAUDE.md는 feature 식별자를 {feature-slug}, 명령 본문은 {branch-name}으로 서로 다르게 정의해 아티팩트 디렉토리가 갈라질 수 있다.
- 증거: `CHAT/commands/contract/websocket.md:14,:44-48 (review/ws-{slug} 산출물, 승인 후 update-docs로 편입) → CHAT/commands/feature/auto.md:12,:67-73 (F3b는 yaml만 재확인), :112 (F7=5관문, Codex [R3]) + :145 (F8.5 dual gate에서 Codex 재호출); CHAT/commands/shared/review-gates.md:33-43 (G2 Codex 독립 리뷰 + 최대 3라운드); CHAT/CLAUDE.md:63 ({feature-slug}) vs CHAT/commands/feature/auto.md:41 ({branch-name})`

### FE 두 모드(디자인/바인딩) 분류가 명령 스텝에 없고, 순수 바인딩 작업에도 시각 산출물 3종이 무조건 강제됨
FE/CLAUDE.md는 '작업 시작(seed) 시 모드를 먼저 분류'하라지만 feature:auto 파이프라인에 분류 스텝이 없다(F3은 '디자인 입력이 있으면'으로 우회 언급뿐). F7은 visual-check.md·responsive-check.md·accessibility-notes.md 기록을 무조건 요구하고, N/A 탈출구는 api-binding-check.md 한 방향에만 있다('디자인 구현 전용이면 N/A'). 반대로 순수 API 바인딩 작업(디자인 변화 0)에도 375/768/1440 반응형 체크와 a11y 노트를 만들어야 한다 — 'FE는 두 모드'라는 사용자의 핵심 구분이 명령 레벨에서 반쪽만 구현된 상태.
- 증거: `FE/CLAUDE.md:63 ('작업 시작(seed) 시 이 작업이 어느 모드인지 먼저 분류') vs FE/commands/feature/auto.md:109-122 (F7: visual/responsive/a11y 무조건, N/A escape는 :120의 api-binding-check에만 존재)`

### 진입점 인지 부하: 레포당 8~13개 명령 + hb-shared 10개, 디스패처 없음 — README Quick Start는 CHAT·SHARED를 아예 누락
작업 하나 시작할 때 사용자는 트랙 3 × tier 3 + shared:update-docs + (CHAT은 adr/contract/verify/review-gates 추가) + hb-shared의 seed/evaluate/review/evolve/보조 6종 중에서 골라야 한다. tier 선택 기준 표는 있지만 '이 요청이 feature인가 maintenance인가, hotfix로 될까'를 판단해 주는 단일 진입 명령이 없다. 게다가 README Quick Start 2단계는 hb-be/hb-cm/hb-fe만 활성화하라고 하고 hb-chat·hb-shared가 빠져 있으며, 명령 예시 블록(118-149행)에도 /hb-chat:* 예시가 하나도 없고, 3단계 '4개 YAML'은 CHAT의 10개 문서(websocket-events 등)와 불일치 — 정작 세리머니가 가장 무거운 CHAT이 온보딩 문서에서 투명인간이다.
- 증거: `README.md:109 (활성화 목록에 hb-chat·hb-shared 누락), :110 ('4개 YAML' vs CHAT/CLAUDE.md:68-83의 10개 문서), :118-149 (예시에 /hb-chat 부재); CHAT/CLAUDE.md:40-54 (13개 명령 표)`

### 산출물 재사용이 우연에 의존 — 이전 작업 산출물을 찾는 인덱스가 없고, auto만 쓰면 재사용 풀이 영원히 빈다
F1.6은 '기존 code-quality-guide.md가 같은 영역에 이미 있는지 확인'하라지만 아티팩트는 .harness/artifacts/feature/{branch-name}/별로 흩어져 있어 '같은 영역'을 찾으려면 과거 브랜치 디렉토리 전체를 뒤져야 하고, 그 방법은 어디에도 정의돼 있지 않다. F2의 'planning 트랙 산출물이 있으면 가져온다'도 plan-YYYYMMDD-slug ↔ branch명 연결 고리가 없다. 결정적으로 auto tier는 code-quality-guide.md를 생성하지 않으므로(':170-171') deep을 안 쓰는 일상 사용자의 재사용 풀은 항상 비어 있다 — '이전 작업 산출물이 다음 작업에 자동 참조되는가'에 대한 답은 사실상 No.
- 증거: `BE/commands/feature/auto.md:40 (같은 영역 확인 — 탐색 방법 미정의), :45-47 (planning 산출물 연결 고리 없음), :170-171 ('auto tier는 prior-art.md, code-quality-guide.md를 생성하지 않는다'); README.md:73-88 (식별자별 분산 구조)`

## 잘된 점 (유지할 것)

- 완료기준·증거·리뷰 렌즈를 스택에 위임하는 원칙이 4개 코어 명령 전체에 일관되게 박혀 있다 — pytest/npm test 하드코딩 금지 명시 (SHARED/commands/evaluate.md:9-12, review.md:8-10, seed.md:42-45)
- 울트라코드 ON/OFF '항상 작동' 저하 경로가 seed/evaluate/review/evolve 모두에 명시되어 lightweight 기본값이 살아 있다 (seed.md:16, evaluate.md:14-15, review.md:11-13, evolve.md:16)
- review 5단계 관문은 실제로 4개 도메인 x feature/maintenance x auto/deep 16개 명령에 인라인 연결됨 — '기본 진입점에 연결' 교훈이 review에는 적용됐다 (BE/commands/feature/auto.md:102 등)
- 컨텍스트 절약 원칙(무거운 읽기는 Sub-agent, 결론·경로만 회수)이 모든 명령에 반복 명시돼 실사용 시 메인 컨텍스트가 안 터진다 (SHARED/CLAUDE.md:32)
- 린터 R5/R6/R7/R9 기준으로 SHARED 경로·등록·버전 패리티가 현재 전부 green (bash scripts/lint-harness.sh 실행 확인)
- tier 체계(T0 hotfix/T1 auto/T2 deep)와 양방향 에스컬레이션 표가 구체적 — BE/commands/maintenance/hotfix.md:105-119의 '상황→전환 대상' 표는 실사용 가능한 수준의 판단 기준을 제공한다
- shared/tdd.md가 형식적이지 않고 실전적 — 카운터 persistence/reset 규칙(tdd.md:60,88-92), Django/DRF Mocking 카탈로그(tdd.md:159-176)가 'fixture 오류를 구현 부재로 오분류'하는 실제 실패 모드를 막는다
- Django 특화 내용이 진짜다: RCA 체크리스트의 CONN_MAX_AGE/Fernet/SimpleJWT/Signal(rca.md:22-35), verify.md의 makemigrations --check, factory_boy 규약 — 복붙 템플릿이 아니라 이 스택의 실제 함정 목록
- hb-shared 5단계 리뷰 관문은 명목이 아니라 실제로 배선됨 — F7/F10/M7/M9 네 곳 모두 동일한 blockquote로 R1~R5를 스텝 본문에 박아놓았다(feature/auto.md:102 등)
- team-protocol.md의 '단일 응답 내 병렬 tool_use 필수'(:22-36), 팀원별 산출 파일 분리, 강제 정리 명령(:71)은 실제 운영에서 얻은 교훈이 코드화된 것
- planning/maintenance의 '본문 제시 (필수)' 규칙(planning/auto.md:40 등)이 '파일에 저장했으니 읽어보세요' 안티패턴을 차단한다
- feature/maintenance 트랙과 shared/tdd.md·verify.md·rca.md·reproduce.md는 스택 치환이 충실함 — Jest 버전별 플래그 분기(--testPathPattern vs --testPathPatterns), Node test-harness 카탈로그(supertest/ioredis-mock/socket.io-client/nock), CM 특화 RCA 체크리스트(EventLoop blocking, unhandled rejection, Socket.io sticky session, Redis adapter, 메인 BE JWT 공유)까지 실질적 특화가 되어 있음 (CM/commands/shared/tdd.md:174-192, CM/commands/maintenance/rca.md:23-40)
- T0/T1/T2 tier 체계와 양방향 에스컬레이션 기준이 명확 — hotfix의 'Refactor 조작적 정의'(변경 되돌리면 H1이 다시 FAIL하는가)와 에스컬레이션 표에 Socket.io/SQL 스키마 항목까지 CM 상황이 반영됨 (CM/commands/maintenance/hotfix.md:78-121)
- hb-shared 5단계 리뷰 관문이 4개 리뷰 지점(feature auto F7/deep F10, maintenance auto M7/deep M9)에 모두 일관되게 임베드되어 BE와 패리티 유지 (CM/commands/feature/auto.md:103, CM/commands/maintenance/deep.md:278)
- 린터 규칙(R3 스텝 대칭, R2 TeamDelete, R5/R6 경로)에 부합하는 구조 — 스텝 헤더 수 BE와 대칭, 팀 스펙 파일에 TeamDelete/병합 섹션 포함
