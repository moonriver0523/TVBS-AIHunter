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
import time

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, 's2_gate_guard.py')
spec = importlib.util.spec_from_file_location('gate_guard', GUARD)
gate_guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate_guard)

TMP = tempfile.mkdtemp(prefix='s2_gate_guard_test_')

# ⚠️ 必須在任何 subprocess 呼叫**之前**設定：`run_hook` 沒有帶 env=，子行程是
# 繼承這裡的環境變數。把第 5 條（通用次數上限）的計數檔導進測試專用暫存夾，
# 才不會汙染真實的系統暫存夾、也不會被別的 S2 session 的計數檔干擾。
TALLY_DIR = os.path.join(TMP, 'tally')
os.environ['S2_GATE_TALLY_DIR'] = TALLY_DIR

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
      and '--skeleton' in platform_reason and '--entries' in platform_reason
      and '--init-patch' in platform_reason)

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

# ── NS/AP/RT entries：無 gate lock 也禁止逐筆 Edit（2026-09-23，A41 續辦）──
# 0923-0430 輪實測：完全沒觸發 gate lock，agent 仍自發對 ns_entries_0430.json
# 連打 10 次 Edit（AP/RT 各 1 次），成本＋150%、turns＋81%。
d8 = os.path.join(TMP, 'site_entries_no_lock')
os.makedirs(d8, exist_ok=True)


def site_entries(dir_, name, payload=None):
    p = os.path.join(dir_, name)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(payload if payload is not None else
                  {'NS0001': {'entry': 'x', 'category': '國際/測試'}}, f, ensure_ascii=False)
    return p


ns_entries_nolock = site_entries(d8, 'ns_entries_0430.json')
site_reason = gate_guard.decide_edit(ns_entries_nolock) or ''
check('NS entries：無 lock 仍 deny Edit', bool(site_reason))
check('NS entries：deny 訊息引導 s2_batch_prep.py rewrite-entry 且列齊參數',
      's2_batch_prep.py rewrite-entry' in site_reason
      and '--site' in site_reason and '--entries' in site_reason
      and '--init-patch' in site_reason
      and '--id' not in site_reason and '--set' not in site_reason, ascii(site_reason))
check('NS entries：deny 訊息講明是「自由模式」（跟 lock 解鎖訊息區分得開）',
      '自由模式' in site_reason and '沒有' in site_reason, ascii(site_reason))
check('NS entries：無 lock 時不混入 gate-clear 解鎖訊息（兩段訊息互斥）',
      'gate-clear' not in site_reason, ascii(site_reason))
check('NS entries：deny 訊息點名白名單欄位 entry／category／tc',
      'entry' in site_reason and 'category' in site_reason and 'tc' in site_reason,
      ascii(site_reason))

for _name in ('ap_entries_0430.json', 'rt_entries_0430.json',
              'ns_entries_0430.renamed.json', 'rt_entries2_0700.json',
              'ap_cctv_entries_1700.json', 'rt_backfill_entries_2359.json',
              'ns_entries_1100_v2.json', 'rt_entries_2000b.json',
              'ap_entries_all_0700.json'):
    check(f'NS/AP/RT entries 命名變體照樣擋：{_name}',
          gate_guard.decide_edit(site_entries(d8, _name)) is not None)

for _name in ('ns_batch_0430.json', 'ns_skeleton_0430.json', 'entries.json',
              'ns_raw_0430.json'):
    check(f'NS/AP/RT 擋線不誤擋非 entries 檔：{_name}',
          gate_guard.decide_edit(site_entries(d8, _name)) is None)

# 臨時改名：靠 NS/AP/RT 草稿獨有的頂層保留鍵 `_new_topics` 接住
renamed_draft = site_entries(d8, 'draft_output.json', {
    '_new_topics': {}, 'NS0002': {'entry': 'y'}})
check('NS/AP/RT entries 臨時改名：靠 _new_topics 形狀擋下',
      gate_guard.decide_edit(renamed_draft) is not None)
batch_like = site_entries(d8, 'weird_batch.json', {'entries': [], 'new_topics': {}})
check('NS/AP/RT 形狀判斷不誤擋 batch.json 的 new_topics（不帶底線）',
      gate_guard.decide_edit(batch_like) is None)

# 訊息優先序：有 lock → 維持既有 lock 訊息，不被新的 NS/AP/RT 訊息蓋掉
d9 = os.path.join(TMP, 'site_entries_with_lock')
os.makedirs(d9, exist_ok=True)
ns_entries_locked = site_entries(d9, 'ns_entries_0430.json')
write_lock(d9, 'NS', ns_entries_locked,
           reasons=[{'code': 'FMT_MISSING_FOOTAGE_SEG', 'name': '缺 ▎畫面： 段', 'count': 6}])
locked_reason = gate_guard.decide_edit(ns_entries_locked) or ''
check('訊息優先序：NS entries 有 lock 時回 lock 訊息（含 gate-clear 逃生路徑）',
      'gate-clear' in locked_reason and 'FMT_MISSING_FOOTAGE_SEG' in locked_reason,
      ascii(locked_reason))
check('訊息優先序：有 lock 時不顯示自由模式訊息（避免兩段互相矛盾）',
      '自由模式' not in locked_reason, ascii(locked_reason))

# 同目錄有別的檔案的 lock → 該檔案本身仍走新的自由模式訊息
ap_entries_same_dir = site_entries(d9, 'ap_entries_0430.json')
same_dir_reason = gate_guard.decide_edit(ap_entries_same_dir) or ''
check('訊息優先序：同目錄 lock 指到別的檔案時，本檔走自由模式訊息',
      bool(same_dir_reason) and '自由模式' in same_dir_reason
      and 'gate-clear' not in same_dir_reason, ascii(same_dir_reason))

