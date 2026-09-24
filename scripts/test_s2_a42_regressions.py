#!/usr/bin/env python3
"""A42 regression tests: cost-priority Edit policy, lock lifecycle, and operator UX."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load_module('a42_gate_guard', 's2_gate_guard.py')
batch = load_module('a42_batch_prep', 's2_batch_prep.py')
bash_guard = load_module('a42_bash_guard', 's2_bash_guard.py')
apply_reclass = load_module('a42_apply_reclass', 's2_apply_reclass.py')
state = load_module('a42_state', 's2_state.py')


class CostPriorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='s2_a42_')
        self.addCleanup(self.tmp.cleanup)
        self.old_tally = os.environ.get('S2_GATE_TALLY_DIR')
        os.environ['S2_GATE_TALLY_DIR'] = os.path.join(self.tmp.name, 'tally')
        self.addCleanup(self._restore_tally)
        self.entries = os.path.join(self.tmp.name, 'ns_entries_1100.json')
        with open(self.entries, 'w', encoding='utf-8') as f:
            json.dump({'NS1': {'entry': '舊摘要', 'category': '國際/測試', 'tc': '政治/美國'}},
                      f, ensure_ascii=False, indent=2)

    def _restore_tally(self):
        if self.old_tally is None:
            os.environ.pop('S2_GATE_TALLY_DIR', None)
        else:
            os.environ['S2_GATE_TALLY_DIR'] = self.old_tally

    def test_first_two_safe_edits_warn_and_third_denies(self):
        tool_input = {
            'file_path': self.entries,
            'old_string': '"entry": "舊摘要"',
            'new_string': '"entry": "新摘要"',
        }
        outcomes = [gate.evaluate_edit(self.entries, tool_input, 'a42-session')
                    for _ in range(3)]
        for index, outcome in enumerate(outcomes[:2], 1):
            with self.subTest(attempt=index):
                self.assertIsNone(outcome['reason'])
                self.assertIn(f'第 {index}/2 次', outcome['warning'])
                self.assertIn('lint', outcome['warning'])
                self.assertIn('build --dry-run', outcome['warning'])
        self.assertIn('第 3 次', outcomes[2]['reason'])
        self.assertIn('Write', outcomes[2]['reason'])

    def test_mechanical_fields_and_active_lock_remain_denied(self):
        category_edit = {
            'old_string': '"category": "國際/測試"',
            'new_string': '"category": "國際/別題"',
        }
        outcome = gate.evaluate_edit(self.entries, category_edit, 'mechanical')
        self.assertIsNotNone(outcome['reason'])
        self.assertIn('category', outcome['reason'])

        lock = {
            'site': 'NS', 'entries_path': os.path.abspath(self.entries).replace('\\', '/'),
            'reasons': [{'code': 'FMT_OPERATIONAL_NOTE', 'name': '操作備註', 'count': 1}],
        }
        with open(os.path.join(self.tmp.name, 'ns_gate_lock.json'), 'w', encoding='utf-8') as f:
            json.dump(lock, f)
        locked = gate.evaluate_edit(self.entries, category_edit, 'locked')
        self.assertIn('gate lock', locked['reason'])

    def test_post_edit_runs_shared_lint_and_requires_full_dry_run(self):
        message = gate.post_edit_lint_message(self.entries)
        self.assertIn('共用 lint', message)
        self.assertIn('build --dry-run', message)

    def test_hook_protocol_emits_allow_warning_then_post_lint_context(self):
        edit = {
            'file_path': self.entries,
            'old_string': '"entry": "舊摘要"',
            'new_string': '"entry": "新摘要"',
        }
        base = {'tool_name': 'Edit', 'tool_input': edit,
                'session_id': 'hook-a42-session'}
        pre = dict(base, hook_event_name='PreToolUse')
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, 's2_gate_guard.py')],
            input=json.dumps(pre, ensure_ascii=False).encode('utf-8'),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
            env=os.environ.copy())
        output = json.loads(proc.stdout.decode('utf-8'))['hookSpecificOutput']
        self.assertEqual('allow', output['permissionDecision'])
        self.assertIn('lint', output['additionalContext'])

        post = dict(base, hook_event_name='PostToolUse', tool_response={'success': True})
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, 's2_gate_guard.py')],
            input=json.dumps(post, ensure_ascii=False).encode('utf-8'),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
            env=os.environ.copy())
        output = json.loads(proc.stdout.decode('utf-8'))['hookSpecificOutput']
        self.assertEqual('PostToolUse', output['hookEventName'])
        self.assertIn('共用 lint 已執行', output['additionalContext'])


class StickyLockTests(unittest.TestCase):
    def test_only_original_trigger_reason_can_keep_lock(self):
        lock = {'reasons': [
            {'code': 'FMT_OPERATIONAL_NOTE', 'name': '操作備註', 'count': 1, 'items': ['NS1']}
        ]}
        cases = [
            ({'FMT_PKG_DONUT_NEED_SOT': {
                'code': 'FMT_PKG_DONUT_NEED_SOT', 'reason_code': 'FMT_PKG_DONUT_NEED_SOT',
                'name': '漏標SOT', 'count': 1, 'items': ['NS2'], 'is_hard_gate': True,
            }}, []),
            ({'FMT_OPERATIONAL_NOTE': {
                'code': 'FMT_OPERATIONAL_NOTE', 'reason_code': 'FMT_OPERATIONAL_NOTE',
                'name': '操作備註', 'count': 1, 'items': ['NS1'], 'is_hard_gate': True,
            }}, ['FMT_OPERATIONAL_NOTE']),
        ]
        for grouped, expected in cases:
            with self.subTest(expected=expected):
                remaining = batch._remaining_active_lock_reasons(lock, grouped)
                self.assertEqual(expected, [r['reason_code'] for r in remaining])

    def test_build_unlocks_when_original_reason_is_zero_but_other_warning_remains(self):
        with tempfile.TemporaryDirectory(prefix='s2_a42_sticky_') as tmp:
            entries = os.path.join(tmp, 'ns_entries_2200.json')
            with open(entries, 'w', encoding='utf-8') as f:
                json.dump({}, f)
            lock_path = batch._gate_lock_path(entries, 'NS')
            lock = {
                'site': 'NS', 'entries_path': os.path.abspath(entries).replace('\\', '/'),
                'reasons': [{'code': 'FMT_OPERATIONAL_NOTE', 'name': '操作備註',
                             'count': 1, 'items': ['NS1']}],
            }
            with open(lock_path, 'w', encoding='utf-8') as f:
                json.dump(lock, f)
            batch._enforce_build_hard_gate(
                ['NS2: FMT_PKG_DONUT_NEED_SOT'], site='NS', dry_run=True,
                entries_path=entries)
            self.assertFalse(os.path.exists(lock_path))

    def test_build_keeps_lock_while_original_reason_is_still_positive(self):
        with tempfile.TemporaryDirectory(prefix='s2_a42_sticky_') as tmp:
            entries = os.path.join(tmp, 'rt_entries_2200.json')
            with open(entries, 'w', encoding='utf-8') as f:
                json.dump({}, f)
            lock_path = batch._gate_lock_path(entries, 'RT')
            lock = {
                'site': 'RT', 'entries_path': os.path.abspath(entries).replace('\\', '/'),
                'reasons': [{'code': 'FMT_FIRST_NOTE_BITE', 'name': '第一備註 BITE',
                             'count': 5, 'items': ['RT1']}],
            }
            with open(lock_path, 'w', encoding='utf-8') as f:
                json.dump(lock, f)
            batch._enforce_build_hard_gate(
                ['RT1: FMT_FIRST_NOTE_BITE', 'RT2: FMT_PKG_DONUT_NEED_SOT'],
                site='RT', dry_run=True, entries_path=entries)
            self.assertTrue(os.path.exists(lock_path))
            with open(lock_path, encoding='utf-8') as f:
                updated = json.load(f)
            self.assertEqual(['FMT_FIRST_NOTE_BITE'],
                             [r['code'] for r in updated['reasons']])


class OperatorUxTests(unittest.TestCase):
    def test_quote_guard_handles_multiline_commands_conservatively(self):
        cases = [
            ('single-line unclosed double quote', 'echo "oops', True),
            ('multiline unclosed double quote',
             'printf "%s\\n" "first"\nprintf "%s" "oops', True),
            ('multiline unclosed single quote with CRLF',
             "printf '%s' 'first'\r\nprintf '%s' 'oops", True),
            ('balanced quote may span lines', 'printf "%s" "first\nsecond"', False),
            ('balanced quotes on separate lines',
             "printf '%s' 'first'\nprintf \"%s\" \"second\"", False),
            ('unmatched quote characters in comments are ignored',
             'echo ok # user\'s note\n# "documentation only\npwd', False),
            ('escaped quotes remain balanced', 'printf "%s" "a\\\"b"\npwd', False),
            ('heredoc remains outside quote detection',
             "python - <<'PY'\nprint(\"not shell quoting)\nPY", False),
        ]
        for name, command, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(expected, bash_guard._has_unclosed_quote(command))

    def test_inspect_ids_accept_comma_whitespace_and_mixed_forms(self):
        raw = os.path.join(self.tmpdir(), 'ns_ids.json')
        with open(raw, 'w', encoding='utf-8') as f:
            json.dump({
                'NS1': {'entry': 'one'},
                'NS2': {'entry': 'two'},
                'NS3': {'entry': 'three'},
            }, f)
        cases = [
            ('comma separated', ['NS1,NS3'], {'NS1', 'NS3'}),
            ('whitespace separated', ['NS1', 'NS3'], {'NS1', 'NS3'}),
            ('mixed comma and whitespace', ['NS1,NS2', 'NS3'], {'NS1', 'NS2', 'NS3'}),
            ('empty comma segments ignored', ['NS1,,NS3'], {'NS1', 'NS3'}),
            ('index aliases remain accepted', ['#0', '#2'], {'NS1', 'NS3'}),
        ]
        for name, ids, expected in cases:
            with self.subTest(name=name):
                proc = subprocess.run(
                    [sys.executable, os.path.join(HERE, 's2_batch_prep.py'),
                     'inspect', raw, '--site', 'ns', '--ids', *ids,
                     '--fields', 'entry'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                stdout = proc.stdout.decode('utf-8', 'replace')
                stderr = proc.stderr.decode('utf-8', 'replace')
                self.assertEqual(0, proc.returncode, stderr)
                for item_id in {'NS1', 'NS2', 'NS3'}:
                    assertion = self.assertIn if item_id in expected else self.assertNotIn
                    assertion(item_id, stdout)
                self.assertNotIn('找不到這些 id', stderr)

    def test_flat_map_is_inspectable_and_offset_is_applied(self):
        loaded = batch._raw_from_payload('entries.json', {
            'NS1': {'entry': '一'}, 'NS2': {'entry': '二'},
        })
        self.assertEqual(['NS1', 'NS2'], [row['id'] for row in loaded.items])
        args = types.SimpleNamespace(raw='', site='ns', index=None, ids=None,
                                     fields='entry', lengths=False, limit=1, offset=1)
        rows = batch._slice_inspect_rows(list(enumerate(loaded.items)), args)
        self.assertEqual('NS2', rows[0][1]['id'])

    def test_common_wrong_commands_have_actionable_corrections(self):
        self.assertIn('S2_RUN_ID', bash_guard.decide('Bash', 'uuidgen'))
        self.assertIn('未閉合', bash_guard.decide('Bash', 'echo "oops'))
        self.assertEqual(('米蘭時裝週', '米蘭時尚週'),
                         state._normalize_topic_alias_args(None, None,
                                                           '米蘭時尚週=米蘭時裝週'))
        state_path = os.path.join(self.tmpdir(), '0923-s2-state.json')
        self.assertTrue(apply_reclass._default_suggest_path(state_path).endswith(
            os.path.join('_待整併', '0923-分類收斂建議.txt')))

    def test_browser_guard_rejects_missing_itemids_and_bad_syntax(self):
        browser = load_module('a42_browser_guard', 's2_browser_guard.py')
        missing = browser.decide('mcp__browser__browser_evaluate', {
            'function': 'async (itemids) => itemids.map(x => x)'
        })
        self.assertIn('const itemids', missing)
        bad = browser.decide('mcp__browser__browser_evaluate', {
            'function': 'async () => { const x = ; }'
        })
        self.assertIn('語法', bad)
        good = browser.decide('mcp__browser__browser_evaluate', {
            'function': 'async () => { const itemids = ["a"]; return itemids.map(x => x); }'
        })
        self.assertIsNone(good)

    def test_rules_templates_are_self_contained_and_null_safe(self):
        rules = os.path.join(os.path.dirname(HERE), 'common',
                             '13c-S2-執行版-上-入口與三站擷取.md')
        with open(rules, encoding='utf-8') as f:
            text = f.read()
        self.assertNotIn('async (itemids) =>', text)
        self.assertIn('const itemids = [', text)
        self.assertIn('if (!rawSession)', text)

    def test_cli_aliases_and_error_messages_match_the_recovery_path(self):
        entries = os.path.join(self.tmpdir(), 'enex_entries.json')
        with open(entries, 'w', encoding='utf-8') as f:
            json.dump({'ENEX1': {'category': '國際/測試', 'raw_entry': ''}}, f,
                      ensure_ascii=False)
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, 's2_batch_prep.py'),
             'check-entries', '--entries', entries],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(0, proc.returncode, proc.stderr.decode('utf-8', 'replace'))

        flat = os.path.join(self.tmpdir(), 'ns_entries_0700.json')
        with open(flat, 'w', encoding='utf-8') as f:
            json.dump({'NS1': {'entry': '一'}, 'NS2': {'entry': '二'}}, f,
                      ensure_ascii=False)
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, 's2_batch_prep.py'), 'inspect', flat,
             '--site', 'ns', '--offset', '1', '--limit', '1', '--fields', 'entry'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        stdout = proc.stdout.decode('utf-8', 'replace')
        self.assertEqual(0, proc.returncode)
        self.assertIn('NS2', stdout)
        self.assertNotIn('NS1', stdout)

        batch_path = os.path.join(self.tmpdir(), 'ap_batch_1700.json')
        with open(batch_path, 'w', encoding='utf-8') as f:
            json.dump([{'id': 'AP1', 'entry': 'x'}], f)
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, 's2_batch_prep.py'), 'rewrite-entry',
             '--site', 'ap', '--entries', batch_path, '--id', 'AP1', '--set', 'AP1=x'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        error = proc.stderr.decode('utf-8', 'replace')
        self.assertEqual(2, proc.returncode)
        self.assertIn('batch/skeleton', error)
        self.assertIn('上游 entries', error)

    def test_needs_review_wrong_id_lists_the_valid_ids(self):
        state_path = os.path.join(self.tmpdir(), '0923-s2-state.json')
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump({'items': {
                'A': {'script_status': 'pending', 'raw_entry': '', 'needs_review': '待確認'},
                'B': {'script_status': 'pending', 'raw_entry': ''},
            }}, f, ensure_ascii=False)
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, 's2_state.py'), '--file', state_path,
             'needs-review', 'done', '--ids', 'B'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        output = (proc.stdout + proc.stderr).decode('utf-8', 'replace')
        self.assertEqual(2, proc.returncode)
        self.assertIn('目前可結案 ID：A', output)
        self.assertIn('needs-review list', output)

    def test_topic_alias_add_compatibility_form_updates_registry(self):
        registry = os.path.join(self.tmpdir(), 'registry.json')
        state_path = os.path.join(self.tmpdir(), '0923-s2-state.json')
        with open(registry, 'w', encoding='utf-8') as f:
            json.dump({'topics': [{'name': '米蘭時裝週', 'charter': '時裝週消息',
                                   'aliases': [], 'big': '生活', 'tc': {'T': [], 'C': []}}]},
                      f, ensure_ascii=False)
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump({'items': {}}, f)
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, 's2_state.py'), '--file', state_path,
             '--registry', registry, 'topic-alias', '--add', '米蘭時尚週=米蘭時裝週'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(0, proc.returncode,
                         (proc.stdout + proc.stderr).decode('utf-8', 'replace'))
        with open(registry, encoding='utf-8') as f:
            saved = json.load(f)
        self.assertIn('米蘭時尚週', saved['topics'][0]['aliases'])

    def tmpdir(self):
        if not hasattr(self, '_tmp'):
            self._tmp = tempfile.TemporaryDirectory(prefix='s2_a42_ops_')
            self.addCleanup(self._tmp.cleanup)
        return self._tmp.name


if __name__ == '__main__':
    unittest.main(verbosity=2)
