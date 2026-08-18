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

# ── dedup-check（D9 第一步：0817-2200 那 5 次臨時 python 的替代品）──
DC = write_json('ns_full.json', [
    {'id': 'EN-32MO', 'desc': 'A 版描述', 'script': '同一段稿子逐字相同'},
    {'id': 'EN-31MO', 'desc': 'B 版描述', 'script': '同一段稿子逐字相同'},
    {'id': 'MI-15MO', 'desc': '相同描述', 'script': '這段稿子前半相同，後半不同了ABC'},
    {'id': 'MI-14MO', 'desc': '相同描述', 'script': '這段稿子前半相同，後半不同了XYZ'},
    {'id': 'WS-01MO', 'desc': 'x', 'script': '空白 不同' + chr(10) + '但內容相同'},
    {'id': 'WS-02MO', 'desc': 'x', 'script': '空白不同但內容相同'},
    {'id': 'MK-01MO', 'desc': 'x', 'script': '<p>同一段內容<b>加粗</b>而已</p>'},
    {'id': 'MK-02MO', 'desc': 'x', 'script': '<p>同一段內容加粗而已</p>'},
    {'id': 'MK-03MO', 'desc': 'x', 'script': '<p>同一段內容<b>加粗</b>而已但這裡多一句</p>'},
    {'id': 'EMP-01MO', 'desc': 'x', 'script': ''},
    {'id': 'EMP-02MO', 'desc': 'x', 'script': ''},
    {'id': 'NOF-01MO', 'dur_ms': 1000},
])


def dc(**kw):
    a = dict(raw=DC, site=None, fields=None)
    a.update(kw)
    return run(bp.cmd_dedup_check, Args(**a))


o, c = dc(ids='EN-32MO,EN-31MO')
check('dedup-check 逐字相同要判 same', c == 0 and '逐字相同' in o)
check('dedup-check 同時報出不同的欄位（desc）', '✗ EN-32MO vs EN-31MO' in o and 'desc' in o)
check('dedup-check 結論行分開列相同／不同欄位',
      'script 相同' in o.split('結論')[-1] and 'desc 不同' in o.split('結論')[-1])

o, c = dc(ids='MI-15MO,MI-14MO')
check('dedup-check 只有部分相同時 script 判 diff',
      c == 0 and '✗ MI-15MO vs MI-14MO' in o)
check('dedup-check 指出第一個差異位置', '字起不同' in o)
check('dedup-check 不同時印出兩邊差異附近文字', 'ABC' in o and 'XYZ' in o)

o, c = dc(ids='MK-01MO,MK-02MO', fields='script')
check('dedup-check 只差 HTML 標記要判「剝掉標記後相同」',
      c == 0 and '只差 HTML 標記' in o)
check('dedup-check 只差標記時不可謊稱逐字相同',
      '✓ MK-01MO vs MK-02MO：逐字相同' not in o)

o, c = dc(ids='MK-01MO,MK-03MO', fields='script')
check('dedup-check 內容真的不同時仍判 diff', c == 0 and '✗ MK-01MO vs MK-03MO' in o)
check('dedup-check 差異位置算在剝掉標記後、不指到 <b>',
      '剝掉標記後第 ' in o and '<b>' not in o.split('MK-01MO vs MK-03MO')[-1])

# 結論行是掃帶 agent 唯一會讀的一行，四種判定都要在那裡講清楚、不可印空白
o, c = dc(ids='MK-01MO,MK-02MO', fields='script')
concl = o.split('結論')[-1]
check('dedup-check 只差標記時結論行不可空白',
      'MK-01MO vs MK-02MO：' in concl
      and concl.split('MK-01MO vs MK-02MO：')[1].strip() != '')
check('dedup-check 結論行把「剝標記後相同」跟「逐字相同」分開講',
      '剝標記後相同' in concl and 'script 相同' not in concl)

o, c = dc(ids='WS-01MO,WS-02MO', fields='script')
check('dedup-check 結論行把「去空白後相同」單獨講',
      '去空白後相同' in o.split('結論')[-1])

o, c = dc(ids='EMP-01MO,EMP-02MO', fields='script')
check('dedup-check 兩邊皆空不可判成逐字相同',
      c == 0 and '兩邊這個欄位都是空的' in o and '✓ EMP-01MO vs EMP-02MO' not in o)
check('dedup-check 兩邊皆空在結論行也講明', '兩邊皆空' in o.split('結論')[-1])

o, c = dc(ids='WS-01MO,WS-02MO', fields='script')
check('dedup-check 只差空白要明確標示、不可當成完全相同',
      c == 0 and '只差空白' in o and '✓ WS-01MO vs WS-02MO：逐字相同' not in o)

