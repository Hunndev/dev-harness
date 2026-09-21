"""Exact v7 acceptance rows for the post-table indented-comment boundary.

RED 9 rows fail on 203d5ca in both entry paths; GUARD 14 and the two
user-adopted option-(b) unclosed-comment consequences already pass.
"""
import unittest

from test_request_parsing_sf910 import ParserAssertions

# Preserve all 25 canonical IDs, requests, and expected values exactly.
HEADER = '# Request\nType: bug\n\n'

# 실제 헤더·구분선으로 열린 표 + 본문 한 행
TBL = '| AC-ID | 기준 |\n| - | - |\n'
EX = '| AC-9 | 예시 |\n'

ROWS = [
    # ---- RED: 표 뒤 들여쓴 주석 다음의 실제 기준이 사라진다 ----------------------
    # 공개 경로에서 rc 0 -> rc 2 PACKET_SCHEMA_INVALID 로 뒤집히는 두 행.
    ('V7K-BLOCK-ONLY', 'RED',
     TBL + '    <!-- 설명 -->\n    - AC-1: 진짜 기준\n',
     ['- AC-1: 진짜 기준']),
    ('V7K-BLOCK-NESTED', 'RED',
     '- Group\n  | Label | Criterion |\n  |---|---|\n  | data | value |\n'
     '      <!-- note -->\n      - AC-1: 진짜 기준\n',
     ['- AC-1: 진짜 기준']),

    # rc 는 0으로 남고 실제 기준만 조용히 빠지는 행.
    ('V7K-ROW', 'RED',
     TBL + '| AC-1 | real |\n    <!-- 설명 -->\n    - AC-2: 진짜 기준\n',
     ['AC-1 | real', '- AC-2: 진짜 기준']),
    ('V7K-EXAMPLE-ROW', 'RED',
     TBL + EX + '    <!-- 설명 -->\n    - AC-1: 진짜 기준\n',
     ['AC-9 | 예시', '- AC-1: 진짜 기준']),
    ('V7K-TABLE-ROW', 'RED',
     TBL + EX + '    <!-- 설명 -->\n    | AC-1 | 진짜 |\n',
     ['AC-9 | 예시', 'AC-1 | 진짜']),
    ('V7K-TAB', 'RED',
     TBL + EX + '\t<!-- 설명 -->\n\t- AC-1: 진짜 기준\n',
     ['AC-9 | 예시', '- AC-1: 진짜 기준']),
    ('V7K-MULTI', 'RED',
     TBL + '| AC-1 | real |\n    <!-- 설명 -->\n'
     '    - AC-2: 진짜 기준\n    - AC-3: 또 진짜\n- AC-4: 바깥\n',
     ['AC-1 | real', '- AC-2: 진짜 기준', '- AC-3: 또 진짜', '- AC-4: 바깥']),
    ('V7K-DEEPER', 'RED',
     TBL + EX + '    <!-- 설명 -->\n        - AC-1: 진짜 기준\n',
     ['AC-9 | 예시', '- AC-1: 진짜 기준']),
    ('V7K-MULTILINE', 'RED',
     TBL + EX + '    <!-- 설명\n    이어지는 설명\n    -->\n    - AC-1: 진짜 기준\n',
     ['AC-9 | 예시', '- AC-1: 진짜 기준']),

    # ---- GUARD: 주석이 없는 형제. 203d5ca도 통과한다. 수정이 이 쪽을 건드리면 안 된다 ----
    ('V7G-NOCOMMENT', 'GUARD', TBL + '    - AC-1: 진짜 기준\n', ['- AC-1: 진짜 기준']),
    ('V7G-NOCOMMENT-NESTED', 'GUARD',
     '- Group\n  | Label | Criterion |\n  |---|---|\n  | data | value |\n'
     '      - AC-1: 진짜 기준\n',
     ['- AC-1: 진짜 기준']),
    ('V7G-NOCOMMENT-DEEPER', 'GUARD', TBL + EX + '        - AC-1: 진짜 기준\n',
     ['AC-9 | 예시', '- AC-1: 진짜 기준']),
    ('V7G-ONELINE-AT-ZERO', 'GUARD',
     TBL + EX + '    <!-- 설명 -->\n| AC-1 | real |\n', ['AC-9 | 예시', 'AC-1 | real']),
    ('V7G-BLANK-RESETS', 'GUARD',
     TBL + EX + '    <!-- 설명 -->\n\n- AC-1: 진짜 기준\n',
     ['AC-9 | 예시', '- AC-1: 진짜 기준']),

    # ---- GUARD: 순진한 수정(주석 줄만 지우기)을 막는 음성 대조군 --------------------
    # 주석이 자기 `-->` 안에서 닫히면 그 사이의 예시는 계속 숨어 있어야 한다.
    ('V7G-EXAMPLE-ROW-HIDDEN', 'GUARD',
     '| Label | Criterion |\n|---|---|\n| data | value |\n'
     '    <!-- note\n    | AC-99 | hidden |\n    -->\n', []),
    ('V7G-EXAMPLE-LIST-HIDDEN', 'GUARD',
     '| Label | Criterion |\n|---|---|\n| data | value |\n'
     '    <!-- note\n    - AC-99: hidden\n    -->\n', []),

    # ---- GUARD: SF-11b 가 닫은 구멍이 다시 열리면 안 된다 ------------------------
    ('V7G-SF11B-1', 'GUARD',
     '| AC-ID | 기준 |\n|---|---|\n| AC-9 | ex |\n    <!-- 설명\n| AC-1 | real |\n    -->\n',
     ['AC-9 | ex', 'AC-1 | real']),
    ('V7G-SF11B-2', 'GUARD',
     '| AC-ID | 기준 |\n|---|---|\n    <!-- 설명\n| AC-1 | real |\n| AC-2 | real |\n    -->\n',
     ['AC-1 | real', 'AC-2 | real']),
    ('V7G-SF11B-3', 'GUARD',
     '완료 기준:\n| AC-ID | 기준 |\n|---|---|\n| AC-9 | ex |\n'
     '    <!-- 이 행은 예시다\n| AC-1 | real |\n    -->\n',
     ['AC-9 | ex', 'AC-1 | real']),
    ('V7G-REAL-TABLE-BEFORE-COMMENT', 'GUARD',
     '| Label | Criterion |\n|---|---|\n| data | value |\n'
     '    <!-- note\n| AC-99 | hidden |\n    -->\n', ['AC-99 | hidden']),

    # ---- GUARD: 일상 입력 ---------------------------------------------------
    ('V7G-PLAIN-LIST', 'GUARD', '- AC-1: 진짜 기준\n- AC-2: 또 진짜\n',
     ['- AC-1: 진짜 기준', '- AC-2: 또 진짜']),
    ('V7G-PLAIN-TABLE', 'GUARD', '| AC-ID | 기준 |\n| --- | --- |\n| AC-1 | 진짜 |\n',
     ['AC-1 | 진짜']),
    ('V7G-PROSE-INDENTED', 'GUARD', '설명 문단\n    - AC-1: 진짜 기준\n', ['- AC-1: 진짜 기준']),
]

