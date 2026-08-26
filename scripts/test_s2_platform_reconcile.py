#!/usr/bin/env python3
"""s2_platform_reconcile.py 的測試（MASTER A9 子項④）。

用法：python scripts/test_s2_platform_reconcile.py
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


rec = load("s2_platform_reconcile")

TMP = tempfile.mkdtemp(prefix="s2_reconcile_test_")
results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"　{extra}" if extra and not cond else ""))


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def run(argv):
    old_argv = sys.argv
    sys.argv = ["s2_platform_reconcile.py"] + argv
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = rec.main()
    finally:
        sys.argv = old_argv
    return rc, buf.getvalue()


# --- 一致：exit 0，不動檔案 ---
p1 = os.path.join(TMP, "0826-ABC-state.json")
write_json(p1, {"counts": {"掃描": 10, "收錄": 8, "排除": 2}, "items": []})
rc, out = run(["--file", p1, "--true-count", "10"])
check("一致時 exit 0", rc == 0, f"rc={rc}")
check("一致時印出 ✅", "✅" in out, out)

# --- 不一致、未 --apply：exit 1，不寫檔 ---
p2 = os.path.join(TMP, "0826-ENEX-state.json")
write_json(p2, {"counts": {"掃描": 5, "收錄": 5, "排除": 0}, "items": []})
rc, out = run(["--file", p2, "--true-count", "7"])
check("不一致未 apply：exit 1", rc == 1, f"rc={rc}")
check("不一致訊息含少算則數", "少算 2" in out, out)
with open(p2, encoding="utf-8") as f:
    doc2 = json.load(f)
check("未 apply 不寫入 needs_review", "needs_review" not in doc2 or not doc2.get("needs_review"))

# --- 不一致、--apply：exit 0，寫入 needs_review ---
rc, out = run(["--file", p2, "--true-count", "7", "--apply"])
check("apply 後 exit 0", rc == 0, f"rc={rc}")
with open(p2, encoding="utf-8") as f:
    doc2b = json.load(f)
check("apply 後 needs_review 有記錄", any("對帳不符" in n for n in doc2b.get("needs_review", [])),
      doc2b.get("needs_review"))

# --- 重跑 --apply 不重複寫入同一則 ---
run(["--file", p2, "--true-count", "7", "--apply"])
with open(p2, encoding="utf-8") as f:
    doc2c = json.load(f)
check("重複 apply 不重複寫入", len(doc2c.get("needs_review", [])) == 1, doc2c.get("needs_review"))

# --- 缺 counts.掃描：exit 2 ---
p3 = os.path.join(TMP, "0826-bad.json")
write_json(p3, {"items": []})
rc, out = run(["--file", p3, "--true-count", "1"])
check("缺 counts.掃描時 exit 2", rc == 2, f"rc={rc}")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nPASS={sum(results)} FAIL={len(results) - sum(results)}")
sys.exit(0 if all(results) else 1)
