"""Claude F5: exercise each argument guard through public CLI entrypoints."""
import json
import os
import unittest
from unittest.mock import patch
import test_gate_pack_run as fixtures
from hb_eval_review import cli


class CliArgumentTests(unittest.TestCase):
    def fixture(self):
        case=fixtures.GatePackRunTests();case.setUp();self.addCleanup(case.doCleanups)
        return case

    @staticmethod
    def without(argv,*flags):
        values=list(argv)
        for flag in flags:
            index=values.index(flag);del values[index:index+2]
        return values

    @staticmethod
    def environment():
        return {k:v for k,v in os.environ.items() if k not in ('CLAUDE_MODEL_ID','CODEX_MODEL_ID')}

    @staticmethod
    def pack_args(case):
        return ['pack','--repo',str(case.repo),'--artifacts',str(case.artifacts),'--request-source',case.request_name,'--base','HEAD']

    def test_legacy_run_requires_each_of_the_seven_arguments_before_provider(self):
        case=self.fixture();case.pack()
        flags=('--packet','--packet-source','--evaluate-prompt','--review-prompt','--output-root','--claude-model','--codex-model')
        for flag in flags:
            with self.subTest(missing=flag),patch.dict(os.environ,self.environment(),clear=True),patch.object(cli,'run_provider_stage') as provider:
                rc,result=case.invoke(self.without(case.run_args(False),flag))
                self.assertEqual(2,rc);self.assertEqual(['RUN_ARGUMENTS_MISSING'],result['errors']);provider.assert_not_called()
        rc,result,seen=case.run_packet(False);self.assertEqual(0,rc,result);self.assertEqual(4,len(seen))

    def test_from_and_packet_conflict_is_rejected_before_provider(self):
        case=self.fixture();case.pack()
        with patch.object(cli,'run_provider_stage') as provider:
            rc,result=case.invoke(case.run_args()+['--packet',str(case.packet_dir/'packet.json')])
        self.assertEqual(2,rc);self.assertEqual(['RUN_ARGUMENT_CONFLICT'],result['errors']);provider.assert_not_called()

    def test_pack_uses_explicit_environment_model_ids(self):
        case=self.fixture()
        with patch.dict(os.environ,dict(self.environment(),CLAUDE_MODEL_ID='env-claude',CODEX_MODEL_ID='env-codex'),clear=True):
            rc,result=case.invoke(self.pack_args(case))
        self.assertEqual(0,rc,result)
        packet=json.loads((case.packet_dir/'packet.json').read_text())
        self.assertEqual({'claude':'env-claude','codex':'env-codex'},packet['request']['model_ids'])

    def test_from_uses_environment_model_ids_and_compares_packet_models(self):
        case=self.fixture();case.pack();original=case.run_args
        case.run_args=lambda mode=True:self.without(original(mode),'--claude-model','--codex-model')
        env=dict(self.environment(),CLAUDE_MODEL_ID='claude-test',CODEX_MODEL_ID='codex-test')
        with patch.dict(os.environ,env,clear=True):
            rc,result,seen=case.run_packet()
        self.assertEqual(0,rc,result);self.assertEqual(4,len(seen))
        case.output=case.base/'mismatched-model-output'
        env['CODEX_MODEL_ID']='different-codex'
        with patch.dict(os.environ,env,clear=True):
            rc,result,seen=case.run_packet()
        self.assertEqual(2,rc);self.assertEqual(['MODEL_ID_MISMATCH'],result['errors']);self.assertEqual([],seen)

    def test_pack_without_operator_model_ids_is_explicitly_blocked(self):
        case=self.fixture()
        with patch.dict(os.environ,self.environment(),clear=True),patch.object(cli,'run_provider_stage') as provider:
            rc,result=case.invoke(self.pack_args(case))
        self.assertEqual(2,rc);self.assertEqual(['MODEL_ID_REQUIRED'],result['errors']);provider.assert_not_called()

if __name__=='__main__':unittest.main()
