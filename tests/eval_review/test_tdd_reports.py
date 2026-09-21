import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'SHARED' / 'runtime'))
from hb_eval_review.tdd_reports import prepare_report, parse_report

JEST_BODY_FRAME = '    at _callCircusTest (/cache/node_modules/jest-circus/build/run.js:218:40)'
JEST_HOOK_FRAME = '    at _callCircusHook (/cache/node_modules/jest-circus/build/run.js:181:40)'
JEST_ASSERTION = 'Error: expect(received).toBe(expected)\nExpected: 2\nReceived: 1'
JEST_BODY_FAILURE = JEST_ASSERTION + '\n' + JEST_BODY_FRAME


class TddReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.reports = self.root / 'runner'
        self.reports.mkdir()

    def plan(self, argv):
        return prepare_report(argv, self.reports)

    def write_junit(self, plan, body):
        target = plan['report_path']
        if plan['kind'] == 'gradle':
            target = target / 'app' / 'test' / 'TEST-Behavior.xml'
            target.parent.mkdir(parents=True)
        target.write_text(body, encoding='utf-8')

    def test_pytest_report_injection_preserves_path_and_python_module_selector(self):
        for argv in (['pytest', 'tests/test_behavior.py::test_value'],
                     ['python3', '-m', 'pytest', 'tests/test_behavior.py', '-k', 'value']):
            with self.subTest(argv=argv):
                plan = self.plan(argv)
                self.assertEqual('pytest', plan['kind'])
                self.assertEqual(argv, plan['argv'][:len(argv)])
                self.assertIn('--junitxml=' + str(plan['report_path']), plan['argv'])
                self.assertIn('junit_family=xunit1', plan['argv'])
                self.assertFalse(plan['report_path'].exists())

    def test_jest_report_injection_preserves_named_and_positional_selectors(self):
        commands = [
            ['npx', 'jest', '--testPathPattern', 'behavior'],
            ['npm', 'test', '--', 'tests/behavior.test.ts'],
            ['npm', 'run', 'unit', '--testPathPattern=behavior'],
            ['yarn', 'test', 'tests/behavior.test.ts'],
            ['pnpm', 'test', '--testPathPattern=behavior'],
        ]
        for argv in commands:
            with self.subTest(argv=argv):
                plan = self.plan(argv)
                self.assertEqual('jest', plan['kind'])
                self.assertIn('--json', plan['argv'])
                self.assertIn('--outputFile=' + str(plan['report_path']), plan['argv'])
                if argv[0] == 'npm':
                    self.assertIn('--', plan['argv'])

    def test_user_report_overrides_rejected_before_execution(self):
        commands = [
            ['pytest', '--junitxml', '/tmp/stale.xml'],
            ['pytest', '--junit-xml=stale.xml'],
            ['pytest', '-o', 'junit_family=xunit2'],
            ['pytest', '--override-ini=junit_suite_name=other'],
            ['jest', '--outputFile=stale.json'],
            ['npm', 'test', '--', '--json'],
            ['jest', '--reporters', '/tmp/custom.js'],
            ['./gradlew', 'test', '-I', '/tmp/override.gradle'],
            ['./gradlew', 'test', '--init-script=/tmp/override.gradle'],
            ['xcodebuild', 'test', '-resultBundlePath', '/tmp/stale.xcresult'],
            ['xcodebuild', 'test', '-resultBundlePath=/tmp/stale.xcresult'],
        ]
        for argv in commands:
            with self.subTest(argv=argv):
                with self.assertRaisesRegex(ValueError, '^TDD_REPORT_PATH_INVALID$'):
                    self.plan(argv)

    def test_gradle_reports_are_runner_owned_and_force_execution(self):
        argv = ['./gradlew', ':app:testDebugUnitTest', '--tests', 'com.example.BehaviorTest']
        plan = self.plan(argv)
        self.assertEqual('gradle', plan['kind'])
        self.assertEqual(argv, plan['argv'][:len(argv)])
        script = Path(plan['argv'][plan['argv'].index('--init-script') + 1])
        body = script.read_text()
        self.assertIn(str(self.reports), body)
        self.assertIn('junitXml', body)
        self.assertIn('outputLocation', body)
        self.assertIn('--rerun-tasks', plan['argv'])
        self.assertIn('--no-build-cache', plan['argv'])
        self.assertFalse(plan['report_path'].exists())

    def test_gradle_lowercase_info_flag_is_not_an_init_script_override(self):
        argv = ['./gradlew', 'test', '-i', '--tests', 'com.example.BehaviorTest']
        plan = self.plan(argv)
        self.assertEqual(argv, plan['argv'][:len(argv)])
        self.assertIn('--init-script', plan['argv'])

    def test_junit_assertion_fixture_runtime_skip_and_pass_are_distinct(self):
        plan = self.plan(['pytest', 'tests/test_behavior.py'])
        self.write_junit(plan, '''<testsuites><testsuite tests="5">
          <testcase file="tests/test_behavior.py" classname="tests.test_behavior" name="test_assertion"><failure message="assert 1 == 2">AssertionError</failure></testcase>
          <testcase file="tests/test_behavior.py" classname="tests.test_behavior" name="test_fixture"><error message="failed on setup">AssertionError</error></testcase>
          <testcase file="tests/test_behavior.py" classname="tests.test_behavior" name="test_runtime"><failure type="ValueError">unexpected exception</failure></testcase>
          <testcase file="tests/test_behavior.py" classname="tests.test_behavior" name="test_skip"><skipped/></testcase>
          <testcase file="tests/test_behavior.py" classname="tests.test_behavior" name="test_pass"/>
        </testsuite></testsuites>''')
        cases = parse_report(plan, self.repo)
        self.assertEqual(['FAIL', 'ERROR', 'FAIL', 'SKIP', 'PASS'], [x['outcome'] for x in cases])
        self.assertEqual([True, False, False, False, False], [x['assertion'] for x in cases])
        self.assertEqual('tests/test_behavior.py::test_assertion', cases[0]['id'])
        self.assertEqual('tests/test_behavior.py', cases[0]['file'])
        self.assertEqual('tests.test_behavior', cases[0]['classname'])

    def test_junit_class_names_disambiguate_methods_with_same_name(self):
        plan = self.plan(['pytest', 'tests/test_behavior.py'])
        self.write_junit(plan, '''<testsuite>
          <testcase file="tests/test_behavior.py" classname="tests.test_behavior.One" name="test_value"/>
          <testcase file="tests/test_behavior.py" classname="tests.test_behavior.Two" name="test_value"/>
        </testsuite>''')
        cases = parse_report(plan, self.repo)
        self.assertEqual(2, len(set(case['id'] for case in cases)))

    def test_error_while_evaluating_assertion_expression_is_not_assertion_failure(self):
        plan = self.plan(['pytest', 'tests/test_behavior.py'])
        self.write_junit(plan, '''<testsuite><testcase classname="test_behavior" name="test_value">
          <failure message="'NoneType' object has no attribute 'value'">def test_value():
&gt; assert None.value == 1
E AttributeError: 'NoneType' object has no attribute 'value'
test_behavior.py:2: AttributeError</failure></testcase></testsuite>''')
        self.assertFalse(parse_report(plan, self.repo)[0]['assertion'])

    def test_terminal_assertion_controls_chained_pytest_failure(self):
        plan = self.plan(['pytest', 'test_behavior.py'])
        # Primary pytest 9 output: pytest.raises catches ValueError, then its
        # regex mismatch raises the actual terminal AssertionError.
        self.write_junit(plan, '''<testsuite><testcase file="test_behavior.py" classname="test_behavior" name="test_error_message">
<failure message="AssertionError: Regex pattern did not match.">
def test_error_message():
    with pytest.raises(ValueError, match="good"):
&gt;       raise ValueError("bad")
E       ValueError: bad

test_behavior.py:5: ValueError

During handling of the above exception, another exception occurred:

def test_error_message():
&gt;   with pytest.raises(ValueError, match="good"):
E   AssertionError: Regex pattern did not match.
E     Expected regex: 'good'
E     Actual message: 'bad'

test_behavior.py:4: AssertionError</failure></testcase></testsuite>''')
        case = parse_report(plan, self.repo)[0]
        self.assertEqual('FAIL', case['outcome'])
        self.assertTrue(case['assertion'])

    def test_terminal_runtime_error_after_caught_assertion_is_not_assertion_failure(self):
        plan = self.plan(['pytest', 'test_behavior.py'])
        self.write_junit(plan, '''<testsuite><testcase file="test_behavior.py" classname="test_behavior" name="test_error_message">
<failure message="RuntimeError: crash after caught assertion">
E AssertionError: assert 1 == 2
test_behavior.py:2: AssertionError

During handling of the above exception, another exception occurred:

E RuntimeError: crash after caught assertion
test_behavior.py:4: RuntimeError</failure></testcase></testsuite>''')
        self.assertFalse(parse_report(plan, self.repo)[0]['assertion'])

    def test_junit_assertion_type_can_wrap_a_runtime_cause(self):
        plan = self.plan(['./gradlew', 'test', '--tests', 'example.BehaviorTests'])
        self.write_junit(plan, '''<testsuite><testcase classname="example.BehaviorTests" name="testExpectedFailure">
<failure type="org.opentest4j.AssertionFailedError" message="Unexpected exception type thrown">
org.opentest4j.AssertionFailedError: expected IllegalArgumentException
Caused by: java.lang.IllegalStateException: bad value</failure></testcase></testsuite>''')
        self.assertTrue(parse_report(plan, self.repo)[0]['assertion'])

    def test_gradle_xml_reports_bind_class_and_assertion_type(self):
        plan = self.plan(['./gradlew', 'test', '--tests', 'com.example.BehaviorTest'])
        self.write_junit(plan, '''<testsuite name="com.example.BehaviorTest">
          <testcase classname="com.example.BehaviorTest" name="returnsExpectedValue"><failure type="org.opentest4j.AssertionFailedError">expected 2, got 1</failure></testcase>
        </testsuite>''')
        cases = parse_report(plan, self.repo)
        self.assertEqual('com.example.BehaviorTest::returnsExpectedValue', cases[0]['id'])
        self.assertIsNone(cases[0]['file'])
        self.assertTrue(cases[0]['assertion'])

    def test_no_stale_gradle_repo_reports_are_used(self):
        stale = self.repo / 'build/test-results/test/TEST-Behavior.xml'
        stale.parent.mkdir(parents=True)
        stale.write_text('<testsuite><testcase classname="Behavior" name="passes"/></testsuite>')
        plan = self.plan(['./gradlew', 'test', '--tests', 'Behavior'])
        with self.assertRaisesRegex(ValueError, '^TDD_RED_REASON_INVALID$'):
            parse_report(plan, self.repo)

    def test_jest_json_executed_cases_and_assertions(self):
        plan = self.plan(['npm', 'test', '--', '--testPathPattern', 'behavior'])
        plan['report_path'].write_text(json.dumps({'testResults': [{
            'name': str(self.repo / 'tests/behavior.test.ts'), 'status': 'failed',
            'assertionResults': [
                {'fullName': 'Behavior returns value', 'title': 'returns value', 'ancestorTitles': ['Behavior'],
                 'status': 'failed', 'failureMessages': [JEST_BODY_FAILURE]},
                {'fullName': 'Behavior runtime', 'title': 'runtime', 'ancestorTitles': ['Behavior'],
                 'status': 'failed', 'failureMessages': ['TypeError: undefined is not a function']},
                {'fullName': 'Behavior skipped', 'title': 'skipped', 'status': 'pending', 'failureMessages': []},
                {'fullName': 'Behavior passing', 'title': 'passing', 'status': 'passed', 'failureMessages': []},
            ]}]}))
        cases = parse_report(plan, self.repo)
        self.assertEqual(['FAIL', 'FAIL', 'SKIP', 'PASS'], [x['outcome'] for x in cases])
        self.assertEqual([True, False, False, False], [x['assertion'] for x in cases])
        self.assertEqual('tests/behavior.test.ts::Behavior returns value', cases[0]['id'])
        self.assertEqual('Behavior', cases[0]['classname'])

    def test_jest_suite_error_cannot_be_hidden_by_other_passed_cases(self):
        plan = self.plan(['jest', 'behavior'])
        plan['report_path'].write_text(json.dumps({'testResults': [{
            'name': str(self.repo / 'tests/behavior.test.ts'),
            'testExecError': {'message': 'Cannot find module'}, 'assertionResults': [
                {'fullName': 'passes', 'status': 'passed'}]}]}))
        cases = parse_report(plan, self.repo)
        self.assertIn('ERROR', [x['outcome'] for x in cases])

    def test_jest_empty_failed_suite_cannot_hide_beside_assertion_failure(self):
        plan = self.plan(['jest', 'behavior'])
        plan['report_path'].write_text(json.dumps({'testResults': [
            {'name': 'tests/broken.test.ts', 'status': 'failed', 'message': 'SyntaxError', 'assertionResults': []},
            {'name': 'tests/behavior.test.ts', 'status': 'failed', 'assertionResults': [
                {'fullName': 'returns value', 'status': 'failed', 'failureMessages': [JEST_BODY_FAILURE]}]},
        ]}))
        cases = parse_report(plan, self.repo)
        self.assertEqual(['ERROR', 'FAIL'], [case['outcome'] for case in cases])

    def test_jest_todo_and_runtime_exception_in_expect_expression(self):
        plan = self.plan(['jest', 'behavior'])
        plan['report_path'].write_text(json.dumps({'testResults': [{
            'name': 'tests/behavior.test.ts', 'assertionResults': [
                {'fullName': 'todo', 'status': 'todo'},
                {'fullName': 'crash', 'status': 'failed',
                 'failureMessages': ['TypeError: cannot read value\nexpect(value()).toBe(2)\n' + JEST_BODY_FRAME]},
            ]}]}))
        cases = parse_report(plan, self.repo)
        self.assertEqual('SKIP', cases[0]['outcome'])
        self.assertFalse(cases[1]['assertion'])

    def test_jest_assertion_red_requires_test_body_phase_and_rejects_hooks(self):
        messages = {
            'body': (JEST_BODY_FAILURE, True),
            'beforeEach or afterEach': (JEST_ASSERTION + '\n' + JEST_HOOK_FRAME, False),
            'hook plus body': (JEST_BODY_FAILURE + '\n' + JEST_HOOK_FRAME, False),
            'phase missing': (JEST_ASSERTION, False),
            'phase trimmed': (JEST_ASSERTION + '\n    at _callCircusTest', False),
            'name in message': (JEST_ASSERTION + '\nExpected: _callCircusTest', False),
            'user function with same name': (
                JEST_ASSERTION + '\n    at _callCircusTest (/repo/test/helper.js:1:2)', False),
            'body without assertion': ('Error: body failed\n' + JEST_BODY_FRAME, False),
            'runtime message merely mentions assert': ('Error: assert value failed\n' + JEST_BODY_FRAME, False),
        }
        for name, (message, expected) in messages.items():
            with self.subTest(phase=name):
                plan = self.plan(['jest', 'behavior'])
                plan['report_path'].write_text(json.dumps({'testResults': [{
                    'name': 'tests/behavior.test.ts', 'status': 'failed', 'assertionResults': [
                        {'fullName': 'returns value', 'status': 'failed', 'failureMessages': [message]},
                    ]}]}))
                try:
                    case = parse_report(plan, self.repo)[0]
                    self.assertEqual('FAIL', case['outcome'])
                    self.assertEqual(expected, case['assertion'])
                finally:
                    plan['report_path'].unlink()

    def test_jest_matcher_expected_exception_names_are_not_runtime_failures(self):
        plan = self.plan(['jest', 'behavior'])
        message = ('Error: expect(received).toThrow(expected)\n\n'
                   'Expected constructor: ReferenceError\nReceived constructor: TypeError\n\n'
                   'Received message: "bad"\n' + JEST_BODY_FRAME)
        plan['report_path'].write_text(json.dumps({'testResults': [{
            'name': 'tests/behavior.test.ts', 'status': 'failed', 'assertionResults': [
                {'fullName': 'rejects wrong exception', 'status': 'failed', 'failureMessages': [message]},
            ]}]}))
        self.assertTrue(parse_report(plan, self.repo)[0]['assertion'])

    def test_xcode_plan_has_runner_bundle_and_read_only_parse_commands(self):
        argv = ['xcodebuild', 'test', '-scheme', 'App', '-only-testing:AppTests/BehaviorTests/testValue']
        plan = self.plan(argv)
        self.assertEqual('xcodebuild', plan['kind'])
        self.assertEqual(argv, plan['argv'][:len(argv)])
        self.assertEqual(str(plan['report_path']), plan['argv'][plan['argv'].index('-resultBundlePath') + 1])
        self.assertEqual(2, len(plan['report_commands']))
        self.assertEqual(2, len(plan['report_json_paths']))
        for argv in plan['report_commands']:
            self.assertEqual(['xcrun', 'xcresulttool', 'get', 'test-results'], argv[:4])
            self.assertIn(str(plan['report_path']), argv)
            self.assertNotIn('--format', argv)
            self.assertIn('--compact', argv)

    def test_xcode_tree_requires_failure_summary_assertion_and_retains_test_identity(self):
        plan = self.plan(['xcodebuild', 'test', '-only-testing:AppTests/BehaviorTests'])
        plan['report_path'].mkdir()
        tree = {'testNodes': [{'nodeType': 'Test Suite', 'name': 'BehaviorTests', 'children': [
            {'nodeType': 'Test Case', 'name': 'testValue()', 'nodeIdentifier': 'AppTests/BehaviorTests/testValue()', 'result': 'Failed'},
            {'nodeType': 'Test Case', 'name': 'testPass()', 'nodeIdentifier': 'AppTests/BehaviorTests/testPass()', 'result': 'Passed'},
            {'nodeType': 'Test Case', 'name': 'testSkip()', 'nodeIdentifier': 'AppTests/BehaviorTests/testSkip()', 'result': 'Skipped'},
        ]}]}
        summary = {'testFailures': [{'testIdentifier': 123, 'testIdentifierString': 'BehaviorTests/testValue()',
                                     'targetName': 'AppTests', 'testName': 'testValue()',
                                     'failureText': 'XCTAssertEqual failed: (1) is not equal to (2)'}]}
        for path, data in zip(plan['report_json_paths'], (tree, summary)):
            path.write_text(json.dumps(data))
        cases = parse_report(plan, self.repo)
        self.assertEqual(['FAIL', 'PASS', 'SKIP'], [x['outcome'] for x in cases])
        self.assertTrue(cases[0]['assertion'])
        self.assertEqual('AppTests/BehaviorTests/testValue()', cases[0]['id'])
        self.assertEqual('BehaviorTests', cases[0]['classname'])

    def test_xcode_failure_without_assertion_reason_is_not_assertion_red(self):
        plan = self.plan(['xcodebuild', 'test'])
        plan['report_path'].mkdir()
        data = {'testNodes': [{'nodeType': 'Test Case', 'nodeIdentifier': 'AppTests/T/testValue()', 'result': 'Failed'}]}
        plan['report_json_paths'][0].write_text(json.dumps(data))
        plan['report_json_paths'][1].write_text(json.dumps({'testFailures': []}))
        self.assertFalse(parse_report(plan, self.repo)[0]['assertion'])

    def test_xcode_nested_case_runs_do_not_double_count_or_hide_failed_retry(self):
        plan = self.plan(['xcodebuild', 'test'])
        plan['report_path'].mkdir()
        data = {'testNodes': [{'nodeType': 'Test Case', 'name': 'testValue()',
            'nodeIdentifier': 'AppTests/T/testValue()', 'result': 'Passed', 'children': [
                {'nodeType': 'Test Case Run', 'name': 'First run', 'result': 'Failed'},
                {'nodeType': 'Test Case Run', 'name': 'Second run', 'result': 'Passed'},
            ]}]}
        plan['report_json_paths'][0].write_text(json.dumps(data))
        plan['report_json_paths'][1].write_text(json.dumps({'testFailures': [
            {'testIdentifierString': 'T/testValue()', 'targetName': 'AppTests',
             'failureText': 'XCTAssertEqual failed'}]}))
        cases = parse_report(plan, self.repo)
        self.assertEqual(1, len(cases))
        self.assertEqual('FAIL', cases[0]['outcome'])
        self.assertTrue(cases[0]['assertion'])

    def test_xcode_expected_failure_does_not_establish_green(self):
        plan = self.plan(['xcodebuild', 'test'])
        plan['report_path'].mkdir()
        plan['report_json_paths'][0].write_text(json.dumps({'testNodes': [
            {'nodeType': 'Test Case', 'name': 'testValue()', 'nodeIdentifier': 'AppTests/T/testValue()',
             'result': 'Expected Failure'}]}))
        plan['report_json_paths'][1].write_text(json.dumps({'testFailures': []}))
        self.assertEqual('SKIP', parse_report(plan, self.repo)[0]['outcome'])

    def test_missing_empty_malformed_and_zero_case_reports_are_invalid(self):
        fixtures = [None, '', '<broken>', '<testsuites/>', '<unrelated><testcase name="fake"/></unrelated>',
                    '<testsuite><testcase/></testsuite>',
                    '<testsuite><testcase name="t"><failure/><skipped/></testcase></testsuite>']
        for body in fixtures:
            with self.subTest(body=body):
                plan = self.plan(['pytest', 'test_behavior.py'])
                if body is not None:
                    plan['report_path'].write_text(body)
                try:
                    with self.assertRaisesRegex(ValueError, '^TDD_RED_REASON_INVALID$'):
                        parse_report(plan, self.repo)
                finally:
                    plan['report_path'].unlink(missing_ok=True)

    def test_invalid_jest_shapes_and_outcomes_are_rejected(self):
        fixtures = [[], {}, {'testResults': []}, {'testResults': [{}]},
                    {'testResults': [{'name': 'test.js', 'assertionResults': []}]},
                    {'testResults': [{'name': 'test.js', 'assertionResults': [{'fullName': 't', 'status': 'unknown'}]}]},
                    {'testResults': [{'name': 'test.js', 'assertionResults': [{'fullName': 't', 'status': {}}]}]}]
        for data in fixtures:
            with self.subTest(data=data):
                plan = self.plan(['jest', 'test.js'])
                plan['report_path'].write_text(json.dumps(data))
                try:
                    with self.assertRaisesRegex(ValueError, '^TDD_RED_REASON_INVALID$'):
                        parse_report(plan, self.repo)
                finally:
                    plan['report_path'].unlink()

    def test_duplicate_case_ids_are_not_execution_proof(self):
        plan = self.plan(['pytest', 'test_behavior.py'])
        self.write_junit(plan, '<testsuite><testcase classname="Behavior" name="same"/><testcase classname="Behavior" name="same"/></testsuite>')
        with self.assertRaisesRegex(ValueError, '^TDD_RED_REASON_INVALID$'):
            parse_report(plan, self.repo)

    def test_existing_report_and_symbolic_link_report_are_rejected(self):
        plan = self.plan(['pytest', 'test_behavior.py'])
        plan['report_path'].write_text('<testsuite><testcase name="old"/></testsuite>')
        with self.assertRaisesRegex(ValueError, '^TDD_REPORT_PATH_INVALID$'):
            self.plan(['pytest', 'test_behavior.py'])
        plan['report_path'].unlink()
        outside = self.root / 'outside.xml'
        outside.write_text('<testsuite><testcase classname="Behavior" name="old"/></testsuite>')
        plan['report_path'].symlink_to(outside)
        with self.assertRaisesRegex(ValueError, '^TDD_REPORT_PATH_INVALID$'):
            parse_report(plan, self.repo)

    def test_report_case_file_cannot_escape_repo(self):
        plan = self.plan(['pytest', 'test_behavior.py'])
        self.write_junit(plan, '<testsuite><testcase file="../elsewhere.py" classname="Other" name="old"/></testsuite>')
        with self.assertRaisesRegex(ValueError, '^TDD_RED_REASON_INVALID$'):
            parse_report(plan, self.repo)


if __name__ == '__main__':
    unittest.main()
