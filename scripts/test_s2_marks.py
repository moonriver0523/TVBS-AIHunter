# -*- coding: utf-8 -*-
"""時段標記迴歸：新符號 ■ 生成正確，舊符號 ● 仍解析得動。

2026-08-04 使用者反映 `●` 與其他圓形標記易混淆，改用 `■`。**只改生成不改解析**
——舊資料不回頭改，已歸檔的 txt 整份都是 `●`，解析端若不再認得，那些行會
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

# ── 生成：07:00–09:00 那格一律產出 ■，不再產出 ● ──────────────────────
for cp, want, label in (
    ("0804-1600", "△", "16:00 → △"),
    ("0805-0100", "▲", "隔天 01:00 → ▲"),
    ("0805-0430", "▲", "隔天 04:30 → ▲"),
    ("0805-0700", "■", "隔天 07:00 → ■（原 ●）"),
    ("0805-0800", "■", "隔天 08:00 → ■（原 ●）"),
    ("0805-1000", "◆", "隔天 10:00 → ◆"),
    ("0805-1300", "◆", "隔天 13:00 → ◆"),
):
    got = sr.mark_for(cp, "0804")
    report(label, got == want, f"得到 {got!r}")

report("render 產物不含舊符號 ●",
       "●" not in sr.render_item({"raw_entry": BODY,
                                  "first_seen_checkpoint": "0805-0800"}, "0804")[0])
report("render 產物用 ■",
       sr.render_item({"raw_entry": BODY,
                       "first_seen_checkpoint": "0805-0800"}, "0804")[0].startswith("■ "))

# ── 相容：舊 txt 的 ● 行仍要被辨識成素材行（最重要的一組）─────────────
for mk in ("△", "▲", "■", "◆", "●"):
    line = f"{mk} {BODY}"
    mark, rest = sv.strip_mark(line)
    report(f"「{mk}」行仍 match LINE_RE", bool(sv.LINE_RE.match(rest)), repr(rest[:32]))
    report(f"「{mk}」被正確剝出", mark == mk, repr(mark))

old = [f"● {BODY}", "▲ RT2880 (NYSE) ▎美股開高。▎畫面：開市鐘。▎無BITE。▎00:55"]
hdr = "\n".join(sv.header_from_lines(old, mmdd="0803"))
report("舊 ● 行計入檔頭則數（應 2 則）", "共2則" in hdr, hdr)
report("舊 ● 計入隔夜續掃", "隔夜續掃" in hdr and "● 1則" in hdr, hdr)
report("舊 ● 有圖例可查", "●=" in hdr, hdr)

new = [f"■ {BODY}", "▲ RT2880 (NYSE) ▎美股開高。▎畫面：開市鐘。▎無BITE。▎00:55"]
hdr2 = "\n".join(sv.header_from_lines(new, mmdd="0805"))
report("新 ■ 計入隔夜續掃", "■ 1則" in hdr2, hdr2)
report("新檔圖例不出現舊符號 ●", "●" not in hdr2, hdr2)

# ── set-mark 的可選值 ────────────────────────────────────────────────
report("set-mark 接受 ■", "■" in sr.render_item(
    {"raw_entry": BODY, "first_seen_checkpoint": "0804-1600", "mark": "■"}, "0804")[0])
report("set-mark 寫死的舊 ● 仍生效（舊資料相容）", sr.render_item(
    {"raw_entry": BODY, "first_seen_checkpoint": "0804-1600", "mark": "●"},
    "0804")[0].startswith("● "))

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
