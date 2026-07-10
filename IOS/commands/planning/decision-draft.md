# ADR 드래프트

확정된 대안을 .harness/docs/adr.yaml 형식의 드래프트로 작성한다.

## 실행 방식

이 skill은 Fork에서 실행된다.

## 중요 규칙

**이 단계에서 adr.yaml에 자동 편입하지 않는다.**
decision-draft.md는 반드시 사용자 명시 승인 후 `/hb-ios:shared:update-docs adr`로 흘려보낸다.

## 절차

1. `feasibility.md`에서 확정된 대안을 확인한다.
2. `.harness/docs/adr.yaml`의 기존 항목을 읽고, 새 결정이 기존 결정과 충돌하지 않는지 확인한다.
3. 충돌이 있으면 사용자에게 명시적으로 제시한다:
   - 어떤 기존 ADR과 충돌하는지
   - 기존 ADR을 superseded로 변경할지, 새 결정을 수정할지
4. adr.yaml 형식에 맞춰 드래프트를 작성한다.
5. 사용자에게 드래프트를 제시하고, 편입 여부를 확인한다.

## context 작성 가이드라인

- context만 읽고도 "왜 이 결정이 필요했는가"를 구체적으로 연상할 수 있어야 한다.
- 나쁜 예: "푸시 알림 정리가 필요해서"
- 좋은 예: "푸시 알림 클릭 시 딥링크가 로그인 화면으로 떨어지는 문의가 반복됐다. 원인은 알림 페이로드의 목적지 URL을 WebView 로드 전에 소비해 쿠키 동기화가 끝나기 전 진입하는 것. 알림 → 딥링크 → 세션 복원 순서를 명문화하지 않으면 형제 플랫폼(AOS)과도 동작이 갈라진다."
- 당시 어떤 문제가 있었는지, 누가 고통받았는지, 어떤 대안을 검토했는지를 포함한다.

## 산출물: decision-draft.md

```markdown
# ADR 드래프트

## 편입 상태: 미승인

> 이 문서는 adr.yaml 후보입니다. 편입하려면 사용자 승인 후 `/hb-ios:shared:update-docs adr`을 실행하세요.

## adr.yaml 항목

```yaml
- id: ADR-{번호}
  title: {제목}
  status: adopted
  date: {YYYY-MM-DD}
  stacks: [...]
  context: |
    {구체적 상황 서술}
  decision: {결정 내용}
  consequence: {결과와 트레이드오프}
```

## 기존 ADR과의 관계
| 기존 ADR | 관계 | 조치 |
|---------|------|------|
| ADR-XXX | 호환 / 충돌 / 보완 | 변경 불필요 / superseded / ... |

## 연쇄 수정 필요 여부
- code-convention.yaml: {변경 필요 / 불필요}
- module-registry.yaml: {변경 필요 / 불필요}
- architecture.yaml: {변경 필요 / 불필요}
- bridge-contract.yaml: {변경 필요 / 불필요} — 변경 필요면 형제 플랫폼(AOS) 반영 필요 여부 명시
```
