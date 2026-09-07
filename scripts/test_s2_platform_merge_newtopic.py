# -*- coding: utf-8 -*-
"""A10 P1b：ENEX／ABC 整併端過閘迴歸——`s2_platform_merge.py --apply` 一路
呼叫 `add-batch`＋`set-category --auto-register`，遇到登記簿沒有的中主題
要自動登記，不能悄悄漏分類（這條交件端沒有 `new_topics` 可用，見計畫
P1b Task 2「🔴 其他產線過閘」）。

用法：python test_s2_platform_merge_newtopic.py
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "s2_state.py")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ok = True


def report(name, passed, detail=""):
    global ok
    ok = ok and passed
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def load_mod(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


merge = load_mod("s2_platform_merge")

TMP = tempfile.mkdtemp(prefix="s2_p1b_merge_test_")

ABC_LINE = ("ABC090726007 (ABC) ▎聯準會9月降息機率升高，市場押注一碼。"
            "▎畫面：交易大廳、聯準會大樓外觀。▎無BITE。▎01:26")
SRC = ("(ABC) LOCATION: NEW YORK. FED OFFICIALS SIGNALED A POSSIBLE RATE CUT "
       "IN SEPTEMBER AS INFLATION COOLED. SUPERS: NONE. FORMAT: VO.")


def abc_doc():
    return {
        "window_start": "2026-09-07 13:00", "window_end": "2026-09-07 16:50",
        "checkpoint": "0907-1650", "source": "ABC",
        "merged_into_handover": False, "reviewed": False,
        "counts": {"掃描": 1, "收錄": 1, "排除": 0},
        "skipped": [], "needs_review": [], "known_gaps": [],
        "items": [{"id": "ABC090726007", "source": "ABC",
                   "first_seen_checkpoint": "0907-1650",
                   "script_status": "has_script", "raw_entry": ABC_LINE,
                   "category": {"大分類": "財經", "中主題": "全新聯準會話題"},
                   "sb_count": 0, "src_text": SRC,
                   "abc": {"storyNumber": "090726007"}}],
    }


def write(name, obj):
    p = os.path.join(TMP, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return p


def run_main(argv):
    buf = io.StringIO()
    old = sys.argv
    sys.argv = ["s2_platform_merge.py"] + argv
    try:
        with redirect_stdout(buf):
            rc = merge.main()
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
        buf.write(str(e))
    finally:
        sys.argv = old
    return rc, buf.getvalue()


def get(state_path, registry_path, id_):
    r = subprocess.run([sys.executable, SCRIPT, "--file", state_path,
                       "--registry", registry_path, "get", "--id", id_],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return json.loads(r.stdout)


def registry_topics(registry_path):
    if not os.path.exists(registry_path):
        return []
    with open(registry_path, encoding="utf-8") as f:
        return (json.load(f) or {}).get("topics") or []


def by_name(topics, name):
    return next((t for t in topics if t.get("name") == name), None)


cand = write("0907-ABC-state.json", abc_doc())
state_file = os.path.join(TMP, "0907-s2-state.json")
with open(state_file, "w", encoding="utf-8") as f:
    json.dump({"date": "0907", "checkpoint": "0907-1650", "items": []}, f, ensure_ascii=False)
registry_path = os.path.join(TMP, "registry.json")

rc, out = run_main([cand, "--apply", "--file", state_file, "--registry", registry_path])
report("--apply 成功（rc=0）", rc == 0, out.strip()[-400:])

v = get(state_file, registry_path, "ABC090726007")
report("素材已入庫", v.get("script_status") == "has_script")
report("category 有寫（未登記名一樣照寫，因為 --auto-register）",
       v.get("category") == {"大分類": "財經", "中主題": "全新聯準會話題"},
       f"實得 {v.get('category')!r}")
t = by_name(registry_topics(registry_path), "全新聯準會話題")
report("登記簿自動新增這一筆並標 auto:true", bool(t) and t.get("auto") is True, f"實得 {t!r}")
report("stdout 提到「待補 charter」", "待補 charter" in out, out.strip()[-400:])

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
