import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from generate_authority_cases import generate, write_set, PATTERNS, canonical

class GeneratorTests(unittest.TestCase):
    def test_repeatability(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'a'; b=Path(td)/'b'
            x=write_set(47,2,a); y=write_set(47,2,b)
            self.assertEqual(x,y)
            self.assertEqual(sorted(p.name for p in a.iterdir()),sorted(p.name for p in b.iterdir()))
            for p in a.iterdir(): self.assertEqual(p.read_bytes(),(b/p.name).read_bytes())
    def test_different_seed_changes_fictions(self):
        a,_=generate(1,2); b,_=generate(2,2)
        self.assertNotEqual([x['source_inventory_text'] for x in a],[x['source_inventory_text'] for x in b])
    def test_count_uniqueness(self):
        for n in (1,3):
            c,o=generate(9,n)
            self.assertEqual(len(c),6*n);self.assertEqual(len(o),6*n)
            self.assertEqual(set(x['pattern'] for x in c),set(PATTERNS))
            self.assertEqual(len(set(x['case_id'] for x in c)),len(c))
    def test_grants_and_deliberate_invalids(self):
        c,o=generate(42,1)
        for case in c:
            grantids={g['grant_id'] for g in case['grants']}
            for e in case['events']:
                self.assertTrue(set(e['authority_grant_ids']) <=grantids)
                if e['authority_grant_ids']: self.assertTrue(e['principal_id'] in [g['grantee'] for g in case['grants'] if g['grant_id'] in e['authority_grant_ids']])
        self.assertFalse(c[-1]['grants'])
    def test_temporal_fields(self):
        c,_=generate(42,1)
        for x in c:
            for e in x['events']: self.assertGreaterEqual(e['recorded_at'],e['valid_at'])
        self.assertGreater(c[4]['events'][1]['valid_at'],c[4]['query_at'])
    def test_conflict_all_evidence(self):
        c,o=generate(12,1)
        self.assertEqual(o[2]['expected_resolution'],'CONFLICT_UNRESOLVED')
        self.assertEqual(set(o[2]['required_event_ids']),{'E1','E2'})
    def test_retired_companion(self):
        c,o=generate(12,1)
        self.assertEqual(o[0]['historical_event_ids'],['E1'])
        self.assertEqual(o[0]['supersession_event_ids'],['E2'])
    def test_cut_metadata_not_scoring(self):
        c,o=generate(12,1)
        self.assertIn('after cut',o[0]['interpretation_note'])
        self.assertNotIn('score',c[0])
    def test_fiction_only(self):
        c,_=generate(12,1)
        serialized=json.dumps(c)
        for forbidden in ('govkm.com','SYN-VGR','robnoyes','Nishant','Simone','pipeshub'):
            self.assertNotIn(forbidden,serialized)
    def test_private_holdout_block(self):
        with tempfile.TemporaryDirectory() as td:
            result=subprocess.run([sys.executable,str(ROOT/'generate_authority_cases.py'),'--seed','12','--count','1','--output-dir',str(Path(td)/'hidden'),'--set','holdout'],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((Path(td)/'hidden').exists())

if __name__=='__main__': unittest.main()

class ProtocolV02Tests(unittest.TestCase):
    def test_inventory_is_not_measured_delivery(self):
        c, o = generate(13, 1)
        for case, oracle in zip(c, o):
            self.assertNotIn('public_delivery_text', case)
            self.assertNotIn('delivered_text_after_cut', case)
            self.assertIn('unscored_source_input', case['evidence_inventory_role'])
            self.assertIn('delivered_text_after_cut only', oracle['delivery_boundary'])
            self.assertNotIn('operative_values', case)

    def test_supersession_requires_original_and_replacement_sources(self):
        _, oracle = generate(13, 1)
        self.assertEqual(oracle[0]['required_event_ids'], ['E1', 'E2'])
        self.assertIn('G1', oracle[0]['required_grant_ids'])

    def test_revocation_requires_authority_chain(self):
        _, oracle = generate(13, 1)
        self.assertEqual(oracle[3]['required_event_ids'], ['E1', 'E2'])
        self.assertEqual(oracle[3]['required_grant_ids'], ['G1'])

    def test_missing_grants_provisional_without_coverage(self):
        c, o = generate(13, 1)
        self.assertEqual(o[5]['expected_resolution'],'NO_AUTHORITY_IF_COVERAGE_PROVEN')
        self.assertEqual(o[5]['incomplete_coverage_resolution'],'AUTHORITY_UNRESOLVED')
        self.assertIn('SOURCE-REGISTRY',o[5]['required_coverage_refs'])
        self.assertTrue(c[5]['source_coverage']['grant_registry_complete'])

    def test_independent_dimensions_and_temporal_basis(self):
        _, o = generate(13, 1)
        for row in o:
            self.assertEqual(len(row['independent_dimensions']), 3)
            self.assertIn('valid_at', row['temporal_basis'])

    def test_non_overwrite_and_seed_limits(self):
        from generate_authority_cases import write_set
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'public'
            write_set(99, 1, folder)
            with self.assertRaises(ValueError): write_set(99, 1, folder)
        for seed in (-1,2**63,True):
            with self.assertRaises(ValueError): generate(seed,1)

    def test_manifest_includes_source_and_test(self):
        from generate_authority_cases import write_set
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'public'
            write_set(13,1,folder)
            manifest=json.loads((folder/'sha256_manifest.json').read_text())
            for key in ('generate_authority_cases.py','tests/test_generator.py','cases.json','expected_outcomes.json','metadata.json'):
                self.assertIn(key,manifest['files'])

