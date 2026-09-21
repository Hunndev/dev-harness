"""dev PR-5 v6 수용 행 (SF-11a·SF-11b·SF-12). 모든 요청은 HEADER 뒤에 붙인다.

각 행은 (ID, 종류, 요청, 기대) 이다.
- RED: df18fc3에서 지금 실패하는 행.
- GUARD: df18fc3에서 이미 통과하며 유지해야 하는 행. 특히 인라인 HTML 3행은
  "느슨한 정규식으로 고치면 깨지는" 대조군이다.
- 기대: 파서 직접 결과(`pack._acceptance(HEADER + 요청)`)의 목록. 빈 목록이면 그 요청만으로
  공개 pack이 rc 2 `PACKET_SCHEMA_INVALID`, provider 0회여야 한다.
v4 정본 40행·v5 정본 27행은 그대로 유지한다. 여기에는 새 행만 있다.
"""

HEADER = '# Request\nType: bug\n\n'
ROW = '| AC-1 | real |\n'
T_HEAD = 'Intro prose\n    <!-- 예시 시작\n'
T_TAIL = '| AC-99 | 예시에만 있는 기준 |\n-->\n'
T_EXP = ['AC-99 | 예시에만 있는 기준']


def BND(tag):
    return 'Acceptance:\n    <!-- 예시\n' + tag + '\n' + ROW + '    -->\n'


