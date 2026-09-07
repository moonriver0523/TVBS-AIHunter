#!/usr/bin/env python3
"""s2_batch_prep.py `from-raw` 骨架＋提示表（含 D12 已在庫標記）測試（09-A24）。

比照 test_s2_batch_prep.py 的手動 check() 跑法（`python test_s2_from_raw.py`），
不用 pytest。

覆蓋：
  - Task 1：AP raw 4 則（1 則 prelim），狀態檔已有其中 2 則
            （1 則 has_script、1 則就是那個 prelim 的 pending）。
    斷言：骨架排除 has_script 那則、留 3 則；pending 的保留並帶 prev_status；
    提示表 3 行；尾行講清楚已在庫略過幾則、pending 保留幾則。
  - Task 2：`build --skeleton` 用骨架 ＋ 極小 entries（{id:{entry,category,tc}}）
    合併出三鍵齊全的 batch。
"""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'bp_from_raw', os.path.join(HERE, 's2_batch_prep.py'))
bp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bp)

TMP = tempfile.mkdtemp(prefix='s2_a24_test_')
results = []


def check(name, cond, extra=''):
    results.append(bool(cond))
    print(f'{"PASS" if cond else "FAIL"}  {name}{(" -> " + extra) if extra else ""}')


def write_json(name, obj):
    p = os.path.join(TMP, name)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
    return p


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def run(fn, args):
    """跑子指令，回傳 (合併輸出, exit_code)。sys.exit 不讓它中斷測試。"""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with redirect_stdout(out), redirect_stderr(err):
            fn(args)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    return out.getvalue() + err.getvalue(), code


# ── Task 1：from-raw 骨架＋提示表＋D12 已在庫標記 ──────────────────

AP_RAW = write_json('ap_raw.json', [
    {'id': 'AP1001', 'head': 'Prelim story on floods', 'script': 'SHOTLIST: flood scenes',
     'sb_count': 1, 'has_sot': False, 'prelim': True, 'dur': '00:01:20', 'src': 'AP'},
    {'id': 'AP1002', 'head': 'Already has script', 'script': 'SHOTLIST: already filed',
     'sb_count': 0, 'has_sot': False, 'prelim': False, 'dur': '00:00:55', 'src': 'AP'},
    {'id': 'AP1003', 'head': 'Fresh item three', 'script': 'SHOTLIST: fresh three',
     'sb_count': 2, 'has_sot': True, 'prelim': False, 'dur': '00:02:10', 'src': 'AP'},
    {'id': 'AP1004', 'head': 'Fresh item four', 'script': 'SHOTLIST: fresh four',
     'sb_count': 0, 'has_sot': False, 'prelim': False, 'dur': '00:01:45', 'src': 'AP'},
])

# 狀態檔：AP1002 已經 has_script（該排除）；AP1001（就是那個 prelim 的）已是 pending（該保留＋標記）。
STATE_FILE = write_json('0907-s2-state.json', {
    'date': '2026-09-07',
    'checkpoint': '0907-1000',
    'items': [
        {'id': 'AP1002', 'source': 'AP', 'script_status': 'has_script', 'entry': '既有稿'},
        {'id': 'AP1001', 'source': 'AP', 'script_status': 'pending', 'entry': ''},
    ],
})

skel_out = os.path.join(TMP, 'ap_skeleton_1000.json')
fr_out, fr_code = run(bp.cmd_from_raw, Args(
    site='ap', raw=AP_RAW, checkpoint='0907-1000', state=STATE_FILE,
    out=skel_out, page=None,
))

check('from-raw 正常結束（exit 0）', fr_code == 0, f'code={fr_code}\n{fr_out}')
check('from-raw 骨架檔已寫出', os.path.exists(skel_out))

skeleton = []
if os.path.exists(skel_out):
    with open(skel_out, encoding='utf-8') as f:
        skeleton = json.load(f)

check('骨架含 3 則（排除已在庫 has_script 的 AP1002）', len(skeleton) == 3,
      f'實際 {len(skeleton)} 則：{[r.get("id") for r in skeleton]}')

by_id = {r.get('id'): r for r in skeleton}
check('AP1002（has_script）被排除', 'AP1002' not in by_id)
check('AP1001（prelim 的 pending）有保留', 'AP1001' in by_id)
check('AP1001 標 prev_status=pending', by_id.get('AP1001', {}).get('prev_status') == 'pending',
      str(by_id.get('AP1001')))
