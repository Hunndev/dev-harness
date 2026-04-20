# 검증 (QA)

구현/수정 완료 후 코드 품질과 동작을 검증한다.
feature(F8/F11) 및 maintenance(M6/M8) 트랙에서 사용한다.

## 실행 방식

이 skill은 Fork에서 실행된다.

## 검증 항목

### 1. 타입 체크
```bash
tsc --noEmit
```
TypeScript strict 모드 위반은 무조건 차단. any 사용 금지.

### 2. 린트
```bash
npm run lint
```
ESLint 규칙(single quotes, semi, prefer-const, eqeqeq) 위반 차단.

### 3. 테스트 실행
```bash
npm test -- src/__tests__/{module}    # 대상 모듈
npm test                                # 전체 (회귀 확인)
```

### 4. 빌드 (선택)
```bash
npm run build
```

### 5. Convention 체크
변경된 파일에 대해 `.harness/docs/code-convention.yaml` 위반 여부를 확인:
- console.log 사용 (GEN-004)
- any 타입 (GEN-005)
- 50줄 초과 함수 (GEN-001)
- Controller에 비즈니스 로직 (EXP-001)
- response.ts 헬퍼 미사용 (EXP-002)
- ApiError 미사용 (EXP-003)
- Repository 우회 SQL (REPO-002)
- SQL parameterized binding 미사용 (REPO-001)
- 경로 별칭 미사용, 상대경로 ../../ 두 단계 이상 (TS-003)
- 커버리지 임계 미달 (TEST-003: branches 70%, 나머지 80%)

### 6. 결과 판정
- 전체 PASS → 통과
- 실패 → 수정 루프 (최대 3회)
- 3회 초과 → 사용자에게 보고하고 판단 요청

## 보고 형식

```markdown
## 검증 결과

### 타입 체크: PASS | FAIL (에러 목록)
### 린트: PASS | FAIL (위반 목록)
### 테스트
- 대상 모듈: {N} 통과 / {M} 실패
- 전체: {N} 통과 / {M} 실패
- 커버리지: branches {X}%, functions {Y}%, lines {Z}%, statements {W}%
### Convention 위반: {N}건
### 최종: PASS | FAIL
```