ROWS = [
    # SF-11a: 문단 연속 주석의 짝 찾기 경계 목록에 HTML 블록 시작(CommonMark type 1·3·4·5·6)과
    # setext `-` 밑줄(1~2자)이 없다. 6688272는 실제 기준을 수집하는데 df18fc3는 삼킨다.
    ('SF11A-PRE', 'RED', BND('<pre>'), ['AC-1 | real']),
    ('SF11A-SCRIPT', 'RED', BND('<script type="x">'), ['AC-1 | real']),
    ('SF11A-STYLE', 'RED', BND('<style>'), ['AC-1 | real']),
    ('SF11A-TEXTAREA', 'RED', BND('<textarea>'), ['AC-1 | real']),
    ('SF11A-PRE-UPPER', 'RED', BND('<PRE>'), ['AC-1 | real']),
    ('SF11A-PI', 'RED', BND('<?php'), ['AC-1 | real']),
    ('SF11A-DECL', 'RED', BND('<!DOCTYPE html>'), ['AC-1 | real']),
    ('SF11A-CDATA', 'RED', BND('<![CDATA['), ['AC-1 | real']),
    ('SF11A-DIV', 'RED', BND('<div>'), ['AC-1 | real']),
    ('SF11A-DIV-ATTR', 'RED', BND('<div class="note">'), ['AC-1 | real']),
    ('SF11A-DIV-CLOSE', 'RED', BND('</div>'), ['AC-1 | real']),
    ('SF11A-DETAILS', 'RED', BND('<details>'), ['AC-1 | real']),
    ('SF11A-SUMMARY', 'RED', BND('<summary>정리</summary>'), ['AC-1 | real']),
    ('SF11A-TABLE-TAG', 'RED', BND('<table border="1">'), ['AC-1 | real']),
    ('SF11A-SECTION', 'RED', BND('<section>'), ['AC-1 | real']),
    ('SF11A-UL-TAG', 'RED', BND('<ul>'), ['AC-1 | real']),
    ('SF11A-BLOCKQUOTE-TAG', 'RED', BND('<blockquote>'), ['AC-1 | real']),
    ('SF11A-HR-TAG', 'RED', BND('<hr />'), ['AC-1 | real']),
    ('SF11A-SETEXT-DASH1', 'RED', BND('-'), ['AC-1 | real']),
    ('SF11A-SETEXT-DASH2', 'RED', BND('--'), ['AC-1 | real']),
    # 느슨한 `</?[A-Za-z]` 정규식으로 고치면 아래 3행이 깨진다. type 7과 인라인 HTML은
    # 문단을 끊지 못하므로 주석이 예시를 계속 숨겨야 한다.
    ('SF11A-IMG', 'GUARD', BND('<img src="a.png">'), []),
    ('SF11A-BR', 'GUARD', BND('<br>'), []),
    ('SF11A-SPAN', 'GUARD', BND('<span>x</span>'), []),
    ('SF11A-CUSTOM', 'GUARD', BND('<mytag>'), []),
    # 이미 경계인 것들은 유지한다.
    ('SF11A-ATX-G', 'GUARD', BND('# 제목'), ['AC-1 | real']),
    ('SF11A-EQ-G', 'GUARD', BND('='), ['AC-1 | real']),
    ('SF11A-HR3-G', 'GUARD', BND('---'), ['AC-1 | real']),
    ('SF11A-DASHSP-G', 'GUARD', BND('-   '), ['AC-1 | real']),

    # SF-11b: 표 본문 뒤의 4칸 `<!--`는 문단 연속이 아니라 들여쓴 코드다. 스캔을 시작하면
    # 뒤따르는 실제 기준 행을 삼킨다. 6688272는 모두 수집했다.
    ('SF11B-1', 'RED', '| AC-ID | 기준 |\n|---|---|\n| AC-9 | ex |\n    <!-- 설명\n| AC-1 | real |\n    -->\n',
     ['AC-9 | ex', 'AC-1 | real']),
    ('SF11B-2', 'RED', '| AC-ID | 기준 |\n|---|---|\n    <!-- 설명\n| AC-1 | real |\n| AC-2 | real |\n    -->\n',
     ['AC-1 | real', 'AC-2 | real']),
    ('SF11B-3', 'RED', '완료 기준:\n| AC-ID | 기준 |\n|---|---|\n| AC-9 | ex |\n    <!-- 이 행은 예시다\n'
     '| AC-1 | 로그인 성공 |\n| AC-2 | 실패 시 오류 |\n    -->\n',
     ['AC-9 | ex', 'AC-1 | 로그인 성공', 'AC-2 | 실패 시 오류']),
    ('SF11B-CTRL', 'GUARD', '| AC-ID | 기준 |\n|---|---|\n| AC-9 | ex |\n| AC-1 | real |\n',
     ['AC-9 | ex', 'AC-1 | real']),
    ('SF11B-ONELINE', 'GUARD', '| AC-ID | 기준 |\n|---|---|\n| AC-9 | ex |\n    <!-- 설명 -->\n| AC-1 | real |\n',
     ['AC-9 | ex', 'AC-1 | real']),
    # 산문 뒤 주석은 계속 예시를 숨긴다(v5 SF9-C2와 같은 요구).
    ('SF11B-PROSE-G', 'GUARD', 'Acceptance:\n    <!-- 예시\n| AC-9 | example |\n    -->\n- AC-1: real\n',
     ['- AC-1: real']),

    # SF-12: 표 경계 판정이 구분선 줄의 들여쓰기를 보지 않는다. 컨테이너 기준 4칸 이상 구분선은
    # GFM에서 표가 아니므로 주석이 예시를 계속 숨겨야 한다. 이 델타가 새로 만든 fail-open이다.
    ('SF12-ONLYEX-4SP', 'RED', 'Acceptance:\n    <!-- 예시\n| ID | 기준 |\n        | - | - |\n'
     '| AC-9 | ex |\n    -->\n', []),
    ('SF12-SEP4SP', 'RED', 'Acceptance:\n    <!-- 예시\n| ID | 기준 |\n        | - | - |\n'
     '| AC-9 | ex |\n    -->\n- AC-1: real\n', ['- AC-1: real']),
    ('SF12-SEPTAB', 'RED', 'Acceptance:\n    <!-- 예시\n| ID | 기준 |\n\t| - | - |\n'
     '| AC-9 | ex |\n    -->\n- AC-1: real\n', ['- AC-1: real']),
    ('SF12-LIST-SEP4SP', 'RED', '- AC-0: real\n      <!-- 예시\n  | ID | 기준 |\n          | - | - |\n'
     '  | AC-9 | ex |\n      -->\n', ['- AC-0: real']),
    # 구분선이 컨테이너 기준 0–3칸이면 GFM에서도 표다. 주석은 닫히지 못하고 예시가 드러난다.
    # 이는 SF-9가 의도한 동작이며 유지한다.
    ('SF12-SEP0-G', 'GUARD', 'Acceptance:\n    <!-- 예시\n| ID | 기준 |\n| - | - |\n'
     '| AC-9 | ex |\n    -->\n- AC-1: real\n', ['AC-9 | ex', '- AC-1: real']),
    ('SF12-SEP3SP-G', 'GUARD', 'Acceptance:\n    <!-- 예시\n| ID | 기준 |\n   | - | - |\n'
     '| AC-9 | ex |\n    -->\n- AC-1: real\n', ['AC-9 | ex', '- AC-1: real']),
    ('SF12-NOSEP-G', 'GUARD', 'Acceptance:\n    <!-- 예시\n| ID | 기준 |\n| AC-9 | ex |\n    -->\n', []),
    ('SF12-HDR4SP-G', 'GUARD', 'Acceptance:\n    <!-- 예시\n    | ID | 기준 |\n    | - | - |\n'
     '    | AC-9 | ex |\n    -->\n- AC-1: real\n', ['- AC-1: real']),

    # SF-12b: 같은 판정이 헤더 셀 수와 구분선 셀 수를 맞추지 않는다. GFM은 둘이 다르면 표로 보지 않는다.
    # 들여쓰기 정규화만으로는 닫히지 않는 별개 기전이다.
    ('SF12B-ESCPIPE-ONLY', 'RED', T_HEAD + '파이프 문자 \\| 설명\n--- | ---\n' + T_TAIL, []),
    ('SF12B-CELLCOUNT', 'RED', T_HEAD + '헤더 | 둘\n--- | --- | ---\n' + T_TAIL, []),
    ('SF12B-SEP0-G', 'GUARD', T_HEAD + '예시 표 | 설명\n--- | ---\n' + T_TAIL, T_EXP),
    ('SF12B-CODESPAN-G', 'GUARD', T_HEAD + '`a | b` 형식\n--- | ---\n' + T_TAIL, T_EXP),
    ('SF12B-HDR4SP-G', 'GUARD', T_HEAD + '    예시 표 | 설명\n--- | ---\n' + T_TAIL, []),
    ('SF12B-SEP4SP', 'RED', T_HEAD + '예시 표 | 설명\n    --- | ---\n' + T_TAIL, []),
    ('SF12B-SEP8SP', 'RED', T_HEAD + '예시 표 | 설명\n        --- | ---\n' + T_TAIL, []),
    ('SF12B-SEPTAB', 'RED', T_HEAD + '예시 표 | 설명\n\t--- | ---\n' + T_TAIL, []),
    ('SF12B-NESTED-DEEP', 'RED', '- 항목\n  본문 산문\n      <!-- 예시 시작\n  표 | 설명\n'
     '          --- | ---\n  | AC-98 | 예시에만 있는 기준 |\n  -->\n', []),
    ('SF12B-NESTED-OK-G', 'GUARD', '- 항목\n  본문 산문\n      <!-- 예시 시작\n  표 | 설명\n'
     '  --- | ---\n  | AC-98 | 예시에만 있는 기준 |\n  -->\n', ['AC-98 | 예시에만 있는 기준']),
]

