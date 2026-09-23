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

# ID 清單數量門檻：10 則以下維持舊的逐筆輸出；11 則起改為摘要＋旁檔。
SMALL_RAW = write_json('small_ids_raw.json', {
    'items': [{'code': f'RTS{i:02d}', 'head': 'h', 'story': 's'} for i in range(10)]})
SMALL_BATCH = write_json('small_ids_batch.json', [])
out_small_ids, _ = run(bp.cmd_compare, Args(
    raw=SMALL_RAW, batch=SMALL_BATCH, site='rt', require=None, json_result=None))
check('ID 清單量小（=10）維持逐筆印出',
      '  - RTS00' in out_small_ids and '  - RTS09' in out_small_ids
      and '清單已寫入' not in out_small_ids)

LARGE_RAW = write_json('large_ids_raw.json', {
    'items': [{'code': f'RTM{i:02d}', 'head': 'h', 'story': 's'} for i in range(11)]})
_large_batch_rows = []
for _i in range(11):
    _large_batch_rows.extend([
        dict(id=f'RTE{_i:02d}', **FULL),
        dict(id=f'RTE{_i:02d}', **FULL),
    ])
LARGE_BATCH = write_json('large_ids_batch.json', _large_batch_rows)
out_large_ids, _ = run(bp.cmd_compare, Args(
    raw=LARGE_RAW, batch=LARGE_BATCH, site='rt', require=None, json_result=None))
_missing_list = os.path.join(TMP, 'large_ids_raw_missing_ids.txt')
_extra_list = os.path.join(TMP, 'large_ids_raw_extra_ids.txt')
_dup_list = os.path.join(TMP, 'large_ids_raw_duplicate_ids.txt')
check('compare 大量 missing/extra/dup 只印數量摘要',
      '清單已寫入' in out_large_ids
      and '  - RTM00' not in out_large_ids and '  - RTE00' not in out_large_ids,
      out_large_ids[:500])
check('compare 大量 missing/extra/dup 各寫一份完整清單',
      all(os.path.exists(p) for p in (_missing_list, _extra_list, _dup_list)))
check('compare 大量清單保留原理由文字與全部 ID',
      '可能是刻意排除' in open(_missing_list, encoding='utf-8').read()
      and 'RTM00' in open(_missing_list, encoding='utf-8').read()
      and 'RTM10' in open(_missing_list, encoding='utf-8').read()
      and 'RTE10' in open(_extra_list, encoding='utf-8').read())

# cmd_build 同樣覆蓋大量 missing 的摘要＋旁檔路徑。
BUILD_LARGE_ENTRIES = write_json('build_large_entries.json', {})
BUILD_LARGE_RAW = write_json(
    'build_large_raw.json',
    [{'code': f'RTM{i:02d}', 'head': 'h', 'story': 's'} for i in range(11)])
BUILD_LARGE_OUT = os.path.join(TMP, 'build_large_batch.json')
out_build_large, code_build_large = run(bp.cmd_build, Args(
    site='rt', raw=BUILD_LARGE_RAW, entries=BUILD_LARGE_ENTRIES,
    checkpoint='0923-2200', out=BUILD_LARGE_OUT, skeleton=None,
    dry_run=False))
_build_missing_list = os.path.join(TMP, 'build_large_entries_missing_ids.txt')
check('build 大量 missing 改印數量摘要、不印全清單',
      code_build_large == 0 and '11 則，清單已寫入' in out_build_large
      and 'RTM00, RTM01' not in out_build_large, out_build_large[:500])
check('build 大量 missing 旁檔寫在 entries 同目錄且內容完整',
      os.path.exists(_build_missing_list)
      and 'RTM00' in open(_build_missing_list, encoding='utf-8').read()
      and 'RTM10' in open(_build_missing_list, encoding='utf-8').read())

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

# ── inspect --site 補 enex/abc 選項（2026-09-19，D9 步驟②同源缺口：
# argparse choices 漏了這兩個，即使 PLATFORM_ID_OF 早就支援，CLI 直接
# invalid choice 擋掉，agent 只能猜著換掉 --site 硬試）──
ABC_RAW = write_json('abc_raw.json', [
    {'News Story': '643399600', 'Headline': 'oil prices'},
])
ENEX_RAW = write_json('enex_raw.json', [
    {'id': '931565', 'title': 'wildfire update'},
])
o, c = run(bp.cmd_inspect, Args(raw=ABC_RAW, ids='ABC643399600', fields=None,
                                limit=None, index=None, site='abc', lengths=False))
check('inspect --site abc 用 PLATFORM_ID_OF 找得到（不再 invalid choice）',
      c == 0 and 'ABC643399600' in o and '找不到' not in o)
o, c = run(bp.cmd_inspect, Args(raw=ENEX_RAW, ids='ENEX931565', fields=None,
                                limit=None, index=None, site='enex', lengths=False))
check('inspect --site enex 用 PLATFORM_ID_OF 找得到',
      c == 0 and 'ENEX931565' in o and '找不到' not in o)

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

# ── T9（2026-08-25）：inspect 全文改由字元預算決定，不再由筆數決定 ──────
# 舊判準是 `len(indexed) <= 3` 才印全文，於是「要看完整 script」＝「一次只能查
# 3 筆」，0825-0100 實測 56 次 inspect 裡 31 次是一次只看一則。
_S = 'x' * 5000
BUDGET_OK = write_json('budget_ok.json', [
    {'id': f'N{i}', 'script': _S} for i in range(5)])          # 25,000 < 28,000
BUDGET_OVER = write_json('budget_over.json', [
    {'id': f'N{i}', 'script': _S} for i in range(8)])          # 40,000 > 28,000
BUDGET_HUGE = write_json('budget_huge.json', [
    {'id': 'N0', 'script': 'y' * 40000}])                      # 單則就爆預算

o, c = run(bp.cmd_inspect, Args(raw=BUDGET_OK, ids=None, fields='script',
                                limit=None, index=None, site=None, lengths=False))
check('T9 5 筆共 25,000 字元吃得下預算 → 整批全文（舊制只有 ≤3 筆才全文）',
      c == 0 and '...[略]' not in o)

o, c = run(bp.cmd_inspect, Args(raw=BUDGET_OVER, ids=None, fields='script',
                                limit=None, index=None, site=None, lengths=False))
check('T9 8 筆共 40,000 字元超預算 → 退回預覽', c == 0 and '...[略]' in o)
check('T9 超預算要**明講**，不是靜默截斷', '超過 28,000 字元預算' in o)
check('T9 超預算要附可直接貼的分批指令', '--ids N0,N1,N2,N3,N4' in o)

o, c = run(bp.cmd_inspect, Args(raw=BUDGET_HUGE, ids=None, fields='script',
                                limit=None, index=None, site=None, lengths=False))
# ⛔ 這裡掉到 200 字元預覽會是功能退步：舊制單則查是印全文的。
check('T9 單則自己爆預算 → 截到預算為止（不是掉回 200 字元）',
      c == 0 and o.count('y') > 20000)
check('T9 單則爆預算也要明講截在哪', '自己就超過' in o)

o, c = run(bp.cmd_inspect, Args(raw=BUDGET_OK, ids='N1', fields='script',
                                limit=None, index=None, site=None, lengths=False))
check('T9 一次只查一則 → 印批次引導（比照 A10 v2「要有觸發點」）',
      c == 0 and '同檔還有 4 筆' in o)

o, c = run(bp.cmd_inspect, Args(raw=BUDGET_OK, ids='N1,N2', fields='script',
                                limit=None, index=None, site=None, lengths=False))
check('T9 已經批次了就不要再囉嗦引導', c == 0 and '同檔還有' not in o)

# RT detail 的素材編號在 `edit`（清單檔才是 `code`），原本掉到 `#index`，
# `--ids` 對 RT detail 形同不存在——那 15 次 `--index N` 的根因。
RT_DETAIL = write_json('rt_detail.json', [
    {'edit': 'RT7542', 'head': 'Sheinbaum presser', 'story': 'short'},
    {'edit': 'RT7500', 'head': 'Amatrice quake', 'story': 'short'}])
o, c = run(bp.cmd_inspect, Args(raw=RT_DETAIL, ids=None, fields=None,
                                limit=None, index=None, site='rt', lengths=False))
check('T9 RT detail 認得 edit 當 id（不再是 #0／#1，--ids 才可用）',
      c == 0 and 'RT7542' in o and '#0' not in o)

# ── T9 二輪（對抗性審查發現）：`edit` 上游有退化值，撞名的 id 比沒有 id 更糟 ──
# 實測 20260824 六份 rt_detail 有五份含裸前綴 'RT'，1800 那份 39 筆裡就有 19 筆。
RT_DIRTY = write_json('rt_dirty.json', [
    {'edit': 'RT', 'head': 'A', 'story': _S},
    {'edit': 'RT', 'head': 'B', 'story': _S},
    {'edit': 'RT7440', 'head': 'C', 'story': _S},
    {'edit': 'RT', 'head': 'D', 'story': _S},
    {'edit': 'RT7415', 'head': 'E', 'story': _S},
    {'edit': 'RT7427', 'head': 'F', 'story': _S},
])
o, c = run(bp.cmd_inspect, Args(raw=RT_DIRTY, ids=None, fields=None,
                                limit=None, index=None, site='rt', lengths=False))
check('T9-2 edit 的裸前綴退化值不當 id（撞名會讓 --ids 撈到一整群）',
      c == 0 and o.count('\tA') and '#0\t' in o and '#1\t' in o and 'RT7440' in o)

o, c = run(bp.cmd_dedup_check, Args(raw=RT_DIRTY, ids='RT,RT7440', site='rt', fields=None))
check('T9-2 dedup-check 對退化值要 fail-loud（不可靜默拿第一個比）',
      c != 0 and 'RT' in o)

# 分批建議必須 round-trip：貼回去要剛好撈到承諾的筆數，否則會再度爆預算、
# 印出同一條壞建議 → 不收斂，agent 照做只是白燒呼叫。
o, c = run(bp.cmd_inspect, Args(raw=RT_DIRTY, ids=None, fields='story',
                                limit=None, index=None, site='rt', lengths=False))
sug = [l for l in o.splitlines() if '--ids' in l]
check('T9-2 撞名檔仍給得出建議（退化值已退回 #N，#N 也可貼回）', len(sug) == 1)
if sug:
    _ids = sug[0].split('--ids ')[-1].strip()
    o2, c2 = run(bp.cmd_inspect, Args(raw=RT_DIRTY, ids=_ids, fields='story',
                                      limit=None, index=None, site='rt', lengths=False))
    check('T9-2 建議指令 round-trip：貼回去筆數相符且不再爆預算',
          c2 == 0 and f'本次顯示 {len(_ids.split(","))} 筆' in o2 and '超過' not in o2)

o, c = run(bp.cmd_inspect, Args(raw=RT_DIRTY, ids='#0,#1', fields='head',
                                limit=None, index=None, site='rt', lengths=False))
check('T9-2 `--ids #N` 序號定址受理（工具自己印的 #N 要貼得回去）',
      c == 0 and '本次顯示 2 筆' in o and '找不到' not in o)

# 預算量的是序列化後的長度：raw len 加總不含 JSON escape，NS 型內容實測膨脹 4.9%，
# 近飽和時足以把「宣告整批全文」的輸出推破 Bash 的 30k 靜默截斷線。
ESCAPE_HEAVY = write_json('escape_heavy.json', [
    {'id': f'E{i}', 'script': ('line\n"quoted"\t' * 250)} for i in range(9)])
o, c = run(bp.cmd_inspect, Args(raw=ESCAPE_HEAVY, ids=None, fields='script',
                                limit=None, index=None, site=None, lengths=False))
check('T9-2 escape 膨脹要計入預算（宣告全文就不能破 30k）',
      c == 0 and (len(o) <= 30000 or '超過' in o))

# dict 欄位（AP nitf 殼）原本被算成 0 → 宣告「整批全文」卻整包 dumps。
NITF = write_json('nitf.json', [
    {'id': f'P{i}', 'script': {'words': 500, 'nitf': 'z' * 3000}} for i in range(15)])
o, c = run(bp.cmd_inspect, Args(raw=NITF, ids=None, fields='script',
                                limit=None, index=None, site=None, lengths=False))
check('T9-2 dict 欄位也要計入預算（原本算 0，會靜默爆 30k）',
      c == 0 and (len(o) <= 30000 or '超過' in o))

# ── timeline（2026-08-30 補：0730 輪 `_mk_audit_snapshots.py`／`_mk_ns_snapshot.py`
#    這種自算時區的臨時腳本的替代品）────────────────────────────
TL_NS = write_json('tl_ns.json', [
    {'id': 'IN-01SU', 'created': '2026-08-30T14:05:37.905000Z'},
    {'id': 'IN-02SU', 'created': '2026-08-30T13:10:00.000000Z'},
])
o, c = run(bp.cmd_timeline, Args(raw=TL_NS, site='ns', out=None))
check('timeline NS：created 是 ISO 帶微秒 UTC，要 +8h 轉台北',
      c == 0 and '08/30/2026 22:05' in o and '08/30/2026 21:10' in o)
check('timeline 依時間排序（早的在前）',
      o.index('IN-02SU') < o.index('IN-01SU'))

TL_AP = write_json('tl_ap.json', [
    {'id': 'AP4681284', 'ts': '2026-08-30T14:20:00Z'},
    {'id': 'AP4681283', 'ts': '2026-08-30T13:00:00Z'},
])
o, c = run(bp.cmd_timeline, Args(raw=TL_AP, site='ap', out=None))
check('timeline AP：ts 是 ISO 秒 UTC，要 +8h 轉台北',
      c == 0 and '08/30/2026 22:20' in o and '08/30/2026 21:00' in o)

