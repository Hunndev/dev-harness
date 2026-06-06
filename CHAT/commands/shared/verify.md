# 검증 (QA)

구현/수정 완료 후 코드 품질과 동작을 검증한다. feature·maintenance 트랙에서 사용하며, `commands/shared/review-gates.md`의 1~4단계를 담당한다.

## 실행 방식

이 skill은 Fork에서 실행된다.

## 검증 항목

### 1. 테스트 (Jest)
```bash
npm test                       # 전체 (회귀 포함)
npm test -- --watchAll=false   # CI 모드 (watch 비활성)
```
대상 모듈만 빠르게 보려면 `npm test -- <path/pattern> --watchAll=false`.

### 2. 린트 (ESLint)
```bash
npm run lint
```
0 error여야 통과. warning은 기록.

### 3. 타입 체크 (tsc)
```bash
npx tsc --noEmit
```
타입 에러 0이어야 통과.

### 4. 빌드
```bash
npm run build
```

### 5. Convention / 경계 체크
변경 파일에 대해 `.harness/docs/code-convention.yaml` 및 chat 경계 위반 여부 확인:
- console.log 잔존 (logging 규칙)
- any 남용 / 타입 우회
- BE DB 직접 접근 (금지)
- Socket 이벤트가 `websocket-events.yaml` 미등록
- REST 변경이 `api-contract.yaml` 미반영
- 첨부 원본 DB 저장

### 6. 결과 판정
- 1~5 전부 PASS → 통과 → `review-gates.md`의 dual review(G1/G2)로 진행
- 실패 → 수정 루프 (최대 3회)
- 3회 초과 → 사용자에게 보고하고 판단 요청

> 프로젝트 스크립트(`package.json`)가 확정되면 위 명령을 실제 스크립트명에 맞춘다.

## 보고 형식

```markdown
## 검증 결과

### 테스트 (Jest): {N} 통과 / {M} 실패
### 린트 (ESLint): PASS | FAIL ({N} error)
### 타입 (tsc --noEmit): PASS | FAIL
### 빌드: PASS | FAIL
### Convention / 경계 위반: {N}건
### 최종: PASS | FAIL  → (PASS면 dual review로)
```
