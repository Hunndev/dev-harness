"""SF-5–SF-8 exact v4 rows, separating 6688272 RED from existing GUARD behavior.

The equivalent class adds behavior beyond the canonical RED rows; its inputs
also fail on 6688272 and are reported separately from the canonical baseline.
"""
import unittest
from unittest.mock import patch

import test_gate_pack_run as fixtures
from hb_eval_review import cli, pack

# Canonical v4 inputs retain their IDs and expectations. Optional C3r/C4r remain
# recorded below but are not required acceptance cases or RED-to-GREEN evidence.
HEADER = '# Request\nType: bug\n\n'

# 배포 SHARED/commands/seed.md:97-99 완료기준 표(원본)와, AC-01 셀에 예시 주석만 더한 변형.
SEED = (
    '| 완료기준 | 적용 렌즈 (스택) | 어디서 검증 |\n'
    '|----------|------------------|-------------|\n'
    '| AC-01: ... | BE/CM=테스트·lint·build / FE=[디자인]시각·UX·반응형·접근성+Claude 검증·'
    '[바인딩]계약·상태·mock / CHAT=+계약·dual gate / AOS·IOS=[shell]기기·권한·푸시·딥링크·'
    '[브리지]계약·형제 동일 | build / evaluate |\n'
)
SEED_COMMENTED = SEED.replace('| AC-01: ... |', '| AC-01: ... <!-- 예: 로그인 성공 --> |', 1)


def ANY_OF(*options):
    return tuple(options)