# ENEX/ABC 既有判斷不受影響（不可被 NS/AP/RT 新分支蓋掉）
check('回歸：ENEX entries 仍走 platform bridge 訊息，不被 NS/AP/RT 分支搶走',
      's2_platform_bridge.py rewrite-entry' in (gate_guard.decide_edit(platform_entries) or ''))

out_site, code_site = run_hook({
    'hook_event_name': 'PreToolUse',
    'tool_name': 'Edit',
    'tool_input': {'file_path': ns_entries_nolock, 'old_string': 'x', 'new_string': 'y'},
})
try:
    site_deny = (json.loads(out_site).get('hookSpecificOutput', {})
                 .get('permissionDecision') == 'deny')
except (ValueError, AttributeError):
    site_deny = False
check('subprocess：NS entries 無 lock 的 Edit → 合法 deny JSON',
      code_site == 0 and site_deny, out_site)

out_site_multi, _ = run_hook({
    'hook_event_name': 'PreToolUse',
    'tool_name': 'MultiEdit',
    'tool_input': {'file_path': ns_entries_nolock, 'edits': []},
})
try:
    site_multi_deny = (json.loads(out_site_multi).get('hookSpecificOutput', {})
                       .get('permissionDecision') == 'deny')
except (ValueError, AttributeError):
    site_multi_deny = False
check('subprocess：NS entries MultiEdit 也無法繞過', site_multi_deny, out_site_multi)

# ── batch 草稿：只鎖 category／tc 欄位的逐筆 Edit（2026-09-23，A41 第三種攔截）──
# 0923-1100 輪實測：entries.json 的逐筆 Edit 被上面兩道鎖擋下了（AP 2 次、ABC 1 次），
# 但同一輪對 batch.json 做了 14 次逐筆 Edit 完全沒被擋，14 次全在改 category 值。
d10 = os.path.join(TMP, 'batch_draft')
os.makedirs(d10, exist_ok=True)


def batch_file(dir_, name):
    """batch 草稿檔本身的內容不影響判斷（檔名＋Edit 內容才是判準），
    但還是寫成真實形狀，避免被內容形狀類的判斷誤傷。"""
    p = os.path.join(dir_, name)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump([{'id': 'NS0001', 'source': 'NS', 'src_text': 'x',
                    'entry': '', 'category': '', 'tc': ''}], f, ensure_ascii=False)
    return p


ns_batch = batch_file(d10, 'ns_batch_1100.json')


def edit_input(path, old, new):
    return {'file_path': path, 'old_string': old, 'new_string': new}


def multi_input(path, pairs):
    return {'file_path': path,
            'edits': [{'old_string': o, 'new_string': n} for o, n in pairs]}


# ① category 欄位 → 擋
batch_cat_reason = gate_guard.decide_edit(ns_batch, edit_input(
    ns_batch, '"category": "國際/中東"', '"category": "國際/以巴衝突"')) or ''
check('batch 草稿：改 category 值 → deny', bool(batch_cat_reason))
check('batch 草稿：deny 訊息點名 category／tc 兩個欄位',
      'category' in batch_cat_reason and 'tc' in batch_cat_reason,
      ascii(batch_cat_reason))
check('batch 草稿：deny 訊息講明只鎖這兩欄、其他欄位照樣可改',
      'entry' in batch_cat_reason and 'footage_type' in batch_cat_reason,
      ascii(batch_cat_reason))
check('batch 草稿：deny 訊息指路 rewrite-entry→build（尚未 add-batch 的修法）',
      's2_batch_prep.py rewrite-entry' in batch_cat_reason
      and 'build' in batch_cat_reason, ascii(batch_cat_reason))
check('batch 草稿：deny 訊息指路 s2_state.py set-category --pairs（真實指令位置）',
      's2_state.py' in batch_cat_reason
      and 'set-category --pairs' in batch_cat_reason, ascii(batch_cat_reason))
check('batch 草稿：deny 訊息指路 s2_state.py set-tc --pairs',
      'set-tc --pairs' in batch_cat_reason, ascii(batch_cat_reason))
check('batch 草稿：deny 訊息附 collate-category 收字串的捷徑',
      'collate-category' in batch_cat_reason, ascii(batch_cat_reason))
check('batch 草稿：deny 訊息不冒充不存在的 s2_batch_prep.py set-category',
      's2_batch_prep.py set-category' not in batch_cat_reason, ascii(batch_cat_reason))
check('batch 草稿：deny 訊息不混入 gate lock 的 gate-clear 解鎖訊息（四段訊息互斥）',
      'gate-clear' not in batch_cat_reason, ascii(batch_cat_reason))

# ② tc 欄位 → 擋
check('batch 草稿：改 tc 值 → deny',
      gate_guard.decide_edit(ns_batch, edit_input(
          ns_batch, '"tc": ""', '"tc": "川普關稅/美國"')) is not None)
check('batch 草稿：新增原本不存在的 tc 鍵 → deny（單側有鍵也算動到）',
      gate_guard.decide_edit(ns_batch, edit_input(
          ns_batch, '"src_text": "x"',
          '"src_text": "x",\n  "tc": "川普關稅/美國"')) is not None)
check('batch 草稿：刪掉 category 鍵 → deny',
      gate_guard.decide_edit(ns_batch, edit_input(
          ns_batch, '"category": "國際/中東",\n  "tc": ""', '"tc": ""')) is not None)

