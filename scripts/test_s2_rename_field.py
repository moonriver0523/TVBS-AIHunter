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
import shutil
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

# ── ⑪ STATE_DIR 判準（2026-09-14 review fix）─────────────────────────
# 舊版 `commonpath(ab, state_dir) == state_dir` 會把**帶日期的子資料夾**
# （掃帶輪次工作 batch 實際落腳處，`s2_scan.ps1` 每輪 cwd 設在這一層）也當成
# 生產 state 一併擋掉。用 monkeypatch STATE_DIR 到一個乾淨的 tmp 目錄，
# 分別驗根目錄／Archive 底下要擋，帶日期子資料夾要放行。
STATE_ROOT = tempfile.mkdtemp(prefix='s2_rf_state_')
_orig_state_dir = bp.s2_state.STATE_DIR
bp.s2_state.STATE_DIR = STATE_ROOT

os.makedirs(os.path.join(STATE_ROOT, '20260909'), exist_ok=True)
os.makedirs(os.path.join(STATE_ROOT, 'Archive', '2026'), exist_ok=True)

# ⑪a 帶日期子資料夾（非 Archive）── 要放行，不是生產 state
p11a = write_json(os.path.join(STATE_ROOT, '20260909', 'ns_batch_0700.json'), [
    {'id': 'NS0001', 'raw_entry': '甲'},
])
out11a, code11a = run(Args(batch=p11a, from_key='raw_entry', to_key='entry'))
check('⑪a 日期子資料夾的工作 batch → 放行（exit 0）', code11a == 0, out11a[:200])
check('⑪a 有寫出改名後的檔案',
      os.path.exists(os.path.join(STATE_ROOT, '20260909', 'ns_batch_0700.renamed.json')))

# ⑪b 直接落在 STATE_DIR 根目錄 ── 要拒絕
p11b = write_json(os.path.join(STATE_ROOT, 'ns_batch_0700.json'), [
    {'id': 'NS0002', 'raw_entry': '乙'},
])
out11b, code11b = run(Args(batch=p11b, from_key='raw_entry', to_key='entry'))
check('⑪b STATE_DIR 根目錄直接落檔 → 拒絕（非 0 exit）', code11b != 0, code11b)
check('⑪b 沒有寫出任何檔案',
      not os.path.exists(os.path.join(STATE_ROOT, 'ns_batch_0700.renamed.json')))

# ⑪c Archive 封存底下 ── 要拒絕（含更深一層巢狀）
p11c = write_json(os.path.join(STATE_ROOT, 'Archive', '2026', 'ns_batch_0700.json'), [
    {'id': 'NS0003', 'raw_entry': '丙'},
])
out11c, code11c = run(Args(batch=p11c, from_key='raw_entry', to_key='entry'))
check('⑪c Archive 封存底下 → 拒絕（非 0 exit）', code11c != 0, code11c)
check('⑪c 沒有寫出任何檔案',
      not os.path.exists(os.path.join(STATE_ROOT, 'Archive', '2026', 'ns_batch_0700.renamed.json')))

# ⑪d --out 指到生產 state 檔名 → 一樣要拒絕（不能繞過輸入檔檢查、只查 --out）
p11d = write_json('out_target_1.json', [{'id': 'NS0004', 'raw_entry': '丁'}])
out11d_target = os.path.join(TMP, '0914-s2-state.json')
out11d, code11d = run(Args(batch=p11d, from_key='raw_entry', to_key='entry',
                            out=out11d_target))
check('⑪d --out 指到 {MMDD}-s2-state.json → 拒絕（非 0 exit）', code11d != 0, code11d)
check('⑪d 沒有寫出任何檔案', not os.path.exists(out11d_target))

bp.s2_state.STATE_DIR = _orig_state_dir
shutil.rmtree(STATE_ROOT, ignore_errors=True)

# ── ⑫ 真實路徑 dry-run（不 monkeypatch，用真正的 s2_state.STATE_DIR）────
# 驗證掃帶輪次資料夾（STATE_DIR\<YYYYMMDD>\...）底下真實存在的工作 batch
# 能被放行、且 --dry-run 真的不寫任何檔案。找不到真實檔案就跳過（環境依賴）。
_real_state_dir = _orig_state_dir
_real_candidates = []
try:
    for _d in sorted(os.listdir(_real_state_dir)):
        _dp = os.path.join(_real_state_dir, _d)
        if not (os.path.isdir(_dp) and _d[:1].isdigit() and _d.lower() != 'archive'):
            continue
        for _f in os.listdir(_dp):
            if _f.endswith('.json') and '_batch_' in _f:
                _real_candidates.append(os.path.join(_dp, _f))
except OSError:
    pass