ROWS = [
    # SF-5: 중첩 목록의 lazy 판정은 바깥 컨테이너 기준 나머지로 블록 시작을 본다.
    ('SF5-L2', 'RED', '- 그룹 A\n    - 예시 요청:\n    ```\n    - AC-9: example only\n    ```\n', []),
    ('SF5-L6tab', 'RED', '- 그룹 A\n\t- 예시 요청:\n\t```\n\t- AC-9: example only\n\t```\n', []),
    ('SF5-L4', 'RED', '- 그룹 A\n    - 메모:\n    <!--\n    - AC-9: example only\n    -->\n', []),
    ('SF5-L8', 'RED', '1. 로그인\n    - 입력 예시:\n    <!--\n    - AC-9: example\n    -->\n', []),
    ('SF5-L1', 'RED', '- 그룹 A\n    - 예시 요청:\n    ```\n    - AC-9: example only\n    ```\n- AC-1: real\n',
     ['- AC-1: real']),
    ('SF5-L3', 'RED', '- 그룹 A\n    - 메모:\n    <!--\n    - AC-9: example only\n    -->\n- AC-1: real\n',
     ['- AC-1: real']),
    ('SF5-L5', 'RED', '- a\n  - b\n     - c\n    ```\n    - AC-9: example\n    ```\n- AC-1: real\n',
     ['- AC-1: real']),
    ('SF5-Z1', 'GUARD', '- AC-1: first\nlazy continuation\n\n    - AC-2: second\n',
     ['- AC-1: first', '- AC-2: second']),
    ('SF5-L7ctl', 'GUARD', '- 그룹 A\n  - 예시 요청:\n  ```\n  - AC-9: example only\n  ```\n', []),
    ('SF5-C12', 'GUARD', '- AC-1: first\n<!--\n- AC-9: hidden\n-->\n- AC-2: second\n',
     ['- AC-1: first', '- AC-2: second']),

    # SF-6: 빈 줄 없는 과도 들여쓰기 fence의 예시 구간은 짝이 되는 닫는 fence에서 끝난다.
    ('SF6-A4', 'RED', 'Acceptance:\n    ```text\n    example\n    ```\n    - AC-1: real\n', ['- AC-1: real']),
    ('SF6-A7', 'RED', 'Acceptance:\n    ```text\n    - AC-9: example\n    ```\n    - AC-1: real\n    - AC-2: real2\n',
     ['- AC-1: real', '- AC-2: real2']),
    ('SF6-A5', 'RED', '- Example:\n      ```\n      - AC-9: example only\n      ```\n      - AC-1: real\n',
     ['- AC-1: real']),
    ('SF6-R2', 'RED', 'Acceptance:\n    - 예시 형식:\n      ```\n      - AC-9: example\n      ```\n    - AC-1: real\n'
     '    - AC-2: real\n', ['- AC-1: real', '- AC-2: real']),
    ('SF6-A8k', 'RED', '인수 조건:\n    - AC-1: `make test`가 통과한다\n    ```sh\n    make test\n    ```\n'
     '    - AC-2: 로그인 후 대시보드로 이동한다\n',
     ['- AC-1: `make test`가 통과한다', '- AC-2: 로그인 후 대시보드로 이동한다']),
    ('SF6-A14', 'RED', 'Acceptance:\n    - AC-1: foo\n    ~~~\n    output\n    ~~~\n    - AC-2: bar\n',
     ['- AC-1: foo', '- AC-2: bar']),
    ('SF6-R1', 'RED', 'Acceptance:\n    - AC-1: foo\n      ```\n      - AC-9: example\n      ```\n    - AC-2: bar\n',
     ['- AC-1: foo', '- AC-2: bar']),
    ('SF6-R3', 'RED', 'Acceptance:\n    - AC-1: foo\n        ```\n        - AC-9: example\n        ```\n    - AC-2: bar\n',
     ['- AC-1: foo', '- AC-2: bar']),
    ('SF6-A6', 'GUARD', 'Acceptance:\n    ```text\n    example\n    ```\n- AC-1: real\n', ['- AC-1: real']),
    ('SF6-A12', 'GUARD', '- AC-1: first\n      ```\n      example\n      ```\n  - AC-2: nested real\n',
     ['- AC-1: first', '- AC-2: nested real']),
    ('SF6-A13', 'GUARD', '1. AC-1: run\n       ```sh\n       make\n       ```\n   - AC-2: nested\n',
     ['1. AC-1: run', '- AC-2: nested']),

    # SF-7: `...` 자리표시자 비교는 닫힌 inline 주석을 뺀 렌더 문구로 한다. 기록 문구는 보존해도 된다.
    ('SF7-D1', 'RED', '- AC-01: ... <!-- 예: 로그인 성공 -->\n', []),
    ('SF7-D2', 'RED', '| AC-ID | 기준 |\n|---|---|\n| AC-01 | ... <!-- 예시 --> |\n', []),
    ('SF7-D3', 'RED', '- AC-01: <!-- 여기에 기준 --> ...\n', []),
    ('SF7-D4seed', 'RED', SEED_COMMENTED, []),
    ('SF7-D5', 'RED', '## Acceptance criteria\n- ... <!-- 기준 작성 -->\n', []),
    ('SF7-SEED', 'GUARD', SEED, []),
    ('SF7-GIN', 'GUARD', '- AC-1: real <!-- note --> text\n- AC-2: next\n',
     ANY_OF(['- AC-1: real <!-- note --> text', '- AC-2: next'], ['- AC-1: real  text', '- AC-2: next'])),
    ('SF7-CODESPAN', 'GUARD', '- AC-1: render `<!-- x -->` literally\n- AC-2: next\n',
     ['- AC-1: render `<!-- x -->` literally', '- AC-2: next']),

    # SF-8: 문단 연속 줄 속 여러 줄 inline 주석(또는 제목 뒤 들여쓴 코드)의 예시는 기준이 아니다.
    ('SF8-C5b', 'RED', 'Acceptance:\n    <!--\n    - AC-9: example, delete me\n    -->\n', []),
    ('SF8-C1tab', 'RED', 'Acceptance:\n\t<!--\n\t- AC-9: example only\n\t-->\n', []),
    ('SF8-C1r', 'RED', 'Acceptance:\n    <!-- 템플릿 예시\n    - AC-9: example\n    -->\n', []),
    ('SF8-C5c', 'RED', '## 완료 기준\n    <!--\n    - AC-01: 예시 기준, 지우고 작성\n    -->\n', []),
    ('SF8-C5', 'RED', 'Intro text\n    <!--\n    - AC-9: example\n    -->\n- AC-1: real\n', ['- AC-1: real']),
    ('SF8-C1list', 'RED', '- Group:\n      <!--\n      - AC-9: example only\n      -->\n- AC-1: real\n',
     ['- AC-1: real']),
    ('SF8-C2r', 'RED', 'Acceptance:\n    - AC-1: foo\n      <!-- 예시\n      - AC-9: example\n      -->\n    - AC-2: bar\n',
     ['- AC-1: foo', '- AC-2: bar']),
    ('SF8-C3r', 'OPTIONAL_RED', '예시는 아래와 같다 <!--\n| AC-9 | example |\n-->\n', []),
    ('SF8-C4r', 'OPTIONAL_RED', '예시는 아래와 같다 <!--\n| AC-9 | example |\n-->\n- AC-1: real\n', ['- AC-1: real']),
    ('SF8-K3', 'GUARD', 'Note: <!--\n- AC-9: example\n-->\n', ['- AC-9: example']),
    ('SF8-ONELINE4', 'GUARD', 'Acceptance:\n    <!-- note -->\n    - AC-1: real\n', ['- AC-1: real']),
]

