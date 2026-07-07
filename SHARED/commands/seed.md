# 주문서 작성 (seed)

기능·수정의 **목표·범위·제외·완료기준·검증법**을 한 장의 주문서로 굳힌다. scope + requirements + criteria를 하나로 흡수한 진입점이며, 이후 build·evaluate·review가 모두 이 주문서를 기준으로 돈다.

## 목적

- 작업을 시작하기 전에 "무엇을, 어디까지, 무엇을 안 하고, 어떻게 끝났다고 보는가"를 한 장으로 합의한다.
- 완료기준·증거·리뷰 렌즈는 **여기에 박지 않는다**. 기준은 각 플러그인(스택)을 따른다 — 이 주문서는 "스택 기준을 어디에 적용할지"만 가리킨다.
- 빈틈(모호한 범위·미정 요구사항)이 보이면 해당 도메인 플러그인의 planning interview(예: `/hb-be:planning:deep`의 인터뷰 스텝)로 되돌린다.

## 실행 방식

- **기본은 메인이 혼자, 얇게** 작성한다. 작은 일(hotfix급)은 3줄, 큰 일(deep급)은 한 장. 분량은 일의 크기에 맞춘다.
- **무거운 읽기·조사는 Sub-agent로 내린다.** 기존 코드 유사 구현 조사, `.harness/docs/*.yaml`(adr·code-convention·module-registry) 전문 스캔, 관련 아티팩트 수집은 Sub-agent에게 위임하고 메인은 **결론 몇 줄과 산출물 경로만** 회수한다. 파일 전문을 메인 컨텍스트에 올리지 않는다.
- **도구는 일이 쪼개지고 값어치 있을 때만 키운다.** 단순 작업은 메인 혼자로 충분하다. 조사 범위가 넓으면 Sub-agent 한둘로 분담한다.
- **울트라코드(워크플로우)가 켜지면** 더 정밀하게 — 조사 Sub-agent를 병렬로 굴리고, 완성된 주문서를 "범위가 새거나 완료기준이 비검증 가능하지 않은가"로 반박검증하는 패스를 한 번 더 돈다. **꺼져 있으면** 메인이 순서대로 가볍게 한 바퀴 돈다. 어느 쪽이든 산출물은 동일하다 — 항상 작동한다.
- 큰 기능 여러 개를 동시에 주문해야 하는 드문 경우에만 Claude Code 네이티브 Teams로 확장한다. 평소엔 불필요하다.

## 절차

### [S1] 입력 정리 (메인)

1. 식별자를 resolve한다: feature 트랙이면 `git branch --show-current`, maintenance 트랙이면 **트랙 파이프라인의 issue-id**(예: `BUCCL-BE-42`, `maint-20260408-slug`), planning 트랙이면 사용자가 지정한 슬러그. 산출물 디렉토리(`.harness/artifacts/{track}/{identifier}/`)와 **반드시 같은 식별자**를 쓴다 — 다르면 트랙 스텝이 seed를 찾지 못한다.
2. 트랙과 작업 크기(hotfix / auto / deep)를 사용자와 확인한다. 크기가 주문서 분량을 결정한다.
3. 선행 산출물이 있으면 경로만 끌어온다: `.harness/artifacts/planning/{identifier}/` 의 interview·feasibility 산출물, 관련 ADR(`.harness/docs/adr.yaml` 편입 항목).
4. 빈틈(범위 모호·요구사항 미정)이 크면 여기서 멈추고 interview로 되돌린다.

### [S2] 맥락 조사 (Sub-agent)

1. **Sub-agent를 호출**하여 무거운 읽기를 위임한다 (메인 컨텍스트 보호). 조사 범위가 좁으면 이 스텝을 생략하고 메인이 직접 처리한다.
2. Sub-agent 입력: 작업 한 줄 요약 + `.harness/docs/module-registry.yaml`, `.harness/docs/adr.yaml`, `.harness/docs/code-convention.yaml`, 관련 기존 코드.
3. Sub-agent 조사 항목:
   - 기존 코드에 재사용·확장 가능한 유사 구현이 있는가, 충돌 가능성은 어디인가.
   - 이 작업에 걸리는 ADR·convention 항목은 무엇인가 (stacks 필터 1차 + 내용 2차).
