# -*- coding: utf-8 -*-
"""PROTOTYPE — T/C 矩陣網頁試作，B版專用（無 A/C 切換）。勿當生產渲染器。

重用 build_tc_matrix_0821.py 的字典／掛標邏輯，只換模板與輸出路徑。
含「歷史」試作：多產幾天的靜態頁，用相對連結互串，模擬釘頂歷史列的體驗。
"""
import json
import os

import build_tc_matrix_0821 as BASE

HERE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_ROOT = r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\Archive"
DL_DIR = r"D:\Downloads"

TODAY_MMDD = "0821"
TODAY_STATE = r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\Archive\20260821\0821-s2-state.json"
TODAY_OUT = os.path.join(DL_DIR, "0821晚班交接-TC矩陣B版.html")

HIST_DAYS = [
    ("0820", r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\Archive\20260820\0820-s2-state.json"),
    ("0819", r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\Archive\20260819\0819-s2-state.json"),
    ("0818", r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\Archive\20260818\0818-s2-state.json"),
    ("0817", r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\Archive\20260817\0817-s2-state.json"),
    ("0816", r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\Archive\20260816\0816-s2-state.json"),
]


def out_name(mmdd):
    if mmdd == TODAY_MMDD:
        return os.path.basename(TODAY_OUT)
    return f"0821晚班交接-TC矩陣B版-{mmdd}.html"


def build_histpills(active_mmdd):
    pills = []
    on = " on" if active_mmdd == TODAY_MMDD else ""
    pills.append(f'<a class="dpill{on}" href="{out_name(TODAY_MMDD)}">今天 {TODAY_MMDD[:2]}/{TODAY_MMDD[2:]}</a>')
    for mmdd, _ in HIST_DAYS:
        on = " on" if active_mmdd == mmdd else ""
        pills.append(f'<a class="dpill{on}" href="{out_name(mmdd)}">{mmdd[:2]}/{mmdd[2:]}</a>')
    return "".join(pills)


def build_page(mmdd, state_path, out_path):
    st = json.load(open(state_path, encoding="utf-8-sig"))
    window_line, stats_line = BASE.header_bits(st, mmdd)
    rows = BASE.H.collect(st, mmdd)
    out = []
    for r in rows:
        if r.get("kind") == "empty":
            continue
        T, C, flags = BASE.tag_tc(r)
        out.append({
            "id": r.get("id") or "",
            "big": r.get("big") or "",
            "mid": r.get("mid") or "",
            "sub": r.get("sub") or "",
            "src": r.get("src") or "",
            "kind": r.get("kind") or "",
            "mark": r.get("mark") or "",
            "alert": r.get("alert") or "",
            "hilite": r.get("hilite") or "",
            "text": r.get("text") or "",
            "preview": BASE.slim_text(r.get("text") or ""),
            "q": (r.get("q") or "")[:400],
            "T": T,
            "C": C,
            "flags": flags,
        })
    html_path = os.path.join(HERE, "_template_b.html")
    tpl = open(html_path, encoding="utf-8").read()
    html = tpl.replace("__DATA__", json.dumps(out, ensure_ascii=False))
    html = html.replace("__T__", json.dumps(BASE.T_FIXED, ensure_ascii=False))
    html = html.replace("__C__", json.dumps(BASE.C_FIXED, ensure_ascii=False))
    html = html.replace("__C_FALLBACK__", json.dumps(BASE.C_FALLBACK, ensure_ascii=False))
    html = html.replace("__FLAGS__", json.dumps(BASE.FLAGS, ensure_ascii=False))
    html = html.replace("__WINDOW__", window_line)
    html = html.replace("__STATS__", stats_line)
    html = html.replace("__HISTPILLS__", build_histpills(mmdd))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("OK", out_path, "bytes", os.path.getsize(out_path), "rows", len(out))


def main():
    build_page(TODAY_MMDD, TODAY_STATE, TODAY_OUT)
    for mmdd, state_path in HIST_DAYS:
        build_page(mmdd, state_path, os.path.join(DL_DIR, out_name(mmdd)))


if __name__ == "__main__":
    main()
