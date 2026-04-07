# 검증 (QA)

구현/수정 완료 후 코드 품질과 동작을 검증한다.
maintenance(M8), feature(F8) 트랙에서 사용한다.

## 실행 방식

이 skill은 Fork에서 실행된다.

## 검증 항목

### 1. 시스템 체크
```bash
python manage.py check
```

### 2. 마이그레이션 확인
```bash
python manage.py makemigrations --check --dry-run
```
누락된 마이그레이션이 있으면 생성한다. 파일명은 의미 있는 이름으로 (DJ-005).

### 3. 테스트 실행
```bash
python manage.py test {app} --verbosity=2    # 대상 앱
python manage.py test --verbosity=2           # 전체 (회귀 확인)
```

### 4. Convention 체크
변경된 파일에 대해 `.harness/docs/code-convention.yaml` 위반 여부를 확인:
- print() 사용 (GEN-004)
- bare except (GEN-005)
- 50줄 초과 함수 (GEN-001)
- View에 비즈니스 로직 (DJ-001)
- permission_classes 누락 (DRF-004)
- pagination_class 누락 (DRF-006)

### 5. 결과 판정
- 전체 PASS → 통과
- 실패 → 수정 루프 (최대 3회)
- 3회 초과 → 사용자에게 보고하고 판단 요청

## 보고 형식

```markdown
## 검증 결과

### 시스템 체크: PASS | FAIL
### 마이그레이션: PASS | FAIL (누락: ...)
### 테스트
- 대상 앱: {N} 통과 / {M} 실패
- 전체: {N} 통과 / {M} 실패
### Convention 위반: {N}건
### 최종: PASS | FAIL
```
