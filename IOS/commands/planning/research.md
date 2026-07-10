# 외부 사례/문서 조사 (iOS)

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
1. 유사 서비스/기능의 구현 사례 (iOS WebView 앱/하이브리드 shell/푸시 알림/딥링크)
2. iOS 생태계에서 관련 라이브러리, WebView 설정, JS 브리지, 쿠키/세션 동기화 패턴
3. 푸시·딥링크·권한 관련 패턴 (FCM 페이로드 설계, App Links/Universal Link·커스텀 스킴, 런타임 권한 UX)
4. 알려진 함정이나 안티패턴 (JS 인터페이스 과다 노출, message handler 미등록으로 브리지 호출 실패,
   백그라운드 실행 제한, ANR, WebView 버전 파편화, 스토어 심사 리젝 사유)
5. 웹(FE) 브리지 호출부와 메인 BE(Django) 인증 흐름과의 연동 사례 (앱 shell 관점)
6. BUCCL iOS 스택(Swift / Xcode / iOS WebView / FCM / App Store 배포)
   에서의 구현 가능성 특이사항 (형제 플랫폼(AOS)과의 패리티 포함)

각 항목에 대해:
- 출처(URL, 라이브러리명, 문서명)를 명시하라.
- BUCCL iOS에 적용 시 주의점을 덧붙여라.
- 보안 이슈가 있는 라이브러리는 반드시 명시하라.

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
- BUCCL iOS 적용 시 주의: ...

## 관련 iOS 라이브러리
| 이름 | 용도 | Swift 지원 | 최근 업데이트 | 보안 이슈 | 비고 |
|------|------|------------|-------------|---------|------|

## 푸시·딥링크·권한 패턴
- ...

## 알려진 함정/안티패턴
- ...

## 웹(FE)/BE 연동
| 시스템 | 용도 | 인증 | 비고 |
|--------|------|-----|------|

## BUCCL iOS 스택 특이사항
- ...
```
