"""SF-9/SF-10 exact v5 rows with RED, adopted CONSEQUENCE, and GUARD evidence.

Existing SF-5–SF-8 equivalence classes in test_request_parsing_sf58.py also fail
on 6688272 and represent additional behavior changes, not existing guards.
They remain unchanged and are separate from the canonical v5 RED evidence.
"""
import unittest
from unittest.mock import patch

import test_gate_pack_run as fixtures
from hb_eval_review import cli, pack

# Preserve all 27 canonical v5 row IDs, requests, and expectations exactly.
# The user adopted the two CONSEQUENCE rows as required blocking behavior.
HEADER = '# Request\nType: bug\n\n'

TABLE = '| ID | Criterion |\n| --- | --- |\n| AC-1 | real criterion |\n'


def ANY_OF(*options):
    return tuple(options)


ROWS = [
    # SF-9: 문단 연속 inline 주석의 짝 찾기는 GFM 표 시작(헤더 줄 + 바로 다음 구분선)과
    # setext `=` 밑줄을 문단 경계로 본다. 경계를 만나면 주석은 닫히지 못하고 글자로 남는다.
    ('SF9-A1', 'RED', 'Plan the table below.\n    <!-- note\n' + TABLE + 'end -->\n',
     ['AC-1 | real criterion']),
    ('SF9-A1b', 'RED', 'Plan the table below.\n    <!-- note\n' + TABLE + '    -->\n- AC-2: real list\n',
     ['AC-1 | real criterion', '- AC-2: real list']),
    ('SF9-A1c', 'RED', 'Plan the table below.\n    <!-- note\nID | Criterion\n--- | ---\nAC-1 | real criterion\n    -->\n',
     ['AC-1 | real criterion']),
    ('SF9-A1d', 'RED', '- AC-0: real item\n      <!-- note\n  | ID | Criterion |\n  | --- | --- |\n'
     '  | AC-1 | real criterion |\n      -->\n', ['- AC-0: real item', 'AC-1 | real criterion']),
    ('SF9-A3b', 'RED', 'Plan.\n    <!-- note\n===\n' + TABLE + '    -->\n', ['AC-1 | real criterion']),
    ('SF9-A1crlf', 'RED', ('Plan.\n    <!-- note\n' + TABLE + '    -->\n').replace('\n', '\r\n'),
     ['AC-1 | real criterion']),
    ('SF9-C1h', 'RED', '## 완료 기준\n    <!-- 아래 표는 예시\n| AC-ID | 기준 |\n|---|---|\n| AC-1 | 로그인 성공 |\n    -->\n',
     ['AC-1 | 로그인 성공']),
    ('SF9-C3', 'RED', 'Acceptance:\n    <!-- 예시\n===\n| AC-1 | real |\n    -->\n', ['AC-1 | real']),
    ('SF9-T1', 'RED', 'Acceptance:\n    <!--\n| AC-ID | 기준 |\n|---|---|\n| AC-1 | real |\n-->\n',
     ['AC-1 | real']),
    # T7 기대값은 기록 문구 그대로의 정확 일치다(표 셀 문구의 `-->`를 지우지 않는다).
    ('SF9-T7', 'RED', 'Acceptance:\n    <!--\n| AC-ID | 기준 |\n|---|---|\n| AC-1 | real --> |\n',
     ['AC-1 | real -->']),
    ('SF9-T8', 'RED', 'Acceptance:\n\t<!--\n| AC-ID | 기준 |\n|---|---|\n| AC-1 | real |\n-->\n', ['AC-1 | real']),
    # 구분선이 없는 파이프 줄은 표가 아니라 문단 연속이다. 닫힌 주석 안이면 계속 숨긴다.
    ('SF9-C2', 'GUARD', 'Acceptance:\n    <!-- 예시\n| AC-9 | example |\n    -->\n- AC-1: real\n', ['- AC-1: real']),
    # 4칸 들여쓴 표 모양 줄은 문단 연속이다(표 시작은 컨테이너 기준 0–3칸). 닫힌 주석 안이면 계속 숨긴다.
    ('SF9-4sp-table', 'GUARD', 'Acceptance:\n    <!-- 예시\n    | AC-9 | example |\n    |---|---|\n    -->\n', []),
    # 한 열 구분선(`|---|`)은 이 파서의 표 시작이 아니다(셀 2개 이상). 헤더 `| AC-9 |`를 기준으로 되살리지 않는다.
    ('SF9-1col', 'GUARD', 'Acceptance:\n    <!-- 예시\n| AC-9 |\n|---|\n    -->\n- AC-1: real\n', ['- AC-1: real']),
    # setext `---` 밑줄은 기존 thematic break 경계가 이미 처리한다(별도 규칙 불필요).
    ('SF9-setext-dash', 'GUARD', 'Acceptance:\n    <!-- 예시\n---\n| AC-1 | real |\n    -->\n', ['AC-1 | real']),
    ('SF9-4sp-setext', 'GUARD', 'Acceptance:\n    <!-- 예시\n    ====\n    - AC-9: x\n    -->\n- AC-1: real\n',
     ['- AC-1: real']),

    # SF-10: 호환 예시 fence 구간 안에 빈 줄이 끼면 그 문단은 끝난다. 뒤의 닫는 fence 모양 줄과
    # 4칸 줄은 들여쓴 코드이고, 호환 기준 수집을 재개하지 않는다(RL2 정의: 빈 줄로 끊기지 않은 산문 뒤).
    ('SF10-B1', 'RED', 'Example of how to write criteria:\n    ```\n    - AC-1: example only\n\n    ```\n'
     '    - AC-2: example only\n', []),
    ('SF10-B1t', 'RED', 'Example of how to write criteria:\n    ~~~\n    - AC-1: example only\n\n    ~~~\n'
     '    - AC-2: example only\n', []),
    ('SF10-B1l', 'RED', '- AC-0: real item\n      ```\n      - AC-1: example only\n\n      ```\n'
     '      - AC-2: example only\n', ['- AC-0: real item']),
    # 아래 두 행은 수정의 귀결(CONSEQUENCE)이다. 렌더러와 6688272는 코드로 보고, 943324e·c2db7de·233cac7은
    # 실제 AC로 수집한다. B1과 구조가 같아 따로 떼어 낼 수 없으며 이번 사용자 결정으로 차단을 채택했다.
    ('SF10-F8', 'CONSEQUENCE', 'Acceptance:\n    ```\n    a\n\n    b\n    ```\n    - AC-1: real\n', []),
    ('SF10-TRADEOFF', 'CONSEQUENCE', 'Acceptance:\n    ```text\n    - AC-9: example one\n\n    - AC-8: example two\n'
     '    ```\n    - AC-1: real\n', []),
    ('SF10-NOFENCE', 'GUARD', 'Example:\n    - AC-1: x\n\n    - AC-2: x\n', ['- AC-1: x']),
    ('SF10-F9', 'GUARD', 'Acceptance:\n    ```text\n    one\n    ```\n    ```text\n    - AC-9: two\n    ```\n'
     '    - AC-1: real\n', ['- AC-1: real']),
    ('SF10-F2', 'GUARD', 'Acceptance:\n    ```\n    ex\n    `````\n    - AC-1: real\n', ['- AC-1: real']),
    # 닫는 fence 짝 조건(문자·길이·info). 233cac7은 지키지만 테스트가 없다(변이 V4–V6 생존).
    ('SF10-F3', 'GUARD', 'Acceptance:\n    ````\n    ex\n    ```\n    - AC-1: real\n', []),
    ('SF10-F4', 'GUARD', 'Acceptance:\n    ```\n    ex\n    ~~~\n    - AC-1: real\n', []),
    ('SF10-F5', 'GUARD', 'Acceptance:\n    ```\n    ex\n    ``` text\n    - AC-1: real\n', []),
]