# 결정이 필요한 귀결. 기대값은 **203d5ca의 현재 동작**으로 고정했다(권고 기본값).
# 두 행 모두 df18fc3에서는 `- AC-1/- AC-2` 가 더 있었고, 첫 행은 공개 경로에서
# rc 0 -> rc 2 로 뒤집힌다. 닫히지 않은 `<!--` 라서 렌더러도 전체를 코드로 본다.
# (a) 로 바꾸려면 두 기대값을 df18fc3 값으로 되돌려라.
CONSEQUENCE_ROWS = [
    ('V7C-UNCLOSED-ONLY', 'CONSEQUENCE',
     TBL + '    <!-- 설명\n    - AC-1: 진짜 기준\n', []),               # df18fc3: ['- AC-1: 진짜 기준']
    ('V7C-UNCLOSED-ROW', 'CONSEQUENCE',
     TBL + '| AC-1 | real |\n    <!-- 설명\n    - AC-2: 진짜 기준\n',
     ['AC-1 | real']),                                                  # df18fc3: 위 + '- AC-2: 진짜 기준'
]



def select(kind):
    return [(label, request, expected) for label, row_kind, request, expected
            in ROWS + CONSEQUENCE_ROWS if row_kind == kind]


class RequestParsingV7RedTests(ParserAssertions, unittest.TestCase):
    def test_closed_post_table_comments_direct(self):
        self.assert_direct_rows(select('RED'))

    def test_closed_post_table_comments_public(self):
        self.assert_public_rows(select('RED'))