# All these controls also pass on 6688272. They protect the state transitions
# around the required rows without treating newly discovered guards as RED.
NEIGHBOR_GUARDS = (
    ('SF5-invalid-backtick-info-lazy', '- Parent\n    - Child\n    ```bad`info\n\n'
     '      - AC-1: real\n', ['- AC-1: real']),
    ('SF5-invalid-backtick-info-lazy-tab', '- Parent\n\t- Child\n\t```bad`info\n\n'
     '\t  - AC-1: real\n', ['- AC-1: real']),
    ('N6-B5', 'Intro\n\n\t\t- AC-9: code\n- AC-1: real\n', ['- AC-1: real']),
    ('N6-F8', '- AC-1: first\nlazy\n\n      - AC-9: code\n', ['- AC-1: first']),
    ('N6-C14', '- AC-1: real\n<!--\n- AC-9: hidden\n', ['- AC-1: real']),
    ('SF6-unclosed-dedent', '- AC-1: first\n      ```\n      example\n'
     '  - AC-2: nested real\n', ['- AC-1: first', '- AC-2: nested real']),
    ('SF6-ordered-unclosed-dedent', '1. AC-1: run\n       ```sh\n       make\n'
     '   - AC-2: nested\n', ['1. AC-1: run', '- AC-2: nested']),
    ('SF6-blank-start-code', 'Intro\n\n    ```\n    example\n    ```\n'
     '    - AC-9: still code\n- AC-1: real\n', ['- AC-1: real']),
    ('SF6-deeper-delimiter-is-example', 'Acceptance:\n    ```\n        ```\n'
     '    - AC-9: still example\n    ```\n- AC-1: real\n', ['- AC-1: real']),
    ('SF8-list-boundary', 'Acceptance:\n    <!--\n- AC-1: real\n-->\n',
     ['- AC-1: real']),
    ('SF8-blank-boundary', 'Acceptance:\n    <!--\n\n- AC-1: real\n-->\n',
     ['- AC-1: real']),
    ('SF8-blank-interrupts-candidate', 'Acceptance:\n    <!--\n    - AC-1: literal\n'
     '\n    -->\n- AC-2: real\n', ['- AC-1: literal', '- AC-2: real']),
    ('SF8-interrupted-example', 'Acceptance:\n    <!--\n    - AC-9: literal\n'
     '- AC-1: real\n-->\n', ['- AC-9: literal', '- AC-1: real']),
    ('SF8-unclosed-continuation', 'Acceptance:\n    <!--\n    - AC-1: real\n',
     ['- AC-1: real']),
    ('SF8-oneline-before-later-closer', 'Acceptance:\n    <!-- note -->\n'
     '    - AC-1: real\n    -->\n', ['- AC-1: real']),
    ('SF8-quote-boundary', 'Acceptance:\n    <!--\n    - AC-1: literal\n'
     '> quoted paragraph\n-->\n', ['- AC-1: literal']),
    ('SF8-thematic-break-boundary', 'Acceptance:\n    <!--\n    - AC-1: literal\n'
     '***\n-->\n', ['- AC-1: literal']),
    ('SF8-empty-heading-boundary', 'Acceptance:\n    <!--\n    - AC-1: literal\n'
     '##\n-->\n', ['- AC-1: literal']),
    ('SF7-comment-in-code', '- AC-1: `<!-- ... -->`\n', ['- AC-1: `<!-- ... -->`']),
    ('SF7-backtick-runs', '- AC-1: ``literal ` <!-- ... -->``\n',
     ['- AC-1: ``literal ` <!-- ... -->``']),
)

