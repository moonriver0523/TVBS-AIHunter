# -*- coding: utf-8 -*-
"""s2_audit.py `reconcile()` RT 清單對帳前綴修正的迴歸測試（R20，2026-09-07）。

為什麼要釘死：RT 清單快照是站方 Edit No（無 `RT` 前綴，如 `9614`），狀態檔
key 卻帶 `RT` 前綴（`RT9614`）。`reconcile()` 原本直接拿快照的 code 去比對
`cur = set(st["items"])`，永遠比不中——每一則已收的 RT 都會被誤判成「窗內
漏收」，造成假陽性。這支測試釘死修好後：已收（帶前綴能對上）的兩則不報漏收，
真的沒收的那一則才報漏收。

用法：python -X utf8 scripts/test_s2_audit_rt_prefix.py
"""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout

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


audit = load("s2_audit")

results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"　{extra}" if extra and not cond else ""))


TMP = tempfile.mkdtemp(prefix="s2_audit_rt_prefix_test_")
# 隔離真正的 BASE（G:\...\自動掃帶系統）——reconcile() 內部會 glob
# `BASE/Archive/**/[01]*-s2-state.json` 找 prev；改指到一個沒有 Archive
# 子目錄的空白暫存目錄，測試才不會受真實歷史資料影響（也不去讀真檔）。
audit.BASE = TMP

# mmdd 用一個不會撞到真實排班日期的哨兵值（`checkpoint_time`／`mmdd_shift`
# 內部會拿去建構真的 `datetime`，必須是合法曆日；BASE 已隔離，不必擔心跟
# 真實 Archive 撞號，選哪天都安全，這裡挑非本輪年份的 0201 純粹圖好認）。
MMDD = "0201"

st = {
    "_top": {"window_start": "18:00", "checkpoint": f"{MMDD}-2300"},
    "items": {
        "RT9614": {"first_seen_checkpoint": f"{MMDD}-2000"},
        "RT9700": {"first_seen_checkpoint": f"{MMDD}-2030"},
        "AP1": {"first_seen_checkpoint": f"{MMDD}-2000"},
    },
}

rt_list_path = os.path.join(TMP, "rt_list.txt")
with open(rt_list_path, "w", encoding="utf-8") as f:
    f.write("9614|02/01/2026 20:00\n")
    f.write("9700|02/01/2026 20:30\n")
    f.write("9800|02/01/2026 21:00\n")

buf = io.StringIO()
with redirect_stdout(buf):
    r = audit.reconcile(st, MMDD, rt_list_path, "RT")
out = buf.getvalue()

check("漏收只有 9800 一則", r["missing_ids"] == ["9800"], r["missing_ids"])
check("漏收數為 1（不是 3）", r["missing"] == 1, r["missing"])
check("已收數為 2（RT9614／RT9700 對上帶前綴的 key）", r["got"] == 2, r["got"])
check("9614／9700 不在漏收清單裡",
      "9614" not in r["missing_ids"] and "9700" not in r["missing_ids"],
      r["missing_ids"])

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nPASS={sum(results)} FAIL={len(results) - sum(results)}")
sys.exit(0 if all(results) else 1)
