# -*- coding: utf-8 -*-
"""s2_topic_review 粒度 lint 迴歸（全檢 A32，2026-09-07）。

要解的是「中主題粒度」問題：巨格（一個中主題底下小分題散得太開，其實該拆）、
類別詞命名（中主題名本身就是個大類別，等於沒分類，見 CATEGORY_WORDS 註解）、
孤兒（只有 1 則的中主題，可能該併進同大分類裡名稱相近的那個）。

⚠️ 只印不改（見模組頂端註解）——這支測試只驗證「印出正確的候選」，
不驗證任何自動合併／拆分行為，本支不存在。

用法：python -X utf8 test_s2_topic_review_granularity.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "s2_topic_review.py")

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


def run(items):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "s.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"date": "0907", "items": items}, f, ensure_ascii=False)
    r = subprocess.run([sys.executable, SCRIPT, "--file", p],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


_seq = [0]


def it(big, mid, sub=""):
    """造一則已分類素材（每呼叫一次算一則）。"""
    _seq[0] += 1
    i = f"T{_seq[0]}"
    return {"id": i, "source": "RT", "script_status": "has_script",
            "raw_entry": f"{i} (x) ▎測試內容。▎畫面：無。▎無BITE。",
            "category": {"大分類": big, "中主題": mid, "小分題": sub}}


def repeat(n, big, mid, sub):
    return [it(big, mid, sub) for _ in range(n)]


items = []

# 【國際體壇】12 則／10 個小分題：k/n=10/12=83% ≥ SPREAD(60%)、n≥BIG_N(8) → 巨格候選。
# 名稱本身含類別詞「體壇」→ 命名警告。
# 小分題刻意分三群（公開賽系列／拳擊系列／NBA 系列）＋三個獨立單點，
# 驗證「拆法建議」的連通分群。
items += repeat(2, "體育", "國際體壇", "美國公開賽")
items += repeat(1, "體育", "國際體壇", "日本公開賽")
items += repeat(1, "體育", "國際體壇", "英國公開賽")
items += repeat(2, "體育", "國際體壇", "NBA例行賽")
items += repeat(1, "體育", "國際體壇", "NBA季後賽")
items += repeat(1, "體育", "國際體壇", "拳擊賽事")
items += repeat(1, "體育", "國際體壇", "拳擊冠軍賽")
items += repeat(1, "體育", "國際體壇", "撞球錦標賽")
items += repeat(1, "體育", "國際體壇", "滑板競賽")
items += repeat(1, "體育", "國際體壇", "馬拉松")

# 【美網】1 則（孤兒）／【美網戰報】5 則，同大分類、字面共同「美網」→ 孤兒合併候選。
items += repeat(1, "體育", "美網", "決賽")
items += repeat(3, "體育", "美網戰報", "男單")
items += repeat(2, "體育", "美網戰報", "女單")

# 【尼泊爾洪災】12 則／3 個小分題：k/n=3/12=25% < SPREAD → 不是巨格。
items += repeat(4, "社會", "尼泊爾洪災", "死傷統計")
items += repeat(4, "社會", "尼泊爾洪災", "搜救進度")
items += repeat(4, "社會", "尼泊爾洪災", "國際反應")

# 【川普改湖名】1 則，獨立大分類、同大分類沒有其他中主題可比 → 孤兒但無候選。
items += repeat(1, "政治", "川普改湖名", "")

out = run(items)


def section(marker_start, marker_end):
    """取兩個標記之間的片段，方便斷言「某個候選沒有出現在某一段裡」。"""
    if marker_start not in out or marker_end not in out:
        return ""
    return out.split(marker_start, 1)[1].split(marker_end, 1)[0]


report("段標印出（📐 粒度）", "📐 粒度" in out, out.strip()[:80])
report("巨格候選命中【國際體壇】", "📐 巨格候選 1" in out and "【國際體壇】" in out)
report("巨格候選附小分題分群", "拆法建議" in out and "群1" in out)
report("命名警告命中【國際體壇】含類別詞", "命名警告 1" in out and "【國際體壇】" in out and "體壇" in out)
report("孤兒合併候選【美網】→【美網戰報】",
       "孤兒合併候選 1 筆（含互指）：【美網】→【美網戰報】" in out)
report("孤兒無候選【川普改湖名】沒被誤列為合併候選",
       "【川普改湖名】→" not in out)
report("尼泊爾洪災不是巨格候選（k/n=25%<門檻）",
       "【尼泊爾洪災】" not in section("📐 巨格候選", "⚠️ 命名警告"))

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
