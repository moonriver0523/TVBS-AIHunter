#!/usr/bin/env python3
"""validate_sot.py 的反例測試（PASS／FAIL 各有樣本，不需要外部檔案）。

執行：
    python scripts/test_validate_sot.py

每個案例都宣告「期望通過」或「期望在訊息裡出現某個關鍵字」，這樣一條規則
如果被改壞（例如又把 SB 中文當成固定單行），這裡就會紅。

規則來源：
  - cnn/01-auto-script-writing.md（CTV 輸出結構、BAR 字卡、SB 長度下限）
  - common/00-寫稿通則.md（SB 五行格式）
  - common/06-auto-script-sot.md（SOT 主標題／次標題）
  - common/auto-script-learning/cases/2026-07-21-爆紅浣熊1600.md（多行中文、碎句）
"""

from __future__ import annotations

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("validate_sot", os.path.join(_HERE, "validate_sot.py"))
v = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


# --- CTV 稿件樣板 -----------------------------------------------------------

CTV_HEAD = """西雅圖一隻外型異常圓滾的浣熊在當地四處趴趴走被網友拍下，因身形像球體而爆紅，目擊民眾替牠取名Jimothy。當地獸醫研判，可能是先天脊椎縮短疾病；另外在加州舊金山灣，一隻落水小狗獲消防海空救援，之後也順利與尋找多日的主人團圓。

##

SUPER:
目擊民眾

BAR 1
西雅圖球型浣熊爆紅 外型怪異掀網路熱
BAR 2
目擊民眾取名Jimothy 獸醫先天脊椎病
BAR 3
網路瘋傳粉絲創作畫 浣熊成傳奇迷因星
BAR 4
舊金山灣落水小狗 消防海空救援返主人

BAR1
西雅圖有隻浣熊
外型特別圓滾
"""

CTV_TAIL = """
BAR2
這名字雖然有點隨性
但大家也覺得挺合理

BAR3
網路上的粉絲
反而更捧場

BAR4
另一邊加州舊金山灣
一隻小狗獨自落水
後來也順利找到主人
"""


def ctv(sb_block: str) -> str:
    return CTV_HEAD + "\n" + sb_block.strip("\n") + "\n" + CTV_TAIL


# 稿頭去標點錯誤版（魚群暴斃1600 案）：整段連寫、無任何中文句讀。
CTV_HEAD_NO_PUNCT = CTV_HEAD.replace(
    "西雅圖一隻外型異常圓滾的浣熊在當地四處趴趴走被網友拍下，因身形像球體而爆紅，"
    "目擊民眾替牠取名Jimothy。當地獸醫研判，可能是先天脊椎縮短疾病；"
    "另外在加州舊金山灣，一隻落水小狗獲消防海空救援，之後也順利與尋找多日的主人團圓。",
    "西雅圖一隻外型異常圓滾的浣熊在當地四處趴趴走被網友拍下因身形像球體而爆紅"
    "目擊民眾替牠取名Jimothy當地獸醫研判可能是先天脊椎縮短疾病"
    "另外在加州舊金山灣一隻落水小狗獲消防海空救援之後也順利與尋找多日的主人團圓",
)


def ctv_no_punct(sb_block: str) -> str:
    return CTV_HEAD_NO_PUNCT + "\n" + sb_block.strip("\n") + "\n" + CTV_TAIL


SB_MULTILINE = """
SB
目擊民眾
我和我先生看到牠
就覺得牠看起來
就是一隻Jimothy
0025-0029
Me and my husband saw him and he looked like a Jimothy to us
"""

SB_SINGLE_LINE = """
SB
目擊民眾
我們覺得牠就是Jimothy
0025-0029
Me and my husband saw him and he looked like a Jimothy to us
"""

SB_TOO_SHORT = """
SB
目擊民眾
我和我先生看到牠
就覺得牠看起來
就是一隻Jimothy
0025-0026
Me and my husband saw him and he looked like a Jimothy to us
"""

SB_LINE_TOO_WIDE = """
SB
目擊民眾
我和我先生看到牠的時候就覺得牠看起來就是一隻Jimothy
0025-0029
Me and my husband saw him and he looked like a Jimothy to us
"""

SB_NO_ENGLISH = """
SB
目擊民眾
我和我先生看到牠
0025-0029
"""

SB_QUOTED_ZH = """
SB
目擊民眾
「我和我先生看到牠
就覺得牠就是Jimothy
0025-0029
Me and my husband saw him and he looked like a Jimothy to us
"""