# 三則以上要兩兩都比
o, c = dc(ids='EN-32MO,EN-31MO,MI-15MO', fields='script')
check('dedup-check 三則要兩兩比（3 組）',
      o.count('EN-32MO vs EN-31MO') and o.count('EN-32MO vs MI-15MO')
      and o.count('EN-31MO vs MI-15MO'))

# ── 以下每一項都必須「明確失敗」，不可靜默略過 ──
o, c = dc(ids='EN-32MO')
check('dedup-check 只給一個 id 要失敗', c == 1 and '至少要兩個' in o)

o, c = dc(ids='EN-32MO,EN-32MO')
check('dedup-check --ids 重複要失敗', c == 1 and '重複' in o)

o, c = dc(ids='EN-32MO,NOSUCH-99MO')
check('dedup-check id 不存在要失敗（不可只比得出來的那幾則）',
      c == 1 and 'NOSUCH-99MO' in o and '逐字相同' not in o)

o, c = dc(ids='EN-32MO,EN-31MO', fields='nosuchfield')
check('dedup-check 指定不存在的欄位要失敗', c == 1 and 'nosuchfield' in o)

o, c = dc(ids='NOF-01MO,EN-32MO')
check('dedup-check 一邊沒有該欄位時標無法比對、不判相同',
      '無法比對' in o or '無此欄位' in o)

o, c = run(bp.cmd_dedup_check,
           Args(raw=os.path.join(TMP, 'nope.json'), ids='A,B', site=None, fields=None))
check('dedup-check 讀不到檔要明確失敗', c == 1 and '逐字相同' not in o)

# RT 的 id 欄位是 code，per-site adapter 要生效
DC_RT = write_json('rt_dc.json', [
    {'code': 'RT1001', 'story': '同一則'},
    {'code': 'RT1002', 'story': '同一則'},
])
o, c = run(bp.cmd_dedup_check, Args(raw=DC_RT, ids='RT1001,RT1002', site='rt', fields=None))
check('dedup-check RT 走 code 當 id', c == 0 and '逐字相同' in o)

# ── inspect／search／snapshot 看穿 AP 的 ES `_source` 殼（D9 步驟②前置）──
# 0817-2200 實測：inspect 在 AP 清單檔上把 id 解成 `_id` 雜湊、--fields 回
# 「無此欄位」，agent 直接彈回 python -c——hook 指路的工具必須先能用。
AP_ES = write_json('ap_es.json', {
    'Items': [
        {'_id': 'dcf0346fabc', '_score': 1.0,
         '_source': {'editorialid': 5467681, 'headline': 'Quake rescue latest',
                     'script': 'Rescue teams continued digging on Monday.'}},
        {'_id': 'ee1122ffdd', '_score': 0.9,
         '_source': {'editorialid': 5467682, 'headline': 'Quake rescue vertical',
                     'script': 'Rescue teams continued digging on Monday.'}},
    ]})

o, c = run(bp.cmd_inspect, Args(raw=AP_ES, ids='AP5467681', fields='headline',
                                limit=None, index=None, site='ap', lengths=False))
check('inspect --ids 用 AP<editorialid> 找得到（不再是 _id 雜湊）',
      c == 0 and 'AP5467681' in o and '找不到' not in o)
check('inspect --fields 看穿 _source（headline 有值）',
      'Quake rescue latest' in o and '無此欄位' not in o)

o, c = run(bp.cmd_inspect, Args(raw=AP_ES, ids=None, fields=None,
                                limit=None, index=None, site=None, lengths=False))
check('inspect 摘要模式沒給 --site 也自動走 AP id（editorialid 自動判站）',
      c == 0 and 'AP5467681' in o and 'dcf0346f' not in o)

o, c = run(bp.cmd_inspect, Args(raw=AP_ES, ids='AP5467681', fields=None,
                                limit=None, index=None, site='ap', lengths=True))
check('inspect --lengths 印字數不印內容（字數檢查缺口）',
      c == 0 and 'len:' in o and 'Rescue teams' not in o)

o, c = run(bp.cmd_inspect, Args(raw=AP_ES, ids='AP5467681', fields='script',
                                limit=None, index=None, site='ap', lengths=True))
check('inspect --lengths 可指定欄位', c == 0 and 'script=len:41' in o)

o, c = run(bp.cmd_search, Args(raw=AP_ES, contains='digging', field='all',
                               limit=None, site='ap'))
