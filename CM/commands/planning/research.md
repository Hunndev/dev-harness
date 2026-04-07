# 외부 사례/문서 조사 (CM)

유사 서비스, 기술 문서, 알려진 함정을 조사한다.

## 실행 방식

이 skill은 Sub-agent가 자동으로 실행한다. 사용자 확인 없이 진행된다.

## 입력

- `scope.md`
- `requirements-interview.md`
- `docs/architecture.yaml` (있으면)
- `docs/module-registry.yaml` (있으면)

## Sub-agent 프롬프트

```
다음 기획의 스코프와 요구사항을 바탕으로 외부 조사를 수행하라.

조사 항목:
1. 유사 서비스/기능의 구현 사례 (커뮤니티/스레드/실시간 메시징/알림 플랫폼)
2. Node.js / TypeScript / Express 생태계에서 관련 라이브러리, 미들웨어, 패턴
3. Socket.io 관련 패턴 (네임스페이스, room, broadcast, Redis adapter, sticky session)
4. 알려진 함정이나 안티패턴 (EventLoop blocking, memory leak, race condition,
   N+1 쿼리, callback hell, unhandled rejection)
5. 외부 API 연동 사례 및 메인 BE(Django) 와의 MSA 패턴
6. BUCCL CM 스택(Node 18+ / TS 5.3 / Express 4.18 / MySQL / Redis / Socket.io / Docker Swarm)
   에서의 구현 가능성 특이사항

각 항목에 대해:
- 출처(URL, npm 패키지명, 문서명)를 명시하라.
- BUCCL CM에 적용 시 주의점을 덧붙여라.
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
- BUCCL CM 적용 시 주의: ...

## 관련 npm 패키지
| 이름 | 용도 | TS 지원 | 최근 업데이트 | 보안 이슈 | 비고 |
|------|------|--------|-------------|---------|------|

## Socket.io / 실시간 패턴
- ...

## 알려진 함정/안티패턴
- ...

## 외부 API/MSA 연동
| 시스템 | 용도 | 인증 | 비고 |
|--------|------|-----|------|

## BUCCL CM 스택 특이사항
- ...
```