SOURCE_BARE_QUOTES = """--REPORTER PKG-AS FOLLOWS--
"what am I looking at?"
THAT IS A GREAT QUESTION - AND THE CONFUSION COULD BE FORGIVEN--
"Me and my husband saw him and he looked like a Jimothy to us"
FAIR ENOUGH. HE LOOKS LIKE SOMETHING- THAT'S FOR SURE.
"""


# --- SOT 稿件樣板 -----------------------------------------------------------

SOT_OK = """【主播稿頭】
這是一段主播稿頭。

【主標題】
美伊戰火失控邊緣 川普揚言擴戰奪島封港

【次標題】
1. 川普稱伊朗急著求和 不談就要徹底解決掉

【記者OS內文與對應畫面】
記者旁白第一句
記者旁白第二句
"""

SOT_FULLWIDTH_SPACE = SOT_OK.replace(
    "美伊戰火失控邊緣 川普揚言擴戰奪島封港",
    "美伊戰火失控邊緣　川普揚言擴戰奪島封港",
)

SOT_BAD_PUNCT = SOT_OK.replace(
    "美伊戰火失控邊緣 川普揚言擴戰奪島封港",
    "美伊戰火失控邊緣,川普揚言擴戰奪島封港再加兩字",
)

_SOT_SB_SINGLE_BLOCK = """記者旁白第二句

SB
智利總統 卡斯特
那些透過非法、不正規且秘密手段越境的人，遲早必須離開我們的國家。
#03 0033-0044
Those who came in illegally will be outside our country."""

_SOT_SB_MULTI_BLOCK = """記者旁白第二句

SB
智利總統 卡斯特
那些透過非法手段越境的人
遲早必須離開我們的國家
#03 0033-0044
Those who came in illegally will be outside our country."""

SOT_SB_SINGLE = SOT_OK.replace("記者旁白第二句", _SOT_SB_SINGLE_BLOCK)
SOT_SB_MULTI = SOT_OK.replace("記者旁白第二句", _SOT_SB_MULTI_BLOCK)

# CNN 六碼側錄的 TC 欄位格式（common/00-寫稿通則.md）：`CNN HHMMSS-HHMMSS`。
# 2026-07-24「破一百1200」案例：TC_RE 原本不認得 CNN 前綴，這兩段 SB 會被判
# 「TC 欄位格式無法辨識」，見 common/09-known-issues.md#validate_sotpy。
_SOT_SB_CNN_BLOCK = """記者旁白第二句

SB
CNN記者 尼克·羅伯森（Nick Robertson）
過去一小時，我們就看到「以眼還眼」的真實案例，一次美軍打擊命中邊境口岸伊朗一側。
CNN 210359-210418
Now we've had a very, very real world example of an eye for an eye in the past hour or so."""

SOT_SB_CNN = SOT_OK.replace("記者旁白第二句", _SOT_SB_CNN_BLOCK)

# P-025：CNN 六碼側錄 TC 帶母帶錄製日期（`CNN 7/28 HHMMSS-HHMMSS`）。
# 負例用帶日期的 1 秒 SB——若日期使解析失敗，SB 會靜默消失、FAIL 不會出現，
# 這個案例就會抓到（P-006 精神：證明檢查真的擋得住）。
_SOT_SB_CNN_DATED_BLOCK = _SOT_SB_CNN_BLOCK.replace("CNN 210359-210418", "CNN 7/28 210359-210418")
SOT_SB_CNN_DATED = SOT_OK.replace("記者旁白第二句", _SOT_SB_CNN_DATED_BLOCK)
_SOT_SB_CNN_DATED_1SEC_BLOCK = _SOT_SB_CNN_BLOCK.replace("CNN 210359-210418", "CNN 7/28 210359-210400")
SOT_SB_CNN_DATED_1SEC = SOT_OK.replace("記者旁白第二句", _SOT_SB_CNN_DATED_1SEC_BLOCK)

# SB 長度下限（P-015）：< 2 秒 FAIL、2~5 秒 WARN（仍通過）。
_SOT_SB_1SEC_BLOCK = _SOT_SB_SINGLE_BLOCK.replace("#03 0033-0044", "#03 0033-0034")  # 1 秒
_SOT_SB_4SEC_BLOCK = _SOT_SB_SINGLE_BLOCK.replace("#03 0033-0044", "#03 0033-0037")  # 4 秒
SOT_SB_1SEC = SOT_OK.replace("記者旁白第二句", _SOT_SB_1SEC_BLOCK)
SOT_SB_4SEC = SOT_OK.replace("記者旁白第二句", _SOT_SB_4SEC_BLOCK)

