#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`s2_batch_prep.py rename-field` 測試（R33，2026-09-14）。

背景：0909-0700 那輪 agent 想把 `ns_batch_0700.json` 裡打錯的鍵名 `raw_entry`
整批改成 `entry`，手寫 `python -c` 讀檔改字串再回寫被 `s2_bash_guard.py` 依
13d §4 攔下——guard 本身沒問題，是攔下之後沒有標準工具可走。這支測試護欄：

  - list／wrapper／flatmap 三種既有形狀都要吃
  - wrapper 的 `new_topics`、flatmap 的 `_new_topics` 保留鍵原樣不動
  - 目的鍵衝突、來源鍵全缺、形狀認不出來 → 整批拒絕、不寫任何檔案
  - 永不原地覆寫（--out 等於輸入檔要拒絕）
  - 拒絕操作生產狀態檔（`{MMDD}-s2-state.json` 命名慣例）
  - --dry-run 不寫檔

用法：python -X utf8 scripts/test_s2_rename_field.py
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'bp', os.path.join(HERE, 's2_batch_prep.py'))
bp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bp)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass

TMP = tempfile.mkdtemp(prefix='s2_rf_test_')
results = []


def check(name, cond, extra=''):
    results.append(bool(cond))
    print(f'{"PASS" if cond else "FAIL"}  {name}{(" -> " + str(extra)) if extra else ""}')


def write_json(name, obj):
    p = os.path.join(TMP, name)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
    return p