# 결정 필요(DECISION): 채택된 SF-10 귀결에 없던 "통과 + 부분 누락" 방향.
# 기대값은 **현 동작(df18fc3)** 이다. 기본값 (b)를 고르면 이 행들을 그대로 CONSEQUENCE 테스트로 넣어
# 현 동작을 고정하고 README에 경고를 적는다. (a)를 고르면 기대값이 바뀌므로 그때 다시 정한다.
# 233cac7·943324e·c2db7de는 세 행 모두 ['- AC-21: 들여쓴 실제 기준', '- AC-22: 바깥 실제 기준']이었다.
DECISION_ROWS = [
    ('SF13-PARTIAL', 'DECISION', 'Intro prose\n    ```\n    예시 코드\n\n    ```\n'
     '    - AC-21: 들여쓴 실제 기준\n- AC-22: 바깥 실제 기준\n',
     ['- AC-22: 바깥 실제 기준']),
    ('SF13-PARTIAL-WS', 'DECISION', 'Intro prose\n    ```\n    예시 코드\n   \n    ```\n'
     '    - AC-21: 들여쓴 실제 기준\n- AC-22: 바깥 실제 기준\n',
     ['- AC-22: 바깥 실제 기준']),
    ('SF13-PARTIAL-TAB', 'DECISION', 'Intro prose\n    ```\n    예시 코드\n\t\n    ```\n'
     '    - AC-21: 들여쓴 실제 기준\n- AC-22: 바깥 실제 기준\n',
     ['- AC-22: 바깥 실제 기준']),
    # 대조군: 빈 줄이 없으면 df18fc3도 둘 다 수집한다(모든 커밋 동일).
    ('SF13-CTRL', 'GUARD', 'Intro prose\n    ```\n    예시 코드\n    ```\n'
     '    - AC-21: 들여쓴 실제 기준\n- AC-22: 바깥 실제 기준\n',
     ['- AC-21: 들여쓴 실제 기준', '- AC-22: 바깥 실제 기준']),
]