# ③ 其他欄位 → 放行（batch 本來就是 draft，刻意保留彈性）
check('batch 草稿：改 entry 欄位 → 放行',
      gate_guard.decide_edit(ns_batch, edit_input(
          ns_batch, '"entry": ""', '"entry": "NS0001 (華府/關稅) ▎摘要…"')) is None)
check('batch 草稿：改 footage_type 欄位 → 放行',
      gate_guard.decide_edit(ns_batch, edit_input(
          ns_batch, '"footage_type": "PKG"', '"footage_type": "VO"')) is None)
check('batch 草稿：改 status 欄位 → 放行',
      gate_guard.decide_edit(ns_batch, edit_input(
          ns_batch, '"status": "pending"', '"status": "has_script"')) is None)
check('batch 草稿：entry 內文剛好提到 category 這個英文字（沒有鍵樣式）→ 放行',
      gate_guard.decide_edit(ns_batch, edit_input(
          ns_batch, '"entry": "舊文"',
          '"entry": "報導提到 category 這個字"')) is None)

# ④ 整顆物件重寫但 category／tc 原值照抄 → 放行（證明判準是「值有變」不是「出現關鍵字」）
same_cat_old = ('{"id": "NS0001", "entry": "舊", "category": "國際/中東", "tc": "/以色列"}')
same_cat_new = ('{"id": "NS0001", "entry": "新", "category": "國際/中東", "tc": "/以色列"}')
check('batch 草稿：整顆物件重寫但 category／tc 值不變 → 放行',
      gate_guard.decide_edit(ns_batch, edit_input(
          ns_batch, same_cat_old, same_cat_new)) is None)
check('batch 草稿：整顆物件重寫且 category 值有變 → deny',
      gate_guard.decide_edit(ns_batch, edit_input(
          ns_batch, same_cat_old,
          same_cat_new.replace('國際/中東', '國際/以巴衝突'))) is not None)
check('batch 草稿：只有排版空白不同、category 值一樣 → 放行',
      gate_guard.decide_edit(ns_batch, edit_input(
          ns_batch, '"category":"國際/中東"', '"category": "國際/中東"')) is None)
check('batch 草稿：截斷的半截 category 值（片段不是合法 JSON）照樣比得出差異 → deny',
      gate_guard.decide_edit(ns_batch, edit_input(
          ns_batch, '"category": "國際/中', '"category": "國際/以')) is not None)
check('batch 草稿：category 值是 R25 的 dict 形狀也接得住 → deny',
      gate_guard.decide_edit(ns_batch, edit_input(
          ns_batch, '"category": {"大分類": "國際", "中主題": "中東"}',
          '"category": {"大分類": "國際", "中主題": "以巴衝突"}')) is not None)

# ⑤ MultiEdit：混合「該擋」與「不該擋」→ 整組擋
#    理由：MultiEdit 在工具層 all-or-nothing，放行等於讓 category 改動過關；
#    且否則只要在 category 改動旁塞一筆 entry 改動就能繞過。拆開單獨送即可。
check('batch 草稿 MultiEdit：全部都是其他欄位 → 放行',
      gate_guard.decide_edit(ns_batch, multi_input(ns_batch, [
          ('"entry": "a"', '"entry": "b"'),
          ('"status": "pending"', '"status": "has_script"')])) is None)
check('batch 草稿 MultiEdit：全部都是 category → deny',
      gate_guard.decide_edit(ns_batch, multi_input(ns_batch, [
          ('"category": "國際/中東"', '"category": "國際/以巴衝突"'),
          ('"category": "國際/美國"', '"category": "國際/川普關稅"')])) is not None)
check('batch 草稿 MultiEdit：混合（entry 放行 ＋ category 該擋）→ 整組 deny（不准夾帶繞過）',
      gate_guard.decide_edit(ns_batch, multi_input(ns_batch, [
          ('"entry": "a"', '"entry": "b"'),
          ('"category": "國際/中東"', '"category": "國際/以巴衝突"')])) is not None)
check('batch 草稿 MultiEdit：edits 空陣列 → 放行（沒有內容可判讀，fail-open）',
      gate_guard.decide_edit(ns_batch, {'file_path': ns_batch, 'edits': []}) is None)

# ⑥ 檔名變體：production 真的出現過的全部要擋
for _name in ('ap_batch_1100_full.json', 'ap_batch_1100_extra.json',
              'ap_batch_1100b.json', 'ns_batch_2000b.json',
              'rt_backfill_batch_2359.json', 'ap_batch_0100_sntv.json',
              'ap_batch_2000_b.json', '_rt_batch_1000.json',
              'rt_batch_1100.json', 'enex_batch_1100.json', 'abc_batch_1100.json'):
    check(f'batch 檔名變體照樣擋：{_name}',
          gate_guard.decide_edit(batch_file(d10, _name), edit_input(
              os.path.join(d10, _name), '"category": "A/B"',
              '"category": "A/C"')) is not None)

# ⑦ 檔名不命中 batch 規則的檔案，就算內容在改 category 也不受影響
#    ⚠️ 這裡刻意不在 d10 裡建 `*_gate_lock.json`：`_find_lock_for_path` 對
#    「內容不是 dict 的 lock 檔」會直接 AttributeError（既有缺陷，不在這次範圍，
#    已列入回報），planted 之後會連累同目錄後續所有 decide_edit 呼叫。
for _name in ('ns_skeleton_1100.json', '0922-s2-state.json',
              'state.json', 'yc_batch_2200.json', 'yna_cna_batch_2000.json',
              'weird_batch.json', 'ns_raw_1100.json', 'ns_entries_1100.json'):
    _p = batch_file(d10, _name)
    _r = gate_guard.decide_edit(_p, edit_input(
        _p, '"category": "A/B"', '"category": "A/C"')) or ''
    check(f'batch 擋線不誤擋非 batch 檔（即使在改 category）：{_name}',
          'batch 草稿' not in _r, ascii(_r))