# 2026-09-19 二次訂正：拉了 2026-08-11～09-18 全部歷史 rt_list_*.json（近 40
# 輪）逐輪核對，RT `at` 從有記錄以來從未是 UTC——0831 那次訂正本身才是錯的
# （單輪證據、19 分鐘落差就判定吻合，不夠紮實）。改回免轉，並斷言不再 +8h。
TL_RT = write_json('tl_rt.json', [
    {'code': 'RT8928', 'at': '08/30/2026 21:50'},
    {'code': 'RT8927', 'at': ''},
])
o, c = run(bp.cmd_timeline, Args(raw=TL_RT, site='rt', out=None))
check('timeline RT：at 已經是台北當地時間，不轉（2026-09-19 二次訂正，見 TIMELINE_SPEC 註解）',
      c == 0 and '08/30/2026 21:50' in o and '05:50' not in o)
check('timeline 缺時間的筆數印警告到 stderr，不吞不猜',
      'RT8927' in o and '解不出時間' in o)

# cmd_timeline 自我檢查：換算後最大值離現在太遠就示警（RT 那次錯了 20 天沒人
# 發現，就是因為沒有這道警告）——用 NS（有 utc 轉換）的舊日期 fixture 觸發。
o, c = run(bp.cmd_timeline, Args(raw=TL_NS, site='ns', out=None))
check('timeline 換算後時間離現在太遠會示警（TIMELINE_SANITY_HOURS）',
      c == 0 and ('可能猜錯' in o or '偏' in o))

tl_out = os.path.join(TMP, 'tl_ns_out.txt')
o, c = run(bp.cmd_timeline, Args(raw=TL_NS, site='ns', out=tl_out))
check('timeline --out 落檔且內容跟 stdout 一致',
      c == 0 and os.path.exists(tl_out)
      and open(tl_out, encoding='utf-8').read().strip().splitlines()
          == [ln for ln in o.strip().splitlines() if '|' in ln])

# ── fill-src-text（2026-08-31 補：0818/0820/0825/0828/0829 反覆出現的
#    `_merge_src_*.py`／`_fix_src_*.py` 替代品）───────────────────
FS_RAW = write_json('fs_raw.json', [
    {'id': 'AP4681284', 'head': 'Headline one', 'script': 'Full body one.'},
    {'id': 'AP4681283', 'head': 'Headline two', 'script': ''},
])
FS_BATCH = write_json('fs_batch.json', [
    {'id': 'AP4681284', 'src_text': ''},
    {'id': 'AP4681283', 'src_text': ''},
    {'id': 'AP9999999', 'src_text': 'already have text'},
])
o, c = run(bp.cmd_fill_src_text, Args(batch=FS_BATCH, raw=FS_RAW, site='ap',
                                       fields=None, out=None))
check('fill-src-text 只填空的 src_text，不覆寫已有內容',
      c == 0 and 'already have text' == json.load(open(FS_BATCH, encoding='utf-8'))[2]['src_text'])
check('fill-src-text 依欄位優先序（head 有內容就併，script 空也照樣併非空欄位）',
      'Headline one' in json.load(open(FS_BATCH, encoding='utf-8'))[0]['src_text']
      and 'Full body one.' in json.load(open(FS_BATCH, encoding='utf-8'))[0]['src_text'])
check('fill-src-text 回報填入筆數', c == 0 and '填入 2 則' in o)

FS_BATCH2 = write_json('fs_batch2.json', [{'id': 'AP_NOT_IN_RAW', 'src_text': ''}])
o, c = run(bp.cmd_fill_src_text, Args(batch=FS_BATCH2, raw=FS_RAW, site='ap',
                                       fields=None, out=None))
check('fill-src-text raw 裡找不到的 id → 印警告不吞、不當錯誤中止',
      c == 0 and 'AP_NOT_IN_RAW' in o and '找不到' in o)

# ── collate-category（2026-08-31 補：0810/0827-1000 的 `run_setcat_1000.py`／
#    `_tmp_ns_cat.py` 替代品）──────────────────────────────────
CAT1 = write_json('cat1.json', [
    {'id': 'AP1', 'category': {'大分類': '政治', '中主題': '選舉'}},
    {'id': 'AP2', 'category': {'大分類': '社會', '中主題': '案件', '小分題': '審判'}},
    {'id': 'AP3'},
])
o, c = run(bp.cmd_collate_category, Args(batches=[CAT1]))
check('collate-category 組出 set-category --pairs 吃得下的字串',
      c == 0 and 'AP1=政治/選舉' in o and 'AP2=社會/案件/審判' in o)
check('collate-category 缺 category 的則不進 pairs、印警告',
      'AP3' not in o.split('\n')[0] and 'AP3' in o)

CAT2 = write_json('cat2.json', [
    {'id': 'RT1', 'category': {'大分類': '國際', '中主題': '烏俄'}},
])
o, c = run(bp.cmd_collate_category, Args(batches=[CAT1, CAT2]))
check('collate-category 可一次收多個 batch.json（三站各一個的場景）',
      c == 0 and 'AP1=政治/選舉' in o and 'RT1=國際/烏俄' in o)

# ── concat（2026-08-31 補：23 個命中／約 9-10 個不同日期反覆出現的
#    `a=json.load(...); b=json.load(...); json.dump(a+b,...)` 替代品）───
CC_A = write_json('cc_a.json', [{'id': 'AP1'}, {'id': 'AP2'}])
CC_B = write_json('cc_b.json', [{'id': 'AP3'}, {'id': 'AP2'}])

o, c = run(bp.cmd_concat, Args(files=[CC_A, CC_B], site=None, out=None))
check('concat 不給 --site 就純合併、不去重（4 筆全留）',
      c == 0 and o.count('"id"') == 4)

o, c = run(bp.cmd_concat, Args(files=[CC_A, CC_B], site='ap', out=None))
check('concat 給 --site 才去重，保留第一次出現的 AP2', c == 0 and '共 3 筆' in o)
check('concat 去重丟掉的重複 id 有警告，不是靜默', 'AP2' in o and '丟掉' in o)

CC_OUT = os.path.join(TMP, 'cc_out.json')
o, c = run(bp.cmd_concat, Args(files=[CC_A, CC_B], site=None, out=CC_OUT))
check('concat --out 落檔且是合法 json 陣列',
      c == 0 and os.path.exists(CC_OUT)
      and len(json.load(open(CC_OUT, encoding='utf-8'))) == 4)

CC_RT = write_json('cc_rt.json', [{'code': 'RT1'}, {'code': 'RT2'}])
CC_RT2 = write_json('cc_rt2.json', [{'code': 'RT2'}, {'code': 'RT3'}])
o, c = run(bp.cmd_concat, Args(files=[CC_RT, CC_RT2], site='rt', out=None))
check('concat 對 RT 用 code 當 id 去重（per-site adapter 沒漏接）',
      c == 0 and '共 3 筆' in o and 'RT2' in o)

# ── 2026-09-05（0905-0430 實錯）：concat --site 要認得 abc／enex ─────────
check('concat --site abc 用 News Story 當 id',
      bp._site_id_of('abc', {'News Story': '090426151'}, 0) == 'ABC090426151')
check('concat --site enex 帶不帶前綴都正規化成同一個 id',
      bp._site_id_of('enex', {'id': 'ENEX929681'}, 0)
      == bp._site_id_of('enex', {'id': '929681'}, 0) == 'ENEX929681')
check('concat --site abc 缺欄位時退回通用猜測，不炸',
      bp._site_id_of('abc', {'Slug': 'x'}, 7) is not None)
check('abc／enex 沒混進 SITE_SPEC（dump／build 仍只認三站）',
      set(bp.SITE_SPEC) == {'ns', 'ap', 'rt'})

# ── build：entries.json 值為物件時 category／tc 原樣帶進 batch row（T12，2026-09-07）
# 🔴 cmd_build 讀 raw 用 load_json()（純陣列），不是 cmd_snapshot／cmd_compare
#    那套會自動卸殼的 _load_raw_any——不能沿用上面包了 items 殼的 RAW。
BUILD_RAW = write_json('build_raw.json', [
    {'code': 'RT1001', 'head': 'Story one', 'story': 'text one', 'sb_count': 2},
    {'code': 'RT1002', 'head': 'Story two', 'story': 'text two', 'sb_count': 0},
])
BUILD_ENTRIES = write_json('build_entries.json', {
    'RT1001': {'entry': '◆ 摘要一', 'category': '社會/測試案', 'tc': '社會/美國'},
    'RT1002': '◆ 摘要二（純字串 entries，沒有 category／tc 可帶）',
})
BUILD_OUT = os.path.join(TMP, 'build_batch.json')
outB, codeB = run(bp.cmd_build, Args(site='rt', raw=BUILD_RAW, entries=BUILD_ENTRIES,
                                     checkpoint='0817-1600', out=BUILD_OUT))
check('build 執行成功', codeB == 0, outB.strip()[:80])
# P1b-2 硬上線（2026-09-08）：build 一律出 {"entries":[…],"new_topics":{…}} 外殼
_bo = json.load(open(BUILD_OUT, encoding='utf-8'))
check('build 一律出新格式外殼（三站純陣列已被 add-batch 拒收）',
      isinstance(_bo, dict) and isinstance(_bo.get('entries'), list)
      and isinstance(_bo.get('new_topics'), dict), str(type(_bo)))
rowsB = {r['id']: r for r in _bo['entries']}
check('build：entries 為物件時 category 原樣帶進 row',
      rowsB.get('RT1001', {}).get('category') == '社會/測試案', str(rowsB.get('RT1001')))
check('build：entries 為物件時 tc 原樣帶進 row',
      rowsB.get('RT1001', {}).get('tc') == '社會/美國', str(rowsB.get('RT1001')))
check('build：純字串 entries 不含 category 鍵（舊格式不變）',
      'category' not in rowsB.get('RT1002', {}), str(rowsB.get('RT1002')))
check('build：純字串 entries 不含 tc 鍵（舊格式不變）',
      'tc' not in rowsB.get('RT1002', {}), str(rowsB.get('RT1002')))

# ── §四（R31/T12）：build 出口共用 fmt_issues／pretag.lint，只警告不擋 ──────
# 壞 entry：標了 (BITE) 但沒有 ▎BITE： 段（跟 add-batch 那條既有告警同一套判準）。
LINT_RAW = write_json('lint_raw.json', [
    {'code': 'RT2001', 'head': 'bad one', 'story': 'story bad', 'sb_count': 1},
    {'code': 'RT2002', 'head': 'clean one', 'story': 'story clean', 'sb_count': 0},
])
LINT_ENTRIES = write_json('lint_entries.json', {
    'RT2001': 'RT2001 (測試 標題) (BITE) 這裡沒有BITE段落純摘要。',
    'RT2002': 'RT2002 (測試 標題) ▎測試摘要。▎畫面：資料畫面。無BITE。',
})
LINT_OUT = os.path.join(TMP, 'lint_batch.json')
outL, codeL = run(bp.cmd_build, Args(site='rt', raw=LINT_RAW, entries=LINT_ENTRIES,
                                     checkpoint='0914-1200', out=LINT_OUT))
check('build＋lint：壞 entry 仍 exit 0（只警告不擋）', codeL == 0, codeL)
check('build＋lint：壞 entry 的 ID 出現在警告裡', 'RT2001:' in outL, outL[-600:])
check('build＋lint：乾淨 entry（RT2002）沒有被列進警告', 'RT2002:' not in outL, outL[-600:])
_lo = json.load(open(LINT_OUT, encoding='utf-8'))
_lo_rows = {r['id']: r for r in _lo['entries']}
check('build＋lint：輸出檔內容不受警告影響（entry 原文照舊、沒被改寫）',
      _lo_rows['RT2001']['entry'] == 'RT2001 (測試 標題) (BITE) 這裡沒有BITE段落純摘要。'
      and _lo_rows['RT2002']['entry'] == 'RT2002 (測試 標題) ▎測試摘要。▎畫面：資料畫面。無BITE。')

# 預檢沿用 build 的 lint，但不得印／寫正式 batch 輸出。
LINT_DRY_OUT = os.path.join(TMP, 'lint_dry_run_batch.json')
outLD, codeLD = run(bp.cmd_build, Args(site='rt', raw=LINT_RAW, entries=LINT_ENTRIES,
                                       checkpoint='0914-1200', out=LINT_DRY_OUT,
                                       dry_run=True))
check('build --dry-run：壞 entry 仍印出警告',
      codeLD == 0 and 'RT2001:' in outLD and '--dry-run' in outLD, outLD[-600:])
check('build --dry-run：不寫 batch 輸出檔', not os.path.exists(LINT_DRY_OUT), LINT_DRY_OUT)

# 同一站同一原因達門檻才給整批重寫提示，少量不過度提示。
out_summary, _ = run(lambda pair: bp._print_build_lint_warnings(*pair),
                      (['RT300%d: 第一備註寫了 BITE' % i for i in range(5)], 'rt'))
out_small_summary, _ = run(lambda pair: bp._print_build_lint_warnings(*pair),
                           (['RT300%d: 第一備註寫了 BITE' % i for i in range(4)], 'rt'))
check('lint 匯總提示：同類問題達 5 則時出現',
      '整批重寫 RT entries.json' in out_summary and '不要逐筆 Edit' in out_summary,
      out_summary)
check('lint 匯總提示：少於 5 則時不出現', '整批重寫' not in out_small_summary,
      out_small_summary)

