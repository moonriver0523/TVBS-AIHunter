# -*- coding: utf-8 -*-
"""機械預標：T/C 建議、涉臺提醒、(BITE) 建議、素材行 lint（A31，2026-09-07）。

⛔ **不是 collector**：只讀已經抽好的 raw／entry 文字，不碰站方 API。
⛔ **不寫狀態檔**：四個出口（`from-raw` 提示表／`build` 的 `row["suggest"]`／
   `add-batch` 缺 tc 時的提示／`lint()`）全部只印、只當「row 上多一個沒人存的
   欄位」，agent 判斷不同時以 agent 為準，不必回報。
⛔ **純函式、無網路、無 LLM**：輸入純文字／已解析欄位，輸出純資料結構或訊息
   list，方便單元測試（tempfile 合成即可，不需要真的跑一輪掃帶）。

T/C 候選重用 `scripts/prototype/build_tc_matrix_0821.py::tag_tc()` 的關鍵詞表——
透過 `s2_render_matrix._make_tagger()` 拿「UNKNOWN 就不建議」的 patched 版
（見 `_get_matrix()`），不是直接 import 原始 `tag_tc()`：原始版找不到分類會
靜默塞「社會」／「國際」，那樣「判出來的」跟「猜的」在畫面上長得一樣，
違背「建議永遠是建議」的前提。

D15（2026-09-07 已裁決）：T 新增「軍事國防」、C 歐洲拆出「英國」。**這裡先補
關鍵詞讓 pre-tagger 能建議**，TC-字典.md 本身這次不改（另案落地，見全檢實作
06）——agent 若照建議下 `set-tc` 而字典還沒收錄，會被 `_set_one_tc()` 退件，
這是已知、可接受的過渡狀態，不是這支腳本的 bug。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2_parse as sp  # noqa: E402  raw_entry → 結構化欄位（parse_entry）

# ── 涉臺詞表（Architecture 訂案，可擴充）：只加不改；改字典見 D15 ──────
# ⚠️ `from-raw` 提示表餵的文字是 AP／RT／NS 站方原文（英文為主），中文詞表在
# 英文稿上幾乎打不中——這裡刻意中英夾雜，測過命中率再决定要不要繼續擴。
TAIWAN_KW = [
    "臺灣", "台灣", "臺海", "國軍", "漢光", "兩岸", "我國", "臺北", "高雄",
    "台積電", "海峽中線", "陸委會", "國台辦",
    "Taiwan", "Taipei", "TSMC", "Han Kuang", "cross-strait", "Cross-Strait",
]

# D15：T 新增「軍事國防」。只加不改；字典本身這次不動，改字典見 D15。
MILITARY_T_KW = [
    "國防", "軍演", "軍事演習", "演習", "漢光", "飛彈", "導彈", "軍艦", "軍機",
    "徵兵", "軍售", "國防部長", "核潛艦", "航艦",
    "defense ministry", "military drill", "missile", "warship",
]

# D15：C 歐洲拆出「英國」。只加不改；字典本身這次不動，改字典見 D15。
UK_C_KW = [
    "英國", "倫敦", "唐寧街", "英相", "白金漢宮",
    "UK", "Britain", "London", "Downing Street",
]

# 來源預設 C（13f 已訂，2026-08-25 使用者裁）：只在**內容判不出東西時墊底**，
# 內容判出來的一律疊加、不取代——韓聯社報「川普關稅衝擊南韓車廠」要掛
# 南韓,美國，不是只掛預設的南韓。
SOURCE_DEFAULT_C = {
    "YNA": ["南韓"],
    "CNA": ["新加坡", "東南亞"],
    "NHK": ["日本"],
}

# 🔖 負面（R19，2026-08-30 已修訂進 13e）：畫面欄只有這些詞、沒有實拍內容時
# 不該標「畫面好」。只加不改；判準文字見 13e §「只標真正突出的」。
FOOTAGE_NEG_KW = [
    "受訪畫面", "記者連線", "站立播報", "專訪", "證詞",
    "記者棚內播報", "純談話畫面", "地圖圖卡", "資料畫面",
]

# 與 s2_state.FT_MUST_BITE 同一組判準（見 bite_doubt()）。這裡自己存一份常數
# 而不 import s2_state，是為了讓 lint() 的這條分支不必付出模組依賴的代價——
# 唯一真的需要碰 s2_state 的是 🌀 機動 T 檢查（load_special_t()），且那裡是
# 函式內延後 import，見 `_active_special_t()` 的說明。
_FT_MUST_BITE = {"SOT", "BUTTED SOTS", "SOT RAW", "ISO", "DONUT", "INTERVIEW", "RAW"}

_matrix_mod = None


def _get_matrix():
    """延後載入 `s2_render_matrix`，取它 patch 過的 `tag_tc`（UNKNOWN 不兜底）。

    ⛔ **不要改成模組頂部 `import`**：`s2_render_matrix` 頂部有
    `from s2_state import normalize_c, normalize_t, load_special_t`；而
    `s2_state.py`（Task 3）要 `import s2_pretag`——三者連成一個環：
    `s2_state → s2_pretag → s2_render_matrix → s2_state`（此時
    `normalize_c` 還沒定義到）會直接 `ImportError`。延後到**第一次真的呼叫
    `suggest_tc()` 時**才載入，那時兩邊模組都已經跑完 import 階段，環就打斷了。
    """
    global _matrix_mod
    if _matrix_mod is None:
        import s2_render_matrix
        _matrix_mod = s2_render_matrix
    return _matrix_mod


def _active_special_t():
    """機動 T 的 active 名單。壞掉／載不到都當「沒有」，不擋 lint。

    用 `import s2_state`（不是 `from s2_state import load_special_t`）：
    測試要 mock 這支時是直接改 `s2_state.load_special_t` 這個屬性
    （見 test_s2_pretag.py 案例 f），`import` 整個模組再呼叫屬性能吃到 mock，
    `from...import` 那種寫法在函式定義當下就把參照釘死了，mock 不到。
    """
    try:
        import s2_state
        active, _all = s2_state.load_special_t()
        return active or []
    except Exception:
        return []


def suggest_tc(text, source=None):
    """機械 T/C 候選：`{"T": [...], "C": [...]}`。

    純建議，**它只是起點**——agent 判斷與這裡不同時以 agent 為準，不必回報。
    """
    s = text or ""
    matrix = _get_matrix()
    r = {"big": None, "mid": None, "sub": None, "text": s}
    t_raw, c_raw, _flags = matrix.tag_tc(r)
    T = [] if list(t_raw) == [matrix.UNKNOWN] else list(t_raw)
    C = [] if list(c_raw) == [matrix.UNKNOWN] else list(c_raw)

    if any(kw in s for kw in MILITARY_T_KW) and "軍事國防" not in T:
        T.append("軍事國防")
    if any(kw in s for kw in UK_C_KW) and "英國" not in C:
        C.append("英國")
    if taiwan_hit(s) and "臺灣" not in C:
        C.append("臺灣")
    if source in SOURCE_DEFAULT_C:
        for c in SOURCE_DEFAULT_C[source]:
            if c not in C:
                C.append(c)
    return {"T": T, "C": C}


def taiwan_hit(text):
    """命中的涉臺詞（見 `TAIWAN_KW`）。空 list＝沒命中。"""
    s = text or ""
    return [kw for kw in TAIWAN_KW if kw in s]


def bite_suggest(sb_count=None, has_sot=None, entry=None):
    """是否建議這則標 `(BITE)`。

    - `True`：有訊號（`sb_count>0`／`has_sot`／entry 已有 `▎BITE：` 段），
      但 entry 還沒標 `(BITE)`——建議補上。
    - `False`：沒有任何訊號。
    - `None`：entry **已經**標了 `(BITE)`——已經決定過，不必再建議
      （這是刻意的設計：`bite_suggest` 只填「還沒決定」的空白，不覆核已決定的）。
    """
    e = entry or ""
    if "(BITE)" in e:
        return None
    return bool(has_sot) or (isinstance(sb_count, int) and sb_count > 0) or "▎BITE：" in e


def _as_tc_dict(tc):
    """把 `tc` 正規化成 `{"T": [...], "C": [...]}`。

    接受兩種形狀：`add-batch` 傳進來的原始 spec 字串（`"T1,T2/C1,C2"`，
    同 `s2_state._set_one_tc()` 的格式）、或呼叫端已經拆好的 dict。
    """
    if isinstance(tc, dict):
        return {"T": list(tc.get("T") or []), "C": list(tc.get("C") or [])}
    if isinstance(tc, str) and "/" in tc:
        tside, cside = tc.split("/", 1)
        return {"T": [x.strip() for x in tside.split(",") if x.strip()],
                "C": [x.strip() for x in cside.split(",") if x.strip()]}
    return {"T": [], "C": []}


def lint(entry, sb_count=None, has_sot=None, footage_type=None, tc=None):
    """對已寫好的素材行做四項機械檢查，只警告不修，回傳訊息 list（可能是空的）。

    四項檢查（前綴分別是）：
      📏 摘要 >150 字
      🎙 `(BITE)` 與 `▎BITE：` 段不一致
      🔖 畫面欄只有受訪／連線類詞卻標了 🔖（R19）
      🌀 機動 T active 且文本命中，但 `tc.T` 沒有掛
    """
    msgs = []
    e = entry or ""
    fields, _why = sp.parse_entry(e)

    # 📏 摘要 >150 字
    summary = fields.get("summary") if fields else None
    if summary and len(summary) > 150:
        msgs.append(f"📏 摘要 {len(summary)} 字，超過 150 字上限（13c2）")

    # 🎙 (BITE) 與 BITE 段不一致——**不能只靠 `parse_entry`**：`(BITE)` 沒配
    # `▎BITE：` 段時 `parse_entry` 本身就會判定失敗回 `None`（"既沒有 無BITE
    # 也沒有 ▎BITE： 段"），那正是這裡要抓的情況，得看原始字串。
    has_bite_note = "(BITE)" in e
    has_bite_seg = "▎BITE：" in e
    no_bite_marked = "無BITE" in e
    if has_bite_note and not has_bite_seg and not no_bite_marked:
        msgs.append("🎙 標了 (BITE) 但沒有 ▎BITE： 段，確認是否漏寫")
    if no_bite_marked and isinstance(sb_count, int) and sb_count > 0:
        msgs.append(f"🎙 稿內有 {sb_count} 個 SOUNDBITE 卻標「無BITE」，確認是否漏寫 ▎BITE： 段")
    ft = str(footage_type or "").strip().upper()
    if no_bite_marked and ft in _FT_MUST_BITE:
        msgs.append(f"🎙 footageType={ft} 通常必有訪問聲音卻標「無BITE」，確認是否漏寫")

    # 🔖 負面：畫面欄只有受訪／連線類詞、沒有實拍內容卻標了 🔖（R19）。
    # ⚠️ 用 `fields.footage`（entry 裡 ▎畫面： 段的內容），不是 `footage_type`
    # （那是 NS 的 footageType 代碼如 SOT/PKG，跟畫面欄文字是兩回事）。
    footage = fields.get("footage") if fields else None
    if footage and "🔖" in e:
        tokens = [t.strip() for t in re.split(r"[、,，]", footage) if t.strip()]
        if tokens and all(any(kw in t for kw in FOOTAGE_NEG_KW) for t in tokens):
            msgs.append("🔖 畫面欄只有「受訪畫面／記者連線」類詞、沒有實拍內容，依 R19 不應標 🔖")

    # 🌀 機動 T active 且文本命中卻沒掛（tc 沒給就跳過，不是每個呼叫端都知道
    # 這一則現在標了什麼 T/C）。
    if tc is not None:
        tcd = _as_tc_dict(tc)
        have_t = set(tcd.get("T") or [])
        for name in _active_special_t():
            if name and name in e and name not in have_t:
                msgs.append(f"🌀 機動 T「{name}」目前 active 且文本命中，tc.T 沒有掛，確認是否漏標")

    return msgs
