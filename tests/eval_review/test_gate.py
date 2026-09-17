import copy
import hashlib
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
sys.path.insert(0, str(ROOT / 'SHARED' / 'runtime'))
from hb_eval_review.gate import generate_gate, validate_gate_file, run_gate_command
from hb_eval_review.schema_validation import validate_schema
from hb_eval_review.snapshot import compute_source_snapshot


def tdd_documents(baseline='RED_TO_GREEN', version='1.1'):
    design = {
        'schema_version': version, 'stage': 'tdd-test-design', 'tier': 'T1',
        'status': 'PASS', 'test_id': 'test_behavior', 'acceptance_refs': ['AC-1'],
        'red_failure_kind': 'bug_reproduced',
        'assertions': [{'kind': 'observable_behavior', 'description': 'Returns corrected result'}],
        'mocked_boundaries': [], 'system_under_test_mocked': False,
        'paths': ['success', 'failure'], 'reviewer': {'independent': False, 'read_only': True},
    }
    sensitivity = {
        'schema_version': version, 'stage': 'tdd-sensitivity', 'tier': 'T1',
        'status': 'PASS', 'test_id': 'test_behavior', 'red_test_hash': 'a' * 64,
        'green_test_hash': 'a' * 64, 'red_outcome': 'FAIL', 'green_outcome': 'PASS',
        'approved_red_revision': False, 'high_risk': False,
        'mutation': {'required': False, 'performed': False, 'outcome': 'NOT_REQUIRED'},
        'regression': {'status': 'PASS'},
    }
    if version == '1.1':
        design['baseline'] = sensitivity['baseline'] = baseline
    if baseline == 'PASS_TO_PASS':
        design.pop('red_failure_kind')
        sensitivity['red_outcome'] = 'PASS'
    return design, sensitivity


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q'], cwd=self.repo, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=self.repo, check=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.invalid'], cwd=self.repo, check=True)
        (self.repo / 'app.py').write_text('value = 1\n')
        subprocess.run(['git', 'add', 'app.py'], cwd=self.repo, check=True)
        subprocess.run(['git', 'commit', '-qm', 'fixture'], cwd=self.repo, check=True)
        self.artifacts = self.repo / '.harness/artifacts/feature/issue-1'
        self.gate = self.artifacts / 'eval-review/gate-result.json'
        self.write_tdd()

    def write_tdd(self, baseline='RED_TO_GREEN', version='1.1'):
        self.artifacts.mkdir(parents=True, exist_ok=True)
        for name, data in zip(('tdd-test-design-result.json', 'tdd-sensitivity-result.json'),
                              tdd_documents(baseline, version)):
            (self.artifacts / name).write_text(json.dumps(data))

    def create_gate(self, **kwargs):
        return generate_gate(self.repo, [shlex.join([sys.executable, '-c', 'print("ok")'])], self.gate, **kwargs)

    def overwrite_gate(self, data):
        self.gate.write_text(json.dumps(data))

    def test_gate_schema_v11_requires_source_id_and_rejects_evidence_packet_ids(self):
        data = self.create_gate()
        self.assertEqual('PASS', data['status'])
        self.assertEqual([], validate_schema(data, 'gate-result.schema.json'))
        for field in ('source_snapshot_id', 'commands', 'tdd_evidence'):
            with self.subTest(missing=field):
                bad = copy.deepcopy(data)
                del bad[field]
                self.assertTrue(validate_schema(bad, 'gate-result.schema.json'))
        for field in ('evidence_bundle_id', 'packet_id'):
            with self.subTest(forbidden=field):
                self.assertTrue(validate_schema(dict(data, **{field: 'a' * 64}), 'gate-result.schema.json'))

    def test_validate_gate_file_rejects_empty_commands_or_nonzero_exit(self):
        data = self.create_gate()
        for commands in ([], [dict(data['commands'][0], exit_code=1)]):
            with self.subTest(commands=commands):
                self.overwrite_gate(dict(data, commands=commands))
                self.assertIn('GATE_NOT_PASSED', validate_gate_file(self.gate, self.repo))

    def test_validate_gate_file_blocks_blocked_status_with_pass_metadata(self):
        data = self.create_gate()
        data['status'] = 'BLOCKED'
        data['commands'][0]['exit_code'] = 1
        self.overwrite_gate(data)
        self.assertIn('GATE_NOT_PASSED', validate_gate_file(self.gate, self.repo))

    def test_validate_gate_file_blocks_stale_source(self):
        self.create_gate()
        (self.repo / 'app.py').write_text('value = 2\n')
        self.assertIn('GATE_STALE', validate_gate_file(self.gate, self.repo))

    def test_gate_commands_are_sequential_and_source_changes_block(self):
        commands = [shlex.join([sys.executable, '-c', 'from pathlib import Path; Path("app.py").write_text("changed")']),
                    shlex.join([sys.executable, '-c', 'from pathlib import Path; print(Path("app.py").read_text())'])]
        data = generate_gate(self.repo, commands, self.gate)
        self.assertEqual('BLOCKED', data['status'])
        self.assertIn('GATE_SOURCE_CHANGED', data['errors'])
        self.assertEqual('changed\n', data['commands'][1]['stdout_tail'])

    def test_gate_rejects_shell_operators_before_any_command_runs(self):
        marker = self.repo / 'marker'
        for command in ('echo safe | cat', 'echo x > marker', 'echo x; touch marker', 'echo x && touch marker', 'echo $(touch marker)'):
            with self.subTest(command=command):
                data = generate_gate(self.repo, ['touch marker', command], self.gate)
                self.assertEqual('BLOCKED', data['status'])
                self.assertIn('GATE_COMMAND_INVALID', data['errors'])
                self.assertFalse(marker.exists())

    def test_gate_runner_redacts_before_hashing_and_retains_test_environment(self):
        secret = 'sk-ant-abcdefghijk'
        code = 'import os; print("' + secret + '"); print(os.environ.get("DJANGO_SETTINGS_MODULE")); print(os.environ.get("OPERATOR_PRIVATE_TOKEN", "absent"))'
        with patch.dict(os.environ, {'DJANGO_SETTINGS_MODULE': 'project.test_settings', 'OPERATOR_PRIVATE_TOKEN': 'private-value'}):
            row = run_gate_command(shlex.join([sys.executable, '-c', code]), self.repo, track='feature')
        self.assertEqual(0, row['exit_code'])
        self.assertNotIn(secret, json.dumps(row))
        self.assertIn('project.test_settings', row['stdout_tail'])
        self.assertIn('absent', row['stdout_tail'])
        self.assertEqual(hashlib.sha256(row['stdout_tail'].encode()).hexdigest(), row['stdout_sha256'])

    def test_pack_requires_track_tdd_json_valid(self):
        for track, issue_type, baseline in (('feature', None, 'RED_TO_GREEN'), ('maintenance', 'bug', 'RED_TO_GREEN'),
                                            ('maintenance', 'refactor', 'PASS_TO_PASS'), ('hotfix', None, 'RED_TO_GREEN')):
            with self.subTest(track=track, issue_type=issue_type):
                self.artifacts = self.repo / '.harness/artifacts' / track / 'issue-1'
                self.gate = self.artifacts / 'eval-review/gate-result.json'
                self.write_tdd(baseline)
                self.assertEqual('PASS', self.create_gate(issue_type=issue_type)['status'])
                self.assertEqual([], validate_gate_file(self.gate, self.repo, track=track, issue_type=issue_type))
                target = self.artifacts / 'tdd-test-design-result.json'
                target.unlink()
                self.assertIn('TDD_EVIDENCE_MISSING', validate_gate_file(self.gate, self.repo, track=track, issue_type=issue_type))
                self.write_tdd(baseline)
                doc = json.loads(target.read_text())
                doc['status'] = 'BLOCKED'
                target.write_text(json.dumps(doc))
                self.assertIn('TDD_EVIDENCE_MISSING', validate_gate_file(self.gate, self.repo, track=track, issue_type=issue_type))

    def test_gate_preserves_tdd_meaning_error_codes(self):
        self.create_gate()
        target = self.artifacts / 'tdd-sensitivity-result.json'
        doc = json.loads(target.read_text())
        doc['green_test_hash'] = 'b' * 64
        target.write_text(json.dumps(doc))
        self.assertIn('TDD_TEST_IDENTITY_CHANGED', validate_gate_file(self.gate, self.repo))

    def test_gate_keeps_semantic_codes_when_schema_also_rejects_value(self):
        self.create_gate()
        design_path = self.artifacts / 'tdd-test-design-result.json'
        sensitivity_path = self.artifacts / 'tdd-sensitivity-result.json'
        design = json.loads(design_path.read_text())
        design['red_failure_kind'] = 'import_error'
        design_path.write_text(json.dumps(design))
        sensitivity = json.loads(sensitivity_path.read_text())
        sensitivity['red_outcome'] = 'PASS'
        sensitivity_path.write_text(json.dumps(sensitivity))
        errors = validate_gate_file(self.gate, self.repo)
        self.assertIn('TDD_SCHEMA_INVALID', errors)
        self.assertIn('TDD_RED_REASON_INVALID', errors)
        self.assertIn('TDD_TRANSITION_INVALID', errors)

    def test_gate_blocks_wrong_tdd_shapes_without_traceback(self):
        self.create_gate()
        target = self.artifacts / 'tdd-test-design-result.json'
        document = json.loads(target.read_text())
        document['assertions'] = [5]
        target.write_text(json.dumps(document))
        self.assertIn('TDD_SCHEMA_INVALID', validate_gate_file(self.gate, self.repo))

    def test_gate_stdout_hash_covers_complete_redacted_output(self):
        command = shlex.join([sys.executable, '-c', 'print("x" * 70000)'])
        row = run_gate_command(command, self.repo, track='hotfix')
        self.assertEqual(65536, len(row['stdout_tail']))
        self.assertEqual(hashlib.sha256(('x' * 70000 + '\n').encode()).hexdigest(), row['stdout_sha256'])

    def test_gate_validates_v10_compatibility_and_v11_baseline_pair(self):
        self.write_tdd(version='1.0')
        self.assertEqual('PASS', self.create_gate()['status'])
        self.assertEqual([], validate_gate_file(self.gate, self.repo))
        self.write_tdd()
        target = self.artifacts / 'tdd-sensitivity-result.json'
        doc = json.loads(target.read_text())
        doc['baseline'] = 'PASS_TO_PASS'
        doc['red_outcome'] = 'PASS'
        target.write_text(json.dumps(doc))
        self.assertIn('TDD_BASELINE_MISMATCH', validate_gate_file(self.gate, self.repo))
        doc.pop('baseline')
        target.write_text(json.dumps(doc))
        self.assertIn('TDD_BASELINE_INVALID', validate_gate_file(self.gate, self.repo))

    def test_pass_baseline_cannot_change_issue_type(self):
        self.write_tdd('PASS_TO_PASS')
        data = self.create_gate(issue_type='refactor')
        self.assertEqual('BLOCKED', data['status'])
        self.assertIn('TDD_BASELINE_INVALID', data['errors'])

    def test_frozen_evidence_validator_never_reads_live_source(self):
        data = self.create_gate()
        frozen = Path(self.temp.name) / 'packet/evidence'
        frozen.mkdir(parents=True)
        (frozen / 'gate-result.json').write_bytes(self.gate.read_bytes())
        for name in ('tdd-test-design-result.json', 'tdd-sensitivity-result.json'):
            (frozen / name).write_bytes((self.artifacts / name).read_bytes())
            (self.artifacts / name).unlink()
        (self.repo / 'app.py').write_text('changed after frozen copy')
        with patch('hb_eval_review.gate.compute_source_snapshot', side_effect=AssertionError('must not reread live source')):
            self.assertEqual([], validate_gate_file(frozen / 'gate-result.json', self.repo,
                evidence_root=frozen, source_snapshot_id=data['source_snapshot_id'], track='feature', artifacts=self.artifacts))

    def test_gate_path_and_tdd_reference_cannot_escape_artifact_layout(self):
        data = self.create_gate()
        data['tdd_evidence'][0] = '../outside.json'
        self.overwrite_gate(data)
        self.assertIn('TDD_EVIDENCE_MISSING', validate_gate_file(self.gate, self.repo))


if __name__ == '__main__':
    unittest.main()
