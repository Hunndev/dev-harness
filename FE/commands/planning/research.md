# 외부 사례/문서 조사 (FE)

유사 서비스, 기술 문서, 알려진 함정을 조사한다.

## 실행 방식

이 skill은 Sub-agent가 자동으로 실행한다. 사용자 확인 없이 진행된다.

## 입력

- `scope.md`
- `requirements-interview.md`
- `.harness/docs/architecture.yaml` (있으면)
- `.harness/docs/module-registry.yaml` (있으면)

## Sub-agent 프롬프트

```
다음 기획의 스코프와 요구사항을 바탕으로 외부 조사를 수행하라.

조사 항목:
1. 유사 서비스/기능의 구현 사례 (프론트엔드/모바일 웹/알림/커뮤니티 UI)
2. React / CRA 생태계에서 관련 라이브러리, route guard, state, styling 패턴
3. 브라우저 이벤트 관련 패턴(visibility, resize, scroll, push notification, deep link)
4. 알려진 함정이나 안티패턴 (main thread blocking, memory leak, race condition,
   중복 API 호출, nested effect hell, unhandled promise rejection)
5. 외부 API 연동 사례 및 메인 BE(Django) API 소비 패턴(클라이언트 관점)
6. BUCCL FE 스택(React 18 / CRA / React Router / Zustand / MUI/Bootstrap / Capacitor / Docker Swarm)
   에서의 구현 가능성 특이사항

각 항목에 대해:
- 출처(URL, npm 패키지명, 문서명)를 명시하라.
- BUCCL FE에 적용 시 주의점을 덧붙여라.
- 보안 이슈가 있는 패키지는 반드시 명시하라.

[scope.md]
[requirements-interview.md]
```

## 산출물: external-research.md

```markdown
# 외부 조사 결과

## 유사 서비스 사례
### {서비스명}
- 개요: ...
- 참고 포인트: ...
- BUCCL FE 적용 시 주의: ...

## 관련 npm 패키지
| 이름 | 용도 | TS 지원 | 최근 업데이트 | 보안 이슈 | 비고 |
|------|------|--------|-------------|---------|------|

## 브라우저 이벤트 / 반응형 패턴
- ...

## 알려진 함정/안티패턴
- ...

## 외부 API/MSA 연동
| 시스템 | 용도 | 인증 | 비고 |
|--------|------|-----|------|

## BUCCL FE 스택 특이사항
- ...
```
