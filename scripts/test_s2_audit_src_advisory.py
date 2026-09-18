# -*- coding: utf-8 -*-
"""scoped 1259：audit 狀態檔原文待補 advisory 區塊；advisory-only exit 0。"""
import argparse
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

import s2_audit as audit  # noqa: E402

ok = True


def report(name, passed, detail=""):
    global ok
    ok = ok and bool(passed)
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


TMP = tempfile.mkdtemp(prefix="s2_audit_src_adv_")
audit.BASE = TMP
audit.AUDIT_ARGS = argparse.Namespace(rt_list=None, ap_list=None, ns_list=None)

ENTRY = "AP4677621 (測) ▎摘要。▎無BITE。▎00:30"


def write_state(items):
    path = os.path.join(TMP, "0201-s2-state.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "date": "0201",
            "_top": {"window_start": "18:00", "checkpoint": "0201-2300"},
            "items": items,
        }, f, ensure_ascii=False)
    return path


def run_audit(items):
    audit.RED.clear()
    audit.YEL.clear()
    path = write_state(items)
    txt = os.path.join(TMP, "0201晚班交接.txt")
    with open(txt, "w", encoding="utf-8") as f:
        f.write("0201 晚班交接\n")
    scratch = os.path.join(TMP, "scratch")
    os.makedirs(scratch, exist_ok=True)
    buf = io.StringIO()
    with redirect_stdout(buf):
        audit.audit("0201", path, txt, scratch)
    return buf.getvalue(), list(audit.RED), list(audit.YEL)


out, red, yel = run_audit([
    {"id": "AP4677621", "source": "AP", "script_status": "has_script",
     "raw_entry": ENTRY, "src_text_missing": True, "compiled": None,
     "category": {"大分類": "社會", "中主題": "測"}},
    {"id": "RT2880", "source": "RT", "script_status": "has_script",
     "raw_entry": "RT2880 (測) ▎摘要。▎無BITE。▎00:30",
     "src_text": "HEAD: keep\nSTORY: keep", "compiled": None,
     "category": {"大分類": "社會", "中主題": "測"}},
    {"id": "SN-1MO", "source": "NS", "script_status": "has_script",
     "raw_entry": "SN-1MO (測) ▎摘要。▎無BITE。▎00:30",
     "src_text": "DESC: keep\nSCRIPT: keep", "compiled": None,
     "category": {"大分類": "社會", "中主題": "測"}},
])
yel_text = "\n".join(yel)
adv = [y for y in yel if "原文待補" in y]
report("AP src_text_missing 進 advisory",
       any("AP4677621" in y for y in adv),
       yel_text[:240])
report("已有原文的 RT/NS 不列",
       adv and "RT2880" not in adv[0] and "SN-1MO" not in adv[0],
       (adv[:1] or yel_text)[:240])
report("advisory 不併入待人工",
       not any("待人工" in y and "AP4677621" in y for y in yel),
       yel_text[:240])
report("advisory-only 不升紅",
       not any("原文待補" in r for r in red),
       repr(red[:4]))

out2, red2, yel2 = run_audit([
    {"id": "RT2880", "source": "RT", "script_status": "has_script",
     "raw_entry": "RT2880 (測) ▎摘要。▎無BITE。▎00:30",
     "src_text": "HEAD: keep\nSTORY: keep", "compiled": None,
     "category": {"大分類": "社會", "中主題": "測"}},
])
report("全有原文不報原文待補",
       not any("原文待補" in y for y in yel2),
       "\n".join(yel2)[:200])
report("全有原文仍不升紅",
       not any("原文待補" in r for r in red2),
       repr(red2[:4]))

shutil.rmtree(TMP, ignore_errors=True)
print()
print("ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