class RequestParsingV7GuardTests(ParserAssertions, unittest.TestCase):
    def test_existing_guards_direct(self):
        self.assert_direct_rows(select('GUARD'))

    def test_existing_guards_public(self):
        self.assert_public_rows(select('GUARD'))


class RequestParsingV7ConsequenceTests(ParserAssertions, unittest.TestCase):
    def test_adopted_unclosed_option_b_direct(self):
        self.assert_direct_rows(select('CONSEQUENCE'))

    def test_adopted_unclosed_option_b_public(self):
        self.assert_public_rows(select('CONSEQUENCE'))

_TABLE = '| Label | Criterion |\n|---|---|\n| data | value |\n'
_NESTED_TABLE = '- Group\n' + ''.join('  ' + line + '\n' for line in _TABLE.splitlines())

# Pin both sides of the closing/dedent boundary, including subsequent code
# regions, so comment state cannot accidentally close an unrelated fence.
BOUNDARY_NEIGHBORS = [
    ('closed-comment-hides-list-and-row', _TABLE +
     '    <!-- note\n    - AC-98: hidden\n    | AC-99 | hidden |\n'
     '    -->\n    - AC-1: real\n', ['- AC-1: real']),
    ('closer-deeper-than-opener', _TABLE +
     '    <!-- note\n        -->\n        - AC-1: real\n', ['- AC-1: real']),
    ('deep-opener-closes-at-code-threshold', _TABLE +
     '        <!-- note\n    -->\n    - AC-1: real\n', ['- AC-1: real']),
    ('closer-line-list-suffix-stays-hidden', _TABLE +
     '    <!-- note\n    - AC-99: hidden -->\n    - AC-1: real\n', ['- AC-1: real']),
    ('closer-line-table-criterion-stays-hidden', _TABLE +
     '    <!-- note\n    | AC-99 | hidden --> |\n    - AC-1: real\n', ['- AC-1: real']),
    ('near-miss-closer-does-not-end-code', _TABLE +
     '    <!-- note\n    -- >\n    - AC-99: hidden\n    -->\n    - AC-1: real\n',
     ['- AC-1: real']),
    ('empty-overlapping-comment-short', _TABLE +
     '    <!-->\n    - AC-1: real\n', ['- AC-1: real']),
    ('empty-overlapping-comment-long', _TABLE +
     '    <!--->\n    - AC-1: real\n', ['- AC-1: real']),
    ('empty-comment', _TABLE + '    <!---->\n    - AC-1: real\n', ['- AC-1: real']),
    ('embedded-closer-ends-whole-line', _TABLE +
     '    <!-- note\n    text --> trailing text\n    | AC-1 | real |\n', ['AC-1 | real']),
    ('blank-inside-comment-preserves-closer', _TABLE +
     '    <!-- note\n\n    - AC-99: hidden\n    -->\n    - AC-1: real\n', ['- AC-1: real']),
    ('tab-blank-inside-comment-preserves-closer', _TABLE +
     '    <!-- note\n\t\n    | AC-99 | hidden |\n    -->\n    - AC-1: real\n', ['- AC-1: real']),
    ('unclosed-comment-with-blank-keeps-code', _TABLE +
     '    <!-- note\n\n    - AC-99: hidden\n', []),
    ('dedent-one-column-before-closer', _TABLE +
     '    <!-- note\n    - AC-99: hidden\n   - AC-1: real\n    -->\n', ['- AC-1: real']),
    ('at-threshold-before-closer-stays-hidden', _TABLE +
     '    <!-- note\n    - AC-99: hidden\n    -->\n', []),
    ('nested-dedent-one-column-before-closer', _NESTED_TABLE +
     '      <!-- note\n      | AC-99 | hidden |\n     | AC-1 | real |\n      -->\n', ['AC-1 | real']),
    ('nested-at-threshold-stays-hidden', _NESTED_TABLE +
     '      <!-- note\n      | AC-99 | hidden |\n      -->\n', []),
    ('sibling-ends-unclosed-comment-code', _NESTED_TABLE +
     '      <!-- note\n      - AC-99: hidden\n- AC-1: real sibling\n', ['- AC-1: real sibling']),
    ('nested-close-then-sibling', _NESTED_TABLE +
     '      <!-- note -->\n      - AC-1: real nested\n- AC-2: real sibling\n',
     ['- AC-1: real nested', '- AC-2: real sibling']),
    ('two-level-container-close', '- Outer\n  - Inner\n' +
     ''.join('    ' + line + '\n' for line in _TABLE.splitlines()) +
     '        <!-- note -->\n        - AC-1: real\n', ['- AC-1: real']),
    ('dedented-prose-ends-unclosed-comment-code', _TABLE +
     '    <!-- note\n    - AC-99: hidden\nNew prose\n    - AC-1: real\n', ['- AC-1: real']),
    ('separate-tables-reset-comment-state', _TABLE +
     '    <!-- first -->\n    - AC-1: first\n' + _TABLE +
     '    <!-- second\n    - AC-99: hidden\n    -->\n    - AC-2: second\n',
     ['- AC-1: first', '- AC-2: second']),
    ('tab-closer-and-following-row', _TABLE +
     '\t<!-- note\n\t- AC-99: hidden\n\t-->\n\t| AC-1 | real |\n', ['AC-1 | real']),
    ('nested-tab-closer', _NESTED_TABLE +
     '\t\t<!-- note\n\t\t- AC-99: hidden\n\t\t-->\n\t\t- AC-1: real\n', ['- AC-1: real']),
    ('crlf-multiline-comment', (_TABLE +
     '    <!-- note\n    - AC-99: hidden\n    -->\n    - AC-1: real\n').replace('\n', '\r\n'),
     ['- AC-1: real']),
    ('comment-closer-then-unrelated-fence', _TABLE +
     '    <!-- note -->\n    ````\n    - AC-99: hidden -->\n    ```\n'
     '    - AC-98: hidden\n    ````\n    - AC-1: real\n', ['- AC-1: real']),
    ('comment-dedent-then-unrelated-fence', _TABLE +
     '    <!-- note\nNew prose\n    ```\n    - AC-99: hidden -->\n'
     '    - AC-98: hidden\n    ```\n    - AC-1: real\n', ['- AC-1: real']),
    ('fence-marker-inside-comment-is-literal', _TABLE +
     '    <!-- note\n    ```\n    - AC-99: hidden\n    -->\n    - AC-1: real\n', ['- AC-1: real']),
    ('closed-comment-then-blank-start-code', _TABLE +
     '    <!-- note -->\n\n    - AC-99: hidden\n    -->\n    - AC-98: hidden\n- AC-1: real\n',
     ['- AC-1: real']),
    ('blank-before-comment-remains-ordinary-code', _TABLE +
     '\n    <!-- note -->\n    - AC-99: hidden\n- AC-1: real\n', ['- AC-1: real']),
    ('blank-in-following-fence-retains-option-b', _TABLE +
     '    <!-- note -->\n    ```\n    - AC-99: hidden\n\n    ```\n'
     '    - AC-98: hidden\n- AC-1: real\n', ['- AC-1: real']),
    ('dedent-closer-line-keeps-existing-criterion-text', _TABLE +
     '    <!-- note\n| AC-1 | real --> |\n', ['AC-1 | real -->']),
]


class RequestParsingV7NeighborTests(ParserAssertions, unittest.TestCase):
    def test_comment_boundary_neighbors_direct(self):
        self.assert_direct_rows(BOUNDARY_NEIGHBORS)

    def test_comment_boundary_neighbors_public(self):
        self.assert_public_rows(BOUNDARY_NEIGHBORS)


if __name__ == '__main__':
    unittest.main()
