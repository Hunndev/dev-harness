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

### 5. Convention 체크
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

### 6. 결과 판정
- 전체 PASS → 통과
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
### Convention 위반: {N}건
### 최종: PASS | FAIL
```