# Table-neighbor behavior is explicit, including container-relative indentation.
TABLE_NEIGHBORS = (
    ('SF9-list-container-table', '- Group\n      <!-- note\n'
     '     | ID | Criterion |\n     |---|---|\n     | AC-1 | real |\n      -->\n',
     ['AC-1 | real']),
    ('SF9-escaped-pipe-header', 'Intro\n    <!-- note\n'
     '| Label \\| detail | Criterion |\n|---|---|\n| AC-1 | real |\n    -->\n',
     ['AC-1 | real']),
    ('SF9-no-header-pipe', 'Intro\n    <!-- note\n    - AC-9: example\n'
     'Label and criterion\n|---|---|\n    -->\n- AC-1: real\n', ['- AC-1: real']),
    ('SF9-immediate-header-three-spaces', 'Intro\n    <!--\n'
     '   | ID | Criterion |\n   |:---|---:|\n   | AC-1 | real |\n    -->\n',
     ['AC-1 | real']),
    ('SF9-list-four-space-table', '- Group\n      <!-- note\n'
     '      | AC-9 | example |\n      |---|---|\n      -->\n', []),
    ('SF9-one-column-alignment', 'Intro\n    <!-- note\n| AC-9 |\n|:---:|\n'
     '    -->\n- AC-1: real\n', ['- AC-1: real']),
)


def required_rows(kind, prefix=''):
    return [(label, request, expected) for label, row_kind, request, expected in ROWS
            if row_kind == kind and label.startswith(prefix)]


class ParserAssertions:
    def assert_direct_rows(self, rows):
        for label, request, expected in rows:
            with self.subTest(case=label):
                self.assertEqual(expected, pack._acceptance(HEADER + request))

    def assert_public_rows(self, rows):
        case = fixtures.GatePackRunTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.artifacts, case.request_name = fixtures.evidence_fixture(
            case.repo, 'maintenance', 'bug', ignored=True)
        case.packet_dir = case.artifacts / 'eval-review/packet'
        args = ['pack', '--repo', str(case.repo), '--artifacts', str(case.artifacts),
                '--request-source', case.request_name, '--base', 'HEAD',
                '--claude-model', 'claude-test', '--codex-model', 'codex-test']
        for label, request, expected in rows:
            with self.subTest(case=label):
                (case.artifacts / case.request_name).write_text(HEADER + request, encoding='utf-8')
                with patch.object(cli, 'run_provider_stage') as provider:
                    rc, result = case.invoke(args)
                provider.assert_not_called()
                if expected:
                    self.assertEqual(0, rc, result)
                    packet = cli._load(str(case.packet_dir / 'packet.json'))
                    self.assertEqual(expected, packet['request']['acceptance_refs'])
                    self.assertEqual(expected, packet['request']['acceptance_criteria'])
                else:
                    self.assertEqual(2, rc, result)
                    self.assertEqual('BLOCKED', result['status'])
                    self.assertEqual(['PACKET_SCHEMA_INVALID'], result['errors'])


