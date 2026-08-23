# -*- coding: utf-8 -*-
"""v1 薄殼：T/C 矩陣版晚班交接（試作，唯讀讀狀態檔，不寫回、不上雲）。

跟試作版（build_tc_matrix_b.py）的四個差異：
 1. 側錄「摺疊後」納入矩陣與總則數（2026-08-23 使用者裁決；原本拆開報有邏輯矛盾）。
    摺疊鍵 (src, 大分類, 中主題, 小分題)，跟正式版 JS 與 s2_render.py 的對帳鍵一致。
 2. 歷史列改用生產現成的 find_archive_dates() 動態掃 Archive，不再寫死 HIST_DAYS。
 3. 吃 --file / --base-date 參數，不寫死 Archive 舊檔。
 4. 標題／檔頭從狀態檔算，不寫死 0821。

⛔ 產出只寫本機（預設 D:\\Downloads），**不寫 G:\\ 雲端同步資料夾**，
   也刻意不取名 `{MMDD}晚班交接.html`——Apps Script 的 findLatest_() 是
   `title contains "晚班交接.html"` 取最新，同名會把編輯手機上開的那份換掉。
"""
import argparse
import inspect
import json
import os
import re
import sys

# 路徑由本檔位置推得，不寫死絕對路徑（repo 換位置也能跑）。
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))   # scripts/ ← 生產渲染器
sys.path.insert(0, HERE)                    # scripts/prototype/ ← 字典與 tag_tc()

import s2_render_html as H      # noqa: E402  生產渲染器，唯讀使用
import s2_render as R           # noqa: E402
import build_tc_matrix_0821 as BASE  # noqa: E402  字典與 tag_tc()

TPL = os.path.join(HERE, "_template_v1.html")

UNKNOWN = "未分類"

# ── 「未分類」可見桶（2026-08-23） ───────────────────────────────────────────
# 問題：`tag_tc()` 規則全部沒命中時會靜默塞進「社會」／「國際」，於是「判出來的」
#       和「猜的」在畫面上長得一模一樣，人看不出哪些需要複核。
# 作法：把那幾條兜底分支改成回傳 `未分類`，讓它在矩陣上自成一格。
# ⚠️ 這是**暫時的外掛改寫**（取原始碼字串替換後 exec），不是正統作法。
#    正式化時應該直接改分類器本身、讓它回傳「未分類」，而不是從外面改它的原始碼。
#    改寫對不上就 **直接失敗**，不靜默退回舊行為——靜默退回會讓畫面看起來正常、
#    但「未分類」永遠是 0，比壞掉更難發現。
_FALLBACK_PATCHES = [
    ('T.add("話題" if big == "話題" else "社會")', f'T.add("{UNKNOWN}")'),
    ('if not C:\n        C.add("國際")', f'if not C:\n        C.add("{UNKNOWN}")'),
    ('if big == "美國" and not T:\n        T.add("社會")',
     f'if big == "美國" and not T:\n        T.add("{UNKNOWN}")'),
    ('if big == "體育" and not C:\n        C.add("國際")',
     f'if big == "體育" and not C:\n        C.add("{UNKNOWN}")'),
]


def _make_tagger():
    src = inspect.getsource(BASE.tag_tc)
    for old, new in _FALLBACK_PATCHES:
        if old not in src:
            raise SystemExit(
                "ERROR: tag_tc() 的兜底分支改寫失敗，原始碼可能已變動：\n"
                f"  找不到：{old!r}\n"
                "  請對照 build_tc_matrix_0821.py::tag_tc() 更新 _FALLBACK_PATCHES。"
            )
        src = src.replace(old, new)
    ns = dict(BASE.__dict__)
    exec(compile(src, "<tag_tc+未分類>", "exec"), ns)
    return ns["tag_tc"]


tag_tc = _make_tagger()


def fold_side(rows):
    """把側錄列依 (src,大,中,小) 摺成單元；其餘列原樣保留，順序不變。

    正式版 txt 檔頭的「側錄 N 則」就是這個數字（s2_validate.side_units），
    網頁版若照列數算會把一段連線的十幾個 TC 當成十幾則，數字灌爆。
    """
    out, cur, curkey = [], None, None
    for r in rows:
        if r.get("kind") != "side":
            if cur:
                out.append(cur)
                cur, curkey = None, None
            out.append(r)
            continue
        k = (r.get("src"), r.get("big"), r.get("mid"), r.get("sub"))
        if cur and k == curkey:
            cur["text"] = cur["text"] + "\n" + (r.get("text") or "")
            cur["q"] = cur["q"] + " " + (r.get("q") or "")
            cur["segs"] += 1
            continue
        if cur:
            out.append(cur)
        cur, curkey = dict(r), k
        cur["segs"] = 1
    if cur:
        out.append(cur)
    return out