# --skeleton 分支同樣要跑同一套 lint（A24 骨架路徑，共用 _lint_row）
LINT_SKEL = write_json('lint_skeleton.json', [
    {'id': 'RT2001', 'source': 'RT', 'checkpoint': '0914-1200', 'status': 'has_script',
     'src_text': 'x', 'sb_count': 1, 'entry': '', 'category': '', 'tc': ''},
    {'id': 'RT2002', 'source': 'RT', 'checkpoint': '0914-1200', 'status': 'has_script',
     'src_text': 'x', 'sb_count': 0, 'entry': '', 'category': '', 'tc': ''},
])
LINT_SKEL_ENTRIES = write_json('lint_skeleton_entries.json', {
    'RT2001': {'entry': 'RT2001 (測試 標題) (BITE) 這裡沒有BITE段落純摘要。'},
    'RT2002': {'entry': 'RT2002 (測試 標題) ▎測試摘要。▎畫面：資料畫面。無BITE。'},
})
LINT_SKEL_OUT = os.path.join(TMP, 'lint_skeleton_batch.json')
outLS, codeLS = run(bp.cmd_build, Args(site='rt', raw=None, entries=LINT_SKEL_ENTRIES,
                                       checkpoint='0914-1200', out=LINT_SKEL_OUT,
                                       skeleton=LINT_SKEL))
check('build --skeleton＋lint：壞 entry 仍 exit 0', codeLS == 0, codeLS)
check('build --skeleton＋lint：壞 entry 的 ID 出現在警告裡', 'RT2001:' in outLS, outLS[-600:])
check('build --skeleton＋lint：乾淨 entry 沒有被列進警告', 'RT2002:' not in outLS, outLS[-600:])
_lso = json.load(open(LINT_SKEL_OUT, encoding='utf-8'))
_lso_rows = {r['id']: r for r in _lso['entries']}
check('build --skeleton＋lint：輸出檔內容不受警告影響',
      _lso_rows['RT2001']['entry'] == 'RT2001 (測試 標題) (BITE) 這裡沒有BITE段落純摘要。')

LINT_SKEL_DRY_OUT = os.path.join(TMP, 'lint_skeleton_dry_run_batch.json')
outLSD, codeLSD = run(bp.cmd_build, Args(site='rt', raw=None,
                                         entries=LINT_SKEL_ENTRIES,
                                         checkpoint='0914-1200', out=LINT_SKEL_DRY_OUT,
                                         skeleton=LINT_SKEL, dry_run=True))
check('build --skeleton --dry-run：仍跑 lint 且不寫輸出檔',
      codeLSD == 0 and 'RT2001:' in outLSD and not os.path.exists(LINT_SKEL_DRY_OUT),
      outLSD[-600:])

# ── R43 硬閘測試：白名單機械格式類原因同站 >= 5 則時，正式 build 與 --dry-run 均擋下 ──
GATE_RAW_5 = write_json('gate_raw_5.json', [
    {'code': f'RT310{i}', 'head': f'head {i}', 'story': f'story {i}', 'sb_count': 1}
    for i in range(5)
])
GATE_ENTRIES_5 = write_json('gate_entries_5.json', {
    f'RT310{i}': f'RT310{i} (BITE) ▎摘要。▎畫面：資料畫面。無BITE。'
    for i in range(5)
})
GATE_OUT_5 = os.path.join(TMP, 'gate_batch_5.json')

# 1. 正式 build 達門檻：exit 2、不寫 batch、錯誤訊息包含 ⛔ 與完整關鍵字
outG5, codeG5 = run(bp.cmd_build, Args(site='rt', raw=GATE_RAW_5, entries=GATE_ENTRIES_5,
                                       checkpoint='0914-1200', out=GATE_OUT_5))
check('build 硬閘：白名單格式錯誤≥5則時 exit 2 擋下', codeG5 == 2, str(codeG5))
check('build 硬閘：正式 build 被擋時絕不寫入 batch 輸出檔', not os.path.exists(GATE_OUT_5), GATE_OUT_5)
check('build 硬閘：錯誤訊息含 ⛔ 攔截警示', '⛔' in outG5, outG5[-600:])
check('build 硬閘：錯誤訊息點名站別與 reason code', 'RT' in outG5 and 'FMT_FIRST_NOTE_BITE' in outG5, outG5[-600:])
check('build 硬閘：錯誤訊息指明 batch.json 尚未寫入', 'batch.json 尚未寫入' in outG5, outG5[-600:])
check('build 硬閘：錯誤訊息要求一次 Write 整批重寫', '一次 `Write` 整批重寫' in outG5, outG5[-600:])
check('build 硬閘：錯誤訊息禁止逐筆 Edit', '禁止逐筆' in outG5 and 'Edit' in outG5, outG5[-600:])
check('build 硬閘：錯誤訊息要求重跑 --dry-run 至 0 則', '重跑 `build --dry-run`' in outG5 and '降到 0' in outG5, outG5[-600:])

# 2. --dry-run 模式達門檻：回傳非 0 exit code（exit 2），同樣印 ⛔ 訊息且不寫檔
GATE_DRY_OUT_5 = os.path.join(TMP, 'gate_dry_batch_5.json')
outGD5, codeGD5 = run(bp.cmd_build, Args(site='rt', raw=GATE_RAW_5, entries=GATE_ENTRIES_5,
                                         checkpoint='0914-1200', out=GATE_DRY_OUT_5,
                                         dry_run=True))
check('build --dry-run 硬閘：白名單格式錯誤≥5則時回傳非0 exit code（exit 2）', codeGD5 == 2, str(codeGD5))
check('build --dry-run 硬閘：不寫入輸出檔', not os.path.exists(GATE_DRY_OUT_5), GATE_DRY_OUT_5)
check('build --dry-run 硬閘：包含 ⛔ 與預檢未通過提示', '⛔' in outGD5 and '--dry-run 預檢未通過' in outGD5, outGD5[-600:])

# 3. --skeleton 分支達門檻：同樣 exit 2 且不寫檔
GATE_SKEL_5 = write_json('gate_skel_5.json', [
    {'id': f'RT310{i}', 'source': 'RT', 'checkpoint': '0914-1200', 'status': 'has_script',
     'src_text': 'x', 'sb_count': 1, 'entry': '', 'category': '', 'tc': ''}
    for i in range(5)
])
GATE_SKEL_ENTRIES_5 = write_json('gate_skel_entries_5.json', {
    f'RT310{i}': {'entry': f'RT310{i} (BITE) ▎摘要。▎畫面：資料畫面。無BITE。'}
    for i in range(5)
})
GATE_SKEL_OUT_5 = os.path.join(TMP, 'gate_skel_batch_5.json')
outGS5, codeGS5 = run(bp.cmd_build, Args(site='rt', raw=None, entries=GATE_SKEL_ENTRIES_5,
                                         checkpoint='0914-1200', out=GATE_SKEL_OUT_5,
                                         skeleton=GATE_SKEL_5))
check('build --skeleton 硬閘：白名單格式錯誤≥5則時 exit 2', codeGS5 == 2, str(codeGS5))
check('build --skeleton 硬閘：不寫入 batch 輸出檔', not os.path.exists(GATE_SKEL_OUT_5), GATE_SKEL_OUT_5)

# 4. 回歸測試：內容/語意類警告即使 >= 5 則，也絕不觸發硬閘（exit 0、正常產出 batch）
SEM_RAW_5 = write_json('sem_raw_5.json', [
    {'code': f'RT320{i}', 'head': f'head {i}', 'story': f'story {i}', 'sb_count': 1}
    for i in range(5)
])
# 觸發「BITE 引言疑似未翻譯成中文」內容警告（英文字元多於中文字元，非白名單機械格式）
SEM_ENTRIES_5 = write_json('sem_entries_5.json', {
    f'RT320{i}': f'RT320{i} (地方) (BITE) ▎測試摘要。▎畫面：資料畫面。▎BITE：拜登「This is an English soundbite without translation.」'
    for i in range(5)
})
SEM_OUT_5 = os.path.join(TMP, 'sem_batch_5.json')
outSEM, codeSEM = run(bp.cmd_build, Args(site='rt', raw=SEM_RAW_5, entries=SEM_ENTRIES_5,
                                         checkpoint='0914-1200', out=SEM_OUT_5))
check('build 回歸測試：內容類原因≥5則絕不觸發硬閘（維持 exit 0）', codeSEM == 0, str(codeSEM))
check('build 回歸測試：內容類原因≥5則正常寫入 batch.json', os.path.exists(SEM_OUT_5), SEM_OUT_5)
check('build 回歸測試：內容類原因無 ⛔ 硬閘訊息', '⛔' not in outSEM, outSEM[-600:])
check('build 回歸測試：內容類警告正常印出到 stderr', 'BITE 引言疑似未翻譯成中文' in outSEM, outSEM[-600:])
check('build 回歸測試：內容類原因不落 gate lock 檔（不觸發 Edit 技術鎖）',
      not os.path.exists(bp._gate_lock_path(SEM_ENTRIES_5, 'RT')))


def gate_scenario_dir(name):
    """gate lock 的作用範圍是「entries.json 所在目錄 ＋ 站別」，不是檔名——
    production 每輪各站的 entries.json 本來就落在各自獨立的 scratch 目錄，
    這裡每個情境各開一個子目錄，避免測試 fixture 互相共用同一份 lock 檔。"""
    d = os.path.join(TMP, name)
    os.makedirs(d, exist_ok=True)
    return d


def write_json_in(dir_, name, obj):
    p = os.path.join(dir_, name)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
    return p


# ── R43 遵守修法方向1：gate lock 標記檔（Edit 技術鎖）── ─────────────────
# 硬閘觸發時要落一份 <site>_gate_lock.json（跟 entries.json 同目錄），
# 給 PreToolUse hook（s2_gate_guard.py）技術性擋 Edit；重跑 build/--dry-run
# 確認 reason code 計數降到 0 時要自動清除。

# 情境一：驗 lock 檔內容欄位（站別／entries_path／reasons／dry_run）
_dir_content = gate_scenario_dir('gatelock_content')
GATE_ENTRIES_CONTENT = write_json_in(_dir_content, 'entries.json', {
    f'RT313{i}': f'RT313{i} (BITE) ▎摘要。▎畫面：資料畫面。無BITE。'
    for i in range(5)
})
GATE_RAW_CONTENT = write_json_in(_dir_content, 'raw.json', [
    {'code': f'RT313{i}', 'head': f'head {i}', 'story': f'story {i}', 'sb_count': 1}
    for i in range(5)
])
GATE_LOCK_PATH_CONTENT = bp._gate_lock_path(GATE_ENTRIES_CONTENT, 'RT')
run(bp.cmd_build, Args(site='rt', raw=GATE_RAW_CONTENT, entries=GATE_ENTRIES_CONTENT,
                       checkpoint='0918-2200', out=None))
check('gate lock：正式 build 觸發硬閘時落一份 gate lock 檔', os.path.exists(GATE_LOCK_PATH_CONTENT), GATE_LOCK_PATH_CONTENT)
with open(GATE_LOCK_PATH_CONTENT, encoding='utf-8') as f:
    _lock5 = json.load(f)
check('gate lock：內容含正確站別', _lock5.get('site') == 'RT', json.dumps(_lock5, ensure_ascii=False))
check('gate lock：內容含 entries.json 絕對路徑（正斜線）',
      _lock5.get('entries_path', '').replace('\\', '/') == os.path.abspath(GATE_ENTRIES_CONTENT).replace('\\', '/'),
      json.dumps(_lock5, ensure_ascii=False))
check('gate lock：內容含觸發的 reason code 與筆數',
      any(r.get('code') == 'FMT_FIRST_NOTE_BITE' and r.get('count') == 5 for r in _lock5.get('reasons', [])),
      json.dumps(_lock5, ensure_ascii=False))
check('gate lock：每個 reason 記錄涉及 ID，供 rewrite-entry 做權限邊界',
      any(r.get('code') == 'FMT_FIRST_NOTE_BITE'
          and r.get('items') == [f'RT313{i}' for i in range(5)]
          for r in _lock5.get('reasons', [])),
      json.dumps(_lock5, ensure_ascii=False))
check('gate lock：正式 build 觸發時 dry_run 欄位為 False', _lock5.get('dry_run') is False,
      json.dumps(_lock5, ensure_ascii=False))

# --dry-run 再次命中同一個 entries.json → 同一份 lock 被覆寫（dry_run 欄位改 True，不新增第二份）
run(bp.cmd_build, Args(site='rt', raw=GATE_RAW_CONTENT, entries=GATE_ENTRIES_CONTENT,
                       checkpoint='0918-2200', out=None, dry_run=True))
with open(GATE_LOCK_PATH_CONTENT, encoding='utf-8') as f:
    _lock5_dry = json.load(f)
check('gate lock：--dry-run 觸發後 dry_run 欄位更新為 True', _lock5_dry.get('dry_run') is True,
      json.dumps(_lock5_dry, ensure_ascii=False))
check('gate lock：同目錄同站別只有一份 lock 檔（覆寫不新增）',
      len([p for p in os.listdir(_dir_content) if p.endswith('_gate_lock.json')]) == 1)