# User-adopted option (b): the three DECISION rows retain their df18fc3 result.
# They are consequences, not new RED evidence; the no-blank control is a guard.
import unittest
from test_request_parsing_sf910 import ParserAssertions
from hb_eval_review import pack


def table_probe(header, separator, prefix='Intro\n    <!-- note\n'):
    return prefix + header + '\n' + separator + '\n| AC-99 | hidden |\n    -->\n'


# Each separator neighbor varies the delimiter line, leaving the header valid.
# N23's two controls put the AC in a body row, not an empty-wording header.
TABLE_NEIGHBORS = [
    ('N23-header-four-spaces', table_probe('    Label | Criterion', '--- | ---'), []),
    ('N23-one-cell', table_probe('| Label |', '|---|'), []),
    ('delimiter-three-spaces', table_probe('Label | Criterion', '   --- | ---'), ['AC-99 | hidden']),
    ('delimiter-four-spaces', table_probe('Label | Criterion', '    --- | ---'), []),
    ('delimiter-tab', table_probe('Label | Criterion', '\t--- | ---'), []),
    ('delimiter-space-tab', table_probe('Label | Criterion', ' \t--- | ---'), []),
    ('delimiter-fullwidth-prefix', table_probe('Label | Criterion', '\u3000--- | ---'), []),
    ('delimiter-nbsp-prefix', table_probe('Label | Criterion', '\u00a0--- | ---'), []),
    ('delimiter-fullwidth-cell', table_probe('Label | Criterion', '| --- | \u3000--- |'), []),
    ('delimiter-crlf-three', table_probe('Label | Criterion', '   --- | ---').replace('\n', '\r\n'),
     ['AC-99 | hidden']),
    ('delimiter-crlf-four', table_probe('Label | Criterion', '    --- | ---').replace('\n', '\r\n'), []),
    ('delimiter-two-v-three', table_probe('Label | Criterion', '--- | --- | ---'), []),
    ('delimiter-three-v-two', table_probe('Label | Detail | Criterion', '--- | ---'), []),
    ('empty-middle-header-cell', table_probe('Label || Criterion', '--- | --- | ---'), ['AC-99 | hidden']),
    ('empty-middle-header-mismatch', table_probe('Label || Criterion', '--- | ---'), []),
    ('double-leading-border', table_probe('|| Label | Criterion |', '|---|---|---|'), ['AC-99 | hidden']),
    ('double-trailing-border', table_probe('| Label | Criterion ||', '|---|---|---|'), ['AC-99 | hidden']),
    ('empty-delimiter-cell', table_probe('Label | Criterion', '|---||---|'), []),
    ('escaped-border', table_probe('Label | Criterion\\|', '--- | ---'), ['AC-99 | hidden']),
    ('codespan-pipe-counts', table_probe('`a|b` | Criterion', '--- | --- | ---'), ['AC-99 | hidden']),
    ('codespan-escaped-pipe', table_probe('`a\\|b` | Criterion', '--- | ---'), ['AC-99 | hidden']),
    ('nested-delimiter-tab-relative-two', '- Group\n      <!-- note\n  Label | Criterion\n\t--- | ---\n'
     '  | AC-99 | hidden |\n      -->\n', ['AC-99 | hidden']),
    ('nested-delimiter-tab-relative-six', '- Group\n      <!-- note\n  Label | Criterion\n\t\t--- | ---\n'
     '  | AC-99 | hidden |\n      -->\n', []),
    ('nested-delimiter-dedented', '- Group\n      <!-- note\n  Label | Criterion\n--- | ---\n'
     '  | AC-99 | hidden |\n      -->\n', []),
]
# GFM's table scanner treats a pipe immediately preceded by a backslash as
# escaped even after two/four backslashes; generic inline escape parity differs.
TABLE_NEIGHBORS += [
    ('backslashes-%s-cells-%s' % (slashes, count),
     table_probe('Label' + '\\' * slashes + '|Detail | Criterion', ' | '.join(['---'] * count)),
     ['AC-99 | hidden'] if count == 2 else [])
    for slashes in (1, 2, 3, 4) for count in (2, 3)
]