def build_histpills(mmdd, live_dir):
    """歷史列 pill：日期來源＝生產的 find_archive_dates()（動態掃 Archive）。

    連結沿用生產的 %%EXEC_URL%%?date=MMDD 佔位字串——正式代管時由
    Apps Script doGet() 換成部署固定網址。本機／tunnel 預覽沒有那一層，
    由 --local-links 換成 # （點了不動作），這是預期行為不是壞掉。
    """
    dates = H.find_archive_dates(live_dir)
    parts = [f'<a class="dpill on" href="%%EXEC_URL%%">今天 {mmdd[:2]}/{mmdd[2:]}</a>']
    for d in dates:
        parts.append(f'<a class="dpill" href="%%EXEC_URL%%?date={d}">{d[:2]}/{d[2:]}</a>')
    return "".join(parts), dates


def stats_line(rows, mmdd):
    """檔頭則數行。2026-08-23 使用者裁決：側錄計入總則數，並在括號裡分列。"""
    n_side = sum(1 for r in rows if r.get("kind") == "side")
    by = {}
    for r in rows:
        if r.get("kind") == "side":
            continue
        src = r.get("src") or "?"
        if src in ("CNN", "CNN_newsource"):
            src = "NS"
        by[src] = by.get(src, 0) + 1
    order = ["AP", "RT", "NS"]
    head = [f"{s} {by[s]}則" for s in order if by.get(s)]
    other = sum(v for k, v in by.items() if k not in order)
    if other:
        head.append(f"其他 {other}則")
    if n_side:
        head.append(f"側錄 {n_side}則")
    return f"收錄外電共 {len(rows)} 則（{'／'.join(head)}）"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True)
    p.add_argument("--base-date", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--local-links", action="store_true",
                   help="把 %%EXEC_URL%% 換成 # ，供本機／tunnel 預覽")
    args = p.parse_args()

    base = args.base_date
    if not base:
        m = re.search(r"(\d{4})-s2-state", os.path.basename(args.file))
        base = m.group(1) if m else ""
    st = json.load(open(args.file, encoding="utf-8-sig"))
    win = R.window_from_state(st, base) or st.get("window_local", "")
    head = H.build_header(st, base, win)
    title = head[0] if head else f"{base} 晚班交接"
    window_line = head[1] if len(head) > 1 else win

    raw = [r for r in H.collect(st, base) if r.get("kind") != "empty"]
    rows = fold_side(raw)

    out = []
    for r in rows:
        T, C, flags = tag_tc(r)
        out.append({
            "id": r.get("id") or "", "big": r.get("big") or "",
            "mid": r.get("mid") or "", "sub": r.get("sub") or "",
            "src": r.get("src") or "", "kind": r.get("kind") or "",
            "mark": r.get("mark") or "", "alert": r.get("alert") or "",
            "hilite": r.get("hilite") or "", "text": r.get("text") or "",
            "preview": BASE.slim_text(r.get("text") or ""),
            "segs": r.get("segs") or 1,
            "q": (r.get("q") or "")[:400],
            "T": T, "C": C, "flags": flags,
        })

    live_dir = os.path.dirname(os.path.abspath(args.file))
    pills, dates = build_histpills(base, live_dir)

    # 「未分類」只在**真的有**的時候才加進顯示用清單——沒有就不要多一列空格子。
    # ⚠️ 只加進「這一頁的顯示清單」，TC-字典.md（已裁決的權威名單）不動。
    t_list = list(BASE.T_FIXED)
    c_list = list(BASE.C_FIXED)
    c_fb = dict(BASE.C_FALLBACK)
    if any(UNKNOWN in r["T"] for r in out):
        t_list.append((UNKNOWN, "❓"))
    if any(UNKNOWN in r["C"] for r in out):
        c_list.append((UNKNOWN, ""))
        c_fb[UNKNOWN] = "❓"

    tpl = open(TPL, encoding="utf-8").read()
    html = (tpl
            .replace("__DATA__", json.dumps(out, ensure_ascii=False))
            .replace("__T__", json.dumps(t_list, ensure_ascii=False))
            .replace("__C__", json.dumps(c_list, ensure_ascii=False))
            .replace("__C_FALLBACK__", json.dumps(c_fb, ensure_ascii=False))
            .replace("__FLAGS__", json.dumps(BASE.FLAGS, ensure_ascii=False))
            .replace("__TITLE__", title + "（T/C 矩陣 v1）")
            .replace("__WINDOW__", window_line)
            .replace("__STATS__", stats_line(rows, base))
            .replace("__HISTPILLS__", pills))
    if args.local_links:
        html = html.replace("%%EXEC_URL%%", "#")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    n_side_raw = sum(1 for r in raw if r.get("kind") == "side")
    n_side = sum(1 for r in rows if r.get("kind") == "side")
    print(f"OK {args.out}（{os.path.getsize(args.out)} bytes）")
    print(f"   原始列 {len(raw)} → 摺疊後 {len(rows)} 則"
          f"（側錄 {n_side_raw} 列 → {n_side} 則）")
    print(f"   歷史列日期（動態掃 Archive）：{dates}")
    ut = sum(1 for r in out if UNKNOWN in r["T"])
    uc = sum(1 for r in out if UNKNOWN in r["C"])
    ue = sum(1 for r in out if UNKNOWN in r["T"] or UNKNOWN in r["C"])
    n = len(out) or 1
    print(f"   未分類：T {ut}／C {uc}／至少一軸 {ue}（共 {n} 則，{ue*100//n}%）")


if __name__ == "__main__":
    main()