# 情境二：完整生命週期——觸發 → 整批 Write 修好 → 重跑 --dry-run 確認歸零 → 自動清鎖
_dir_cycle = gate_scenario_dir('gatelock_cycle')
GATE_ENTRIES_CYCLE = write_json_in(_dir_cycle, 'entries.json', {
    f'RT311{i}': f'RT311{i} (BITE) ▎摘要。▎畫面：資料畫面。無BITE。'
    for i in range(5)
})
GATE_RAW_CYCLE = write_json_in(_dir_cycle, 'raw.json', [
    {'code': f'RT311{i}', 'head': f'head {i}', 'story': f'story {i}', 'sb_count': 1}
    for i in range(5)
])
GATE_LOCK_PATH_CYCLE = bp._gate_lock_path(GATE_ENTRIES_CYCLE, 'RT')
_, _code_cycle_trigger = run(bp.cmd_build, Args(site='rt', raw=GATE_RAW_CYCLE, entries=GATE_ENTRIES_CYCLE,
                                                checkpoint='0918-2200', out=None, dry_run=True))
check('gate lock 生命週期：觸發後 exit 2 且 lock 存在',
      _code_cycle_trigger == 2 and os.path.exists(GATE_LOCK_PATH_CYCLE))

# 模擬 agent 依指示用一次整批 Write 重寫（測試層面直接改寫同路徑內容）
with open(GATE_ENTRIES_CYCLE, 'w', encoding='utf-8') as f:
    json.dump({
        f'RT311{i}': f'RT311{i} ▎摘要 {i}。▎畫面：資料畫面。無BITE。'
        for i in range(5)
    }, f, ensure_ascii=False)

_out_cycle_recheck, _code_cycle_recheck = run(
    bp.cmd_build, Args(site='rt', raw=GATE_RAW_CYCLE, entries=GATE_ENTRIES_CYCLE,
                       checkpoint='0918-2200', out=None, dry_run=True))
check('gate lock 生命週期：內容修好後重跑 --dry-run 成功（exit 0）', _code_cycle_recheck == 0, str(_code_cycle_recheck))
check('gate lock 生命週期：reason code 計數降到 0 時自動清鎖',
      not os.path.exists(GATE_LOCK_PATH_CYCLE), GATE_LOCK_PATH_CYCLE)
check('gate lock 生命週期：自動清鎖訊息含 ✅', '✅' in _out_cycle_recheck and 'gate lock 已清除' in _out_cycle_recheck,
      _out_cycle_recheck[-400:])

# 情境三：gate-clear 子指令——手動清鎖逃生路徑
_dir_manual = gate_scenario_dir('gatelock_manual')
GATE_ENTRIES_MANUAL = write_json_in(_dir_manual, 'entries.json', {
    f'RT312{i}': f'RT312{i} (BITE) ▎摘要。▎畫面：資料畫面。無BITE。'
    for i in range(5)
})
GATE_RAW_MANUAL = write_json_in(_dir_manual, 'raw.json', [
    {'code': f'RT312{i}', 'head': f'head {i}', 'story': f'story {i}', 'sb_count': 1}
    for i in range(5)
])
GATE_LOCK_PATH_MANUAL = bp._gate_lock_path(GATE_ENTRIES_MANUAL, 'RT')
run(bp.cmd_build, Args(site='rt', raw=GATE_RAW_MANUAL, entries=GATE_ENTRIES_MANUAL,
                       checkpoint='0918-2200', out=None, dry_run=True))
check('gate-clear 前置：lock 存在', os.path.exists(GATE_LOCK_PATH_MANUAL), GATE_LOCK_PATH_MANUAL)

_out_gc, _code_gc = run(bp.cmd_gate_clear, Args(site='rt', entries=GATE_ENTRIES_MANUAL))
check('gate-clear：手動清除成功（exit 0）', _code_gc == 0, str(_code_gc))
check('gate-clear：lock 檔案已刪除', not os.path.exists(GATE_LOCK_PATH_MANUAL))
check('gate-clear：訊息含已手動清除字樣', '已手動清除' in _out_gc, _out_gc)

_out_gc2, _code_gc2 = run(bp.cmd_gate_clear, Args(site='rt', entries=GATE_ENTRIES_MANUAL))
check('gate-clear：lock 已不存在時再呼叫不報錯（exit 0）', _code_gc2 == 0, str(_code_gc2))
check('gate-clear：lock 已不存在時印出提示而非報錯', '沒有找到' in _out_gc2, _out_gc2)

# ── S3（複核 2026-09-14）：Claude Code offload 殼 → unwrap → from-raw ──────
#
# 背景：raw 檔太大時 Claude Code 會把工具結果落成本機「offload」檔，形狀是
# `[{"type":"text","text":"### Result\n<payload>\n### Page …"}]`，`<payload>`
# 可能裸 JSON、也可能包一層 ```json fenced code block```。`unwrap` 原本認
# 不出這層殼，會把整個 `[{"type":"text",...}]` 當「裸陣列」直接原樣複製，
# `from-raw` 拿到這種假裸陣列會對每個 `{"type":"text","text":...}` 算 id，
# 全部算出空字串——生出一份看起來正常、其實全空 id 的垃圾骨架。

NS_INNER = [
    {'id': 'NS0001', 'desc': '測試描述一',
     'script': '--REPORTER PKG-AS FOLLOWS-- Reporter Sot: "quote"',
     'ft': 'pkg', 'dur_ms': 121000},
    {'id': 'NS0002', 'desc': '測試描述二', 'script': '測試逐字稿二',
     'ft': 'vo', 'dur_ms': 55000},
]


def _offload_shell(payload_text):
    return [{'type': 'text', 'text': f'### Result\n{payload_text}\n### Page 1/1'}]


# S3-① unfenced payload：`### Result` 後面直接是裸 JSON
OFFLOAD_UNFENCED = write_json(
    'offload_unfenced.json',
    _offload_shell(json.dumps(NS_INNER, ensure_ascii=False)))
UNWRAPPED_UNFENCED = os.path.join(TMP, 'offload_unfenced_unwrapped.json')
out_s3a, code_s3a = run(bp.cmd_unwrap, Args(raw=OFFLOAD_UNFENCED, out=UNWRAPPED_UNFENCED))
check('S3① unwrap unfenced offload 殼 → exit 0', code_s3a == 0, out_s3a[:300])
check('S3① unwrap 認出殼型是 offload（訊息點名）', 'offload' in out_s3a, out_s3a[:300])
_s3a_data = json.load(open(UNWRAPPED_UNFENCED, encoding='utf-8'))
check('S3① unwrap 卸殼後是乾淨的裸陣列（2 筆、id 正確）',
      [it.get('id') for it in _s3a_data] == ['NS0001', 'NS0002'], str(_s3a_data))

# S3-② fenced payload：`### Result` 後面包一層 ```json fenced code block```
OFFLOAD_FENCED = write_json(
    'offload_fenced.json',
    _offload_shell('```json\n' + json.dumps(NS_INNER, ensure_ascii=False) + '\n```'))
UNWRAPPED_FENCED = os.path.join(TMP, 'offload_fenced_unwrapped.json')
out_s3b, code_s3b = run(bp.cmd_unwrap, Args(raw=OFFLOAD_FENCED, out=UNWRAPPED_FENCED))
check('S3② unwrap fenced offload 殼 → exit 0', code_s3b == 0, out_s3b[:300])
_s3b_data = json.load(open(UNWRAPPED_FENCED, encoding='utf-8'))
check('S3② unwrap fenced 卸殼後是乾淨的裸陣列（2 筆、id 正確）',
      [it.get('id') for it in _s3b_data] == ['NS0001', 'NS0002'], str(_s3b_data))

# S3-③ end-to-end：unwrap 產出的裸陣列直接餵給 from-raw（NS 站），要能正常
# 產出骨架，不是全空 id 的垃圾。
FR_OUT = os.path.join(TMP, 'ns_from_offload_skeleton.json')
out_s3c, code_s3c = run(bp.cmd_from_raw, Args(
    site='ns', raw=UNWRAPPED_FENCED, checkpoint='0914-1500',
    state=None, out=FR_OUT, page=None))
check('S3③ from-raw 吃 unwrap 後的 offload 內容 → exit 0', code_s3c == 0, out_s3c[:300])
_fr_skel = json.load(open(FR_OUT, encoding='utf-8'))
check('S3③ 骨架 2 則、id 正確（不是全空 id 的垃圾）',
      [r['id'] for r in _fr_skel] == ['NS0001', 'NS0002'], str(_fr_skel))
_fr_by_id = {r['id']: r for r in _fr_skel}
check('R44 NS from-raw 骨架保留 footage_type／duration_ms／inline_sot_count',
      _fr_by_id['NS0001'].get('footage_type') == 'pkg'
      and _fr_by_id['NS0001'].get('duration_ms') == 121000
      and _fr_by_id['NS0001'].get('inline_sot_count') == 1,
      str(_fr_by_id['NS0001']))
check('R44 NS 提示表不再印誤導 sb_count=0，改印 ft／inline_sot',
      'sb=n/a' in out_s3c and 'ft=pkg' in out_s3c and 'inline_sot=1' in out_s3c
      and '｜0｜' not in out_s3c, out_s3c[:500])

NS_ENTRIES = write_json('ns_entries.json', {
    'NS0001': {'entry': 'NS0001 (地方) ▎長片摘要。▎畫面：現場畫面▎無BITE。▎02:01'},
    'NS0002': {'entry': 'NS0002 (地方) ▎短片摘要。▎畫面：資料畫面▎無BITE。▎00:55'},
})
NS_BATCH_OUT = os.path.join(TMP, 'ns_batch.json')
out_s3h, code_s3h = run(bp.cmd_build, Args(
    site='ns', raw=None, entries=NS_ENTRIES, checkpoint='0914-1500',
    skeleton=FR_OUT, out=NS_BATCH_OUT))
_ns_batch = json.load(open(NS_BATCH_OUT, encoding='utf-8'))
_ns_rows = {r['id']: r for r in _ns_batch['entries']}
check('R44 build --skeleton 保留 NS footage_type／duration_ms／inline_sot_count',
      code_s3h == 0 and _ns_rows['NS0001'].get('footage_type') == 'pkg'
      and _ns_rows['NS0001'].get('duration_ms') == 121000
      and _ns_rows['NS0001'].get('inline_sot_count') == 1,
      str(_ns_rows.get('NS0001')))

# build 會先機械補上 SOT，再跑 lint；duration 白名單應已消失，inline SOT 的
# 內容判斷仍需保留。
check('R41/R42 build autofix 後只保留仍需人工判斷的 inline SOT 提醒',
      '補SOT 1 則：NS0001' in out_s3h and 'inline SOT' in out_s3h
      and 'PKG/DONUT且時長>1分鐘' not in out_s3h, out_s3h[-800:])

NS_DIRECT_BATCH_OUT = os.path.join(TMP, 'ns_direct_batch.json')
out_s3i, code_s3i = run(bp.cmd_build, Args(
    site='ns', raw=UNWRAPPED_FENCED, entries=NS_ENTRIES,
    checkpoint='0914-1500', out=NS_DIRECT_BATCH_OUT, skeleton=None))
_ns_direct = json.load(open(NS_DIRECT_BATCH_OUT, encoding='utf-8'))
_ns_direct_rows = {r['id']: r for r in _ns_direct['entries']}
check('R44 build（raw＋entries，非 skeleton）也保留 NS 結構化欄位',
      code_s3i == 0 and _ns_direct_rows['NS0001'].get('footage_type') == 'pkg'
      and _ns_direct_rows['NS0001'].get('duration_ms') == 121000
      and _ns_direct_rows['NS0001'].get('inline_sot_count') == 1,
      str(_ns_direct_rows.get('NS0001')))

# inline SOT 落在 4,000 字後也要留下可稽核錨點，不能被 truncate 靜默砍掉。
_long_inline = 'x' * 4100 + ' Reporter Sot: "quote"'
_long_kept = bp.truncate(_long_inline)
check('R41 truncate 保留 4,000 字後的 inline SOT 錨點',
      len(_long_kept) <= bp.SRC_TEXT_LIMIT and 'Reporter Sot' in _long_kept,
      f'len={len(_long_kept)}')

# S3-④ 殼認得出來，但內容解不出合法 JSON → 明確 ValueError／unwrap exit 非 0，
# 不悄悄把殼字串原樣複製當成資料。
OFFLOAD_GARBAGE = write_json(
    'offload_garbage.json',
    _offload_shell('這不是 JSON，也沒有 fenced code block，就是一段爬蟲爬壞的文字'))
UNWRAPPED_GARBAGE = os.path.join(TMP, 'offload_garbage_unwrapped.json')
out_s3d, code_s3d = run(bp.cmd_unwrap, Args(raw=OFFLOAD_GARBAGE, out=UNWRAPPED_GARBAGE))
check('S3④ offload 殼但內容解不出 JSON → 非 0 exit（不靜默假裝成功）', code_s3d != 0, out_s3d[:300])
check('S3④ 沒有寫出任何檔案', not os.path.exists(UNWRAPPED_GARBAGE))

# S3-⑤ from-raw 直接餵一份「不是 dict 陣列」的檔案（例如整份還沒卸殼的
# offload 殼本身）→ 要明確拒絕、非 0 exit，不產出骨架。
FR_BAD_SHAPE_OUT = os.path.join(TMP, 'ns_from_bad_shape_skeleton.json')
out_s3e, code_s3e = run(bp.cmd_from_raw, Args(
    site='ns', raw=OFFLOAD_UNFENCED, checkpoint='0914-1500',
    state=None, out=FR_BAD_SHAPE_OUT, page=None))
check('S3⑤ from-raw 吃到未卸殼的 offload 檔（每筆算出的 id 都空）→ 非 0 exit',
      code_s3e != 0, out_s3e[:300])
check('S3⑤ 沒有寫出任何骨架檔', not os.path.exists(FR_BAD_SHAPE_OUT))

