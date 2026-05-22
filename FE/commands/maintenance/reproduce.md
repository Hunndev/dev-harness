# 이슈 재현 (FE)

이슈를 재현하는 테스트 케이스를 작성하여 수정의 기준점을 확보한다.

## 실행 방식

이 skill은 Fork에서 실행된다.

## 절차

> 이 skill은 TDD 사이클의 **Red 단계** 역할을 한다. 자세한 사이클 정의는 `commands/shared/tdd.md` 참조.

### bug 유형
1. 에러 로그/재현 절차/스크린샷/브라우저 이벤트 로그를 분석한다.
2. 버그를 재현하는 React Testing Library + Jest 테스트를 작성한다:
   - 파일: `src/__tests__/{module}.maint.{identifier}.test.jsx`
   - 외부 의존성은 target repo의 기존 mock 패턴을 우선 사용
   - API는 MSW, axios mock, jest mock 중 적합한 것 선택
   - 현재 상태에서 **FAIL** 확인
3. FAIL 출력을 `.harness/artifacts/maintenance/{identifier}/tdd-baseline-log.txt`에 캡처한다. 실패 이유가 **'올바른 이유'(버그 때문)**인지 확인한다. JS/TS 컴파일/import/mock 오류이면 Red 재작성 (최대 3회, 자세한 규칙은 `commands/shared/tdd.md` 참조).
4. 재현 불가 시 가능한 원인과 추가 필요 정보를 보고한다.

### refactor 유형
1. 리팩토링 대상 코드의 현재 동작을 캡처한다.
2. characterization test를 작성한다:
   - 현재 동작을 "정답"으로 간주하고, 그대로 캡처
   - 리팩토링 후에도 이 테스트가 PASS해야 함
3. 테스트 커버리지가 부족한 영역을 식별한다.
4. **TDD 관점**: characterization test는 '현재 동작'을 Green baseline으로 고정하는 역할. 리팩토링 후에도 이 테스트가 PASS해야 하며, 이는 Refactor 단계의 안전망이다.

### performance 유형
1. 성능 기준선을 측정한다:
   - render time, interaction latency, 메모리 사용량
   - React Profiler 또는 브라우저 Performance 관찰
   - API 호출 횟수와 중복 요청 여부
2. 기준선을 `reproduction.md`에 기록한다.
3. **TDD 관점**: 기준선과 목표치를 명확히 기록하여 Green 단계의 수용기준으로 사용한다.

## FE 특화 재현 체크리스트

- [ ] 로그인/JWT 만료/redirect 관련인가?
- [ ] route guard 또는 protected route 관련인가?
- [ ] hook dependency / 비동기 처리 관련인가?
- [ ] main thread blocking (큰 이미지, 과한 계산, 무거운 렌더링) 관련인가?
- [ ] Promise unhandled promise rejection 관련인가?
- [ ] API 중복 호출, abort 누락, unmounted setState 관련인가?
- [ ] Zustand/localStorage/sessionStorage stale 관련인가?
- [ ] CSS cascade, z-index, overflow, safe-area 관련인가?
- [ ] mobile viewport 또는 Capacitor shell 관련인가?
- [ ] 메인 BE(hb-be) 연동 / JWT 공유 관련인가?
- [ ] Docker Swarm 환경 (replica 간 상태 공유) 관련인가?

## 산출물: reproduction.md

```markdown
# 이슈 재현

## 이슈 요약
- 유형: bug | refactor | performance | dependency
- 증상: ...
- 관련 모듈: ...

## 재현 방법
(단계별 재현 절차)

## 재현 테스트
- 파일: src/__tests__/{module}.maint.{identifier}.test.jsx
- 테스트명: {describe} > {it}
- 결과: FAIL (expected) | 재현 불가
- 연관 아티팩트: tdd-baseline-log.txt (FAIL 출력 캡처)

## 성능 기준선 (performance 유형)
| 항목 | 현재 값 | 목표 값 |
|------|--------|--------|
| render time | ... | ... |
| interaction latency | ... | ... |
| API call count | ... | ... |
| 메모리 | ... | ... |
| render lag | ... | ... |

## 추가 필요 정보 (재현 불가 시)
- ...
```
