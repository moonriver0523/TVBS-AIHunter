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
    "Taiwan Strait", "Taiwanese",  # D18（2026-09-07）：只加不改
]

# D15：T 新增「軍事國防」。只加不改；字典本身這次不動，改字典見 D15。
MILITARY_T_KW = [
    "國防", "軍演", "軍事演習", "演習", "漢光", "飛彈", "導彈", "軍艦", "軍機",
    "徵兵", "軍售", "國防部長", "核潛艦", "航艦",
    "defense ministry", "military drill", "missile", "warship",
]

# D15：C 歐洲拆出「英國」。只加不改；字典本身這次不動，改字典見 D15。
# D18（2026-09-07）：拿掉裸字 "UK"——這裡是純子字串比對（`kw in s`），"UK"
# 會誤中 "UKRAINIAN"（實測 AP4682773 烏克蘭快訊被誤掛英國才抓到）。真的
# "UK" 詞邊界比對交給 `EN_C_ALIASES["英國"]`（見下）就夠，這裡不用裸字版。
UK_C_KW = [
    "英國", "倫敦", "唐寧街", "英相", "白金漢宮",
    "Britain", "London", "Downing Street",
]

# ── D18（2026-09-07 已裁決）英文別名層：只加不改，改字典見 D15 ─────────
# AP／RT／NS 站方原文（head＋first150）以英文為主，TC-字典.md 的中文關鍵詞
# 在英文稿上幾乎打不中。這裡替現行 12 個 T、22 個 C 類別（`s2_state._load_tc_dict()`
# 讀回的名單）各補一組英文別名，讓 `suggest_tc()` 對英文原文也能命中；
# 完全不新增／更動類別名稱本身，也不碰 TC-字典.md（同 D15 的分工）。
#
# 專項獨佔規則（英國不掛歐洲、以色列／伊朗不掛中東）跟
# `build_tc_matrix_0821.py::tag_tc()` 一致：作法是讓中東的別名跟以色列／
# 伊朗的別名彼此不重疊（兩邊詞表本來就沒有交集），英國／歐洲則額外在
# `suggest_tc()` 最後補一次 `discard`，跟 `tag_tc()` 329 行同款寫法。
#
# 比對規則：大小寫不敏感、詞邊界（`\b`），避免「us」這種英文常用詞在縮寫
# 情境下（如 "US"）誤觸——採詞邊界後風險已大幅降低，仍請人工抽查誤標。
EN_T_ALIASES = {
    "烏俄": ["Ukraine", "Ukrainian", "Kyiv", "Zelensky", "Zelenskyy"],
    "美伊": ["Iran nuclear", "Iran sanctions", "Tehran strike", "IRGC"],
    "地緣衝突": ["Gaza strike", "Hamas", "Hezbollah", "West Bank"],
    "軍事國防": ["military drill", "military parade", "arms sale", "defense budget"],
    "天災天氣": ["typhoon", "earthquake", "flood", "wildfire", "mudslide", "landslide"],
    "政治": ["election", "parliament", "summit", "prime minister",
             "gubernatorial", "cabinet secretary", "energy secretary"],
    "社會": ["shooting", "stabbing", "manhunt", "homicide", "building collapse"],
    "財經": ["tariff", "inflation", "interest rate", "trade deal"],
    "科技醫藥": ["AI chip", "vaccine", "clinical trial", "space launch", "outbreak", "Ebola"],
    "娛樂藝文": ["box office", "Hollywood", "film festival", "Grammy", "actor"],
    "體育": ["World Cup", "Olympics", "championship", "Grand Slam"],
    "話題": ["viral video", "internet sensation", "record holder", "rare sighting"],
}

EN_C_ALIASES = {
    "臺灣": ["Taiwan", "Taiwanese", "Taipei", "Taiwan Strait", "TSMC"],
    "中國大陸": ["China", "Chinese", "Beijing", "Hong Kong", "Jiangxi", "Tibet", "Xizang"],
    "美國": ["United States", "US", "American", "Washington", "White House",
             # 對齊 build_tc_matrix_0821.py::tag_tc() 既有中文美國關鍵詞的英文版
             # （德州/夏威夷/紐約/西雅圖/奧馬哈），不是另開新範圍。
             "Texas", "Dallas", "Hawaii", "New York", "Seattle", "Omaha"],
    "加拿大": ["Canada", "Canadian", "Ottawa", "Toronto"],
    "日本": ["Japan", "Japanese", "Tokyo", "Osaka"],
    "南韓": ["South Korea", "South Korean", "Seoul", "Yoon"],
    "北韓": ["North Korea", "North Korean", "Pyongyang", "Kim Jong Un"],
    "泰國": ["Thailand", "Thai", "Bangkok", "baht"],
    "新加坡": ["Singapore", "Singaporean", "Changi", "Marina Bay"],
    "東南亞": ["Southeast Asia", "ASEAN", "Vietnam", "Philippines"],
    "南亞": ["South Asia", "India", "Indian", "Pakistan", "Bangladesh", "Nepal"],
    "以色列": ["Israel", "Israeli", "IDF", "Gaza", "Hamas"],
    "伊朗": ["Iran", "Iranian", "Tehran", "IRGC"],
    "中東": ["Middle East", "Lebanon", "Yemen", "Syria", "Hormuz"],
    "烏克蘭": ["Ukraine", "Ukrainian", "Kyiv", "Zelensky", "Zelenskyy"],
    "俄羅斯": ["Russia", "Russian", "Moscow", "Putin"],
    "英國": ["UK", "United Kingdom", "Britain", "British", "London", "Starmer"],
    "歐洲": ["Europe", "European Union", "EU", "Brussels", "NATO", "Germany", "France"],
    "非洲": ["Africa", "African", "Nigeria", "Kenya", "Congo"],
    "中南美": ["Latin America", "Mexico", "Mexican", "Colombia"],
    "紐澳": ["Australia", "Australian", "New Zealand", "Sydney"],
    "國際": ["United Nations", "WHO", "global summit", "APEC"],
}


