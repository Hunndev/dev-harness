# PR 본문 생성

git diff 기반으로 PR 본문을 생성한다.

## 실행 방식

이 skill은 Fork에서 실행된다.

## 절차

1. `git diff main...HEAD`로 변경 내용을 수집한다.
2. 변경된 파일 목록과 각 파일의 변경 내용을 분석한다.
3. PR 본문 초안을 작성한다.
4. 초안과 **명확히 해야 할 논의점**을 사용자에게 제시한다:
   - breaking change 여부
   - 마이그레이션 필요 여부
   - 관련 이슈 번호
5. 사용자 피드백을 반영하여 확정한다.

## 산출물: pr-body.md

```markdown
# PR: {제목}

## Summary
(이 PR이 해결하는 문제와 접근 방식 요약, 1-3문장)

## Changes

### {모듈/영역}
- ...

## Breaking Changes
(없으면 "없음")

## Migration
(없으면 "없음". 있으면 마이그레이션 파일 목록과 주의사항)

## Test Plan
- [ ] ...

## Related
- 설계의도: `.harness/artifacts/feature/{branch}/design-intent.md`
- ADR: ...
- 이슈: ...
```
