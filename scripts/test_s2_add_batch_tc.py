# -*- coding: utf-8 -*-
"""add-batch 一次帶 category＋tc 的迴歸（2026-09-07 T12）。

**要解的問題**：批次入庫跟分類／T-C 標記原本是三支獨立指令（add-batch →
set-category --pairs → set-tc --pairs），逼 agent 為同一批素材多下兩次呼叫，
還撞上 13f 記錄過的兩個 T/C 時序陷阱（checkpoint 記錯輪、補標在 render 之後）。
這裡驗證 batch.json 每則可以直接帶 `category`／`tc` 兩個鍵，`add-batch` 一次
入庫＋分類＋標 T/C；錯誤不擋入庫，退回明細記進 `tc_rejected`，而且**不計入**
`tc_calls`（那個上限是擋逐則呼叫，不是擋批次內建的一次性標記）。

用法：python test_s2_add_batch_tc.py
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


def new_state(checkpoint="0999-1700"):
    d = tempfile.mkdtemp()
    sp = os.path.join(d, "s.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump({"date": "0999", "checkpoint": checkpoint, "items": []}, f,
                  ensure_ascii=False)
    return d, sp


def run(sp, *args):
    r = subprocess.run([sys.executable, SCRIPT, "--file", sp] + list(args),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def add_batch(sp, entries):
    d = os.path.dirname(sp)
    bp = os.path.join(d, "b.json")
    with open(bp, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)
    return run(sp, "add-batch", "--entries", bp)


def raw(sp):
    with open(sp, encoding="utf-8-sig") as f:
        return json.load(f)


def item(id_, extra=None):
    # P1b-2（2026-09-08 硬上線）：三站（RT／NS／AP）的純陣列會被 add-batch 退回，
    # 這支測的是 T12「一次帶 category／tc」，跟閘門無關，所以用平台線的 ENEX——
    # 純陣列在平台線仍然合法，off 模式的行為才驗得到。
    e = {"id": id_, "source": "ENEX", "checkpoint": "0999-1700",
         "status": "has_script",
         "entry": f"{id_} (測試) ▎摘要。▎畫面：測試。▎無BITE。"}
    if extra:
        e.update(extra)
    return e


d, sp = new_state()
entries = [
    item("AA1", {"category": "社會/測試案/子題", "tc": "社會/美國"}),
    item("AA2", {"tc": "不存在的T/美國"}),
    item("AA3", {"tc": "政治,社會,財經,體育/美國"}),
]
out = add_batch(sp, entries)

# ── ① 帶合法 category＋tc → 一次入庫＋分類＋標 T/C ──────────────────────
v1 = json.loads(run(sp, "get", "--id", "AA1"))
report("① category 有寫入", v1.get("category") == {"大分類": "社會", "中主題": "測試案", "小分題": "子題"},
       f"實得 {v1.get('category')!r}")
report("① tc 有寫入", v1.get("tc") == {"T": ["社會"], "C": ["美國"]},
       f"實得 {v1.get('tc')!r}")

# ── ② tc 用了不在字典裡的名稱 → 素材照樣入庫、tc 缺、退件有留痕 ──────────
v2 = json.loads(run(sp, "get", "--id", "AA2"))
report("② AA2 素材照樣入庫", v2.get("script_status") == "has_script")
report("② AA2 沒有 tc（退件）", not v2.get("tc"), f"實得 {v2.get('tc')!r}")
report("② stdout 有講清楚是字典查不到", "不在 TC-字典" in out, out[:400])

# ── ③ T 超過上限（4 個）→ 整則退回，素材仍入庫 ──────────────────────────
v3 = json.loads(run(sp, "get", "--id", "AA3"))
report("③ AA3 素材照樣入庫", v3.get("script_status") == "has_script")
report("③ AA3 沒有 tc（超上限退回）", not v3.get("tc"), f"實得 {v3.get('tc')!r}")

# ── 退回明細要記進 tc_rejected，且不計進 tc_calls（上限是擋逐則呼叫，不是擋批次）──
top = raw(sp)
report("退回明細記進 _top.tc_rejected[本輪 checkpoint]",
       any("AA2" in x for x in (top.get("tc_rejected") or {}).get("0999-1700", []))
       and any("AA3" in x for x in (top.get("tc_rejected") or {}).get("0999-1700", [])),
       f"實得 {top.get('tc_rejected')!r}")
report("add-batch 內建的 T/C 不計進 tc_calls",
       "0999-1700" not in (top.get("tc_calls") or {}),
       f"實得 {top.get('tc_calls')!r}")

# ── 舊格式（沒有 category／tc 兩鍵）行為完全不變 ─────────────────────────
d2, sp2 = new_state()
out_old = add_batch(sp2, [item("BB1")])
v_old = json.loads(run(sp2, "get", "--id", "BB1"))
report("舊格式 batch：素材照樣入庫", v_old.get("script_status") == "has_script")
report("舊格式 batch：category 仍是 None（沒被憑空生出東西）", v_old.get("category") is None,
       f"實得 {v_old.get('category')!r}")
report("舊格式 batch：沒有 tc 鍵", "tc" not in v_old, f"實得 {v_old.keys()!r}")
top_old = raw(sp2)
report("舊格式 batch：沒有產生 tc_rejected", not (top_old.get("tc_rejected") or {}).get("0999-1700"))

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
