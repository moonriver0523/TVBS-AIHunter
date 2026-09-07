# -*- coding: utf-8 -*-
"""P1b-2（2026-09-07）：`build --skeleton` 出 `{"entries":[…],"new_topics":{…}}` 新格式，
主力三站產線也過 A10 P1b 新題閘門；`fill-src-text`／`collate-category` 認新殼。

用法：python -X utf8 scripts/test_s2_build_newformat.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PREP = os.path.join(HERE, "s2_batch_prep.py")
STATE = os.path.join(HERE, "s2_state.py")

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


def run(*args):
    env = dict(os.environ)
    env.pop("S2_CHECKPOINT", None)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([sys.executable, "-X", "utf8", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def jdump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return path


def jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


d = tempfile.mkdtemp()
skel = jdump(os.path.join(d, "rt_skeleton_2000.json"), [
    {"id": "RT0001", "source": "RT", "checkpoint": "0999-2000", "status": "has_script",
     "src_text": "STORY: one", "sb_count": 2, "entry": "", "category": "", "tc": "",
     "hint": {"head": "h", "dur": "01:00", "sb_count": 2, "first150": "x"}},
    {"id": "RT0002", "source": "RT", "checkpoint": "0999-2000", "status": "has_script",
     "src_text": "STORY: two", "sb_count": 0, "entry": "", "category": "", "tc": "",
     "hint": {"head": "h2", "dur": "00:30", "sb_count": 0, "first150": "y"}},
])
ent = jdump(os.path.join(d, "rt_entries_2000.json"), {
    "_new_topics": {"全新主題": {"charter": "測試新題收什麼", "big": "體育"}},
    "RT0001": {"entry": "RT0001 (測試 標題) (BITE) ▎摘要一。",
               "category": {"大分類": "體育", "中主題": "全新主題", "小分題": "x"}, "tc": "體育/歐洲"},
    "RT0002": {"entry": "RT0002 (測試 標題二) (無BITE) ▎摘要二。", "category": "社會/尼泊爾洪災/搜救", "tc": "天災天氣/南亞"},
})
out = os.path.join(d, "rt_batch_2000.json")
code, log = run(PREP, "build", "--site", "rt", "--skeleton", skel, "--entries", ent, "--raw", skel, "--checkpoint", "0999-2000", "--out", out)
b = jload(out) if os.path.exists(out) else None
report("build 出新格式殼", isinstance(b, dict) and isinstance(b.get("entries"), list) and len(b["entries"]) == 2, log[-300:])
report("new_topics 原樣搬到頂層", isinstance(b, dict) and b.get("new_topics", {}).get("全新主題", {}).get("charter") == "測試新題收什麼")
report("entries 不含 _new_topics／hint", isinstance(b, dict) and all("hint" not in e for e in b["entries"])
       and all(e.get("id") != "_new_topics" for e in b["entries"]))

# 沒有 _new_topics 鍵 → 仍然出外殼（2026-09-08 硬上線；軟上線那版會退回純陣列，
# 而純陣列已被 add-batch 拒收，等於把坑往下游搬）
ent_old = jdump(os.path.join(d, "rt_entries_old.json"), {
    "RT0001": {"entry": "RT0001 (測試 標題) (BITE) ▎摘要一。", "category": "體育/全新主題/x"},
})
out_old = os.path.join(d, "rt_batch_old.json")
code, log = run(PREP, "build", "--site", "rt", "--skeleton", skel, "--entries", ent_old, "--raw", skel, "--checkpoint", "0999-2000", "--out", out_old)
bo = jload(out_old) if os.path.exists(out_old) else None
report("沒 _new_topics 鍵 → 照樣出外殼、new_topics 空（硬上線）",
       isinstance(bo, dict) and len(bo.get("entries") or []) == 1
       and bo.get("new_topics") == {} and "新格式、過閘" in log, log[-200:])

# fill-src-text 認新殼、殼原樣寫回
raw = jdump(os.path.join(d, "rt_detail_2000.json"), [
    {"edit": "RT0001", "story": "FULL STORY ONE", "head": "h"},
    {"edit": "RT0002", "story": "FULL STORY TWO", "head": "h2"},
])
for e in b["entries"]:
    e.pop("src_text", None)
jdump(out, b)
code, log = run(PREP, "fill-src-text", "--site", "rt", "--raw", raw, "--batch", out)
b2 = jload(out)
report("fill-src-text 新殼就地填入", code == 0 and isinstance(b2, dict) and all(e.get("src_text") for e in b2["entries"]), log[-300:])
report("fill-src-text 殼與 new_topics 保留", isinstance(b2, dict) and "全新主題" in (b2.get("new_topics") or {}))

# collect-category 認新殼＋字串形 category
code, log = run(PREP, "collate-category", out)
report("collate-category 新殼＋字串 category", code == 0 and "RT0001=體育/全新主題/x" in log and "RT0002=社會/尼泊爾洪災/搜救" in log, log[-300:])

# add-batch 吃新格式：new_topics 登記後，未登記名也寫得進去
sp = jdump(os.path.join(d, "s.json"), {"date": "0999", "checkpoint": "0999-1700", "items": []})
rp = jdump(os.path.join(d, "registry.json"), {"version": 1, "topics": [
    {"name": "尼泊爾洪災", "charter": "c", "aliases": [], "big": "社會", "tc": {"T": [], "C": []},
     "first_seen": "2026-09-01", "last_seen": "2026-09-01", "resident": False}]})
code, log = run(STATE, "--file", sp, "--registry", rp, "add-batch", "--entries", out)
st = jload(sp)
items = {x["id"]: x for x in st["items"]}
report("add-batch 新格式：new_topics 登記＋分類寫入", items.get("RT0001", {}).get("category", {}).get("中主題") == "全新主題"
       and items.get("RT0002", {}).get("category", {}).get("中主題") == "尼泊爾洪災", log[-400:])
report("add-batch 新格式：T/C 也寫入", (items.get("RT0002", {}).get("tc") or {}).get("C") == ["南亞"])
report("桶鍵無退回", not st.get("tc_rejected"), str(st.get("tc_rejected")))

print("\nALL PASS" if ok else "\nSOME FAILED")
sys.exit(0 if ok else 1)
