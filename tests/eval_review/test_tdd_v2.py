"""Accepted PR-6 review boundaries: inline-code, local state, and XCTest identity."""
import json
import shlex
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_tdd_check as fixtures
from hb_eval_review import tdd_observation
from hb_eval_review.gate import generate_gate


class TddRevisionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.TddCheckTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_inline_shell_or_interpreter_cannot_forge_runner_report(self):
        # This was an actual assertion report forgery at 269cd29; no test body runs.
        failure = '<failure type="AssertionError">AssertionError</failure>'
        for phase in ('red', 'green'):
            xml = '<testsuite><testcase file="test_behavior.py" classname="test_behavior" name="test_behavior">'
            xml += failure if phase == 'red' else ''
            xml += '</testcase></testsuite>'
            script = 'f="${1#--junitxml=}"; printf %s ' + shlex.quote(xml) + ' > "$f"; exit ' + ('1' if phase == 'red' else '0')
            command = shlex.join(['bash', '-c', script, 'pytest'])
            with self.subTest(forged_phase=phase), patch.object(
                    tdd_observation, 'run_gate_command', wraps=tdd_observation.run_gate_command) as launch:
                result, payload = self.case.call(phase, command=command)
                self.assertEqual(2, result, payload)
                self.assertIn('TDD_COMMAND_INVALID', payload['errors'])
                launch.assert_not_called()
        self.assertEqual('value = 1\n', (self.case.repo / 'app.py').read_text())
        # Every specified inline form fails before repository or baseline checks.
        commands = [('sh', '-c'), ('bash', '-lc'), ('zsh', '-c'), ('dash', '-c'), ('ksh', '-c'),
                    ('python3', '-c'), (sys.executable, '-c'), ('node', '-e'), ('node', '-p'),
                    ('node', '--eval'), ('node', '--print')]
        for prefix in commands:
            for phase in ('red', 'green'):
                with self.subTest(prefix=prefix, phase=phase), patch.object(tdd_observation, 'run_gate_command') as launch:
                    result, payload = self.case.call(phase, command=shlex.join([*prefix, '0', 'pytest']))
                    self.assertEqual(2, result, payload)
                    self.assertIn('TDD_COMMAND_INVALID', payload['errors'])
                    launch.assert_not_called()
        for argv in ([sys.executable, '-m', 'pytest', '-c', 'pytest.ini'],
                     [sys.executable, '-Werror::ResourceWarning', '-m', 'pytest'],
                     ['npm', 'test', '--', '--testPathPattern', 'behavior'],
                     ['./gradlew', 'testDebugUnitTest', '--tests', 'example.Behavior'],
                     ['xcodebuild', 'test', '-only-testing:App/Behavior']):
            with self.subTest(documented_command=argv):
                parser = getattr(tdd_observation, '_command_argv', tdd_observation._argv)
                self.assertEqual(argv, parser(shlex.join(argv)))

    def test_deleting_tdd_check_state_is_detected_or_documented(self):
        self.case.red()
        self.case.test_file.write_text('import app\nassert app.value >= 2\n')
        self.case.fix()
        result, payload = self.case.call('green')
        self.assertEqual(2, result)
        self.assertIn('TDD_TEST_IDENTITY_CHANGED', payload['errors'])
        # Accepted S3 minimum: local state deletion resets the baseline. This is
        # a documented limit, not a claim that a local digest authenticates history.
        shutil.rmtree(self.case.out / 'eval-review/tdd-check')
        (self.case.out / 'tdd-test-design-result.json').unlink()
        (self.case.repo / 'app.py').write_text('value = 1\n')
        self.case.red()
        (self.case.repo / 'app.py').write_text('value = 3\n')
        result, payload = self.case.call('green')
        self.assertEqual(0, result, payload)
        gate = generate_gate(self.case.repo, [shlex.join([sys.executable, '-c', 'print("ok")'])],
                             self.case.out / 'eval-review/gate-result.json', issue_type='feature')
        self.assertEqual('PASS', gate['status'])
        for relative in ('README.md', 'BE/commands/shared/tdd.md', 'CM/commands/shared/tdd.md',
                         'FE/commands/shared/tdd.md', 'CHAT/commands/shared/tdd.md',
                         'AOS/commands/shared/tdd.md', 'IOS/commands/shared/tdd.md'):
            text = (fixtures.ROOT / relative).read_text()
            with self.subTest(document=relative):
                self.assertIn('상태 디렉터리 삭제', text)
                self.assertIn('초기화', text)
                self.assertIn('재계산', text)

    def test_interpreter_option_values_cannot_hide_inline_code(self):
        # Unknown option arity must not turn its value into a trusted script
        # boundary and hide a later evaluator. Wrappers must not hide argv either.
        invocations = [
            ['node', '--input-type', 'module', '-e', '0', 'pytest'],
            ['node', '--unhandled-rejections', 'strict', '--eval', '0', 'pytest'],
            ['node', '--stack-trace-limit', '20', '-p', '0', 'pytest'],
            ['node', '--future-runtime-option', 'value', '--print', '0', 'pytest'],
            ['node', '--title', '--', '-e', '0', 'pytest'],
            ['node', '--future-runtime-option', '--', '--eval', '0', 'pytest'],
            ['zsh', '--emulate', 'sh', '-c', 'exit 1', 'pytest'],
            ['bash', '--future-shell-option', 'value', '-c', 'exit 1', 'pytest'],
            ['python3', '--future-interpreter-option', 'value', '-c', 'pass', 'pytest'],
            ['python3', '-Q', 'future-value', '-c', 'pass', 'pytest'],
            ['env', 'MODE=test', 'node', '--input-type', 'module', '-e', '0', 'pytest'],
            ['npx', 'node', '--input-type', 'module', '-e', '0', 'pytest'],
            ['npm', 'exec', '--', 'node', '--input-type', 'module', '--eval', '0', 'pytest'],
            ['env', '-S', 'node --input-type module -e 0', 'pytest'],
            ['env', '--split-string=node --input-type module -e 0', 'pytest'],
            ['npx', '--call', 'node -e 0', 'pytest'],
            ['npx', '-c', 'node -e 0', 'pytest'],
            ['npm', 'exec', '--call=node -e 0'],
            ['npm', 'exec', '-c', 'node -e 0'],
        ]
        for argv in invocations:
            for phase in ('red', 'green'):
                with self.subTest(argv=argv, phase=phase), patch.object(
                        tdd_observation, 'run_gate_command') as launch:
                    result, payload = self.case.call(phase, command=shlex.join(argv))
                    self.assertEqual(2, result, payload)
                    self.assertIn('TDD_COMMAND_INVALID', payload['errors'])
                    launch.assert_not_called()
        controls = [
            ['node', 'scripts/test-runner.js', '-e', 'script-owned-argument', 'pytest'],
            ['node', '--', 'scripts/test-runner.js', '-e', 'script-owned-argument'],
            ['node', '--require', 'setup.cjs', 'scripts/test-runner.js', '-p', 'argument'],
            ['node', '--title=worker', 'scripts/test-runner.js', '-p', 'argument'],
            ['bash', '--noprofile', 'scripts/tests.sh', '-c', 'script-owned-argument'],
            ['python3', '-m', 'pytest', '-c', 'pytest.ini'],
            ['python3', '-W', 'error::ResourceWarning', '-m', 'pytest', '-c', 'pytest.ini'],
            ['npm', 'test', '--', '-c', 'jest.config.js'],
            ['npm', 'test', '--', '-t', 'exec', '-c', 'jest.config.js'],
            ['npm', 'exec', '--', 'jest', '-c', 'jest.config.js'],
            ['npx', '--', 'jest', '-c', 'jest.config.js'],
        ]
        for argv in controls:
            with self.subTest(repository_command=argv):
                self.assertEqual(argv, tdd_observation._command_argv(shlex.join(argv)))

    def test_xcresult_target_named_class_does_not_bind_other_classes(self):
        test = self.case.repo / 'MyAppTests.swift'
        case = {'id': 'MyAppTests/OtherTests/testFoo()', 'file': None,
                'classname': 'OtherTests', 'outcome': 'FAIL', 'assertion': True}
        self.assertFalse(tdd_observation._bound_case(case, test, self.case.repo,
                                                   'class MyAppTests: XCTestCase {}'))
        self.assertTrue(tdd_observation._bound_case(case, self.case.repo / 'OtherTests.swift', self.case.repo,
                                                  'class OtherTests: XCTestCase {}'))


if __name__ == '__main__':
    unittest.main()
