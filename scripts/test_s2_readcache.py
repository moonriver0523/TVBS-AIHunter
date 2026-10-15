# -*- coding: utf-8 -*-
"""T15（2026-10-15）：list-topics／pending 同 revision 重複查詢只回一行。

用法：python test_s2_readcache.py
"""
import json
import os
import subprocess
import sys
import tempfile

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


def mk(run_id="r1", extra_item=False):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "s.json")
    items = {"A-1": {"source": "NS", "script_status": "pending",
                     "category": {"大分類": "美國", "中主題": "期中選舉", "小分題": "造勢"}}}
    if extra_item:
        items["A-2"] = {"source": "NS", "script_status": "has_script",
                        "category": {"大分類": "美國", "中主題": "期中選舉", "小分題": "辯論"}}
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"date": "1015", "run_id": run_id, "items": items}, f, ensure_ascii=False)
    return p


def run(p, *args, env=None):
    e = dict(os.environ)
    e.pop("S2_NO_READCACHE", None)
    if env:
        e.update(env)
    r = subprocess.run([sys.executable, SCRIPT, "--file", p, *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=e)
    return r.stdout


p = mk()
first = run(p, "list-topics")
second = run(p, "list-topics")
report("第一次完整輸出", "期中選舉" in first and "revision" not in first)
report("同 revision 第二次只回一行", "期中選舉" not in second and "revision" in second and second.count("\n") <= 2, repr(second[:80]))
report("--force 重印完整輸出", "期中選舉" in run(p, "list-topics", "--force"))
report("不同參數（--compact）不被省略", "期中選舉" in run(p, "list-topics", "--compact"))

p = mk()
run(p, "list-topics")
d = json.load(open(p, encoding="utf-8"))
d["items"]["A-2"] = {"source": "NS", "script_status": "has_script",
                     "category": {"大分類": "美國", "中主題": "期中選舉", "小分題": "辯論"}}
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
report("狀態改變後重新完整輸出", "期中選舉" in run(p, "list-topics"))

p = mk()
a = run(p, "pending")
b = run(p, "pending")
report("pending 第一次印 ID", "A-1" in a)
report("pending 同 revision 第二次一行", "A-1" not in b and "revision" in b)

p = mk()
run(p, "list-topics")
d = json.load(open(p, encoding="utf-8"))
d["run_id"] = "r2"
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
report("換 run_id（新一輪）不省略", "期中選舉" in run(p, "list-topics"))

p = mk()
run(p, "list-topics")
report("S2_NO_READCACHE=1 不省略", "期中選舉" in run(p, "list-topics", env={"S2_NO_READCACHE": "1"}))

p = mk()
run(p, "list-topics")
d = json.load(open(p, encoding="utf-8"))
d["updated_at"] = "2099-01-01T00:00:00+08:00"
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
report("只有 updated_at 變動仍視為同 revision", "revision" in run(p, "list-topics"))

report("寫狀態檔旁檔不污染狀態檔", "readcache" not in open(p, encoding="utf-8").read())
print("ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