# HTML condition 1 and 6 have different suffix sets: only type 6 accepts '/>'.
# Unicode whitespace is not the ASCII space/tab token boundary in either type.
# Pin CommonMark 0.31.2: type 6 contains search (not source), and declarations
# start with any ASCII letter. The canonical review's renderer used 0.30.
HTML_NEIGHBORS = [
    (label, BND(tag), ['AC-1 | real'] if interrupts else [])
    for label, tag, interrupts in (
        ('html-mixed-case', '<DiV>', True),
        ('html-uppercase-section', '<SECTION>', True),
        ('html-lowercase-script', '<script>', True),
        ('html-long-s-unicode-guard', '<ſection>', False),
        ('html-dotted-i-unicode-guard', '<scrİpt>', False),
        ('html-attributes', '<section data-note="x">', True),
        ('html-self-closing', '<div/>', True),
        ('html-space-self-closing', '<pre />', True),
        ('html-end-tag', '</TABLE>', True),
        ('html-type6-eol', '<search', True),
        ('html-type1-eol', '<script', True),
        ('html-type1-tab', '<style\tmedia="screen">', True),
        ('html-type1-immediate-slash', '<pre/>', False),
        ('html-type1-close', '</pre>', False),
        ('html-type1-suffix', '<prelude>', False),
        ('html-type6-suffix', '<dividend>', False),
        ('html-type6-invalid-slash', '<div/x>', False),
        ('html-type6-fullwidth', '<div\u3000class="x">', False),
        ('html-custom-end-tag', '</mytag>', False),
        ('html-inline-self-closing', '<img/>', False),
        ('html-type6-source-guard', '<source>', False),
        ('html-type4-lowercase', '<!doctype html>', True),
        ('html-type4-nonascii', '<!가', False),
        ('html-cdata-lowercase', '<![cdata[', False),
        ('html-three-spaces', '   <div>', True),
        ('html-four-spaces', '    <div>', False),
        ('setext-two-dashes-tab', '--\t', True),
        ('setext-four-spaces', '    --', False),
    )
]

_TABLE = '| Label | Criterion |\n|---|---|\n| data | value |\n'
_COMMENT = '    <!-- note\n| AC-99 | hidden |\n    -->\n'
CONTEXT_NEIGHBORS = [
    ('real-table-before-comment', _TABLE + _COMMENT, ['AC-99 | hidden']),
    ('pipe-prose-before-comment', '| Label | Criterion |\n| data | value |\n' + _COMMENT, []),
    ('table-blank-then-prose', _TABLE + '\nNew prose\n' + _COMMENT, []),
    ('table-nonpipe-prose', _TABLE + 'New prose\n' + _COMMENT, []),
    ('table-blank-before-comment', _TABLE + '\n' + _COMMENT, ['AC-99 | hidden']),
    ('table-heading-then-prose', _TABLE + '## Next\nNew prose\n' + _COMMENT, []),
    ('table-quote-containing-pipe', _TABLE + '> quoted | text\n' + _COMMENT, []),
    ('table-html-containing-pipe', _TABLE + '<div title="a|b">\n' + _COMMENT, []),
    ('quote-cannot-open-table', '> Label | Criterion\n|---|---|\n' + _COMMENT, []),
    ('html-cannot-open-table', '<div> Label | Criterion\n|---|---|\n' + _COMMENT, []),
    ('table-nested-context', '- Group\n' + ''.join('  ' + row + '\n' for row in _TABLE.splitlines()) +
     '      <!-- note\n  | AC-99 | hidden |\n      -->\n', ['AC-99 | hidden']),
    ('table-sibling-context', '- Group\n' + ''.join('  ' + row + '\n' for row in _TABLE.splitlines()) +
     '- New group\n      <!-- note\n  | AC-99 | hidden |\n      -->\n', []),
    ('table-deeper-context', '- Group\n' + ''.join('  ' + row + '\n' for row in _TABLE.splitlines()) +
     '  - Nested prose\n        <!-- note\n    | AC-99 | hidden |\n        -->\n', []),
    ('table-dedent-prose', '- Group\n' + ''.join('  ' + row + '\n' for row in _TABLE.splitlines()) +
     '\nOuter prose\n' + _COMMENT, []),
]


