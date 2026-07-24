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

# SB 長度下限（P-015）：< 2 秒 FAIL、2~5 秒 WARN（仍通過）。
_SOT_SB_1SEC_BLOCK = _SOT_SB_SINGLE_BLOCK.replace("#03 0033-0044", "#03 0033-0034")  # 1 秒
_SOT_SB_4SEC_BLOCK = _SOT_SB_SINGLE_BLOCK.replace("#03 0033-0044", "#03 0033-0037")  # 4 秒
SOT_SB_1SEC = SOT_OK.replace("記者旁白第二句", _SOT_SB_1SEC_BLOCK)
SOT_SB_4SEC = SOT_OK.replace("記者旁白第二句", _SOT_SB_4SEC_BLOCK)


# --- 測試表 -----------------------------------------------------------------
# (名稱, 模式, 稿件, 官方稿, 期望)
#   期望 True            → 必須完全沒有 problems
#   期望 "某關鍵字"       → problems 裡必須有一條含這個關鍵字
CASES = [
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

    print(f"\n{passed} 通過，{failed} 失敗。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
