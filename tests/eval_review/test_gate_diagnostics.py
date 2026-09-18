import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'SHARED' / 'runtime'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hb_eval_review.gate import validate_gate_file
from test_gate import tdd_documents


TDD_NAMES = ('tdd-test-design-result.json', 'tdd-sensitivity-result.json')


class GateDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / 'repo'
        self.artifacts = self.repo / '.harness/artifacts/feature/issue-1'
        self.gate = self.artifacts / 'eval-review/gate-result.json'
        self.gate.parent.mkdir(parents=True)
        self.source_id = 'a' * 64
        self.gate_data = {
            'schema_version': '1.1', 'stage': 'gate', 'status': 'PASS',
            'source_snapshot_id': self.source_id,
            'commands': [{'name': 'check', 'command': ['check'], 'exit_code': 0,
                          'duration_ms': 1, 'stdout_tail': '', 'stderr_tail': '',
                          'stdout_sha256': 'b' * 64}],
            'tdd_evidence': [(self.artifacts / name).relative_to(self.repo).as_posix()
                             for name in TDD_NAMES],
        }
        self.gate.write_text(json.dumps(self.gate_data))
        self.write_documents()

    def write_documents(self):
        for name, document in zip(TDD_NAMES, tdd_documents()):
            (self.artifacts / name).write_text(json.dumps(document))

    def validate(self):
        return validate_gate_file(self.gate, self.repo, source_snapshot_id=self.source_id)

    def freeze(self):
        evidence = self.root / 'packet/evidence'
        evidence.mkdir(parents=True)
        (evidence / 'gate-result.json').write_bytes(self.gate.read_bytes())
        for name in TDD_NAMES:
            (evidence / name).write_bytes((self.artifacts / name).read_bytes())
        return evidence

    def test_valid_documents_are_the_diagnostic_positive_control(self):
        self.assertEqual([], self.validate())

    def test_existing_malformed_or_nonobject_tdd_retains_schema_diagnostic(self):
        for name in TDD_NAMES:
            for content in ('{', '[]', 'null', '5'):
                with self.subTest(name=name, content=content):
                    self.write_documents()
                    (self.artifacts / name).write_text(content)
                    errors = self.validate()
                    self.assertIn('TDD_EVIDENCE_MISSING', errors)
                    self.assertIn('TDD_SCHEMA_INVALID', errors)

    def test_blocked_v11_evidence_still_reports_its_missing_baseline(self):
        for name in TDD_NAMES:
            with self.subTest(name=name):
                self.write_documents()
                path = self.artifacts / name
                document = json.loads(path.read_text())
                document['status'] = 'BLOCKED'
                document.pop('baseline')
                path.write_text(json.dumps(document))
                errors = self.validate()
                self.assertIn('TDD_EVIDENCE_MISSING', errors)
                self.assertIn('TDD_SCHEMA_INVALID', errors)
                self.assertIn('TDD_BASELINE_INVALID', errors)

    def test_blocked_evidence_preserves_errors_from_both_documents(self):
        design, sensitivity = tdd_documents()
        design.update(status='BLOCKED', red_failure_kind='import_error', acceptance_refs=[])
        sensitivity.update(status='BLOCKED', green_test_hash='c' * 64, red_outcome='PASS')
        for name, document in zip(TDD_NAMES, (design, sensitivity)):
            (self.artifacts / name).write_text(json.dumps(document))
        errors = self.validate()
        for code in ('TDD_EVIDENCE_MISSING', 'TDD_SCHEMA_INVALID', 'TDD_AC_TRACE_MISSING',
                     'TDD_RED_REASON_INVALID', 'TDD_TEST_IDENTITY_CHANGED', 'TDD_TRANSITION_INVALID'):
            self.assertIn(code, errors)
            self.assertEqual(1, errors.count(code))

    def test_unavailable_document_does_not_hide_other_document_diagnostics(self):
        for unavailable_index in (0, 1):
            for unavailable in ('missing', 'malformed', 'nonobject'):
                with self.subTest(name=TDD_NAMES[unavailable_index], unavailable=unavailable):
                    documents = list(tdd_documents())
                    documents[0]['red_failure_kind'] = 'import_error'
                    documents[1]['green_test_hash'] = 'c' * 64
                    for name, document in zip(TDD_NAMES, documents):
                        (self.artifacts / name).write_text(json.dumps(document))
                    path = self.artifacts / TDD_NAMES[unavailable_index]
                    if unavailable == 'missing':
                        path.unlink()
                    else:
                        path.write_text('{' if unavailable == 'malformed' else '[]')
                    errors = self.validate()
                    expected = ('TDD_TEST_IDENTITY_CHANGED' if unavailable_index == 0
                                else 'TDD_RED_REASON_INVALID')
                    self.assertIn('TDD_EVIDENCE_MISSING', errors)
                    self.assertIn(expected, errors)

    def test_frozen_evidence_requires_original_artifact_context(self):
        frozen = self.freeze()
        with patch('hb_eval_review.gate.compute_source_snapshot',
                   side_effect=AssertionError('must not reread live source')):
            errors = validate_gate_file(frozen / 'gate-result.json', self.repo,
                evidence_root=frozen, source_snapshot_id=self.source_id, track='feature')
            self.assertIn('TDD_EVIDENCE_MISSING', errors)
            for name in TDD_NAMES:
                (self.artifacts / name).unlink()
            self.assertEqual([], validate_gate_file(frozen / 'gate-result.json', self.repo,
                evidence_root=frozen, source_snapshot_id=self.source_id, track='feature',
                artifacts=self.artifacts))

    def test_frozen_evidence_rejects_references_to_another_issue(self):
        self.gate_data['tdd_evidence'] = [value.replace('/issue-1/', '/issue-2/')
                                          for value in self.gate_data['tdd_evidence']]
        self.gate.write_text(json.dumps(self.gate_data))
        frozen = self.freeze()
        errors = validate_gate_file(frozen / 'gate-result.json', self.repo,
            evidence_root=frozen, source_snapshot_id=self.source_id, track='feature',
            artifacts=self.artifacts)
        self.assertIn('TDD_EVIDENCE_MISSING', errors)

    def test_frozen_evidence_rejects_invalid_artifact_layout_without_traceback(self):
        frozen = self.freeze()
        for artifacts in (self.root / 'outside', self.repo / '.harness/artifacts/feature',
                          self.repo / '.harness/artifacts/feature/issue-1/../issue-2'):
            with self.subTest(artifacts=artifacts):
                errors = validate_gate_file(frozen / 'gate-result.json', self.repo,
                    evidence_root=frozen, source_snapshot_id=self.source_id, track='feature',
                    artifacts=artifacts)
                self.assertIn('TDD_EVIDENCE_MISSING', errors)


if __name__ == '__main__':
    unittest.main()
