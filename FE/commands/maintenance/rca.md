# 근본 원인 추적 — RCA (FE)

tracer 스타일로 코드를 추적하여 근본 원인을 추정한다.

## 실행 방식

이 skill은 Sub-agent가 실행한다. 단일 가설-검증 루프가 효과적이므로 병렬로 쪼개지 않는다.

## Sub-agent 프롬프트

```
다음 이슈의 근본 원인을 추적하라.

추적 방법:
1. stack trace가 있으면 발생 지점을 특정하라.
2. architecture.yaml의 request flow를 따라 문제 지점을 역추적하라.
   - 화면: route → page → component → hook/store → API client → backend API
   - 이벤트: browser event → handler → state update → render → side effect
3. 가설을 세우고 코드에서 검증하라. 가설이 틀리면 다음 가설로.
4. 근본 원인(root cause)을 추정하라. 복수이면 가능성 순 나열.
5. adr.yaml에서 관련 결정을 찾아라.

FE(React/CRA) 특화 확인 항목:
- async/await 누락 → unhandled promise rejection
- try/catch 누락 → API 실패 상태 처리 누락
- auth guard / protected route / redirect 순서
- main thread blocking (무거운 JSON.parse, 큰 이미지, 과한 re-render)
- axios cancellation 누락 또는 중복 요청
- Zustand/localStorage 상태 stale
- 브라우저 이벤트 listener cleanup 누락
- loading/empty/error/success 상태 누락
- style cascade, z-index, overflow, fixed/sticky position 영향
- mobile viewport / Capacitor shell safe-area 영향

인프라 확인 항목:
- Docker Swarm FE 서비스 상태 / nginx 설정
- API base URL / CORS / proxy 설정
- CDN/cache/header 동작
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
- 레이어: route | page | component | hook | store | API client | style | browser-event

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
