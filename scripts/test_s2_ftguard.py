# -*- coding: utf-8 -*-
"""NS `footage_type` BITE 兜底迴歸（2026-08-04）。

NS 稿件不用 `SOUNDBITE` 這個詞、數不出 `sb_count`，在這條兜底之前 **NS 是三站裡
唯一完全沒有機械擋線的**——只能靠 agent 自己讀稿判斷，那正是誤判的來源。

分類依據是 0731–0804 全庫存交叉統計（見 13b §1a-3），不是憑印象列舉。

用法：python test_s2_ftguard.py
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


def run_batch(entries):
    d = tempfile.mkdtemp()
    sp_, bp = os.path.join(d, "s.json"), os.path.join(d, "b.json")
    with open(sp_, "w", encoding="utf-8") as f:
        json.dump({"date": "0101", "items": []}, f)
    with open(bp, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)
    r = subprocess.run([sys.executable, SCRIPT, "--file", sp_, "add-batch", "--entries", bp],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    with open(sp_, encoding="utf-8-sig") as f:
        got = {i["id"] for i in json.load(f)["items"]}
    return (r.stdout or "") + (r.stderr or ""), got


def e(i, ft, nobite=True):
    tail = "▎無BITE。▎01:30" if nobite else "▎BITE：受訪者「內容」。▎01:30"
    tag = "" if nobite else " (BITE)"
    return {"id": i, "source": "NS", "checkpoint": "t", "status": "has_script",
            "footage_type": ft, "entry": f"{i} (測試){tag} ▎摘要。▎畫面：畫面。{tail}"}


# 必有 BITE 的七種：標無BITE 一律擋下、不入庫
for n, ft in enumerate(("SOT", "BUTTED SOTS", "SOT RAW", "ISO", "DONUT", "INTERVIEW", "RAW")):
    code = f"AA-{n + 10}ZZ"
    out, got = run_batch([e(code, ft)])
    report(f"{ft} 標無BITE → 擋下不入庫", code not in got and ft in out)

# 同樣的 footageType，有寫 BITE 就正常入庫
out, got = run_batch([e("AA-20ZZ", "INTERVIEW", nobite=False)])
report("INTERVIEW 有寫 BITE → 正常入庫", "AA-20ZZ" in got, out.strip())

# 灰區 PKG：不擋，但要出提醒
out, got = run_batch([e("AA-21ZZ", "PKG")])
report("PKG 標無BITE → 入庫但印提醒", "AA-21ZZ" in got and "提醒" in out, out.strip()[:90])

# 無聲類：不檢查
for n, ft in enumerate(("VO/NAT", "VO/STILL", "VO/SIL", "VO/RAW", "LOOK LIVE", "CLIP-VIDEO")):
    code = f"AA-{n + 30}ZZ"
    out, got = run_batch([e(code, ft)])
    report(f"{ft} 標無BITE → 正常入庫（不檢查）", code in got)

# 沒帶 footage_type：向下相容，不檢查
x = e("AA-40ZZ", "INTERVIEW")
del x["footage_type"]
out, got = run_batch([x])
report("沒帶 footage_type → 不檢查（向下相容）", "AA-40ZZ" in got)

# 大小寫／空白容錯
out, got = run_batch([e("AA-41ZZ", " interview ")])
report("footage_type 大小寫與前後空白容錯", "AA-41ZZ" not in got)

# 一批混合：擋的擋、過的過，不因一筆壞掉就中斷
out, got = run_batch([e("AA-50ZZ", "INTERVIEW"), e("AA-51ZZ", "VO/SIL"),
                      e("AA-52ZZ", "PKG"), e("AA-53ZZ", "SOT", nobite=False)])
report("混合批次：只擋該擋的，其餘照常入庫",
       got == {"AA-51ZZ", "AA-52ZZ", "AA-53ZZ"}, sorted(got))

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
