"""D1: every decisive consumer requires the observed 1.2 evidence pair."""
import copy
import json
import shlex
import sys
import unittest

import test_gate_pack_run as packet_fixtures
import test_tdd_check as observed_fixtures
from test_gate import tdd_documents
from hb_eval_review.gate import generate_gate, validate_gate_file
from hb_eval_review.snapshot import compute_source_snapshot


NAMES = ('tdd-test-design-result.json', 'tdd-sensitivity-result.json')
REQUIRED = 'TDD_OBSERVATION_REQUIRED'


class ConsumerObservationTests(unittest.TestCase):
    def observed_case(self):
        observed = observed_fixtures.TddCheckTests()
        observed.setUp()
        self.addCleanup(observed.doCleanups)
        observed.red()
        observed.fix()
        rc, payload = observed.call('green')
        self.assertEqual(0, rc, payload)
        case = packet_fixtures.GatePackRunTests()
        case.repo, case.artifacts, case.base = observed.repo, observed.out, observed.root
        case.packet_dir = case.artifacts / 'eval-review/packet'
        case.request_name = 'seed.md'
        case.output = case.base / 'consumer-run'
        self.addCleanup(lambda: packet_fixtures.remove_materialized_packet(case.output / 'materialized-packet'))
        (case.artifacts / case.request_name).write_text(
            '# Request\nType: feature\n## Acceptance criteria\n- AC-1: corrected value\n')
        gate_path = case.artifacts / 'eval-review/gate-result.json'
        command = shlex.join([sys.executable, '-c', 'print("checks pass")'])
        gate = generate_gate(case.repo, [command], gate_path, issue_type='feature')
        self.assertEqual('PASS', gate['status'], gate)
        return observed, case, gate_path, command, case.pack(issue_type='feature')

    def test_consumers_require_observed_pair(self):
        for scenario in ('hand-written-1.0', 'hand-written-1.1',
                         'downgraded-after-source-change', 'downgraded-after-failed-green'):
            observed, case, gate_path, command, packet = self.observed_case()
            prompts = {stage: (case.packet_dir / (stage + '-prompt.md')).read_bytes()
                       for stage in ('evaluate', 'review')}
            documents = [json.loads((case.artifacts / name).read_text()) for name in NAMES]
            if scenario.startswith('hand-written'):
                documents = tdd_documents(version=scenario.rsplit('-', 1)[-1])
                for name in ('tdd-baseline-log.txt', 'tdd-green-log.txt'):
                    (case.artifacts / name).write_text('marker only, nothing executed\n')
            else:
                (case.repo / 'app.py').write_text('value = 3\n')
                if scenario.endswith('failed-green'):
                    rc, payload = observed.call('green')
                    self.assertEqual(2, rc, payload)
                    self.assertIn('TDD_TRANSITION_INVALID', payload['errors'])
                    self.assertEqual('BLOCKED', json.loads((case.artifacts / NAMES[1]).read_text())['status'])
                control = generate_gate(case.repo, [command], gate_path, issue_type='feature')
                self.assertIn('TDD_EVIDENCE_MISSING' if scenario.endswith('failed-green')
                              else 'TDD_SOURCE_CHANGED', control['errors'])
                # Replaying the previous PASS as a legacy self-report must not
                # discard source binding or the failed Green invalidation.
                documents = copy.deepcopy(documents)
                for document in documents:
                    document.pop('observed')
                    document['schema_version'] = '1.1'
            for name, document in zip(NAMES, documents):
                path = case.artifacts / name
                path.chmod(0o600)
                packet_fixtures.write_json(path, document)

            generated = generate_gate(case.repo, [command], gate_path, issue_type='feature')
            with self.subTest(scenario=scenario, consumer='generate_gate'):
                self.assertEqual('BLOCKED', generated['status'], generated)
                self.assertIn(REQUIRED, generated['errors'])

            # A stale producer may still supply PASS metadata. Each consumer
            # must inspect the pair itself even with fresh outer packet hashes.
            generated['status'] = 'PASS'
            generated.pop('errors', None)
            packet_fixtures.write_json(gate_path, generated)
            with self.subTest(scenario=scenario, consumer='validate_gate_file'):
                self.assertIn(REQUIRED, validate_gate_file(gate_path, case.repo, issue_type='feature'))
            args = ['pack', '--repo', str(case.repo), '--artifacts', str(case.artifacts),
                    '--request-source', case.request_name, '--base', 'HEAD',
                    '--claude-model', 'claude-test', '--codex-model', 'codex-test']
            with self.subTest(scenario=scenario, consumer='pack'):
                rc, result = case.invoke(args)
                self.assertEqual(2, rc, result)
                self.assertEqual('BLOCKED', result['status'])
                self.assertIn(REQUIRED, result['errors'])
            packet['source_snapshot_id'] = compute_source_snapshot(case.repo)['source_snapshot_id']
            for stage, content in prompts.items():
                (case.packet_dir / (stage + '-prompt.md')).write_bytes(content)
            case.rebind(packet)
            for from_mode in (True, False):
                with self.subTest(scenario=scenario, consumer='run --from' if from_mode else 'run --packet'):
                    case.output = case.base / ('consumer-run-' + str(from_mode))
                    rc, result, providers = case.run_packet(from_mode)
                    self.assertEqual(2, rc, result)
                    self.assertEqual('BLOCKED', result['status'])
                    self.assertIn(REQUIRED, result['errors'])
                    self.assertEqual([], providers)

    def test_observed_v12_golden_pair_reaches_both_run_modes(self):
        _, case, _, _, _ = self.observed_case()
        for name in NAMES:
            document = json.loads((case.artifacts / name).read_text())
            self.assertEqual('1.2', document['schema_version'])
            self.assertEqual(1, document['observed']['executed'])
        for from_mode in (True, False):
            with self.subTest(from_mode=from_mode):
                case.output = case.base / ('golden-run-' + str(from_mode))
                rc, result, providers = case.run_packet(from_mode)
                self.assertEqual(0, rc, result)
                self.assertEqual('PASS', result['status'])
                self.assertEqual(4, len(providers))


if __name__ == '__main__':
    unittest.main()