check('search 看穿 _source（AP 清單檔不再永遠空手）',
      c == 0 and 'AP5467681' in o and 'AP5467682' in o)

snap_ap = os.path.join(TMP, 'snap_ap.txt')
o, c = run(bp.cmd_snapshot, Args(raw=AP_ES, site='ap', checkpoint='0818-1600', out=snap_ap))
body_ap = open(snap_ap, encoding='utf-8').read()
check('snapshot AP 清單檔印 AP<editorialid>＋標題（不是 _id 雜湊）',
      c == 0 and 'AP5467681' in body_ap and 'dcf0346f' not in body_ap)

o, c = run(bp.cmd_dedup_check, Args(raw=AP_ES, ids='AP5467681,AP5467682',
                                    site=None, fields='script'))
check('dedup-check 沒給 --site 也認得 AP id（editorialid 自動判站）',
      c == 0 and '逐字相同' in o)

# ── A13：AP 詳情 API 的 nitf 殼，三條查詢路徑都要看得穿（2026-08-18）────────
#
# 0818-2200 實錯：AP 詳情 API 回的 `script`／`caption` 是
# `{'words': N, 'nitf': '<p>SHOTLIST:</p>…'}` 一層 dict，不是字串。
# `inspect --lengths` 只挑 str 欄位 → 沒列出 script；`search --field script`
# 同樣只認 str → 0 命中。掃帶 agent 兩個訊號都看到「沒有」，判定「AP API 缺欄位」，
# 照 13c §1a 退 §1b 逐則開了 14 個詳情頁——資料其實一直都在（15/15 筆都有）。
# 這組測試把「工具答錯比沒工具更糟」釘住：**檔案裡有的東西，工具不准說沒有。**
AP_NITF = write_json('ap_nitf.json', [
    {'_id': 'aaa111', '_source': {
        'editorialid': 4679131,
        'caption': {'words': 8, 'nitf': '<p>RUSSIA: PUTIN MEETING +PLAYBACK+</p>'},
        'script': {'words': 89, 'nitf': '<p>SHOTLIST:</p><p>1. SOUNDBITE (English) Someone</p>'},
        'shots': [{'start': '00:00:00.000'}],          # 存在但既非 str 也非 nitf 殼
        'headline': 'Putin meeting playback',           # 一般字串欄位，行為不可變
    }},
])

o, c = run(bp.cmd_inspect, Args(raw=AP_NITF, ids=None, fields=None,
                                limit=None, index=None, site='ap', lengths=True))
check('A13 --lengths 自動列欄位時要含 nitf 殼（原本整個漏掉）',
      c == 0 and 'script.nitf=len:' in o and 'caption.nitf=len:' in o)
check('A13 --lengths 仍照列一般字串欄位（沒有回歸）', 'headline=len:' in o)

o, c = run(bp.cmd_inspect, Args(raw=AP_NITF, ids=None, fields='script,caption',
                                limit=None, index=None, site='ap', lengths=True))
check('A13 --lengths 指名 nitf 欄位不再回「無此欄位」',
      c == 0 and 'script.nitf=len:' in o and '無此欄位' not in o)

o, c = run(bp.cmd_inspect, Args(raw=AP_NITF, ids=None, fields='shots,nosuchfield',
                                limit=None, index=None, site='ap', lengths=True))
check('A13 「欄位存在但非文字」與「真的沒這欄位」要講不同的話',
      c == 0 and 'shots=<欄位存在但非文字>' in o and 'nosuchfield=<無此欄位>' in o)

o, c = run(bp.cmd_search, Args(raw=AP_NITF, contains='SOUNDBITE', field='script',
                               limit=None, site='ap'))
check('A13 search --field script 在 nitf 殼上要命中（原本 0 命中）',
      c == 0 and 'script.nitf' in o and 'AP4679131' in o)

o, c = run(bp.cmd_search, Args(raw=AP_NITF, contains='SOUNDBITE', field='all',
                               limit=None, site='ap'))
check('A13 --field all 與 --field script 結論一致（同檔不同參數不可相反）',
      c == 0 and 'script.nitf' in o)

# 純字串站別（NS／RT）不可因為這次改動而改變行為
o, c = run(bp.cmd_search, Args(raw=AP_ES, contains='digging', field='script',
                               limit=None, site='ap'))
check('A13 一般 str 欄位的 --field 查詢照舊命中（NS/RT 形狀無回歸）',
      c == 0 and 'AP5467681' in o)

shutil.rmtree(TMP, ignore_errors=True)
print(f'\nPASS={sum(results)} FAIL={len(results) - sum(results)}')
sys.exit(0 if all(results) else 1)