# 2026-10-12：問答合一與非路人連發，原文行不得混入 OS 字數。
SOT_QA_BLOCK = """SB
記者 Alex vs. 官員 Taylor
你會繼續推動這項政策嗎？
會，我們會繼續推動。
#03 0117-0124
Will you continue this policy?
Yes, we will continue."""
SOT_OFFICIAL_BLOCK = """SB
專家 Morgan
這項政策需要更多資源。
#04 0030-0039
This policy needs more resources."""
SOT_QA = SOT_OK + "\n" + SOT_QA_BLOCK + "\n\n記者收尾。\n"
SOT_CONSECUTIVE = SOT_OK + "\n" + SOT_QA_BLOCK + "\n" + SOT_OFFICIAL_BLOCK + "\n\n記者收尾。\n"
SOT_CONSECUTIVE_1SEC = SOT_CONSECUTIVE.replace("#04 0030-0039", "#04 0030-0031")

# SOL4：原文取滿即停，無空行的後續旁白仍須計入 OS。
SOT_SINGLE_ORIGINAL = """SB
官員 Taylor
我們會繼續推動。
#03 0117-0124
We will continue."""
SOT_OVERLONG = SOT_OK.replace(
    "記者旁白第二句", SOT_SINGLE_ORIGINAL + "\n" + "應計入旁白的中文字。" * 100,
)


# --- 測試表 -----------------------------------------------------------------
# (名稱, 模式, 稿件, 官方稿, 期望)
#   期望 True            → 必須完全沒有 problems
#   期望 "某關鍵字"       → problems 裡必須有一條含這個關鍵字
CASES = [
    ("SOT/問答合一多行原文應通過", "sot", SOT_QA, None, True),
    ("SOT/非路人 SB 連發應通過", "sot", SOT_CONSECUTIVE, None, True),
    ("SOT/連發中 1 秒 SB 仍須 FAIL", "sot", SOT_CONSECUTIVE_1SEC, None, "秒下限"),
    # ---- 本案核心：SB 中文可多行 ----
    ("CTV/SB 中文多行應通過", "ctv", ctv(SB_MULTILINE), None, True),
    ("CTV/SB 中文單行也應通過", "ctv", ctv(SB_SINGLE_LINE), None, True),

    # ---- 本案核心：碎句要被擋 ----
    ("CTV/1 秒碎句必須 FAIL", "ctv", ctv(SB_TOO_SHORT), None, "秒下限"),

    # ---- 每行 14 字仍要逐行檢查（多行不等於免檢） ----
    ("CTV/單行超過 14 字必須 FAIL", "ctv", ctv(SB_LINE_TOO_WIDE), None, "超過上限"),

    # ---- 五行格式的其餘欄位不可因多行解析而漏檢 ----
    ("CTV/缺英文原句必須 FAIL", "ctv", ctv(SB_NO_ENGLISH), None, "缺少英文原句"),
    ("CTV/中文以引號起始必須 FAIL", "ctv", ctv(SB_QUOTED_ZH), None, "引號"),

    # ---- 稿頭句讀（魚群暴斃1600 案，P-014） ----
    ("CTV/稿頭有句讀應通過", "ctv", ctv(SB_MULTILINE), None, True),
    ("CTV/稿頭整段無句讀必須 FAIL", "ctv", ctv_no_punct(SB_MULTILINE), None, "沒有任何中文句讀"),

    # ---- SOT 主標題／次標題 ----
    ("SOT/SB 中文單行應通過", "sot", SOT_SB_SINGLE, None, True),
    ("SOT/SB 中文多行應通過", "sot", SOT_SB_MULTI, None, True),
    ("SOT/CNN六碼側錄TC格式應通過", "sot", SOT_SB_CNN, None, True),
    ("SOT/CNN TC帶錄製日期應通過（P-025）", "sot", SOT_SB_CNN_DATED, None, True),
    ("SOT/CNN TC帶日期的1秒SB必須FAIL", "sot", SOT_SB_CNN_DATED_1SEC, None, "秒下限"),

    # ---- SOT SB 長度下限（P-015） ----
    ("SOT/1 秒 SB 必須 FAIL", "sot", SOT_SB_1SEC, None, "秒下限"),
    ("SOT/4 秒 SB 應通過（僅 WARN）", "sot", SOT_SB_4SEC, None, True),
    ("SOT/半形空格標題應通過", "sot", SOT_OK, None, True),
    ("SOT/全形空格標題必須 FAIL", "sot", SOT_FULLWIDTH_SPACE, None, "非半形空格"),
    ("SOT/半形逗號標題必須 FAIL", "sot", SOT_BAD_PUNCT, None, "不允許的半形標點"),
]


