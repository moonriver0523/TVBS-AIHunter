# -*- coding: utf-8 -*-
"""🟡 次級重大標記迴歸（2026-08-05）。

兩層設計要解的問題：檔頭只有 3 行上限，但一晚常有十幾件重大事件。單一層級下
agent 判斷「這則排不進前三」時會**連正文標記一起放棄**（0804 整晚 164 則只標 1 則）。
拆成 🔴＝曾進檔頭／🟡＝重大但未進檔頭之後，標 🟡 不必宣稱自己是今天前三。

一樣要防「標記沒剝乾淨 → 整行從品質掃與檔頭統計靜默消失」那個老坑。

用法：python test_s2_orange.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_validate as sv  # noqa: E402
import s2_render as sr    # noqa: E402

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


BODY = "AP4676573 (火山) ▎瓜地馬拉火山噴發。▎畫面：熔岩。▎無BITE。▎01:00"

# ── 解析層：五種前綴組合都要活著 ─────────────────────────────────────
for pre, red, orange, aired, label in (
    ("△ ", False, False, False, "無標記"),
    ("△ 🔴 ", True, False, False, "🔴"),
    ("△ 🟡 ", False, True, False, "🟡"),
    ("△ 🟡 🟤 ", False, True, True, "🟡＋🟤"),
    ("△ 🔴 🟤 ", True, False, True, "🔴＋🟤"),
):
    line = pre + BODY
    mark, rest = sv.strip_mark(line)
    report(f"{label}：剝乾淨後仍 match LINE_RE", bool(sv.LINE_RE.match(rest)), repr(rest[:28]))
    report(f"{label}：is_red/is_subalert/is_aired 正確",
           (sv.is_red(line), sv.is_subalert(line), sv.is_aired(line)) == (red, orange, aired),
           f"{sv.is_red(line)},{sv.is_subalert(line)},{sv.is_aired(line)}")

report("🟡 在代碼之後不算標記", not sv.is_subalert("△ AP4676573 (x) ▎內文提到 🟡 符號。"))

# ── 檔頭：🟡 行照常計數，圖例有用到才印 ──────────────────────────────
lines = ["△ " + BODY, "△ 🟡 RT3130 (野火) ▎6.4萬人撤離。▎畫面：廢墟。▎無BITE。▎00:55"]
hdr = "\n".join(sv.header_from_lines(lines, mmdd="0804"))
report("🟡 行計入檔頭則數（應 2 則）", "共2則" in hdr, hdr)
report("用到 🟡 才印圖例", "🟡=重大未進檔頭" in hdr, hdr)
report("沒用到 🟡 不印圖例",
       "🟡" not in "\n".join(sv.header_from_lines(["△ " + BODY], mmdd="0804")))

# ── render：互斥與排序 ───────────────────────────────────────────────
def r(pre):
    return sr.render_item({"raw_entry": pre + BODY,
                           "first_seen_checkpoint": "0804-1600"}, "0804")[0]


report("🟡 印得出來", r("🟡 ").startswith("△ 🟡 "), r("🟡 ")[:12])
report("🔴 不受影響", r("🔴 ").startswith("△ 🔴 "), r("🔴 ")[:12])
report("兩個都寫時取較高層級 🔴（不降級）",
       r("🔴 🟡 ").startswith("△ 🔴 ") and "🟡" not in r("🔴 🟡 "), r("🔴 🟡 ")[:14])
report("順序：時段 → 🟡 → 🟤", r("🟡 🟤 ").startswith("△ 🟡 🟤 "), r("🟡 🟤 ")[:16])
report("aired 欄位與 🟡 併用",
       sr.render_item({"raw_entry": "🟡 " + BODY, "aired": True,
                       "first_seen_checkpoint": "0804-1600"}, "0804")[0].startswith("△ 🟡 🟤 "))
report("沒標時不憑空生出 🟡", "🟡" not in r(""))
report("🟡 只印一次", r("🟡 ").count("🟡") == 1)

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
