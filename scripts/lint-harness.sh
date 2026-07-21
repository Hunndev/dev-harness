#!/usr/bin/env bash
# BUCCL harness 플러그인 린터
#
# 검증 규칙 (모두 통과해야 exit 0):
#   R1. 옛 "Agent Team을 호출" / "이 skill은 Agent Team으로 실행" 문구 잔재 없음
#   R2. 팀 스펙(team_name) 있는 파일엔 TeamDelete 언급 있음
#   R3. 도메인 간 스텝 대칭 — 개수 + 스텝 ID 집합 (planning·maintenance는 BE/CM/FE/CHAT 동일 / feature는 FE·CHAT ⊇ BE / AOS↔IOS는 전 트랙 완전 미러)
#   R4. 팀 스펙의 산출 파일이 "메인: 병합" 섹션에 모두 언급됨
#   R5. 아티팩트 경로 일관성 (BE/CM/FE/CHAT/SHARED/AOS/IOS 모두 .harness/artifacts 사용. .harness-artifacts 발견 시 실패)
#   R6. 참조 문서 경로 일관성 (BE/CM/FE/CHAT/SHARED/AOS/IOS/README 모두 .harness/docs/*.yaml 사용. 백틱 또는 단독으로 쓰인 docs/*.yaml 및 BE/docs/ 잔재 발견 시 실패)
#   R7. 플러그인(BE/CM/FE/CHAT/SHARED/AOS/IOS) Codex/Claude 등록 파일 존재·JSON 유효성·양쪽 marketplace 등록
#   R8. FE 전용 커맨드 drift 방지 (hb-cm 잔재, 디자인+API바인딩 산출물, watchAll=false 테스트 명령) + AOS/IOS 모바일 두 모드 산출물
#   R9. 플러그인 이름·버전 패리티 (claude plugin.json ↔ codex plugin.json ↔ marketplace.json)
#   R10. 문서 참조 경로 실재성 — 백틱 `commands/**.md`는 같은 플러그인 안에, `SHARED/commands/**.md`는 레포 루트에 실재해야 함
#   R11. 슬래시 명령 참조 실재성 — /hb-<plugin>:<track>:<cmd> 가 실제 <PLUGIN>/commands/<track>/<cmd>.md 에 대응해야 함
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

TARGET_DIRS=(BE/commands CM/commands FE/commands CHAT/commands SHARED/commands AOS/commands IOS/commands)

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

# ── R3: 도메인 간 스텝 헤더 대칭 ─────────────────────────────
# planning·maintenance: 4도메인(BE/CM/FE/CHAT) 완전 대칭(스택 무관 동일 골격).
# shared·feature: BE↔CM 엄격. feature의 FE(+F7 검증)·CHAT(+F3b 계약)은 의도적 추가 스텝이라 BE 이상이면 통과(누락만 차단).
# AOS↔IOS: 모바일 쌍둥이 — 전 트랙 완전 미러(개수+ID 집합+파일 존재 양방향).
echo
echo "R3. 도메인 간 스텝 헤더 개수 대칭 (planning·maintenance 4도메인 / feature FE·CHAT≥BE / AOS↔IOS 미러)"
r3_violations=0
count_steps() { grep -cE '^### \[[A-Z][0-9]' "$1" 2>/dev/null; }