def run_case(name, mode, text, source, expect):
    if mode == "ctv":
        problems = v.validate_ctv(text, source)[0]
    else:
        problems = v.validate(text, 120.0, None)[0]

    if expect is True:
        if problems:
            return False, "期望通過，實際 FAIL：" + "｜".join(problems[:3])
        return True, "通過"

    hit = [p for p in problems if expect in p]
    if not hit:
        return False, f"期望出現「{expect}」，實際 problems：" + ("｜".join(problems[:3]) or "(無)")
    return True, hit[0][:60]


def test_source_quote_extraction():
    """--source-script 對「引號式引言」官方稿的抽取（爆紅浣熊1600 案）。"""
    quotes = v.collect_source_quotes(SOURCE_BARE_QUOTES)
    if len(quotes) != 2:
        return False, f"期望抽到 2 句引號式引言，實際 {len(quotes)} 句：{quotes}"
    if "what am I looking at?" not in quotes:
        return False, f"漏抓問句引言：{quotes}"
    return True, f"抽到 {len(quotes)} 句：{quotes[0][:30]}…"


def main() -> int:
    passed = failed = 0
    print("=== validate_sot.py 反例測試 ===\n")

    for name, mode, text, source, expect in CASES:
        ok, detail = run_case(name, mode, text, source, expect)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}\n         {detail}")
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)

    ok, detail = test_source_quote_extraction()
    print(f"  [{'PASS' if ok else 'FAIL'}] 官方稿/引號式引言要抓得到\n         {detail}")
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)

    for name, check in [
        ("問答原文完整解析與 OS 排除", test_sot_multiline_original),
        ("非路人連發逐段解析與累計", test_sot_consecutive_blocks),
        ("單行 SB 後無空行接中文 OS", test_sot_single_original_zh_os),
        ("單行 SB 後無空行接英文 OS", test_sot_single_original_en_os),
        ("日文原文後無空行接中文 OS", test_sot_japanese_original_zh_os),
        ("問答原文取滿後無空行接 OS", test_sot_qa_original_os_boundary),
        ("問答原文不足須回報格式問題", test_sot_qa_original_shortage),
        ("SOL4 超長整稿必須 FAIL", test_sot_overlong),
    ]:
        try:
            check()
            ok, detail = True, "通過"
        except AssertionError as exc:
            ok, detail = False, str(exc)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}\n         {detail}")
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)

    print(f"\n{passed} 通過，{failed} 失敗。")
    return 1 if failed else 0


def test_sot_multiline_original():
    blocks = v.parse_sot_sb_blocks(SOT_QA_BLOCK)
    assert len(blocks) == 1, "問答應是一段 SB"
    assert blocks[0]["english"] == "Will you continue this policy?\nYes, we will continue.", "第二行原文遺失"
    assert blocks[0]["line_span"] == (0, 7), "line_span 未涵蓋全部原文"
    assert blocks[0]["raw_lines"][-1] == "Yes, we will continue.", "raw_lines 未保留答句"
    assert v.count_sot_os_chars(SOT_QA_BLOCK + "\n\n記者收尾。") == v.full_width_len("記者收尾。"), "原文被計入 OS"
    # 下一區塊沒有空行時，也不得吞掉畫面、NS、圖卡、署名或章節標題。
    for marker in ['#01 TC0005 "畫面"', 'NS #01 0005-0010 環境音', '==AICG==', 'TVBS 許岱軒', '【其他區塊】']:
        blk = v.parse_sot_sb_blocks(SOT_QA_BLOCK + "\n" + marker)[0]
        assert blk["line_span"] == (0, 7), f"原文誤吞下一區塊：{marker}"


def test_sot_consecutive_blocks():
    blocks = v.parse_sot_sb_blocks(SOT_CONSECUTIVE)
    assert [b["tc"] for b in blocks] == ["#03 0117-0124", "#04 0030-0039"], "連發 SB 未逐段解析"
    problems, notes, _ = v.validate(SOT_CONSECUTIVE, 120.0, None)
    assert not problems, str(problems)
    assert any("第1段 SB：#03 0117-0124 = 7秒" in n for n in notes), str(notes)
    assert any("第2段 SB：#04 0030-0039 = 9秒" in n for n in notes), str(notes)
    expected = v.count_sot_os_chars(v.extract_section(SOT_OK, "記者OS內文")) + v.full_width_len("記者收尾。")
    os_block = v.extract_section(SOT_CONSECUTIVE, "記者OS內文")
    assert v.count_sot_os_chars(os_block) == expected, "連發原文混入 OS"
    total = expected / v.CHARS_PER_MINUTE * 60 + 16
    assert f"SB共16.0秒" in notes[-1], notes[-1]
    assert f"總長度約{total:.1f}秒" in notes[-1], notes[-1]


