"""Claude F3/F4: normalize issue declarations and keep actual acceptance criteria."""
import os
import unittest
from unittest.mock import patch
import test_gate_pack_run as fixtures
from hb_eval_review import cli, pack


class RequestParsingTests(unittest.TestCase):
    def fixture(self, kind='bug'):
        case=fixtures.GatePackRunTests();case.setUp();self.addCleanup(case.doCleanups)
        case.artifacts,case.request_name=fixtures.evidence_fixture(case.repo,'maintenance',kind,ignored=True)
        case.packet_dir=case.artifacts/'eval-review/packet'
        return case

    def pack_args(self,case):
        return ['pack','--repo',str(case.repo),'--artifacts',str(case.artifacts),'--request-source',case.request_name,'--base','HEAD','--claude-model','claude-test','--codex-model','codex-test']

    def test_capitalized_issue_types_are_normalized_before_contract_checks(self):
        for kind in ('bug','refactor'):
            for explicit in (False,True):
                with self.subTest(kind=kind,explicit=explicit):
                    case=self.fixture(kind);path=case.artifacts/case.request_name
                    path.write_text(path.read_text().replace('Type: '+kind,'Type: '+kind.title()))
                    args=self.pack_args(case)+(['--issue-type',kind] if explicit else [])
                    rc,result=case.invoke(args);self.assertEqual(0,rc,result)
                    packet=cli._load(str(case.packet_dir/'packet.json'))
                    self.assertEqual(kind,packet['request']['issue_type'])
                    rc,result,seen=case.run_packet();self.assertEqual(0,rc,result);self.assertEqual(4,len(seen))

    def test_issue_type_conflict_is_distinct_from_baseline_mismatch(self):
        case=self.fixture()
        for requested in ('refactor','hotfix'):
            with self.subTest(requested=requested),patch.object(cli,'run_provider_stage') as provider:
                rc,result=case.invoke(self.pack_args(case)+['--issue-type',requested])
                self.assertEqual(2,rc);self.assertEqual(['ISSUE_TYPE_CONFLICT'],result['errors']);provider.assert_not_called()
                self.assertNotIn('TDD_BASELINE_MISMATCH',result['errors'])

    def test_acceptance_combines_explicit_rows_with_heading_lists_and_ignores_prose(self):
        text='# Request\nSee AC-7 in the old ticket.\n- AC-1: explicit first\n| AC-2: table first | evidence |\n## Acceptance criteria\n- works offline\n1. keeps data\n- AC-3: no duplicates\n'
        self.assertEqual(['- AC-1: explicit first','AC-2: table first | evidence','- works offline','1. keeps data','- AC-3: no duplicates'],pack._acceptance(text))
        self.assertEqual(['AC-1|Must pass'],pack._acceptance('|ID|Criterion|\n|---|---|\n|AC-1|Must pass|\n'))
        self.assertEqual(['AC-1 | Must pass'],pack._acceptance('ID | Criterion\n--- | ---\nAC-1 | Must pass\n'))
        self.assertEqual([],pack._acceptance('Note: old criteria\nAC-1 | rejected in old ticket\n'))

    def test_acceptance_excludes_backtick_and_tilde_fences(self):
        for fence in ('```','~~~'):
            for indent in ('','    '):
                with self.subTest(fence=fence,indent=len(indent)):
                    text='# Request\n- Example syntax:\n'+indent+fence+'sh\n'+indent+'export AC_POWER=1\n'+indent+'- AC-9: example not a criterion\n'+indent+fence+'\n## Acceptance criteria\n- works offline\n'
                    self.assertEqual(['- works offline'],pack._acceptance(text))

    def test_prose_only_ac_mention_cannot_satisfy_packet_schema(self):
        case=self.fixture();(case.artifacts/case.request_name).write_text('# Request\nType: bug\nNote: AC-1 from the old ticket was rejected.\n')
        with patch.object(cli,'run_provider_stage') as provider:
            rc,result=case.invoke(self.pack_args(case))
        self.assertEqual(2,rc);self.assertIn('PACKET_SCHEMA_INVALID',result['errors']);provider.assert_not_called()

if __name__=='__main__':unittest.main()
