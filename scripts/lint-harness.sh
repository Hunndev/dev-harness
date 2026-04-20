#!/usr/bin/env bash
# BUCCL harness 플러그인 린터
#
# 검증 규칙 (모두 통과해야 exit 0):
#   R1. 옛 "Agent Team을 호출" / "이 skill은 Agent Team으로 실행" 문구 잔재 없음
#   R2. 팀 스펙(team_name) 있는 파일엔 TeamDelete 언급 있음
#   R3. BE/CM 대응 파일의 스텝 헤더(M1/P1/F1...) 개수 일치
#   R4. 팀 스펙의 산출 파일이 "메인: 병합" 섹션에 모두 언급됨
#   R5. 아티팩트 경로 일관성 (BE/CM 모두 .harness/artifacts 사용. .harness-artifacts 발견 시 실패)
#   R6. 참조 문서 경로 일관성 (BE/CM 모두 .harness/docs/*.yaml 사용. 백틱 또는 단독으로 쓰인 docs/*.yaml 발견 시 실패)
#
# 로컬 실행: bash scripts/lint-harness.sh
# CI: .github/workflows/lint-harness.yml에서 호출

set -u
cd "$(dirname "$0")/.."

FAIL=0
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
RESET=$'\033[0m'

pass() { echo "${GREEN}✅${RESET} $*"; }
fail() { echo "${RED}❌${RESET} $*"; FAIL=1; }
info() { echo "${YELLOW}▸${RESET} $*"; }

TARGET_DIRS=(BE/commands CM/commands)

# ── R1: 옛 문구 잔재 ───────────────────────────────────────────────
echo
echo "R1. 옛 'Agent Team을 호출' 문구 잔재 체크"
hits=$(grep -rn -E "Agent Team을 호출|이 skill은 Agent Team으로 실행" "${TARGET_DIRS[@]}" 2>/dev/null || true)
if [ -n "$hits" ]; then
  fail "옛 문구 발견:"
  echo "$hits" | sed 's/^/    /'
else
  pass "잔재 없음"
fi

# ── R2: 팀 스펙 파일은 TeamDelete 언급 필수 ───────────────────────
echo
echo "R2. 팀 스펙 있는 파일은 TeamDelete 언급 필수"
r2_violations=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  if ! grep -q "TeamDelete" "$f"; then
    fail "$f : team_name 있으나 TeamDelete 언급 없음"
    r2_violations=$((r2_violations + 1))
  fi
done < <(grep -rl "team_name" "${TARGET_DIRS[@]}" 2>/dev/null)
[ $r2_violations -eq 0 ] && pass "모든 팀 스펙 파일이 TeamDelete 포함"