def assert_sot_original_os_boundary(sb, os_text, original, end):
    text = sb + "\n" + os_text
    blk = v.parse_sot_sb_blocks(text)[0]
    assert blk["english"] == original, "原文誤吞後續 OS"
    assert blk["line_span"] == (0, end), "line_span 誤含 OS"
    assert blk["raw_lines"] == sb.splitlines(), "raw_lines 誤含 OS 或遺失原文"
    assert v.count_sot_os_chars(text) == v.full_width_len(os_text), "後續 OS 漏算"


def test_sot_single_original_zh_os():
    assert_sot_original_os_boundary(
        SOT_SINGLE_ORIGINAL, "記者旁白必須計入字數。", "We will continue.", 5,
    )
    # 一般 SB 的中文可多行，原文仍只取一行（既有行為）。
    multi_zh = SOT_SINGLE_ORIGINAL.replace("我們會繼續推動。", "我們會繼續\n推動這項政策。")
    assert_sot_original_os_boundary(multi_zh, "記者旁白。", "We will continue.", 6)


def test_sot_single_original_en_os():
    assert_sot_original_os_boundary(
        SOT_SINGLE_ORIGINAL, "The reporter continues with the next development.", "We will continue.", 5,
    )


def test_sot_japanese_original_zh_os():
    original = "私たちはこの政策を続けます。"
    sb = SOT_SINGLE_ORIGINAL.replace("We will continue.", original)
    assert_sot_original_os_boundary(sb, "記者旁白必須計入字數。", original, 5)


def test_sot_qa_original_os_boundary():
    original = "Will you continue this policy?\nYes, we will continue."
    for speaker in [
        "記者 Alex vs. 官員 Taylor", "記者VS.美國總統 川普 8.11",
        "記者ｖｓ．美國總統 川普 8.11", "記者ＶＳ．美國總統 川普 8.11",
    ]:
        sb = SOT_QA_BLOCK.replace("記者 Alex vs. 官員 Taylor", speaker)
        for os_text in ["記者旁白必須計入字數。", "The reporter continues."]:
            assert_sot_original_os_boundary(sb, os_text, original, 7)


def test_sot_qa_original_shortage():
    partial = SOT_QA_BLOCK.rsplit("\n", 1)[0]
    for boundary in [
        "", "\n\n記者旁白。", '\n#01 TC0005 "畫面"\n記者旁白。',
        "\nNS #01 0005-0010 環境音\n記者旁白。", "\n==AICG==\n記者旁白。",
        "\nTVBS 許岱軒", "\n【其他區塊】", "\n#05 0010-0020",
        "\n" + SOT_OFFICIAL_BLOCK,
    ]:
        text = partial + boundary
        blk = v.parse_sot_sb_blocks(text)[0]
        assert blk["english"] == "Will you continue this policy?", "原文不足時誤吞邊界"
        assert blk["line_span"] == (0, 6), "原文不足時區間未正確結束"
        problems = v.validate(SOT_OK + "\n" + text, 120.0, None)[0]
        assert any("問答 SB 原文行數不足" in p and "預期2行" in p and "實際1行" in p for p in problems), str(problems)
        if "記者旁白。" in boundary:
            assert v.count_sot_os_chars(text) == v.full_width_len("記者旁白。"), "格式問題後的 OS 漏算"
    no_original = partial.rsplit("\n", 1)[0]
    problems = v.validate(SOT_OK + "\n" + no_original, 120.0, None)[0]
    assert any("問答 SB 原文行數不足" in p and "實際0行" in p for p in problems), str(problems)


def test_sot_overlong():
    os_block = v.extract_section(SOT_OVERLONG, "記者OS內文")
    assert v.count_sot_os_chars(os_block) == 1007, "SOL4 的 1000 字旁白漏算"
    problems, notes, _ = v.validate(SOT_OVERLONG, 120.0, None)
    assert any("超過目標" in p for p in problems), str(problems)
    assert "總長度約248.7秒" in notes[-1], notes[-1]


if __name__ == "__main__":
    sys.exit(main())
