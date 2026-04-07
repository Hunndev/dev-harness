# 이슈 재현

이슈를 재현하는 테스트 케이스를 작성하여 수정의 기준점을 확보한다.

## 실행 방식

이 skill은 Fork에서 실행된다.

## 절차

### bug 유형
1. 에러 로그/재현 절차를 분석한다.
2. 버그를 재현하는 테스트를 작성한다:
   - 파일: `tests/test_{module}_maint_{identifier}.py`
   - factory_boy로 테스트 데이터 생성
   - 현재 상태에서 **FAIL** 확인
3. 재현 불가 시 가능한 원인과 추가 필요 정보를 보고한다.

### refactor 유형
1. 리팩토링 대상 코드의 현재 동작을 캡처한다.
2. characterization test를 작성한다:
   - 현재 동작을 "정답"으로 간주하고, 그대로 캡처
   - 리팩토링 후에도 이 테스트가 PASS해야 함
3. 테스트 커버리지가 부족한 영역을 식별한다.

### performance 유형
1. 성능 기준선을 측정한다:
   - 응답 시간, 쿼리 수, 메모리 사용량
2. 기준선을 `reproduction.md`에 기록한다.

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

## 성능 기준선 (performance 유형)
| 항목 | 현재 값 | 목표 값 |
|------|--------|--------|

## 추가 필요 정보 (재현 불가 시)
- ...
```
