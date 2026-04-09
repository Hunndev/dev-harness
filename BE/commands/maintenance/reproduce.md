# 이슈 재현

이슈를 재현하는 테스트 케이스를 작성하여 수정의 기준점을 확보한다.

## 실행 방식

이 skill은 Fork에서 실행된다.

## 절차

> 이 skill은 TDD 사이클의 **Red 단계** 역할을 한다. 자세한 사이클 정의는 `commands/shared/tdd.md` 참조.

### bug 유형
1. 에러 로그/재현 절차를 분석한다.
2. 버그를 재현하는 테스트를 작성한다:
   - 파일: `tests/test_{module}_maint_{identifier}.py`
   - factory_boy로 테스트 데이터 생성
   - 현재 상태에서 **FAIL** 확인
3. FAIL 출력을 `.harness/artifacts/maintenance/{identifier}/tdd-baseline-log.txt`에 캡처한다. 실패 이유가 **'올바른 이유'(버그 때문)**인지 확인한다. syntax/import/fixture 오류이면 Red 재작성 (최대 3회, 자세한 규칙은 `commands/shared/tdd.md` 참조).
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
   - 응답 시간, 쿼리 수, 메모리 사용량
2. 기준선을 `reproduction.md`에 기록한다.
3. **TDD 관점**: 기준선과 목표치를 명확히 기록하여 Green 단계의 수용기준으로 사용한다.

## Django/DRF 특화 재현 체크리스트

- [ ] JWT 토큰 상태 (만료, 블랙리스트) 관련인가?
- [ ] DB 연결 상태 (CONN_MAX_AGE) 관련인가?
- [ ] Fernet 암호화/복호화 관련인가?
- [ ] Signal 실행 순서 관련인가?
- [ ] QuerySet lazy evaluation 타이밍 관련인가?
- [ ] Docker Swarm 환경 특이사항 관련인가?

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
- 파일: tests/test_{module}_maint_{identifier}.py
- 테스트명: test_{description}
- 결과: FAIL (expected) | 재현 불가
- 연관 아티팩트: tdd-baseline-log.txt (FAIL 출력 캡처)

## 성능 기준선 (performance 유형)
| 항목 | 현재 값 | 목표 값 |
|------|--------|--------|

## 추가 필요 정보 (재현 불가 시)
- ...
```
