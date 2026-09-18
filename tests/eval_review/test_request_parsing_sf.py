"""SF-1/2/4: distinguish c2db7de failures from already-passing regressions."""
import unittest
from unittest.mock import patch

import test_gate_pack_run as fixtures
from hb_eval_review import cli, pack


HEADER = '# Request\nType: bug\n\n'

# Keep the review's exact inputs and IDs so RED and GUARD evidence stays auditable.
SF1_RED = (
    ('RI3', 'Example request:\n\n    ```\n    - AC-9: example only\n    ```\n', []),
    ('RI5', 'Example request:\n\n\t```\n\t- AC-9: example only\n\t```\n', []),
    ('RI2', '- Example:\n      ```\n      - AC-9: example only\n      ```\n- AC-1: real\n',
     ['- AC-1: real']),
)
SF1_GUARD = (
    ('RK1', '- 그룹 A\n    - AC-1: nested criterion\n', ['- AC-1: nested criterion']),
    ('RK2', '1. 그룹 A\n    - AC-1: nested criterion\n', ['- AC-1: nested criterion']),
    ('RK3', '- AC-1: first\n\n    - AC-2: second\n', ['- AC-1: first', '- AC-2: second']),
    ('RK4', '1. 예시 요청:\n    ```\n    - AC-9: example\n    ```\n- AC-1: real\n',
     ['- AC-1: real']),
    ('RU1', 'Shell output:\n\n    ```\n    exit 1\n\n- AC-1: real criterion\n',
     ['- AC-1: real criterion']),
    ('RL1', '- AC-1: first\nlazy continuation\n    - AC-2: second\n',
     ['- AC-1: first', '- AC-2: second']),
    ('RL2', 'Acceptance:\n    - AC-1: foo\n    - AC-2: bar\n',
     ['- AC-1: foo', '- AC-2: bar']),
)
SF2_RED = (
    ('RC1', '- AC-1: treat `<!--` as literal text\n- AC-2: save works\n',
     ['- AC-1: treat `<!--` as literal text', '- AC-2: save works']),
    ('RC2', 'The template may contain a literal <!-- marker.\n\n- AC-1: real criterion\n',
     ['- AC-1: real criterion']),
    ('RC4', '<!-->\n- AC-1: real criterion\n', ['- AC-1: real criterion']),
    ('RC5', '<!--->\n- AC-1: real criterion\n', ['- AC-1: real criterion']),
    ('X2', '<!-- a --> <!-- b\n- AC-1: real\n', ['- AC-1: real']),
    ('X3', 'Intro.\n\n    <!--\n- AC-9: counted\n', ['- AC-9: counted']),
    ('X4', '- AC-1: first <!-- note\n- AC-2: second criterion\n',
     ['- AC-1: first <!-- note', '- AC-2: second criterion']),
    ('X5', '| AC-ID | 기준 |\n|---|---|\n| AC-1 | render `<!--` literally |\n| AC-2 | second |\n',
     ['AC-1 | render `<!--` literally', 'AC-2 | second']),
    ('X1', '<!-- template --> - AC-1: same line\n- AC-2: next line\n', ['- AC-2: next line']),
    ('X7', '<!--\n- AC-9: hidden\n--> - AC-2: trailing\n- AC-1: real\n', ['- AC-1: real']),
)
SF2_GUARD = (
    ('RC3', '<!--\n- AC-9: template example\n-->\n- AC-1: real criterion\n',
     ['- AC-1: real criterion']),
    ('X6', '<!--\n- AC-9: hidden\n-->\n- AC-1: real\n', ['- AC-1: real']),
)
SF4_RED = tuple(
    ('T3-' + str(index), '| AC-ID | Criterion |\n' + delimiter + '\n', [])
    for index, delimiter in enumerate(('|-|-|', '| - | - |', '|:-|-:|', '|--|--|',
                                       ':-: | -----------:'), 1)
) + (
    ('RS1', '## Acceptance criteria\n- ...\n', []),
    ('RS2', '## 완료기준\n- [ ] ...\n', []),
    ('RS3', '## 수용 기준\n1. ...\n', []),
)
SF4_GUARD = (
    ('T1', '| AC-ID | 기준 |\n|---|---|\n| AC-1 | 로그인 |\n| - | - |\n',
     ['AC-1 | 로그인']),
)
N5_GUARD = (
    ('RM18a', '- AC-01 - ...\n', []),
    ('RM18b', '- AC-01. ...\n', []),
    ('RM20', '- - ```\n    - AC-8: code\n    ```\n- AC-1: real\n', ['- AC-1: real']),
)


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


class RequestParsingSFRedTests(ParserAssertions, unittest.TestCase):
    """Every subTest here fails on the unmodified c2db7de runtime."""

    def test_sf1_indented_examples(self):
        self.assert_direct_rows(SF1_RED)

    def test_sf1_public_pack(self):
        self.assert_public_rows(SF1_RED)

    def test_sf2_comment_block_boundaries(self):
        self.assert_direct_rows(SF2_RED)

    def test_sf2_public_pack(self):
        self.assert_public_rows(SF2_RED)

    def test_sf4_short_delimiters_and_heading_placeholders(self):
        self.assert_direct_rows(SF4_RED)

    def test_sf4_public_pack(self):
        self.assert_public_rows(SF4_RED)


class RequestParsingSFGuardTests(ParserAssertions, unittest.TestCase):
    """These cases already pass on c2db7de; never count them as RED evidence."""

    def test_sf1_nested_lists_lazy_continuation_and_unpaired_code_fence(self):
        self.assert_direct_rows(SF1_GUARD)

    def test_indented_inline_backticks_do_not_hide_following_criteria(self):
        # Independent delta review: these pass on c2db7de but caught the first
        # SF-1 draft treating invalid backtick info strings as literal code blocks.
        rows = (
            ('inline', 'Acceptance:\n    ```x``` is inline code in prose\n    - AC-1: real criterion\n',
             ['- AC-1: real criterion']),
            ('invalid-info', 'Acceptance:\n    ```language`option\n    - AC-1: real criterion\n',
             ['- AC-1: real criterion']),
            ('nested-inline', '- Group:\n      ```x``` is inline code in prose\n      - AC-1: real criterion\n',
             ['- AC-1: real criterion']),
        )
        self.assert_direct_rows(rows)
        self.assert_public_rows(rows)

    def test_sf2_comments_still_hide_examples(self):
        self.assert_direct_rows(SF2_GUARD)

    def test_sf2_closed_inline_comment_keeps_both_criteria(self):
        actual = pack._acceptance(HEADER + '- AC-1: real <!-- note --> text\n- AC-2: next\n')
        self.assertEqual(2, len(actual))
        self.assertIn(actual[0], ('- AC-1: real <!-- note --> text', '- AC-1: real  text'))
        self.assertEqual('- AC-2: next', actual[1])

    def test_sf4_delimiter_in_table_body_does_not_remove_previous_criterion(self):
        self.assert_direct_rows(SF4_GUARD)

    def test_n5_placeholder_punctuation_and_repeated_list_markers(self):
        self.assert_direct_rows(N5_GUARD)

    def test_public_pack_preserves_guards(self):
        self.assert_public_rows(SF1_GUARD + SF2_GUARD + SF4_GUARD + N5_GUARD)


if __name__ == '__main__':
    unittest.main()