class RequestParsingSF910RedTests(ParserAssertions, unittest.TestCase):
    """The canonical RED 14 rows each fail directly and publicly on 233cac7."""

    def test_sf9_paragraph_boundaries_direct(self):
        self.assert_direct_rows(required_rows('RED', 'SF9-'))

    def test_sf9_paragraph_boundaries_public(self):
        self.assert_public_rows(required_rows('RED', 'SF9-'))

    def test_sf10_blank_ends_compatibility_direct(self):
        self.assert_direct_rows(required_rows('RED', 'SF10-'))

    def test_sf10_blank_ends_compatibility_public(self):
        self.assert_public_rows(required_rows('RED', 'SF10-'))


class RequestParsingSF910ConsequenceTests(ParserAssertions, unittest.TestCase):
    """Both adopted consequences fail on 233cac7, separately from the RED 14."""

    def test_adopted_consequences_direct(self):
        self.assert_direct_rows(required_rows('CONSEQUENCE'))

    def test_adopted_consequences_public(self):
        self.assert_public_rows(required_rows('CONSEQUENCE'))


class RequestParsingSF910GuardTests(ParserAssertions, unittest.TestCase):
    """The canonical GUARD 11 rows already pass on 233cac7."""

    def test_existing_guards_direct(self):
        self.assert_direct_rows(required_rows('GUARD'))

    def test_existing_guards_public(self):
        self.assert_public_rows(required_rows('GUARD'))


class RequestParsingSF910NeighborTests(ParserAssertions, unittest.TestCase):
    """Table neighbors supplement the canonical evidence without relabeling it."""

    def test_table_neighbors_direct(self):
        self.assert_direct_rows(TABLE_NEIGHBORS)

    def test_table_neighbors_public(self):
        self.assert_public_rows(TABLE_NEIGHBORS)


# A failed scan stops before its boundary. Later candidates still need their own
# pairing decision, including a changed list context and a same-line closer.
SCAN_BOUNDARIES = (
    ('blank', '\n', []),
    ('list', '- AC-2: boundary\n', ['- AC-2: boundary']),
    ('heading', '## Notes\n', []),
    ('empty-heading', '##\n', []),
    ('quote', '> quote\n', []),
    ('thematic-break', '***\n', []),
    ('setext-equals', '===\n', []),
    ('table', '| ID | Criterion |\n|---|---|\n| AC-2 | boundary |\n',
     ['AC-2 | boundary']),
    ('html-comment', '<!-- boundary -->\n', []),
    ('fence', '```text\nexample\n```\n', []),
)
SCAN_NEIGHBORS = tuple(
    ('N11-' + label,
     'Intro\n    <!-- unclosed\n    <!-- also unclosed\n'
     '    - AC-1: literal before boundary\n' + boundary +
     'Following paragraph\n    <!-- same line -->\n    - AC-3: real\n'
     '    <!-- paired\n    - AC-9: hidden\n    -->\n- AC-4: final\n',
     ['- AC-1: literal before boundary'] + boundary_refs + ['- AC-3: real', '- AC-4: final'])
    for label, boundary, boundary_refs in SCAN_BOUNDARIES
) + (
    ('N11-changing-list-context', '- Outer\n      <!-- unclosed\n  - Nested\n'
     '        <!-- unclosed\n        - AC-1: literal\n  - AC-2: sibling\n'
     '        <!-- paired\n        - AC-9: hidden\n        -->\n- AC-3: final\n',
     ['- AC-1: literal', '- AC-2: sibling', '- AC-3: final']),
)


class RequestParsingSF910ScanTests(ParserAssertions, unittest.TestCase):
    def test_scan_boundary_neighbors_direct(self):
        self.assert_direct_rows(SCAN_NEIGHBORS)

    def test_scan_boundary_neighbors_public(self):
        self.assert_public_rows(SCAN_NEIGHBORS)

    def test_unmatched_candidates_have_linear_line_inspections(self):
        # Count actual line expansion rather than relying on host wall-clock speed.
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

                request = CountedText(HEADER + 'Intro\n' + '    <!-- unclosed\n' * count
                                      + '    - AC-1: literal\n')
                self.assertEqual(['- AC-1: literal'], pack._acceptance(request))
                self.assertLessEqual(len(inspections), 3 * count + 20)


if __name__ == '__main__':
    unittest.main()