4. Sub-agent는 결론과 근거 경로만 반환한다. 메인은 요약만 주문서에 옮긴다.
5. 울트라코드 ON이면 조사 Sub-agent를 관점별(재사용 / 충돌 / 규칙)로 병렬 분담한다.

### [S3] 주문서 작성 (메인)

1. 목표·범위·제외를 한 문장씩 박는다. **제외(안 하는 것)를 반드시 명시**한다 — 범위 폭주의 1차 방어선이다.
2. 요구사항을 MUST / SHOULD / NICE로 분류한다.
3. **완료기준은 스택에 위임한다.** 구체적 통과 명령을 주문서에 하드코딩하지 말고, "검증은 이 작업의 플러그인(스택) 기준을 따른다"고 적은 뒤 어떤 렌즈를 적용할지만 가리킨다:
   - BE/CM = 해당 스택의 테스트·lint·build 통과 (구체 명령은 각 플러그인 `shared/verify`·`shared/tdd` 참조).
   - FE = 시각·UX·반응형·접근성 + Claude 디자인 검증 (시각 회귀를 텍스트 통과로 환원하지 않는다).
   - CHAT = 테스트·lint·build + 계약 검증(websocket-events·api-contract 등록) + dual review gate.
   - 어느 스택이든 "무엇을 증거로 볼지"는 그 플러그인이 정의한다. 이 주문서는 그 증거를 가리키기만 한다.
4. 검증 가능성을 점검한다: 각 완료기준이 build·evaluate 단계에서 객관적으로 확인 가능한가. 불가능하면 기준을 다시 쓴다.
5. 울트라코드 ON이면 완성 초안을 반박검증한다 — "범위가 제외와 모순되지 않는가 / 완료기준이 비검증 가능하지 않은가". blocking 지적이 있으면 [S1]로 되돌린다.

### [S4] 확정 (메인)

1. 초안과 **모호한 논의점**을 사용자에게 제시한다.
2. 피드백을 반영하여 `seed.md`를 확정·저장한다.
3. 메인에는 산출물 경로(`.harness/artifacts/{track}/{identifier}/seed.md`)만 남기고 다음 단계(build — 해당 스택의 트랙 명령, 예: `/hb-be:feature:auto`)로 넘긴다. 트랙 파이프라인의 요구사항 스텝은 이 seed.md를 읽고 같은 질문을 반복하지 않는다.

## 산출물: seed.md

```markdown
# 주문서: {작업 제목}

## 한 줄 목표
(이 작업이 끝나면 무엇이 가능해지는가)

## 트랙 / 식별자 / 크기
- 트랙: {feature | maintenance | planning}
- 식별자: {branch명 또는 슬러그}
- 크기: {hotfix | auto | deep}

## 범위
- 포함: ...

## 제외 (안 하는 것)
- ...

## 요구사항
### MUST
- REQ-M01: ...
### SHOULD
- REQ-S01: ...
### NICE
- REQ-N01: ...

## 기반 문서 (경로만)
- 선행 산출물: {`.harness/artifacts/planning/{identifier}/...` 또는 "없음"}
- 관련 ADR: {ADR-XXX (`.harness/docs/adr.yaml`) 또는 "없음"}

## 맥락 (Sub-agent 회수 요약)
- 재사용·확장 가능: ...
- 충돌 가능성: ...
- 걸리는 ADR/convention: ...

## 완료기준 (기준은 스택을 따른다)
> 구체 통과 명령은 각 플러그인(스택)이 정의한다. 아래는 적용할 렌즈만 가리킨다.

| 완료기준 | 적용 렌즈 (스택) | 어디서 검증 |
|----------|------------------|-------------|
| AC-01: ... | BE/CM=테스트·lint·build / FE=시각·UX·반응형·접근성+Claude 디자인 검증 / CHAT=+계약·dual gate | build / evaluate |

## 미결 사항
- ...
```
