# 검증 (QA)

구현/수정 완료 후 코드 품질과 동작을 검증한다.
feature(F9/F12) 및 maintenance(M6/M8) 트랙에서 사용한다.

## 실행 방식

이 skill은 Fork에서 실행된다.

## 검증 항목

### 1. CRA build
```bash
npm run build
```
컴파일 오류, import 오류, 환경변수 누락, 번들 생성 실패를 차단한다.

### 2. 린트
```bash
npm run lint
```
ESLint 규칙(single quotes, semi, prefer-const, eqeqeq) 위반 차단.

### 3. 테스트 실행
```bash
npm test -- --watchAll=false src/__tests__/{module}    # 대상 모듈
npm test -- --watchAll=false           # 전체 (회귀 확인)
```

### 4. 화면 검증
디자인/레이아웃/라우팅 변경이 있으면 `visual-check.md`, `responsive-check.md`, `accessibility-notes.md` 또는 `visual-regression.md`가 최신인지 확인한다.
API 바인딩 변경이 있으면 `api-binding-check.md`(계약 일치·상태 처리·mock 잔재)도 최신인지 확인한다.

### 5. E2E 검증 (해당 시)
E2E 렌즈가 걸린 작업이면 (렌즈·환경·안전경계 정의: `CLAUDE.md`의 "E2E 검증 렌즈 (Playwright)" 절) 제품 repo의 Playwright 스크립트로 대상 시나리오를 실행하고 `e2e-check.md`가 최신인지 확인한다:
- **Origin 확인(fail-closed)**: context 생성·로그인·mutation 전에 browser baseURL·API/Chat origin을 resolve해 기록하고, **local 또는 명시 승인된 dev allowlist** 외의 origin(production·unknown host)이면 **즉시 중단(fail-closed)**한다.
- **재사용 가드**: F7/F9 Fork(또는 직전 실행)가 이미 실행해 남긴 `e2e-check.md`가 있으면, 거기 기록된 **검사 시점 HEAD SHA·E2E 대상 source/spec 파일 content fingerprint·환경·시나리오**가 현재와 **모두 동일할 때만 재실행하지 않고 그 결과를 재사용**한다 — 하나라도 다르면 재실행한다. `actual-dev` 결과는 추가로 **배포 identity**(served FE bundle URL+content digest, API/Chat deployment identity(노출 시), secret 제외 behavior-affecting config/fixture fingerprint)가 기록되어 있고 현재와 일치할 때만 재사용한다 — identity 증명 불가 시 **재사용 금지**(재실행).
- **maintenance 트랙**: E2E 렌즈가 걸렸는데 `e2e-check.md`가 아직 없으면 **이 항목이 실행·증거 생산을 담당**한다.
- 실행 환경(`local-mock` / `local-dev-api` / `actual-dev`)과 user-inst 독립 context(시나리오에 필요한 **역할별 독립 context** — 양계정 참여 시 `user`/`inst` 각각, 단일 역할은 해당 계정만; cookie·localStorage·sessionStorage·auth 격리) 기록
- 시나리오별 판정 `정상 / 비정상 / 미확인` + screenshot/video/trace 증거 경로
- `actual-dev`에서 생성한 테스트 데이터의 범위(고유 실행 ID)와 cleanup 여부
- 기존 spec 재사용/신규 추가 구분

### 6. Convention 체크
변경된 파일에 대해 `.harness/docs/code-convention.yaml` 위반 여부를 확인:
- console.log 사용 (GEN-004)
- 50줄 초과 함수 (GEN-001)
- component에 API/상태/도메인 로직 과도하게 집중 (COMP-001)
- hook 책임 위반 또는 dependency 누락 (HOOK-001)
- API client 계층 우회 호출 (API-001)
- style cascade, z-index, fixed position 변경의 영향 미기록 (STYLE-001)
- alt text, label, focus, contrast 누락 (A11Y-001)
- 상대경로 ../../ 두 단계 이상 (PATH-001)
- 커버리지 임계 미달 (TEST-003: branches 70%, 나머지 80%)

### 7. 결과 판정
- 전체 PASS (E2E `비정상`·`미확인` 0 포함) → 통과
- E2E `비정상` ≥ 1건 → FAIL. E2E `미확인`이 남으면 최종 PASS 불가 — `미확인`만 잔존해도 최종 판정은 **FAIL**로 기록하고 사유를 "미확인 잔존(환경/데이터 사유)"으로 명시한 뒤 사용자 판단을 요청한다. 환경/데이터 사유의 `미확인`은 아래 **수정 루프 대상이 아니다** — 즉시 사용자 판단으로 간다.
- 실패 → 수정 루프 (최대 3회)
- 3회 초과 → 사용자에게 보고하고 판단 요청

## 보고 형식

```markdown
## 검증 결과

### CRA build: PASS | FAIL (에러 목록)
### 린트: PASS | FAIL (위반 목록)
### 테스트
- 대상 모듈: {N} 통과 / {M} 실패
- 전체: {N} 통과 / {M} 실패
- 커버리지: branches {X}%, functions {Y}%, lines {Z}%, statements {W}%
### 화면 검증: PASS | FAIL | N/A
### E2E 검증: 정상 {N} / 비정상 {M} / 미확인 {K} | N/A (증거: e2e-check.md)
### Convention 위반: {N}건
### 최종: PASS | FAIL (E2E 미확인 잔존 시 PASS 불가 — 사유 명시)
```
