"""S2 成本修正回歸：只用本機合成資料，不呼叫網路或付費服務。"""
import copy
import io
import json
import shlex
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s2_batch_prep as prep
import s2_platform_bridge as bridge
import s2_token_metrics as metrics


class CostP0Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return str(path)

    def measure(self, rows):
        path = self.root / 'transcript.jsonl'
        path.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
        return metrics.measure(path)

    def test_metrics_only_official_assistant_and_unique_tool_ids(self):
        row = {'type': 'assistant', 'timestamp': '2026-10-15T00:00:00Z',
               'message': {'id': 'm1', 'usage': {'input_tokens': 3},
                           'content': [{'type': 'tool_use', 'id': 't1',
                                        'name': 'Read', 'input': {}}]}}
        blob = copy.deepcopy(row)
        blob['type'] = 'api-request-blob'
        blob['message']['usage'] = {'input_tokens': 7}
        blob['message']['content'].append({'type': 'tool_use', 'id': 'blob-only', 'name': 'Write'})
        result = self.measure([blob, row, row, blob])
        self.assertEqual(1, result['tool_calls'])
        self.assertEqual({'Read': 1}, result['tool_calls_by_name'])
        self.assertEqual(1, result['phase_calls_total'])
        self.assertEqual(1, result['requests'])
        self.assertEqual(7, result['input_tokens'])

    def test_metrics_no_tool_id_counts_each_official_block(self):
        row = {'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'name': 'Read', 'input': {}},
            {'type': 'tool_use', 'id': '', 'name': 'Read', 'input': {}}]}}
        blob = copy.deepcopy(row)
        blob['type'] = 'api-request-blob'
        self.assertEqual(2, self.measure([row, blob])['tool_calls'])
        row.pop('type')
        self.assertEqual(0, self.measure([row])['tool_calls'])

    def inspect(self, raw, **kw):
        args = Namespace(raw=raw, ids=None, fields='script', site=None,
                         limit=None, index=None, offset=0, lengths=False)
        vars(args).update(kw)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            prep.cmd_inspect(args)
        return out.getvalue(), err.getvalue()

    def check_pages(self, raw, expected, **kw):
        _, note = self.inspect(raw, **kw)
        commands = [line.split('：', 1)[1] for line in note.splitlines()
                    if line.startswith('第 ') and 'python ' in line]
        self.assertGreater(len(commands), 1)
        seen = []
        for n, command in enumerate(commands, 1):
            self.assertIn(f'第 {n}/{len(commands)} 頁', note)
            tokens = shlex.split(command)
            parsed = {'ids': tokens[tokens.index('--ids') + 1],
                      'fields': tokens[tokens.index('--fields') + 1],
                      'limit': int(tokens[tokens.index('--limit') + 1])}
            if '--site' in tokens:
                parsed['site'] = tokens[tokens.index('--site') + 1]
            output, next_note = self.inspect(tokens[3], **parsed)
            self.assertNotIn('完整分頁計畫', next_note)
            self.assertLessEqual(len(output), prep.INSPECT_TEXT_BUDGET)
            for line in output.splitlines():
                item_id, payload = line.split('\t', 1)
                seen.append(item_id)
                self.assertNotIn('...[略]', payload)
                json.loads(payload)
        self.assertEqual(expected, seen)
        return commands

    def test_inspect_complete_greedy_pages_serialized_length(self):
        rows = [{'id': f'N{i}', 'script': '字\n"\t' * 650} for i in range(13)]
        raw = self.write('raw with spaces.json', rows)
        commands = self.check_pages(raw, [r['id'] for r in rows])
        self.assertEqual(3, len(commands))

    def test_inspect_duplicate_ids_use_unambiguous_indexes(self):
        rows = [{'id': 'same', 'script': 'x' * 10000} for _ in range(7)]
        commands = self.check_pages(self.write('raw.json', rows), ['same'] * 7)
        selectors = [shlex.split(c)[shlex.split(c).index('--ids') + 1]
                     for c in commands]
        self.assertEqual([f'#{i}' for i in range(7)], ','.join(selectors).split(','))

    def test_inspect_more_than_default_limit_covers_all_requested_ids(self):
        rows = [{'id': f'N{i}', 'script': 'x' * 400} for i in range(125)]
        self.check_pages(self.write('raw.json', rows), [r['id'] for r in rows],
                         ids=','.join(r['id'] for r in rows))

    def test_inspect_selected_indexes_do_not_include_duplicate_ids_outside_window(self):
        rows = [{'id': 'same', 'script': 'x' * 10000} for _ in range(8)]
        raw = self.write('raw.json', rows)
        commands = self.check_pages(raw, ['same'] * 5, ids='#2,#3,#4,#5,#6')
        self.assertIn("'#2,#3'", commands[0])

    def test_inspect_index_selector_cannot_match_literal_hash_id(self):
        rows = [{'id': '#1', 'script': 'first'}, {'id': 'N1', 'script': 'second'}]
        out, _ = self.inspect(self.write('raw.json', rows), ids='#1')
        self.assertEqual(['N1'], [line.split('\t')[0] for line in out.splitlines()])

    def test_inspect_single_oversize_is_complete_and_marked(self):
        body = '全文' * 20000 + '最後一句'
        out, note = self.inspect(self.write('raw.json', [{'id': 'N0', 'script': body}]))
        self.assertEqual(body, json.loads(out.split('\t', 1)[1])['script'])
        self.assertIn('單筆超過預算', note)
        self.assertIn('第 1/1 頁', note)

    def test_inspect_oversize_in_middle_has_its_own_page(self):
        rows = [{'id': f'N{i}', 'script': 'x' * size}
                for i, size in enumerate((100, 40000, 100))]
        _, note = self.inspect(self.write('raw.json', rows))
        self.assertIn('第 2/3 頁', note)
        self.assertIn('單筆超過預算', note)
        self.assertIn('--ids N2', note)

    def test_inspect_within_budget_unchanged(self):
        rows = [{'id': 'N0', 'script': '完整原文'}]
        out, note = self.inspect(self.write('raw.json', rows))
        self.assertEqual('N0\t' + json.dumps({'script': '完整原文'}, ensure_ascii=False) + '\n', out)
        self.assertNotIn('分頁', note)

    def blank_skeleton(self, **kw):
        row = dict(id='ABC123', source='ABC', src_text='站方完整原文',
                   detailId='123', entry='', category='', tc='', skip='')
        row.update(kw)
        return self.write('abc_skeleton.json', [row])

    def run_bridge(self, *argv, fails=False):
        err, out = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            if fails:
                with self.assertRaises(SystemExit) as raised:
                    bridge.main(list(argv))
                self.assertEqual(2, raised.exception.code)
            else:
                bridge.main(list(argv))
        return err.getvalue()

    def test_build_protects_written_entries_and_force_works(self):
        skeleton = self.blank_skeleton()
        entries = self.write('abc_entries.json', {'ABC123': {'raw_entry': '已寫好的稿', 'category': '美國'}})
        before = Path(entries).read_bytes()
        error = self.run_bridge('build', '--skeleton', skeleton, '--out', entries, fails=True)
        self.assertEqual(before, Path(entries).read_bytes())
        self.assertIn('--force', error)
        self.assertIn('rewrite-entry --site abc --skeleton', error)
        self.run_bridge('build', '--skeleton', skeleton, '--out', entries, '--force')
        self.assertEqual('', json.loads(Path(entries).read_text(encoding='utf-8'))['ABC123']['raw_entry'])

    def test_build_new_blank_file_unchanged(self):
        out = str(self.root / 'entries.json')
        self.run_bridge('build', '--skeleton', self.blank_skeleton(), '--out', out)
        self.assertEqual('站方完整原文', json.loads(Path(out).read_text(encoding='utf-8'))['ABC123']['src_text'])

    def test_build_preserves_judgments_and_fills_src_from_same_skeleton(self):
        skeleton = self.blank_skeleton()
        out = self.write('abc_entries.json', {'ABC123': {'raw_entry': '已寫好的稿', 'tc': 'T'}})
        self.run_bridge('build', '--skeleton', skeleton, '--entries', out, '--out', out)
        value = json.loads(Path(out).read_text(encoding='utf-8'))['ABC123']
        self.assertEqual('已寫好的稿', value['raw_entry'])
        self.assertEqual('站方完整原文', value['src_text'])
        self.assertEqual('T', value['tc'])
        row = json.loads(Path(skeleton).read_text(encoding='utf-8'))[0]
        self.assertEqual('已寫好的稿', row['entry'])
        self.assertEqual('T', row['tc'])

    def test_build_filled_skeleton_can_update_existing_filled_entries(self):
        skeleton = self.blank_skeleton(entry='新版稿件', category='美國')
        out = self.write('entries.json', {'ABC123': {'raw_entry': '舊稿件', 'category': '美國'}})
        self.run_bridge('build', '--skeleton', skeleton, '--out', out)
        self.assertEqual('新版稿件', json.loads(Path(out).read_text(encoding='utf-8'))['ABC123']['raw_entry'])

    def test_build_protects_skip_decisions_and_empty_existing_is_safe(self):
        skeleton = self.blank_skeleton()
        out = self.write('entries.json', {'ABC123': {'skip': '排除理由'}})
        before = Path(out).read_bytes()
        self.run_bridge('build', '--skeleton', skeleton, '--out', out, fails=True)
        self.assertEqual(before, Path(out).read_bytes())
        self.write('entries.json', {'ABC123': {'raw_entry': '', 'category': ''}})
        self.run_bridge('build', '--skeleton', skeleton, '--out', out)

    def test_build_refill_missing_source_keeps_both_files_unchanged(self):
        skeleton = self.blank_skeleton(src_text='')
        out = self.write('entries.json', {'ABC123': {'raw_entry': '稿件', 'category': '美國'}})
        before = (Path(skeleton).read_bytes(), Path(out).read_bytes())
        error = self.run_bridge('build', '--skeleton', skeleton, '--entries', out, '--out', out, fails=True)
        self.assertIn('src_text', error)
        self.assertEqual(before, (Path(skeleton).read_bytes(), Path(out).read_bytes()))

    def test_build_missing_src_reports_id_and_leaves_output_untouched(self):
        skeleton = self.blank_skeleton(src_text='', entry='已填的稿')
        out = self.write('entries.json', {'original': 'keep'})
        before = Path(out).read_bytes()
        error = self.run_bridge('build', '--skeleton', skeleton, '--out', out, fails=True)
        self.assertIn('ABC123', error)
        self.assertIn('src_text', error)
        self.assertEqual(before, Path(out).read_bytes())

    def test_patch_initialization_errors_include_full_correct_command(self):
        skeleton = self.blank_skeleton()
        for omitted in ('--site', '--entries', '--skeleton'):
            args = {'--site': 'abc', '--skeleton': skeleton,
                    '--entries': str(self.root / 'abc_entries.json'),
                    '--init-patch': str(self.root / 'patch.json')}
            argv = ['rewrite-entry']
            for key, value in args.items():
                if key != omitted:
                    argv += [key, value]
            with self.subTest(omitted=omitted):
                err = self.run_bridge(*argv, fails=True)
                for token in ('python scripts/s2_platform_bridge.py rewrite-entry',
                              '--site abc', '--skeleton', '--entries', '--init-patch'):
                    self.assertIn(token, err)

    def test_patch_same_path_gives_distinct_entries_and_retry_succeeds(self):
        skeleton = self.blank_skeleton()
        error = self.run_bridge('rewrite-entry', '--site', 'abc', '--skeleton', skeleton,
                                '--entries', skeleton, '--init-patch', str(self.root / 'patch.json'), fails=True)
        command = next(line for line in error.splitlines() if line.startswith('python '))
        argv = shlex.split(command)[2:]
        self.assertNotEqual(argv[argv.index('--skeleton') + 1], argv[argv.index('--entries') + 1])
        self.run_bridge(*argv)
        self.assertTrue((self.root / 'patch.json').exists())


if __name__ == '__main__':
    unittest.main()
