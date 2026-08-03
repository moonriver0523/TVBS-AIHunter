# -*- coding: utf-8 -*-
"""S2 晚班交接 txt 渲染器（WP1 原型）。

從 s2-state.json 單向生成整份 txt，取代 agent 手寫整份（省 30–50 萬字元/晚輸出）。
狀態檔＝唯一真相源（txt 全由 AI 編寫、人工不改，2026-08-03 使用者確認）。

生成順序：檔頭（複用 s2_validate.stats 邏輯）→ 樣板 16 格大分類順序 →
每格 中主題【】→ 小分題 → 素材行。時段標記按 first_seen_checkpoint 自動補，
不依賴 raw_entry 存不存（現有 85 則舊資料沒帶標記）。🔴 從 raw_entry 保留。
"""
import argparse
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DEFAULT_FILE = r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\0802-s2-state.json"
TEMPLATE = ["(時效性特殊)", "大陸", "關稅", "美伊", "中東", "烏俄", "美國",
            "政治", "財經", "社會", "天氣", "體育", "科技", "娛樂", "話題"]
MARK_RE = re.compile(r"^([△▲●]\s*)+")
RED_RE = re.compile(r"^🔴\s*")


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        raw = json.load(f)
    return raw


def strip_marks(entry):
    """剝掉 raw_entry 開頭已有的時段標記與 🔴，回傳 (有無🔴, 淨內容)。"""
    e = entry
    m = MARK_RE.match(e)
    if m:
        e = e[m.end():]
    red = bool(RED_RE.match(e))
    if red:
        e = RED_RE.sub("", e, count=1)
    return red, e


def mark_for(checkpoint):
    """按 first_seen_checkpoint 推時段標記：
    0802（晚班當天，含 16:00 等純時間）→ △；
    0803：抽 HHMM，<0700 → ▲、>=0700 → ●。
    """
    cp = checkpoint or ""
    if "0803" in cp:
        m = re.search(r"(\d{4})(?!.*\d)", cp)  # 最後一組 4 位數＝HHMM
        hhmm = int(m.group(1)) if m else 0
        return "●" if hhmm >= 700 else "▲"
    return "△"


def is_side(it):
    return it.get("source") in ("SIDE_CNN", "SIDE_NHK")


def cat_of(it):
    c = it.get("category")
    if isinstance(c, dict):
        return c.get("大分類") or "話題", c.get("中主題") or "", c.get("小分題") or ""
    return "話題", "", ""


def render_material(it):
    """通訊社素材行：{時段標記} {🔴若有} {淨raw_entry}。"""
    red, body = strip_marks(it.get("raw_entry", ""))
    mk = mark_for(it.get("first_seen_checkpoint"))
    prefix = mk + " "
    if red:
        prefix += "🔴 "
    return prefix + body


def render_side(it):
    """側錄兩行式：raw_entry 原樣（TC 行＋內容行），行首補時段標記。"""
    red, body = strip_marks(it.get("raw_entry", ""))
    mk = mark_for(it.get("first_seen_checkpoint"))
    lines = body.split("\n")
    if lines:
        lines[0] = f"{mk} {lines[0]}"
    return "\n".join(lines)


def build_header(state, window):
    """複用 s2_validate.stats 的檔頭——直接 import 以免邏輯分叉。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "s2v", os.path.join(os.path.dirname(__file__), "s2_validate.py"))
    # stats 讀的是 txt 檔，這裡改用它的常數自己組。退而求其次：呼叫 stats 需 txt，
    # 原型階段先組基本行，正式版把 stats 的檔頭生成抽成可餵 state 的函式。
    return None  # 佔位，見 main 說明


def render(state, window=""):
    items = state.get("items", [])
    if isinstance(items, dict):
        items = [dict(id=k, **v) for k, v in items.items()]
    live = [it for it in items if it.get("script_status") != "note"]

    # 分組：大分類 → 中主題 → 小分題（保序，用 items 原順序）
    groups = {}  # big -> mid -> sub -> [items]
    for it in live:
        big, mid, sub = cat_of(it)
        groups.setdefault(big, {}).setdefault(mid, {}).setdefault(sub, []).append(it)

    out = []
    for big in TEMPLATE:
        disp = "熊本地震" if big == "(時效性特殊)" else big  # 機動格名稱由使用者定，原型佔位
        out.append(f"======{big}======")
        mids = groups.get(big) or groups.get(disp) or {}
        for mid, subs in mids.items():
            out.append("")               # 中主題前空行（使用者強調）
            if mid:
                out.append(f"【{mid}】")
            for sub, its in subs.items():
                if sub:
                    out.append(sub)       # 小分題裸行標題
                for it in its:
                    out.append(render_side(it) if is_side(it) else render_material(it))
        out.append("")                    # 大分類間空行
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", default=DEFAULT_FILE)
    p.add_argument("--window", default="")
    args = p.parse_args()
    state = load(args.file)
    print(render(state, args.window))


if __name__ == "__main__":
    main()
