# -*- coding: utf-8 -*-
"""scoped 1259 step 3：add-batch 三訊號 pure preflight。

bare + gated 無 --auto-register → 整批 exit 2、零副作用。
--auto-register 只解除 shape gate，不解除 SOURCE_ID_MISMATCH。
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


def run(state, entries, *extra, registry=None):
    argv = [sys.executable, "-X", "utf8", SCRIPT, "--file", state]
    if registry:
        argv += ["--registry", registry]
    argv += ["add-batch", "--entries", entries, *extra]
    r = subprocess.run(argv, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def write_json(obj):
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return path


def fresh_state(items=None):
    items = items or [
        {"id": "RT2880", "source": "RT", "script_status": "has_script",
         "raw_entry": "RT2880 (測試) ▎摘要。▎無BITE。▎00:30",
         "compiled": None, "category": {"大分類": "社會", "中主題": "既有"}},
    ]
    return write_json({"date": "0918", "items": items})


def load_items(path):
    with open(path, encoding="utf-8-sig") as f:
        d = json.load(f)
    items = d.get("items") or []
    if isinstance(items, list):
        return {x.get("id"): x for x in items if isinstance(x, dict)}, d
    return items, d


ENTRY = "FAKE (假) ▎摘要。▎無BITE。▎00:30 ▎畫面：無"


# 1. bare AP ID + 偽造 source
st = fresh_state()
ent = write_json([{
    "id": "AP4677621", "source": "QAB", "checkpoint": "0918-1259",
    "status": "pending", "entry": ENTRY,
}])
mtime = os.path.getmtime(st)
rc, out = run(st, ent)
items, _ = load_items(st)
report("bare AP+QAB 整批拒收",
       rc == 2 and "AP4677621" not in items and os.path.getmtime(st) == mtime,
       f"rc={rc} keys={list(items)} {out.strip()[:200]}")
report("bare AP+QAB 列出三訊號",
       "AP" in out and ("QAB" in out or "id_family" in out or "三" in out or "gated" in out.lower()
                        or "SOURCE" in out or "P1b-2" in out),
       out.strip()[:200])


# 2. bare NS source + 偽造 ID
st = fresh_state()
ent = write_json([{
    "id": "NOT-AN-ID", "source": "NS", "checkpoint": "0918-1259",
    "status": "pending", "entry": ENTRY,
}])
mtime = os.path.getmtime(st)
rc, out = run(st, ent)
items, _ = load_items(st)
report("bare NS source+偽造 ID 整批拒收",
       rc == 2 and "NOT-AN-ID" not in items and os.path.getmtime(st) == mtime,
       f"rc={rc} keys={list(items)} {out.strip()[:200]}")


# 3. envelope existing RT rescue + 偽造 source
st = fresh_state()
ent = write_json({
    "entries": [{
        "id": "RT2880", "source": "QAB", "checkpoint": "0918-1259",
        "status": "has_script", "entry": ENTRY, "category": "社會/救援題",
    }],
    "new_topics": {"救援題": {"charter": "不該登記", "big": "社會"}},
})
reg = write_json({"version": 1, "topics": []})
mtime = os.path.getmtime(st)
rc, out = run(st, ent, registry=reg)
items, _ = load_items(st)
with open(reg, encoding="utf-8") as f:
    topics = json.load(f).get("topics") or []
report("existing RT+偽造 source 整批拒收 SOURCE_ID_MISMATCH",
       rc == 2 and "SOURCE_ID_MISMATCH" in out,
       f"rc={rc} {out.strip()[:240]}")
report("existing RT 救援失敗零副作用（分類／registry 不動）",
       items["RT2880"].get("category", {}).get("中主題") == "既有" and topics == [],
       f"cat={items['RT2880'].get('category')} topics={topics} mtime_changed={os.path.getmtime(st)!=mtime}")


# 4. --auto-register 只解除 shape，不解除 mismatch
st = fresh_state()
ent = write_json([{
    "id": "AP4677621", "source": "QAB", "checkpoint": "0918-1259",
    "status": "pending", "entry": ENTRY,
}])
rc, out = run(st, ent, "--auto-register")
items, _ = load_items(st)
report("--auto-register 仍擋 AP+QAB mismatch",
       rc == 2 and "AP4677621" not in items and "SOURCE_ID_MISMATCH" in out,
       f"rc={rc} keys={list(items)} {out.strip()[:240]}")


# 5. bare ENEX 非 gated 可過 shape gate（writer 合法即可入庫或 skip，不得因 P1b-2 整批退）
st = fresh_state()
ent = write_json([{
    "id": "ENEX1234", "source": "ENEX", "checkpoint": "0918-1259",
    "status": "pending", "entry": "ENEX1234 (測) ▎摘要。▎無BITE。▎00:30 ▎畫面：無",
}])
rc, out = run(st, ent)
items, _ = load_items(st)
report("bare ENEX 非三站不過 shape gate",
       rc == 0 and "ENEX1234" in items,
       f"rc={rc} keys={list(items)} {out.strip()[:200]}")


print()
print("ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
