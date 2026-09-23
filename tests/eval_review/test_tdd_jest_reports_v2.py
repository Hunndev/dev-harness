"""B2: replay supplied primary Jest reports through the public TDD CLI.

These tests execute no Jest or product code. Only the shared runner is mocked;
the report adapter, selected-ID binding, immutable baseline and CLI run normally.
Fixture provenance lists source hashes and the single portable path substitution.
"""
import hashlib
import json
import shlex
import unittest
from pathlib import Path
from unittest.mock import patch

import test_tdd_check as fixtures
from hb_eval_review.tdd_reports import prepare_report

REPORTS = Path(__file__).parent / 'fixtures' / 'jest-v2'


class JestPrimaryReportTests(unittest.TestCase):
    def replay(self, version, name, *, argv_extra=(), transform=None,
               require_location_flag=False, root_prefix=None):
        fixture = fixtures.TddCheckTests(methodName='runTest')
        if root_prefix is None:
            fixture.setUp()
        else:
            temporary_directory = fixtures.tempfile.TemporaryDirectory
            with patch.object(fixtures.tempfile, 'TemporaryDirectory',
                              side_effect=lambda: temporary_directory(prefix=root_prefix)):
                fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        raw = (REPORTS / version / name).read_text()
        data = json.loads(raw.replace('/__jest_fixture__', str(fixture.repo / 'tests')))
        suite = data['testResults'][0]
        source = Path(suite['name'])
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes((REPORTS / 'source' / source.name).read_bytes())
        if transform:
            transform(data)
        relative = source.relative_to(fixture.repo).as_posix()
        calls = []

        def run(command, repo, *, track, capture_output=False):
            argv = shlex.split(command)
            calls.append(argv)
            self.assertEqual(fixture.repo, repo)
            self.assertTrue(capture_output)
            if require_location_flag:
                self.assertIn('--testLocationInResults', argv)
            self.assertNotIn('--testEnvironment', argv)
            # An explicit unsupported testRunner input is inspected, never
            # replaced with a preferred runner by the report adapter.
            self.assertEqual(list(argv_extra), argv[3:3 + len(argv_extra)])
            report = Path(next(x.split('=', 1)[1] for x in argv if x.startswith('--outputFile=')))
            report.write_text(json.dumps(data), encoding='utf-8')
            output = 'FAIL ' + relative
            return {'name': 'npx', 'command': argv, 'exit_code': 1, 'duration_ms': 1,
                    'stdout': output, 'stderr': '', 'stdout_tail': output, 'stderr_tail': '',
                    'stdout_sha256': hashlib.sha256(output.encode()).hexdigest(), 'execution_error': None}

        command = shlex.join(['npx', 'jest', relative] + list(argv_extra))
        with patch('hb_eval_review.tdd_observation.run_gate_command', side_effect=run):
            rc, payload = fixture.call('red', '--test-file', relative, command=command)
        document = fixture.out / 'tdd-test-design-result.json'
        if rc == 0:
            observed = json.loads(document.read_text())['observed']
            self.assertEqual([relative + '::' + suite['assertionResults'][0]['fullName']], observed['selected_tests'])
            self.assertEqual(1, observed['executed'])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), observed['test_file_sha256'])
        else:
            self.assertFalse(document.exists())
        return rc, payload, calls

    def test_jest_async_body_assertion_red_is_valid(self):
        for version, name in (('jest27', 'async.json'), ('jest29', 'async.json'),
                              ('jest27', 'async-loc.json'), ('jest29', 'async-loc.json'),
                              ('jest29-tsjest', 'async.json')):
            with self.subTest(version=version, report=name):
                rc, payload, _ = self.replay(version, name)
                self.assertEqual(0, rc, payload)

    def test_jest_deep_helper_assertion_red_is_valid(self):
        for version in ('jest27', 'jest29'):
            with self.subTest(version=version):
                rc, payload, _ = self.replay(version, 'deep.json')
                self.assertEqual(0, rc, payload)

    def test_jest_async_report_accepts_parenthesized_repository_path(self):
        for prefix in ('copy (archive)-', 'copy (archive (v2))-'):
            for version in ('jest27', 'jest29', 'jest29-tsjest'):
                with self.subTest(prefix=prefix, version=version):
                    rc, payload, _ = self.replay(version, 'async.json', root_prefix=prefix)
                    self.assertEqual(0, rc, payload)

    def test_jest_hook_failure_red_is_rejected(self):
        for version in ('jest27', 'jest29'):
            with self.subTest(version=version):
                rc, payload, _ = self.replay(version, 'hook.json')
                self.assertEqual(2, rc, payload)
                self.assertIn('TDD_RED_REASON_INVALID', payload['errors'])

    def test_jest_synchronous_body_assertion_red_remains_valid(self):
        for version in ('jest27', 'jest29', 'jest29-tsjest'):
            with self.subTest(version=version):
                rc, payload, _ = self.replay(version, 'body.json')
                self.assertEqual(0, rc, payload)

    def test_jest_async_hook_without_phase_marker_is_explicit_d2_tradeoff(self):
        # D2 accepts this known ambiguity: a declaration location cannot prove
        # that an earlier helper belonged to a hook instead of the test body.
        for version, name in (('jest27', 'asynchook-loc.json'),
                              ('jest29', 'asynchook-loc.json'), ('jest29', 'asynchook.json')):
            with self.subTest(version=version, report=name):
                rc, payload, _ = self.replay(version, name)
                self.assertEqual(0, rc, payload)

    def test_jest_report_location_flag_is_runner_owned(self):
        rc, payload, _ = self.replay('jest29', 'body.json', require_location_flag=True)
        self.assertEqual(0, rc, payload)
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            for option in ('--testLocationInResults=false', '--no-testLocationInResults'):
                with self.subTest(option=option):
                    with self.assertRaisesRegex(ValueError, '^TDD_REPORT_PATH_INVALID$'):
                        prepare_report(['jest', 'tests/behavior.test.js', option], Path(directory))

    def test_jest_unsupported_phase_configuration_has_specific_code(self):
        options = [('--noStackTrace',), ('--noStackTrace=true',),
                   ('--testRunner', 'jest-jasmine2'), ('--testRunner=jest-jasmine2',),
                   ('--config', '{"testRunner":"jest-jasmine2"}'),
                   ('--config', '{"noStackTrace":true}')]
        for extra in options:
            with self.subTest(options=extra):
                rc, payload, calls = self.replay('jest29', 'body.json', argv_extra=extra)
                self.assertEqual(2, rc, payload)
                self.assertIn('TDD_JEST_PHASE_UNSUPPORTED', payload['errors'])
                self.assertEqual([], calls)

    def test_jest_missing_stack_has_specific_unsupported_code(self):
        for frame in ('', '\n    at <anonymous>', '\n    at <anonymous>:1:1',
                      '\n    at Object.<anonymous> (<anonymous>:1:1)'):
            with self.subTest(frame=frame):
                def trim(data):
                    test = data['testResults'][0]['assertionResults'][0]
                    test['failureMessages'] = ['Error: expect(received).toBe(expected)\nExpected: 2\nReceived: 1' + frame]
                rc, payload, _ = self.replay('jest29', 'async.json', transform=trim)
                self.assertEqual(2, rc, payload)
                self.assertIn('TDD_JEST_PHASE_UNSUPPORTED', payload['errors'])

    def test_jest_jasmine_stack_has_specific_unsupported_code(self):
        def jasmine(data):
            test = data['testResults'][0]['assertionResults'][0]
            test['failureMessages'][0] += '\n    at jasmineAsyncInstall (/cache/node_modules/jest-jasmine2/build/jasmineAsyncInstall.js:106:17)'
        rc, payload, _ = self.replay('jest29', 'async.json', transform=jasmine)
        self.assertEqual(2, rc, payload)
        self.assertIn('TDD_JEST_PHASE_UNSUPPORTED', payload['errors'])


if __name__ == '__main__':
    unittest.main()
