"""R4: bind actual criteria, excluding Markdown examples and empty seed rows."""
import unittest
from unittest.mock import patch

import test_gate_pack_run as fixtures
from hb_eval_review import cli, pack


def seed_template():
    source = (fixtures.ROOT / 'SHARED/commands/seed.md').read_text(encoding='utf-8')
    return source.split('```markdown\n', 1)[1].split('\n```', 1)[0]


class RequestParsingR4Tests(unittest.TestCase):
    def fixture(self, request):
        case = fixtures.GatePackRunTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.artifacts, case.request_name = fixtures.evidence_fixture(
            case.repo, 'maintenance', 'bug', ignored=True)
        case.packet_dir = case.artifacts / 'eval-review/packet'
        (case.artifacts / case.request_name).write_text(request, encoding='utf-8')
        return case

    def pack_args(self, case):
        return ['pack', '--repo', str(case.repo), '--artifacts', str(case.artifacts),
                '--request-source', case.request_name, '--base', 'HEAD',
                '--claude-model', 'claude-test', '--codex-model', 'codex-test']

    def test_html_comments_do_not_supply_criteria_or_change_heading_scope(self):
        for comment in (
                '<!--\n- AC-9: template example, delete me\n-->\n',
                '<!--\n## Acceptance criteria\n- AC-9: hidden\n-->\n- notes only\n',
                '<!--\n```\n- AC-9: hidden\n-->\n',
                '<!--\n- AC-9: hidden without a closing comment\n'):
            with self.subTest(comment=comment):
                self.assertEqual([], pack._acceptance(comment))
        self.assertEqual(['- AC-1: real'], pack._acceptance(
            '<!--\n- AC-9: hidden\n-->\n- AC-1: real\n'))
        # A comment opener in literal fenced content cannot hide the real criterion.
        self.assertEqual(['- AC-1: real'], pack._acceptance(
            '```\n<!--\n```\n- AC-1: real\n'))

    def test_table_header_is_excluded_with_and_without_data_rows(self):
        for edges in (True, False):
            for data in (False, True):
                with self.subTest(edges=edges, data=data):
                    lines = ['AC-ID | Criterion', '--- | ---']
                    if data:
                        lines.append('AC-1 | Login succeeds')
                    if edges:
                        lines = ['| ' + line + ' |' for line in lines]
                    self.assertEqual(['AC-1 | Login succeeds'] if data else [],
                                     pack._acceptance('\n'.join(lines)))

    def test_backtick_info_cannot_contain_backticks(self):
        for inline in ('```x``` is inline code in prose', '```language`option',
                       '````x``` is inline code in prose'):
            with self.subTest(inline=inline):
                self.assertEqual(['- AC-1: first', '- AC-2: second'], pack._acceptance(
                    '- AC-1: first\n' + inline + '\n- AC-2: second\n'))
        self.assertEqual(['- AC-1: real'], pack._acceptance(
            '~~~language`option\n- AC-9: code\n~~~\n- AC-1: real\n'))

    def test_fence_closing_indent_is_at_most_three_spaces(self):
        for fence in ('```', '~~~'):
            for indent in (0, 3, 4):
                with self.subTest(fence=fence, indent=indent):
                    if indent <= 3:
                        text = fence + '\n' + ' ' * indent + fence + '\n- AC-1: real\n'
                    else:
                        text = (fence + '\n    ' + fence + '\n- AC-8: still code\n'
                                + fence + '\n- AC-1: real\n')
                    self.assertEqual(['- AC-1: real'], pack._acceptance(text))

    def test_list_fence_indent_is_relative_to_the_container(self):
        for marker, content_indent in (('- ', 2), ('10. ', 4)):
            for fence in ('```', '~~~'):
                with self.subTest(marker=marker, fence=fence):
                    indent = ' ' * content_indent
                    text = (marker + 'Example:\n' + indent + fence + '\n'
                            + indent + '    ' + fence + '\n'
                            + indent + '- AC-8: still code\n'
                            + indent + '   ' + fence + '\n- AC-1: real\n')
                    self.assertEqual(['- AC-1: real'], pack._acceptance(text))
        self.assertEqual(['- AC-1: real'], pack._acceptance(
            '- ```\n  - AC-8: code\n  ```\n- AC-1: real\n'))
        # A list container ending also ends an unclosed fence within it.
        self.assertEqual(['- AC-1: real'], pack._acceptance(
            '- Example:\n  ```\n  - AC-8: code\n- AC-1: real\n'))

    def test_acceptance_heading_scope_ends_at_same_or_parent_level(self):
        for following in ('## Notes', '# Notes'):
            with self.subTest(following=following):
                self.assertEqual(['- works offline', '- keeps data'], pack._acceptance(
                    '## Acceptance criteria\n- works offline\n### Details\n- keeps data\n'
                    + following + '\n- unresolved question\n'))

    def test_only_placeholder_criterion_is_excluded(self):
        for empty in ('- AC-01: ...', '- [ ] AC-01: ...',
                      '| AC-01: ... | build / evaluate |',
                      '| AC-01 | ... | build / evaluate |'):
            with self.subTest(empty=empty):
                self.assertEqual([], pack._acceptance('## Acceptance criteria\n' + empty))
        for actual in ('- AC-01: Show ... while loading', '- AC-01: ... then show results',
                       '- AC-01: ... | fallback is available',
                       '| AC-01: Display the literal ... | build / evaluate |',
                       '| AC-01 | ... then show results | build / evaluate |'):
            with self.subTest(actual=actual):
                self.assertEqual([actual.strip('|').strip()], pack._acceptance(actual))

    def test_seed_template_excludes_unresolved_list_and_requires_filled_criterion(self):
        empty = seed_template()
        self.assertEqual([], pack._acceptance(empty))
        filled = empty.replace('| AC-01: ... |', '| AC-01: 로그인 실패 시 오류 문구를 표시한다 |')
        filled = filled.replace('## 미결 사항\n- ...', '## 미결 사항\n- 다국어 문구 확정 여부')
        expected = next(line.strip('|').strip() for line in filled.splitlines()
                        if line.startswith('| AC-01:'))
        self.assertEqual([expected], pack._acceptance(filled))

    def test_noncriteria_only_requests_are_schema_blocked_without_provider(self):
        requests = {
            'comment': '<!--\n- AC-1: template example, delete me\n-->\n',
            'header': '| AC-ID | Criterion |\n|---|---|\n',
            'fence': '```\n    ```\n- AC-8: still code\n```\n',
            'placeholder': '| AC-01: ... | build / evaluate |\n',
            'seed': seed_template(),
        }
        for name, request in requests.items():
            with self.subTest(name=name):
                case = self.fixture(request)
                with patch.object(cli, 'run_provider_stage') as provider:
                    rc, result = case.invoke(self.pack_args(case))
                self.assertEqual(2, rc, result)
                self.assertEqual(['PACKET_SCHEMA_INVALID'], result['errors'])
                provider.assert_not_called()

    def test_real_criteria_survive_public_pack(self):
        filled = seed_template().replace('| AC-01: ... |', '| AC-01: 로그인 실패 시 오류 문구를 표시한다 |')
        filled = filled.replace('## 미결 사항\n- ...', '## 미결 사항\n- 다국어 문구 확정 여부')
        expected_seed = next(line.strip('|').strip() for line in filled.splitlines()
                             if line.startswith('| AC-01:'))
        requests = (
            ('```x``` is inline\n- AC-2: second\n', ['- AC-2: second']),
            ('| AC-ID | Criterion |\n|---|---|\n| AC-1 | Login succeeds |\n',
             ['AC-1 | Login succeeds']),
            ('- AC-1: ... then show results\n', ['- AC-1: ... then show results']),
            (filled, [expected_seed]),
        )
        for request, expected in requests:
            with self.subTest(request=request):
                case = self.fixture(request)
                with patch.object(cli, 'run_provider_stage') as provider:
                    rc, result = case.invoke(self.pack_args(case))
                self.assertEqual(0, rc, result)
                provider.assert_not_called()
                packet = cli._load(str(case.packet_dir / 'packet.json'))
                self.assertEqual(expected, packet['request']['acceptance_refs'])
                self.assertEqual(expected, packet['request']['acceptance_criteria'])


if __name__ == '__main__':
    unittest.main()
