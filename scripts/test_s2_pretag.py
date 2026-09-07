# -*- coding: utf-8 -*-
"""s2_pretag.py 機械預標測試：T/C 建議、涉臺、(BITE) 建議、150 字、🔖 負面 lint（A31）。

比照 test_s2_from_raw.py 的手動 check() 跑法（`python test_s2_pretag.py`），不用 pytest。

覆蓋 Task 1 六案例：
  (a) 「漢光演習」→ taiwan_hit 命中、T 建議含「軍事國防」、C 建議含「臺灣」
  (b) YNA 來源＋文本講川普關稅（未提及「南韓」字面）→ C 建議含「南韓,美國」
      （南韓來自來源預設 C，美國來自內容）
  (c) sb_count=2 而 entry 寫「無BITE」→ lint 報 🎙 不一致
  (d) 摘要 160 字 → lint 報 📏 超長
  (e) footage「受訪畫面、記者連線」＋ entry 有 🔖 → lint 報 🔖（R19）
  (f) 機動 T「颱風」active、文本有「颱風」、tc.T 沒有 → lint 報 🌀 漏掛（mock load_special_t）
附帶：bite_suggest() 三態（True／False／None）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(f'{"PASS" if cond else "FAIL"}  {name}' + (f" -> {extra}" if extra else ""))


def finish():
    print(f"\n共 {len(results)} 項，通過 {sum(results)}，失敗 {len(results) - sum(results)}")
    sys.exit(0 if all(results) else 1)


try:
    import s2_pretag as pretag
except ImportError as e:
    check("s2_pretag 模組存在", False, str(e))
    finish()

check("s2_pretag 模組存在", True)

import s2_state  # noqa: E402  用來 mock load_special_t（案例 f）


# ── (a) 漢光演習：涉臺 ＋ 軍事國防 ＋ 臺灣 ─────────────────────────
TEXT_A = "漢光演習今天登場，國軍模擬應變本島遭突襲情境"
hit_a = pretag.taiwan_hit(TEXT_A)
check("(a) taiwan_hit 命中涉臺詞", bool(hit_a), str(hit_a))
sug_a = pretag.suggest_tc(TEXT_A)
check("(a) T 建議含「軍事國防」（D15）", "軍事國防" in sug_a["T"], str(sug_a))
check("(a) C 建議含「臺灣」", "臺灣" in sug_a["C"], str(sug_a))


# ── (b) YNA 來源＋川普關稅（文本未提「南韓」字面）→ C 建議含 南韓,美國 ──
TEXT_B = "美國川普政府片面加徵高額關稅，衝擊本國汽車業與出口商"
sug_b = pretag.suggest_tc(TEXT_B, source="YNA")
check("(b) C 建議含「美國」（內容判出）", "美國" in sug_b["C"], str(sug_b))
check("(b) C 建議含「南韓」（YNA 來源預設，13f）", "南韓" in sug_b["C"], str(sug_b))


# ── (c) sb_count=2 卻標「無BITE」→ lint 報 🎙 不一致 ───────────────
ENTRY_C = "RT9003 (備註) ▎某摘要內容簡短說明。▎畫面：資料畫面▎無BITE。▎00:20"
msgs_c = pretag.lint(ENTRY_C, sb_count=2)
check("(c) 🎙 BITE 標記與 sb_count 不一致", any(m.startswith("🎙") for m in msgs_c), str(msgs_c))


# ── (d) 摘要 160 字 → lint 報 📏 超長 ──────────────────────────
SUMMARY_160 = "測" * 160
ENTRY_D = f"RT9004 (備註) ▎{SUMMARY_160}▎畫面：資料畫面▎無BITE。▎00:45"
msgs_d = pretag.lint(ENTRY_D)
check("(d) 📏 摘要超過 150 字上限", any(m.startswith("📏") for m in msgs_d), str(msgs_d))


# ── (e) footage 只有受訪／連線類詞＋entry 有 🔖 → lint 報 R19 負面 ──
ENTRY_E = ("🔖 RT9001 (畫面好) (BITE) ▎災民描述驚悚經過。"
           "▎畫面：受訪畫面、記者連線▎BITE：某人「引言內容」▎01:23")
msgs_e = pretag.lint(ENTRY_E)
check("(e) 🔖 R19 負面命中（畫面欄只有受訪／連線類詞）",
      any(m.startswith("🔖") for m in msgs_e), str(msgs_e))


# ── (f) 機動 T「颱風」active、文本命中、tc.T 沒有 → lint 報 🌀 漏掛 ──
ENTRY_F = "颱風持續侵襲東南亞多地，淹水災情擴大"
_orig_load_special_t = s2_state.load_special_t
s2_state.load_special_t = lambda: (["颱風"], [{"name": "颱風", "status": "active"}])
try:
    msgs_f = pretag.lint(ENTRY_F, tc={"T": ["天災天氣"], "C": ["東南亞"]})
finally:
    s2_state.load_special_t = _orig_load_special_t
check("(f) 🌀 機動 T「颱風」active 且文本命中，tc.T 沒掛",
      any(m.startswith("🌀") and "颱風" in m for m in msgs_f), str(msgs_f))

# 反例：tc.T 已經有「颱風」時不該再報
msgs_f2 = None
_orig_load_special_t = s2_state.load_special_t
s2_state.load_special_t = lambda: (["颱風"], [{"name": "颱風", "status": "active"}])
try:
    msgs_f2 = pretag.lint(ENTRY_F, tc={"T": ["天災天氣", "颱風"], "C": ["東南亞"]})
finally:
    s2_state.load_special_t = _orig_load_special_t
check("(f 反例) tc.T 已掛「颱風」不再報 🌀", not any(m.startswith("🌀") for m in msgs_f2), str(msgs_f2))


# ── 附帶：bite_suggest() 三態 ──────────────────────────────────
check("bite_suggest：sb_count>0 且未標 (BITE) → True",
      pretag.bite_suggest(sb_count=3,
                           entry="RT9005 (備註) ▎摘要。▎畫面：資料畫面▎無BITE。▎00:10") is True)
check("bite_suggest：無任何訊號 → False",
      pretag.bite_suggest(sb_count=0, has_sot=False,
                           entry="RT9006 (備註) ▎摘要。▎畫面：資料畫面▎無BITE。▎00:10") is False)
check("bite_suggest：entry 已標 (BITE) → None（已決定過，不必再建議）",
      pretag.bite_suggest(sb_count=1,
                           entry="RT9007 (備註) (BITE) ▎摘要。▎畫面：資料畫面▎BITE：某人「話」▎00:10") is None)

finish()
