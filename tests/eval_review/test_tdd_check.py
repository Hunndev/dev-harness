"""Public CLI tests use a real subprocess and runner-owned JUnit output.

The miniature pytest-shaped executable actually evaluates the fixture's assertion;
format/parser coverage against primary runner fixtures lives in test_tdd_reports.
"""
import contextlib
import copy
import hashlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'SHARED/runtime'))
from hb_eval_review import cli
from hb_eval_review.schema_validation import validate_schema
from hb_eval_review.gate import generate_gate
from test_gate import tdd_documents


RUNNER = r'''import json, pathlib, sys, traceback, xml.etree.ElementTree as ET
sys.dont_write_bytecode = True
repo = pathlib.Path.cwd()
sys.path.insert(0, str(repo))
args = sys.argv[1:]
report = next((a.split('=', 1)[1] for a in args if a.startswith('--junitxml=')), None)
if report is None and '--junitxml' in args:
    report = args[args.index('--junitxml') + 1]
mode = json.loads((repo / 'scenario.json').read_text())
suite = ET.Element('testsuite', name='pytest', tests='0' if mode == 'zero' else '1')
code = 1
if mode != 'zero':
    name = 'test_other' if mode == 'other' else 'test_behavior'
    case = ET.SubElement(suite, 'testcase', name=name, classname='test_behavior', file='test_behavior.py')
    try:
        if mode == 'fixture':
            raise RuntimeError('fixture setup failed')
        if mode == 'skip':
            ET.SubElement(case, 'skipped')
        else:
            exec(compile((repo / 'test_behavior.py').read_text(), 'test_behavior.py', 'exec'), {})
        code = 0
    except AssertionError:
        error = ET.SubElement(case, 'failure', message='assertion failure')
        error.text = traceback.format_exc()
        print(error.text)
    except Exception:
        error = ET.SubElement(case, 'error', message='failed on setup with fixture error')
        error.text = traceback.format_exc()
        print(error.text)
if report:
    path = pathlib.Path(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(path, encoding='unicode')
sys.exit(code)
'''


class TddCheckTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'config', 'user.name', 'Test'], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'config', 'user.email', 'test@example.invalid'], check=True)
        (self.repo / 'app.py').write_text('value = 1\n')
        self.test_file = self.repo / 'test_behavior.py'
        self.test_file.write_text('import app\nassert app.value == 2\n')
        (self.repo / 'scenario.json').write_text(json.dumps('assertion'))
        self.runner = self.repo / 'tools/pytest'
        self.runner.parent.mkdir()
        self.runner.write_text('#!' + sys.executable + '\n' + RUNNER)
        self.runner.chmod(0o755)
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'commit', '-qm', 'fixture'], check=True)
        self.out = self.repo / '.harness/artifacts/feature/issue-1'
        self.out.mkdir(parents=True)
        # Producer metadata remains semantic input; consumer golden fixtures are 1.2.
        self.design, self.sensitivity = tdd_documents(version='1.1')
        self.design_input = self.repo / 'design-input.json'
        self.sensitivity_input = self.repo / 'sensitivity-input.json'
        self.design_input.write_text(json.dumps(self.design))
        self.sensitivity_input.write_text(json.dumps(self.sensitivity))
        self.command = shlex.join([str(self.runner), 'test_behavior.py'])

    def call(self, phase, *extra, design=None, command=None, issue_type='feature'):
        args = ['tdd-check', phase, '--repo', str(self.repo), '--test-file', 'test_behavior.py',
                '--cmd', command or self.command, '--design', str(design or (
                    self.design_input if phase == 'red' else self.out / 'tdd-test-design-result.json')),
                '--out', str(self.out), '--issue-type', issue_type]
        if phase == 'green':
            args += ['--sensitivity', str(self.sensitivity_input)]
        args += list(extra)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = cli.main(args)
        return result, json.loads(stdout.getvalue())

    def red(self, **kwargs):
        result, payload = self.call('red', **kwargs)
        self.assertEqual(0, result, payload)
        return json.loads((self.out / 'tdd-test-design-result.json').read_text())

    def fix(self):
        (self.repo / 'app.py').write_text('value = 2\n')

    def test_red_requires_at_least_one_selected_test_executed(self):
        (self.repo / 'scenario.json').write_text(json.dumps('zero'))
        result, payload = self.call('red')
        self.assertEqual(2, result)
        self.assertIn('TDD_RED_REASON_INVALID', payload['errors'])
        self.assertFalse((self.out / 'tdd-test-design-result.json').exists())
        (self.repo / 'scenario.json').write_text(json.dumps('assertion'))
        design = self.red()
        self.assertEqual(1, design['observed']['executed'])

    def test_red_rejects_fixture_error_on_stdout(self):
        (self.repo / 'scenario.json').write_text(json.dumps('fixture'))
        result, payload = self.call('red')
        self.assertEqual(2, result)
        self.assertIn('TDD_RED_REASON_INVALID', payload['errors'])

    def test_green_requires_same_selected_test_ids_pass(self):
        baseline = self.red()
        self.fix()
        for mode in ('other', 'skip'):
            with self.subTest(mode=mode):
                (self.repo / 'scenario.json').write_text(json.dumps(mode))
                result, payload = self.call('green')
                self.assertEqual(2, result)
                self.assertIn('TDD_TRANSITION_INVALID', payload['errors'])
        (self.repo / 'scenario.json').write_text(json.dumps('assertion'))
        # Extra runner switches may legitimately differ. IDs, not argv text, bind.
        result, payload = self.call('green', command=self.command + ' -q')
        self.assertEqual(0, result, payload)
        sensitivity = json.loads((self.out / 'tdd-sensitivity-result.json').read_text())
        self.assertEqual(baseline['observed']['selected_tests'], sensitivity['observed']['selected_tests'])

    def approval(self, baseline):
        revision = 'revision 1: clarify the asserted behavior'
        (self.out / 'tdd-red-revisions.md').write_text(revision + '\n')
        observed = baseline['observed']
        record = {
            'schema_version': '1.0', 'kind': 'tdd-red-revision-approval',
            'repo': str(self.repo), 'git_dir': observed['git_dir'], 'artifacts': str(self.out),
            'run_id': observed['run_id'], 'test_file': 'test_behavior.py',
            'old_sha256': observed['test_file_sha256'],
            'new_sha256': hashlib.sha256(self.test_file.read_bytes()).hexdigest(),
            'revision': 1, 'revision_line': revision, 'approved_by': 'user',
            'approval_source': 'fixture-user-message-1', 'recorded_at': '2026-09-21T00:00:00Z',
        }
        path = self.root / 'controller-approval.json'
        path.write_text(json.dumps(record))
        return path

    def test_identity_change_without_approval_record_is_blocked(self):
        baseline = self.red()
        self.fix()
        self.test_file.write_text(self.test_file.read_text() + '# approved revision candidate\n')
        self.sensitivity['approved_red_revision'] = True
        self.sensitivity_input.write_text(json.dumps(self.sensitivity))
        result, payload = self.call('green')
        self.assertEqual(2, result)
        self.assertIn('TDD_TEST_IDENTITY_CHANGED', payload['errors'])
        approval = self.approval(baseline)
        result, payload = self.call('green', '--approval-record', str(approval))
        self.assertEqual(0, result, payload)
        sensitivity = json.loads((self.out / 'tdd-sensitivity-result.json').read_text())
        self.assertTrue(sensitivity['approved_red_revision'])

    def test_refactor_pass_to_pass_baseline(self):
        self.out = self.repo / '.harness/artifacts/maintenance/issue-1'
        self.out.mkdir(parents=True)
        self.design['baseline'] = 'PASS_TO_PASS'
        self.design.pop('red_failure_kind')
        self.design_input.write_text(json.dumps(self.design))
        self.fix()
        baseline = self.red(issue_type='refactor')
        self.assertEqual('PASS_TO_PASS', baseline['baseline'])
        self.assertNotIn('red_failure_kind', baseline)
        result, payload = self.call('green', issue_type='refactor')
        self.assertEqual(0, result, payload)
        sensitivity = json.loads((self.out / 'tdd-sensitivity-result.json').read_text())
        self.assertEqual(('PASS_TO_PASS', 'PASS', 'PASS'),
                         (sensitivity['baseline'], sensitivity['red_outcome'], sensitivity['green_outcome']))

    def test_stack_selectors_accepted(self):
        # Real subprocess pytest path plus each other stack's owned-report parser;
        # native Gradle/Xcode execution is not claimed by fixture coverage.
        self.red()
        from hb_eval_review.tdd_reports import prepare_report, parse_report
        commands = [('jest', '--testPathPattern', 'test_behavior'), ('jest', 'test_behavior'),
                    ('./gradlew', 'testDebugUnitTest', '--tests', 'example.TestBehavior'),
                    ('xcodebuild', 'test', '-only-testing:AppTests/TestBehavior')]
        with tempfile.TemporaryDirectory() as temporary:
            for index, command in enumerate(commands):
                path = Path(temporary) / str(index)
                path.mkdir()
                plan = prepare_report(list(command), path)
                for selector in command[1:]:
                    self.assertIn(selector, plan['argv'])
                if plan['kind'] == 'jest':
                    expected_id = 'test_behavior.py::returns expected value'
                    plan['report_path'].write_text(json.dumps({'testResults': [{
                        'name': str(self.test_file), 'status': 'failed', 'assertionResults': [{
                            'fullName': 'returns expected value', 'status': 'failed',
                            'failureMessages': ['Error: expect(received).toBe(expected)\nExpected: 2\nReceived: 1\n'
                                '    at Object.<anonymous> (' + str(self.test_file) + ':2:1)\n'
                                '    at _callCircusTest (/fixture/node_modules/jest-circus/build/run.js:200:1)']}]}]}))
                elif plan['kind'] == 'gradle':
                    expected_id = 'example.TestBehavior::returnsExpectedValue'
                    target = plan['report_path'] / 'test/TEST-TestBehavior.xml'
                    target.parent.mkdir(parents=True)
                    target.write_text('<testsuite><testcase classname="example.TestBehavior" name="returnsExpectedValue">'
                                      '<failure type="java.lang.AssertionError">expected 2, got 1</failure></testcase></testsuite>')
                else:
                    expected_id = 'AppTests/TestBehavior/testValue()'
                    plan['report_path'].mkdir()
                    plan['report_json_paths'][0].write_text(json.dumps({'testNodes': [{
                        'nodeType': 'Test Case', 'nodeIdentifier': expected_id, 'result': 'Failed'}]}))
                    plan['report_json_paths'][1].write_text(json.dumps({'testFailures': [{
                        'testIdentifierString': 'TestBehavior/testValue()', 'targetName': 'AppTests',
                        'failureText': 'XCTAssertEqual failed: (1) is not equal to (2)'}]}))
                cases = parse_report(plan, self.repo)
                self.assertEqual([(expected_id, 'FAIL', True)],
                                 [(case['id'], case['outcome'], case['assertion']) for case in cases])
                self.assertEqual(1, sum(case['outcome'] in ('PASS', 'FAIL') for case in cases))

    def test_report_paths_are_runner_owned(self):
        foreign = self.repo / 'old.xml'
        foreign.write_text('<testsuite tests="1"><testcase name="old"/></testsuite>')
        result, payload = self.call('red', command=self.command + ' --junitxml=' + str(foreign))
        self.assertEqual(2, result)
        self.assertIn('TDD_REPORT_PATH_INVALID', payload['errors'])
        self.assertEqual('<testsuite tests="1"><testcase name="old"/></testsuite>', foreign.read_text())

    def test_schema_v11_observed_fields(self):
        baseline = self.red()
        self.fix()
        result, payload = self.call('green')
        self.assertEqual(0, result, payload)
        for filename in ('tdd-test-design-result', 'tdd-sensitivity-result'):
            data = json.loads((self.out / (filename + '.json')).read_text())
            self.assertEqual('1.2', data['schema_version'])
            self.assertEqual([], validate_schema(data, filename + '.schema.json'))
            self.assertTrue({'argv', 'cwd', 'exit_code', 'selected_tests', 'executed', 'recorded_at',
                             'test_file_sha256'}.issubset(data['observed']))
        legacy = copy.deepcopy(baseline)
        legacy.pop('observed')
        legacy['schema_version'] = '1.1'
        path = self.repo / 'legacy.json'
        path.write_text(json.dumps(legacy))
        result, payload = self.call('green', design=path)
        self.assertEqual(2, result)
        self.assertIn('TDD_OBSERVATION_INVALID', payload['errors'])

    def test_baseline_cannot_be_overwritten_or_substituted_between_runs(self):
        baseline = self.red()
        original = (self.out / 'tdd-test-design-result.json').read_bytes()
        result, payload = self.call('red')
        self.assertEqual(2, result)
        self.assertIn('TDD_BASELINE_IMMUTABLE', payload['errors'])
        self.assertEqual(original, (self.out / 'tdd-test-design-result.json').read_bytes())
        baseline['observed']['run_id'] = 'f' * 32
        (self.out / 'tdd-test-design-result.json').chmod(0o600)
        (self.out / 'tdd-test-design-result.json').write_text(json.dumps(baseline))
        self.fix()
        result, payload = self.call('green')
        self.assertEqual(2, result)
        self.assertIn('TDD_OBSERVATION_INVALID', payload['errors'])

    def test_external_approval_cannot_point_into_repository(self):
        baseline = self.red()
        self.fix()
        self.test_file.write_text(self.test_file.read_text() + '# revision\n')
        external = self.approval(baseline)
        inside = self.repo / 'self-approved.json'
        inside.write_bytes(external.read_bytes())
        link = self.root / 'approval-link.json'
        link.symlink_to(inside)
        for path in (inside, link):
            with self.subTest(path=path.name):
                result, payload = self.call('green', '--approval-record', str(path))
                self.assertEqual(2, result)
                self.assertIn('TDD_TEST_IDENTITY_CHANGED', payload['errors'])

    def test_shell_operators_are_rejected_without_launch(self):
        with patch('hb_eval_review.gate.subprocess.run') as launch:
            result, payload = self.call('red', command=self.command + ' | cat')
        self.assertEqual(2, result)
        self.assertIn('TDD_COMMAND_INVALID', payload['errors'])
        launch.assert_not_called()

    def test_green_declared_schema_status_and_stage_are_not_upgraded(self):
        self.red()
        self.fix()
        for key, value in (('schema_version', '99.0'), ('stage', 'arbitrary'), ('status', 'BLOCKED'),
                           ('regression', {'status': 'FAIL'}), ('mutation', {'required': True,
                            'performed': False, 'outcome': 'NOT_REQUIRED'})):
            with self.subTest(key=key):
                metadata = dict(self.sensitivity, **{key: value})
                self.sensitivity_input.write_text(json.dumps(metadata))
                with patch('hb_eval_review.tdd_observation.run_gate_command') as launch:
                    result, payload = self.call('green')
                self.assertEqual(2, result, payload)
                launch.assert_not_called()
        metadata = {key: self.sensitivity[key] for key in ('tier', 'test_id', 'high_risk', 'mutation', 'regression')}
        self.sensitivity_input.write_text(json.dumps(metadata))
        result, payload = self.call('green')
        self.assertEqual(0, result, payload)

    def test_test_file_changed_during_command_is_blocked(self):
        from hb_eval_review import tdd_observation
        original = tdd_observation._observe
        def changing(*args, **kwargs):
            result = original(*args, **kwargs)
            self.test_file.write_text(self.test_file.read_text() + '# changed during run\n')
            return result
        with patch.object(tdd_observation, '_observe', side_effect=changing):
            result, payload = self.call('red')
        self.assertEqual(2, result)
        self.assertIn('TDD_TEST_IDENTITY_CHANGED', payload['errors'])
        self.assertFalse((self.out / 'tdd-test-design-result.json').exists())

    def test_complete_stdout_error_is_not_lost_outside_tail(self):
        from hb_eval_review import tdd_observation
        original = tdd_observation.run_gate_command
        def long_error(*args, **kwargs):
            row = original(*args, **kwargs)
            row['stdout'] = 'ERROR at setup of an unrelated test\n' + 'x' * 70000 + row['stdout']
            row['stdout_tail'] = row['stdout'][-65536:]
            return row
        with patch.object(tdd_observation, 'run_gate_command', side_effect=long_error):
            result, payload = self.call('red')
        self.assertEqual(2, result)
        self.assertIn('TDD_RED_REASON_INVALID', payload['errors'])

    def test_timeout_with_partial_assertion_report_is_not_valid_red(self):
        from hb_eval_review import tdd_observation
        original = tdd_observation.run_gate_command
        def timed_out(*args, **kwargs):
            row = original(*args, **kwargs)
            row.update(exit_code=124, execution_error='timeout')
            return row
        with patch.object(tdd_observation, 'run_gate_command', side_effect=timed_out):
            result, payload = self.call('red')
        self.assertEqual(2, result)
        self.assertIn('TDD_RED_REASON_INVALID', payload['errors'])

    def test_approval_change_during_execution_is_blocked(self):
        from hb_eval_review import tdd_observation
        baseline = self.red()
        self.fix()
        self.test_file.write_text(self.test_file.read_text() + '# revision\n')
        approval = self.approval(baseline)
        original = tdd_observation._observe
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            approval.write_text(approval.read_text() + ' ')
            return result
        with patch.object(tdd_observation, '_observe', side_effect=changed):
            result, payload = self.call('green', '--approval-record', str(approval))
        self.assertEqual(2, result)
        self.assertIn('TDD_OBSERVATION_INVALID', payload['errors'])

    def test_approved_red_revision_creates_new_run_and_keeps_old_baseline(self):
        baseline = self.red()
        self.test_file.write_text(self.test_file.read_text() + '# revision\n')
        approval = self.approval(baseline)
        result, payload = self.call('red', '--approval-record', str(approval))
        self.assertEqual(0, result, payload)
        new = json.loads((self.out / 'tdd-test-design-result.json').read_text())
        self.assertNotEqual(baseline['observed']['run_id'], new['observed']['run_id'])
        old = self.out / 'eval-review/tdd-check' / (baseline['observed']['run_id'] + '.json')
        self.assertEqual(baseline, json.loads(old.read_text()))
        self.fix()
        result, payload = self.call('green')
        self.assertEqual(0, result, payload)

    def test_gate_consumes_pair_binding_and_rejects_another_artifact(self):
        self.red()
        self.fix()
        result, payload = self.call('green')
        self.assertEqual(0, result, payload)
        gate = self.out / 'eval-review/gate-result.json'
        command = shlex.join([sys.executable, '-c', 'print("gate")'])
        self.assertEqual('PASS', generate_gate(self.repo, [command], gate, issue_type='feature')['status'])
        sensitivity = json.loads((self.out / 'tdd-sensitivity-result.json').read_text())
        sensitivity['observed']['run_id'] = 'f' * 32
        path = self.out / 'tdd-sensitivity-result.json'
        path.chmod(0o600)
        path.write_text(json.dumps(sensitivity))
        blocked = generate_gate(self.repo, [command], gate, issue_type='feature')
        self.assertEqual('BLOCKED', blocked['status'])
        self.assertIn('TDD_BASELINE_MISMATCH', blocked['errors'])

    def test_failed_green_refresh_invalidates_prior_pass_even_with_same_sut(self):
        from hb_eval_review import tdd_observation
        self.red()
        self.fix()
        result, payload = self.call('green')
        self.assertEqual(0, result, payload)
        original = tdd_observation._observe
        def failed_refresh(*args, **kwargs):
            row, ids, _, _ = original(*args, **kwargs)
            return row, ids, False, 'TDD_TRANSITION_INVALID'
        with patch.object(tdd_observation, '_observe', side_effect=failed_refresh):
            result, payload = self.call('green')
        self.assertEqual(2, result)
        self.assertEqual('BLOCKED', json.loads((self.out / 'tdd-sensitivity-result.json').read_text())['status'])
        gate = generate_gate(self.repo, [shlex.join([sys.executable, '-c', 'print("ok")'])],
                             self.out / 'eval-review/gate-result.json', issue_type='feature')
        self.assertIn('TDD_EVIDENCE_MISSING', gate['errors'])


if __name__ == '__main__':
    unittest.main()