# 檔名層級直接驗（不碰檔案系統，避開上面那個 lock 檔地雷）
for _name in ('ns_gate_lock.json', 'ap_gate_lock.json', 'ns_entries_1100.json',
              'enex_entries_1100.json', 'ns_skeleton_1100.json',
              '0922-s2-state.json', 'entries.json',
              'yc_batch_2200.json', 'yna_cna_batch_2000.json',
              'weird_batch.json', 'batch.json', 'my_batch.json'):
    check(f'_batch_artifact_kind 不命中：{_name}',
          gate_guard._batch_artifact_kind(_name) is None,
          str(gate_guard._batch_artifact_kind(_name)))

# ⑧ 向後相容：只給 file_path（沒有 tool_input）→ 放行，既有呼叫端行為零改變
check('batch 草稿：decide_edit 只帶 file_path（無 tool_input）→ 放行（向後相容）',
      gate_guard.decide_edit(ns_batch) is None)
check('回歸：既有 ns_batch_0430.json 單參數呼叫仍放行',
      gate_guard.decide_edit(os.path.join(d8, 'ns_batch_0430.json')) is None)

# ⑨ 優先序：entries 檔就算在改 category，也要走既有的 entries 訊息，不能被 batch 分支搶走
_entries_cat_reason = gate_guard.decide_edit(ns_entries_nolock, edit_input(
    ns_entries_nolock, '"category": "A/B"', '"category": "A/C"')) or ''
check('優先序：NS entries 改 category → 仍走 NS/AP/RT 自由模式訊息，不是 batch 訊息',
      '自由模式' in _entries_cat_reason
      and 'batch 草稿' not in _entries_cat_reason, ascii(_entries_cat_reason))
_platform_cat_reason = gate_guard.decide_edit(platform_entries, edit_input(
    platform_entries, '"category": "A/B"', '"category": "A/C"')) or ''
check('優先序：ENEX entries 改 category → 仍走 platform bridge 訊息',
      's2_platform_bridge.py rewrite-entry' in _platform_cat_reason
      and 'batch 草稿' not in _platform_cat_reason, ascii(_platform_cat_reason))
_locked_cat_reason = gate_guard.decide_edit(ns_entries_locked, edit_input(
    ns_entries_locked, '"category": "A/B"', '"category": "A/C"')) or ''
check('優先序：有 gate lock 的檔案改 category → 仍走 lock 訊息（最高優先不變）',
      'gate-clear' in _locked_cat_reason and 'batch 草稿' not in _locked_cat_reason,
      ascii(_locked_cat_reason))

# ⑩ subprocess 全流程
out_batch, code_batch = run_hook({
    'hook_event_name': 'PreToolUse', 'tool_name': 'Edit',
    'tool_input': edit_input(ns_batch, '"category": "國際/中東"',
                             '"category": "國際/以巴衝突"'),
})
try:
    batch_deny = (json.loads(out_batch).get('hookSpecificOutput', {})
                  .get('permissionDecision') == 'deny')
except (ValueError, AttributeError):
    batch_deny = False
check('subprocess：batch 草稿改 category 的 Edit → 合法 deny JSON',
      code_batch == 0 and batch_deny, out_batch)
check('subprocess：batch deny 輸出是 ASCII 安全（ensure_ascii，cp950 主控台不炸）',
      all(ord(c) < 128 for c in out_batch.strip()) if out_batch.strip() else False,
      repr(out_batch))

out_batch_ok, code_batch_ok = run_hook({
    'hook_event_name': 'PreToolUse', 'tool_name': 'Edit',
    'tool_input': edit_input(ns_batch, '"entry": ""', '"entry": "新素材行"'),
})
check('subprocess：batch 草稿改 entry 的 Edit → stdout 全空（放行）',
      out_batch_ok == '' and code_batch_ok == 0, repr(out_batch_ok))

out_batch_multi, _ = run_hook({
    'hook_event_name': 'PreToolUse', 'tool_name': 'MultiEdit',
    'tool_input': multi_input(ns_batch, [
        ('"entry": "a"', '"entry": "b"'),
        ('"category": "國際/中東"', '"category": "國際/以巴衝突"')]),
})
try:
    batch_multi_deny = (json.loads(out_batch_multi).get('hookSpecificOutput', {})
                        .get('permissionDecision') == 'deny')
except (ValueError, AttributeError):
    batch_multi_deny = False
check('subprocess：batch 草稿混合 MultiEdit 也無法繞過', batch_multi_deny,
      out_batch_multi)

check('batch 內部函式：tool_input 不是 dict → 不擋（fail-open）',
      gate_guard._batch_tool_input_touches_fields(None) is False)
check('batch 內部函式：old/new 皆非字串 → 不擋（fail-open）',
      gate_guard._batch_edit_touches_fields(None, None) is False)
check('batch 內部函式：_batch_artifact_kind 空路徑 → None',
      gate_guard._batch_artifact_kind('') is None)

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

# ── 既有缺陷修復：*_gate_lock.json 頂層不是 dict（例如被寫成陣列）不炸 ──
d_badlock = os.path.join(TMP, 'badlock_notdict')
os.makedirs(d_badlock, exist_ok=True)
target_badlock = os.path.join(d_badlock, 'ns_entries_1100.json')
with open(target_badlock, 'w', encoding='utf-8') as f:
    f.write('{}')
