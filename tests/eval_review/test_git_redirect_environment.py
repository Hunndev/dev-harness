"""Approved U1: reject exported Git redirection before pack/run uses Git."""
import os
import unittest
from unittest.mock import patch
import test_gate_pack_run as fixtures
from hb_eval_review import cli, pack
from hb_eval_review.snapshot import compute_source_snapshot

REDIRECT_KEYS=('GIT_DIR','GIT_COMMON_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES')
CODE='GIT_REDIRECT_ENV_UNSUPPORTED'


class GitRedirectEnvironmentTests(unittest.TestCase):
    def fixture(self):
        case=fixtures.GatePackRunTests();case.setUp();self.addCleanup(case.doCleanups)
        return case

    @staticmethod
    def clean_environment():
        return {key:value for key,value in os.environ.items() if key not in REDIRECT_KEYS}

    @staticmethod
    def pack_args(case):
        return ['pack','--repo',str(case.repo),'--artifacts',str(case.artifacts),'--request-source',case.request_name,'--base','HEAD','--claude-model','claude-test','--codex-model','codex-test']

    def test_pack_and_run_block_git_redirect_environment(self):
        case=self.fixture()
        with patch.dict(os.environ,self.clean_environment(),clear=True):
            packet=case.pack();before=compute_source_snapshot(case.repo)
        for key in REDIRECT_KEYS:
            for value in ('',str(case.base/'untrusted-redirection')):
                with self.subTest(key=key,empty=not value),patch.dict(os.environ,dict(self.clean_environment(),**{key:value}),clear=True):
                    with patch.object(pack,'_git',side_effect=AssertionError('Git must not run')) as git_call,patch.object(cli,'run_provider_stage') as provider:
                        rc,result=case.invoke(self.pack_args(case))
                    self.assertEqual(2,rc);self.assertEqual([CODE],result['errors']);git_call.assert_not_called();provider.assert_not_called()
                    with self.assertRaises(pack.ContractError) as caught:case.pack()
                    self.assertEqual([CODE],caught.exception.errors)
                    for from_mode in (True,False):
                        with patch.object(cli,'validate_packet_bindings',side_effect=AssertionError('Git must not run')) as bindings:
                            rc,result,seen=case.run_packet(from_mode)
                        self.assertEqual(2,rc);self.assertEqual([CODE],result['errors']);self.assertEqual([],seen);bindings.assert_not_called()
                    self.assertEqual(value,os.environ[key], 'the guard must not sanitize or alter the operator environment')
        with patch.dict(os.environ,self.clean_environment(),clear=True):
            self.assertEqual(before,compute_source_snapshot(case.repo));self.assertEqual(packet['source_snapshot_id'],before['source_snapshot_id'])
            rc,result,seen=case.run_packet();self.assertEqual(0,rc,result);self.assertEqual(4,len(seen))

    def test_git_redirect_cannot_select_another_worktree_or_subdirectory(self):
        case=self.fixture()
        with patch.dict(os.environ,self.clean_environment(),clear=True):
            other=case.base/'other-worktree'
            fixtures.git(case.repo,'worktree','add','-q','-b','other',str(other))
            (other/'app.py').write_text('value = 2\n');fixtures.git(other,'commit','-qam','other head')
            w1_head=fixtures.git(case.repo,'rev-parse','HEAD').decode().strip()
            w2_head=fixtures.git(other,'rev-parse','HEAD').decode().strip()
            w2_gitdir=fixtures.git(other,'rev-parse','--absolute-git-dir').decode().strip()
            self.assertNotEqual(w1_head,w2_head)
            packet=case.pack();self.assertEqual(w1_head,packet['request']['base_sha'])
        with patch.dict(os.environ,dict(self.clean_environment(),GIT_DIR=w2_gitdir),clear=True):
            # Existing snapshot helper is deliberately unchanged: this positive control
            # proves the exported value really selects W2 and why the entry guard matters.
            polluted=compute_source_snapshot(case.repo)
            self.assertEqual(w2_head,polluted['manifest']['head'])
            case.artifacts,case.request_name=fixtures.evidence_fixture(case.repo)
            rc,result=case.invoke(self.pack_args(case))
            self.assertEqual(2,rc);self.assertEqual([CODE],result['errors'])
            # Simulate a pre-guard packet that a prior version created in this environment.
            packet['source_snapshot_id']=polluted['source_snapshot_id'];packet['request']['base_sha']=w2_head
            (case.artifacts/'eval-review/diff.patch').write_bytes(pack._diff(case.repo,w2_head,polluted))
            case.rebind(packet)
            for from_mode in (True,False):
                rc,result,seen=case.run_packet(from_mode)
                self.assertEqual(2,rc);self.assertEqual([CODE],result['errors']);self.assertEqual([],seen)
        inner=case.repo/'inner';inner.mkdir()
        with patch.dict(os.environ,self.clean_environment(),clear=True):
            with self.assertRaises(pack.ContractError) as natural:pack.repository_root(inner)
            self.assertEqual(['PACKET_SOURCE_NOT_REPOSITORY_ROOT'],natural.exception.errors)
            w1_gitdir=fixtures.git(case.repo,'rev-parse','--absolute-git-dir').decode().strip()
        with patch.dict(os.environ,dict(self.clean_environment(),GIT_DIR=w1_gitdir),clear=True):
            with self.assertRaises(pack.ContractError) as redirected:pack.repository_root(inner)
            self.assertEqual([CODE],redirected.exception.errors)

if __name__=='__main__':unittest.main()