if _real_candidates:
    _real_p = _real_candidates[0]
    _real_out = _real_p[:-5] + '.renamed.json'
    out12, code12 = run(Args(batch=_real_p, from_key='__不存在的鍵__', to_key='__也不存在__',
                              dry_run=True))
    # 來源鍵在真實檔案裡幾乎必然不存在（故意挑一個不存在的鍵名），
    # 所以預期是「來源鍵全缺」拒絕，但重點是**不管哪種結果都不寫檔**、
    # 且不能被誤判成生產 state（那會是完全不同的錯誤訊息、rc=2 且無關來源鍵）。
    check('⑫ 真實日期子資料夾路徑不被誤判成生產 state',
          '生產狀態檔' not in out12, out12[:300])
    check('⑫ dry-run 對真實路徑沒有寫出任何檔案', not os.path.exists(_real_out))
else:
    print('SKIP  ⑫ 真實路徑 dry-run：找不到 STATE_DIR 底下任何日期子資料夾的 '
          '_batch_ 工作檔，環境依賴、略過（不算失敗）')

# ── ⑬ 預設輸出檔已存在 → 拒絕；明確 --out 則照樣覆寫 ─────────────────────
p13 = write_json('exists_1.json', [{'id': 'RT0061', 'raw_entry': '甲'}])
default_out13 = os.path.join(TMP, 'exists_1.renamed.json')
with open(default_out13, 'w', encoding='utf-8') as f:
    f.write('{"pre-existing": true}')  # 湊巧已經有這個檔名的東西
out13, code13 = run(Args(batch=p13, from_key='raw_entry', to_key='entry'))
check('⑬a 預設輸出檔已存在 → 拒絕（非 0 exit）', code13 != 0, code13)
check('⑬a 既有檔案內容沒被動到',
      read_json(default_out13) == {'pre-existing': True})

# 明確帶 --out 指到同一個路徑 → 視為使用者主動選擇，照常覆寫
out13b, code13b = run(Args(batch=p13, from_key='raw_entry', to_key='entry',
                            out=default_out13))
check('⑬b 明確 --out 指到已存在的檔案 → 照常覆寫（exit 0）', code13b == 0, code13b)
check('⑬b 內容確實被改名後的結果覆寫',
      read_json(default_out13)[0].get('entry') == '甲')

# ── ⑭ 原子寫入：模擬寫檔中途失敗，輸出檔與暫存檔都不留殘骸 ────────────────
p14 = write_json('atomic_1.json', [{'id': 'RT0071', 'raw_entry': '甲'}])
out14_path = os.path.join(TMP, 'atomic_1.renamed.json')


def _boom(*a, **kw):
    raise RuntimeError('模擬寫檔中途失敗')


def run_expect_exception(args):
    """跟 `run()` 一樣包 stdout/stderr，但連一般例外（不只 SystemExit）都接住——
    ⑭ 故意讓 `json.dump` 中途炸掉，驗的是「例外會往外傳、不被吞掉」，
    用 `run()` 會讓這個例外直接砸穿測試腳本本身。"""
    out, err = io.StringIO(), io.StringIO()
    code = 1
    try:
        with redirect_stdout(out), redirect_stderr(err):
            bp.cmd_rename_field(args)
        code = 0
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (1 if e.code else 0)
    except Exception:
        code = 1
    return out.getvalue() + err.getvalue(), code


_orig_json_dump = bp.json.dump
bp.json.dump = _boom
try:
    out14, code14 = run_expect_exception(Args(batch=p14, from_key='raw_entry', to_key='entry'))
finally:
    bp.json.dump = _orig_json_dump

check('⑭a 模擬寫檔失敗 → 非 0 exit（例外沒被吞掉）', code14 != 0, code14)
check('⑭a 沒有留下半寫壞的輸出檔', not os.path.exists(out14_path))
_leftover_tmp = [f for f in os.listdir(TMP) if f.startswith('.s2rf_tmp_')]
check('⑭a 沒有留下暫存檔殘骸', not _leftover_tmp, _leftover_tmp)

# ── guard 驗證附帶檢查：呼叫 rename-field 這條指令本身要被 guard 放行 ────
# （R33 明文界線：這支工具不是繞 guard，是既有授權路徑的窄出口——guard 不必改）
sys.path.insert(0, HERE)
import s2_bash_guard as guard  # noqa: E402
_cmd = ('python E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py rename-field '
        'ns_batch_0700.json --from raw_entry --to entry --out out.json')
check('guard：呼叫 rename-field 的標準指令被放行（basename 命中 s2_ 白名單）',
      guard.decide('Bash', _cmd) is None)

shutil.rmtree(TMP, ignore_errors=True)
print(f'\nPASS={sum(results)} FAIL={len(results) - sum(results)}')
sys.exit(0 if all(results) else 1)
