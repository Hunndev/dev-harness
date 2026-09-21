"""Fresh-review regressions: required evidence membership and original artifact paths."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'SHARED/runtime'))
import test_gate_pack_run as fixtures
from hb_eval_review import cli, pack


class EvidenceCatalogTests(unittest.TestCase):
    def fixture(self, kind='bug'):
        case = fixtures.GatePackRunTests(); case.setUp()
        self.addCleanup(case.doCleanups)
        case.artifacts, case.request_name = fixtures.evidence_fixture(case.repo, 'maintenance' if kind=='hotfix' else 'feature', kind, ignored=True)
        case.packet_dir = case.artifacts / 'eval-review/packet'
        return case, case.pack(issue_type=kind)

    def test_each_required_log_is_enforced_by_both_run_entrypoints(self):
        for kind,names in [('bug',('tdd-baseline-log.txt','tdd-green-log.txt')),('hotfix',('hotfix-red-log.txt','hotfix-green-log.txt'))]:
            for missing in [(names[0],),(names[1],),names]:
                for from_mode in (True,False):
                    with self.subTest(kind=kind,missing=missing,from_mode=from_mode):
                        case,packet=self.fixture(kind)
                        for name in missing:
                            (case.artifacts/name).unlink();packet['request']['evidence_digests'].pop(name)
                        packet['evidence_entries']=[e for e in packet['evidence_entries'] if Path(e['path']).name not in missing]
                        case.rebind(packet)
                        with patch.object(cli,'materialize_evidence',wraps=cli.materialize_evidence) as copy:
                            rc,result,seen=case.run_packet(from_mode)
                        self.assertEqual(2,rc,result);self.assertIn('TDD_EVIDENCE_MISSING',result['errors']);self.assertEqual([],seen);copy.assert_not_called()

    def test_extra_ignored_secret_shaped_evidence_is_rejected_before_read_or_copy(self):
        for from_mode in (True,False):
            with self.subTest(from_mode=from_mode):
                case,packet=self.fixture();secret=case.artifacts/'.env';secret.write_text('SYNTHETIC_ONLY=never-copy\n')
                packet['evidence_entries'].append({'path':secret.relative_to(case.repo).as_posix(),'sha256':fixtures.sha(secret.read_bytes())})
                case.rebind(packet)
                reads=[];original=Path.read_bytes
                def read(path): reads.append(path);return original(path)
                with patch.object(Path,'read_bytes',read),patch.object(cli,'materialize_evidence',wraps=cli.materialize_evidence) as copy:
                    rc,result,seen=case.run_packet(from_mode)
                self.assertEqual(2,rc,result);self.assertEqual([],seen);self.assertIn('EVIDENCE_ENTRY_UNEXPECTED',result['errors']);self.assertNotIn(secret,reads);copy.assert_not_called()
                self.assertFalse((case.output/'materialized-packet/evidence/.env').exists())

    def test_entries_cannot_substitute_another_artifact_id(self):
        for from_mode in (True,False):
            with self.subTest(from_mode=from_mode):
                case,packet=self.fixture();other=case.artifacts.with_name('case-2')
                for entry in packet['evidence_entries']:
                    original=case.repo/entry['path'];moved=other/original.relative_to(case.artifacts)
                    moved.parent.mkdir(parents=True,exist_ok=True);moved.write_bytes(original.read_bytes())
                    entry['path']=moved.relative_to(case.repo).as_posix()
                gate_path=other/'eval-review/gate-result.json';data=json.loads(gate_path.read_text());data['tdd_evidence']=[value.replace('/case-1/','/case-2/') for value in data['tdd_evidence']];fixtures.write_json(gate_path,data)
                packet['request']['gate']['path']=gate_path.relative_to(case.repo).as_posix();case.rebind(packet)
                rc,result,seen=case.run_packet(from_mode)
                self.assertEqual(2,rc,result);self.assertEqual([],seen);self.assertIn('ARTIFACT_EVIDENCE_MISMATCH',result['errors'])

    def test_frozen_gate_references_must_name_the_actual_packet_entries(self):
        for from_mode in (True,False):
            with self.subTest(from_mode=from_mode):
                case,packet=self.fixture();path=case.artifacts/'eval-review/gate-result.json';data=json.loads(path.read_text())
                data['tdd_evidence']=[value.replace('/case-1/','/nonexistent-id/') for value in data['tdd_evidence']];fixtures.write_json(path,data);case.rebind(packet)
                rc,result,seen=case.run_packet(from_mode)
                self.assertEqual(2,rc,result);self.assertEqual([],seen);self.assertIn('TDD_EVIDENCE_MISSING',result['errors'])
                self.assertFalse((case.output/'materialized-packet').exists())

    def test_pack_checks_original_gate_references_after_freezing(self):
        case,_=self.fixture();(case.packet_dir/'packet.json').unlink();original=pack._read_safe
        def change_gate(root,relative):
            if relative.endswith('gate-result.json'):
                path=root/relative;data=json.loads(path.read_text());data['tdd_evidence']=[p.replace('/case-1/','/nonexistent-id/') for p in data['tdd_evidence']];fixtures.write_json(path,data)
            return original(root,relative)
        with patch.object(pack,'_read_safe',side_effect=change_gate):
            with self.assertRaises(pack.ContractError) as caught:case.pack()
        self.assertIn('TDD_EVIDENCE_MISSING',caught.exception.errors)
        self.assertFalse((case.packet_dir/'packet.json').exists())

    def test_duplicate_entries_and_extra_digest_names_are_rejected(self):
        for corruption in ('duplicate','extra-digest'):
            for from_mode in (True,False):
                with self.subTest(corruption=corruption,from_mode=from_mode):
                    case,packet=self.fixture()
                    if corruption=='duplicate':packet['evidence_entries'].append(dict(packet['evidence_entries'][0]))
                    else:packet['request']['evidence_digests']['unexpected']='a'*64
                    case.rebind(packet);rc,result,seen=case.run_packet(from_mode)
                    self.assertEqual(2,rc,result);self.assertEqual([],seen)
                    self.assertIn('EVIDENCE_ENTRY_DUPLICATE' if corruption=='duplicate' else 'EVIDENCE_DIGESTS_INVALID',result['errors'])

    def test_pack_rejects_live_source_aba_during_diff_capture(self):
        from hb_eval_review.snapshot import PacketPolicyError
        case,_=self.fixture();(case.packet_dir/'packet.json').unlink()
        original_diff=pack._diff;original_source=(case.repo/'app.py').read_bytes()
        def transient(repo,base,snapshot=None):
            (repo/'app.py').write_text('transient source not checked by Gate\n')
            try:
                return original_diff(repo,base,snapshot) if snapshot is not None else original_diff(repo,base)
            finally:
                (repo/'app.py').write_bytes(original_source)
        with patch.object(pack,'_diff',side_effect=transient):
            with self.assertRaises(PacketPolicyError) as caught:case.pack()
        self.assertEqual('DIFF_SOURCE_MISMATCH',caught.exception.code)
        self.assertEqual(original_source,(case.repo/'app.py').read_bytes())
        self.assertFalse((case.packet_dir/'packet.json').exists())

    def test_secret_shaped_artifact_components_cannot_bypass_source_policy(self):
        from hb_eval_review.snapshot import PacketPolicyError
        for identifier in ('secrets','case.pem','.env.case'):
            for from_mode in (True,False):
                with self.subTest(identifier=identifier,from_mode=from_mode):
                    case,packet=self.fixture();old=case.artifacts;new=old.with_name(identifier)
                    old.rename(new);case.artifacts=new;case.packet_dir=new/'eval-review/packet'
                    original_prefix=old.relative_to(case.repo).as_posix()
                    new_prefix=new.relative_to(case.repo).as_posix()
                    packet['request']['artifacts']=new_prefix;packet['request']['identifier']=identifier
                    packet['request']['gate']['path']=packet['request']['gate']['path'].replace(original_prefix,new_prefix)
                    for entry in packet['evidence_entries']:entry['path']=entry['path'].replace(original_prefix,new_prefix)
                    path=new/'eval-review/gate-result.json';data=json.loads(path.read_text());data['tdd_evidence']=[value.replace(original_prefix,new_prefix) for value in data['tdd_evidence']];fixtures.write_json(path,data);case.rebind(packet)
                    with self.assertRaises(PacketPolicyError) as caught:case.pack()
                    self.assertEqual('PACKET_SECRET_MATERIAL_PRESENT',caught.exception.code)
                    with patch.object(cli,'materialize_evidence',wraps=cli.materialize_evidence) as copy:
                        rc,result,seen=case.run_packet(from_mode)
                    self.assertEqual(2,rc,result);self.assertIn('PACKET_SECRET_MATERIAL_PRESENT',result['errors']);self.assertEqual([],seen);copy.assert_not_called()

if __name__=='__main__':unittest.main()
