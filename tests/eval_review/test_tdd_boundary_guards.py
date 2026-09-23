"""Pin approval and repository boundaries with runner-owned observations."""
import json
import shlex
import shutil
import sys
import unittest
from unittest.mock import patch

import test_tdd_check as fixtures
from hb_eval_review import tdd_observation
from hb_eval_review.gate import generate_gate, validate_gate_file
from hb_eval_review.snapshot import compute_source_snapshot


class TddBoundaryGuardTests(unittest.TestCase):
    def fixture(self):
        case = fixtures.TddCheckTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def test_approval_record_requires_matching_revision_line_in_artifacts(self):
        case = self.fixture()
        baseline = case.red()
        case.fix()
        case.test_file.write_text(case.test_file.read_text() + '# approved revision candidate\n')
        approval = case.approval(baseline)
        record = json.loads(approval.read_text())
        approved_line = record['revision_line']
        revision_path = case.out / 'tdd-red-revisions.md'
        invalid_revisions = {
            'different reason': 'revision 1: a different unapproved reason\n',
            'unapproved second line': approved_line + '\nrevision 2: another unapproved edit\n',
        }
        for reason, revisions in invalid_revisions.items():
            with self.subTest(reason=reason):
                revision_path.write_text(revisions)
                result, payload = case.call('green', '--approval-record', str(approval))
                self.assertEqual(2, result, payload)
                self.assertIn('TDD_TEST_IDENTITY_CHANGED', payload['errors'])
        revision_path.write_text(approved_line + '\n')
        result, payload = case.call('green', '--approval-record', str(approval))
        self.assertEqual(0, result, payload)
        sensitivity = json.loads((case.out / 'tdd-sensitivity-result.json').read_text())
        self.assertEqual('PASS', sensitivity['status'])
        self.assertEqual(record, sensitivity['observed']['approval']['record'])

    def test_test_file_under_harness_is_rejected(self):
        for under_harness in (False, True):
            with self.subTest(under_harness=under_harness):
                case = self.fixture()
                test = case.out / 'test_behavior.py' if under_harness else case.test_file
                if under_harness:
                    test.write_bytes(case.test_file.read_bytes())
                relative = test.relative_to(case.repo).as_posix()
                # Execute and report the selected file, so a removed path guard
                # cannot be masked by an unrelated report/file-binding failure.
                runner = case.runner.read_text().replace(
                    "file='test_behavior.py'", 'file=args[0]').replace(
                    "(repo / 'test_behavior.py').read_text()", '(repo / args[0]).read_text()')
                case.runner.write_text(runner)
                command = shlex.join([str(case.runner), relative])
                with patch.object(tdd_observation, 'run_gate_command',
                                  wraps=tdd_observation.run_gate_command) as launch:
                    result, payload = case.call('red', '--test-file', relative, command=command)
                if under_harness:
                    self.assertEqual(2, result, payload)
                    self.assertIn('TDD_PATH_INVALID', payload['errors'])
                    launch.assert_not_called()
                    self.assertFalse((case.out / 'tdd-test-design-result.json').exists())
                else:
                    self.assertEqual(0, result, payload)
                    launch.assert_called_once()
                    self.assertEqual(1, payload['executed'])

    def test_red_source_change_during_command_is_blocked(self):
        case = self.fixture()
        original_test = case.test_file.read_bytes()
        # The executable first observes the real failing assertion, then changes
        # implementation bytes before exiting with its valid assertion report.
        runner = case.runner.read_text().replace(
            'sys.exit(code)', "(repo / 'app.py').write_text('value = 3\\n')\nsys.exit(code)")
        case.runner.write_text(runner)
        with patch.object(tdd_observation, 'run_gate_command',
                          wraps=tdd_observation.run_gate_command) as launch:
            result, payload = case.call('red')
        self.assertEqual('value = 3\n', (case.repo / 'app.py').read_text())
        self.assertEqual(original_test, case.test_file.read_bytes())
        launch.assert_called_once()
        self.assertEqual(2, result, payload)
        self.assertIn('TDD_SOURCE_CHANGED', payload['errors'])
        self.assertFalse((case.out / 'tdd-test-design-result.json').exists())

    def test_refactor_issue_type_outside_maintenance_is_rejected_before_execution(self):
        for track in ('feature', 'hotfix'):
            with self.subTest(track=track):
                case = self.fixture()
                case.out = case.repo / '.harness/artifacts' / track / 'issue-1'
                case.out.mkdir(parents=True, exist_ok=True)
                with patch.object(tdd_observation, 'run_gate_command',
                                  wraps=tdd_observation.run_gate_command) as launch:
                    result, payload = case.call('red', issue_type='refactor')
                self.assertEqual(2, result, payload)
                self.assertIn('TDD_BASELINE_INVALID', payload['errors'])
                launch.assert_not_called()
                self.assertFalse((case.out / 'tdd-test-design-result.json').exists())
                # The same command and track remain usable with their own type.
                result, payload = case.call('red', issue_type=track)
                self.assertEqual(0, result, payload)

    def test_gate_rejects_observation_from_another_checkout(self):
        case = self.fixture()
        case.red()
        case.fix()
        result, payload = case.call('green')
        self.assertEqual(0, result, payload)
        command = shlex.join([sys.executable, '-c', 'print("checks pass")'])
        gate = case.out / 'eval-review/gate-result.json'
        original = generate_gate(case.repo, [command], gate, issue_type='feature')
        self.assertEqual('PASS', original['status'], original)
        self.assertEqual([], validate_gate_file(gate, case.repo, issue_type='feature'))

        copied_repo = case.root / 'another-checkout'
        shutil.copytree(case.repo, copied_repo)
        copied_out = copied_repo / case.out.relative_to(case.repo)
        copied_gate = copied_out / 'eval-review/gate-result.json'
        for name in ('tdd-test-design-result.json', 'tdd-sensitivity-result.json'):
            self.assertEqual((case.out / name).read_bytes(), (copied_out / name).read_bytes())
        self.assertEqual(compute_source_snapshot(case.repo)['source_snapshot_id'],
                         compute_source_snapshot(copied_repo)['source_snapshot_id'])
        with self.subTest(consumer='validate_gate_file'):
            self.assertIn('TDD_OBSERVATION_INVALID',
                          validate_gate_file(copied_gate, copied_repo, issue_type='feature'))
        with self.subTest(consumer='generate_gate'):
            copied = generate_gate(copied_repo, [command], copied_gate, issue_type='feature')
            self.assertEqual('BLOCKED', copied['status'], copied)
            self.assertIn('TDD_OBSERVATION_INVALID', copied['errors'])


if __name__ == '__main__':
    unittest.main()
