# 근본 원인 추적 — RCA (CM)

tracer 스타일로 코드를 추적하여 근본 원인을 추정한다.

## 실행 방식

이 skill은 Sub-agent가 실행한다. 단일 가설-검증 루프가 효과적이므로 병렬로 쪼개지 않는다.

## Sub-agent 프롬프트

```
다음 이슈의 근본 원인을 추적하라.

추적 방법:
1. stack trace가 있으면 발생 지점을 특정하라.
2. architecture.yaml의 request flow를 따라 문제 지점을 역추적하라.
   - HTTP: route → middleware → controller → service → repository → DB
   - WebSocket: connection → auth middleware → event handler → service → repository
3. 가설을 세우고 코드에서 검증하라. 가설이 틀리면 다음 가설로.
4. 근본 원인(root cause)을 추정하라. 복수이면 가능성 순 나열.
5. adr.yaml에서 관련 결정을 찾아라.

CM(Node/TS/Express) 특화 확인 항목:
- TypeScript 타입 안정성 위반 (any, type assertion)
- async/await 누락 → unhandled promise rejection
- try/catch 누락 → 미들웨어 에러 핸들링 누락
- Express 미들웨어 순서 (auth → validation → controller → error handler)
- EventLoop blocking (sync fs, 무거운 JSON.parse, 정규식 ReDoS)
- Connection pool 고갈 / leak
- Redis pub/sub 구독 해제 누락
- Socket.io 이벤트 핸들러 메모리 leak (listener 제거 안 함)
- ApiError 미사용 (일반 Error throw 시 status code 누락)
- response.ts 헬퍼 미사용 (응답 형식 불일치)

인프라 확인 항목:
- Docker Swarm 서비스 상태 / replica 상태
- Sticky session 설정 (Socket.io 다중 노드)
- Redis 연결 / adapter 동작
- MySQL 연결 / wait_timeout
- 메인 BE(hb-be) JWT 공유 키 동기화

[reproduction.md]
[관련 모듈 코드]
[adr.yaml]
[architecture.yaml]
```

## 산출물: root-cause.md

```markdown
# 근본 원인 분석

## 발생 지점
- 파일: {path}
- 라인: {line}
- 함수: {function_name}
- 레이어: route | middleware | controller | service | repository | websocket

## 근본 원인 추정

### 추정 1 (가능성: 높음)
- 원인: ...
- 근거: (코드의 어떤 부분이 이 추정을 뒷받침하는가)
- 관련 ADR: ADR-XXX (있으면)

### 추정 2 (가능성: 중간)
- 원인: ...
- 근거: ...

## 수정 방향 제안
1. ...
2. ...

## 확인 필요 사항
(사용자에게 추가 확인이 필요한 것)
```
