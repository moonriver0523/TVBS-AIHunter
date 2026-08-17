#!/usr/bin/env python3
"""s2_batch_prep.py 的 snapshot／compare 測試（MASTER A2）。

護欄（A2 子項明列）：
  - per-site adapter：RT 的 id 是 `code` 不是 `id`
  - 冪等、**不覆寫舊 snapshot**（覆寫＝靜默銷毀稽核依據）
  - compare 乾淨就一行，有差才列——不印整批

用法：python test_s2_batch_prep.py
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

TMP = tempfile.mkdtemp(prefix='s2_a2_test_')
results = []


def check(name, cond, extra=''):
    results.append(bool(cond))
    print(f'{"PASS" if cond else "FAIL"}  {name}{(" → " + extra) if extra else ""}')


def write_json(name, obj):
    p = os.path.join(TMP, name)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
    return p


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def run(fn, args):
    """跑子指令，回傳 (stdout, exit_code)。sys.exit 不讓它中斷測試。"""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with redirect_stdout(out), redirect_stderr(err):
            fn(args)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    return out.getvalue() + err.getvalue(), code


# RT 殼：陣列在 items 底下，id 欄位叫 code
RAW = write_json('rt_raw.json', {
    'boxFound': True, 'count': 3,
    'items': [
        {'code': 'RT1001', 'head': 'Story one', 'story': 'text one', 'sb_count': 2},
        {'code': 'RT1002', 'head': 'Story two', 'story': 'text two', 'sb_count': 0},
        {'code': 'RT1003', 'head': 'Story three', 'story': 'text three', 'sb_count': 1},
    ]})

FULL = {'source': 'RT', 'checkpoint': '0817-1600', 'status': 'has_script',
        'entry': '◆ …', 'src_text': 'HEAD: x'}
BATCH_OK = write_json('batch_ok.json', [dict(id=i, **FULL)
                                        for i in ('RT1001', 'RT1002', 'RT1003')])
BATCH_BAD = write_json('batch_bad.json', [
    dict(id='RT1001', **FULL),
    {k: v for k, v in dict(id='RT1002', **FULL).items() if k != 'src_text'},
    dict(id='RT9999', **FULL),          # raw 沒有
    dict(id='RT1001', **FULL),          # 重複
])

# ── snapshot ────────────────────────────────────────────────
snap = os.path.join(TMP, 'snap.txt')
out, code = run(bp.cmd_snapshot, Args(raw=RAW, site='rt', checkpoint='0817-1600', out=snap))
check('snapshot 寫得出檔', code == 0 and os.path.exists(snap), out.strip()[:80])

body = open(snap, encoding='utf-8').read()
check('snapshot 用 RT 的 code 當 id（per-site adapter）',
      'RT1001\tStory one' in body and 'RT1003' in body)
check('snapshot 標頭記殼型與筆數', '筆數：3' in body and 'items' in body)

out2, code2 = run(bp.cmd_snapshot, Args(raw=RAW, site='rt', checkpoint='0817-1600', out=snap))
check('snapshot 拒絕覆寫舊檔（冪等護欄）', code2 == 1 and '不覆寫舊檔' in out2)
check('snapshot 拒絕覆寫後內容沒被動過',
      open(snap, encoding='utf-8').read() == body)

out3, code3 = run(bp.cmd_snapshot, Args(raw=RAW, site='rt', checkpoint=None, out=None))
check('snapshot 沒 --out 也沒 --checkpoint 要明確失敗', code3 == 1, out3.strip()[:60])

# 預設檔名 _audit_{site}_{HHMM}.txt
out4, code4 = run(bp.cmd_snapshot, Args(raw=RAW, site='rt', checkpoint='0817-1600', out=None))
auto = os.path.join(TMP, '_audit_rt_1600.txt')
check('snapshot 預設檔名 _audit_{site}_{HHMM}.txt', code4 == 0 and os.path.exists(auto),
      os.path.basename(auto))

# ── compare ─────────────────────────────────────────────────
out5, code5 = run(bp.cmd_compare, Args(raw=RAW, batch=BATCH_OK, site='rt', require=None))
check('compare 乾淨時只印一行「無差異」', '無差異' in out5, out5.strip().splitlines()[-1][:70])
check('compare 乾淨時不印整批',
      'RT1001' not in out5.split('無差異')[0].replace('rt_raw.json', ''))

out6, _ = run(bp.cmd_compare, Args(raw=RAW, batch=BATCH_BAD, site='rt', require=None))
check('compare 抓到 raw 有 batch 沒有（RT1003）', 'RT1003' in out6)
check('compare 抓到 batch 有 raw 沒有（RT9999）', 'RT9999' in out6)
check('compare 抓到缺 src_text（RT1002）', 'RT1002：缺 src_text' in out6)
check('compare 抓到 batch 內重複 id', '重複 id' in out6 and 'RT1001' in out6)

out7, _ = run(bp.cmd_compare, Args(raw=RAW, batch=BATCH_OK, site='rt', require='sb_count'))
check('compare --require 可自訂欄位', 'sb_count' in out7 and '缺欄位' in out7)

# ── 讀不到要明確失敗，不可當成「無差異」 ──
out8, code8 = run(bp.cmd_compare,
                  Args(raw=os.path.join(TMP, 'nope.json'), batch=BATCH_OK,
                       site='rt', require=None))
check('compare raw 讀不到要明確失敗', code8 == 1 and '無差異' not in out8)

shutil.rmtree(TMP, ignore_errors=True)
print(f'\nPASS={sum(results)} FAIL={len(results) - sum(results)}')
sys.exit(0 if all(results) else 1)
