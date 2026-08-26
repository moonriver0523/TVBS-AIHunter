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
raw_enex = [
    {"id": "928358", "title": "t1", "desc": "STORYLINE ...", "partner": "FR BFM",
     "cat": "Crime", "loc": "Paris", "tags": ["A"], "ts": 1, "dl": "https://x/928358.mp4", "nlid": 2365490},
    {"id": "928999", "title": "t2", "desc": "TVBS 回流", "partner": "TVBS", "dl": None, "nlid": 1},
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
raw2 = raw_enex + [{"id": "930000", "title": "t3", "desc": "x", "dl": None}]
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
check("CLI 輸出 counts 正確", doc["counts"] == {"掃描": 1, "收錄": 1, "排除": 0}, doc["counts"])

import shutil
shutil.rmtree(TMP, ignore_errors=True)

print(f"\nPASS={sum(results)} FAIL={len(results) - sum(results)}")
sys.exit(0 if all(results) else 1)
