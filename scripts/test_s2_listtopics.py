# -*- coding: utf-8 -*-
"""list-topics 迴歸（2026-08-05）。

要解的是中主題重複的**真正成因：agent 每輪獨立命名、看不到既有清單**。
0805 實例：20:00 輪替基輔攻擊開【俄襲烏克蘭】，但 16:30 輪已有【基輔空襲】
——兩個名稱都合理卻分裂（當天 77 個中主題人工合併後剩 55）。

用法：python test_s2_listtopics.py
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


def run(items, *extra):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "s.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"date": "0805", "items": items}, f, ensure_ascii=False)
    r = subprocess.run([sys.executable, SCRIPT, "--file", p, "list-topics", *extra],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def it(i, big, mid, sub=""):
    return {"id": i, "source": "RT", "script_status": "has_script",
            "raw_entry": f"{i} (x) ▎a。▎畫面：b。▎無BITE。",
            "category": {"大分類": big, "中主題": mid, "小分題": sub}}


out = run([it("RT1", "烏俄", "基輔空襲", "災後"), it("RT2", "烏俄", "基輔空襲", "大火"),
           it("RT3", "烏俄", "俄軍動態"), it("RT4", "美國", "密西根初選")])
report("列出中主題與則數", "【基輔空襲】×2" in out and "【俄軍動態】×1" in out, out.strip()[:60])
report("大分類含則數與中主題數", "烏俄（3 則 / 2 個中主題）" in out)
report("大分類依則數排序（烏俄在美國前）", out.index("烏俄") < out.index("美國"))
report("合計行正確", "合計 4 則 / 3 個中主題" in out, [l for l in out.split("\n") if "合計" in l])
report("結尾有提醒不要另起爐灶", "不要另起爐灶" in out)

report("--subs 才列小分題",
       "災後" not in run([it("RT1", "烏俄", "基輔空襲", "災後")])
       and "災後" in run([it("RT1", "烏俄", "基輔空襲", "災後")], "--subs"))

out = run([it("RT1", "天氣", "歐洲熱浪"), it("RT2", "天氣", "亞洲熱浪"),
           it("RT3", "天氣", "歐洲野火"), it("RT4", "天氣", "野火")])
i熱 = [out.index("【歐洲熱浪】"), out.index("【亞洲熱浪】")]
i火 = [out.index("【歐洲野火】"), out.index("【野火】")]
report("中主題套用 render 的靠攏排序（同族相鄰）",
       abs(i熱[0] - i熱[1]) < max(i火) - min(i熱) or abs(i火[0] - i火[1]) < 40)

report("空狀態檔不炸", "沒有任何已分類" in run([]))
report("未分類素材不列入",
       "未填" not in run([{"id": "RT9", "source": "RT", "script_status": "has_script",
                           "raw_entry": "RT9 (x) ▎a。▎畫面：b。▎無BITE。", "category": None}]))
out = run([it("RT1", "美國", None)])
report("中主題空白顯示 (未填) 而不是消失", "(未填)" in out, out.strip()[:50])

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
