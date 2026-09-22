#!/usr/bin/env python3
"""s2_gate_guard.py 的測試（R43 遵守修法方向1，2026-09-18）。

重點：
  - PreToolUse／Edit：目標檔案對應到 active gate lock → deny，訊息含站別／
    reason code／解鎖指引；沒有對應 lock、或目標是別的檔案 → 放行。
  - PostToolUse／Write：成功寫入對應檔案 → 清除 lock；寫入失敗（is_error／
    exit_code 非 0…）不准清掉 lock（fail-safe，寧可多鎖一輪也不能誤清）。
  - 路徑正規化：正／反斜線、大小寫都要比對得出同一個檔案（Windows 慣例，
    同 s2_bash_guard.py 既有測試方向）。
  - stdin 餵爛 JSON／缺欄位一律不炸、不動作（fail-open，同 s2_bash_guard.py）。
  - 透過 subprocess 走一次真實的 stdin→stdout hook 協議（不只測內部函式），
    確認 deny 輸出是合法 JSON 且 permissionDecision=deny。

用法：python test_s2_gate_guard.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, 's2_gate_guard.py')
spec = importlib.util.spec_from_file_location('gate_guard', GUARD)
gate_guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate_guard)

TMP = tempfile.mkdtemp(prefix='s2_gate_guard_test_')
results = []


def check(name, cond, extra=''):
    results.append(bool(cond))
    print(f'{"PASS" if cond else "FAIL"}  {name}{(" → " + extra) if extra else ""}')


def write_lock(dir_, site, entries_path, reasons=None, dry_run=False):
    lock = {
        'site': site,
        'entries_path': entries_path.replace('\\', '/'),
        'reasons': reasons or [{'code': 'FMT_FIRST_NOTE_BITE', 'name': '第一備註寫了 BITE', 'count': 5}],
        'triggered_at': '2026-09-18T22:00:00',
        'dry_run': dry_run,
    }
    p = os.path.join(dir_, f'{site.lower()}_gate_lock.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(lock, f, ensure_ascii=False)
    return p


def run_hook(payload):
    """走真實 subprocess，測完整 stdin→stdout 協議（不只測內部函式）。"""
    proc = subprocess.run(
        [sys.executable, GUARD],
        input=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
    )
    return proc.stdout.decode('utf-8', 'replace'), proc.returncode


# ── PreToolUse／Edit：deny ──────────────────────────────────────────
d1 = os.path.join(TMP, 'ap_deny')
os.makedirs(d1, exist_ok=True)
entries1 = os.path.join(d1, 'entries.json')
with open(entries1, 'w', encoding='utf-8') as f:
    f.write('{}')
write_lock(d1, 'AP', entries1, reasons=[{'code': 'FMT_FIRST_NOTE_BITE', 'name': '第一備註寫了 BITE', 'count': 7}])

check('decide_edit：目標檔有 active lock → deny',
      gate_guard.decide_edit(entries1) is not None)
check('decide_edit：deny 訊息含站別', 'AP' in (gate_guard.decide_edit(entries1) or ''))
check('decide_edit：deny 訊息含 reason code 與筆數',
      'FMT_FIRST_NOTE_BITE' in (gate_guard.decide_edit(entries1) or '')
      and '7則' in (gate_guard.decide_edit(entries1) or ''))
check('decide_edit：deny 訊息指路 Write 整批重寫',
      'Write' in (gate_guard.decide_edit(entries1) or ''))
check('decide_edit：deny 訊息指路少量錯誤的 rewrite-entry 精準修補',
      'rewrite-entry' in (gate_guard.decide_edit(entries1) or ''))
check('decide_edit：deny 訊息指路手動解鎖逃生路徑 gate-clear',
      'gate-clear' in (gate_guard.decide_edit(entries1) or ''))

# 反斜線／大小寫變體照樣要比對得出來（Windows 路徑慣例）
entries1_backslash = entries1.replace('/', '\\')
entries1_upper = entries1.upper()
check('decide_edit：反斜線路徑一樣能比對出 lock', gate_guard.decide_edit(entries1_backslash) is not None)
check('decide_edit：大小寫變體一樣能比對出 lock', gate_guard.decide_edit(entries1_upper) is not None)

# subprocess 全流程：真的送 PreToolUse Edit payload，驗 stdout 是合法 deny JSON
out_deny, code_deny = run_hook({
    'hook_event_name': 'PreToolUse',
    'tool_name': 'Edit',
    'tool_input': {'file_path': entries1, 'old_string': 'x', 'new_string': 'y'},
})
check('subprocess：Edit 命中 lock → exit 0（deny 靠 JSON 輸出不是靠 exit code）', code_deny == 0, str(code_deny))
try:
    deny_payload = json.loads(out_deny)
    deny_ok = (deny_payload.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny'
               and deny_payload.get('hookSpecificOutput', {}).get('hookEventName') == 'PreToolUse')
except (ValueError, AttributeError):
    deny_ok = False
check('subprocess：deny 輸出是合法 JSON 且 permissionDecision=deny', deny_ok, out_deny)
check('subprocess：deny 輸出是 ASCII 安全（ensure_ascii，cp950 主控台不炸）',
      all(ord(c) < 128 for c in out_deny.strip()) if out_deny.strip() else True, repr(out_deny))

# ── PreToolUse／Edit：放行 ──────────────────────────────────────────
d2 = os.path.join(TMP, 'ap_allow')
os.makedirs(d2, exist_ok=True)
other_file = os.path.join(d2, 'unrelated.json')
with open(other_file, 'w', encoding='utf-8') as f:
    f.write('{}')
check('decide_edit：同目錄但沒有 lock 對到這個檔案 → 放行', gate_guard.decide_edit(other_file) is None)
check('decide_edit：整個目錄都沒有 lock 檔 → 放行',
      gate_guard.decide_edit(os.path.join(d2, 'nonexistent.json')) is None)

d3 = os.path.join(TMP, 'ap_lock_other_file')
os.makedirs(d3, exist_ok=True)
locked_entries = os.path.join(d3, 'entries.json')
unrelated_in_locked_dir = os.path.join(d3, 'notes.json')
with open(locked_entries, 'w', encoding='utf-8') as f:
    f.write('{}')
write_lock(d3, 'NS', locked_entries)
check('decide_edit：同目錄有 lock，但目標是另一個檔案 → 放行（只鎖 entries_path 本身）',
      gate_guard.decide_edit(unrelated_in_locked_dir) is None)

out_allow, code_allow = run_hook({
    'hook_event_name': 'PreToolUse',
    'tool_name': 'Edit',
    'tool_input': {'file_path': other_file, 'old_string': 'x', 'new_string': 'y'},
})
check('subprocess：Edit 無對應 lock → stdout 全空（放行）', out_allow == '', repr(out_allow))
check('subprocess：Edit 無對應 lock → exit 0', code_allow == 0, str(code_allow))

# ── ENEX/ABC 整批產物：無 gate lock 也禁止逐筆 Edit ────────────────
platform_entries = os.path.join(d2, 'enex_entries_2200.json')
with open(platform_entries, 'w', encoding='utf-8') as f:
    json.dump({'100001': {'raw_entry': 'old', 'category': 'x'}}, f)
platform_reason = gate_guard.decide_edit(platform_entries) or ''
check('platform entries：無 lock 仍 deny Edit', bool(platform_reason))
check('platform entries：deny 訊息引導 bridge rewrite-entry',
      's2_platform_bridge.py rewrite-entry' in platform_reason
      and '--skeleton' in platform_reason and '--entries' in platform_reason)

candidate_json = os.path.join(d2, '0923-ABC-state.json')
with open(candidate_json, 'w', encoding='utf-8') as f:
    json.dump({'source': 'ABC', 'items': [], 'counts': {}}, f)
candidate_txt = os.path.join(d2, '0923-ABC.txt')
with open(candidate_txt, 'w', encoding='utf-8') as f:
    f.write('ABC 候選')
check('platform 候選 JSON：禁止直接 Edit', gate_guard.decide_edit(candidate_json) is not None)
check('platform 候選 TXT：禁止直接 Edit', gate_guard.decide_edit(candidate_txt) is not None)
check('platform 候選：deny 訊息要求重跑 extract',
      's2_platform_extract.py' in (gate_guard.decide_edit(candidate_json) or ''))

custom_candidate = os.path.join(d2, 'custom_output.json')
with open(custom_candidate, 'w', encoding='utf-8') as f:
    json.dump({'source': 'ENEX', 'items': [], 'counts': {}}, f)
check('platform 候選臨時改名：仍能依 JSON 形狀擋下',
      gate_guard.decide_edit(custom_candidate) is not None)

out_platform, code_platform = run_hook({
    'hook_event_name': 'PreToolUse',
    'tool_name': 'Edit',
    'tool_input': {'file_path': platform_entries, 'old_string': 'old', 'new_string': 'new'},
})
try:
    platform_payload = json.loads(out_platform)
    platform_deny = platform_payload.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny'
except (ValueError, AttributeError):
    platform_deny = False
check('subprocess：platform entries Edit → 合法 deny JSON',
      code_platform == 0 and platform_deny, out_platform)
out_platform_multi, _ = run_hook({
    'hook_event_name': 'PreToolUse',
    'tool_name': 'MultiEdit',
    'tool_input': {'file_path': platform_entries, 'edits': []},
})
try:
    platform_multi_deny = (
        json.loads(out_platform_multi).get('hookSpecificOutput', {})
        .get('permissionDecision') == 'deny')
except (ValueError, AttributeError):
    platform_multi_deny = False
check('subprocess：platform entries MultiEdit 也無法繞過', platform_multi_deny,
      out_platform_multi)
check('platform 辨識不誤擋一般 JSON', gate_guard.decide_edit(other_file) is None)

# 非 Edit／Write 工具（例如 Read）一律不動作
out_other, code_other = run_hook({
    'hook_event_name': 'PreToolUse',
    'tool_name': 'Read',
    'tool_input': {'file_path': entries1},
})
check('subprocess：非 Edit/Write 工具（Read）→ 放行、不動作', out_other == '' and code_other == 0)

# ── PostToolUse／Write：清鎖（成功寫入才清）────────────────────────
d4 = os.path.join(TMP, 'write_clear')
os.makedirs(d4, exist_ok=True)
entries4 = os.path.join(d4, 'entries.json')
with open(entries4, 'w', encoding='utf-8') as f:
    f.write('{}')
lock4 = write_lock(d4, 'RT', entries4)
check('前置：lock 存在', os.path.exists(lock4))

gate_guard.clear_lock_after_write(entries4)
check('clear_lock_after_write：對應 lock 被刪除', not os.path.exists(lock4))

# 沒有對應 lock 時呼叫不報錯
gate_guard.clear_lock_after_write(os.path.join(d4, 'no_such_file.json'))
check('clear_lock_after_write：找不到對應 lock 不報錯', True)

# subprocess 全流程：PostToolUse Write 成功 → 清鎖
d5 = os.path.join(TMP, 'write_clear_subprocess')
os.makedirs(d5, exist_ok=True)
entries5 = os.path.join(d5, 'entries.json')
with open(entries5, 'w', encoding='utf-8') as f:
    f.write('{}')
lock5 = write_lock(d5, 'RT', entries5)
out_w, code_w = run_hook({
    'hook_event_name': 'PostToolUse',
    'tool_name': 'Write',
    'tool_input': {'file_path': entries5, 'content': '{}'},
    'tool_response': {'success': True},
})
check('subprocess：Write 成功且命中 lock → 清鎖', not os.path.exists(lock5))
check('subprocess：PostToolUse 清鎖流程 stdout 不印任何東西（沒有 deny 可印）', out_w == '', repr(out_w))
check('subprocess：PostToolUse 清鎖流程 exit 0', code_w == 0, str(code_w))

# ── PostToolUse／Write：寫入失敗不准清鎖（fail-safe）──────────────────
d6 = os.path.join(TMP, 'write_failed_keep_lock')
os.makedirs(d6, exist_ok=True)
entries6 = os.path.join(d6, 'entries.json')
with open(entries6, 'w', encoding='utf-8') as f:
    f.write('{}')
lock6_is_error = write_lock(d6, 'RT', entries6)
run_hook({
    'hook_event_name': 'PostToolUse', 'tool_name': 'Write',
    'tool_input': {'file_path': entries6},
    'tool_response': {'is_error': True, 'error': 'disk full'},
})
check('subprocess：Write is_error=True → 不清鎖（fail-safe）', os.path.exists(lock6_is_error))

d7 = os.path.join(TMP, 'write_failed_exitcode')
os.makedirs(d7, exist_ok=True)
entries7 = os.path.join(d7, 'entries.json')
with open(entries7, 'w', encoding='utf-8') as f:
    f.write('{}')
lock7 = write_lock(d7, 'RT', entries7)
run_hook({
    'hook_event_name': 'PostToolUse', 'tool_name': 'Write',
    'tool_input': {'file_path': entries7},
    'tool_response': {'exit_code': 1},
})
check('subprocess：Write exit_code!=0 → 不清鎖（fail-safe）', os.path.exists(lock7))

check('_write_looked_successful：is_error=True → False', gate_guard._write_looked_successful({'is_error': True}) is False)
check('_write_looked_successful：success=False → False', gate_guard._write_looked_successful({'success': False}) is False)
check('_write_looked_successful：error 非 None → False', gate_guard._write_looked_successful({'error': 'x'}) is False)
check('_write_looked_successful：exit_code!=0 → False', gate_guard._write_looked_successful({'exit_code': 2}) is False)
check('_write_looked_successful：沒有錯誤欄位 → True', gate_guard._write_looked_successful({'success': True}) is True)
check('_write_looked_successful：tool_response 不是 dict → 預設 True（跟既有 fail-open 對稱）',
      gate_guard._write_looked_successful(None) is True)

# ── 容錯：爛 JSON／缺欄位 → 一律放行、不炸 ─────────────────────────
proc_bad = subprocess.run([sys.executable, GUARD], input=b'not json at all',
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
check('爛 JSON stdin → exit 0 不炸', proc_bad.returncode == 0, str(proc_bad.returncode))
check('爛 JSON stdin → stdout 全空（放行）', proc_bad.stdout == b'', repr(proc_bad.stdout))

out_missing, code_missing = run_hook({'tool_name': 'Edit'})  # 沒有 tool_input
check('缺 tool_input → 放行不炸', out_missing == '' and code_missing == 0)

check('_find_lock_for_path：空字串路徑 → None', gate_guard._find_lock_for_path('') is None)
check('_find_lock_for_path：路徑所在目錄不存在 → None',
      gate_guard._find_lock_for_path(os.path.join(TMP, 'no_such_dir_xyz', 'x.json')) is None)

print(f'\nPASS={sum(results)} FAIL={len(results) - sum(results)}')
sys.exit(0 if all(results) else 1)