def read_json(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


class Args:
    def __init__(self, **kw):
        kw.setdefault('out', None)
        kw.setdefault('dry_run', False)
        self.__dict__.update(kw)


def run(args):
    """跑 cmd_rename_field，回傳 (合併輸出, exit_code)。sys.exit 不讓它中斷測試。"""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with redirect_stdout(out), redirect_stderr(err):
            bp.cmd_rename_field(args)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (1 if e.code else 0)
    return out.getvalue() + err.getvalue(), code


# ── ① 多筆改名（list 形狀）──────────────────────────────────────────
p1 = write_json('list_1.json', [
    {'id': 'RT0001', 'raw_entry': '第一則'},
    {'id': 'RT0002', 'raw_entry': '第二則'},
    {'id': 'RT0003', 'category': '社會/測試'},  # 沒有 raw_entry 也沒有 entry，純粹跳過
])
out1, code1 = run(Args(batch=p1, from_key='raw_entry', to_key='entry'))
check('① exit 0', code1 == 0, code1)
out1_path = os.path.join(TMP, 'list_1.renamed.json')
check('① 預設輸出檔名是 <name>.renamed.json', os.path.exists(out1_path))
data1 = read_json(out1_path)
check('① RT0001 改名成功、值不變', data1[0].get('entry') == '第一則' and 'raw_entry' not in data1[0])
check('① RT0002 改名成功', data1[1].get('entry') == '第二則' and 'raw_entry' not in data1[1])
check('① RT0003（本來沒有 raw_entry）維持原樣、沒被硬塞 entry',
      'entry' not in data1[2] and data1[2].get('category') == '社會/測試')
check('① 印出改到 2 筆、跳過 1 筆', '2 筆改到' in out1 and '1 筆沒有這個鍵' in out1, out1[:200])
check('① 原檔內容不變（仍是 raw_entry）', read_json(p1)[0].get('raw_entry') == '第一則')

# ── ② wrapper 外殼保留（new_topics 原樣不動）──────────────────────────
p2 = write_json('wrapper_1.json', {
    'entries': [
        {'id': 'AP0001', 'raw_entry': '摘要甲'},
        {'id': 'AP0002', 'raw_entry': '摘要乙'},
    ],
    'new_topics': {'某中主題': {'charter': '收什麼', 'big': '社會'}},
})
out2, code2 = run(Args(batch=p2, from_key='raw_entry', to_key='entry'))
check('② exit 0', code2 == 0, code2)
data2 = read_json(os.path.join(TMP, 'wrapper_1.renamed.json'))
check('② entries 兩筆都改名', all('entry' in e and 'raw_entry' not in e for e in data2['entries']))
check('② new_topics 外殼原樣保留、未被誤當 entry', data2.get('new_topics') == {'某中主題': {'charter': '收什麼', 'big': '社會'}})

# ── ③ flatmap 外殼保留（_new_topics 原樣不動）─────────────────────────
p3 = write_json('flatmap_1.json', {
    'NS0001': {'raw_entry': '摘要丙', 'category': '社會/測試'},
    'NS0002': {'raw_entry': '摘要丁'},
    '_new_topics': {'新題': {'charter': '章程', 'big': '國際'}},
})
out3, code3 = run(Args(batch=p3, from_key='raw_entry', to_key='entry'))
check('③ exit 0', code3 == 0, code3)
data3 = read_json(os.path.join(TMP, 'flatmap_1.renamed.json'))
check('③ NS0001 改名成功、其他欄位不動', data3['NS0001'].get('entry') == '摘要丙' and data3['NS0001'].get('category') == '社會/測試')
check('③ NS0002 改名成功', data3['NS0002'].get('entry') == '摘要丁')
check('③ _new_topics 保留鍵原樣不動、未被當成一則 entry 掃進去改名',
      data3.get('_new_topics') == {'新題': {'charter': '章程', 'big': '國際'}})

# ── ④ 衝突：目的鍵已存在 → 整批拒絕、不寫檔 ──────────────────────────
p4 = write_json('conflict_1.json', [
    {'id': 'RT0011', 'raw_entry': '甲', 'entry': '已經有 entry 了'},
    {'id': 'RT0012', 'raw_entry': '乙'},
])
out4_path = os.path.join(TMP, 'conflict_1.renamed.json')
out4, code4 = run(Args(batch=p4, from_key='raw_entry', to_key='entry'))
check('④ 目的鍵衝突 → 非 0 exit', code4 != 0, code4)
check('④ 錯誤訊息點名衝突的 id', 'RT0011' in out4, out4[:200])
check('④ 沒有寫出任何檔案', not os.path.exists(out4_path))

# ── ⑤ 來源鍵在全部項目都不存在 → 整批拒絕、不寫檔 ─────────────────────
p5 = write_json('missing_1.json', [
    {'id': 'RT0021', 'entry': '甲'},
    {'id': 'RT0022', 'entry': '乙'},
])
out5_path = os.path.join(TMP, 'missing_1.renamed.json')
out5, code5 = run(Args(batch=p5, from_key='raw_entry', to_key='entry_v2'))
check('⑤ 來源鍵全缺 → 非 0 exit', code5 != 0, code5)
check('⑤ 沒有寫出任何檔案', not os.path.exists(out5_path))

# ── ⑥ 資料形態不符（bad shape）→ 整批拒絕、不寫檔 ──────────────────────
p6 = write_json('bad_shape_1.json', {'不是entries也不是flatmap': 123, 'new_topics': {}})
# 上面這個形狀：頂層 dict，沒有 entries 陣列，且非保留鍵只有一個且值不是 dict——
# 會被 _load_batch_any 判成 flatmap（因為有非保留鍵），但 _iter_rename_entries
# 找不到任何 dict 值 → 「找不到可改名的項目」錯誤路徑。另外驗一個真正認不出來的頂層。
out6_path = os.path.join(TMP, 'bad_shape_1.renamed.json')
out6, code6 = run(Args(batch=p6, from_key='raw_entry', to_key='entry'))
check('⑥a flatmap 值非 dict → 找不到可改項、拒絕', code6 != 0, code6)
check('⑥a 沒有寫出任何檔案', not os.path.exists(out6_path))

p6b = write_json('bad_shape_2.json', '純字串，頂層不是 list 也不是 dict？其實 JSON 頂層字串會被 json.load 讀成 str')
out6b_path = os.path.join(TMP, 'bad_shape_2.renamed.json')
out6b, code6b = run(Args(batch=p6b, from_key='raw_entry', to_key='entry'))
check('⑥b 頂層是字串 → 形狀認不出來、拒絕', code6b != 0, code6b)
check('⑥b 沒有寫出任何檔案', not os.path.exists(out6b_path))

# ── ⑦ 原檔在成功案例中也不能被動到（① 已驗過 list，這裡補 wrapper／flatmap）──
check('⑦ wrapper 原檔內容不變', read_json(p2)['entries'][0].get('raw_entry') == '摘要甲')
check('⑦ flatmap 原檔內容不變', read_json(p3)['NS0001'].get('raw_entry') == '摘要丙')

# ── ⑧ --out 等於輸入檔 → 拒絕 ────────────────────────────────────────
p8 = write_json('same_out_1.json', [{'id': 'RT0031', 'raw_entry': '甲'}])
out8, code8 = run(Args(batch=p8, from_key='raw_entry', to_key='entry', out=p8))
check('⑧ --out==輸入檔 → 非 0 exit', code8 != 0, code8)
check('⑧ 原檔沒被改壞（仍是 raw_entry）', read_json(p8)[0].get('raw_entry') == '甲')

# ── ⑨ 生產 state 路徑拒絕（{MMDD}-s2-state.json 命名慣例）─────────────
p9 = write_json('0999-s2-state.json', [{'id': 'RT0041', 'raw_entry': '甲'}])
out9_path = os.path.join(TMP, '0999-s2-state.renamed.json')
out9, code9 = run(Args(batch=p9, from_key='raw_entry', to_key='entry'))
check('⑨ 生產 state 檔名 → 非 0 exit', code9 != 0, code9)
check('⑨ 錯誤訊息講明是生產狀態檔', '生產狀態檔' in out9, out9[:200])
check('⑨ 沒有寫出任何檔案', not os.path.exists(out9_path))

# ── ⑩ --dry-run 不寫任何檔案，但照樣印預覽 ──────────────────────────
p10 = write_json('dryrun_1.json', [
    {'id': 'RT0051', 'raw_entry': '甲'},
    {'id': 'RT0052', 'raw_entry': '乙'},
])
out10_path = os.path.join(TMP, 'dryrun_1.renamed.json')
out10, code10 = run(Args(batch=p10, from_key='raw_entry', to_key='entry', dry_run=True))
check('⑩ dry-run exit 0', code10 == 0, code10)
check('⑩ dry-run 沒有寫出任何檔案', not os.path.exists(out10_path))
check('⑩ dry-run 仍印出改到 2 筆的預覽', '2 筆改到' in out10, out10[:200])
check('⑩ dry-run 原檔不變', read_json(p10)[0].get('raw_entry') == '甲')

# ── guard 驗證附帶檢查：呼叫 rename-field 這條指令本身要被 guard 放行 ────
# （R33 明文界線：這支工具不是繞 guard，是既有授權路徑的窄出口——guard 不必改）
sys.path.insert(0, HERE)
import s2_bash_guard as guard  # noqa: E402
_cmd = ('python E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py rename-field '
        'ns_batch_0700.json --from raw_entry --to entry --out out.json')
check('guard：呼叫 rename-field 的標準指令被放行（basename 命中 s2_ 白名單）',
      guard.decide('Bash', _cmd) is None)

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print(f'\nPASS={sum(results)} FAIL={len(results) - sum(results)}')
sys.exit(0 if all(results) else 1)