with open(os.path.join(d_badlock, 'ns_gate_lock.json'), 'w', encoding='utf-8') as f:
    json.dump(['不是 dict，是陣列'], f)
try:
    result_badlock = gate_guard._find_lock_for_path(target_badlock)
    check('_find_lock_for_path：gate_lock.json 頂層不是 dict → 略過不炸、回 None',
          result_badlock is None)
except AttributeError as e:
    check('_find_lock_for_path：gate_lock.json 頂層不是 dict → 略過不炸、回 None',
          False, f'炸了：{e!r}')

# ── 通用兜底：同一 session 同一份 JSON 的 Edit／MultiEdit 次數上限 ──────────
# （2026-09-23，A41 第四種攔截）門檻預設 3：第 1／2 次放行，第 3 次起擋。
# 這條不分檔名也不分欄位，是「未來毛病換位置」時的安全網。
d11 = os.path.join(TMP, 'generic_tally')
os.makedirs(d11, exist_ok=True)


def plain_json(dir_, name):
    """刻意取一個前四條規則都不會命中的檔名／內容（不是 entries／batch／候選檔、
    同目錄也沒有 gate lock），確保測到的真的是第 5 條。"""
    p = os.path.join(dir_, name)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump({'note': 'x'}, f, ensure_ascii=False)
    return p


def tally_snapshot(session_id):
    """把某個 session 的計數檔讀回來（找不到→{}），用來驗「有沒有被計數」。"""
    path = gate_guard._edit_tally_file(TALLY_DIR, session_id)
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


generic_a = plain_json(d11, 'generic_notes.json')
check('前置：通用兜底目標檔沒被前四條命中（無 session_id → 放行）',
      gate_guard.decide_edit(generic_a) is None)

g1 = gate_guard.decide_edit(generic_a, edit_input(generic_a, 'a', 'b'), 'sess-A')
g2 = gate_guard.decide_edit(generic_a, edit_input(generic_a, 'b', 'c'), 'sess-A')
g3 = gate_guard.decide_edit(generic_a, edit_input(generic_a, 'c', 'd'), 'sess-A') or ''
check('通用兜底：同檔第 1 次 Edit → 放行', g1 is None, ascii(str(g1)))
check('通用兜底：同檔第 2 次 Edit → 放行', g2 is None, ascii(str(g2)))
check('通用兜底：同檔第 3 次 Edit → deny', bool(g3))
g4 = gate_guard.decide_edit(generic_a, edit_input(generic_a, 'd', 'e'), 'sess-A') or ''
check('通用兜底：第 4 次以後繼續 deny（不會因為被擋就重置）', bool(g4))

# 訊息內容
check('通用兜底：deny 訊息帶出實際次數與門檻',
      '第 3 次' in g3 and '上限 3 次' in g3, ascii(g3))
check('通用兜底：deny 訊息點名 Edit／MultiEdit 兩個工具',
      'Edit' in g3 and 'MultiEdit' in g3, ascii(g3))
check('通用兜底：deny 訊息帶出檔案路徑', os.path.basename(generic_a) in g3, ascii(g3))
check('通用兜底：deny 訊息誠實承認「不知道對應哪支批次指令」',
      '通用兜底' in g3 and '不知道' in g3, ascii(g3))
check('通用兜底：deny 訊息給兩條出路（專屬批次指令／一次 Write 整份重寫）',
      'Write' in g3 and '整份重寫' in g3, ascii(g3))
check('通用兜底：deny 訊息說明「嘗試次數」含被擋的這次',
      '嘗試次數' in g3, ascii(g3))
check('通用兜底：deny 訊息不冒充前四條的精準指令（不含 gate-clear／自由模式／batch 草稿）',
      'gate-clear' not in g3 and '自由模式' not in g3 and 'batch 草稿' not in g3,
      ascii(g3))
check('通用兜底：deny 訊息不外洩門檻環境變數（免得變成繞過說明書）',
      'S2_GATE_EDIT_THRESHOLD' not in g3, ascii(g3))

# 不同檔案各自獨立計數
generic_b = plain_json(d11, 'other_notes.json')
check('通用兜底：另一份檔案第 1 次 → 放行（每個檔案各自計數）',
      gate_guard.decide_edit(generic_b, edit_input(generic_b, 'a', 'b'), 'sess-A') is None)
check('通用兜底：另一份檔案第 2 次 → 放行',
      gate_guard.decide_edit(generic_b, edit_input(generic_b, 'b', 'c'), 'sess-A') is None)
check('通用兜底：另一份檔案第 3 次 → deny',
      gate_guard.decide_edit(generic_b, edit_input(generic_b, 'c', 'd'), 'sess-A') is not None)

# 不同 session（＝不同輪掃帶）計數重置，不會疊加
check('通用兜底：換一個 session id → 同一份檔案第 1 次重新放行（每輪自然歸零）',
      gate_guard.decide_edit(generic_a, edit_input(generic_a, 'a', 'b'), 'sess-B') is None)
check('通用兜底：新 session 第 2 次仍放行（沒有把舊 session 的次數疊加進來）',
      gate_guard.decide_edit(generic_a, edit_input(generic_a, 'b', 'c'), 'sess-B') is None)
check('通用兜底：新 session 第 3 次才 deny',
      gate_guard.decide_edit(generic_a, edit_input(generic_a, 'c', 'd'), 'sess-B') is not None)
