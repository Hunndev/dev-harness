"""dev-1v3 acceptance: real repositories and frozen evidence, mocked providers only."""
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'SHARED' / 'runtime'))
from hb_eval_review import cli
from hb_eval_review.snapshot import compute_source_snapshot, compute_evidence_bundle_id, compute_packet_id
from hb_eval_review.materialize import remove_materialized_packet


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, *args):
    return subprocess.check_output(['git', *args], cwd=repo, stderr=subprocess.DEVNULL)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + '\n')


def evidence_fixture(repo, track='feature', issue_type='bug', ignored=False):
    artifacts = repo / '.harness' / 'artifacts' / track / 'case-1'
    artifacts.mkdir(parents=True, exist_ok=True)
    if ignored:
        (repo / '.gitignore').write_text('.harness/artifacts/\n')
    source_name = 'hotfix-reproduction.md' if issue_type == 'hotfix' else 'seed.md'
    (artifacts / source_name).write_text('# Request\nType: ' + issue_type + '\n## Acceptance criteria\n- AC-1: observed behavior stays correct\n')
    red, green = ('hotfix-red-log.txt', 'hotfix-green-log.txt') if issue_type == 'hotfix' else ('tdd-baseline-log.txt', 'tdd-green-log.txt')
    (artifacts / red).write_text('PASS baseline\n' if issue_type == 'refactor' else 'FAIL assertion\n')
    (artifacts / green).write_text('PASS\n')
    baseline = 'PASS_TO_PASS' if issue_type == 'refactor' else 'RED_TO_GREEN'
    design = {'schema_version':'1.1', 'baseline':baseline, 'stage':'tdd-test-design', 'tier':'T1', 'status':'PASS', 'test_id':'test_behavior', 'acceptance_refs':['AC-1'], 'assertions':[{'kind':'observable_behavior','description':'observed result'}], 'mocked_boundaries':[], 'system_under_test_mocked':False, 'paths':['success','failure'], 'reviewer':{'independent':True,'read_only':True}}
    if baseline == 'RED_TO_GREEN': design['red_failure_kind'] = 'bug_reproduced'
    sensitivity = {'schema_version':'1.1','baseline':baseline,'stage':'tdd-sensitivity','tier':'T1','status':'PASS','test_id':'test_behavior','red_test_hash':'a'*64,'green_test_hash':'a'*64,'red_outcome':'PASS' if baseline=='PASS_TO_PASS' else 'FAIL','green_outcome':'PASS','approved_red_revision':False,'high_risk':False,'mutation':{'required':False,'performed':False,'outcome':'NOT_REQUIRED'},'regression':{'status':'PASS'}}
    write_json(artifacts / 'tdd-test-design-result.json', design)
    write_json(artifacts / 'tdd-sensitivity-result.json', sensitivity)
    gate = {'schema_version':'1.1','stage':'gate','status':'PASS','source_snapshot_id':compute_source_snapshot(repo)['source_snapshot_id'],'commands':[{'name':'test','command':['python3','-m','unittest'],'exit_code':0,'duration_ms':1,'stdout_tail':'PASS','stderr_tail':'','stdout_sha256':sha(b'PASS')}], 'tdd_evidence':[(artifacts/name).relative_to(repo).as_posix() for name in ('tdd-test-design-result.json','tdd-sensitivity-result.json')]}
    write_json(artifacts / 'eval-review' / 'gate-result.json', gate)
    return artifacts, source_name


class GatePackRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.repo = self.base / 'repo'; self.repo.mkdir()
        git(self.repo, 'init', '-q')
        git(self.repo, 'config', 'user.name', 'Fixture')
        git(self.repo, 'config', 'user.email', 'fixture@example.invalid')
        (self.repo / 'app.py').write_text('value = 1\n')
        git(self.repo, 'add', '-A'); git(self.repo, 'commit', '-qm', 'fixture')
        self.artifacts, self.request_name = evidence_fixture(self.repo)
        self.packet_dir = self.artifacts / 'eval-review' / 'packet'
        self.output = self.base / 'run-output'
        self.addCleanup(lambda: remove_materialized_packet(self.output / 'materialized-packet'))

    def invoke(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try: rc = cli.main(argv)
            except SystemExit as error: self.fail('CLI rejected required dev-1v3 command: ' + str(error))
        return rc, json.loads(out.getvalue())

    def pack(self, **overrides):
        from hb_eval_review.pack import build_packet
        return build_packet(self.repo, self.artifacts, self.request_name, 'HEAD', {'claude':'claude-test','codex':'codex-test'}, **overrides)

    def run_args(self, from_mode=True):
        prefix = ['run', '--from', str(self.packet_dir)] if from_mode else ['run','--packet',str(self.packet_dir/'packet.json'),'--packet-source',str(self.repo),'--evaluate-prompt',str(self.packet_dir/'evaluate-prompt.md'),'--review-prompt',str(self.packet_dir/'review-prompt.md')]
        return prefix + ['--output-root',str(self.output),'--claude-model','claude-test','--codex-model','codex-test']

    def run_packet(self, from_mode=True):
        seen = []
        def provider(**kwargs):
            seen.append(kwargs)
            return {'semantic':{'status':'PASS'}, 'envelope':{'stage':kwargs['stage'],'engine':kwargs['engine'],'status':'PASS'}}
        def dual(runner, packet):
            records = [runner(stage, engine) for stage in ('evaluate','review') for engine in ('claude','codex')]
            return {'status':'PASS','stage':'final','final':{'status':'PASS'},'results':records}
        with patch.object(cli,'run_provider_stage',side_effect=provider), patch.object(cli,'run_dual_stages',side_effect=dual):
            rc, result = self.invoke(self.run_args(from_mode))
        return rc, result, seen

    def rebind(self, packet):
        for entry in packet['evidence_entries']:
            entry['sha256'] = sha((self.repo / entry['path']).read_bytes())
            packet['request']['evidence_digests'][Path(entry['path']).name] = entry['sha256']
            if Path(entry['path']).name == 'gate-result.json': packet['request']['gate']['sha256'] = entry['sha256']
        packet['evidence_bundle_id'] = compute_evidence_bundle_id(packet['evidence_entries'])
        packet['packet_id'] = compute_packet_id(packet['request'],packet['source_snapshot_id'],packet['evidence_bundle_id'])
        write_json(self.packet_dir/'packet.json', packet)

    def test_validate_gate_file_blocks_blocked_status_with_pass_metadata(self):
        packet = self.pack()
        gate_path = self.artifacts/'eval-review/gate-result.json'
        gate = json.loads(gate_path.read_text()); gate['status']='BLOCKED'; gate['commands'][0]['exit_code']=1
        write_json(gate_path,gate); self.rebind(packet)
        rc,result,seen=self.run_packet()
        self.assertEqual(2,rc); self.assertIn('GATE_NOT_PASSED',result['errors']); self.assertEqual([],seen)

    def test_validate_gate_file_blocks_stale_source(self):
        self.pack(); (self.repo/'app.py').write_text('value = 2\n')
        with patch.object(cli,'run_provider_stage') as provider:
            rc,result=self.invoke(['pack','--repo',str(self.repo),'--artifacts',str(self.artifacts),'--request-source',self.request_name,'--base','HEAD','--claude-model','claude-test','--codex-model','codex-test'])
        self.assertEqual(2,rc); self.assertIn('GATE_STALE',result['errors']); provider.assert_not_called()
        rc,result,seen=self.run_packet(); self.assertEqual(2,rc); self.assertIn('GATE_STALE',result['errors']); self.assertEqual([],seen)

    def test_pack_requires_track_tdd_json_valid(self):
        for track,kind in [('feature','bug'),('maintenance','bug'),('maintenance','refactor'),('maintenance','hotfix')]:
            with self.subTest(track=track,kind=kind):
                self.artifacts,self.request_name=evidence_fixture(self.repo,track,kind)
                self.pack(issue_type=kind)
                missing=self.artifacts/'tdd-sensitivity-result.json'; original=missing.read_bytes(); missing.unlink()
                with self.assertRaises(Exception) as error: self.pack(issue_type=kind)
                self.assertIn('TDD_EVIDENCE_MISSING',str(error.exception)); missing.write_bytes(original)

    def test_run_packet_and_run_from_share_gate_validator(self):
        for from_mode in (True,False):
            for failure in ('status','empty','exit','tdd','hash'):
                with self.subTest(from_mode=from_mode,failure=failure):
                    self.artifacts,self.request_name=evidence_fixture(self.repo)
                    packet=self.pack()
                    gate_path=self.artifacts/'eval-review/gate-result.json'; gate=json.loads(gate_path.read_text())
                    if failure=='status': gate['status']='BLOCKED'
                    elif failure=='empty': gate['commands']=[]
                    elif failure=='exit': gate['commands'][0]['exit_code']=1
                    elif failure=='tdd':
                        path=self.artifacts/'tdd-test-design-result.json'; d=json.loads(path.read_text()); d['status']='BLOCKED'; write_json(path,d)
                    else:
                        path=self.artifacts/'tdd-sensitivity-result.json'; d=json.loads(path.read_text()); d['green_test_hash']='b'*64; write_json(path,d)
                    write_json(gate_path,gate)
                    # Keep source/Gate identity valid so this exercises actual evidence semantics.
                    source_id=compute_source_snapshot(self.repo)['source_snapshot_id']; gate['source_snapshot_id']=source_id; write_json(gate_path,gate)
                    packet['source_snapshot_id']=source_id; self.rebind(packet)
                    rc,result,seen=self.run_packet(from_mode)
                    self.assertEqual(2,rc); self.assertEqual([],seen)
                    expected={'status':'GATE_NOT_PASSED','empty':'GATE_SCHEMA_INVALID','exit':'GATE_NOT_PASSED','tdd':'TDD_EVIDENCE_MISSING','hash':'TDD_TEST_IDENTITY_CHANGED'}[failure]
                    self.assertIn(expected,result['errors'])
                    self.assertFalse((self.output/'materialized-packet').exists())

    def test_pack_diff_excludes_only_artifacts(self):
        path=self.repo/'.harness/docs/adr.yaml'; path.parent.mkdir(parents=True); path.write_text('decision: changed\n')
        self.artifacts,self.request_name=evidence_fixture(self.repo)
        self.pack()
        diff=(self.artifacts/'eval-review/diff.patch').read_text()
        self.assertIn('.harness/docs/adr.yaml',diff); self.assertNotIn('.harness/artifacts/',diff)

    def test_pack_never_truncates_diff_silently(self):
        (self.repo/'app.py').write_text('value = '+repr('x'*500)+'\n')
        self.artifacts,self.request_name=evidence_fixture(self.repo)
        packet=self.pack(prompt_limit=80)
        self.assertTrue(packet['request']['diff_truncated'])
        prompt=(self.packet_dir/'evaluate-prompt.md').read_text()
        self.assertIn('materialized-packet/evidence/diff.patch',prompt)
        self.assertIn(packet['request']['evidence_digests']['diff.patch'],prompt)
        rc,result,seen=self.run_packet(); self.assertEqual(0,rc,result)
        copied=self.output/'materialized-packet/evidence/diff.patch'
        self.assertEqual(packet['request']['evidence_digests']['diff.patch'],sha(copied.read_bytes()))
        self.assertEqual(0o444,copied.stat().st_mode & 0o777)
        self.assertEqual(4,len(seen))
        for call in seen: self.assertEqual([self.output/'materialized-packet'],call['readable_roots'])

    def test_output_root_slug_binds_repo_identity(self):
        from hb_eval_review.pack import repository_slug, default_output_root
        sibling=self.base/'other'/'repo'; sibling.mkdir(parents=True); git(sibling,'init','-q')
        self.assertNotEqual(repository_slug(self.repo),repository_slug(sibling))
        with patch.dict(os.environ,{'HB_EVAL_REVIEW_HOME':str(self.base/'runs')}):
            output=default_output_root(self.repo,'case-1'); output.mkdir(parents=True)
            self.assertEqual('run-2',default_output_root(self.repo,'case-1').name)
            self.assertIn(repository_slug(self.repo),str(output)); self.assertIn('case-1',str(output))

    def test_packet_schema_min_items_enforced(self):
        from hb_eval_review.pack import validate_packet_schema
        packet=self.pack()
        for key in ('acceptance_refs','evidence_entries'):
            changed=json.loads(json.dumps(packet))
            (changed['request'] if key=='acceptance_refs' else changed)[key]=[]
            self.assertIn('PACKET_SCHEMA_INVALID',validate_packet_schema(changed))
            write_json(self.packet_dir/'packet.json',changed)
            rc,result,seen=self.run_packet(); self.assertEqual(2,rc); self.assertIn('PACKET_SCHEMA_INVALID',result['errors']); self.assertEqual([],seen)
        (self.artifacts/self.request_name).write_text('# No acceptance criteria\n')
        self.artifacts,self.request_name=evidence_fixture(self.repo)
        (self.artifacts/self.request_name).write_text('# No acceptance criteria\n')
        gate=json.loads((self.artifacts/'eval-review/gate-result.json').read_text()); gate['source_snapshot_id']=compute_source_snapshot(self.repo)['source_snapshot_id']; write_json(self.artifacts/'eval-review/gate-result.json',gate)
        with self.assertRaises(Exception) as error: self.pack()
        self.assertIn('PACKET_SCHEMA_INVALID',str(error.exception))
        malformed=json.loads(json.dumps(packet)); malformed['request']=[]
        write_json(self.packet_dir/'packet.json',malformed)
        for from_mode in (True,False):
            rc,result,seen=self.run_packet(from_mode)
            self.assertEqual(2,rc);self.assertIn('PACKET_SCHEMA_INVALID',result['errors']);self.assertEqual([],seen)

    def test_ignored_evidence_is_frozen_and_results_are_copied(self):
        self.artifacts,self.request_name=evidence_fixture(self.repo,ignored=True)
        self.pack(); before=compute_source_snapshot(self.repo)['source_snapshot_id']
        rc,result,seen=self.run_packet(); self.assertEqual(0,rc,result)
        frozen=self.output/'materialized-packet/evidence'
        self.assertTrue((frozen/'tdd-sensitivity-result.json').is_file())
        self.assertFalse((self.output/'materialized-packet/source'/self.artifacts.relative_to(self.repo)/'tdd-sensitivity-result.json').exists())
        copies=list((self.artifacts/'eval-review').glob('run-*'))
        self.assertEqual(1,len(copies))
        for name in ('final-result.json','execution-manifest.json'):
            self.assertEqual((self.output/name).read_bytes(),(copies[0]/name).read_bytes())
        self.assertEqual(before,compute_source_snapshot(self.repo)['source_snapshot_id'])

    def test_evidence_copy_hashes_copied_bytes_not_live_source(self):
        from hb_eval_review.pack import materialize_evidence
        packet=self.pack(); target=self.output/'materialized-packet'
        original=Path.read_bytes; live=self.artifacts/'eval-review/diff.patch'; read_count=[]
        def read(path):
            data=original(path)
            if path==live:
                read_count.append(path); live.write_bytes(b'changed after reading')
            return data
        with patch.object(Path,'read_bytes',read):
            copied=materialize_evidence(self.repo,target,packet['evidence_entries'])
        self.assertEqual(1,len(read_count)); self.assertEqual(packet['request']['evidence_digests']['diff.patch'],sha((copied/'diff.patch').read_bytes()))
        self.assertNotEqual(live.read_bytes(),(copied/'diff.patch').read_bytes())
        # A corrupt write must fail even though the original bytes still match the packet.
        from hb_eval_review.snapshot import PacketPolicyError
        live.write_bytes((copied/'diff.patch').read_bytes())
        remove_materialized_packet(target)
        original_write=Path.write_bytes
        def corrupt_copy(path,data):
            return original_write(path,b'corrupt copy' if path==target/'evidence/diff.patch' else data)
        with patch.object(Path,'write_bytes',corrupt_copy):
            with self.assertRaises(PacketPolicyError) as caught:
                materialize_evidence(self.repo,target,packet['evidence_entries'])
        self.assertEqual('EVIDENCE_COPY_MISMATCH',caught.exception.code)

    def test_evidence_failure_and_cleanup_failure_preserve_codes_and_paths(self):
        from hb_eval_review.snapshot import PacketPolicyError
        self.artifacts,self.request_name=evidence_fixture(self.repo,ignored=True)
        self.pack()
        actual_copy=cli.materialize_evidence
        def change_before_copy(*args):
            path=self.artifacts/'tdd-sensitivity-result.json'
            original=path.read_bytes();path.write_bytes(original+b' ')
            return actual_copy(*args)
        with patch.object(cli,'materialize_evidence',side_effect=change_before_copy):
            rc,result,seen=self.run_packet()
        self.assertEqual(2,rc);self.assertEqual(['EVIDENCE_COPY_MISMATCH'],result['errors']);self.assertEqual([],seen)
        self.assertFalse((self.output/'materialized-packet').exists())
        self.artifacts,self.request_name=evidence_fixture(self.repo,ignored=True)
        self.pack()
        with patch.object(cli,'materialize_evidence',side_effect=PacketPolicyError('EVIDENCE_COPY_MISMATCH',['diff.patch'])), patch.object(cli,'remove_materialized_packet',side_effect=PermissionError('detail')):
            rc,result,seen=self.run_packet()
        self.assertEqual(2,rc); self.assertEqual(['EVIDENCE_COPY_MISMATCH','MATERIALIZED_PACKET_REMOVE_FAILED'],result['errors']); self.assertEqual(['diff.patch'],result['paths']); self.assertEqual([],seen)

    def test_pack_validates_the_bytes_it_binds_after_a_live_evidence_change(self):
        from hb_eval_review import pack as pack_module
        self.artifacts,self.request_name=evidence_fixture(self.repo,ignored=True)
        real_validate=pack_module.validate_gate_file
        calls=[]
        def change_after_validate(*args,**kwargs):
            result=real_validate(*args,**kwargs)
            calls.append(True)
            if len(calls)==1:
                path=self.artifacts/'tdd-sensitivity-result.json'
                data=json.loads(path.read_text());data['green_test_hash']='b'*64;write_json(path,data)
            return result
        with patch.object(pack_module,'validate_gate_file',side_effect=change_after_validate):
            with self.assertRaises(Exception) as caught: self.pack()
        self.assertIn('TDD_TEST_IDENTITY_CHANGED',str(caught.exception))
        self.assertFalse((self.packet_dir/'packet.json').exists())

    def test_cleanup_removes_sibling_evidence_already_supported(self):
        # Existing behavior control: first execution passes before implementation.
        root=self.output/'materialized-packet'; evidence=root/'evidence'; evidence.mkdir(parents=True)
        (evidence/'diff.patch').write_text('diff'); (evidence/'diff.patch').chmod(0o444); evidence.chmod(0o555)
        remove_materialized_packet(root); self.assertFalse(root.exists())

if __name__ == '__main__': unittest.main()
