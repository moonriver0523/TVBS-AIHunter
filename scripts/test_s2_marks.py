# -*- coding: utf-8 -*-
"""時段標記迴歸：現行符號 ◇ 生成正確，舊符號 ■／● 仍解析得動。

晨班符號換過兩次：`●` →（2026-08-04）`■` →（2026-09-04）`◇`。**只改生成不改解析**
——舊資料不回頭改（已歸檔的 txt：0802–0803 是 `●`、0804–0904 是 `■`），解析端若不再認得，那些行會
LINE_RE 不 match、從品質掃與檔頭統計裡**靜默消失**（不報錯、只是數字少算）。
這支測試就是把「相容分支不准被清掉」釘死。

用法：python test_s2_marks.py
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


BODY = "AP4676455 (美股) ▎美股大漲。▎畫面：交易鈴。▎無BITE。▎01:00"

# ── 生成：07:00–09:00 那格一律產出 ◇，不再產出 ■／● ────────────────────
for cp, want, label in (
    ("0804-1600", "△", "16:00 → △"),
    ("0805-0100", "▲", "隔天 01:00 → ▲"),
    ("0805-0430", "▲", "隔天 04:30 → ▲"),
    ("0805-0700", "◇", "隔天 07:00 → ◇（原 ■、更早 ●）"),
    ("0805-0800", "◇", "隔天 08:00 → ◇（原 ■、更早 ●）"),
    ("0805-1000", "◆", "隔天 10:00 → ◆"),
    ("0805-1300", "◆", "隔天 13:00 → ◆"),
):
    got = sr.mark_for(cp, "0804")
    report(label, got == want, f"得到 {got!r}")

report("render 產物不含舊符號 ●／■",
       not any(c in sr.render_item({"raw_entry": BODY,
                                    "first_seen_checkpoint": "0805-0800"},
                                   "0804")[0] for c in ("●", "■")))
report("render 產物用 ◇",
       sr.render_item({"raw_entry": BODY,
                       "first_seen_checkpoint": "0805-0800"}, "0804")[0].startswith("◇ "))

# ── 相容：舊 txt 的 ● 行仍要被辨識成素材行（最重要的一組）─────────────
for mk in ("△", "▲", "◇", "■", "◆", "●"):
    line = f"{mk} {BODY}"
    mark, rest = sv.strip_mark(line)
    report(f"「{mk}」行仍 match LINE_RE", bool(sv.LINE_RE.match(rest)), repr(rest[:32]))
    report(f"「{mk}」被正確剝出", mark == mk, repr(mark))

old = [f"● {BODY}", "▲ RT2880 (NYSE) ▎美股開高。▎畫面：開市鐘。▎無BITE。▎00:55"]
hdr = "\n".join(sv.header_from_lines(old, mmdd="0803"))
report("舊 ● 行計入檔頭則數（應 2 則）", "共2則" in hdr, hdr)
report("舊 ● 計入隔夜續掃", "隔夜續掃" in hdr and "● 1則" in hdr, hdr)
report("舊 ● 有圖例可查", "●=" in hdr, hdr)

mid = [f"■ {BODY}", "▲ RT2880 (NYSE) ▎美股開高。▎畫面：開市鐘。▎無BITE。▎00:55"]
hdr2 = "\n".join(sv.header_from_lines(mid, mmdd="0805"))
report("舊 ■ 計入隔夜續掃（0804–0904 的歸檔）", "■ 1則" in hdr2, hdr2)
report("舊 ■ 有圖例可查", "■=" in hdr2, hdr2)

new = [f"◇ {BODY}", "▲ RT2880 (NYSE) ▎美股開高。▎畫面：開市鐘。▎無BITE。▎00:55"]
hdr3 = "\n".join(sv.header_from_lines(new, mmdd="0905"))
report("新 ◇ 計入隔夜續掃", "◇ 1則" in hdr3, hdr3)
report("新檔圖例不出現舊符號 ■／●", "■" not in hdr3 and "●" not in hdr3, hdr3)


# ── set-mark 的可選值 ────────────────────────────────────────────────
report("set-mark 接受 ◇", "◇" in sr.render_item(
    {"raw_entry": BODY, "first_seen_checkpoint": "0804-1600", "mark": "◇"}, "0804")[0])
report("set-mark 寫死的舊 ■ 仍生效（舊資料相容）", sr.render_item(
    {"raw_entry": BODY, "first_seen_checkpoint": "0804-1600", "mark": "■"},
    "0804")[0].startswith("■ "))
report("set-mark 寫死的舊 ● 仍生效（舊資料相容）", sr.render_item(
    {"raw_entry": BODY, "first_seen_checkpoint": "0804-1600", "mark": "●"},
    "0804")[0].startswith("● "))


# ── 累計時間窗（2026-08-04 訂正：不是單輪區間）─────────────────────
def st(items_cp, checkpoint, window_start=None):
    s = {"items": [{"first_seen_checkpoint": c} for c in items_cp],
         "checkpoint": checkpoint}
    if window_start:
        s["window_start"] = window_start
    return s


w = sr.window_from_state(st(["0804-1600", "0804-1800"], "0804-1800",
                            "2026-08-04 13:00"), "0804")
report("有 window_start：從開檔算起", w == "2026-08-04 13:00–2026-08-04 18:00", w)

w = sr.window_from_state(st(["0804-1600", "0804-1800"], "0804-1800"), "0804")
report("沒 window_start：退回最早 checkpoint",
       w == "2026-08-04 16:00–2026-08-04 18:00", w)

w = sr.window_from_state(st(["0804-1600", "0805-0100", "0805-0800"], "0805-0800",
                            "2026-08-04 13:00"), "0804")
report("跨夜：終點落在隔天", w == "2026-08-04 13:00–2026-08-05 08:00", w)

report("不自己補「（約N hrs）」（會被檔頭重複計算）", "hrs" not in w, w)

hdr = "\n".join(sv.header_from_lines(
    ["△ " + BODY], window="2026-08-04 13:00–2026-08-04 18:00", mmdd="0804"))
report("檔頭算出時數且不重複", "（約5hrs）" in hdr and hdr.count("hrs") == 1, hdr)

w = sr.window_from_state({"items": [], "checkpoint": ""}, "0804")
report("完全沒資料時回空字串（不炸）", w == "", repr(w))

# ── 中主題重排：相近名稱靠攏（2026-08-05 使用者訂案）──────────────────
report("三個熱浪靠攏、兩個野火靠攏",
       sr.order_topics(["亞洲熱浪", "歐洲野火", "南亞洪災", "歐洲熱浪",
                        "氣候乾旱", "野火", "火山", "熱浪", "水患"])
       == ["亞洲熱浪", "歐洲熱浪", "熱浪", "歐洲野火", "野火",
           "南亞洪災", "氣候乾旱", "火山", "水患"])
report("華州野火／加州野火靠攏",
       sr.order_topics(["華州野火", "國會動態", "加州野火"])
       == ["華州野火", "加州野火", "國會動態"])
report("只共用 1 字不湊在一起（政治 vs 政壇）",
       sr.order_topics(["政壇", "選舉", "政治"]) == ["政壇", "選舉", "政治"])
report("只共用 1 字不湊在一起（美股 vs 亞股）",
       sr.order_topics(["美股", "太空", "亞股"]) == ["美股", "太空", "亞股"])
report("完全無相近時等同原順序",
       sr.order_topics(["網球", "棒球", "足球"]) == ["網球", "棒球", "足球"])
report("重排不增減、不重複",
       sorted(sr.order_topics(["亞洲熱浪", "野火", "熱浪", "歐洲野火"]))
       == sorted(["亞洲熱浪", "野火", "熱浪", "歐洲野火"]))
report("空清單不炸", sr.order_topics([]) == [])
report("空字串中主題不炸", len(sr.order_topics(["", "野火", "歐洲野火"])) == 3)

_st = {"items": [{"raw_entry": "RT1111 (x) ▎a。▎畫面：b。▎無BITE。", "category":
                  {"大分類": "天氣", "中主題": m, "小分題": "s"}}
                 for m in ("亞洲熱浪", "歐洲野火", "熱浪", "野火")]}
report("0804 走排除名單：維持到貨順序",
       list(sr.group_items(_st, "0804")["天氣"]) == ["亞洲熱浪", "歐洲野火", "熱浪", "野火"])
report("0805 起套用重排",
       list(sr.group_items(_st, "0805")["天氣"]) == ["亞洲熱浪", "熱浪", "歐洲野火", "野火"])

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
