# -*- coding: utf-8 -*-
"""A48 RT 保存器：解析、開關、故障隔離及既有 writer 的跨層契約。"""
import copy
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import s2_batch_prep as B
import s2_source_meta as M
import s2_state as S


GUID = 'tag:reuters.com,2026:newsml_RW615029092026RP1:4'


class GuidTest(unittest.TestCase):
    def test_date_only_and_full_version(self):
        for version in ('1', '0', '0009', '999999999999999999999999'):
            with self.subTest(version=version):
                guid = GUID.rsplit(':', 1)[0] + ':' + version
                meta = M.rt_source_meta({'guid': guid})
                self.assertEqual(meta['guid'], guid)
                self.assertEqual(meta['guid_created_date'], '2026-09-29')
                self.assertEqual(meta['guid_version'], version)
                self.assertEqual(meta['meta_missing_reason'], [])
                self.assertIsNone(meta['time_evidence'][0]['at_utc'])
                self.assertEqual(meta['time_evidence'][0]['precision'], 'date')

    def test_urn_compatibility_and_leap_day(self):
        parsed = M.parse_rt_guid('urn:newsml:reuters.com:newsml_RW123429022024RP1:2')
        self.assertEqual(parsed['guid_created_date'], '2024-02-29')

    def test_malformed_and_odd_version_keep_raw(self):
        for guid in (GUID + ' ', GUID.replace(':4', ':odd'), GUID.replace(':4', ':'),
                     GUID.replace(':4', ':-1'), GUID.replace('29092026', '31022026'),
                     GUID.replace('RW6150', 'RWOS2QA95'), 'newsml_RW615029092026RP1:4', 42, {}, []):
            with self.subTest(guid=guid):
                meta = M.rt_source_meta({'guid': guid})
                self.assertEqual(meta['guid'], guid)
                self.assertIsNone(meta['guid_created_date'])
                self.assertEqual(meta['meta_missing_reason'][0]['code'], 'parse_error')

    def test_missing(self):
        for raw in ({}, {'guid': None}, {'guid': ''}):
            self.assertEqual(M.rt_source_meta(raw)['meta_missing_reason'][0]['code'], 'field_absent')

    def test_cross_day_same_edit_is_not_an_identity_merge(self):
        old = M.rt_source_meta({'guid': GUID})
        new = M.rt_source_meta({'guid': GUID.replace('29092026', '30092026')})
        self.assertNotEqual(old['source_ids'], new['source_ids'])
        self.assertEqual(old['source_ids'][0]['status'], 'candidate')


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='a48-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raw = self.write('raw.json', [{'edit': 'RT6150', 'guid': GUID, 'head': 'Headline',
                                           'story': 'Story', 'sb_count': 0}])
        self.entries = self.write('entries.json', {'RT6150': {
            'entry': 'RT6150 (測試) ▎摘要。▎無BITE。▎00:30',
            'platform': {'guid': '偽造值'}, 'guid': '偽造值'}})

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return str(path)

    def run_pipeline(self, switch, skeleton=True, state=None):
        args = SimpleNamespace(site='rt', raw=self.raw, checkpoint='0929-1700', state=state,
                               out=str(self.root / 'skeleton.json'), page=1, limit=0)
        with patch.dict(os.environ, {'S2_SOURCE_META': switch}), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            B.cmd_from_raw(args)
            skel_bytes = Path(args.out).read_bytes()
            build = SimpleNamespace(site='rt', raw=self.raw, checkpoint=args.checkpoint,
                                    entries=self.entries, skeleton=args.out if skeleton else None,
                                    out=str(self.root / 'batch.json'), dry_run=False)
            B.cmd_build(build)
        return skel_bytes, Path(build.out).read_bytes()

    def test_off_byte_identical_to_previous_adapter(self):
        with patch.dict(B.SITE_SPEC['rt'], {'extra_of': lambda it: {'sb_count': it.get('sb_count', 0)}}):
            baseline = self.run_pipeline('off')
        for switch in ('off', '', 'invalid'):
            self.assertEqual(self.run_pipeline(switch), baseline)
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(B._rt_extra({'guid': GUID}), {'sb_count': 0})

    def test_on_only_platform_changes_in_both_build_paths(self):
        for skeleton in (True, False):
            off = self.run_pipeline('off', skeleton)
            on = self.run_pipeline('on', skeleton)
            for left, right in zip(off, on):
                original, changed = json.loads(left), json.loads(right)
                rows = changed if isinstance(changed, list) else changed['entries']
                self.assertEqual(rows[0]['platform']['guid'], GUID)
                for row in rows:
                    row.pop('platform')
                self.assertEqual(changed, original)

    def test_execution_failure_is_nonblocking_and_keeps_raw(self):
        with patch.object(M, 'rt_source_meta', side_effect=RuntimeError('不得洩漏此訊息')):
            _, on = self.run_pipeline('on')
        meta = json.loads(on)['entries'][0]['platform']
        self.assertEqual(meta['guid'], GUID)
        self.assertEqual(meta['meta_missing_reason'][0]['code'], 'extractor_error')
        self.assertNotIn('不得洩漏', meta['meta_missing_reason'][0]['detail'])

    def test_import_failure_is_nonblocking(self):
        with patch.dict('sys.modules', {'s2_source_meta': None}):
            _, on = self.run_pipeline('on')
        self.assertEqual(json.loads(on)['entries'][0]['platform']['meta_missing_reason'][0]['code'], 'extractor_error')

    def test_missing_guid_still_builds(self):
        self.raw = self.write('raw.json', [{'edit': 'RT6150', 'story': 'Story'}])
        _, on = self.run_pipeline('on')
        self.assertEqual(json.loads(on)['entries'][0]['platform']['meta_missing_reason'][0]['code'], 'field_absent')

    def test_old_platform_is_preserved_and_decisions_cannot_override(self):
        _, on = self.run_pipeline('on')
        batch = json.loads(on)
        batch['entries'][0]['platform']['legacy_key'] = '舊值'
        batch['entries'][0]['status'] = 'pending'
        row = batch['entries'][0]
        state_file = self.write('state.json', {'items': []})
        registry = self.write('registry.json', {'topics': {}})
        args = SimpleNamespace(entries=self.write('batch-on.json', batch), file=state_file,
                               registry=registry, auto_register=False)
        state = S.load(state_file)
        with patch.object(S, 'now_ts', return_value='2026-09-29T17:10:00'), redirect_stdout(StringIO()):
            S.cmd_add_batch(state, args)
        reloaded = S.load(state_file)
        self.assertEqual(reloaded['items']['RT6150']['platform'], row['platform'])
        self.assertEqual(reloaded['items']['RT6150']['src_text'], row['src_text'])
        before = copy.deepcopy(reloaded['items']['RT6150'])
        batch['entries'][0]['platform']['guid'] = GUID.replace(':4', ':5')
        self.write('batch-on.json', batch)
        with redirect_stdout(StringIO()):
            S.cmd_add_batch(reloaded, args)
        self.assertEqual(reloaded['items']['RT6150'], before)

    def test_pending_still_kept_without_refreshing_state(self):
        state_file = self.write('pending.json', {'items': [{'id': 'RT6150', 'source': 'RT',
                                                         'script_status': 'pending', 'platform': {'guid': '舊值'}}]})
        before = Path(state_file).read_bytes()
        skel, _ = self.run_pipeline('on', state=state_file)
        self.assertEqual(json.loads(skel)[0]['prev_status'], 'pending')
        self.assertEqual(Path(state_file).read_bytes(), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
