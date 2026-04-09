# 코드리뷰

평가기준·설계의도·PR본문·diff·TDD 증거를 입력받아 근거 기반 코드리뷰를 수행한다.

## 실행 방식

이 skill은 Sub-agent가 자동으로 실행한다. 사용자 확인 없이 진행된다.

## Sub-agent 프롬프트

```
다음 문서와 diff를 분석하여 코드리뷰를 수행하라.

리뷰 원칙:
1. 설계의도와 PR 본문을 통해 작성자의 의도를 깊이 이해하라.
2. 모든 코멘트는 code-quality-guide.md의 기준에 근거해야 한다. 근거 없는 취향 리뷰 금지.
3. 의도적 결정(design-intent.md에 명시)을 존중하라. 단, 의도와 구현의 불일치는 지적하라.
4. 변경 제안 시 side effect가 있으면 반드시 함께 설명하라.
5. **TDD 증거 교차검증 (MANDATORY)**: tdd-baseline-log.txt(Red FAIL 증거)와 tdd-green-log.txt(Green PASS 증거)가 실제로 Red 테스트 파일과 Green diff에 대응하는지 검증하라:
   - (a) tdd-baseline-log.txt의 실패 테스트 이름이 Red 테스트 파일에 실제로 존재하는가?
   - (b) tdd-baseline-log.txt의 module 경로가 git diff의 신규/수정 테스트 파일 경로와 일치하는가?
   - (c) tdd-baseline-log.txt는 FAIL, tdd-green-log.txt는 PASS를 보이며 전환 방향이 올바른가? (refactor 이슈 유형은 예외 — baseline이 PASS baseline이므로 두 로그 모두 PASS)
   - (d) tdd-green-log.txt의 PASS 테스트가 실제로 구현된 코드(git diff의 non-test 파일)를 exercise하는가? (단순 assert True 의심 여부)
   - 불일치·의심 사항이 하나라도 있으면 **[p1] TDD Evidence Mismatch**로 보고하라. 로그 파일 조작은 test-after 회귀의 신호다.

우선순위:
- [p1] 반드시 수정. 버그, 기준 위반, 의도-구현 불일치, **TDD 증거 불일치**
- [p2] 강력 권장. 유지보수성, 가독성에 유의미한 영향
- [p3] 권장. 개선하면 좋지만 현재도 동작에 문제 없음
- [p4] 사소한 개선. 네이밍, 포맷팅 등

[code-quality-guide.md]
[design-intent.md]
[pr-body.md]
[git diff main...HEAD]
[tdd-baseline-log.txt]
[tdd-green-log.txt]
```

## 산출물: review-comments.md

```markdown
# Code Review

## Summary
(전체 코드 품질에 대한 간략한 총평)

## TDD Evidence Verification
- tdd-baseline-log.txt ↔ Red 테스트 파일 일치: PASS | FAIL
- tdd-green-log.txt ↔ Green diff 일치: PASS | FAIL
- Baseline → Green 전환 방향 올바름: PASS | FAIL (refactor 유형은 "PASS baseline 유지" 체크)
- 의심 사항 (있으면 [p1]로 아래 Comments에 전달):

## Comments

### [p1] {파일경로}:{라인}
- 근거: {code-quality-guide.md의 어떤 기준}
- 내용: ...
- 제안: ...
- side effect: (없으면 "없음")
- 제안 이유: (side effect에도 불구하고 이 방향을 제안하는 이유)

### [p2] {파일경로}:{라인}
- 근거: ...
- 내용: ...
- 제안: ...
- side effect: ...
- 제안 이유: ...

### [p3] {파일경로}:{라인}
- 근거: ...
- 내용: ...
- 제안: ...

### [p4] {파일경로}:{라인}
- 내용: ...
- 제안: ...
```
