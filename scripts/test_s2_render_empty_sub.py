# -*- coding: utf-8 -*-
"""R37 防呆：`render_block` 遇到 0 則的小分題不印孤兒標題，`+` 分隔不跑掉。

直接測 `render_block`——`group_items` 本身產不出空小分題
（`setdefault(sub, []).append(it)` 一定至少一則），這道防呆針對的是
手改狀態檔／別的呼叫者餵進來的形狀。

用法：python test_s2_render_empty_sub.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_render as sr  # noqa: E402

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


def item(text):
    # first_seen_checkpoint 留空 → mark_for 走預設，本測試只看排版不看標記
    return {"raw_entry": text, "first_seen_checkpoint": ""}


MMDD = "0910"

# ① 第一個小分題是空的：後面那個不該冒出開頭多餘的 `+`
out = sr.render_block("測試", {"中主": {"": [], "甲題": [item("RT0001 甲則")]}}, MMDD)
report("① 空的排第一 → 無開頭多餘 `+`", "+" not in out, f"實得 {out}")
report("① 空的排第一 → 甲題與其素材都在", "甲題" in out and any("甲則" in l for l in out))

# ② 空的夾在中間：恰好一個 `+`，且空小分題標題不出現
out = sr.render_block(
    "測試",
    {"中主": {"甲題": [item("RT0001 甲則")], "乙題": [], "丙題": [item("RT0002 丙則")]}},
    MMDD)
report("② 空的夾中間 → `+` 恰好 1 個", out.count("+") == 1, f"實得 {out.count('+')} 個：{out}")
report("② 空的夾中間 → 不印乙題標題", "乙題" not in out, f"實得 {out}")
report("② 空的夾中間 → 甲丙與素材都在",
       "甲題" in out and "丙題" in out
       and any("甲則" in l for l in out) and any("丙則" in l for l in out))
# `+` 必須落在甲則之後、丙題之前（不是被擠到別處）
report("② 空的夾中間 → `+` 位置正確",
       out.index("+") > max(i for i, l in enumerate(out) if "甲則" in l)
       and out.index("+") < out.index("丙題"), f"實得 {out}")

# ③ 全部小分題都空：中主題標題仍印（跟 resident_topics 同一種版面），但不印任何小分題
out = sr.render_block("測試", {"中主": {"甲題": [], "乙題": []}}, MMDD)
report("③ 全空 → 【中主】標題仍在、小分題全不印",
       "【中主】" in out and "甲題" not in out and "乙題" not in out and "+" not in out,
       f"實得 {out}")

# ④ 回歸護欄：resident_topics 的空字典中主題照舊只印標題（本次改動不得波及）
out = sr.render_block("測試", {"常駐": {}}, MMDD)
report("④ resident_topics 空字典 → 【常駐】標題照印",
       "【常駐】" in out, f"實得 {out}")

# ⑤ 回歸護欄：沒有任何空小分題時，排版與改動前完全一致
out = sr.render_block(
    "測試",
    {"中主": {"": [item("RT0001 甲則")], "乙題": [item("RT0002 乙則")]}},
    MMDD)
report("⑤ 無空小分題 → `+` 恰好 1 個、裸標題行不因空 key 冒出",
       out.count("+") == 1 and "乙題" in out, f"實得 {out}")

print("\n" + ("全部通過" if ok else "有未通過項目"))
sys.exit(0 if ok else 1)
