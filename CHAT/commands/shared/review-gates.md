# 리뷰 게이트 (shared:review-gates)

chat 작업의 **완료 조건**을 정의·집행한다. 통과하지 못하면 "완료"가 아니다.

> chat은 계약이 깨지면 FE/BE/앱이 동시에 깨진다. 그래서 단일 리뷰가 아니라 **dual review gate**(Codex + Claude)를 강제한다.
>
> `/hb-shared:review`의 [R3] 생략 조항(소규모·미설치)은 **CHAT에는 적용되지 않는다** — 이 dual gate가 우선한다 (SHARED review [R3] 스택 우선 규칙).

## 완료 게이트 (5단계, 모두 통과)

```
1. npm test          → Jest 전체 통과 (회귀 포함)
2. npm run lint      → ESLint 0 error
3. npm run build     → tsc 빌드 성공
4. npx tsc --noEmit  → 타입 에러 0
5. dual review       → Codex review + Claude review 모두 blocking finding 0
```

1~4는 `commands/shared/verify.md`가 수행한다. 5가 이 문서의 핵심이다.

## Dual Review 절차

### [G1] Claude 리뷰 (Sub-agent)

1. `commands/feature/review.md`(또는 maintenance 리뷰) 기준으로 Claude sub-agent가 diff를 리뷰한다.
2. 입력: 설계의도, contract-check 결과, diff, TDD 증거(`tdd-baseline-log.txt`/`tdd-green-log.txt`).
3. 출력: `review-comments.md` ([p1]~[p4]). **[p1] = blocking.**
4. chat 특화 필수 체크:
   - Socket 이벤트가 `websocket-events.yaml`에 등록됐는가
   - REST 변경이 `api-contract.yaml`에 반영됐는가
   - BE DB 직접 접근이 없는가
   - 첨부 원본을 DB에 넣지 않았는가
   - 신청자 목록을 BE API 검증값만 썼는가

### [G2] Codex 리뷰 (외부)

1. 같은 diff를 Codex에 독립 리뷰시킨다 (`codex review` 또는 사용자가 Codex 세션에서 수행).
2. 출력: `codex-review.md`. Codex가 짚은 blocking finding을 수집한다.
3. Codex는 Claude와 **독립적인 시선** — 같은 사안을 둘 다 짚으면 신뢰도↑, 한쪽만 짚으면 메인이 기준 대조 후 채택/기각(근거 기록).

### [G3] 수정 루프 (메인)

1. Claude 또는 Codex가 blocking을 지적하면 → **Claude Code가 수정**한다.
2. 수정 후 1~4 재실행 + 해당 리뷰 재확인.
3. **둘 다 더 이상 blocking finding이 없을 때까지** 반복 (최대 3라운드, 초과 시 사용자 보고).

### [G4] 게이트 판정

```
PASS  = (1~4 전부 PASS) AND (Claude blocking 0) AND (Codex blocking 0)
BLOCKED = 그 외
```

판정을 `INDEX.md`에 `gate: PASS | BLOCKED (사유)`로 기록한다.

## 산출물

```
.harness/artifacts/{track}/{identifier}/     # 트랙 안에서 호출된 경우 (그 트랙의 리뷰 스텝이 이 파일들을 읽는다)
                                             # 트랙 밖 단독 호출 시에만 .harness/artifacts/review/{identifier}/
  review-comments.md   # Claude 리뷰 ([p1]~[p4])
  codex-review.md      # Codex 리뷰 blocking 목록
  consensus.md         # 양측 합의/불일치 정리 (선택)
  INDEX.md             # gate 판정, 수정 라운드 기록
```

## anti-rationalization (게이트 우회 금지)

| 핑계 | 반박 |
|---|---|
| "이 [p1]은 사소하니 넘기죠" | severity는 근거(`code-convention.yaml`/계약/ADR)로 정해진다. 사후 판단으로 내리지 않는다. |
| "테스트는 나중에" | TDD 증거(baseline/green) 없으면 G1에서 [p1]. 완료 불가. |
| "Codex 리뷰는 생략" | dual gate가 chat의 존재 이유. 한쪽만으로 완료 선언 금지. |
| "계약 문서는 코드 머지 후 갱신" | 계약 미등록 이벤트/엔드포인트는 [p1]. 머지 전 등록. |