check('通用兜底：兩個 session 各自一份計數檔，內容互不影響',
      tally_snapshot('sess-A') != tally_snapshot('sess-B')
      and len(tally_snapshot('sess-A')) == 2 and len(tally_snapshot('sess-B')) == 1,
      ascii(str((tally_snapshot('sess-A'), tally_snapshot('sess-B')))))

# 路徑變體（反斜線／大小寫）要共用同一筆計數，不能各算各的
generic_c = plain_json(d11, 'path_variant.json')
gate_guard.decide_edit(generic_c, edit_input(generic_c, 'a', 'b'), 'sess-P')
gate_guard.decide_edit(generic_c.replace('/', '\\'),
                       edit_input(generic_c, 'b', 'c'), 'sess-P')
check('通用兜底：反斜線／大小寫變體共用同一筆計數（第 3 次照樣擋）',
      gate_guard.decide_edit(generic_c.upper(),
                             edit_input(generic_c, 'c', 'd'), 'sess-P') is not None)
check('通用兜底：路徑變體只在計數檔留一個 key（_norm 正規化生效）',
      len(tally_snapshot('sess-P')) == 1, ascii(str(tally_snapshot('sess-P'))))

# MultiEdit 一次算 1 次（不是照 edits 陣列筆數算）
# 理由：這條鎖要壓的是 turn 數／cache read token，成本由「工具呼叫次數」決定；
# 一次送 5 筆的 MultiEdit 正是我們要鼓勵的批次行為，照筆數算等於懲罰正確做法。
generic_m = plain_json(d11, 'multi_count.json')
multi5 = multi_input(generic_m, [('a%d' % i, 'b%d' % i) for i in range(5)])
check('通用兜底 MultiEdit：一次 5 筆 edits 仍只算 1 次 → 第 1 次放行',
      gate_guard.decide_edit(generic_m, multi5, 'sess-M') is None)
check('通用兜底 MultiEdit：第 2 次 MultiEdit → 放行',
      gate_guard.decide_edit(generic_m, multi5, 'sess-M') is None)
check('通用兜底 MultiEdit：第 3 次 MultiEdit → deny（MultiEdit 與 Edit 併同一筆計數）',
      gate_guard.decide_edit(generic_m, multi5, 'sess-M') is not None)
check('通用兜底 MultiEdit：計數是 3 不是 15（證明不是照 edits 筆數算）',
      tally_snapshot('sess-M').get(gate_guard._norm(generic_m)) == 3,
      ascii(str(tally_snapshot('sess-M'))))

# 非 .json 一律不管（逐筆改文件／腳本是正常行為）
for _name in ('notes.md', 'helper.txt', 'tool.py', 'settings.jsonc'):
    _p = os.path.join(d11, _name)
    with open(_p, 'w', encoding='utf-8') as f:
        f.write('x')
    _allowed = all(
        gate_guard.decide_edit(_p, edit_input(_p, 'a', 'b'), 'sess-NONJSON') is None
        for _ in range(5))
    check(f'通用兜底：非 .json 連改 5 次照樣放行、完全不計數：{_name}',
          _allowed and not tally_snapshot('sess-NONJSON'))

# session_id 缺席 → 整條規則跳過（沒有「同一輪」的定義，不准用全域計數檔）
generic_nosess = plain_json(d11, 'no_session.json')
_tally_files_before = sorted(os.listdir(TALLY_DIR))
check('通用兜底：沒有 session_id → 連改 10 次都放行（不計數）',
      all(gate_guard.decide_edit(generic_nosess,
                                 edit_input(generic_nosess, 'a', 'b')) is None
          for _ in range(10)))
check('通用兜底：沒有 session_id → 計數夾內容完全沒變（連檔案都不碰）',
      sorted(os.listdir(TALLY_DIR)) == _tally_files_before,
      str(sorted(os.listdir(TALLY_DIR))))

# 計數檔壞掉 → fail-open（從 0 重算，不准誤擋也不准炸）
generic_corrupt = plain_json(d11, 'corrupt_tally.json')
gate_guard.decide_edit(generic_corrupt, edit_input(generic_corrupt, 'a', 'b'), 'sess-C')
gate_guard.decide_edit(generic_corrupt, edit_input(generic_corrupt, 'b', 'c'), 'sess-C')
with open(gate_guard._edit_tally_file(TALLY_DIR, 'sess-C'), 'w', encoding='utf-8') as f:
    f.write('{ 這不是合法 JSON')
check('通用兜底：計數檔內容壞掉 → 從 0 重算（放行，fail-open）',
      gate_guard.decide_edit(generic_corrupt,
                             edit_input(generic_corrupt, 'c', 'd'), 'sess-C') is None)
with open(gate_guard._edit_tally_file(TALLY_DIR, 'sess-C'), 'w', encoding='utf-8') as f:
    json.dump(['頂層不是 dict'], f)
check('通用兜底：計數檔頂層不是 dict → 一樣從 0 重算、不炸',
      gate_guard.decide_edit(generic_corrupt,
                             edit_input(generic_corrupt, 'd', 'e'), 'sess-C') is None)

