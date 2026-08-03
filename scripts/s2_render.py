# -*- coding: utf-8 -*-
"""S2 晚班交接 txt 渲染器（WP1）。

從 `{MMDD}-s2-state.json` **單向生成整份 txt**，取代 agent 每輪手寫整份
（0802 實測：一晚整併段約 30–50 萬字元輸出，render 下 agent 輸出趨近 0）。
狀態檔＝唯一真相源（txt 全由 AI 編寫、人工不改，2026-08-03 使用者確認），
render 是它的單向投影——**狀態檔裡沒有的東西，下一輪 render 就會消失**，
所以側錄也必須入狀態檔（見 `s2_state.py add-side`、`14-S2b`）。

生成順序（見 `common/plans/2026-08-02-S2提速計劃.md` 三、WP1）：
  檔頭（複用 `s2_validate.header_from_lines`，🔴 重大行取自 `_top.alerts`）
  → 樣板 16 格大分類順序（空格保留）
  → 每格 `【中主題】` → 小分題（裸行，`+` 分隔）→ 素材行
時段標記按 `first_seen_checkpoint` 自動補（不依賴 raw_entry 存不存標記——
現有 85 則舊資料沒帶標記）；🔴 素材標記從 raw_entry 保留（標過永久保留）。

用法：
  python s2_render.py --file "…/0802-s2-state.json" \
                      --out "…/0802晚班交接.txt" --window "14:00 - 09:00"
  （不給 --out ＝ 印到 stdout 預覽，不寫檔、不動狀態檔）
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2_validate as sv  # noqa: E402  共用行辨識 regex 與檔頭生成，不重寫一套

# ⚠️ 用 reconfigure 不用 TextIOWrapper：包第二層時（例如 s2_state 匯入 s2_validate）
# 舊寫法會讓其中一個 wrapper 被回收時關掉底層 buffer，整支腳本以 "I/O operation on
# closed file" 掛掉（2026-08-03 WP1 實錯）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # py<3.7
        pass

DEFAULT_FILE = r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\s2-state.json"

# 大分類樣板 16 格順序（`晚班交接大分類樣版.txt`）：第一格是機動的「時效性特殊」，
# 顯示名取自 `_top.special_category`，沒設就從 items 裡自動認（不在固定 15 格的那個）。
SPECIAL_SLOT = '(時效性特殊 例如"熊本地震")'
FIXED = ["大陸", "關稅", "美伊", "中東", "烏俄", "美國", "政治", "財經",
         "社會", "天氣", "體育", "科技", "娛樂", "話題"]

MARK_RE = re.compile(r"^\s*([△▲●])\s*")
RED_RE = re.compile(r"^\s*(🔴)\s*")


def load_state(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: 狀態檔讀取失敗（{e}）")
        sys.exit(2)


def strip_marks(entry):
    """剝掉 raw_entry 開頭既有的時段標記與 🔴，回傳 (有無🔴, 淨內容)。

    標記一律由 render 重算後補回：舊資料有的有、有的沒有，照抄會出現雙標記或漏標記。
    """
    e = entry.lstrip("\ufeff")
    m = MARK_RE.match(e)
    if m:
        e = e[m.end():]
    red = bool(RED_RE.match(e))
    if red:
        e = RED_RE.sub("", e, count=1)
    return red, e


def mmdd_shift(mmdd, days):
    """MMDD ± 天數（跨月正確；年份用今年，只影響閏月邊界）。"""
    d = datetime(datetime.now().year, int(mmdd[:2]), int(mmdd[2:])) + timedelta(days=days)
    return d.strftime("%m%d")


def mark_for(checkpoint, base_mmdd):
    """依 `first_seen_checkpoint` 推時段標記（WP1 前提三：由 render 自動補）。

    判準沿用 `13` 隔夜續掃節：23:00 前＝`△`、23:00–07:00＝`▲`、07:00–09:00＝`●`。
    checkpoint 標籤是 agent 自由命名的字串（`0802-1700`／`r8-0803-0100`／
    `exp-0803-0000`／`r13-0803-0910-RT補漏`），所以只認裡面的 4 位數字群：
    認得出當天／隔天 MMDD 就據以判日，認不出才退回「用最後一組數字當 HHMM」。
    23:00 整那輪算 `▲`：那一輪收到的素材是「23:00 當下才進來的」，不是「23:00 前既有」
    （0802 定版 txt 的 5 則實例即標 ▲）。
    補掃輪（例如 09:10 的 `r13-…-RT補掃` 撈回稍早漏掉的素材）用 checkpoint 判會標成 `●`，
    但它們其實屬更早的時段——這種要用 `s2_state.py set-mark` 在該則上寫死標記，見下方 override。
    """
    cp = checkpoint or ""
    toks = re.findall(r"\d{4}", cp)
    nxt = mmdd_shift(base_mmdd, 1) if base_mmdd else None
    day, hhmm = None, None
    for n, t in enumerate(toks):
        if day is not None:
            break
        if t == base_mmdd:
            day, hhmm = 0, int(toks[n + 1]) if n + 1 < len(toks) else None
        elif t == nxt:
            day, hhmm = 1, int(toks[n + 1]) if n + 1 < len(toks) else None
    if day is None:                      # 認不出日期：假設當天，取最後一組數字
        day = 0
        hhmm = int(toks[-1]) if toks else None
    if hhmm is None:
        return "△"
    if day >= 1:
        return "▲" if hhmm < 700 else "●"
    return "▲" if hhmm >= 2300 else "△"


def is_side(it):
    return str(it.get("source", "")).startswith("SIDE_")


def cat_of(it):
    c = it.get("category")
    if isinstance(c, dict):
        return (c.get("大分類") or "", c.get("中主題") or "", c.get("小分題") or "")
    if isinstance(c, str) and "/" in c:  # 舊字串格式，容錯
        p = [x.strip() for x in c.split("/", 2)] + ["", ""]
        return p[0], p[1], p[2]
    return "", "", ""


def render_item(it, base_mmdd):
    """素材行／側錄段落：`{時段標記} {🔴若有} {raw_entry 原文}`。

    raw_entry **零加工**輸出（側錄逐字不壓縮、不加 `▎`、TC 冒號格式照留，見 14-S2b）；
    側錄是多行的，標記只加在第一行（TC 行）行首。
    YouTube 兩行式（13b §4c）的網址行**照樣帶時段標記**，但標記與網址之間
    一定要有半形空格——`△https://…` 會黏成一串、網址點不開（2026-08-03 使用者訂正）。
    """
    red, body = strip_marks(it.get("raw_entry", "") or "")
    # 該則若有寫死的 `mark`（補掃輪等 checkpoint 判不準的情形，見 set-mark）優先用它
    mk = it.get("mark") if it.get("mark") in ("△", "▲", "●") else         mark_for(it.get("first_seen_checkpoint"), base_mmdd)
    prefix = mk + " "
    if red:
        prefix += "🔴 "
    lines = body.split("\n")
    # lstrip：raw_entry 首行若自帶前導空白，補上標記後會變成「△  內容」或讓網址位移；
    # prefix 固定以一個半形空格收尾，確保 `△ https://…` 不會黏在一起
    lines[0] = prefix + lines[0].lstrip()
    return lines


def group_items(state):
    """大分類 → 中主題 → 小分題 → [素材]，三層都保 items 原順序（保序 dict）。"""
    items = state.get("items", [])
    if isinstance(items, dict):                       # 容錯：dict 形式也吃
        items = [dict(id=k, **v) for k, v in items.items()]
    groups = {}
    for it in items:
        if it.get("script_status") == "note" or not (it.get("raw_entry") or "").strip():
            continue                                  # note＝待人工備註殼，沒有內容可出
        big, mid, sub = cat_of(it)
        if not big:
            big = "話題"                              # 沒分類的落到最後一格，不遺失
        groups.setdefault(big, {}).setdefault(mid, {}).setdefault(sub, []).append(it)
    return groups


def render_block(big, mids, base_mmdd):
    out = [f"======{big}======"]
    if not mids:
        out.append("")                                # 空格也保留（樣板 16 格）
    for mid, subs in mids.items():
        out.append("")                                # 中主題前空行
        if mid:
            out.append(f"【{mid}】")
        for n, (sub, its) in enumerate(subs.items()):
            if n:
                out.append("+")                       # 小分題之間用 `+`，不用空行
            if sub:
                out.append(sub)                       # 小分題＝裸行標題
            for it in its:
                out.extend(render_item(it, base_mmdd))
    out.append("")                                    # 大分類末尾空行
    return out


def build_body(state, base_mmdd):
    groups = group_items(state)
    # 第一格機動大分類的顯示名：_top 指定 > items 裡不屬固定 15 格的那個 > 樣板佔位
    special = (state.get("special_category") or "").strip()
    if not special:
        extra = [b for b in groups if b not in FIXED]
        special = extra[0] if extra else ""
    order = [special or SPECIAL_SLOT] + FIXED

    out = []
    for big in order:
        out += render_block(big, groups.get(big, {}), base_mmdd)
    # 落在 16 格之外的大分類（分類寫錯／又一個機動格）不吞掉，附在檔尾並回報
    orphan = [b for b in groups if b not in order]
    for big in orphan:
        out += render_block(big, groups[big], base_mmdd)
    if orphan:
        print("⚠️ 有大分類不在 16 格樣板裡（已附在檔尾，請修分類）：" + "／".join(orphan),
              file=sys.stderr)
    return out


def render(state, window="", base_mmdd="", date=""):
    body = build_body(state, base_mmdd)
    alerts = state.get("alerts") or []
    header = sv.header_from_lines(body, window, date, base_mmdd, alerts)
    return "\n".join(header + [""] + body).rstrip("\n") + "\n"


def write_atomic(path, text):
    """tmp + rename：中途失敗不留半殘 txt（每輪全量覆蓋，寫壞就沒有備份可回）。"""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def touch_last_render(state_path):
    """在狀態檔記下這次 render 時間（resume 的「上次render後有變動」靠它）。"""
    try:
        with open(state_path, encoding="utf-8-sig") as f:
            raw = json.load(f)
        raw["last_render_ts"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")
        tmp = state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=1)
        os.replace(tmp, state_path)
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ last_render_ts 未寫入（{e}）——txt 已產出，不影響本輪", file=sys.stderr)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", default=DEFAULT_FILE, help="狀態檔路徑")
    p.add_argument("--out", help="輸出 txt 路徑（省略＝印到 stdout 預覽，不寫檔）")
    p.add_argument("--window", default="",
                   help='時間窗，如 "14:00 - 09:00"；省略取狀態檔 window_local')
    p.add_argument("--base-date", default="", help="晚班當天 MMDD；省略由 --out 檔名或狀態檔推得")
    p.add_argument("--date", default="", help="YYYY-MM-DD，檔頭時間窗前綴用")
    p.add_argument("--no-touch-state", action="store_true", help="不回寫 last_render_ts")
    args = p.parse_args()

    state = load_state(args.file)
    base = args.base_date
    if not base and args.out:
        m = re.search(r"(\d{4})晚班交接", os.path.basename(args.out))
        base = m.group(1) if m else ""
    if not base:
        m = re.search(r"(\d{4})-s2-state", os.path.basename(args.file))
        base = m.group(1) if m else state.get("date", "")
    text = render(state, args.window or state.get("window_local", ""), base, args.date)
    if not args.out:
        sys.stdout.write(text)
        return
    write_atomic(args.out, text)
    if not args.no_touch_state:
        touch_last_render(args.file)
    print(f"OK 已渲染 {args.out}（{len(text.splitlines())} 行 / {len(text)} 字元）")


if __name__ == "__main__":
    main()