# S3-⑤b 頂層根本不是 list（例如整份還是 dict 殼，例如 AP 清單那種
# {"Items": [...]}）→ 一樣要走「頂層不是 dict 陣列」這條分支拒絕。
NOT_A_LIST = write_json('ns_not_a_list.json', {'Items': [{'id': 'NS9001'}]})
FR_NOT_LIST_OUT = os.path.join(TMP, 'ns_not_list_skeleton.json')
out_s3g, code_s3g = run(bp.cmd_from_raw, Args(
    site='ns', raw=NOT_A_LIST, checkpoint='0914-1500',
    state=None, out=FR_NOT_LIST_OUT, page=None))
check('S3⑤b from-raw 吃到頂層是 dict（非裸陣列）→ 非 0 exit',
      code_s3g != 0, out_s3g[:300])
check('S3⑤b 錯誤訊息點名「頂層不是」dict 陣列', '頂層不是' in out_s3g, out_s3g[:300])
check('S3⑤b 沒有寫出任何骨架檔', not os.path.exists(FR_NOT_LIST_OUT))

# S3-⑥ from-raw 吃到一份「型是 dict 陣列，但每一筆算出的 id 都是空字串」
# 的檔案（例如欄位名整批打錯）→ 拒絕，不生垃圾骨架。
ALL_EMPTY_ID = write_json('ns_all_empty_id.json', [
    {'not_id': 'x', 'desc': '甲'},
    {'not_id': 'y', 'desc': '乙'},
])
FR_EMPTY_ID_OUT = os.path.join(TMP, 'ns_empty_id_skeleton.json')
out_s3f, code_s3f = run(bp.cmd_from_raw, Args(
    site='ns', raw=ALL_EMPTY_ID, checkpoint='0914-1500',
    state=None, out=FR_EMPTY_ID_OUT, page=None))
check('S3⑥ from-raw 每筆 id 都空 → 非 0 exit', code_s3f != 0, out_s3f[:300])
check('S3⑥ 沒有寫出任何骨架檔', not os.path.exists(FR_EMPTY_ID_OUT))

# ── S1（複核 2026-09-14）：rename-field --out 大小寫變體要判成同一個檔 ──
S1_IN = write_json('s1_case_in.json', [{'id': 'RT9001', 'raw_entry': '甲'}])
S1_OUT_UPPER = os.path.join(TMP, os.path.basename(S1_IN).upper())  # 大小寫變體
out_s1, code_s1 = run(bp.cmd_rename_field, Args(
    batch=S1_IN, from_key='raw_entry', to_key='entry', out=S1_OUT_UPPER, dry_run=False))
check('S1 --out 只是輸入檔的大小寫變體 → 拒絕（非 0 exit）', code_s1 != 0, out_s1[:300])
check('S1 原檔沒被改壞（仍是 raw_entry）',
      json.load(open(S1_IN, encoding='utf-8'))[0].get('raw_entry') == '甲')

# ── S2（複核 2026-09-14）：ENEX／ABC 平台狀態檔也要被 rename-field 擋掉 ──
for _platform_state_name in ('0913-ENEX-state.json', '0913-ABC-state.json'):
    _p_state = write_json(_platform_state_name, [{'id': 'X0001', 'raw_entry': '甲'}])
    _out_s2, _code_s2 = run(bp.cmd_rename_field, Args(
        batch=_p_state, from_key='raw_entry', to_key='entry', out=None, dry_run=False))
    check(f'S2 {_platform_state_name} → 非 0 exit（平台生產 state 也要擋）',
          _code_s2 != 0, _out_s2[:300])
    check(f'S2 {_platform_state_name} 錯誤訊息講明是生產狀態檔',
          '生產狀態檔' in _out_s2, _out_s2[:300])

# ── N3（複核 2026-09-14）：--out 帶不合法路徑 → 友善錯誤、exit 2，不炸 traceback ──
N3_IN = write_json('n3_in.json', [{'id': 'RT9101', 'raw_entry': '甲'}])
N3_BAD_OUT = os.path.join(TMP, 'n3_bad_out.json::$DATA')  # NTFS 保留字元組合
_tmp_before_n3 = set(os.listdir(TMP))
out_n3, code_n3 = run(bp.cmd_rename_field, Args(
    batch=N3_IN, from_key='raw_entry', to_key='entry', out=N3_BAD_OUT, dry_run=False))
check('N3 --out 不合法路徑 → 非 0 exit（友善訊息，不是裸 traceback）',
      code_n3 != 0 and 'Traceback' not in out_n3, out_n3[:300])
_tmp_leftover_n3 = [f for f in os.listdir(TMP) if f.startswith('.s2rf_tmp_')]
check('N3 沒有留下暫存檔殘骸', not _tmp_leftover_n3, str(_tmp_leftover_n3))

# ── 修法 B：build 對 raw_entry 常見筆誤做窄範圍自動修復 ──────────────────
# 1. 只有 raw_entry 沒有 entry 時：正式 build 與 --dry-run 自動修復為 entry
RAW_ENTRY_ONLY_DISK = write_json('raw_entry_only.json', {
    'RT9501': {
        'raw_entry': 'RT9501 (地方) ▎測試草稿摘要。▎畫面：資料畫面。無BITE。',
        'category': '國際/測試',
        'tc': 'T1/C1',
    }
})
RAW_ENTRY_RAW = write_json('raw_entry_raw.json', [
    {'code': 'RT9501', 'head': 'head 9501', 'story': 'story 9501', 'sb_count': 0}
])
RAW_ENTRY_OUT = os.path.join(TMP, 'raw_entry_batch.json')
disk_before = open(RAW_ENTRY_ONLY_DISK, encoding='utf-8').read()

out_re, code_re = run(bp.cmd_build, Args(
    site='rt', raw=RAW_ENTRY_RAW, entries=RAW_ENTRY_ONLY_DISK,
    checkpoint='0914-1200', out=RAW_ENTRY_OUT, dry_run=False
))
check('build raw_entry 修復：正式 build 成功（exit 0）', code_re == 0, str(code_re))
check('build raw_entry 修復：輸出檔已寫出', os.path.exists(RAW_ENTRY_OUT))
re_data = json.load(open(RAW_ENTRY_OUT, encoding='utf-8'))['entries'][0]
check('build raw_entry 修復：輸出 batch 正確包含 entry 欄位',
      re_data.get('entry') == 'RT9501 (地方) ▎測試草稿摘要。▎畫面：資料畫面。無BITE。')
check('build raw_entry 修復：輸出 batch 絕不殘留 raw_entry 鍵', 'raw_entry' not in re_data)
check('build raw_entry 修復：印出彙總警告點名 ID',
      '⚠️ 偵測到 1 筆工作草稿使用 raw_entry' in out_re and 'RT9501' in out_re, out_re[-500:])
check('build raw_entry 修復：原始 entries.json 檔案內容完全不變',
      open(RAW_ENTRY_ONLY_DISK, encoding='utf-8').read() == disk_before)

# 1b. --dry-run 同樣自動修復且不寫檔
RAW_ENTRY_DRY_OUT = os.path.join(TMP, 'raw_entry_dry_batch.json')
out_re_dry, code_re_dry = run(bp.cmd_build, Args(
    site='rt', raw=RAW_ENTRY_RAW, entries=RAW_ENTRY_ONLY_DISK,
    checkpoint='0914-1200', out=RAW_ENTRY_DRY_OUT, dry_run=True
))
check('build raw_entry 修復：--dry-run 成功（exit 0）', code_re_dry == 0, str(code_re_dry))
check('build raw_entry 修復：--dry-run 不寫入檔案', not os.path.exists(RAW_ENTRY_DRY_OUT))
check('build raw_entry 修復：--dry-run 亦印出彙總警告',
      '⚠️ 偵測到 1 筆工作草稿使用 raw_entry' in out_re_dry and 'RT9501' in out_re_dry, out_re_dry[-500:])

# 1c. --skeleton 分支同樣自動修復
RAW_ENTRY_SKEL = write_json('raw_entry_skel.json', [
    {'id': 'RT9501', 'source': 'RT', 'checkpoint': '0914-1200', 'status': 'has_script',
     'src_text': 'x', 'sb_count': 0, 'entry': '', 'category': '', 'tc': ''}
])
RAW_ENTRY_SKEL_OUT = os.path.join(TMP, 'raw_entry_skel_batch.json')
out_re_skel, code_re_skel = run(bp.cmd_build, Args(
    site='rt', raw=None, entries=RAW_ENTRY_ONLY_DISK,
    checkpoint='0914-1200', out=RAW_ENTRY_SKEL_OUT, skeleton=RAW_ENTRY_SKEL, dry_run=False
))
check('build --skeleton raw_entry 修復：成功（exit 0）', code_re_skel == 0, str(code_re_skel))
check('build --skeleton raw_entry 修復：輸出檔已寫出', os.path.exists(RAW_ENTRY_SKEL_OUT))
re_skel_data = json.load(open(RAW_ENTRY_SKEL_OUT, encoding='utf-8'))['entries'][0]
check('build --skeleton raw_entry 修復：輸出 batch 包含 entry 且無 raw_entry',
      re_skel_data.get('entry') == 'RT9501 (地方) ▎測試草稿摘要。▎畫面：資料畫面。無BITE。'
      and 'raw_entry' not in re_skel_data)

# 2. 同一筆同時有 entry 又有 raw_entry：拒絕猜測、exit 2 不寫 batch
CONFLICT_ENTRIES = write_json('conflict_entries.json', {
    'RT9502': {
        'entry': '正確 entry',
        'raw_entry': '誤植 raw_entry',
        'category': '國際/測試',
    }
})
CONFLICT_RAW = write_json('conflict_raw.json', [
    {'code': 'RT9502', 'head': 'head 9502', 'story': 'story 9502', 'sb_count': 0}
])
CONFLICT_OUT = os.path.join(TMP, 'conflict_batch.json')
out_cf, code_cf = run(bp.cmd_build, Args(
    site='rt', raw=CONFLICT_RAW, entries=CONFLICT_ENTRIES,
    checkpoint='0914-1200', out=CONFLICT_OUT, dry_run=False
))
check('build 衝突護欄：同時有 entry 與 raw_entry 則 exit 2', code_cf == 2, str(code_cf))
check('build 衝突護欄：不寫入 batch 輸出檔', not os.path.exists(CONFLICT_OUT))
check('build 衝突護欄：錯誤訊息包含 ⛔ 與衝突指引',
      '⛔' in out_cf and '同時包含 "entry" 與 "raw_entry"' in out_cf and 'batch 尚未寫入' in out_cf,
      out_cf[-500:])

# 3. raw_entry 不是字串型別時：不自動修復，維持缺欄位/未填處理
NON_STR_RAW_ENTRY = write_json('non_str_raw_entry.json', {
    'RT9503': {'raw_entry': 12345, 'category': '國際/測試'}
})
NON_STR_RAW = write_json('non_str_raw.json', [
    {'code': 'RT9503', 'head': 'head 9503', 'story': 'story 9503', 'sb_count': 0}
])
NON_STR_SKEL = write_json('non_str_skel.json', [
    {'id': 'RT9503', 'source': 'RT', 'checkpoint': '0914-1200', 'status': 'has_script',
     'src_text': 'x', 'sb_count': 0, 'entry': '', 'category': '', 'tc': ''}
])
NON_STR_OUT = os.path.join(TMP, 'non_str_batch.json')
out_ns, code_ns = run(bp.cmd_build, Args(
    site='rt', raw=None, entries=NON_STR_RAW_ENTRY,
    checkpoint='0914-1200', out=NON_STR_OUT, skeleton=NON_STR_SKEL, dry_run=False
))
check('build 非字串 raw_entry：不自動修復（未填警告）',
      '未填' in out_ns or '沒填' in out_ns, out_ns[-500:])
check('build 非字串 raw_entry：未修復就不印 raw_entry 轉換警告',
      '已暫轉為 entry' not in out_ns, out_ns[-500:])

# 4. 正常純 entry 草稿：既有行為不受影響，不印轉換警告
NORMAL_ENTRIES = write_json('normal_entries.json', {
    'RT9504': {'entry': 'RT9504 (地方) ▎正常摘要。▎畫面：資料畫面。無BITE。'}
})
NORMAL_SKEL = write_json('normal_skel.json', [
    {'id': 'RT9504', 'source': 'RT', 'checkpoint': '0914-1200', 'status': 'has_script',
     'src_text': 'x', 'sb_count': 0, 'entry': '', 'category': '', 'tc': ''}
])
NORMAL_OUT = os.path.join(TMP, 'normal_batch.json')
out_norm, code_norm = run(bp.cmd_build, Args(
    site='rt', raw=None, entries=NORMAL_ENTRIES,
    checkpoint='0914-1200', out=NORMAL_OUT, skeleton=NORMAL_SKEL, dry_run=False
))
check('build 正常草稿：exit 0 且不印轉換警告',
      code_norm == 0 and '已暫轉為 entry' not in out_norm, out_norm[-500:])

# ── 2026-09-22（0922-1700輪返工追查，Sol code review建議補測）：
# FMT_OPERATIONAL_NOTE 硬閘門檻降到 1（其餘reason code維持5）────────────
OPNOTE_ENTRIES = write_json('opnote_entries.json', {
    'RT9601': {'entry': 'RT9601 (地方) ▎摘要（相關人士發言，完整引言待補）。'
                        '▎畫面：資料畫面。無BITE。'}
})
OPNOTE_RAW = write_json('opnote_raw.json', [
    {'code': 'RT9601', 'head': 'head 9601', 'story': 'story 9601', 'sb_count': 0}
])
out_op, code_op = run(bp.cmd_build, Args(
    site='rt', raw=OPNOTE_RAW, entries=OPNOTE_ENTRIES,
    checkpoint='0922-1700', out=os.path.join(TMP, 'opnote_batch.json'), dry_run=True
))
check('硬閘門檻override：FMT_OPERATIONAL_NOTE 單則（count=1）就觸發硬閘攔截',
      code_op == 2 and '硬閘攔截' in out_op and 'FMT_OPERATIONAL_NOTE' in out_op,
      out_op[-500:])

