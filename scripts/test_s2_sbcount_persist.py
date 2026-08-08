# -*- coding: utf-8 -*-
"""sb_count 落進狀態檔的迴歸（2026-08-09）。

**要防的問題**：sb_count 原本只活在 batch 中間檔裡，而 batch **停在送出當下、
事後不回寫**。素材由 pending 轉正、站方 RESENDING 補上完整稿之後，batch 的值
就過期了——稽核③ 會對同一則**永久重複誤報**假 BITE。
0809-0100 實例：RT4098 收錄時真的 0 個 SOUNDBITE（early-access 版只有
VIDEO SHOWS＋COMPLETE SCRIPT TO FOLLOW），站方補稿後實際有 5 個，
但 batch 永遠記著 0，每一輪稽核都要重查一次已經查過的東西。
⚠️ **重複誤報會把警告訓練成雜訊，那比不報還糟。**

**同時釘死一個順手抓到的潛伏 bug**：`update-entry --sb-count` 原本 default=0。
0 是**有意義的值**（真的沒有 SOUNDBITE），拿它當「沒帶參數」的預設，會讓每一次
沒帶該參數的 update-entry 都撞上 bite_doubt 的反向判準、憑空生出 needs_review；
存進狀態檔之後更嚴重——會把好的舊值直接蓋成 0。

用法：python test_s2_sbcount_persist.py
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


def new_state():
    d = tempfile.mkdtemp()
    sp = os.path.join(d, "s.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump({"date": "0101", "items": []}, f)
    return d, sp


def run(sp, *args):
    r = subprocess.run([sys.executable, SCRIPT, "--file", sp] + list(args),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def items_of(sp):
    with open(sp, encoding="utf-8-sig") as f:
        return {i["id"]: i for i in json.load(f)["items"]}


BITE = "RT0001 (測試) (BITE) ▎摘要。▎畫面：測試。▎BITE：受訪者「內容」。▎01:30"
NOBITE = "RT0002 (測試) ▎摘要。▎畫面：測試。▎無BITE。▎01:30"


def add_batch(sp, entries):
    d = os.path.dirname(sp)
    bp = os.path.join(d, "b.json")
    with open(bp, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)
    return run(sp, "add-batch", "--entries", bp)


# ── 1. add-batch 帶 sb_count → 存進狀態檔 ──────────────────────────
d, sp = new_state()
add_batch(sp, [{"id": "RT0001", "source": "RT", "checkpoint": "0809-0100",
                "status": "has_script", "entry": BITE, "sb_count": 3}])
it = items_of(sp).get("RT0001", {})
report("add-batch 的 sb_count 有存進狀態檔", it.get("sb_count") == 3, f"實得 {it.get('sb_count')!r}")

# ── 2. 沒帶 sb_count 就不要無中生有一個 0 ─────────────────────────
d, sp = new_state()
add_batch(sp, [{"id": "RT0002", "source": "RT", "checkpoint": "0809-0100",
                "status": "has_script", "entry": NOBITE}])
it = items_of(sp).get("RT0002", {})
report("沒帶 sb_count 就不寫該欄位（0 是有意義的值，不可當預設）",
       "sb_count" not in it, f"實得 {it.get('sb_count')!r}")

# ── 3. update-entry 回寫：0 → 5（站方補完整稿的實際情境）──────────
d, sp = new_state()
add_batch(sp, [{"id": "RT4098", "source": "RT", "checkpoint": "0808-2300",
                "status": "pending", "entry": BITE, "sb_count": 0}])
before = items_of(sp)["RT4098"]
run(sp, "update-entry", "--id", "RT4098", "--entry", BITE,
    "--status", "has_script", "--sb-count", "5")
after = items_of(sp)["RT4098"]
report("update-entry --sb-count 會回寫（0→5）",
       before.get("sb_count") == 0 and after.get("sb_count") == 5,
       f"{before.get('sb_count')!r} → {after.get('sb_count')!r}")
report("回寫正確值之後假 BITE 疑慮自動結案",
       "needs_review" not in after, f"殘留：{after.get('needs_review')!r}")

# ── 4. ⭐ 最關鍵：update-entry 沒帶 --sb-count 時，舊值不可被蓋成 0 ──
d, sp = new_state()
add_batch(sp, [{"id": "RT0003", "source": "RT", "checkpoint": "0809-0100",
                "status": "has_script", "entry": BITE, "sb_count": 4}])
out = run(sp, "update-entry", "--id", "RT0003", "--entry", BITE + "（改過）")
after = items_of(sp)["RT0003"]
report("沒帶 --sb-count 時舊值原封不動（不可蓋成 0）",
       after.get("sb_count") == 4, f"實得 {after.get('sb_count')!r}")
report("沒帶 --sb-count 時不會憑空生出假 BITE 的 needs_review",
       "needs_review" not in after, f"殘留：{after.get('needs_review')!r}")

# ── 5. 真的是 0 的時候，該報還是要報（不能為了消雜訊把兜底關掉）────
d, sp = new_state()
add_batch(sp, [{"id": "RT0004", "source": "RT", "checkpoint": "0809-0100",
                "status": "has_script", "entry": BITE, "sb_count": 0}])
it = items_of(sp)["RT0004"]
report("sb_count 真的是 0 且標了 (BITE) → 照樣寫 needs_review",
       it.get("sb_count") == 0 and "needs_review" in it,
       f"sb_count={it.get('sb_count')!r} needs_review={'有' if 'needs_review' in it else '無'}")
report("疑慮素材仍然入庫（不准拒收，見 test_s2_ftguard）",
       "RT0004" in items_of(sp))

print("\n" + ("全部通過" if ok else "有失敗"))
sys.exit(0 if ok else 1)
