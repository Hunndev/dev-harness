# 리뷰 관문 (review)

머지 전 마지막 관문. **자동검사 → 관점별 리뷰 → Codex∥Claude 교차검증 → 반박(가짜 경보 제거) → 통과 판정**의 5단계로, 진짜 문제만 남겨 막는다. 모든 스택(BE/CM/FE/CHAT) 공통 stack-agnostic 관문이다.

## 실행 방식

- 무거운 diff 분석·리뷰·교차검증은 **Sub-agent로 내려** 수행하고, 메인은 **통과/blocking 결론과 산출물 경로만** 회수한다 (컨텍스트 절약). 무거운 단계는 백그라운드로 돌려도 된다.
- **완료기준·증거·리뷰 렌즈는 하드코딩하지 않는다 — 기준은 각 플러그인(스택)을 따른다.** 단일 정답 명령(`pytest`·`npm test` 등)을 박지 말 것.
  - BE/CM = 테스트·lint·build 통과 (구체 명령은 해당 플러그인 `shared/verify`).
  - FE = 시각·UX·반응형·접근성 + Claude 디자인 검증 (시각 회귀를 텍스트 통과로 환원하지 않는다).
- **도구 선택 / 울트라코드 — 항상 작동**:
  - **ON**: 관점별 리뷰어를 병렬 Sub-agent(필요 시 Claude Code 네이티브 Teams, 표준 팀 절차는 각 플러그인의 `shared/team-protocol`)로 분리하고, 반박 라운드로 가짜 경보를 제거한다.
  - **OFF**: 단일 Sub-agent가 핵심 관점만 순차로 가볍게 본다. 가시화·반박은 줄지만 근거 기반·산출물 회수 원칙은 동일하다.

## 절차

### [R1] 자동검사 게이트 (Sub-agent · blocking)

1. **Sub-agent를 호출**해 스택이 정의한 자동검사(린터·테스트·빌드, FE는 + 시각·반응형·접근성)를 실행한다 — 해당 플러그인 `shared/verify`.
2. raw 로그는 `.harness/artifacts/{track}/{identifier}/review-auto-log.txt`에 저장하고, 메인엔 통과/실패 + 경로만 회수한다.
3. **실패하면 즉시 멈춘다** → 사람·AI가 코드를 보기 전에 먼저 고친다 (싸게 거른다). 통과해야 [R2]로 넘어간다.

### [R2] 관점별 리뷰 (Sub-agent / 울트라코드 시 Teams)

1. 입력 경로만 확정한다(읽기는 Sub-agent에 위임): `code-quality-guide.md`(기준), `design-intent.md`(의도), `pr-body.md`, `git diff main...HEAD`, 스택 증거.
2. 관점을 나눠 리뷰한다 — **렌즈는 스택을 따른다**:
   - BE/CM = 버그 / 보안 / 성능 / 구조·간결성
   - FE = 디자인 일관성 / 시각 계층 / 접근성 / 구조 (+ Claude 디자인 리뷰)
3. 모든 코멘트는 `code-quality-guide.md` 기준에 **근거**한다. 의도적 결정(`design-intent.md`)은 존중하되, 의도–구현 불일치는 지적한다.
4. **증거 교차검증(필수)**: 제출된 스택 증거가 실제 diff에 대응하는가 — 증거 대상(테스트명·화면·경로)이 변경 파일에 실재하는가, 전환 방향이 올바른가, 비어 있지 않은가. 불일치는 [p1] Evidence Mismatch.
5. 울트라코드 ON이면 렌즈별 팀원을 병렬 스폰하고 부분 산출물 파일에 쓴다.

### [R3] Codex ∥ Claude 교차검증 (메인 → codex 호출)

1. **Claude Code가 `codex` CLI를 Bash로 자동 호출**해 같은 diff를 다른 엔진으로 재검토한다 (사람이 Codex를 따로 켜지 않는다). `gstack-codex` 스킬을 활용할 수 있다.
2. Codex 결과를 [R2] 발견과 **대조**한다: 양쪽이 함께 지적한 것은 신뢰도↑, 한쪽만 지적한 것은 [R4] 반박으로 넘긴다.
3. Codex 미설치/실패 시 이 단계를 건너뛰되 `review-report.md`에 "교차검증 생략(사유)"을 명시한다.

### [R4] 반박 (Sub-agent)

1. [R2]·[R3]의 발견을 "이거 진짜 문제 맞아?"로 **재검증**한다 — 근거가 약하거나 의도된 결정이면 가짜 경보로 제거한다.
2. 울트라코드 ON이면 반박을 별도 Sub-agent로 적대적으로 돌린다(기본 의심, 근거 충분할 때만 인정).
3. 살아남은 진짜 발견만 우선순위 분류: **[p1]** 필수(버그·기준 위반·의도 불일치·증거 불일치) / **[p2]** 강력 권장 / **[p3]** 권장 / **[p4]** 사소.

### [R5] 관문 판정 (메인)

1. `review-report.md`를 병합·확정한다. 울트라코드 Teams였으면 관점 충돌을 명시하고 팀을 해체한다 (`SendMessage({type:"shutdown_request"})` → `TeamDelete`).
2. **blocking([p1]) 있으면** → 멈추고 build로 복귀, 고친 뒤 [R1]부터 재실행한다.
3. **없으면** → 통과 ✅. 메인엔 [p1] 개수와 핵심 결론만 보고하고, 상세는 산출물 경로로 안내한다.

## 산출물: review-report.md

```markdown
# 리뷰 리포트

## Summary
(전체 품질 총평. 스택은 무엇이고, 완료기준 출처는 어디인지 1줄)

## 적용 기준 (스택 위임)
- 스택: BE | CM | FE | CHAT
- 완료기준 출처: 해당 플러그인 (BE/CM = 테스트·lint·build / FE = 시각·UX·반응형·접근성 + Claude 디자인 검증)
- 근거 문서: .harness/artifacts/{track}/{identifier}/code-quality-guide.md

## [R1] 자동검사
- 결과: PASS | FAIL (FAIL이면 여기서 멈춤)
- 로그: .harness/artifacts/{track}/{identifier}/review-auto-log.txt

## Evidence Verification
- 스택 증거 ↔ diff 대응: PASS | FAIL
- 증거 대상이 변경 파일에 실재 / 전환 방향 올바름: PASS | FAIL

## [R3] Codex 교차검증
- 실행: 했음 | 생략(사유)
- 양쪽 공통 지적: ...
- 한쪽만 지적(→반박 대상): ...

## Comments (반박 통과분만)

### [p1] {파일경로}:{라인}
- 근거: {code-quality-guide.md의 기준 / 스택 완료기준}
- 내용: ...
- 제안: ...
- side effect: (없으면 "없음")

### [p2] {파일경로}:{라인}
- 근거: ...
- 내용: ...
- 제안: ...

### [p3] / [p4]
- ...

## 관문 판정
- [ ] 통과 → 머지
- [ ] blocking 존재 → build로 복귀 후 [R1]부터 재실행
```
