# -*- coding: utf-8 -*-
"""A10 P1b：`list-topics --yesterday` 迴歸——建檔輪的命名參考。

讀前一日封存狀態檔（`Archive/{YYYYMMDD}/{MMDD}-s2-state.json`），列出
≥3 則的中主題＋登記簿 charter，給建檔輪（每天第一輪）當「今天要開哪些
中主題」的參考，不必自己回頭翻交接 txt。

用法：python test_s2_list_topics_yesterday.py
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "s2_state.py")

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


def run(*args, file=None, registry=None, archive_dir=None):
    cmd = [sys.executable, SCRIPT]
    if file:
        cmd += ["--file", file]
    if registry:
        cmd += ["--registry", registry]
    cmd += list(args)
    if archive_dir:
        cmd += ["--archive-dir", archive_dir]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def cat_item(id_, mid, big="社會"):
    return {"id": id_, "source": "RT", "script_status": "has_script",
            "raw_entry": f"{id_} (x) ▎a。▎畫面：b。▎無BITE。",
            "category": {"大分類": big, "中主題": mid}}


def yday_paths(archive_root):
    yday = datetime.now() - timedelta(days=1)
    d = os.path.join(archive_root, yday.strftime("%Y%m%d"))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{yday.strftime('%m%d')}-s2-state.json")


tmp = tempfile.mkdtemp()
archive_root = os.path.join(tmp, "Archive")
today_file = os.path.join(tmp, "0907-s2-state.json")   # --file 需要指到存在或可建立的路徑
registry_path = os.path.join(tmp, "registry.json")

# ── ① 前一日檔有 4 則「多則主題」／2 則「少則主題」，只列 ≥3 則的 ────────
yfile = yday_paths(archive_root)
items = ([cat_item(f"RT{i}", "多則主題") for i in range(4)]
         + [cat_item(f"RT{i}0", "少則主題") for i in range(2)])
with open(yfile, "w", encoding="utf-8") as f:
    json.dump({"date": "yday", "items": items}, f, ensure_ascii=False)
run("topic-register", "--name", "多則主題", "--charter", "測試用 charter",
   "--big", "社會", file=today_file, registry=registry_path)

out1 = run("list-topics", "--yesterday", file=today_file, registry=registry_path,
          archive_dir=archive_root)
report("① 列出 ≥3 則的中主題並帶 charter",
       "多則主題｜4｜測試用 charter" in out1, out1.strip())
report("① 不列 <3 則的中主題", "少則主題" not in out1, out1.strip())

# ── ② 前一日檔案不存在 → 明講找不到，不是空白輸出 ────────────────────────
tmp2 = tempfile.mkdtemp()
out2 = run("list-topics", "--yesterday", file=os.path.join(tmp2, "0907-s2-state.json"),
          registry=os.path.join(tmp2, "registry.json"),
          archive_dir=os.path.join(tmp2, "Archive"))
report("② 找不到前一日封存檔時明講，不是空白", "找不到這份封存檔" in out2, out2.strip())

# ── ③ 前一日檔存在但沒有 ≥3 則的中主題 → 明講「無」，不是空白 ────────────
tmp3 = tempfile.mkdtemp()
archive3 = os.path.join(tmp3, "Archive")
yfile3 = yday_paths(archive3)
with open(yfile3, "w", encoding="utf-8") as f:
    json.dump({"date": "yday", "items": [cat_item("RT1", "只有一則")]}, f, ensure_ascii=False)
out3 = run("list-topics", "--yesterday", file=os.path.join(tmp3, "0907-s2-state.json"),
          registry=os.path.join(tmp3, "registry.json"), archive_dir=archive3)
report("③ 有檔但沒有 ≥3 則時明講「無」", "無 ≥3 則的中主題" in out3, out3.strip())

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
