# 외부 사례/문서 조사

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
1. 유사 서비스/기능의 구현 사례 (프리다이빙/수상스포츠/예약 플랫폼 중심)
2. Django/DRF 생태계에서 관련 라이브러리, 패키지, 패턴
3. 알려진 함정이나 안티패턴
4. 관련 API/외부 서비스 연동 사례
5. BucclApp 스택(Django/DRF + MariaDB + Docker Swarm + Azure)에서의 구현 가능성 특이사항

각 항목에 대해:
- 출처(URL, 문서명)를 명시하라.
- BucclApp에 적용 시 주의점을 덧붙여라.

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
- BucclApp 적용 시 주의: ...

## 관련 라이브러리/패키지
| 이름 | 용도 | Django 호환성 | 비고 |
|------|------|-------------|------|

## 알려진 함정/안티패턴
- ...

## 외부 API/서비스
| 서비스 | 용도 | 비용 | 비고 |
|--------|------|------|------|

## BucclApp 스택 특이사항
- ...
```
