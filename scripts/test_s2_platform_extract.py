#!/usr/bin/env python3
"""s2_platform_extract.py 的測試（MASTER A9 子項②）。

`probe_duration_seconds` 需要對公開 CDN 網址跑 ffprobe，測試用假函式替換掉，
不依賴網路（跟真實 ffprobe 的串接已在 2026-08-26 現場查證過：`_id=928358` 讀出
`duration=69.360000`，與瀏覽器 `<video>` 元素一致，見規劃書）。

用法：python scripts/test_s2_platform_extract.py
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ex = load("s2_platform_extract")
results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"　{extra}" if extra and not cond else ""))


# ---------- fmt_mmss ----------
check("fmt_mmss 69.36 秒 -> 01:09", ex.fmt_mmss(69.36) == "01:09", ex.fmt_mmss(69.36))
check("fmt_mmss None -> None", ex.fmt_mmss(None) is None)

# ---------- extract_enex：正常收錄 + 時長 ----------
# 🔴 2026-08-31：fixture 改成 `slimEnex()`（附錄 A-3）**真正的輸出形狀**——
#   `id` **帶 ENEX 前綴**、影片網址在 `url`（videoLowResCdn）、`dl` 是會員下載頁。
#   舊 fixture 用裸 id ＋ 把影片網址放進 `dl`，那是「我們想像的輸入」而不是上游真的
#   會送來的東西，所以 0831 實測抓到的兩個 bug（48 則無聲蒸發、ffprobe 量錯欄位）
#   在舊 fixture 下**測不出來**。⛔ 不要為了讓測試好寫而把形狀改回去。
raw_enex = [
    {"id": "ENEX928358", "title": "t1", "desc": "STORYLINE ...", "partner": "FR BFM",
     "cat": "Crime", "loc": "Paris", "tags": ["A"], "ts": 1,
     "url": "https://cdn/928358.mp4", "dl": "https://members.enex.news/download/928358",
     "estat": "PUBLISHED", "nlid": 2365490},
    {"id": "ENEX928999", "title": "t2", "desc": "TVBS 回流", "partner": "TVBS",
     "url": None, "dl": None, "estat": "PUBLISHED", "nlid": 1},
]
entries_enex = {
    "928358": {"category": {"大分類": "歐洲", "中主題": "測試"}, "sb_count": 0,
               "raw_entry": "ENEX928358 (BFM) …"},
    "928999": {"skip": "own"},
}
items, skipped, dropped, gaps = ex.extract_enex(raw_enex, entries_enex, duration_fn=lambda url: 69.36)
check("enex 收 1 則", len(items) == 1, items)
check("enex id 加前綴", items and items[0]["id"] == "ENEX928358")
check("enex src_text 直接用 desc 原文", items and items[0]["src_text"] == "STORYLINE ...")
check("enex 時長機械算出 01:09", items and items[0]["enex"]["duration"] == "01:09")
check("enex 排除 1 則（TVBS）", len(skipped) == 1 and skipped[0]["id"] == "ENEX928999")
check("enex 沒有 dropped（entries 都有判斷）", not dropped, dropped)
check("enex 沒有 known_gaps（raw_entry／時長都齊）", not gaps, gaps)

# ---------- extract_enex：raw 有但 entries 沒判斷 → dropped，不靜默排除 ----------
raw2 = raw_enex + [{"id": "ENEX930000", "title": "t3", "desc": "x", "url": None, "dl": None}]
items2, skipped2, dropped2, gaps2 = ex.extract_enex(raw2, entries_enex, duration_fn=lambda u: None)
check("enex 未判斷項目進 dropped 不進 items", len(items2) == 1 and len(dropped2) == 1)

# ---------- extract_enex：ffprobe 失敗 → known_gaps 有記錄，不是靜默漏標 ----------
items3, _, _, gaps3 = ex.extract_enex(raw_enex[:1], entries_enex, duration_fn=lambda u: None)
check("enex ffprobe 失敗記進 known_gaps", any("時長抓不到" in g for g in gaps3), gaps3)
check("enex ffprobe 失敗時 duration 為 None", items3[0]["enex"]["duration"] is None)

# ---------- extract_enex：raw_entry 沒填 → known_gaps 提醒，但仍收錄（機械欄位優先） ----------
entries_no_raw = {"928358": {"category": {"大分類": "歐洲"}, "sb_count": 0}}
items4, _, _, gaps4 = ex.extract_enex(raw_enex[:1], entries_no_raw, duration_fn=lambda u: 69.36)
check("缺 raw_entry 記進 known_gaps", any("raw_entry" in g for g in gaps4), gaps4)
check("缺 raw_entry 仍收錄（讓 lint 去擋，不在這裡靜默丟）", len(items4) == 1)

# ---------- extract_abc：正常收錄 + Story Number 格式檢查 ----------
raw_abc = [
    {"DeliveryAvailableDateTime": "8/26/2026 6:30:22 PM", "News Story": "082601",
     "Slug": "TestSlug", "Length": "01:30", "DestinationName": "TVBS News"},
    {"DeliveryAvailableDateTime": "8/26/2026 5:00:00 PM", "News Story": "bad-id",
     "Slug": "BadSlug", "Length": ":45", "DestinationName": "TVBS News"},
]
entries_abc = {
    "082601": {"category": {"大分類": "美國"}, "sb_count": 2,
               "src_text": "x" * 60, "raw_entry": "ABC082601 (ABC) …", "detailId": "1"},
    "bad-id": {"category": {}, "src_text": "y" * 60, "raw_entry": "ABC…"},
}
items_a, skipped_a, dropped_a, gaps_a = ex.extract_abc(raw_abc, entries_abc)
check("abc 收 2 則", len(items_a) == 2, items_a)
check("abc id 加前綴", any(i["id"] == "ABC082601" for i in items_a))
check("abc Length 原樣沿用", next(i for i in items_a if i["id"] == "ABC082601")["abc"]["duration"] == "01:30")
check("abc 不合法 Story Number 記進 known_gaps 但仍收錄", any("MMDDYY" in g for g in gaps_a), gaps_a)

# ---------- extract_abc：entries 鍵帶 ABC 前綴也認得（2026-09-04，V7 準備） ----------
# 🔴 這條擋的是「無聲蒸發」：只認裸鍵時，agent 比照 ENEX 文件寫 ABC 前綴 →
#    全數 dropped、候選檔空的，而 extract 與 lint 的離開碼都是 0。
entries_abc_pref = {
    "ABC082601": {"category": {}, "sb_count": 0, "src_text": "z" * 60,
                  "raw_entry": "ABC082601 (ABC) …"},
}
items_p, _, dropped_p, _ = ex.extract_abc(raw_abc[:1], entries_abc_pref)
check("abc entries 鍵帶前綴也認得", len(items_p) == 1 and not dropped_p, (items_p, dropped_p))

# ---------- extract_abc：Length 自動補成素材行行尾 ▎MM:SS ----------
items_d, _, _, _ = ex.extract_abc(
    [{"News Story": "082601", "Slug": "s", "Length": "01:30"}],
    {"082601": {"category": {}, "sb_count": 0, "src_text": "z" * 60,
                "raw_entry": "ABC082601 (ABC) ▎摘要▎畫面：…"}})
check("abc 時長自動補進素材行", items_d[0]["raw_entry"].endswith("▎01:30"), items_d[0]["raw_entry"])

items_h, _, _, _ = ex.extract_abc(
    [{"News Story": "082601", "Slug": "s", "Length": "00:05:00"}],
    {"082601": {"category": {}, "sb_count": 0, "src_text": "z" * 60,
                "raw_entry": "ABC082601 (ABC) ▎摘要"}})
check("abc HH:MM:SS 正規化成 MM:SS", items_h[0]["raw_entry"].endswith("▎05:00"),
      items_h[0]["raw_entry"])

items_e, _, _, _ = ex.extract_abc(
    [{"News Story": "082601", "Slug": "s", "Length": "01:30"}],
    {"082601": {"category": {}, "sb_count": 0, "src_text": "z" * 60,
                "raw_entry": "ABC082601 (ABC) ▎摘要▎02:00"}})
check("abc 已有時長就不覆蓋", items_e[0]["raw_entry"].endswith("▎02:00"), items_e[0]["raw_entry"])

items_f, _, _, gaps_f = ex.extract_abc(
    [{"News Story": "082601", "Slug": "s", "Length": "亂七八糟"}],
    {"082601": {"category": {}, "sb_count": 0, "src_text": "z" * 60,
                "raw_entry": "ABC082601 (ABC) ▎摘要"}})
check("abc Length 格式不對記 known_gaps、不亂補",
      items_f[0]["raw_entry"].endswith("▎摘要") and any("Length" in g for g in gaps_f), gaps_f)

# ---------- extract_abc：缺 src_text → known_gaps，不是靜默放行 ----------
entries_abc_missing = {"082601": {"category": {}, "raw_entry": "x"}}
items_b, _, _, gaps_b = ex.extract_abc(raw_abc[:1], entries_abc_missing)
check("abc 缺 src_text 記進 known_gaps", any("src_text" in g for g in gaps_b), gaps_b)

# ---------- CLI 端到端：--out 寫出合法候選檔（含 checkpoint 灌回每筆） ----------
import subprocess
import tempfile

TMP = tempfile.mkdtemp(prefix="s2_extract_test_")
raw_path = os.path.join(TMP, "raw.json")
entries_path = os.path.join(TMP, "entries.json")
out_path = os.path.join(TMP, "out.json")
with open(raw_path, "w", encoding="utf-8") as f:
    json.dump(raw_enex[:1], f)
with open(entries_path, "w", encoding="utf-8") as f:
    json.dump(entries_enex, f)

rc = subprocess.run(
    [sys.executable, os.path.join(HERE, "s2_platform_extract.py"), "enex",
     "--raw", raw_path, "--entries", entries_path, "--checkpoint", "0826-1600",
     "--window-start", "2026-08-26 13:00", "--window-end", "2026-08-26 16:00",
     "--out", out_path],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
)
check("CLI 端到端 exit 0", rc.returncode == 0, rc.stderr)
with open(out_path, encoding="utf-8") as f:
    doc = json.load(f)
check("CLI 輸出候選檔含正確 checkpoint 頂層欄位", doc["checkpoint"] == "0826-1600")
check("CLI 輸出每筆 first_seen_checkpoint 有灌回",
      all(i["first_seen_checkpoint"] == "0826-1600" for i in doc["items"]))
check("CLI 輸出 counts 正確（掃描＝收錄＋排除＋漏判）",
      doc["counts"] == {"掃描": 1, "收錄": 1, "排除": 0, "漏判": 0}, doc["counts"])

import shutil

# ── 0831 真實資料實測抓到的 bug，全部釘成迴歸測試 ───────────────────────
# ⚠️ 這幾組是「48 則真實素材打臉」換來的，⛔ 不要因為看起來瑣碎就刪。

check("bare_enex_id 剝前綴", ex.bare_enex_id("ENEX929038") == "929038")
check("bare_enex_id 裸 id 原樣", ex.bare_enex_id("929038") == "929038")

_raw1 = [{"id": "ENEX928358", "title": "t", "desc": "d", "url": "u", "estat": "PUBLISHED"}]
_ent1 = {"928358": {"category": {"大分類": "歐洲"}, "sb_count": 0,
                    "raw_entry": "ENEX928358 (X) …"}}
i1, _, d1, _ = ex.extract_enex(_raw1, _ent1, duration_fn=lambda u: 10.0)
check("BUG-1：raw 帶前綴＋entries 裸鍵 → 收得到（不是 48 則全蒸發）",
      len(i1) == 1 and not d1 and i1[0]["id"] == "ENEX928358",
      f"items={len(i1)} dropped={len(d1)}")

i2, _, _, _ = ex.extract_enex(
    _raw1, {"ENEX928358": _ent1["928358"]}, duration_fn=lambda u: 10.0)
check("BUG-1：entries 用帶前綴的鍵也認，且 id 不會變成 ENEXENEX…",
      len(i2) == 1 and i2[0]["id"] == "ENEX928358", i2[0]["id"] if i2 else "無")

_probed = []
ex.extract_enex(
    [{"id": "ENEX1", "title": "t", "desc": "d", "estat": "PUBLISHED",
      "url": "https://cdn/ok.mp4", "dl": "https://members.enex.news/download/1"}],
    {"1": {"category": {"大分類": "歐洲"}, "sb_count": 0, "raw_entry": "ENEX1 (X) …"}},
    duration_fn=lambda u: (_probed.append(u), 10.0)[1])
check("BUG-2：ffprobe 量的是 url（CDN）不是 dl（會員下載頁）",
      _probed == ["https://cdn/ok.mp4"], _probed)

_, _, _, gpub = ex.extract_enex(
    [{"id": "ENEX2", "title": "t", "desc": "d", "estat": "PUBLISHING NOW", "url": None}],
    {"2": {"category": {"大分類": "歐洲"}, "sb_count": 0, "raw_entry": "ENEX2 (X) …"}},
    duration_fn=lambda u: None)
check("尚未上架（PUBLISHING NOW）不要報成 ffprobe 失敗",
      any("尚未上架" in x for x in gpub), gpub)

check("SRC_TEXT_MAX 容得下實測最長 5,634 字元", ex.SRC_TEXT_MAX >= 5634, ex.SRC_TEXT_MAX)
_long = "A" * 5634
i3, _, _, _ = ex.extract_enex(
    [{"id": "ENEX3", "title": "t", "desc": _long, "estat": "PUBLISHED", "url": "u"}],
    {"3": {"category": {"大分類": "歐洲"}, "sb_count": 0, "raw_entry": "ENEX3 (X) …"}},
    duration_fn=lambda u: 10.0)
check("5,634 字元 desc 不再被截斷（SOUNDBITE 在最後面，切掉＝毀掉查證依據）",
      i3 and i3[0]["src_text"] == _long, len(i3[0]["src_text"]) if i3 else "無")


# ── 併發量時長（2026-09-01）─────────────────────────────────────────────
import threading as _th
_seen, _lock = [], _th.Lock()
def _slow(u):
    import time; time.sleep(0.05)
    with _lock: _seen.append(u)
    return 12.0
_raw_many = [{"id": f"ENEX90{i:04d}", "title": "t", "desc": "d",
              "estat": "PUBLISHED", "url": f"https://cdn/{i}.mp4"} for i in range(16)]
_ent_many = {f"90{i:04d}": {"category": {"大分類": "歐洲"}, "sb_count": 0,
                            "raw_entry": f"ENEX90{i:04d} (X) …"} for i in range(16)}
import time as _t
_t0 = _t.time(); _im, _, _, _ = ex.extract_enex(_raw_many, _ent_many, duration_fn=_slow, workers=8)
_par = _t.time() - _t0
_seen.clear()
_t0 = _t.time(); _is, _, _, _ = ex.extract_enex(_raw_many, _ent_many, duration_fn=_slow, workers=1)
_seq = _t.time() - _t0
check("併發：16 則都量到、結果與序列一致",
      len(_im) == 16 == len(_is)
      and all(i["enex"]["duration"] == "00:12" for i in _im),
      f"併發{len(_im)} 序列{len(_is)}")
check("併發真的比序列快（16 則 × 0.05s）", _par < _seq / 2,
      f"併發 {_par:.2f}s vs 序列 {_seq:.2f}s")

_probed2 = []
ex.extract_enex(
    [{"id": "ENEX7001", "title": "t", "desc": "d", "estat": "PUBLISHED", "url": "u1"},
     {"id": "ENEX7002", "title": "t", "desc": "d", "estat": "PUBLISHED", "url": "u2"}],
    {"7001": {"category": {"大分類": "歐"}, "sb_count": 0, "raw_entry": "ENEX7001 (X) …"},
     "7002": {"skip": "own"}},
    duration_fn=lambda u: (_probed2.append(u), 5.0)[1], workers=4)
check("被 skip 的素材不浪費一次 ffprobe 往返", _probed2 == ["u1"], _probed2)

def _boom(u):
    raise RuntimeError("ffprobe 炸了")
_ib, _, _, _gb = ex.extract_enex(
    [{"id": "ENEX7003", "title": "t", "desc": "d", "estat": "PUBLISHED", "url": "u"}],
    {"7003": {"category": {"大分類": "歐"}, "sb_count": 0, "raw_entry": "ENEX7003 (X) …"}},
    duration_fn=_boom, workers=4)
check("量時長丟例外不會弄死整支腳本（記進 known_gaps 就好）",
      len(_ib) == 1 and _ib[0]["enex"]["duration"] is None and _gb, _gb)

check("--probe-workers 有掛進 CLI",
      "--probe-workers" in open(os.path.join(HERE, "s2_platform_extract.py"),
                                encoding="utf-8").read())


# ── dropped 一定要進候選檔＋算進掃描（2026-09-01，獨立複查抓到）──────────
_rawd = [{"id": "ENEX940001", "title": "t", "desc": "d", "url": "u", "estat": "PUBLISHED"},
         {"id": "ENEX940002", "title": "t", "desc": "d", "url": "u", "estat": "PUBLISHED"}]
_id_, _sk, _dp, _ = ex.extract_enex(_rawd, {"完全對不上": {}}, duration_fn=lambda u: 1.0)
_c = ex.build_counts(len(_id_), len(_sk), len(_dp))
check("整批對不上 → 全進 dropped", len(_id_) == 0 and len(_dp) == 2, f"{len(_id_)}/{len(_dp)}")
check("掃描要算進漏判（否則跟『站方沒素材』分不出來）",
      _c == {"掃描": 2, "收錄": 0, "排除": 0, "漏判": 2}, _c)

# entries 的 falsy 佔位值：前迴圈與主迴圈必須選到同一筆（共用 lookup_entry）
check("lookup_entry 裸鍵優先", ex.lookup_entry({"1": {"a": 1}, "ENEX1": {"a": 2}}, "1") == {"a": 1})
check("lookup_entry 裸鍵不存在才用前綴鍵",
      ex.lookup_entry({"ENEX1": {"a": 2}}, "1") == {"a": 2})
check("lookup_entry：裸鍵是 falsy 的 {} 也算存在，不 fallback（前後迴圈才會一致）",
      ex.lookup_entry({"1": {}, "ENEX1": {"a": 2}}, "1") == {})


# ── 時長要補進素材行行尾（2026-09-01，0901-1700 首輪四站實錯）─────────────
check("with_duration：量到就補 ▎MM:SS",
      ex.with_duration("ENEX1 (X) ▎摘要▎畫面：…▎無BITE。", "00:27")
      == "ENEX1 (X) ▎摘要▎畫面：…▎無BITE。▎00:27")
check("with_duration：agent 自己寫了就不覆蓋",
      ex.with_duration("ENEX1 (X) ▎摘要▎無BITE。▎03:12", "00:27")
      == "ENEX1 (X) ▎摘要▎無BITE。▎03:12")
check("with_duration：量不到就留白，⛔ 不補佔位",
      ex.with_duration("ENEX1 (X) ▎摘要▎無BITE。", None)
      == "ENEX1 (X) ▎摘要▎無BITE。")
check("with_duration：raw_entry 空著不動（lint 會擋，這支不代寫）",
      ex.with_duration("", "00:27") == "")
check("with_duration：HH:MM:SS 也算已有時長",
      ex.with_duration("ENEX1 (X) ▎摘要▎01:02:03", "00:27")
      == "ENEX1 (X) ▎摘要▎01:02:03")

_iw, _sw, _dw, _gw = ex.extract_enex(
    [{"id": "ENEX7100", "title": "t", "desc": "d", "url": "u", "estat": "PUBLISHED"}],
    {"7100": {"category": {"大分類": "歐"}, "sb_count": 0,
              "raw_entry": "ENEX7100 (X) ▎摘要▎畫面：…▎無BITE。"}},
    duration_fn=lambda u: 27.0)
check("extract_enex：量到的時長真的落在 raw_entry 行尾（不是只存進子物件）",
      _iw[0]["raw_entry"].endswith("▎00:27") and _iw[0]["enex"]["duration"] == "00:27",
      _iw[0]["raw_entry"][-20:])


# ── --raw 元素不是物件：記進 dropped，不要吐 AttributeError（0901-2000 實錯）──
_ir, _sr, _dr, _gr = ex.extract_enex(
    ["這是字串不是物件",
     {"id": "ENEX7200", "title": "t", "desc": "d", "url": "u", "estat": "PUBLISHED"}],
    {"7200": {"category": {"大分類": "歐"}, "sb_count": 0,
              "raw_entry": "ENEX7200 (X) ▎摘要▎畫面：…▎無BITE。"}},
    duration_fn=lambda u: 12.0)
check("--raw 混進字串不會整支掛掉（原本 AttributeError: 'str' has no attribute 'get'）",
      len(_ir) == 1 and len(_dr) == 1, f"收{len(_ir)} 漏判{len(_dr)}")
check("非物件那筆要指名第幾筆＋實得型別（不要靜默跳過）",
      _dr[0]["id"] == "第1筆" and "str" in _dr[0]["why"], str(_dr[0]))
check("非物件不影響同批正常那筆（含時長）",
      _ir[0]["raw_entry"].endswith("▎00:12"), _ir[0]["raw_entry"][-12:])

_ia, _sa, _da, _ga = ex.extract_abc(
    [None, {"News Story": "080926021", "Slug": "s", "Length": "05:00"}],
    {"080926021": {"category": {"大分類": "美國"}, "sb_count": 0,
                   "raw_entry": "ABC080926021 (ABC) ▎摘要▎畫面：…▎無BITE。▎05:00",
                   "src_text": "x"}})
check("ABC 也有同一道護欄", len(_da) == 1 and _da[0]["id"] == "第1筆", str(_da))


# ── --raw 包一層要自動解包（0901-2000 掛掉的真正原因）──────────────────
check("raw_list：{total,count,items:[…]} 自動拆 items",
      ex.raw_list({"total": 9, "count": 3, "items": [{"id": "a"}]}) == [{"id": "a"}])
check("raw_list：陣列原樣回傳", ex.raw_list([{"id": "a"}]) == [{"id": "a"}])
check("raw_list：hits／rows／results 也認",
      ex.raw_list({"hits": [1]}) == [1] and ex.raw_list({"rows": [2]}) == [2]
      and ex.raw_list({"results": [3]}) == [3])
check("raw_list：不認識的物件原樣回傳（交給下游的非物件護欄）",
      ex.raw_list({"foo": 1}) == {"foo": 1})

# ── category 兩種寫法 ─────────────────────────────────────────────
check("norm_category：字串照 / 拆三層",
      ex.norm_category("烏俄/國際外交/莫迪籲普欽止戰")
      == {"大分類": "烏俄", "中主題": "國際外交", "小分題": "莫迪籲普欽止戰"})
check("norm_category：只有兩層也行", ex.norm_category("社會/車禍")
      == {"大分類": "社會", "中主題": "車禍"})
check("norm_category：物件原樣", ex.norm_category({"大分類": "美國"}) == {"大分類": "美國"})
check("norm_category：None／空字串 → {}",
      ex.norm_category(None) == {} and ex.norm_category("  ") == {})

# ── entries 形狀預檢 ──────────────────────────────────────────────
GOOD = {"929213": {"category": {"大分類": "烏俄", "中主題": "外交"}, "sb_count": 1,
                   "raw_entry": "ENEX929213 (X) ▎摘要▎畫面：…▎無BITE。"},
        "929181": {"skip": "自家素材"}}
check("預檢：正常的 entries 沒問題", ex.check_entries(GOOD) == [], str(ex.check_entries(GOOD)))

_b = dict(GOOD); _b["929213"] = dict(GOOD["929213"], category="烏俄/外交")
check("預檢：category 字串是合法寫法，不報錯", ex.check_entries(_b) == [])

_b = dict(GOOD); _b["929213"] = dict(GOOD["929213"],
                                     raw_entry="🟡 ENEX929213 (X) ▎摘要▎無BITE。")
check("預檢：🟡／🔴／🔖 開頭合法（0901-2000 被 lint 誤判的那 4 則）",
      ex.check_entries(_b) == [], str(ex.check_entries(_b)))

_b = dict(GOOD); _b["929213"] = dict(GOOD["929213"],
                                     raw_entry="△ ENEX929213 (X) ▎摘要▎無BITE。")
check("預檢：時段標記 △ 要擋（render 會再補一個）",
      any("時段標記" in p for p in ex.check_entries(_b)), str(ex.check_entries(_b)))

_b = dict(GOOD); _b["929213"] = dict(GOOD["929213"], sb_count="1")
check("預檢：sb_count 字串要擋", any("sb_count" in p for p in ex.check_entries(_b)))

_b = dict(GOOD); _b["929213"] = dict(GOOD["929213"], category={"大分類": "烏俄"})
check("預檢：category 缺中主題要擋", any("中主題" in p for p in ex.check_entries(_b)))

_b = dict(GOOD); _b["929213"] = dict(GOOD["929213"],
                                     raw_entry="ENEX929999 (X) ▎摘要▎無BITE。")
check("預檢：行首代碼與鍵值不符要擋", any("不符" in p for p in ex.check_entries(_b)))

check("預檢：整包不是物件時直接點名", len(ex.check_entries([1, 2])) == 1)
_b = dict(GOOD); _b["929213"] = dict(GOOD["929213"])
_b["929213"].pop("raw_entry")
check("預檢：raw_entry 沒填不在預檢範圍（既有設計：記 known_gaps，lint 才擋）",
      ex.check_entries(_b) == [], str(ex.check_entries(_b)))

check("check-entries 有掛進 CLI",
      "check-entries" in open(os.path.join(HERE, "s2_platform_extract.py"),
                              encoding="utf-8").read())

shutil.rmtree(TMP, ignore_errors=True)

print(f"\nPASS={sum(results)} FAIL={len(results) - sum(results)}")
sys.exit(0 if all(results) else 1)