SF7_EQUIVALENTS = (
    ('SF7-empty-comment', '- AC-01: ... <!-->\n', []),
    ('SF7-dash-comment', '- AC-01: ... <!--->\n', []),
)

SF8_EQUIVALENTS = (
    ('SF8-invalid-backtick-info-continuation', 'Intro\n    <!--\n```bad`info\n'
     '    - AC-9: hidden\n    -->\n', []),
)


def required_rows(kind, prefix=''):
    return [(label, request, expected) for label, row_kind, request, expected in ROWS
            if row_kind == kind and label.startswith(prefix)]


class ParserAssertions:
    def assert_refs(self, expected, actual):
        if isinstance(expected, tuple):
            self.assertIn(actual, expected)
        else:
            self.assertEqual(expected, actual)

    def assert_direct_rows(self, rows):
        for label, request, expected in rows:
            with self.subTest(case=label):
                self.assert_refs(expected, pack._acceptance(HEADER + request))

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
                    self.assert_refs(expected, packet['request']['acceptance_refs'])
                    self.assert_refs(expected, packet['request']['acceptance_criteria'])
                else:
                    self.assertEqual(2, rc, result)
                    self.assertEqual('BLOCKED', result['status'])
                    self.assertEqual(['PACKET_SCHEMA_INVALID'], result['errors'])


class RequestParsingSF58RedTests(ParserAssertions, unittest.TestCase):
    """Each direct/public subTest is a required failure on the 6688272 runtime."""

    def test_sf5_outer_container_block_starts(self):
        self.assert_direct_rows(required_rows('RED', 'SF5-'))

    def test_sf5_public_pack(self):
        self.assert_public_rows(required_rows('RED', 'SF5-'))

    def test_sf6_paired_overindented_examples(self):
        self.assert_direct_rows(required_rows('RED', 'SF6-'))

    def test_sf6_public_pack(self):
        self.assert_public_rows(required_rows('RED', 'SF6-'))

    def test_sf7_commented_placeholders(self):
        self.assert_direct_rows(required_rows('RED', 'SF7-'))

    def test_sf7_public_pack(self):
        self.assert_public_rows(required_rows('RED', 'SF7-'))

    def test_sf8_continuation_comments(self):
        self.assert_direct_rows(required_rows('RED', 'SF8-'))

    def test_sf8_public_pack(self):
        self.assert_public_rows(required_rows('RED', 'SF8-'))


class RequestParsingSF58GuardTests(ParserAssertions, unittest.TestCase):
    """These guards already pass on 6688272 and are not RED evidence."""

    def test_required_guards_direct(self):
        self.assert_direct_rows(required_rows('GUARD'))

    def test_required_guards_public(self):
        self.assert_public_rows(required_rows('GUARD'))

    def test_neighbor_guards_direct(self):
        self.assert_direct_rows(NEIGHBOR_GUARDS)

    def test_neighbor_guards_public(self):
        self.assert_public_rows(NEIGHBOR_GUARDS)


class RequestParsingSF58EquivalentTests(ParserAssertions, unittest.TestCase):
    """Equivalent comment cases beyond the canonical 27-row RED evidence."""

    def test_extra_equivalent_cases(self):
        self.assert_direct_rows(SF7_EQUIVALENTS + SF8_EQUIVALENTS)

    def test_extra_equivalent_public_pack(self):
        self.assert_public_rows(SF7_EQUIVALENTS + SF8_EQUIVALENTS)


if __name__ == '__main__':
    unittest.main()