GMT_ENTRIES = write_json('gmt_entries.json', {
    'RT9602': {'entry': 'RT9602 (地方) ▎摘要 GMT 換算。▎畫面：資料畫面。無BITE。'}
})
GMT_RAW = write_json('gmt_raw.json', [
    {'code': 'RT9602', 'head': 'head 9602', 'story': 'story 9602', 'sb_count': 0}
])
out_gmt, code_gmt = run(bp.cmd_build, Args(
    site='rt', raw=GMT_RAW, entries=GMT_ENTRIES,
    checkpoint='0922-1700', out=os.path.join(TMP, 'gmt_batch.json'), dry_run=True
))
check('硬閘門檻維持不變：其餘 reason code（FMT_CONTAINS_GMT）單則（count=1）不觸發硬閘',
      code_gmt in (0, 2) and '硬閘攔截' not in out_gmt, out_gmt[-500:])

# ── gate lock 精準修補：少量錯誤走 rewrite-entry，5 則以上維持整批 Write ──
_rewrite = getattr(bp, 'cmd_rewrite_entry', None)


def run_rewrite(**kw):
    if _rewrite is None:
        return 'rewrite-entry 尚未實作', 1
    defaults = dict(site='rt', ids=[], sets=[], new_ids=None, new_topics=None)
    defaults.update(kw)
    return run(_rewrite, Args(**defaults))


# argparse 真正掛的是薄殼 `cmd_rewrite_entry_cli`（擋「有 lock 卻帶自由模式旗標」）；
# 上面的 run_rewrite 刻意仍直打 cmd_rewrite_entry，好讓既有 lock 模式回歸案例
# 走的是一模一樣的路徑。
_rewrite_cli = getattr(bp, 'cmd_rewrite_entry_cli', None)


def run_rewrite_cli(**kw):
    if _rewrite_cli is None:
        return 'rewrite-entry CLI 薄殼尚未實作', 1
    defaults = dict(site='rt', ids=[], sets=[], new_ids=None, new_topics=None)
    defaults.update(kw)
    return run(_rewrite_cli, Args(**defaults))


_dir_rewrite_small = gate_scenario_dir('rewrite_small')
REWRITE_SMALL_ENTRIES = write_json_in(_dir_rewrite_small, 'entries.json', {
    'RT9701': {'entry': 'RT9701 (地方) ▎摘要（完整引言待補）。▎畫面：資料畫面。無BITE。',
               'category': '國際/測試'},
    'RT9702': {'entry': 'RT9702 (地方) ▎不應被改動。▎畫面：資料畫面。無BITE。',
               'category': '國際/保留'},
})
REWRITE_SMALL_RAW = write_json_in(_dir_rewrite_small, 'raw.json', [
    {'code': 'RT9701', 'head': 'head 9701', 'story': 'story 9701', 'sb_count': 0},
    {'code': 'RT9702', 'head': 'head 9702', 'story': 'story 9702', 'sb_count': 0},
])
_, _small_gate_code = run(bp.cmd_build, Args(
    site='rt', raw=REWRITE_SMALL_RAW, entries=REWRITE_SMALL_ENTRIES,
    checkpoint='0922-2100', out=None, dry_run=True))
REWRITE_SMALL_LOCK = bp._gate_lock_path(REWRITE_SMALL_ENTRIES, 'RT')
_small_before = json.load(open(REWRITE_SMALL_ENTRIES, encoding='utf-8'))['RT9702']
_fixed_9701 = json.dumps({
    'entry': 'RT9701 (地方) ▎已補上完整摘要。▎畫面：資料畫面。無BITE。',
    'category': '國際/測試',
}, ensure_ascii=False)
_out_rw_small, _code_rw_small = run_rewrite(
    entries=REWRITE_SMALL_ENTRIES, ids=['RT9701'], sets=[f'RT9701={_fixed_9701}'])
_small_after = json.load(open(REWRITE_SMALL_ENTRIES, encoding='utf-8'))
check('rewrite-entry：1-4 則時只改指定 ID、其他 entry 完全不變',
      _code_rw_small == 0
      and _small_after.get('RT9701', {}).get('entry', '').startswith('RT9701 (地方) ▎已補上')
      and _small_after.get('RT9702') == _small_before,
      _out_rw_small[-500:])
check('rewrite-entry：修完白名單 lint 歸零後自動清除 gate lock',
      _code_rw_small == 0 and not os.path.exists(REWRITE_SMALL_LOCK)
      and 'gate lock 已清除' in _out_rw_small,
      _out_rw_small[-500:])

_dir_rewrite_many = gate_scenario_dir('rewrite_many')
REWRITE_MANY_ENTRIES = write_json_in(_dir_rewrite_many, 'entries.json', {
    f'RT971{i}': f'RT971{i} (BITE) ▎摘要。▎畫面：資料畫面。無BITE。'
    for i in range(5)
})
REWRITE_MANY_RAW = write_json_in(_dir_rewrite_many, 'raw.json', [
    {'code': f'RT971{i}', 'head': f'head {i}', 'story': f'story {i}', 'sb_count': 1}
    for i in range(5)
])
run(bp.cmd_build, Args(site='rt', raw=REWRITE_MANY_RAW, entries=REWRITE_MANY_ENTRIES,
                       checkpoint='0922-2100', out=None, dry_run=True))
_many_before = open(REWRITE_MANY_ENTRIES, encoding='utf-8').read()
_out_rw_many, _code_rw_many = run_rewrite(
    entries=REWRITE_MANY_ENTRIES, ids=['RT9710'],
    sets=['RT9710=RT9710 ▎摘要。▎畫面：資料畫面。無BITE。'])
check('rewrite-entry：reason count 達 5 則時拒絕並要求整批 Write',
      _code_rw_many == 2 and '整批 Write' in _out_rw_many
      and open(REWRITE_MANY_ENTRIES, encoding='utf-8').read() == _many_before,
      _out_rw_many[-500:])

_dir_rewrite_scope = gate_scenario_dir('rewrite_scope')
REWRITE_SCOPE_ENTRIES = write_json_in(_dir_rewrite_scope, 'entries.json', {
    'RT9721': 'RT9721 (地方) ▎摘要（完整引言待補）。▎畫面：資料畫面。無BITE。',
    'RT9722': 'RT9722 (地方) ▎原稿。▎畫面：資料畫面。無BITE。',
})
REWRITE_SCOPE_RAW = write_json_in(_dir_rewrite_scope, 'raw.json', [
    {'code': 'RT9721', 'head': 'head 1', 'story': 'story 1', 'sb_count': 0},
    {'code': 'RT9722', 'head': 'head 2', 'story': 'story 2', 'sb_count': 0},
])
run(bp.cmd_build, Args(site='rt', raw=REWRITE_SCOPE_RAW, entries=REWRITE_SCOPE_ENTRIES,
                       checkpoint='0922-2100', out=None, dry_run=True))
_scope_before = open(REWRITE_SCOPE_ENTRIES, encoding='utf-8').read()
_out_rw_scope, _code_rw_scope = run_rewrite(
    entries=REWRITE_SCOPE_ENTRIES, ids=['RT9722'],
    sets=['RT9722=RT9722 (地方) ▎越權改稿。▎畫面：資料畫面。無BITE。'])
check('rewrite-entry：ID 不在 gate lock reason items 時拒絕且不改檔',
      _code_rw_scope == 2 and '不在 gate lock' in _out_rw_scope
      and open(REWRITE_SCOPE_ENTRIES, encoding='utf-8').read() == _scope_before,
      _out_rw_scope[-500:])

# ── rewrite-entry 自由模式（沒有 gate lock）──────────────────────────────
# 2026-09-23（A41 續辦）：`s2_gate_guard.py` 把 NS/AP/RT entries.json 改成
# 無條件禁止逐筆 Edit 之後，「沒觸發 gate lock 但想微調幾則」必須有合法管道。
# ⚠️ 這一段**取代**原本「gate lock 不存在時明確報錯且不改檔」那個案例——
# 那個舊期望值正是本次要改掉的行為，不是回歸破壞（見報告說明）。
_dir_rewrite_free = gate_scenario_dir('rewrite_free')
REWRITE_FREE_ENTRIES = write_json_in(_dir_rewrite_free, 'entries.json', {
    'RT9731': {'entry': 'RT9731 (地方) ▎原稿。▎畫面：資料畫面。無BITE。',
               'category': '國際/測試', 'tc': 'T'},
    'RT9732': {'entry': 'RT9732 (地方) ▎不應被改動。▎畫面：資料畫面。無BITE。',
               'category': '國際/保留'},
    '_new_topics': {},
})
_free_before_9732 = json.load(open(REWRITE_FREE_ENTRIES, encoding='utf-8'))['RT9732']
check('rewrite-entry 自由模式前置：確認這個情境真的沒有 gate lock',
      not os.path.exists(bp._gate_lock_path(REWRITE_FREE_ENTRIES, 'RT')))

_out_rw_free, _code_rw_free = run_rewrite(
    entries=REWRITE_FREE_ENTRIES, ids=['RT9731'],
    sets=['RT9731=RT9731 (地方) ▎改好的摘要。▎畫面：資料畫面。無BITE。'])
_free_after = json.load(open(REWRITE_FREE_ENTRIES, encoding='utf-8'))
check('rewrite-entry 自由模式：沒有 gate lock 也能修補（exit 0）',
      _code_rw_free == 0, ascii(_out_rw_free[-400:]))
check('rewrite-entry 自由模式：純文字 --set 只改 entry，category／tc 原樣保留',
      _free_after['RT9731']['entry'].startswith('RT9731 (地方) ▎改好的摘要')
      and _free_after['RT9731']['category'] == '國際/測試'
      and _free_after['RT9731']['tc'] == 'T',
      ascii(json.dumps(_free_after.get('RT9731'), ensure_ascii=False)))
check('rewrite-entry 自由模式：未指定的 ID 完全不動',
      _free_after['RT9732'] == _free_before_9732)
check('rewrite-entry 自由模式：頂層保留鍵 _new_topics 原樣保留',
      _free_after.get('_new_topics') == {})
check('rewrite-entry 自由模式：訊息講明走的是自由模式',
      '自由模式' in _out_rw_free, ascii(_out_rw_free[-400:]))
check('rewrite-entry 自由模式：不會順手生出 gate lock 檔',
      not os.path.exists(bp._gate_lock_path(REWRITE_FREE_ENTRIES, 'RT')))

# 只改 category（JSON object），entry 不能被動到
_out_rw_cat, _code_rw_cat = run_rewrite(
    entries=REWRITE_FREE_ENTRIES, ids=['RT9732'],
    sets=['RT9732=' + json.dumps({'category': '國際/改過'}, ensure_ascii=False)])
_free_after_cat = json.load(open(REWRITE_FREE_ENTRIES, encoding='utf-8'))
check('rewrite-entry 自由模式：object --set 只覆寫指定欄位，entry 原樣保留',
      _code_rw_cat == 0
      and _free_after_cat['RT9732']['category'] == '國際/改過'
      and _free_after_cat['RT9732']['entry'] == _free_before_9732['entry'],
      ascii(json.dumps(_free_after_cat.get('RT9732'), ensure_ascii=False)))

# 機械欄位／非白名單欄位一律拒絕
_dir_rewrite_free_field = gate_scenario_dir('rewrite_free_field')
REWRITE_FIELD_ENTRIES = write_json_in(_dir_rewrite_free_field, 'entries.json', {
    'RT9741': {'entry': 'RT9741 (地方) ▎原稿。▎畫面：資料畫面。無BITE。', 'category': '國際/測試'},
})
_field_before = open(REWRITE_FIELD_ENTRIES, encoding='utf-8').read()
for _bad_field in ('id', 'src_text', 'status', 'raw_entry'):
    _out_bad, _code_bad = run_rewrite(
        entries=REWRITE_FIELD_ENTRIES, ids=['RT9741'],
        sets=['RT9741=' + json.dumps({_bad_field: 'x'}, ensure_ascii=False)])
    check(f'rewrite-entry 自由模式：拒絕非白名單欄位 {_bad_field} 且不改檔',
          _code_bad == 2 and '不可修改欄位' in _out_bad
          and open(REWRITE_FIELD_ENTRIES, encoding='utf-8').read() == _field_before,
          ascii(_out_bad[-300:]))

_out_reserved, _code_reserved = run_rewrite(
    entries=REWRITE_FIELD_ENTRIES, ids=['_new_topics'],
    sets=['_new_topics=x'])
check('rewrite-entry 自由模式：拒絕把底線開頭保留鍵當素材則修改',
      _code_reserved == 2 and '保留鍵' in _out_reserved
      and open(REWRITE_FIELD_ENTRIES, encoding='utf-8').read() == _field_before,
      ascii(_out_reserved[-300:]))

_out_absent, _code_absent = run_rewrite(
    entries=REWRITE_FIELD_ENTRIES, ids=['RT9999'], sets=['RT9999=新增則'])
check('rewrite-entry 自由模式：沒帶 --new-id 時，不存在的 ID 仍拒絕（ID 打錯字防呆）',
      _code_absent == 2 and '找不到 ID' in _out_absent and '--new-id' in _out_absent
      and open(REWRITE_FIELD_ENTRIES, encoding='utf-8').read() == _field_before,
      ascii(_out_absent[-300:]))

