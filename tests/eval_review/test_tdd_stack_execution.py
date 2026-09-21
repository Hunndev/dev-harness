"""Public CLI wiring with primary-format report fixtures, not native SDK runs.

The shared runner boundary is mocked; report preparation, parsing, source-file
binding, baseline persistence and schema validation are exercised end to end.
"""
import hashlib
import json
import re
import shlex
import unittest
from pathlib import Path
from unittest.mock import patch

import test_tdd_check as fixtures
from hb_eval_review.schema_validation import validate_schema


class TddStackExecutionTests(unittest.TestCase):
    def fixture(self, source_path, source):
        # Composition deliberately avoids collecting TddCheckTests a second time.
        fixture = fixtures.TddCheckTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        path = fixture.repo / source_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding='utf-8')
        return fixture

    def row(self, argv, exit_code, stdout='', stderr=''):
        return {
            'name': Path(argv[0]).name, 'command': argv, 'exit_code': exit_code,
            'duration_ms': 1, 'stdout': stdout, 'stderr': stderr,
            'stdout_tail': stdout[-65536:], 'stderr_tail': stderr[-65536:],
            'stdout_sha256': hashlib.sha256(stdout.encode()).hexdigest(),
        }

    def transition(self, fixture, source_path, command, phase, selected_id):
        result, payload = fixture.call('red', '--test-file', source_path, command=command)
        self.assertEqual(0, result, payload)
        red = json.loads((fixture.out / 'tdd-test-design-result.json').read_text())
        self.assertEqual([selected_id], red['observed']['selected_tests'])
        self.assertEqual(1, red['observed']['executed'])
        self.assertEqual(1, red['observed']['exit_code'])
        self.assertEqual(source_path, red['observed']['test_file'])
        self.assertEqual('1.2', red['schema_version'])
        self.assertEqual([], validate_schema(red, 'tdd-test-design-result.schema.json'))
        phase['value'] = 'green'
        fixture.fix()
        result, payload = fixture.call('green', '--test-file', source_path, command=command)
        self.assertEqual(0, result, payload)
        green = json.loads((fixture.out / 'tdd-sensitivity-result.json').read_text())
        self.assertEqual([selected_id], green['observed']['selected_tests'])
        self.assertEqual(1, green['observed']['executed'])
        self.assertEqual(0, green['observed']['exit_code'])
        self.assertEqual(red['observed']['test_file_sha256'], green['observed']['test_file_sha256'])
        self.assertEqual(red['observed']['run_id'], green['observed']['run_id'])
        self.assertEqual(('FAIL', 'PASS'), (green['red_outcome'], green['green_outcome']))
        self.assertEqual('1.2', green['schema_version'])
        self.assertEqual([], validate_schema(green, 'tdd-sensitivity-result.schema.json'))

    def test_jest_named_and_positional_selectors_execute_through_cli_reports(self):
        source_path = 'tests/behavior.test.ts'
        commands = [
            ['npm', 'test', '--', '--testPathPattern', 'behavior'],
            ['npx', 'jest', source_path],
        ]
        for requested in commands:
            with self.subTest(selector=requested):
                fixture = self.fixture(source_path, "test('returns value', () => expect(value()).toBe(2));\n")
                phase, seen, paths = {'value': 'red'}, [], []

                def run(command, repo, *, track, capture_output=False):
                    argv = shlex.split(command)
                    self.assertEqual(fixture.repo, repo)
                    self.assertEqual('feature', track)
                    self.assertTrue(capture_output)
                    self.assertEqual(requested, argv[:len(requested)])
                    self.assertIn('--json', argv)
                    report = Path(next(x.split('=', 1)[1] for x in argv if x.startswith('--outputFile=')))
                    self.assertNotIn(fixture.repo, report.parents)
                    self.assertFalse(report.exists())
                    failing = phase['value'] == 'red'
                    report.write_text(json.dumps({
                        'numFailedTestSuites': int(failing), 'numPassedTestSuites': int(not failing),
                        'numFailedTests': int(failing), 'numPassedTests': int(not failing),
                        'numPendingTests': 0, 'numTodoTests': 0, 'numTotalTests': 1,
                        'success': not failing, 'testResults': [{
                            'name': str(fixture.repo / source_path),
                            'status': 'failed' if failing else 'passed', 'message': '',
                            'assertionResults': [{
                                'ancestorTitles': ['Behavior'], 'title': 'returns value',
                                'fullName': 'Behavior returns value', 'duration': 1,
                                'status': 'failed' if failing else 'passed',
                                'failureMessages': [
                                    'Error: expect(received).toBe(expected)\nExpected: 2\nReceived: 1\n'
                                    '    at _callCircusTest (/cache/node_modules/jest-circus/build/run.js:218:40)'
                                ] if failing else [],
                            }],
                        }],
                    }), encoding='utf-8')
                    seen.append(argv)
                    paths.append(report)
                    return self.row(argv, int(failing), 'FAIL tests/behavior.test.ts' if failing else 'PASS tests/behavior.test.ts')

                with patch('hb_eval_review.tdd_observation.run_gate_command', side_effect=run):
                    self.transition(fixture, source_path, shlex.join(requested), phase,
                                    source_path + '::Behavior returns value')
                self.assertEqual(2, len(seen))
                self.assertNotEqual(paths[0], paths[1])
                self.assertTrue(all(not path.exists() for path in paths))

    def test_gradle_fqcn_selector_and_build_failed_assertion_are_valid_cli_red(self):
        source_path = 'app/src/test/java/example/BehaviorTests.kt'
        fixture = self.fixture(source_path, 'package example\nclass BehaviorTests { fun returnsExpectedValue() {} }\n')
        requested = ['./gradlew', ':app:testDebugUnitTest', '--tests', 'example.BehaviorTests']
        phase, seen, paths = {'value': 'red'}, [], []

        def run(command, repo, *, track, capture_output=False):
            argv = shlex.split(command)
            self.assertEqual(requested, argv[:len(requested)])
            self.assertEqual(fixture.repo, repo)
            self.assertTrue(capture_output)
            script = Path(argv[argv.index('--init-script') + 1])
            body = script.read_text()
            self.assertIn('tasks.withType(org.gradle.api.tasks.testing.Test)', body)
            self.assertIn('outputLocation.finalizeValue()', body)
            self.assertIn('--rerun-tasks', argv)
            self.assertIn('--no-build-cache', argv)
            match = re.search(r"new File\('([^']+)'", body)
            self.assertIsNotNone(match)
            report_root = Path(match.group(1))
            self.assertNotIn(fixture.repo, report_root.parents)
            self.assertFalse(report_root.exists())
            report = report_root / 'app/testDebugUnitTest/TEST-example.BehaviorTests.xml'
            report.parent.mkdir(parents=True)
            failing = phase['value'] == 'red'
            failure = '<failure message="expected: 2 but was: 1" type="java.lang.AssertionError">java.lang.AssertionError: expected: 2 but was: 1</failure>' if failing else ''
            report.write_text(
                '<testsuite name="example.BehaviorTests" tests="1" skipped="0" failures="' + str(int(failing)) + '" errors="0">'
                '<testcase name="returnsExpectedValue" classname="example.BehaviorTests" time="0.001">' + failure + '</testcase>'
                '<system-out/><system-err/></testsuite>', encoding='utf-8')
            seen.append(argv)
            paths.append(report)
            stdout = '1 test completed, 1 failed\nBUILD FAILED in 1s\n' if failing else '1 test completed\nBUILD SUCCESSFUL in 1s\n'
            return self.row(argv, int(failing), stdout)

        with patch('hb_eval_review.tdd_observation.run_gate_command', side_effect=run):
            self.transition(fixture, source_path, shlex.join(requested), phase,
                            'example.BehaviorTests::returnsExpectedValue')
        self.assertEqual(2, len(seen))
        self.assertNotEqual(paths[0], paths[1])
        self.assertTrue(all(not path.exists() for path in paths))
        self.assertIn('BUILD FAILED', (fixture.out / 'tdd-baseline-log.txt').read_text())

    def test_xcode_only_testing_reads_both_complete_reports_and_binds_swift_class(self):
        source_path = 'AppTests/BehaviorTests.swift'
        fixture = self.fixture(source_path, 'import XCTest\nfinal class BehaviorTests: XCTestCase { func testValue() {} }\n')
        requested = ['xcodebuild', 'test', '-scheme', 'App', '-only-testing:AppTests/BehaviorTests/testValue']
        selected = 'AppTests/BehaviorTests/testValue()'
        phase, seen, bundles = {'value': 'red'}, [], []

        def run(command, repo, *, track, capture_output=False):
            argv = shlex.split(command)
            self.assertEqual(fixture.repo, repo)
            self.assertTrue(capture_output)
            failing = phase['value'] == 'red'
            seen.append(argv)
            if argv[0] == 'xcodebuild':
                self.assertEqual(requested, argv[:len(requested)])
                bundle = Path(argv[argv.index('-resultBundlePath') + 1])
                self.assertNotIn(fixture.repo, bundle.parents)
                self.assertFalse(bundle.exists())
                bundle.mkdir()
                bundles.append(bundle)
                return self.row(argv, int(failing), '** TEST FAILED **' if failing else '** TEST SUCCEEDED **')
            self.assertEqual(['xcrun', 'xcresulttool', 'get', 'test-results'], argv[:4])
            self.assertEqual(str(bundles[-1]), argv[argv.index('--path') + 1])
            self.assertIn('--compact', argv)
            status = 'Failed' if failing else 'Passed'
            if argv[4] == 'tests':
                data = {'testPlanConfigurations': [], 'devices': [], 'testNodes': [{
                    'nodeType': 'Unit test bundle', 'name': 'AppTests', 'children': [{
                        'nodeType': 'Test Suite', 'name': 'BehaviorTests', 'children': [{
                            'nodeType': 'Test Case', 'name': 'testValue()',
                            'nodeIdentifier': selected, 'result': status,
                            'children': [{'nodeType': 'Test Case Run', 'name': 'Test run', 'result': status}],
                        }],
                    }],
                }]}
            else:
                self.assertEqual('summary', argv[4])
                data = {
                    'title': 'Test App', 'environmentDescription': 'Primary-format fixture ' + ('x' * 70000),
                    'topInsights': [], 'result': status, 'totalTestCount': 1,
                    'passedTests': int(not failing), 'failedTests': int(failing), 'skippedTests': 0,
                    'expectedFailures': 0, 'statistics': [], 'devicesAndConfigurations': [],
                    'testFailures': [{
                        'testName': 'testValue()', 'targetName': 'AppTests', 'testIdentifier': 123,
                        'testIdentifierString': 'BehaviorTests/testValue()',
                        'failureText': 'XCTAssertEqual failed: (1) is not equal to (2)',
                    }] if failing else [],
                }
            return self.row(argv, 0, json.dumps(data))

        with patch('hb_eval_review.tdd_observation.run_gate_command', side_effect=run):
            self.transition(fixture, source_path, shlex.join(requested), phase, selected)
        self.assertEqual(['xcodebuild', 'xcrun', 'xcrun'] * 2, [argv[0] for argv in seen])
        self.assertEqual(['tests', 'summary'] * 2, [argv[4] for argv in seen if argv[0] == 'xcrun'])
        self.assertNotEqual(bundles[0], bundles[1])
        self.assertTrue(all(not path.exists() for path in bundles))


if __name__ == '__main__':
    unittest.main()