check('AP1003／AP1004 都在（新則，無 prev_status）',
      'AP1003' in by_id and 'AP1004' in by_id
      and 'prev_status' not in by_id['AP1003'] and 'prev_status' not in by_id['AP1004'])

REQUIRED_ROW_KEYS = {'id', 'source', 'checkpoint', 'status', 'src_text', 'sb_count', 'has_sot'}
for iid, row in by_id.items():
    missing_keys = REQUIRED_ROW_KEYS - set(row.keys())
    check(f'{iid} 骨架含必備欄位 {sorted(REQUIRED_ROW_KEYS)}', not missing_keys,
          f'缺：{missing_keys}')
    check(f'{iid} entry/category/tc 皆空字串',
          row.get('entry') == '' and row.get('category') == '' and row.get('tc') == '',
          str({k: row.get(k) for k in ('entry', 'category', 'tc')}))

table_lines = [ln for ln in fr_out.splitlines() if ln.startswith('#')]
check('提示表 3 行', len(table_lines) == 3, f'實際：{table_lines}')
check('尾行講已在庫略過 1 則、且列出 AP1002',
      '已在庫略過 1 則' in fr_out and 'AP1002' in fr_out, fr_out)
check('尾行講 pending 保留 1 則、且列出 AP1001',
      'pending 保留 1 則' in fr_out and 'AP1001' in fr_out, fr_out)
check('尾行講骨架已寫（含檔名與則數）',
      '骨架已寫' in fr_out and '3 則' in fr_out, fr_out)


# ── Task 1 附帶：子指令不存在時應 FAIL（先確認 TDD 紅燈曾經成立）──────
# 這段只是留給人看 TDD 軌跡，不影響本輪判定：cmd_from_raw 已存在於 bp 模組，
# `hasattr` 必為 True；若未來重構把它砍掉，這行會先炸，比整份測試安靜消失好查。
check('cmd_from_raw 存在於 s2_batch_prep 模組', hasattr(bp, 'cmd_from_raw'))


# ── Task 2：build --skeleton 用骨架 ＋ 極小 entries 合併出 batch ──────

mini_entries = write_json('mini_entries.json', {
    'AP1001': {'entry': '◆ AP1001 (…) 洪災畫面。◇畫面重點：…◇備註：無',
               'category': '國際/氣候', 'tc': 'T1,T2/C3'},
    'AP1003': {'entry': '◆ AP1003 (…) 第三則。◇畫面重點：…◇備註：無',
               'category': '國際/一般', 'tc': 'T4/C1'},
    # AP1004 故意不給 entry → 應該落到「未填」警告，不進 batch。
})

batch_out = os.path.join(TMP, 'ap_batch_1000.json')
b_out, b_code = run(bp.cmd_build, Args(
    site='ap', raw=AP_RAW, entries=mini_entries, checkpoint='0907-1000',
    skeleton=skel_out, out=batch_out,
))

check('build --skeleton 正常結束（exit 0）', b_code == 0, f'code={b_code}\n{b_out}')
check('build --skeleton 輸出檔已寫出', os.path.exists(batch_out))

batch = []
if os.path.exists(batch_out):
    with open(batch_out, encoding='utf-8') as f:
        batch = json.load(f)
if isinstance(batch, dict):          # P1b-2（2026-09-07）：build --skeleton 改出 {entries,new_topics} 新格式
    batch = batch.get('entries') or []

batch_by_id = {r.get('id'): r for r in batch}
check('batch 只有 AP1001／AP1003（AP1004 缺 entry 不進 batch，AP1002 本來就不在骨架）',
      set(batch_by_id) == {'AP1001', 'AP1003'}, str(sorted(batch_by_id)))

for iid in ('AP1001', 'AP1003'):
    row = batch_by_id.get(iid, {})
    check(f'{iid} batch 三鍵齊（entry/category/tc）',
          bool(row.get('entry')) and bool(row.get('category')) and bool(row.get('tc')),
          str(row))
    check(f'{iid} batch 仍保留機械欄位（source/checkpoint/status/src_text/sb_count/has_sot）',
          all(k in row for k in ('source', 'checkpoint', 'status', 'src_text', 'sb_count', 'has_sot')),
          str(row))
    check(f'{iid} batch 不殘留骨架內部欄位（hint/prev_status）',
          'hint' not in row and 'prev_status' not in row, str(row))

check('AP1004 缺 entry 列入「未填」警告', 'AP1004' in b_out and ('未填' in b_out or '沒填' in b_out),
      b_out)