# 門檻可用環境變數調整
generic_thr = plain_json(d11, 'threshold_env.json')
os.environ['S2_GATE_EDIT_THRESHOLD'] = '5'
try:
    _thr_results = [gate_guard.decide_edit(generic_thr,
                                           edit_input(generic_thr, 'a', 'b'), 'sess-T')
                    for _ in range(5)]
    check('通用兜底：門檻改 5 → 前 4 次放行',
          all(r is None for r in _thr_results[:4]), ascii(str(_thr_results[:4])))
    check('通用兜底：門檻改 5 → 第 5 次 deny 且訊息寫「上限 5 次」',
          _thr_results[4] is not None and '上限 5 次' in (_thr_results[4] or ''),
          ascii(str(_thr_results[4])))
    os.environ['S2_GATE_EDIT_THRESHOLD'] = '不是數字'
    check('通用兜底：門檻環境變數不是數字 → 退回預設 3',
          gate_guard._edit_tally_threshold() == 3)
    os.environ['S2_GATE_EDIT_THRESHOLD'] = '0'
    check('通用兜底：門檻環境變數 <1 → 退回預設 3（不准設成「第 0 次就擋」）',
          gate_guard._edit_tally_threshold() == 3)
finally:
    os.environ.pop('S2_GATE_EDIT_THRESHOLD', None)
check('通用兜底：拿掉環境變數 → 門檻回到預設 3',
      gate_guard._edit_tally_threshold() == 3)

# ── 優先序：前四條擋下的 Edit 不計數、訊息也不被第 5 條搶走 ──────────────
_before_lock = dict(tally_snapshot('sess-PRIO'))
for _ in range(5):
    _r = gate_guard.decide_edit(entries1, edit_input(entries1, 'a', 'b'), 'sess-PRIO') or ''
    check('優先序：有 gate lock 的檔案連打 5 次 → 每次都回 lock 訊息（不被次數鎖搶走）',
          'gate-clear' in _r and '同檔逐筆 Edit 次數上限' not in _r, ascii(_r))
for _ in range(5):
    _r = gate_guard.decide_edit(platform_entries,
                                edit_input(platform_entries, 'a', 'b'), 'sess-PRIO') or ''
    check('優先序：ENEX entries 連打 5 次 → 每次都回 platform bridge 訊息',
          's2_platform_bridge.py rewrite-entry' in _r
          and '同檔逐筆 Edit 次數上限' not in _r, ascii(_r))
for _ in range(5):
    _r = gate_guard.decide_edit(ns_entries_nolock,
                                edit_input(ns_entries_nolock, 'a', 'b'), 'sess-PRIO') or ''
    check('優先序：NS entries 連打 5 次 → 每次都回自由模式訊息',
          '自由模式' in _r and '同檔逐筆 Edit 次數上限' not in _r, ascii(_r))
for _ in range(5):
    _r = gate_guard.decide_edit(ns_batch, edit_input(
        ns_batch, '"category": "A/B"', '"category": "A/C"'), 'sess-PRIO') or ''
    check('優先序：batch 草稿改 category 連打 5 次 → 每次都回 batch 欄位鎖訊息',
          'batch 草稿' in _r and '同檔逐筆 Edit 次數上限' not in _r, ascii(_r))
check('優先序：被前四條擋下的檔案完全沒有進計數檔（不重複計數）',
      tally_snapshot('sess-PRIO') == _before_lock,
      ascii(str(tally_snapshot('sess-PRIO'))))

# 但 batch 草稿改「其他欄位」是被第 4 條放行的，就該進計數、第 3 次由第 5 條接手
_batch_entry_edit = edit_input(ns_batch, '"entry": "a"', '"entry": "b"')
check('銜接：batch 草稿改 entry（第 4 條放行）第 1 次 → 放行',
      gate_guard.decide_edit(ns_batch, _batch_entry_edit, 'sess-HANDOFF') is None)
check('銜接：batch 草稿改 entry 第 2 次 → 放行',
      gate_guard.decide_edit(ns_batch, _batch_entry_edit, 'sess-HANDOFF') is None)
_handoff = gate_guard.decide_edit(ns_batch, _batch_entry_edit, 'sess-HANDOFF') or ''
check('銜接：batch 草稿改 entry 第 3 次 → 由第 5 條（通用次數上限）接手擋下',
      '同檔逐筆 Edit 次數上限' in _handoff and 'batch 草稿' not in _handoff,
      ascii(_handoff))

# ── 計數檔落點與清理 ────────────────────────────────────────────────
_tally_basenames = {os.path.basename(gate_guard._edit_tally_file(TALLY_DIR, s))
                    for s in ('sess-A', 'sess-B', 'sess-M', 'sess-P')}
check('計數檔：落在 S2_GATE_TALLY_DIR，不汙染目標檔案所在目錄（雲端同步夾）',
      os.path.isdir(TALLY_DIR)
      and _tally_basenames <= set(os.listdir(TALLY_DIR))
      and not (_tally_basenames & set(os.listdir(d11))),
      str(sorted(os.listdir(d11))))
check('計數檔：寫完不留 .tmp 暫存檔（os.replace 原子換名）',
      not [n for n in os.listdir(TALLY_DIR) if n.endswith('.tmp')],
      str(sorted(os.listdir(TALLY_DIR))))

_stale = os.path.join(TALLY_DIR, 'stale-session-0000000000.json')
with open(_stale, 'w', encoding='utf-8') as f:
    json.dump({'x': 1}, f)
_old = time.time() - (25 * 60 * 60)
os.utime(_stale, (_old, _old))
_fresh_keep = gate_guard._edit_tally_file(TALLY_DIR, 'sess-A')
check('前置：過期計數檔與現役計數檔都存在',
      os.path.exists(_stale) and os.path.exists(_fresh_keep))
generic_sweep = plain_json(d11, 'sweep_trigger.json')
gate_guard.decide_edit(generic_sweep, edit_input(generic_sweep, 'a', 'b'), 'sess-SWEEP')
check('計數檔清理：新 session 第一次建檔時順手刪掉超過 24 小時的舊計數檔',
      not os.path.exists(_stale))