# planning·maintenance: BE 기준 CM/FE/CHAT 완전 일치
for be_file in BE/commands/planning/*.md BE/commands/maintenance/*.md; do
  [ -f "$be_file" ] || continue
  be_count=$(count_steps "$be_file")
  for dom in CM FE CHAT; do
    dom_file="$dom/${be_file#BE/}"
    if [ ! -f "$dom_file" ]; then
      fail "$dom에 대응 파일 없음 (planning·maintenance는 4도메인 완전 대칭): $be_file"
      r3_violations=$((r3_violations + 1))
      continue
    fi
    dom_count=$(count_steps "$dom_file")
    if [ "$be_count" != "$dom_count" ]; then
      fail "스텝 수 불일치: $be_file ($be_count) vs $dom_file ($dom_count)"
      r3_violations=$((r3_violations + 1))
    fi
  done
done

# shared·feature: BE↔CM 엄격 비교
for be_file in BE/commands/shared/*.md BE/commands/feature/*.md; do
  [ -f "$be_file" ] || continue
  cm_file="CM/${be_file#BE/}"
  if [ ! -f "$cm_file" ]; then
    fail "CM에 대응 파일 없음 (BE↔CM 엄격 쌍): $be_file"
    r3_violations=$((r3_violations + 1))
    continue
  fi
  be_count=$(count_steps "$be_file")
  cm_count=$(count_steps "$cm_file")
  if [ "$be_count" != "$cm_count" ]; then
    fail "스텝 수 불일치: $be_file ($be_count) vs $cm_file ($cm_count)"
    r3_violations=$((r3_violations + 1))
  fi
done

# feature: FE·CHAT는 BE 이상(의도적 추가 스텝 허용, 누락 차단)
for be_file in BE/commands/feature/*.md; do
  [ -f "$be_file" ] || continue
  be_count=$(count_steps "$be_file")
  for dom in FE CHAT; do
    dom_file="$dom/${be_file#BE/}"
    if [ ! -f "$dom_file" ]; then
      fail "$dom에 대응 파일 없음 (feature는 FE·CHAT ⊇ BE): $be_file"
      r3_violations=$((r3_violations + 1))
      continue
    fi
    dom_count=$(count_steps "$dom_file")
    if [ "$dom_count" -lt "$be_count" ]; then
      fail "feature 스텝 누락 의심: $dom_file ($dom_count) < BE ($be_count)"
      r3_violations=$((r3_violations + 1))
    fi
  done
done
# R3b: 스텝 ID 집합 비교 — 개수 대칭이 못 잡는 치환·중복·번호 갈림 검출.
# (shared/*는 스텝 헤더가 없어 ID 집합이 공집합 — 비교는 참이지만 커버리지는 없음을 명시)
step_ids() { grep -oE '^### \[[A-Z][0-9][^]]*\]' "$1" 2>/dev/null | sort; }
for be_file in BE/commands/planning/*.md BE/commands/maintenance/*.md; do
  [ -f "$be_file" ] || continue
  be_ids=$(step_ids "$be_file")
  for dom in CM FE CHAT; do
    dom_file="$dom/${be_file#BE/}"
    [ -f "$dom_file" ] || continue
    dom_ids=$(step_ids "$dom_file")
    if [ "$be_ids" != "$dom_ids" ]; then
      fail "스텝 ID 불일치: $be_file vs $dom_file"
      diff <(echo "$be_ids") <(echo "$dom_ids") | sed 's/^/    /'
      r3_violations=$((r3_violations + 1))
    fi
  done
done
for be_file in BE/commands/feature/*.md; do
  [ -f "$be_file" ] || continue
  be_ids=$(step_ids "$be_file")
  [ -z "$be_ids" ] && continue
  cm_file="CM/${be_file#BE/}"
  if [ -f "$cm_file" ] && [ "$be_ids" != "$(step_ids "$cm_file")" ]; then
    fail "스텝 ID 불일치: $be_file vs $cm_file"
    r3_violations=$((r3_violations + 1))
  fi
  for dom in FE CHAT; do
    dom_file="$dom/${be_file#BE/}"
    [ -f "$dom_file" ] || continue
    missing=$(comm -23 <(echo "$be_ids") <(step_ids "$dom_file"))
    if [ -n "$missing" ]; then
      fail "feature 스텝 ID 누락: $dom_file — BE 대비 없음: $(echo $missing | tr '\n' ' ')"
      r3_violations=$((r3_violations + 1))
    fi
  done
done
# R3c: AOS↔IOS 완전 미러 — 모바일 쌍둥이는 전 트랙 엄격 쌍 (개수 + ID 집합 + 파일 존재 양방향)
for aos_file in AOS/commands/*/*.md; do
  [ -f "$aos_file" ] || continue
  ios_file="IOS/${aos_file#AOS/}"
  if [ ! -f "$ios_file" ]; then
    fail "IOS에 대응 파일 없음 (AOS↔IOS 완전 미러): $aos_file"
    r3_violations=$((r3_violations + 1))
    continue
  fi
  a_count=$(count_steps "$aos_file")
  i_count=$(count_steps "$ios_file")
  if [ "$a_count" != "$i_count" ]; then
    fail "스텝 수 불일치: $aos_file ($a_count) vs $ios_file ($i_count)"
    r3_violations=$((r3_violations + 1))
  fi
  if [ "$(step_ids "$aos_file")" != "$(step_ids "$ios_file")" ]; then
    fail "스텝 ID 불일치: $aos_file vs $ios_file"
    diff <(step_ids "$aos_file") <(step_ids "$ios_file") | sed 's/^/    /'
    r3_violations=$((r3_violations + 1))
  fi