# Strict table starts above govern comment boundaries only. The established
# acceptance extractor also supports these loose separators outside comments;
# preserve both the body criteria and exclusion of AC-shaped table headers.
LEGACY_TABLE_GUARDS = [
    ('legacy-' + label + ('-ac-header' if ac_header else ''),
     ('| AC-90 | header |\n' if ac_header else '| ID | description |\n') +
     delimiter + '\nAC-91 | real\n', ['AC-91 | real'])
    for label, delimiter in (
        ('double-borders', '|| - | - ||'),
        ('fullwidth-prefix', '\u3000| - | - |'),
        ('fullwidth-suffix', '| - | - |\u3000'),
        ('fullwidth-cell', '| - |\u3000- |'),
    )
    for ac_header in (False, True)
] + [
    ('legacy-plain-indented-list-after-table', _TABLE + '    - AC-1: real\n', ['- AC-1: real']),
    ('legacy-plain-indented-row-after-table', _TABLE + '    | AC-1 | real |\n', ['AC-1 | real']),
]


def select(kind, prefix=''):
    return [(label, request, expected) for label, row_kind, request, expected in ROWS
            if row_kind == kind and label.startswith(prefix)]


class RequestParsingV6RedTests(ParserAssertions, unittest.TestCase):
    """All canonical RED 33 rows fail on df18fc3 in both entry paths."""
    def test_html_and_setext_direct(self):
        self.assert_direct_rows(select('RED', 'SF11A-'))

    def test_html_and_setext_public(self):
        self.assert_public_rows(select('RED', 'SF11A-'))

    def test_table_context_direct(self):
        self.assert_direct_rows(select('RED', 'SF11B-'))

    def test_table_context_public(self):
        self.assert_public_rows(select('RED', 'SF11B-'))

    def test_table_start_direct(self):
        self.assert_direct_rows(select('RED', 'SF12'))

    def test_table_start_public(self):
        self.assert_public_rows(select('RED', 'SF12'))


class RequestParsingV6GuardTests(ParserAssertions, unittest.TestCase):
    """Canonical GUARD 19 rows already pass on df18fc3."""
    def test_guards_direct(self):
        self.assert_direct_rows(select('GUARD'))

    def test_guards_public(self):
        self.assert_public_rows(select('GUARD'))


class RequestParsingV6ConsequenceTests(ParserAssertions, unittest.TestCase):
    def test_adopted_option_b_direct(self):
        self.assert_direct_rows([(label, request, expected) for label, _, request, expected in DECISION_ROWS])

    def test_adopted_option_b_public(self):
        self.assert_public_rows([(label, request, expected) for label, _, request, expected in DECISION_ROWS])


class RequestParsingV6NeighborTests(ParserAssertions, unittest.TestCase):
    def test_legacy_table_guards_direct(self):
        self.assert_direct_rows(LEGACY_TABLE_GUARDS)

    def test_legacy_table_guards_public(self):
        self.assert_public_rows(LEGACY_TABLE_GUARDS)

    def test_table_neighbors_direct(self):
        self.assert_direct_rows(TABLE_NEIGHBORS)

    def test_table_neighbors_public(self):
        self.assert_public_rows(TABLE_NEIGHBORS)

    def test_html_neighbors_direct(self):
        self.assert_direct_rows(HTML_NEIGHBORS)

    def test_html_neighbors_public(self):
        self.assert_public_rows(HTML_NEIGHBORS)

    def test_context_neighbors_direct(self):
        self.assert_direct_rows(CONTEXT_NEIGHBORS)

    def test_context_neighbors_public(self):
        self.assert_public_rows(CONTEXT_NEIGHBORS)

    def test_separator_near_misses_keep_failed_scans_linear(self):
        for count in (64, 128):
            with self.subTest(candidate_lines=count):
                inspections = []

                class CountedLine(str):
                    def expandtabs(self, tabsize=8):
                        inspections.append(1)
                        return super().expandtabs(tabsize)

                class CountedText(str):
                    def splitlines(self, keepends=False):
                        return [CountedLine(line) for line in super().splitlines(keepends)]

                request = CountedText(HEADER + 'Intro\n' +
                                      '    <!-- | unmatched\n' * count +
                                      '    | - | - |\n    - AC-1: literal\n')
                self.assertEqual(['- AC-1: literal'], pack._acceptance(request))
                self.assertLessEqual(len(inspections), 5 * count + 30)


if __name__ == '__main__':
    unittest.main()