check('計數檔清理：沒過期的其他 session 計數檔不會被誤刪',
      os.path.exists(_fresh_keep))

# ── subprocess 全流程：真的走一次 stdin→stdout hook 協議 ────────────────
generic_sub = plain_json(d11, 'subprocess_tally.json')


def run_generic(session_id):
    return run_hook({
        'hook_event_name': 'PreToolUse', 'tool_name': 'Edit',
        'session_id': session_id,
        'tool_input': edit_input(generic_sub, 'a', 'b'),
    })


out_g1, code_g1 = run_generic('sess-SUB')
out_g2, _ = run_generic('sess-SUB')
out_g3, code_g3 = run_generic('sess-SUB')
check('subprocess：帶 session_id 的第 1 次 Edit → stdout 全空（放行）',
      out_g1 == '' and code_g1 == 0, repr(out_g1))
check('subprocess：第 2 次 Edit → 仍放行', out_g2 == '', repr(out_g2))
try:
    generic_deny_payload = json.loads(out_g3)
    generic_deny_ok = (
        generic_deny_payload.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny'
        and generic_deny_payload.get('hookSpecificOutput', {}).get('hookEventName') == 'PreToolUse')
except (ValueError, AttributeError):
    generic_deny_ok = False
check('subprocess：第 3 次 Edit → 合法 deny JSON（exit 0）',
      code_g3 == 0 and generic_deny_ok, out_g3)
check('subprocess：通用兜底 deny 輸出是 ASCII 安全（ensure_ascii，cp950 主控台不炸）',
      all(ord(c) < 128 for c in out_g3.strip()) if out_g3.strip() else False,
      repr(out_g3))
out_g_other, _ = run_generic('sess-SUB-OTHER')
check('subprocess：換一個 session_id → 同一份檔案重新從第 1 次算起（放行）',
      out_g_other == '', repr(out_g_other))

# MultiEdit 走 subprocess 也要併進同一筆計數
generic_sub_multi = plain_json(d11, 'subprocess_multi.json')
for _i in range(2):
    run_hook({'hook_event_name': 'PreToolUse', 'tool_name': 'MultiEdit',
              'session_id': 'sess-SUBM',
              'tool_input': multi_input(generic_sub_multi, [('a', 'b'), ('c', 'd')])})
out_sm, _ = run_hook({'hook_event_name': 'PreToolUse', 'tool_name': 'Edit',
                      'session_id': 'sess-SUBM',
                      'tool_input': edit_input(generic_sub_multi, 'e', 'f')})
try:
    subm_deny = (json.loads(out_sm).get('hookSpecificOutput', {})
                 .get('permissionDecision') == 'deny')
except (ValueError, AttributeError):
    subm_deny = False
check('subprocess：MultiEdit×2 ＋ Edit×1 → 第 3 次被擋（兩種工具併同一筆計數）',
      subm_deny, out_sm)

# PostToolUse／Write 不會被第 5 條計數（Write 本來就是建議路徑）
generic_write = plain_json(d11, 'write_not_counted.json')
for _i in range(5):
    run_hook({'hook_event_name': 'PostToolUse', 'tool_name': 'Write',
              'session_id': 'sess-WRITE',
              'tool_input': {'file_path': generic_write, 'content': '{}'},
              'tool_response': {'success': True}})
check('Write 不計數：PostToolUse Write×5 後，Edit 仍從第 1 次算起（放行）',
      gate_guard.decide_edit(generic_write,
                             edit_input(generic_write, 'a', 'b'), 'sess-WRITE') is None)

# 內部函式邊界
check('通用兜底內部函式：空路徑 → None',
      gate_guard._generic_edit_reason('', 'sess-X') is None)
check('通用兜底內部函式：session_id 空字串 → None',
      gate_guard._generic_edit_reason(generic_a, '') is None)

# 計數機制自己壞掉（磁碟滿、權限、目錄被刪…）→ 不准擋、不准炸。
# 直接把 `_bump_edit_tally` 換成一定會拋例外的版本，確保走的是 except 分支，
# 而不是「剛好次數還沒到門檻」這種假通過。
_real_bump = gate_guard._bump_edit_tally


def _boom(*_a, **_kw):
    raise OSError('模擬計數檔寫入失敗')


gate_guard._bump_edit_tally = _boom
try:
    _failopen = [gate_guard._generic_edit_reason(generic_a, 'sess-A') for _ in range(5)]
    check('通用兜底：計數機制落地失敗（丟例外）→ 連 5 次都放行，不擋也不炸',
          all(r is None for r in _failopen), ascii(str(_failopen)))
    check('通用兜底：計數機制壞掉時 decide_edit 整體仍正常回傳（不影響前四條）',
          gate_guard.decide_edit(entries1, edit_input(entries1, 'a', 'b'),
                                 'sess-A') is not None)
finally:
    gate_guard._bump_edit_tally = _real_bump
check('通用兜底：還原後計數機制照常運作（sess-A 的 generic_notes.json 仍在門檻上）',
      gate_guard._generic_edit_reason(generic_a, 'sess-A') is not None)
check('通用兜底內部函式：session id 清洗後撞名也不會共用計數檔（sha1 短碼區隔）',
      gate_guard._edit_tally_file(TALLY_DIR, 'a/b')
      != gate_guard._edit_tally_file(TALLY_DIR, 'a:b'),
      gate_guard._edit_tally_file(TALLY_DIR, 'a/b'))

print(f'\nPASS={sum(results)} FAIL={len(results) - sum(results)}')
sys.exit(0 if all(results) else 1)
