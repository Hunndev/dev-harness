"""Synthetic 1.2 contract fixtures for consumer tests, never execution evidence.

Producer/golden tests execute their miniature runner. These fixtures isolate the
consumer contracts and bind their simulated observations to the fixture context.
"""
import copy
import hashlib
from pathlib import Path

from hb_eval_review.snapshot import compute_source_snapshot, compute_tdd_sut_sha256
from hb_eval_review.tdd_quality import canonical_design_bytes


def observed_pair(design, sensitivity, repo=None, artifacts=None, snapshot=None):
    design, sensitivity = copy.deepcopy(design), copy.deepcopy(sensitivity)
    if snapshot is None:
        snapshot = (compute_source_snapshot(repo) if repo is not None else
                    {'source_snapshot_id': 'a' * 64, 'manifest': {'files': []}})
    repo = Path(repo or '/synthetic-consumer-fixture').resolve()
    artifacts = Path(artifacts or repo / '.harness/artifacts/feature/issue-1').resolve()
    baseline = design.get('baseline', 'RED_TO_GREEN')
    context = {
        'argv': ['fixture-runner', 'test_behavior.py'], 'cwd': str(repo),
        'git_dir': str(repo / '.git'), 'artifacts': str(artifacts),
        'test_file': 'test_behavior.py', 'selected_tests': ['test_behavior.py::test_behavior'],
        'executed': 1, 'recorded_at': '2026-09-23T00:00:00Z',
        'test_file_sha256': sensitivity['red_test_hash'],
        'run_id': hashlib.sha256(str(artifacts).encode()).hexdigest()[:32],
        'source_snapshot_id': snapshot['source_snapshot_id'],
        'sut_sha256': compute_tdd_sut_sha256(snapshot['manifest'], artifacts.relative_to(repo)),
    }
    design.update(schema_version='1.2', baseline=baseline,
                  observed=dict(context, exit_code=0 if baseline == 'PASS_TO_PASS' else 1))
    sensitivity.update(schema_version='1.2', baseline=baseline,
                       observed=dict(context, exit_code=0,
                                     test_file_sha256=sensitivity['green_test_hash'],
                                     baseline_sha256=hashlib.sha256(canonical_design_bytes(design)).hexdigest()))
    return design, sensitivity