# ── R3: BE/CM 대응 파일 스텝 수 일치 ─────────────────────────────
echo
echo "R3. BE/CM 대응 파일 스텝 헤더 개수 일치"
r3_violations=0
for be_file in BE/commands/planning/*.md BE/commands/maintenance/*.md BE/commands/feature/*.md BE/commands/shared/*.md; do
  [ -f "$be_file" ] || continue
  cm_file="CM/${be_file#BE/}"
  if [ ! -f "$cm_file" ]; then
    info "CM에 대응 파일 없음 (skip): $be_file"
    continue
  fi
  be_count=$(grep -cE '^### \[[A-Z][0-9]' "$be_file" 2>/dev/null)
  cm_count=$(grep -cE '^### \[[A-Z][0-9]' "$cm_file" 2>/dev/null)
  if [ "$be_count" != "$cm_count" ]; then
    fail "스텝 수 불일치: $be_file ($be_count) vs $cm_file ($cm_count)"
    r3_violations=$((r3_violations + 1))
  fi
done
[ $r3_violations -eq 0 ] && pass "BE/CM 스텝 수 대칭"

# ── R4: 팀 산출 파일이 병합 섹션에 언급 ──────────────────────────
echo
echo "R4. 팀 산출 파일이 '메인: 병합' 섹션에 모두 Read됨"
r4_violations=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  # 팀 스펙 테이블에서 산출 파일 추출
  # 패턴: | `이름` | ... | `.../XXX.md` |
  outputs=$(grep -oE '`\.harness[/-][a-z]+/[^`]+\.md`' "$f" 2>/dev/null | sed 's/`//g' | xargs -n1 basename 2>/dev/null | sort -u)
  [ -z "$outputs" ] && continue

  # "메인: 병합" 섹션 추출 (다음 ## 헤더 전까지)
  merge_section=$(awk '/^## 메인[:：] 병합/{flag=1; next} /^## /{flag=0} flag' "$f" 2>/dev/null)
  # M4/M8/P4 스타일 내장 병합도 포함 (deep.md)
  inline_merge=$(awk '/메인이.*부분 산출물|메인이.*결과를 병합/,/팀 해체|TeamDelete/' "$f" 2>/dev/null)
  combined="$merge_section"$'\n'"$inline_merge"

  # 최종 병합 파일은 자기 자신이므로 스킵할 필요 있음 (alternatives.md, impact-analysis.md 등)
  final_name=$(basename "$f")
  while IFS= read -r partial; do
    [ -z "$partial" ] && continue
    [ "$partial" = "$final_name" ] && continue
    if ! echo "$combined" | grep -qF "$partial"; then
      fail "$f : 팀 산출 파일 '$partial'이 병합 섹션에 Read 언급 없음"
      r4_violations=$((r4_violations + 1))
    fi
  done <<< "$outputs"
done < <(grep -rl "team_name" "${TARGET_DIRS[@]}" 2>/dev/null)
[ $r4_violations -eq 0 ] && pass "모든 팀 산출 파일이 병합 섹션에 언급됨"

# ── R5: 아티팩트 경로 일관성 ──────────────────────────────────────
echo
echo "R5. 아티팩트 경로 일관성 (BE/CM 모두 .harness/artifacts)"
r5_violations=0
wrong=$(grep -rn "\.harness-artifacts" BE/commands BE/CLAUDE.md CM/commands CM/CLAUDE.md 2>/dev/null || true)
if [ -n "$wrong" ]; then
  fail "BE/CM 모두 .harness/artifacts 사용해야 함. .harness-artifacts 발견:"
  echo "$wrong" | sed 's/^/    /'
  r5_violations=$((r5_violations + 1))
fi
[ $r5_violations -eq 0 ] && pass "아티팩트 경로 일관성 OK"

# ── R6: 참조 문서 경로 일관성 ─────────────────────────────────────
echo
echo "R6. 참조 문서 경로 일관성 (BE/CM 모두 .harness/docs/*.yaml)"
r6_violations=0
# 백틱 내부의 `docs/<yaml>` 또는 공백/줄시작 뒤 단독으로 쓰인 docs/<yaml> 검색.
# .harness/docs/<yaml>은 `/`가 선행하므로 (^|[^./]) 조건에서 제외됨.
docs_wrong=$(grep -rnE '(^|[^./])docs/(code-convention|adr|architecture|module-registry)\.yaml' \
  BE/commands BE/CLAUDE.md CM/commands CM/CLAUDE.md 2>/dev/null || true)
if [ -n "$docs_wrong" ]; then
  fail "BE/CM 모두 .harness/docs/*.yaml 사용해야 함. 단독 docs/*.yaml 발견:"
  echo "$docs_wrong" | sed 's/^/    /'
  r6_violations=$((r6_violations + 1))
fi
[ $r6_violations -eq 0 ] && pass "참조 문서 경로 일관성 OK"

# ── 요약 ──────────────────────────────────────────────────────────
echo
if [ $FAIL -eq 0 ]; then
  echo "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo "${GREEN}  모든 규칙 통과 (R1~R6)${RESET}"
  echo "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
else
  echo "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo "${RED}  일부 규칙 실패 — 위 상세 확인${RESET}"
  echo "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
fi

exit $FAIL