# 落檔前的 lint 護欄：改出達門檻的白名單格式錯誤就整個拒絕
_dir_rewrite_free_lint = gate_scenario_dir('rewrite_free_lint')
REWRITE_LINT_ENTRIES = write_json_in(_dir_rewrite_free_lint, 'entries.json', {
    f'RT975{i}': {'entry': f'RT975{i} (地方) ▎乾淨摘要 {i}。▎畫面：資料畫面。無BITE。'}
    for i in range(5)
})
_lint_before = open(REWRITE_LINT_ENTRIES, encoding='utf-8').read()
_out_op, _code_op = run_rewrite(
    entries=REWRITE_LINT_ENTRIES, ids=['RT9750'],
    sets=['RT9750=RT9750 (地方) ▎摘要（完整引言待補）。▎畫面：資料畫面。無BITE。'])
check('rewrite-entry 自由模式：改出 FMT_OPERATIONAL_NOTE（門檻 1）就拒絕且不改檔',
      _code_op == 2 and 'FMT_OPERATIONAL_NOTE' in _out_op
      and open(REWRITE_LINT_ENTRIES, encoding='utf-8').read() == _lint_before,
      ascii(_out_op[-400:]))

_out_many_bad, _code_many_bad = run_rewrite(
    entries=REWRITE_LINT_ENTRIES,
    ids=[f'RT975{i}' for i in range(5)],
    sets=[f'RT975{i}=RT975{i} (BITE) ▎摘要。▎畫面：資料畫面。無BITE。' for i in range(5)])
check('rewrite-entry 自由模式：一次改出 5 則 FMT_FIRST_NOTE_BITE（門檻 5）就拒絕且不改檔',
      _code_many_bad == 2 and 'FMT_FIRST_NOTE_BITE' in _out_many_bad
      and open(REWRITE_LINT_ENTRIES, encoding='utf-8').read() == _lint_before,
      ascii(_out_many_bad[-400:]))

# 未達門檻的白名單警告只印警告、照樣落檔（不能把整份檔案鎖死）
_out_sub, _code_sub = run_rewrite(
    entries=REWRITE_LINT_ENTRIES, ids=['RT9751'],
    sets=['RT9751=RT9751 (BITE) ▎摘要。▎畫面：資料畫面。無BITE。'])
_lint_after = json.load(open(REWRITE_LINT_ENTRIES, encoding='utf-8'))
check('rewrite-entry 自由模式：未達門檻的白名單警告只提醒、仍允許落檔',
      _code_sub == 0 and _lint_after['RT9751']['entry'].startswith('RT9751 (BITE)')
      and 'FMT_FIRST_NOTE_BITE' in _out_sub,
      ascii(_out_sub[-400:]))

# 既有 raw_entry 筆誤形態：改 entry 時要把 raw_entry 一起拿掉，
# 否則 parse_draft_entry 會把兩鍵並存當成資料衝突 exit 2
_dir_rewrite_free_raw = gate_scenario_dir('rewrite_free_raw')
REWRITE_RAW_ENTRIES = write_json_in(_dir_rewrite_free_raw, 'entries.json', {
    'RT9761': {'raw_entry': 'RT9761 (地方) ▎舊稿。▎畫面：資料畫面。無BITE。',
               'category': '國際/測試'},
})
_out_raw, _code_raw = run_rewrite(
    entries=REWRITE_RAW_ENTRIES, ids=['RT9761'],
    sets=['RT9761=RT9761 (地方) ▎新稿。▎畫面：資料畫面。無BITE。'])
_raw_after = json.load(open(REWRITE_RAW_ENTRIES, encoding='utf-8'))['RT9761']
check('rewrite-entry 自由模式：原本是 raw_entry 的草稿改 entry 後不留兩鍵衝突',
      _code_raw == 0 and 'raw_entry' not in _raw_after
      and _raw_after['entry'].startswith('RT9761 (地方) ▎新稿')
      and _raw_after['category'] == '國際/測試',
      ascii(json.dumps(_raw_after, ensure_ascii=False)))

# 純字串草稿（舊格式）：只改 entry 仍維持純字串形狀
_dir_rewrite_free_str = gate_scenario_dir('rewrite_free_str')
REWRITE_STR_ENTRIES = write_json_in(_dir_rewrite_free_str, 'entries.json', {
    'RT9771': 'RT9771 (地方) ▎原稿。▎畫面：資料畫面。無BITE。',
})
_out_str, _code_str = run_rewrite(
    entries=REWRITE_STR_ENTRIES, ids=['RT9771'],
    sets=['RT9771=RT9771 (地方) ▎新稿。▎畫面：資料畫面。無BITE。'])
_str_after = json.load(open(REWRITE_STR_ENTRIES, encoding='utf-8'))['RT9771']
check('rewrite-entry 自由模式：舊格式純字串草稿改 entry 後仍是純字串',
      _code_str == 0 and isinstance(_str_after, str)
      and _str_after.startswith('RT9771 (地方) ▎新稿'),
      ascii(json.dumps(_str_after, ensure_ascii=False)))

# ── 自由模式 A41 續辦（2026-09-23）：新增 ID（--new-id）與 _new_topics（--new-topics）─
# ⚠️ 這一段**反轉**上面「不存在的 ID 拒絕（新增則是 Write 的工作）」那個舊斷言的
# 立場：舊期望值是「自由模式只能改既有則」，本次刻意改掉它，不是回歸破壞。
# （0923-1300 輪實測代價：agent 只想在 ns_entries_1300.json 加一個 `_new_topics`，
#   被擋下後只能整份 Write 重生成，花 70 秒＋數千 output token。）
# 舊案例本身保留、但意義換了：沒帶 `--new-id` 時 ID 不存在仍拒絕——那現在是
# 「ID 打錯字防呆」，不再是「不准新增」。
_dir_rw_add = gate_scenario_dir('rewrite_free_add')
REWRITE_ADD_ENTRIES = write_json_in(_dir_rw_add, 'entries.json', {
    'RT9801': {'entry': 'RT9801 (地方) ▎既有則。▎畫面：資料畫面。無BITE。',
               'category': '國際/既有'},
})
_add_before_9801 = json.load(open(REWRITE_ADD_ENTRIES, encoding='utf-8'))['RT9801']
_new_payload = json.dumps({
    'entry': 'RT9802 (地方) ▎新增的一則。▎畫面：資料畫面。無BITE。',
    'category': '國際/新增', 'tc': 'T',
}, ensure_ascii=False)
_out_add, _code_add = run_rewrite(
    entries=REWRITE_ADD_ENTRIES, ids=['RT9802'], new_ids=['RT9802'],
    sets=[f'RT9802={_new_payload}'])
_add_after = json.load(open(REWRITE_ADD_ENTRIES, encoding='utf-8'))
check('rewrite-entry 自由模式：--new-id 可以新增單一 ID（exit 0）',
      _code_add == 0, ascii(_out_add[-400:]))
check('rewrite-entry 自由模式：新增則寫成 13c 正規形狀 {entry, category, tc}',
      _add_after.get('RT9802') == {
          'entry': 'RT9802 (地方) ▎新增的一則。▎畫面：資料畫面。無BITE。',
          'category': '國際/新增', 'tc': 'T'},
      ascii(json.dumps(_add_after.get('RT9802'), ensure_ascii=False)))
check('rewrite-entry 自由模式：新增則不會動到既有則',
      _add_after.get('RT9801') == _add_before_9801)
check('rewrite-entry 自由模式：訊息分開報「新增」與「局部修補」',
      '新增 1 則' in _out_add and '局部修補' not in _out_add, ascii(_out_add[-400:]))
check('rewrite-entry 自由模式：新增則會提醒骨架必須也有這個 id',
      '骨架' in _out_add, ascii(_out_add[-400:]))

# 新增 + 修改既有，混在同一次呼叫
_out_mix, _code_mix = run_rewrite(
    entries=REWRITE_ADD_ENTRIES, ids=['RT9801', 'RT9803'], new_ids=['RT9803'],
    sets=['RT9801=' + json.dumps({'category': '國際/改過'}, ensure_ascii=False),
          'RT9803=RT9803 (地方) ▎第二則新增。▎畫面：資料畫面。無BITE。'])
_mix_after = json.load(open(REWRITE_ADD_ENTRIES, encoding='utf-8'))
check('rewrite-entry 自由模式：新增與修改既有可以混在同一次呼叫',
      _code_mix == 0
      and _mix_after['RT9801']['category'] == '國際/改過'
      and _mix_after['RT9801']['entry'] == _add_before_9801['entry']
      and _mix_after['RT9803'] == {
          'entry': 'RT9803 (地方) ▎第二則新增。▎畫面：資料畫面。無BITE。'},
      ascii(json.dumps(_mix_after, ensure_ascii=False)[-300:]))

# 新增則缺必要欄位（entry）
_dir_rw_addbad = gate_scenario_dir('rewrite_free_add_bad')
REWRITE_ADDBAD_ENTRIES = write_json_in(_dir_rw_addbad, 'entries.json', {
    'RT9811': {'entry': 'RT9811 (地方) ▎既有則。▎畫面：資料畫面。無BITE。'},
})
_addbad_before = open(REWRITE_ADDBAD_ENTRIES, encoding='utf-8').read()
_out_noentry, _code_noentry = run_rewrite(
    entries=REWRITE_ADDBAD_ENTRIES, ids=['RT9812'], new_ids=['RT9812'],
    sets=['RT9812=' + json.dumps({'category': '國際/沒有素材行'}, ensure_ascii=False)])
check('rewrite-entry 自由模式：新增則缺 entry 欄位就拒絕且不改檔',
      _code_noentry == 2 and '沒有非空的 entry' in _out_noentry
      and open(REWRITE_ADDBAD_ENTRIES, encoding='utf-8').read() == _addbad_before,
      ascii(_out_noentry[-300:]))

_out_blank, _code_blank = run_rewrite(
    entries=REWRITE_ADDBAD_ENTRIES, ids=['RT9813'], new_ids=['RT9813'],
    sets=['RT9813=' + json.dumps({'entry': '   '}, ensure_ascii=False)])
check('rewrite-entry 自由模式：新增則 entry 只有空白也拒絕',
      _code_blank == 2 and '沒有非空的 entry' in _out_blank
      and open(REWRITE_ADDBAD_ENTRIES, encoding='utf-8').read() == _addbad_before,
      ascii(_out_blank[-300:]))

# --new-id 指到其實已存在的 ID（典型 ID 打錯字）→ 拒絕，不靜默整則蓋掉
_out_dup, _code_dup = run_rewrite(
    entries=REWRITE_ADDBAD_ENTRIES, ids=['RT9811'], new_ids=['RT9811'],
    sets=['RT9811=RT9811 (地方) ▎以為是新增。▎畫面：資料畫面。無BITE。'])
check('rewrite-entry 自由模式：--new-id 撞到既有 ID 就拒絕（當成打錯字）',
      _code_dup == 2 and '其實已經在 entries.json 裡' in _out_dup
      and open(REWRITE_ADDBAD_ENTRIES, encoding='utf-8').read() == _addbad_before,
      ascii(_out_dup[-300:]))

# --new-id 必須是 --id／--set 的子集
_out_stray, _code_stray = run_rewrite(
    entries=REWRITE_ADDBAD_ENTRIES, ids=['RT9811'], new_ids=['RT9899'],
    sets=['RT9811=RT9811 (地方) ▎改稿。▎畫面：資料畫面。無BITE。'])
check('rewrite-entry 自由模式：--new-id 沒同時出現在 --id／--set 就拒絕',
      _code_stray == 2 and '必須同時出現在 --id' in _out_stray
      and open(REWRITE_ADDBAD_ENTRIES, encoding='utf-8').read() == _addbad_before,
      ascii(_out_stray[-300:]))

# 新增則也要被落檔前的 lint 硬閘看到
_dir_rw_addlint = gate_scenario_dir('rewrite_free_add_lint')
REWRITE_ADDLINT_ENTRIES = write_json_in(_dir_rw_addlint, 'entries.json', {
    'RT9821': {'entry': 'RT9821 (地方) ▎乾淨摘要。▎畫面：資料畫面。無BITE。'},
})
_addlint_before = open(REWRITE_ADDLINT_ENTRIES, encoding='utf-8').read()
_out_addop, _code_addop = run_rewrite(
    entries=REWRITE_ADDLINT_ENTRIES, ids=['RT9822'], new_ids=['RT9822'],
    sets=['RT9822=RT9822 (地方) ▎新增（完整引言待補）。▎畫面：資料畫面。無BITE。'])
check('rewrite-entry 自由模式：新增則格式錯到達門檻（FMT_OPERATIONAL_NOTE）照樣被硬閘擋',
      _code_addop == 2 and 'FMT_OPERATIONAL_NOTE' in _out_addop
      and open(REWRITE_ADDLINT_ENTRIES, encoding='utf-8').read() == _addlint_before,
      ascii(_out_addop[-400:]))

_out_add5, _code_add5 = run_rewrite(
    entries=REWRITE_ADDLINT_ENTRIES,
    ids=[f'RT983{i}' for i in range(5)],
    new_ids=[f'RT983{i}' for i in range(5)],
    sets=[f'RT983{i}=RT983{i} (BITE) ▎摘要。▎畫面：資料畫面。無BITE。' for i in range(5)])
check('rewrite-entry 自由模式：一次新增 5 則 FMT_FIRST_NOTE_BITE（門檻 5）也被擋且不改檔',
      _code_add5 == 2 and 'FMT_FIRST_NOTE_BITE' in _out_add5
      and open(REWRITE_ADDLINT_ENTRIES, encoding='utf-8').read() == _addlint_before,
      ascii(_out_add5[-400:]))

