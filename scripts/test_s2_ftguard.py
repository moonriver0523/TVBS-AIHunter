# -*- coding: utf-8 -*-
"""BITE 兜底迴歸：**照收＋標記**，絕不拒收（2026-08-05 訂正）。

原本 sb_count／footageType 兩條判準是寫成拒收閘門（`continue` 整筆丟棄），
那是設計錯誤——把「BITE 標記對不對」跟「該不該收錄」綁在一起。
0805 實錯 SE-005WE：主播直播打瞌睡的花絮，footageType=RAW 但真的沒有引言
（稿內只有 `(pause :12 seconds for nat)`），被整筆丟棄、只在終端機印一行就消失。

**這支測試的核心是釘死「不准丟資料」**：任何情況都要入庫，疑慮寫進 needs_review。

用法：python test_s2_ftguard.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "s2_state.py")
sys.path.insert(0, HERE)
import s2_state as S  # noqa: E402

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
    # P1b-2（2026-09-08 硬上線）：三站的 batch 一律要帶新格式外殼，
    # 純陣列會被 add-batch 當場退回。測試照生產契約走。
    if isinstance(entries, list):
        entries = {"entries": entries, "new_topics": {}}
    d = tempfile.mkdtemp()
    sp_, bp = os.path.join(d, "s.json"), os.path.join(d, "b.json")
    with open(sp_, "w", encoding="utf-8") as f:
        json.dump({"date": "0101", "items": []}, f)
    with open(bp, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)
    r = subprocess.run([sys.executable, SCRIPT, "--file", sp_, "add-batch", "--entries", bp],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    with open(sp_, encoding="utf-8-sig") as f:
        items = {i["id"]: i for i in json.load(f)["items"]}
    return (r.stdout or "") + (r.stderr or ""), items


def e(i, ft=None, sb=None, nobite=True):
    tail = "▎無BITE。▎01:30" if nobite else "▎BITE：受訪者「內容」。▎01:30"
    tag = "" if nobite else " (BITE)"
    d = {"id": i, "source": "NS", "checkpoint": "0818-2000", "status": "has_script",
         "entry": f"{i} (測試){tag} ▎摘要。▎畫面：畫面。{tail}"}
    if ft:
        d["footage_type"] = ft
    if sb is not None:
        d["sb_count"] = sb
    return d


# ── 核心：必有BITE 類標無BITE → **入庫**＋標記，絕不丟棄 ────────────────
for n, ft in enumerate(("SOT", "BUTTED SOTS", "SOT RAW", "ISO", "DONUT", "INTERVIEW", "RAW")):
    code = f"AA-{n + 10}ZZ"
    out, items = run_batch([e(code, ft=ft)])
    report(f"{ft} 標無BITE → **入庫**（不是丟棄）", code in items)
    report(f"{ft} → 疑慮寫進 needs_review",
           bool(items.get(code, {}).get("needs_review")),
           str(items.get(code, {}).get("needs_review"))[:40])

out, items = run_batch([e("AA-20ZZ", sb=4)])
report("sb_count>0 標無BITE → 入庫＋標記",
       "AA-20ZZ" in items and "4 個 SOUNDBITE" in str(items["AA-20ZZ"].get("needs_review")))

# ── 不該標的別亂標 ───────────────────────────────────────────────────
out, items = run_batch([e("AA-21ZZ", ft="INTERVIEW", nobite=False)])
report("有寫 BITE → 不標疑慮", not items["AA-21ZZ"].get("needs_review"))
for ft in ("VO/NAT", "VO/SIL", "LOOK LIVE", "CLIP-VIDEO"):
    out, items = run_batch([e("AA-22ZZ", ft=ft)])
    report(f"{ft} 標無BITE → 入庫且不標疑慮",
           "AA-22ZZ" in items and not items["AA-22ZZ"].get("needs_review"))
out, items = run_batch([e("AA-23ZZ", ft="PKG")])
report("PKG 灰區 → 入庫、只印提醒、不寫 needs_review",
       "AA-23ZZ" in items and not items["AA-23ZZ"].get("needs_review") and "提醒" in out)
out, items = run_batch([e("AA-24ZZ")])
report("沒帶 footage_type/sb_count → 入庫不標（向下相容）",
       "AA-24ZZ" in items and not items["AA-24ZZ"].get("needs_review"))

# ── 混合批次：一則都不能少 ───────────────────────────────────────────
out, items = run_batch([e("AA-30ZZ", ft="RAW"), e("AA-31ZZ", ft="VO/SIL"),
                        e("AA-32ZZ", ft="PKG"), e("AA-33ZZ", sb=2),
                        e("AA-34ZZ", ft="SOT", nobite=False)])
report("混合批次 5 則全數入庫（零丟棄）", len(items) == 5, sorted(items))
report("混合批次只有該標的被標",
       {k for k, v in items.items() if v.get("needs_review")} == {"AA-30ZZ", "AA-33ZZ"})

# ── 反向：標了 (BITE) 卻沒有 SOUNDBITE（2026-08-06 AP 實錯 7 則）──────
FAKE = ("AA-50ZZ (直播) (BITE) ▎摘要。▎畫面：畫面。"
        "▎BITE：現場原音「逐字稿未附」▎01:00")
report("(BITE) 但 sb_count=0 → 判為疑慮",
       S.bite_doubt(FAKE, 0, None) is not None, str(S.bite_doubt(FAKE, 0, None))[:40])
report("(BITE) 且 sb_count>0 → 不判疑慮",
       S.bite_doubt(FAKE.replace("現場原音「逐字稿未附」", "市長「真的引言」"), 3, None) is None)
report("沒帶 sb_count 時不誤判（NS 走 footageType，不帶 sb_count）",
       S.bite_doubt(FAKE, None, "SOT") is None)
report("標無BITE 的不會被反向規則誤觸",
       S.bite_doubt("AA-51ZZ (x) ▎a。▎畫面：b。▎無BITE。▎01:00", 0, None) is None)

out, items = run_batch([{"id": "AA-52ZZ", "source": "AP", "checkpoint": "0818-2000",
                         "status": "has_script", "sb_count": 0,
                         "entry": FAKE.replace("AA-50ZZ", "AA-52ZZ")}])
report("假 BITE 照樣入庫（不擋）＋寫進 needs_review",
       "AA-52ZZ" in items and bool(items["AA-52ZZ"].get("needs_review")))

# ── bite_doubt 單元 ─────────────────────────────────────────────────
report("bite_doubt：有 BITE 的一律不判疑慮",
       S.bite_doubt("x (BITE) ▎a▎畫面：b▎BITE：「c」▎01:00", 5, "SOT") is None)
report("bite_doubt：大小寫與空白容錯",
       S.bite_doubt("x ▎a▎畫面：b▎無BITE。", None, " raw ") is not None)
report("bite_doubt：sb_count 優先於 footage_type",
       "SOUNDBITE" in (S.bite_doubt("x ▎a▎無BITE。", 3, "RAW") or ""))

# ── update-entry：改好了要自動結案 ──────────────────────────────────
d = tempfile.mkdtemp()
sp_ = os.path.join(d, "s.json")
with open(sp_, "w", encoding="utf-8") as f:
    json.dump({"date": "0101", "items": []}, f)
subprocess.run([sys.executable, SCRIPT, "--file", sp_, "add", "--id", "AA-40ZZ",
                "--source", "NS", "--checkpoint", "0818-2000", "--status", "has_script",
                "--footage-type", "RAW",
                "--entry", "AA-40ZZ (測試) ▎摘要。▎畫面：畫面。▎無BITE。▎01:00"],
               capture_output=True, text=True, encoding="utf-8")
with open(sp_, encoding="utf-8-sig") as f:
    it = json.load(f)["items"][0]
report("add 單筆也會標疑慮（不再是後門）", bool(it.get("needs_review")), str(it.get("needs_review"))[:40])

subprocess.run([sys.executable, SCRIPT, "--file", sp_, "update-entry", "--id", "AA-40ZZ",
                "--sb-count", "1", "--checkpoint", "0818-2000",
                "--entry", "AA-40ZZ (測試) (BITE) ▎摘要。▎畫面：畫面。▎BITE：某人「話」。▎01:00"],
               capture_output=True, text=True, encoding="utf-8")
with open(sp_, encoding="utf-8-sig") as f:
    it = json.load(f)["items"][0]
report("update-entry 補上 BITE 後自動結案", "needs_review" not in it)

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