done
for ios_file in IOS/commands/*/*.md; do
  [ -f "$ios_file" ] || continue
  aos_file="AOS/${ios_file#IOS/}"
  if [ ! -f "$aos_file" ]; then
    fail "AOS에 대응 파일 없음 (AOS↔IOS 완전 미러): $ios_file"
    r3_violations=$((r3_violations + 1))
  fi
done
[ $r3_violations -eq 0 ] && pass "도메인 간 스텝 대칭 OK (개수 + ID 집합 / planning·maintenance 4도메인 / feature FE·CHAT ⊇ BE / AOS↔IOS 미러)"

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
# R5는 문자열 '.harness-artifacts'가 고유하므로 literal grep.
# R6은 'docs/'가 다른 맥락(예: "docs 디렉토리")과 충돌할 수 있어 regex로 경계를 제한.
echo
echo "R5. 아티팩트 경로 일관성 (BE/CM/FE/CHAT/SHARED/AOS/IOS 모두 .harness/artifacts)"
r5_violations=0
wrong=$(grep -rn "\.harness-artifacts" BE/commands BE/CLAUDE.md BE/skills CM/commands CM/CLAUDE.md CM/skills FE/commands FE/CLAUDE.md FE/skills CHAT/commands CHAT/CLAUDE.md CHAT/skills SHARED/commands SHARED/CLAUDE.md SHARED/skills AOS/commands AOS/CLAUDE.md AOS/skills IOS/commands IOS/CLAUDE.md IOS/skills 2>/dev/null || true)
if [ -n "$wrong" ]; then
  fail "일곱 플러그인 모두 .harness/artifacts 사용해야 함. .harness-artifacts 발견:"
  echo "$wrong" | sed 's/^/    /'
  r5_violations=$((r5_violations + 1))
fi
[ $r5_violations -eq 0 ] && pass "아티팩트 경로 일관성 OK"

# ── R6: 참조 문서 경로 일관성 ─────────────────────────────────────
echo
echo "R6. 참조 문서 경로 일관성 (BE/CM/FE/CHAT/SHARED/AOS/IOS/README 모두 .harness/docs/*.yaml)"
r6_violations=0
R6_TARGETS=(BE/commands BE/CLAUDE.md BE/skills CM/commands CM/CLAUDE.md CM/skills FE/commands FE/CLAUDE.md FE/skills CHAT/commands CHAT/CLAUDE.md CHAT/skills SHARED/commands SHARED/CLAUDE.md SHARED/skills AOS/commands AOS/CLAUDE.md AOS/skills IOS/commands IOS/CLAUDE.md IOS/skills README.md)
# 백틱 내부의 `docs/<yaml>` 또는 공백/줄시작 뒤 단독으로 쓰인 docs/<yaml> 검색.
# .harness/docs/<yaml>은 `/`가 선행하므로 (^|[^./]) 조건에서 제외됨.
# 화이트리스트는 CHAT 1급 문서 6종 + 모바일 bridge-contract까지 포함한 전체 11종.
R6_YAMLS='code-convention|adr|architecture|module-registry|websocket-events|api-contract|database-schema|integration-boundary|operations|review-policy|bridge-contract'
docs_wrong=$(grep -rnE "(^|[^./])docs/(${R6_YAMLS})\.yaml" \
  "${R6_TARGETS[@]}" 2>/dev/null || true)
if [ -n "$docs_wrong" ]; then
  fail "다섯 플러그인+README 모두 .harness/docs/*.yaml 사용해야 함. 단독 docs/*.yaml 발견:"
  echo "$docs_wrong" | sed 's/^/    /'
  r6_violations=$((r6_violations + 1))
fi
# <플러그인>/docs/ 잔재 검출: 플러그인은 docs 템플릿을 싣지 않으므로 이 참조는 드리프트.
plug_docs_wrong=$(grep -rnE "(BE|CM|FE|CHAT|SHARED|AOS|IOS)/docs/(${R6_YAMLS})\.yaml" \
  "${R6_TARGETS[@]}" 2>/dev/null || true)
if [ -n "$plug_docs_wrong" ]; then
  fail "플러그인은 docs 템플릿을 싣지 않음. <플러그인>/docs/ 참조 발견:"
  echo "$plug_docs_wrong" | sed 's/^/    /'
  r6_violations=$((r6_violations + 1))
fi
[ $r6_violations -eq 0 ] && pass "참조 문서 경로 일관성 OK"

# 플러그인 디렉토리 → 플러그인 이름 매핑 (bash 3.2 호환: 연관배열 미사용)
plugin_name() {
  case "$1" in
    BE) echo "hb-be" ;;
    CM) echo "hb-cm" ;;
    FE) echo "hb-fe" ;;
    CHAT) echo "hb-chat" ;;
    SHARED) echo "hb-shared" ;;
    AOS) echo "hb-aos" ;;
    IOS) echo "hb-ios" ;;
    *)  echo "" ;;
  esac
}

# ── R7: 다섯 플러그인 구조/등록 검증 (BE/CM/FE/CHAT/SHARED × Claude/Codex) ──
echo
echo "R7. 플러그인 Codex/Claude 등록 구조 (BE/CM/FE/CHAT/SHARED/AOS/IOS)"
r7_violations=0
for p in BE CM FE CHAT SHARED AOS IOS; do
  name="$(plugin_name "$p")"
  for required in \
    "$p/.claude-plugin/plugin.json" \
    "$p/.codex-plugin/plugin.json" \
    "$p/skills/$name/SKILL.md"
  do
    if [ ! -f "$required" ]; then
      fail "필수 파일 없음: $required"
      r7_violations=$((r7_violations + 1))
    fi
  done
  for json_file in "$p/.claude-plugin/plugin.json" "$p/.codex-plugin/plugin.json"; do
    if [ -f "$json_file" ] && ! python3 -m json.tool "$json_file" >/dev/null 2>&1; then
      fail "JSON 파싱 실패: $json_file"
      r7_violations=$((r7_violations + 1))
    fi
  done
done

# 마켓플레이스 2종: JSON 유효성 + 다섯 플러그인 모두 등록되어 있는지
for mp in .claude-plugin/marketplace.json .agents/plugins/marketplace.json; do
  if [ ! -f "$mp" ]; then
    fail "필수 파일 없음: $mp"
    r7_violations=$((r7_violations + 1))
    continue
  fi
  if ! python3 -m json.tool "$mp" >/dev/null 2>&1; then
    fail "JSON 파싱 실패: $mp"
    r7_violations=$((r7_violations + 1))
    continue
  fi
  for name in hb-be hb-cm hb-fe hb-chat hb-shared hb-aos hb-ios; do
    if ! grep -q "\"name\"[[:space:]]*:[[:space:]]*\"$name\"" "$mp"; then
      fail "$mp 에 $name 엔트리 없음"
      r7_violations=$((r7_violations + 1))
    fi
  done
done

# Codex marketplace: 각 플러그인 source.path(./BE, ./CM, ./FE) 확인
if [ -f ".agents/plugins/marketplace.json" ]; then
  for p in BE CM FE CHAT SHARED AOS IOS; do
    if ! grep -q "\"path\"[[:space:]]*:[[:space:]]*\"./$p\"" .agents/plugins/marketplace.json; then
      fail ".agents/plugins/marketplace.json에 source.path \"./$p\" 없음"
      r7_violations=$((r7_violations + 1))
    fi
  done
fi

# name↔source 페어링: 이름과 경로가 뒤바뀌어도 잡히도록 항목 단위로 대조
pairing_errs=$(python3 - <<'PY'
import json
m = {'hb-be': './BE', 'hb-cm': './CM', 'hb-fe': './FE', 'hb-chat': './CHAT', 'hb-shared': './SHARED', 'hb-aos': './AOS', 'hb-ios': './IOS'}
errs = []
try:
    d = json.load(open('.claude-plugin/marketplace.json'))
    for pl in d.get('plugins', []):
        exp = m.get(pl.get('name'))
        if exp and pl.get('source') != exp:
            errs.append(f".claude-plugin/marketplace.json: {pl.get('name')} source={pl.get('source')} (기대 {exp})")
except Exception as e:
    errs.append(f".claude-plugin/marketplace.json 파싱 실패: {e}")
try:
    d = json.load(open('.agents/plugins/marketplace.json'))
    for pl in d.get('plugins', []):
        src = pl.get('source')
        path = src.get('path') if isinstance(src, dict) else src
        exp = m.get(pl.get('name'))
        if exp and path != exp:
            errs.append(f".agents/plugins/marketplace.json: {pl.get('name')} path={path} (기대 {exp})")
except Exception as e:
    errs.append(f".agents/plugins/marketplace.json 파싱 실패: {e}")
print('\n'.join(errs))
PY
)
if [ -n "$pairing_errs" ]; then
  fail "마켓플레이스 name↔source 페어링 불일치:"
  echo "$pairing_errs" | sed 's/^/    /'
  r7_violations=$((r7_violations + 1))
fi
[ $r7_violations -eq 0 ] && pass "플러그인 등록 구조 OK (BE/CM/FE/CHAT/SHARED/AOS/IOS × Claude/Codex + 페어링)"

# ── R8: FE 커맨드 drift 방지 ─────────────────────────────────────
echo
echo "R8. FE 커맨드 drift 방지"
r8_violations=0

fe_stale=$(grep -rnE '/hb-cm:|hb-cm|BUCCL CM|커뮤니티\(Node\.js\)|\.test\.ts\b' FE/commands FE/CLAUDE.md FE/skills/hb-fe/SKILL.md 2>/dev/null || true)
if [ -n "$fe_stale" ]; then
  fail "FE 문서에 CM/TS 잔재 발견:"
  echo "$fe_stale" | sed 's/^/    /'
  r8_violations=$((r8_violations + 1))
fi

for feature_doc in FE/commands/feature/auto.md FE/commands/feature/deep.md; do
  for artifact in design-source.md visual-check.md responsive-check.md accessibility-notes.md api-binding-check.md e2e-check.md; do
    artifact_re="${artifact//./\\.}"
    if ! grep -q "$artifact_re" "$feature_doc"; then
      fail "$feature_doc : FE 검증 산출물 누락 ($artifact — 디자인/API바인딩 두 모드 + E2E 렌즈)"
      r8_violations=$((r8_violations + 1))
    fi
  done
done

for maint_doc in FE/commands/maintenance/auto.md FE/commands/maintenance/deep.md; do
  if ! grep -q "e2e-check\.md" "$maint_doc"; then
    fail "$maint_doc : E2E 렌즈 산출물 누락 (e2e-check.md)"
    r8_violations=$((r8_violations + 1))
  fi
  if ! grep -Eq "E2E 렌즈가 걸린 이슈면.*commands/shared/verify\.md.*항목 5" "$maint_doc"; then
    fail "$maint_doc : E2E 렌즈 실행 배선 누락 (M6/M8 조건부 항목의 commands/shared/verify.md 항목 5 실행 참조)"
    r8_violations=$((r8_violations + 1))
  fi
done

bad_test_cmds=$(grep -rnE '(^|`|[[:space:]])npm test( |`|$)' FE/commands FE/skills/hb-fe/SKILL.md 2>/dev/null | grep -v -- '--watchAll=false' || true)
if [ -n "$bad_test_cmds" ]; then
  fail "FE npm test 명령에 --watchAll=false 누락:"
  echo "$bad_test_cmds" | sed 's/^/    /'
  r8_violations=$((r8_violations + 1))
fi

# R8b: AOS/IOS 모바일 두 모드 산출물 drift 방지 (shell 기능 / 브리지 계약)
for p in AOS IOS; do
  for feature_doc in $p/commands/feature/auto.md $p/commands/feature/deep.md; do
    [ -f "$feature_doc" ] || continue
    for artifact in device-check.md permission-check.md release-check.md bridge-check.md; do
      if ! grep -q "$artifact" "$feature_doc"; then
        fail "$feature_doc : 모바일 검증 산출물 누락 ($artifact — shell 기능/브리지 계약 두 모드)"
        r8_violations=$((r8_violations + 1))
      fi
    done
  done
done
[ $r8_violations -eq 0 ] && pass "FE·모바일 커맨드 drift 방지 OK"

# ── R9: 플러그인 이름·버전 패리티 ────────────────────────────────
echo
echo "R9. 이름·버전 패리티 (claude plugin.json ↔ codex plugin.json ↔ marketplace.json)"
r9_violations=0
for p in BE CM FE CHAT SHARED AOS IOS; do
  name="$(plugin_name "$p")"
  claude_json="$p/.claude-plugin/plugin.json"
  codex_json="$p/.codex-plugin/plugin.json"
  [ -f "$claude_json" ] && [ -f "$codex_json" ] || continue

  c_name=$(python3 -c "import json; print(json.load(open('$claude_json')).get('name',''))" 2>/dev/null)
  x_name=$(python3 -c "import json; print(json.load(open('$codex_json')).get('name',''))" 2>/dev/null)
  c_ver=$(python3 -c "import json; print(json.load(open('$claude_json')).get('version',''))" 2>/dev/null)
  x_ver=$(python3 -c "import json; print(json.load(open('$codex_json')).get('version',''))" 2>/dev/null)
  mp_ver=$(python3 -c "import json; d=json.load(open('.claude-plugin/marketplace.json')); print(next((pl.get('version','') for pl in d.get('plugins',[]) if pl.get('name')=='$name'), ''))" 2>/dev/null)

  if [ "$c_name" != "$name" ] || [ "$x_name" != "$name" ]; then
    fail "$p: name 불일치 (claude=$c_name, codex=$x_name, 기대=$name)"
    r9_violations=$((r9_violations + 1))
  fi
  if [ -z "$c_ver" ] || [ "$c_ver" != "$x_ver" ] || [ "$c_ver" != "$mp_ver" ]; then
    fail "$p: version 불일치 (claude=$c_ver, codex=$x_ver, marketplace=$mp_ver)"
    r9_violations=$((r9_violations + 1))
  fi
done
[ $r9_violations -eq 0 ] && pass "이름·버전 패리티 OK"

# ── R10: 문서 참조 경로 실재성 ────────────────────────────────────
# 문서(CLAUDE.md, SKILL.md, commands/**)가 백틱으로 가리키는 commands/**.md가 실재하는지 검사.
# `commands/...md`는 같은 플러그인 상대 경로, `SHARED/commands/...md`는 레포 루트 상대 경로로 판정.
# {placeholder}·<plugin> 포함 예시는 문자클래스([A-Za-z0-9_/-])에 걸리지 않아 자동 제외된다.
echo
echo "R10. 문서 참조 경로 실재성 (백틱 commands/**.md)"
r10_violations=0
for p in BE CM FE CHAT SHARED AOS IOS; do
  name="$(plugin_name "$p")"
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    while IFS= read -r ref; do
      [ -z "$ref" ] && continue
      if [ ! -f "$p/$ref" ]; then
        fail "$f : 참조 '$ref' 이 $p/ 안에 실재하지 않음"
        r10_violations=$((r10_violations + 1))
      fi
    done < <(grep -ohE '`commands/[A-Za-z0-9_/-]+\.md`' "$f" 2>/dev/null | tr -d '`' | sort -u)
    while IFS= read -r sref; do
      [ -z "$sref" ] && continue
      if [ ! -f "$sref" ]; then
        fail "$f : 참조 '$sref' 이 레포 루트에 실재하지 않음"
        r10_violations=$((r10_violations + 1))
      fi
    done < <(grep -ohE '`SHARED/commands/[A-Za-z0-9_/-]+\.md`' "$f" 2>/dev/null | tr -d '`' | sort -u)
  done < <({ find "$p/commands" -name '*.md' 2>/dev/null; echo "$p/CLAUDE.md"; echo "$p/skills/$name/SKILL.md"; })
done
[ $r10_violations -eq 0 ] && pass "문서 참조 경로 실재성 OK"

# ── R11: 슬래시 명령 참조 실재성 ──────────────────────────────────
# /hb-<plugin>:<track>:<cmd> → <PLUGIN>/commands/<track>/<cmd>.md 실재 검사.
# 2-segment(/hb-shared:seed)는 commands/<cmd>.md, 트랙 디렉토리 참조(/hb-chat:contract)는 디렉토리 존재로 통과.
echo
echo "R11. 슬래시 명령(/hb-*) 참조 실재성"
r11_violations=0
plugin_dir() {
  case "$1" in
    hb-be) echo BE ;; hb-cm) echo CM ;; hb-fe) echo FE ;;
    hb-chat) echo CHAT ;; hb-shared) echo SHARED ;;
    hb-aos) echo AOS ;; hb-ios) echo IOS ;; *) echo "" ;;
  esac
}
while IFS= read -r f; do
  [ -f "$f" ] || continue
  while IFS= read -r ref; do
    [ -z "$ref" ] && continue
    plug="${ref#/}"; plug="${plug%%:*}"
    rest="${ref#/"$plug":}"
    dir="$(plugin_dir "$plug")"
    [ -z "$dir" ] && continue
    if [ "${rest#*:}" = "$rest" ]; then
      target="$dir/commands/$rest.md"
      [ -f "$target" ] || [ -d "$dir/commands/$rest" ] || {
        fail "$f : 슬래시 참조 '$ref' → $target 실재하지 않음"
        r11_violations=$((r11_violations + 1)); }
    else
      track="${rest%%:*}"; cmd="${rest#*:}"
      target="$dir/commands/$track/$cmd.md"
      if [ ! -f "$target" ]; then
        fail "$f : 슬래시 참조 '$ref' → $target 실재하지 않음"
        r11_violations=$((r11_violations + 1))
      fi
    fi
  done < <(grep -ohE '/hb-(be|cm|fe|chat|shared|aos|ios)(:[a-z][a-z0-9-]*){1,2}' "$f" 2>/dev/null | sort -u)
done < <(find BE CM FE CHAT SHARED AOS IOS -name '*.md' 2>/dev/null; echo README.md)
[ $r11_violations -eq 0 ] && pass "슬래시 명령 참조 실재성 OK"

# ── 요약 ──────────────────────────────────────────────────────────
echo
if [ $FAIL -eq 0 ]; then
  echo "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo "${GREEN}  모든 규칙 통과 (R1~R11)${RESET}"
  echo "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
else
  echo "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo "${RED}  일부 규칙 실패 — 위 상세 확인${RESET}"
  echo "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
fi

exit $FAIL