def _compile_alias_map(alias_map):
    """把 `{類別: [英文別名,...]}` 編成 `{類別: 已編譯 regex}`（大小寫不敏感、詞邊界）。

    每個別名尾巴補一個可選的 `s?`（複數／單複數變化），這樣「flood」也會命中
    「floods」——0907 實測 RT0675（Nepal floods）就是卡在這裡沒補上 `s`。
    """
    compiled = {}
    for name, words in alias_map.items():
        pattern = "|".join(re.escape(w) for w in words)
        compiled[name] = re.compile(r"\b(?:" + pattern + r")s?\b", re.IGNORECASE)
    return compiled


_EN_T_PATTERNS = _compile_alias_map(EN_T_ALIASES)
_EN_C_PATTERNS = _compile_alias_map(EN_C_ALIASES)


def _en_alias_hits(patterns, text):
    """命中的類別名 list（可能是空的）。`text` 為空字串一律不命中。"""
    if not text:
        return []
    return [name for name, pat in patterns.items() if pat.search(text)]


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

# NS PKG 的引言可能直接嵌在敘事段落中，不一定有 `--SOT--` 區塊標題。
# 只把「講者名＋SOT＋引號」及「SOT＋講者名＋引號」視為 inline 訊號；
# 單獨出現的 SOT／SOT package 不算。SUPERS 區段的人名也不算，避免把畫面字卡
# 誤當成訪問。這組正規表示式刻意只負責找「訊號」，不擷取或改寫引言內容。
# 上限避免把一整段沒有空白的正文當成「講者名」回溯到全文開頭。
_NAME_TOKEN = r"[A-Za-z][A-Za-z0-9.'/-]{0,79}"
_INLINE_SOT_RE = re.compile(
    rf"(?:\b{_NAME_TOKEN}(?:\s*/\s*{_NAME_TOKEN})?"
    rf"(?:\s+{_NAME_TOKEN}){{0,2}}\s+SOT\b\s*:?\s*[\"'“‘]"
    rf"|\bSOT\s+{_NAME_TOKEN}(?:\s+{_NAME_TOKEN})?"
    rf"\s*:?\s*[\"'“‘])",
    re.IGNORECASE,
)
_SECTION_HEADER_RE = re.compile(
    r"(?im)^[ \t]*--(?P<name>[A-Z][A-Z0-9 /-]*)--[ \t]*(?:\r?\n|$)"
)

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


def _visible_inline_sot_spans(src_text):
    """回傳非 `--SUPERS--` 區段內 inline SOT 候選的原文 span。"""
    if not isinstance(src_text, str) or not src_text:
        return []

    spans = []
    cursor = 0
    skipping_supers = False
    for header in _SECTION_HEADER_RE.finditer(src_text):
        name = header.group("name").strip().upper()
        if not skipping_supers:
            for match in _INLINE_SOT_RE.finditer(src_text[cursor:header.start()]):
                spans.append((cursor + match.start(), cursor + match.end()))
            cursor = header.end()
            skipping_supers = name == "SUPERS"
            continue

        # SUPERS 區段可能以 --END SUPERS-- 結束，也可能直接接下一個區段。
        if name in {"SUPERS", "END SUPERS"}:
            cursor = header.end()
            continue
        skipping_supers = False
        cursor = header.start()

    if not skipping_supers:
        for match in _INLINE_SOT_RE.finditer(src_text[cursor:]):
            spans.append((cursor + match.start(), cursor + match.end()))
    return spans


def inline_sot_count(src_text):
    """計算全文中的具名 inline SOT 訊號；純函式，空值或非字串回 0。"""
    return len(_visible_inline_sot_spans(src_text))


