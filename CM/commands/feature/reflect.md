# 리뷰 반영 + QA (CM)

코드리뷰 코멘트를 검토하고, 수용 여부를 판단하여 코드를 수정한 뒤 QA를 수행한다.

## 실행 방식

이 skill은 Fork에서 실행된다.

## 절차

1. `review-comments.md`를 읽는다.
2. 각 코멘트에 대해 수용/거부를 판단한다:
   - [p1]: 기본 수용. 거부 시 명확한 근거 필수.
   - [p2]: 판단과 근거를 제시하고 사용자 확인.
   - [p3]: 판단을 제시하되 사용자 재량.
   - [p4]: 일괄 수용 또는 무시.
3. 판단 결과를 사용자에게 제시한다.
4. 사용자 확인 후 코드를 수정한다.
5. QA를 수행한다:
   - `tsc --noEmit` (TypeScript strict 컴파일 검사)
   - `npm run lint` (ESLint)
   - `npm test -- src/__tests__/{module}` (관련 모듈 테스트)
   - `npm test` (전체 회귀, 필요 시)
6. 실패 시 수정 루프 (수정 → QA → 재확인, 최대 3회).
7. 핵심 변경사항을 사용자에게 보고한다.

## 판정 형식

각 코멘트 하단에 판정을 추가한다:

```markdown
### [p1] src/services/post.service.ts:42
- 근거: ...
- 내용: ...
- 제안: ...
- **판정: ACCEPT** — 수정 완료. `extractPostMetadata()` 함수로 분리.
```

```markdown
### [p2] src/controllers/post.controller.ts:15
- 근거: ...
- 내용: ...
- 제안: ...
- **판정: REJECT** — 현재 구조에서 분리하면 오히려 복잡도 증가. design-intent.md 참조.
```