# ── R22：RT detail 檔編號在 `edit` 鍵，不是 `code`（0907 A24 真實快照試跑實測）──
# `SITE_SPEC['rt']['id_of']` 原本只認 `code`，detail 檔全部 id_of 回空字串，
# 8 則被 dedup_by_id 當同一個 id 去重成 1 則。修法：`code` 有值優先用，
# 沒有才退 `edit`（且 `edit` 要含數字才採信——上游有純字母的退化值）。

check('_rt_code_or_edit：code 優先於 edit',
      bp._rt_code_or_edit({'code': 'RT9001', 'edit': 'RT9999'}) == 'RT9001')
check('_rt_code_or_edit：沒有 code 才退 edit',
      bp._rt_code_or_edit({'edit': 'RT9002'}) == 'RT9002')
check('_rt_code_or_edit：edit 沒有數字（退化值）視同沒有',
      bp._rt_code_or_edit({'edit': 'RT'}) == '')
check('_rt_code_or_edit：edit 帶雙前綴但有數字仍採信（上游髒值，非本次要修的範圍）',
      bp._rt_code_or_edit({'edit': 'RTRT7400'}) == 'RTRT7400')
check('_rt_code_or_edit：code／edit 都沒有回空字串',
      bp._rt_code_or_edit({}) == '')

RT_DETAIL_EDIT_ONLY = write_json('rt_detail_edit_only.json', [
    {'edit': 'RT7001', 'head': 'Tennis final highlights', 'story': 'SHOTLIST: match highlights',
     'sb_count': 1, 'dur': '00:02:05', 'src': 'RT'},
    {'edit': 'RT7002', 'head': 'Flood aftermath', 'story': 'SHOTLIST: flood aftermath scenes',
     'sb_count': 0, 'dur': '00:01:30', 'src': 'RT'},
    {'edit': 'RT7003', 'head': 'Market close report', 'story': 'SHOTLIST: trading floor',
     'sb_count': 2, 'dur': '00:00:58', 'src': 'RT'},
])

rt_skel_out = os.path.join(TMP, 'rt_skeleton_1200.json')
rt_out, rt_code = run(bp.cmd_from_raw, Args(
    site='rt', raw=RT_DETAIL_EDIT_ONLY, checkpoint='0907-1200', state=None,
    out=rt_skel_out, page=None,
))
check('from-raw（RT detail，只有 edit 鍵）正常結束（exit 0）', rt_code == 0, f'code={rt_code}\n{rt_out}')

rt_skeleton = []
if os.path.exists(rt_skel_out):
    with open(rt_skel_out, encoding='utf-8') as f:
        rt_skeleton = json.load(f)
rt_ids = sorted(r.get('id') for r in rt_skeleton)
check('RT detail（只有 edit 鍵）骨架 3 則、id 正確（沒有被去重成 1 則）',
      rt_ids == ['RT7001', 'RT7002', 'RT7003'], f'實際：{rt_ids}')

RT_LIST_CODE = write_json('rt_list_code.json', [
    {'code': 'RT8001', 'head': 'List format story one', 'story': 'SHOTLIST: one', 'sb_count': 1,
     'dur': '00:01:00', 'src': 'RT'},
    {'code': 'RT8002', 'head': 'List format story two', 'story': 'SHOTLIST: two', 'sb_count': 0,
     'dur': '00:01:10', 'src': 'RT'},
])

rt_list_skel_out = os.path.join(TMP, 'rt_list_skeleton_1200.json')
rt_list_out, rt_list_code = run(bp.cmd_from_raw, Args(
    site='rt', raw=RT_LIST_CODE, checkpoint='0907-1200', state=None,
    out=rt_list_skel_out, page=None,
))
check('from-raw（RT list，code 鍵）正常結束（exit 0）', rt_list_code == 0,
      f'code={rt_list_code}\n{rt_list_out}')

rt_list_skeleton = []
if os.path.exists(rt_list_skel_out):
    with open(rt_list_skel_out, encoding='utf-8') as f:
        rt_list_skeleton = json.load(f)
rt_list_ids = sorted(r.get('id') for r in rt_list_skeleton)
check('RT list（code 鍵）骨架 2 則、id 正確（既有行為不變）',
      rt_list_ids == ['RT8001', 'RT8002'], f'實際：{rt_list_ids}')


shutil.rmtree(TMP, ignore_errors=True)

print(f'\n共 {len(results)} 項，通過 {sum(results)}，失敗 {len(results) - sum(results)}')
sys.exit(0 if all(results) else 1)
