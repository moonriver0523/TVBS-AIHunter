#!/usr/bin/env python3
"""s2_batch_prep.py `autofix-tags` 子指令測試（R43層1治本，2026-09-19）。

背景：0919-0430輪transcript查證確認，機械提示表標記（⚠️SOT／⚠️疑似BITE）
即使正確顯示，草稿階段仍常被漏套用；但漏掉的兩類（缺(BITE)括號、缺SOT
字樣）在「已有錨點括號」時是可以機械安全補上的，不需要編輯判斷內容——
這支子指令做的就是這個。真正需要判斷的 FMT_FIRST_NOTE_BITE（(BITE) 是
唯一/第一個括號，沒有描述性第一備註）刻意不自動修，只列出來。

覆蓋：
  - MW-017FR 真實案例（0919-0430輪）：NS DONUT 108秒、缺(BITE)又缺SOT，
    自動修補後應與 agent 當輪實際手動修法逐字相同。
  - AP4685444 真實案例（同輪）：(BITE) 是唯一括號，不可自動修，應列在
    「仍需人工判斷」報告裡，entry 內容維持不變。
  - --out 給了才另存，不給就地覆寫 --entries（跟 fill-src-text 既有慣例一致）。
  - NS 站沒帶 --skeleton 時只做 (BITE) 修補、SOT 修補略過且有提示，不炸。
  - AP/RT 站完全不需要 --skeleton（(BITE) 修補本身跟站別/時長無關）。
  - category/tc 等其他欄位在修補前後完全不變（只動 entry 欄位本身）。
  - _new_topics 頂層鍵原樣跳過，不被誤當成一筆素材處理。
  - raw_entry 筆誤欄位（R43衍生問題）修補後寫回時保留原欄位名，不擅自改名
    （改名是另一條已merge的邏輯，不在這支工具職責內）。

用法：python test_s2_autofix_tags.py
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('bp_autofix', os.path.join(HERE, 's2_batch_prep.py'))
bp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bp)

TMP = tempfile.mkdtemp(prefix='s2_autofix_test_')
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
    out, err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with redirect_stdout(out), redirect_stderr(err):
            fn(args)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    return out.getvalue() + err.getvalue(), code


# ── 0919-0430輪真實案例：MW-017FR（可自動修）＋ AP4685444（不可自動修）──
MW017_ORIG = ('MW-017FR (愛荷華州 暖心故事) ▎98歲保羅利透過80年前因輟學撐持家計'
              '未能取得的高中畢業證書，本週終於在安養中心收到校方頒發。'
              '▎畫面：安養中心頒發畢業證書。▎BITE：畢業證書獲頒者保羅利透'
              '「我從沒想過會拿到這張畢業證書」▎1:48')
MW017_EXPECTED_FIXED = ('MW-017FR (SOT 愛荷華州 暖心故事) (BITE) ▎98歲保羅利透過80年前因輟學撐持家計'
                         '未能取得的高中畢業證書，本週終於在安養中心收到校方頒發。'
                         '▎畫面：安養中心頒發畢業證書。▎BITE：畢業證書獲頒者保羅利透'
                         '「我從沒想過會拿到這張畢業證書」▎1:48')
AP4685444_ORIG = ('AP4685444 (BITE) ▎墨西哥總統謝恩鮑姆表示，本週與川普通話後兩國貿易談判進展順利。'
                   '▎畫面：謝恩鮑姆記者會受訪。▎BITE：墨西哥總統謝恩鮑姆'
                   '「我能告訴各位的是，我們正在推進」▎2:06')

NS_ENTRIES = write_json('ns_entries.json', {
    'MW-017FR': {'entry': MW017_ORIG, 'category': '美國/美國暖新聞/愛荷華畢業證書', 'tc': '話題/美國'},
})
NS_SKELETON = write_json('ns_skeleton.json', [
    {'id': 'MW-017FR', 'footage_type': 'DONUT', 'duration_ms': 108000},
])

out1, code1 = run(bp.cmd_autofix_tags, Args(site='ns', entries=NS_ENTRIES, skeleton=NS_SKELETON, out=None))
check('autofix-tags（NS，就地覆寫）：成功（exit 0）', code1 == 0, str(code1))
with open(NS_ENTRIES, encoding='utf-8') as f:
    ns_result = json.load(f)
check('MW-017FR：entry 修補後跟 agent 當輪真實手動修法逐字相同',
      ns_result['MW-017FR']['entry'] == MW017_EXPECTED_FIXED, ns_result['MW-017FR']['entry'])
check('MW-017FR：category 欄位維持不變（只動 entry）',
      ns_result['MW-017FR']['category'] == '美國/美國暖新聞/愛荷華畢業證書')
check('MW-017FR：tc 欄位維持不變（只動 entry）',
      ns_result['MW-017FR']['tc'] == '話題/美國')
check('報告：印出補(BITE)與補SOT筆數', '補(BITE) 1 則' in out1 and '補SOT 1 則' in out1, out1)
check('報告：點名 MW-017FR', 'MW-017FR' in out1, out1)

# AP 站（不可自動修）：entry 完全不變、被列進「仍需人工判斷」
AP_ENTRIES = write_json('ap_entries.json', {
    'AP4685444': {'entry': AP4685444_ORIG, 'category': '財經/美墨貿易談判/謝恩鮑姆通話', 'tc': '財經/中南美,美國'},
})
out2, code2 = run(bp.cmd_autofix_tags, Args(site='ap', entries=AP_ENTRIES, skeleton=None, out=None))
check('autofix-tags（AP，不可自動修的情況）：成功（exit 0，不因修不了而報錯）', code2 == 0, str(code2))
with open(AP_ENTRIES, encoding='utf-8') as f:
    ap_result = json.load(f)
check('AP4685444：(BITE)是唯一括號，entry 完全不變（沒被誤修）',
      ap_result['AP4685444']['entry'] == AP4685444_ORIG, ap_result['AP4685444']['entry'])
check('AP4685444：報告列為「仍有機械格式問題無法自動修」',
      '仍有 1 項機械格式問題無法自動修' in out2 and 'AP4685444' in out2 and 'FMT_FIRST_NOTE_BITE' in out2, out2)
check('AP4685444：報告訊息含「需人工判斷」而非假裝修好',
      '需人工判斷' in out2, out2)

# ── --out：給了就另存，不覆寫原檔 ────────────────────────────────
NS_ENTRIES2 = write_json('ns_entries2.json', {
    'MW-017FR': {'entry': MW017_ORIG, 'category': 'x', 'tc': 'y'},
})
NS_OUT2 = os.path.join(TMP, 'ns_entries2_fixed.json')
out3, code3 = run(bp.cmd_autofix_tags, Args(site='ns', entries=NS_ENTRIES2, skeleton=NS_SKELETON, out=NS_OUT2))
check('--out 給了：成功寫到指定輸出路徑', os.path.exists(NS_OUT2), NS_OUT2)
with open(NS_ENTRIES2, encoding='utf-8') as f:
    orig_untouched = json.load(f)
check('--out 給了：原始 --entries 檔完全不被動', orig_untouched['MW-017FR']['entry'] == MW017_ORIG)
with open(NS_OUT2, encoding='utf-8') as f:
    out_content = json.load(f)
check('--out 給了：輸出檔內容是修好的版本', out_content['MW-017FR']['entry'] == MW017_EXPECTED_FIXED)

# ── NS 站沒帶 --skeleton：只做 (BITE) 修補，SOT 略過且提示，不炸 ──────
NS_ENTRIES3 = write_json('ns_entries3.json', {
    'MW-017FR': {'entry': MW017_ORIG, 'category': 'x', 'tc': 'y'},
})
out4, code4 = run(bp.cmd_autofix_tags, Args(site='ns', entries=NS_ENTRIES3, skeleton=None, out=None))
check('NS 沒帶 --skeleton：成功（exit 0，不因缺骨架而炸）', code4 == 0, str(code4))
check('NS 沒帶 --skeleton：印出略過 SOT 修補的提示', 'SOT 自動修補這關略過' in out4, out4)
with open(NS_ENTRIES3, encoding='utf-8') as f:
    ns3_result = json.load(f)
check('NS 沒帶 --skeleton：(BITE) 仍照常補上', '(BITE)' in ns3_result['MW-017FR']['entry'])
check('NS 沒帶 --skeleton：SOT 沒補上（沒有 footage_type/duration_ms 依據）',
      'SOT' not in ns3_result['MW-017FR']['entry'].split('▎', 1)[0])

# ── _new_topics 頂層鍵：原樣跳過，不被誤當成一筆素材 ─────────────────
NS_ENTRIES4 = write_json('ns_entries4.json', {
    '_new_topics': {'測試新題': {'charter': 'x', 'big': '社會'}},
    'MW-017FR': {'entry': MW017_ORIG, 'category': 'x', 'tc': 'y'},
})
out5, code5 = run(bp.cmd_autofix_tags, Args(site='ns', entries=NS_ENTRIES4, skeleton=NS_SKELETON, out=None))
check('_new_topics 存在時：成功（exit 0）', code5 == 0, str(code5))
with open(NS_ENTRIES4, encoding='utf-8') as f:
    ns4_result = json.load(f)
check('_new_topics：原樣保留、未被當成素材處理掉',
      ns4_result.get('_new_topics') == {'測試新題': {'charter': 'x', 'big': '社會'}})
check('_new_topics 存在時：MW-017FR 仍正常修補', '(BITE)' in ns4_result['MW-017FR']['entry']
      and 'SOT' in ns4_result['MW-017FR']['entry'].split('▎', 1)[0])

# ── raw_entry 筆誤欄位：修補後保留原欄位名，不擅自改名 ─────────────────
NS_ENTRIES5 = write_json('ns_entries5.json', {
    'MW-017FR': {'raw_entry': MW017_ORIG, 'category': 'x', 'tc': 'y'},
})
out6, code6 = run(bp.cmd_autofix_tags, Args(site='ns', entries=NS_ENTRIES5, skeleton=NS_SKELETON, out=None))
check('raw_entry 筆誤欄位：成功（exit 0）', code6 == 0, str(code6))
with open(NS_ENTRIES5, encoding='utf-8') as f:
    ns5_result = json.load(f)
check('raw_entry 筆誤欄位：修補結果寫回同一個鍵名（raw_entry），不擅自改名成 entry',
      'raw_entry' in ns5_result['MW-017FR'] and 'entry' not in ns5_result['MW-017FR'],
      str(ns5_result['MW-017FR']))
check('raw_entry 筆誤欄位：內容確實修補到位',
      ns5_result['MW-017FR']['raw_entry'] == MW017_EXPECTED_FIXED)

# ── AP/RT 完全不需要 --skeleton（(BITE) 修補跟站別/時長無關）───────────
RT_ENTRIES = write_json('rt_entries.json', {
    'RT3187': {'entry': 'RT3187 (黎巴嫩牧羊人) ▎黎巴嫩南部…▎畫面：牧羊畫面。▎BITE：牧羊人「這些牲畜是我生命的一部分」▎6:22',
               'category': 'x', 'tc': 'y'},
})
out7, code7 = run(bp.cmd_autofix_tags, Args(site='rt', entries=RT_ENTRIES, skeleton=None, out=None))
check('RT 不帶 --skeleton：成功且正常修補（(BITE)修補跟skeleton無關）', code7 == 0, str(code7))
with open(RT_ENTRIES, encoding='utf-8') as f:
    rt_result = json.load(f)
check('RT3187：(BITE) 補上', '(BITE)' in rt_result['RT3187']['entry'])
check('RT 站沒有 SOT 修補相關輸出（非 NS 站不做這件事）', 'SOT' not in out7 or '略過' not in out7)

# ── 沒有任何可修的項目：不假裝有動作 ────────────────────────────────
CLEAN_ENTRIES = write_json('clean_entries.json', {
    'AP9999': {'entry': 'AP9999 (資料畫面) ▎一般敘述。▎畫面：畫面描述。▎無BITE。', 'category': 'x', 'tc': 'y'},
})
out8, code8 = run(bp.cmd_autofix_tags, Args(site='ap', entries=CLEAN_ENTRIES, skeleton=None, out=None))
check('全部乾淨、無需修補：成功（exit 0）', code8 == 0, str(code8))
check('全部乾淨：報告顯示 0 則修補', '補(BITE) 0 則' in out8, out8)
check('全部乾淨：不印「仍有…無法自動修」（沒有殘留問題）', '仍有' not in out8, out8)
with open(CLEAN_ENTRIES, encoding='utf-8') as f:
    clean_result = json.load(f)
check('全部乾淨：entry 內容完全不變', clean_result['AP9999']['entry'] ==
      'AP9999 (資料畫面) ▎一般敘述。▎畫面：畫面描述。▎無BITE。')

print(f'\n共 {len(results)} 項，通過 {sum(results)}，失敗 {len(results) - sum(results)}')
sys.exit(0 if all(results) else 1)