def inline_sot_examples(src_text, limit=3):
    """回傳少量 inline SOT 標記樣本，供提示／稽核顯示，不改原文。"""
    if limit <= 0:
        return []
    return [src_text[start:end] for start, end in _visible_inline_sot_spans(src_text)[:limit]]


def inline_sot_anchor(src_text):
    """回傳第一個 inline SOT 在原文中的位置，供 `truncate()` 保留尾段。"""
    spans = _visible_inline_sot_spans(src_text)
    return spans[0][0] if spans else None


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

    # D18：英文別名層——AP／RT／NS 英文原文靠這裡補建議，只加不重複。
    for name in _en_alias_hits(_EN_T_PATTERNS, s):
        if name not in T:
            T.append(name)
    for name in _en_alias_hits(_EN_C_PATTERNS, s):
        if name not in C:
            C.append(name)
    # 英國專項獨佔，跟 tag_tc() 329 行同款：掛了英國就不留歐洲。
    if "英國" in C and "歐洲" in C:
        C.remove("歐洲")

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


def _duration_seconds(duration_ms):
    """把 `duration_ms`（NS 正式欄位）轉成秒；也接受既有 MM:SS 形狀。"""
    if isinstance(duration_ms, bool) or duration_ms is None:
        return None
    if isinstance(duration_ms, (int, float)):
        return float(duration_ms) / 1000

    value = str(duration_ms).strip()
    if not value:
        return None
    if ":" in value:
        parts = value.split(":")
        try:
            if len(parts) == 2:
                minutes, seconds = map(float, parts)
                if minutes < 0 or not 0 <= seconds < 60:
                    return None
                return minutes * 60 + seconds
            if len(parts) == 3:
                hours, minutes, seconds = map(float, parts)
                if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
                    return None
                return hours * 3600 + minutes * 60 + seconds
        except ValueError:
            return None
        return None
    try:
        return float(value) / 1000
    except ValueError:
        return None


def _first_bracket_has_sot(entry):
    """判斷素材行第一個括號是否含 SOT 標記。"""
    match = re.search(r"\(([^()\r\n]*)\)", entry or "")
    return bool(match and re.search(r"SOT", match.group(1), re.IGNORECASE))


def pkg_donut_needs_sot(footage_type, duration_ms):
    """R42／13e:406-415 判準抽成公用函式（2026-09-18，R43方向2機械化修法）：
    NS 的 PKG／DONUT 且時長 >1 分鐘時，第一備註應標 SOT。

    `lint()`（草稿寫完後才驗）與 `s2_batch_prep.cmd_from_raw()`（草稿寫之前
    先在提示表機械標記提醒）兩處都要用**同一個**判準，不能各自重寫一份
    ——否則兩處門檻漂移（例如一個用 `>60`、一個用 `>=60`）會讓「提示表沒警示
    但硬閘擋下」這種自相矛盾的情況發生，比完全沒有提示更誤導人。
    只回傳布林值，不含「有沒有標 SOT」的檢查（那要有 entry 文字才判得出來，
    `lint()` 自己接著呼叫 `_first_bracket_has_sot()`）。"""
    ft = str(footage_type or "").strip().upper()
    return ft in {"PKG", "DONUT"} and (_duration_seconds(duration_ms) or 0) > 60


def lint(entry, sb_count=None, has_sot=None, footage_type=None, tc=None,
         duration_ms=None, src_text=None, source=None):
    """對已寫好的素材行做機械檢查，只警告不修，回傳訊息 list（可能是空的）。

    四項檢查（前綴分別是）：
      📏 摘要 >150 字
      🎙 `(BITE)` 與 `▎BITE：` 段不一致
      🔖 畫面欄只有受訪／連線類詞卻標了 🔖（R19）
      🌀 機動 T active 且文本命中，但 `tc.T` 沒有掛
      NS inline SOT／PKG-DONUT 長片第一備註漏標（R41／R42）
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
    inline_count = inline_sot_count(src_text)
    if no_bite_marked and inline_count > 0:
        msgs.append(f"🎙 全文掃到 {inline_count} 段 inline SOT 卻標「無BITE」，確認是否漏寫 ▎BITE： 段")
    ft = str(footage_type or "").strip().upper()
    if no_bite_marked and ft in _FT_MUST_BITE:
        msgs.append(f"🎙 footageType={ft} 通常必有訪問聲音卻標「無BITE」，確認是否漏寫")

    # R42：NS PKG／DONUT 超過 1 分鐘時，第一個備註括號應標 SOT。
    # 只警告、不改 entry；source 明確帶入後，AP／RT 不會套用這條白名單。
    if (str(source or "").strip().upper() == "NS"
            and pkg_donut_needs_sot(footage_type, duration_ms)
            and not _first_bracket_has_sot(e)):
        msgs.append("🎙 PKG/DONUT且時長>1分鐘，依13e:406-415規則備註應標SOT卻沒標")

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
