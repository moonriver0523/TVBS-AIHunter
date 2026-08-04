# -*- coding: utf-8 -*-
"""raw_entry → 結構化欄位的解析迴歸。

重點不只是「拆得出來」，還有 **不准擋入庫**（解析失敗只標 parse_ok:false）
與 **不准動 raw_entry**（render 仍吃原字串，欄位只是附加）。

用法：python test_s2_parse.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_parse as sp  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

ok = True


def report(name, passed, detail=""):
    global ok
    ok = ok and passed
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


# ── 標準格式 ─────────────────────────────────────────────────────────
STD = ("△ 🔴 🟤 AP4676497 (斯波坎縱火逮嫌 限斯波坎市場) (BITE) ▎警長宣布37歲男子被捕。"
       "▎畫面：燒毀社區、警長簡報。▎BITE：警長諾威爾斯「下午5點執行拘票」。▎01:34")
f, why = sp.parse_entry(STD)
report("標準格式解析成功", f is not None, why or "")
if f:
    report("代碼", f["codes"] == ["AP4676497"], f["codes"])
    report("備註拆成陣列", f["notes"] == ["斯波坎縱火逮嫌 限斯波坎市場", "BITE"], f["notes"])
    report("摘要", f["summary"] == "警長宣布37歲男子被捕。", f["summary"])
    report("畫面", f["footage"] == "燒毀社區、警長簡報。", f["footage"])
    report("BITE 為陣列", f["bite"] == ["警長諾威爾斯「下午5點執行拘票」。"], f["bite"])
    report("時長", f["duration"] == "01:34", f["duration"])
    report("no_bite 為 False", f["no_bite"] is False)
    report("前綴標記（△🔴🟤）不進任何欄位",
           all("🔴" not in str(v) and "🟤" not in str(v) and "△" not in str(v)
               for v in f.values()))

# ── 無BITE ───────────────────────────────────────────────────────────
f, _ = sp.parse_entry("△ RT2995 (資料畫面) ▎日本防衛白皮書。▎畫面：自衛隊演習。▎無BITE。▎04:54")
report("無BITE：no_bite=True 且 bite 為空", f and f["no_bite"] and f["bite"] == [])

# ── 舊格式（0731／0801）：摘要前面沒有 ▎ ─────────────────────────────
f, why = sp.parse_entry("AP4675852 (足壇反FIFA) (BITE) 歐足聯決抵制FIFA賽事。"
                        "▎畫面：視訊受訪。▎BITE：「不可接受的交易」")
report("舊格式（摘要前無 ▎）仍解析得出", f is not None, why or "")
report("舊格式摘要正確", f and f["summary"] == "歐足聯決抵制FIFA賽事。", f and f["summary"])

# ── 多講者：BITE 之後的無標籤段落算第二位 ─────────────────────────────
f, _ = sp.parse_entry("△ RT2654 (華州野火) (BITE) ▎州長宣布緊急狀態。▎畫面：火場。"
                      "▎BITE：州長「宣布全州緊急狀態」▎市長「史上最嚴重」▎02:10")
report("多講者收成 bite 陣列兩筆", f and len(f["bite"]) == 2, f and f["bite"])

# ── 時長變體 ─────────────────────────────────────────────────────────
f, _ = sp.parse_entry("△ AP4676115 (測試) ▎摘要。▎畫面：畫面。▎無BITE。▎01:01:01")
report("HH:MM:SS 時長也認（舊資料有）", f and f["duration"] == "01:01:01", f and f["duration"])
f, _ = sp.parse_entry("△ AP4676115 (測試) ▎摘要。▎畫面：畫面。▎無BITE。")
report("沒有時長時 duration 為 None", f and f["duration"] is None)

# ── NS 代碼的字母前綴不是固定兩碼（2026-08-04 實錯）─────────────────
for code, label in (("PY-03MO", "兩碼前綴"), ("WE-001TU", "兩碼＋三位數"),
                    ("DIG-01TU", "三碼前綴"), ("HIST-02TU", "四碼前綴")):
    f, why = sp.parse_entry(f"△ {code} (測試) ▎摘要。▎畫面：畫面。▎無BITE。▎00:25")
    report(f"NS {label}（{code}）解析得出", f is not None and f["codes"] == [code], why or "")

# ── 多代碼並列 ───────────────────────────────────────────────────────
f, _ = sp.parse_entry("△ RT2670 / RT2654 (華州野火) ▎野火當下畫面。▎畫面：火場。▎無BITE。")
report("A/B 並列代碼都收", f and f["codes"] == ["RT2670", "RT2654"], f and f["codes"])

# ── 失敗案例：要回原因，不可拋例外 ───────────────────────────────────
for bad, label in (
    ("", "空字串"),
    ("https://www.youtube.com/watch?v=abc123", "YouTube 網址"),
    ("△ AP4676455 (測試) ▎摘要。▎無BITE。", "缺畫面段"),
    ("△ AP4676455 (測試) ▎摘要。▎畫面：畫面。", "既無 BITE 也無 無BITE"),
):
    f, why = sp.parse_entry(bad)
    report(f"失敗案例「{label}」回原因不拋例外", f is None and bool(why), why)

# ── derive()：不准動 raw_entry、不准擋 ───────────────────────────────
it = {"source": "AP", "script_status": "has_script", "raw_entry": STD}
sp.derive(it)
report("derive 後 raw_entry 原封不動", it["raw_entry"] == STD)
report("derive 成功時 parse_ok=True 且有 fields", it["parse_ok"] and "fields" in it)

bad_it = {"source": "AP", "script_status": "has_script", "raw_entry": "壞掉的內容"}
sp.derive(bad_it)
report("derive 失敗時 parse_ok=False 不拋例外", bad_it["parse_ok"] is False)
report("derive 失敗時記下原因", bool(bad_it.get("parse_note")), bad_it.get("parse_note"))
report("derive 失敗時不留半殘的 fields", "fields" not in bad_it)
report("derive 失敗時 raw_entry 仍在（不擋入庫）", bad_it["raw_entry"] == "壞掉的內容")

# 失敗後又修好 → 舊的 parse_note 要清掉
bad_it["raw_entry"] = STD
sp.derive(bad_it)
report("修好後 parse_note 被清掉", "parse_note" not in bad_it and bad_it["parse_ok"])

# ── skip_reason：三類非三段式不解析 ──────────────────────────────────
for item, want, label in (
    ({"script_status": "note", "source": "?"}, "備註殼", "備註殼"),
    ({"script_status": "has_script", "source": "SIDE_CNN"}, "側錄", "側錄"),
    ({"script_status": "has_script", "source": "YT"}, "YouTube", "YouTube"),
    ({"script_status": "has_script", "source": "AP"}, None, "一般通訊社素材"),
):
    r = sp.skip_reason(item)
    hit = (r is None) if want is None else (r and want in r)
    report(f"skip_reason：{label}", bool(hit), repr(r))

skipped = {"source": "SIDE_CNN", "script_status": "has_script", "raw_entry": "CNN 152131\n內容"}
report("略過的項目完全不寫欄位",
       sp.derive(skipped) is False and "parse_ok" not in skipped and "fields" not in skipped)

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
