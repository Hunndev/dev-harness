"""Observed Green binds current SUT, including the public frozen-evidence path."""
import contextlib
import hashlib
import io
import json
import shlex
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_tdd_check as fixtures
from hb_eval_review import cli
from hb_eval_review.gate import generate_gate, validate_gate_file
from hb_eval_review.pack import build_packet, ContractError
from hb_eval_review.snapshot import (compute_source_snapshot, compute_evidence_bundle_id,
                                     compute_packet_id)


class TddSutBindingTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.TddCheckTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.repo, self.out = self.case.repo, self.case.out
        self.case.red()
        self.case.fix()
        result, payload = self.case.call('green')
        self.assertEqual(0, result, payload)
        (self.out / 'seed.md').write_text('# Request\nType: feature\n## Acceptance criteria\n- AC-1: returns correct value\n')
        self.gate = self.out / 'eval-review/gate-result.json'
        self.command = shlex.join([sys.executable, '-c', 'print("checks pass")'])
        self.assertEqual('PASS', generate_gate(self.repo, [self.command], self.gate, issue_type='feature')['status'])

    def invoke(self, args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = cli.main(args)
        return rc, json.loads(output.getvalue())

    def pack(self):
        return build_packet(self.repo, self.out, 'seed.md', 'HEAD',
                            {'claude': 'claude-test', 'codex': 'codex-test'}, issue_type='feature')

    def test_green_sut_allows_own_evidence_writes_but_not_source_or_sibling_artifacts(self):
        (self.out / 'review-notes.md').write_text('generated after Green\n')
        self.assertEqual('PASS', generate_gate(self.repo, [self.command], self.gate, issue_type='feature')['status'])
        for path in (self.repo / 'app.py', self.out.with_name('issue-10') / 'note.md',
                     self.repo / '.harness/docs/adr.md'):
            with self.subTest(path=str(path)):
                old = path.read_bytes() if path.exists() else None
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('changed SUT\n')
                result = generate_gate(self.repo, [self.command], self.gate, issue_type='feature')
                self.assertEqual('BLOCKED', result['status'])
                self.assertIn('TDD_SOURCE_CHANGED', result['errors'])
                if old is None:
                    path.unlink()
                else:
                    path.write_bytes(old)

    def test_public_pack_cannot_refresh_gate_around_stale_green(self):
        (self.repo / 'app.py').write_text('value = 3\n')
        gate = json.loads(self.gate.read_text())
        gate['source_snapshot_id'] = compute_source_snapshot(self.repo)['source_snapshot_id']
        self.gate.write_text(json.dumps(gate))
        rc, result = self.invoke(['pack', '--repo', str(self.repo), '--artifacts', str(self.out),
            '--request-source', 'seed.md', '--base', 'HEAD', '--issue-type', 'feature',
            '--claude-model', 'claude-test', '--codex-model', 'codex-test'])
        self.assertEqual(2, rc, result)
        self.assertIn('TDD_SOURCE_CHANGED', result['errors'])

    def test_both_public_run_modes_reject_rebound_stale_green_without_providers(self):
        packet = self.pack()
        (self.repo / 'app.py').write_text('value = 3\n')
        snapshot = compute_source_snapshot(self.repo)
        gate = json.loads(self.gate.read_text())
        gate['source_snapshot_id'] = snapshot['source_snapshot_id']
        self.gate.write_text(json.dumps(gate))
        packet['source_snapshot_id'] = snapshot['source_snapshot_id']
        for entry in packet['evidence_entries']:
            entry['sha256'] = hashlib.sha256((self.repo / entry['path']).read_bytes()).hexdigest()
            packet['request']['evidence_digests'][Path(entry['path']).name] = entry['sha256']
            if Path(entry['path']).name == 'gate-result.json':
                packet['request']['gate']['sha256'] = entry['sha256']
        packet['evidence_bundle_id'] = compute_evidence_bundle_id(packet['evidence_entries'])
        packet['packet_id'] = compute_packet_id(packet['request'], packet['source_snapshot_id'], packet['evidence_bundle_id'])
        packet_dir = self.out / 'eval-review/packet'
        (packet_dir / 'packet.json').write_text(json.dumps(packet))
        for from_mode in (True, False):
            with self.subTest(from_mode=from_mode):
                args = ['run', '--from', str(packet_dir)] if from_mode else [
                    'run', '--packet', str(packet_dir / 'packet.json'), '--packet-source', str(self.repo),
                    '--evaluate-prompt', str(packet_dir / 'evaluate-prompt.md'),
                    '--review-prompt', str(packet_dir / 'review-prompt.md')]
                args += ['--output-root', str(self.case.root / ('run-' + str(from_mode))),
                         '--claude-model', 'claude-test', '--codex-model', 'codex-test']
                with patch.object(cli, 'run_provider_stage') as provider:
                    rc, result = self.invoke(args)
                self.assertEqual(2, rc, result)
                self.assertIn('TDD_SOURCE_CHANGED', result['errors'])
                provider.assert_not_called()

    def test_frozen_validation_uses_verified_manifest_without_live_read(self):
        snapshot = compute_source_snapshot(self.repo)
        frozen = self.case.root / 'frozen'
        frozen.mkdir()
        for name, source in [('gate-result.json', self.gate),
                             ('tdd-test-design-result.json', self.out / 'tdd-test-design-result.json'),
                             ('tdd-sensitivity-result.json', self.out / 'tdd-sensitivity-result.json')]:
            (frozen / name).write_bytes(source.read_bytes())
        (self.repo / 'app.py').write_text('value = 3\n')
        with patch('hb_eval_review.gate.compute_source_snapshot', side_effect=AssertionError('live reread')):
            errors = validate_gate_file(frozen / 'gate-result.json', self.repo, evidence_root=frozen,
                source_snapshot_id=snapshot['source_snapshot_id'], source_manifest=snapshot['manifest'],
                track='feature', issue_type='feature', artifacts=self.out)
        self.assertEqual([], errors)


if __name__ == '__main__':
    unittest.main()