# ── --new-topics ────────────────────────────────────────────────────────
_dir_rw_nt = gate_scenario_dir('rewrite_free_newtopics')
REWRITE_NT_ENTRIES = write_json_in(_dir_rw_nt, 'entries.json', {
    'RT9841': {'entry': 'RT9841 (地方) ▎既有則。▎畫面：資料畫面。無BITE。'},
})
_nt_json = json.dumps(
    {'加薩停火談判': {'charter': '收加薩停火的談判進度，不收地面戰況',
                      'big': '國際', 'aliases': ['加薩談判']}}, ensure_ascii=False)
_out_nt, _code_nt = run_rewrite(entries=REWRITE_NT_ENTRIES, new_topics=_nt_json)
_nt_after = json.load(open(REWRITE_NT_ENTRIES, encoding='utf-8'))
check('rewrite-entry 自由模式：--new-topics 可以單獨使用（不給 --id）且 exit 0',
      _code_nt == 0, ascii(_out_nt[-400:]))
check('rewrite-entry 自由模式：--new-topics 寫出 build/add-batch 預期的 charter/big/aliases 形狀',
      _nt_after.get('_new_topics') == {
          '加薩停火談判': {'charter': '收加薩停火的談判進度，不收地面戰況',
                           'big': '國際', 'aliases': ['加薩談判']}},
      ascii(json.dumps(_nt_after.get('_new_topics'), ensure_ascii=False)))
check('rewrite-entry 自由模式：--new-topics 不動任何素材則',
      _nt_after.get('RT9841', {}).get('entry', '').startswith('RT9841 (地方) ▎既有則'))

# 逐題逐欄合併：只帶 charter，原本的 big/aliases 要留著
_out_nt2, _code_nt2 = run_rewrite(
    entries=REWRITE_NT_ENTRIES,
    new_topics=json.dumps({'加薩停火談判': {'charter': '改寫過的 charter'}},
                          ensure_ascii=False))
_nt_after2 = json.load(open(REWRITE_NT_ENTRIES, encoding='utf-8'))['_new_topics']
check('rewrite-entry 自由模式：--new-topics 是逐欄合併，只換 charter 不會清掉 big/aliases',
      _code_nt2 == 0
      and _nt_after2['加薩停火談判'] == {'charter': '改寫過的 charter',
                                         'big': '國際', 'aliases': ['加薩談判']},
      ascii(json.dumps(_nt_after2, ensure_ascii=False)))

# 新增 ID ＋ 補 _new_topics 同一次呼叫（0923-1300 那輪真正想做的事）
_out_both, _code_both = run_rewrite(
    entries=REWRITE_NT_ENTRIES, ids=['RT9842'], new_ids=['RT9842'],
    sets=['RT9842=RT9842 (地方) ▎新題的第一則。▎畫面：資料畫面。無BITE。'],
    new_topics=json.dumps({'某國大選': {'charter': '只收該國大選本身',
                                        'big': '國際'}}, ensure_ascii=False))
_both_after = json.load(open(REWRITE_NT_ENTRIES, encoding='utf-8'))
check('rewrite-entry 自由模式：一次呼叫可同時新增 ID 與補 _new_topics',
      _code_both == 0
      and _both_after['RT9842']['entry'].startswith('RT9842 (地方) ▎新題的第一則')
      and _both_after['_new_topics']['某國大選']['big'] == '國際'
      and '加薩停火談判' in _both_after['_new_topics'],
      ascii(_out_both[-400:]))

# `{}` ＝只確保頂層鍵存在（13c2 §2 要求三站一律帶這個鍵）
_dir_rw_nt_empty = gate_scenario_dir('rewrite_free_newtopics_empty')
REWRITE_NTE_ENTRIES = write_json_in(_dir_rw_nt_empty, 'entries.json', {
    'RT9851': {'entry': 'RT9851 (地方) ▎既有則。▎畫面：資料畫面。無BITE。'},
})
_out_nte, _code_nte = run_rewrite(entries=REWRITE_NTE_ENTRIES, new_topics='{}')
_nte_after = json.load(open(REWRITE_NTE_ENTRIES, encoding='utf-8'))
check('rewrite-entry 自由模式：--new-topics {} 只把頂層鍵補成空 object',
      _code_nte == 0 and _nte_after.get('_new_topics') == {}
      and '_new_topics' in _out_nte,
      ascii(_out_nte[-300:]))

# --new-topics 的格式驗證
_dir_rw_nt_bad = gate_scenario_dir('rewrite_free_newtopics_bad')
REWRITE_NTBAD_ENTRIES = write_json_in(_dir_rw_nt_bad, 'entries.json', {
    'RT9861': {'entry': 'RT9861 (地方) ▎既有則。▎畫面：資料畫面。無BITE。'},
})
_ntbad_before = open(REWRITE_NTBAD_ENTRIES, encoding='utf-8').read()
for _label, _bad_nt, _expect in (
        ('不是合法 JSON', '{題名: 沒引號}', '必須是合法 JSON'),
        ('JSON 但不是 object', '["題名"]', '必須是 JSON object'),
        ('單題的值不是 object', '{"題名": "charter 寫成字串"}', '必須是 object'),
        ('缺 big', '{"題名": {"charter": "只有 charter"}}', '合併後仍缺'),
        ('缺 charter', '{"題名": {"big": "國際"}}', '合併後仍缺'),
        ('charter 是空字串', '{"題名": {"charter": "  ", "big": "國際"}}', '必須是非空字串'),
        ('含不支援欄位', '{"題名": {"charter": "c", "big": "國際", "tc": "T"}}',
         '含不支援欄位'),
        ('aliases 型別錯', '{"題名": {"charter": "c", "big": "國際", "aliases": 5}}',
         'aliases 必須是陣列'),
        ('aliases 元素非字串', '{"題名": {"charter": "c", "big": "國際", "aliases": [1]}}',
         '非空字串'),
        ('題名用底線開頭', '{"_x": {"charter": "c", "big": "國際"}}', '不可用底線開頭'),
):
    _o, _c = run_rewrite(entries=REWRITE_NTBAD_ENTRIES, new_topics=_bad_nt)
    check(f'rewrite-entry 自由模式：--new-topics 格式驗證拒絕「{_label}」且不改檔',
          _c == 2 and _expect in _o
          and open(REWRITE_NTBAD_ENTRIES, encoding='utf-8').read() == _ntbad_before,
          ascii(_o[-300:]))

# 既有 `_new_topics` 是壞形狀時不靜默重建
_dir_rw_nt_broken = gate_scenario_dir('rewrite_free_newtopics_broken')
REWRITE_NTBROKEN_ENTRIES = write_json_in(_dir_rw_nt_broken, 'entries.json', {
    'RT9871': {'entry': 'RT9871 (地方) ▎既有則。▎畫面：資料畫面。無BITE。'},
    '_new_topics': ['寫成陣列了'],
})
_ntbroken_before = open(REWRITE_NTBROKEN_ENTRIES, encoding='utf-8').read()
_out_ntbroken, _code_ntbroken = run_rewrite(
    entries=REWRITE_NTBROKEN_ENTRIES,
    new_topics=json.dumps({'某題': {'charter': 'c', 'big': '國際'}}, ensure_ascii=False))
check('rewrite-entry 自由模式：既有 _new_topics 不是 object 時拒絕，不靜默覆蓋',
      _code_ntbroken == 2 and '不敢靜默覆蓋' in _out_ntbroken
      and open(REWRITE_NTBROKEN_ENTRIES, encoding='utf-8').read() == _ntbroken_before,
      ascii(_out_ntbroken[-300:]))

# 什麼都沒給：--id 與 --new-topics 皆空 → 明確報錯
_out_nothing, _code_nothing = run_rewrite(entries=REWRITE_NTBAD_ENTRIES)
check('rewrite-entry 自由模式：--id 與 --new-topics 都沒給就明確報錯',
      _code_nothing == 2 and '--id 至少給一個' in _out_nothing
      and '--new-topics' in _out_nothing,
      ascii(_out_nothing[-300:]))

# 有 gate lock 時：自由模式一律不接手，既有 lock 路徑行為完全不變（回歸）
_dir_rewrite_lock_guard = gate_scenario_dir('rewrite_lock_still_scoped')
REWRITE_LOCKGUARD_ENTRIES = write_json_in(_dir_rewrite_lock_guard, 'entries.json', {
    'RT9781': 'RT9781 (地方) ▎摘要（完整引言待補）。▎畫面：資料畫面。無BITE。',
    'RT9782': 'RT9782 (地方) ▎原稿。▎畫面：資料畫面。無BITE。',
})
REWRITE_LOCKGUARD_RAW = write_json_in(_dir_rewrite_lock_guard, 'raw.json', [
    {'code': 'RT9781', 'head': 'h1', 'story': 's1', 'sb_count': 0},
    {'code': 'RT9782', 'head': 'h2', 'story': 's2', 'sb_count': 0},
])
run(bp.cmd_build, Args(site='rt', raw=REWRITE_LOCKGUARD_RAW,
                       entries=REWRITE_LOCKGUARD_ENTRIES,
                       checkpoint='0923-0430', out=None, dry_run=True))
check('回歸前置：lock 已產生', os.path.exists(bp._gate_lock_path(REWRITE_LOCKGUARD_ENTRIES, 'RT')))
_lockguard_before = open(REWRITE_LOCKGUARD_ENTRIES, encoding='utf-8').read()
_out_lockguard, _code_lockguard = run_rewrite(
    entries=REWRITE_LOCKGUARD_ENTRIES, ids=['RT9782'],
    sets=['RT9782=RT9782 (地方) ▎越權改稿。▎畫面：資料畫面。無BITE。'])
check('回歸：有 lock 時仍只准改 lock reason items 列出的 ID（自由模式不接手）',
      _code_lockguard == 2 and '不在 gate lock' in _out_lockguard
      and open(REWRITE_LOCKGUARD_ENTRIES, encoding='utf-8').read() == _lockguard_before,
      ascii(_out_lockguard[-400:]))

# 帶錯 --site 不能混進自由模式繞過別站的 lock（跟 hook 端 _find_lock_for_path 同判準）
_out_xsite, _code_xsite = run_rewrite(
    site='ap', entries=REWRITE_LOCKGUARD_ENTRIES, ids=['RT9782'],
    sets=['RT9782=RT9782 (地方) ▎換個站別繞過。▎畫面：資料畫面。無BITE。'])
check('回歸：帶錯 --site 不能混進自由模式繞過別站 gate lock',
      _code_xsite == 2 and '站別不一致' in _out_xsite
      and open(REWRITE_LOCKGUARD_ENTRIES, encoding='utf-8').read() == _lockguard_before,
      ascii(_out_xsite[-400:]))

# 薄殼 cmd_rewrite_entry_cli：有 lock 時自由模式專屬旗標一律擋下，
# 不讓它靜默被 lock 模式忽略（那會變成「一半做了一半沒做」）。
for _label, _kw in (
        ('--new-id', dict(ids=['RT9781', 'RT9790'], new_ids=['RT9790'],
                          sets=['RT9781=RT9781 (地方) ▎修好。▎畫面：資料畫面。無BITE。',
                                'RT9790=RT9790 (地方) ▎偷渡新增。▎畫面：資料畫面。無BITE。'])),
        ('--new-topics', dict(ids=['RT9781'],
                              sets=['RT9781=RT9781 (地方) ▎修好。▎畫面：資料畫面。無BITE。'],
                              new_topics='{"某題":{"charter":"c","big":"國際"}}')),
):
    _o_cli, _c_cli = run_rewrite_cli(entries=REWRITE_LOCKGUARD_ENTRIES, **_kw)
    check(f'CLI 薄殼：有 gate lock 時 {_label} 直接拒絕且不改檔',
          _c_cli == 2 and '只在自由模式' in _o_cli
          and open(REWRITE_LOCKGUARD_ENTRIES, encoding='utf-8').read() == _lockguard_before,
          ascii(_o_cli[-400:]))

# 薄殼在沒有旗標時必須完全透明（lock 模式行為一個字未變）
_o_cli_pass, _c_cli_pass = run_rewrite_cli(
    entries=REWRITE_LOCKGUARD_ENTRIES, ids=['RT9782'],
    sets=['RT9782=RT9782 (地方) ▎越權改稿。▎畫面：資料畫面。無BITE。'])
check('CLI 薄殼：沒帶自由模式旗標時原樣轉交，lock 模式行為不變',
      _c_cli_pass == 2 and '不在 gate lock' in _o_cli_pass
      and open(REWRITE_LOCKGUARD_ENTRIES, encoding='utf-8').read() == _lockguard_before,
      ascii(_o_cli_pass[-400:]))

# 沒有 lock 時薄殼放行，自由模式旗標照常運作
_o_cli_free, _c_cli_free = run_rewrite_cli(
    entries=REWRITE_NTE_ENTRIES,
    new_topics='{"薄殼放行題":{"charter":"c","big":"國際"}}')
check('CLI 薄殼：沒有 gate lock 時 --new-topics 照常放行',
      _c_cli_free == 0
      and json.load(open(REWRITE_NTE_ENTRIES, encoding='utf-8'))
      ['_new_topics'].get('薄殼放行題', {}).get('big') == '國際',
      ascii(_o_cli_free[-300:]))

shutil.rmtree(TMP, ignore_errors=True)
print(f'\nPASS={sum(results)} FAIL={len(results) - sum(results)}')
sys.exit(0 if all(results) else 1)
