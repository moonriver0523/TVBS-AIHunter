"""Contracts for deterministic editorial derivation and optional input mapping."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import s2_warehouse_editorial as E
import s2_warehouse_publish as P
import test_s2_warehouse_publish as T
from test_s2_warehouse import item


class DeriveTest(unittest.TestCase):
    def seed(self):
        payloads = {
            'a': item('AP4684001', raw_entry='🔴 AP4684001 原文', category={'大分類': '社會', '中主題': '舊名'}, fields={'bite': ['原句']}),
            'b': item('RT1234', 'RT', raw_entry='RT1234 原文', category={'大分類': '政治', '中主題': '正名'}),
            'c': item('AP4684002', raw_entry='備註', script_status='note', category={'中主題': '正名'}),
            'd': item('AP4684003', raw_entry='單則', category={'中主題': '單例'}),
        }
        materials = {mid: dict(kind='wire', material_date='2026-10-03', material_date_range=None,
                              date_quality='structured_source', date_confidence='high', source_link={}) for mid in payloads}
        observations = [('2026-10-03', mid, p) for mid, p in payloads.items() if mid != 'b']
        observations += [('2026-10-02', 'b', payloads['b'])]
        return payloads, materials, observations

    def test_v5_global_minimum_exact_canonical_and_shift_score(self):
        ps, ms, obs = self.seed()
        before = copy.deepcopy((ps, ms, obs))
        bs, rows, refs, resolver = E.derive(ps, ms, obs, {'topics': [{'name': '正名', 'aliases': ['舊名']}]})
        self.assertEqual(set(bs), {'2026-10-02', '2026-10-03'})
        self.assertEqual(len(bs['2026-10-03']), 1)
        a, b = bs['2026-10-03'][0], bs['2026-10-02'][0]
        self.assertEqual(a['id'], b['id'])
        self.assertEqual(a['ids'], ['a'])  # >=2 globally, singleton TAG per shift
        self.assertTrue(a['shifts']['2026-10-03']['qualifies'])
        self.assertFalse(b['shifts']['2026-10-02']['qualifies'])
        self.assertEqual(a['shifts']['2026-10-03']['score'], E.A33.score([ps['a']])[0])
        self.assertEqual(before, (ps, ms, obs))
        self.assertEqual(resolver['legacy:2026-10-03:AP:AP4684001'], 'a')
        self.assertTrue(any(r['id'] == 'a' for r in refs[E.bucket('a')]))
        self.assertNotIn('fields', rows['2026-10-03'][0])

    def test_duplicate_observations_do_not_duplicate_members_and_ambiguous_alias_is_omitted(self):
        ps, ms, obs = self.seed()
        obs += [obs[0], ('2026-10-03', 'b', ps['a'])]
        bs, _, _, resolver = E.derive(ps, ms, obs, {'topics': [{'name': '正名', 'aliases': ['舊名']}]})
        self.assertEqual(bs['2026-10-03'][0]['ids'], ['a', 'b'])
        self.assertNotIn('legacy:2026-10-03:AP:AP4684001', resolver)

    def test_optional_mapping_reports_missing_and_stale_bites_without_mutating_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '2026-10-03.json'
            candidates = [{'id': 'human', '稿名': '人工稿單', '形式': 'SOT', '主軸': '保留角度',
                           'segments': [{'title': '主段', 'note': '', 'items': [
                               {'material_id': 'legacy:ok', '用途': '原用途'}, {'material_id': 'missing', '用途': '缺件'}]}],
                           'bites': [{'material_id': 'legacy:ok', 'text': '原句'}, {'material_id': 'legacy:ok', 'text': '過時句'}]}]
            raw = json.dumps(candidates, ensure_ascii=False).encode('utf-8')
            path.write_bytes(raw)
            cs, report = E.optional_rundown(path, {'legacy:ok': 'new'}, {'new': {'raw_entry': '引言「原句」'}})
            self.assertEqual(report['remapped_ids'], 1)
            self.assertEqual(report['unresolved_ids'], ['missing'])
            self.assertEqual(len(report['stale_bites']), 1)
            self.assertEqual(cs[0]['segments'][0]['items'], [{'material_id': 'new', '用途': '原用途'}])
            self.assertEqual(cs[0]['bites'], [{'material_id': 'new', 'text': '原句'}])
            self.assertIn('本版無法對映素材：missing', cs[0]['gaps'])
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(E.optional_rundown(path.with_name('absent.json'), {}, {})[0], [])


class EditorialPublishTest(unittest.TestCase):
    setUp = T.PublishTest.setUp
    put = T.PublishTest.put
    manifest = T.PublishTest.manifest
    files = T.PublishTest.files
    # Reuse the isolated archive helpers, not the parent's full test collection.
    def test_optional_input_and_all_new_hashes_are_deterministic(self):
        self.put('2026-10-03', [item('AP4684001', category={'中主題': '共同主題'}), item('AP4684002', category={'中主題': '共同主題'})])
        inputs = self.root / 'inputs'; inputs.mkdir()
        candidate = {'id': 'human-1', '稿名': '共同主題', '主軸': '人工撰寫', '形式': 'BS',
                     'segments': [{'title': '段', 'note': '', 'items': [{'material_id': 'legacy:2026-10-03:AP:AP4684001', '用途': '用途'}]}]}
        (inputs / '2026-10-03.json').write_text(json.dumps([candidate]), encoding='utf-8')
        first = P.export_archive(self.root, rundown_dir=inputs)
        for group in ('bundles', 'editorial', 'references', 'rundowns', 'config'):
            for entry in self.manifest()[group]:
                for part in entry['parts']:
                    data = (self.output / part['path']).read_bytes()
                    self.assertEqual(P.digest(data), part['sha256'])
                    self.assertEqual(len(data), part['bytes'])
        self.assertEqual(self.manifest()['rundowns'][0]['count'], 1)
        self.assertEqual(self.manifest()['bundles'][0]['count'], 1)
        before = self.files()
        second = P.export_archive(self.root, rundown_dir=inputs)
        self.assertEqual(first['generation'], second['generation'])
        self.assertEqual(second['changed_files'], 0)
        self.assertEqual(before, self.files())


if __name__ == '__main__':
    unittest.main()
