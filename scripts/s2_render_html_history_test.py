# -*- coding: utf-8 -*-
"""晚班交接 HTML 歷史瀏覽——測試版（2026-08-11）。

⛔ 這是獨立的測試腳本，**不修改、不匯入覆寫任何production檔案**：
   `s2_render_html.py`／`s2_render.py` 全部原封不動、只 import 使用其現成函式。
   輸出也不寫回 `G:\\...\\自動掃帶系統\\`，只寫到使用者指定的測試資料夾。

做法：對「今天＋最近 N 天 Archive」各自呼叫production的 build_html() 產生
完整頁面（跟正式站一模一樣），再疊一條「歷史列」在檔頭下方——**只加這一塊**，
其餘 CSS／JS／篩選／複製功能全部沿用production頁面，不會有兩份互相漂移的風險。

**本機測試的連結是相對檔名**（`0810.html`／`0811.html`…），所以雙擊本機檔案
就能直接點著切換，不需要架站。**正式上線會換成 Apps Script 的 `?date=MMDD`**
查詢參數（見 `scripts/appsscript/晚班交接WebApp_v2test.gs` 草稿）——那邊還沒動，
上線前只是把這裡的 href 產生方式換一種寫法，頁面外觀跟互動邏輯不會變。

用法：
  python scripts/s2_render_html_history_test.py \\
      --file "G:\\我的雲端硬碟\\Claude共用\\自動掃帶系統\\0811-s2-state.json" \\
      --out-dir "<測試輸出資料夾>" --days 5
"""
import argparse
import html
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_render as R          # noqa: E402  （production，唯讀使用）
import s2_render_html as H     # noqa: E402  （production，唯讀使用）


def find_archive_dates(live_dir, n):
    """在 live_dir/Archive/{YYYYMMDD}/ 底下找過去 n 天的狀態檔，回傳新到舊。"""
    archive_dir = os.path.join(live_dir, "Archive")
    out = []
    if not os.path.isdir(archive_dir):
        return out
    for name in sorted(os.listdir(archive_dir), reverse=True):
        if not re.match(r"^\d{8}$", name):
            continue
        mmdd = name[4:]
        state_path = os.path.join(archive_dir, name, f"{mmdd}-s2-state.json")
        if os.path.isfile(state_path):
            out.append((mmdd, state_path))
        if len(out) >= n:
            break
    return out


DATEBAR_CSS = """
:root{--histh:0px}
.histbar{display:flex;gap:6px;overflow-x:auto;padding:6px 14px 10px;
         border-bottom:1px solid var(--line);-webkit-overflow-scrolling:touch;
         position:sticky;top:0;z-index:11;background:var(--bg)}
.histbar::-webkit-scrollbar{height:4px}
.hlabel{flex:none;font-size:12px;color:var(--mut);align-self:center;margin-right:2px}
.dpill{flex:none;padding:4px 11px;font-size:12px;border:1px solid var(--line);
       border-radius:12px;color:var(--mut);text-decoration:none;white-space:nowrap}
.dpill.on{background:var(--chipon);color:#fff;border-color:var(--chipon);font-weight:600}
/* 歷史列跟原本會收合的檔頭（.top）是兩件事：檔頭捲走就捲走，歷史列跟搜尋列
   一樣永遠釘頂。兩條 sticky 疊在一起不能都用 top:0（會互相蓋住），下面的搜尋列
   要讓出「歷史列的高度」——用行內 script 量測實際高度寫進 --histh，
   而不是用猜的 px 值，字級／螢幕寬度變動時才不會兩者間出現縫隙或重疊。*/
.sticky{top:var(--histh)}
/* 桌機版切成 CSS Grid（body{display:grid;grid-template-areas:"panel top" "panel
   sticky" "panel main"}），.histbar 沒配 grid-area 會被自動丟到孤兒格、擠到左欄
   最下面看不到——這裡補一列「hist」，讓它卡在 top 跟 sticky 之間，跟手機版同位置。*/
@media (min-width:820px) and (hover:hover){
  body{grid-template-areas:"panel top" "panel hist" "panel sticky" "panel main"}
  .histbar{grid-area:hist}
}
"""


def build_datebar(entries, current_mmdd, href_for):
    """entries: [(mmdd, path, is_today), ...] 新到舊。"""
    parts = ['<div class="histbar" id="histbar"><span class="hlabel">歷史：</span>']
    for mmdd, _path, is_today in entries:
        cls = "dpill on" if mmdd == current_mmdd else "dpill"
        label = f"今天 {mmdd[:2]}/{mmdd[2:]}" if is_today else f"{mmdd[:2]}/{mmdd[2:]}"
        parts.append(f'<a class="{cls}" href="{html.escape(href_for(mmdd))}">{html.escape(label)}</a>')
    parts.append('</div>')
    parts.append(
        '<script>(function(){var h=document.getElementById("histbar");'
        'if(h)document.documentElement.style.setProperty("--histh",h.offsetHeight+"px");'
        '})();</script>'
    )
    return "".join(parts)


def inject_datebar(page_html, datebar_html):
    page_html = page_html.replace("</style></head><body>",
                                   DATEBAR_CSS + "</style></head><body>", 1)
    page_html = page_html.replace('<div class="sticky">',
                                   datebar_html + '<div class="sticky">', 1)
    return page_html


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True, help="今天的狀態檔（正式版路徑，唯讀）")
    p.add_argument("--out-dir", required=True, help="測試輸出資料夾（不可＝正式資料夾）")
    p.add_argument("--days", type=int, default=5, help="往前找幾天的 Archive")
    args = p.parse_args()

    live_dir = os.path.dirname(os.path.abspath(args.file))
    out_dir = os.path.abspath(args.out_dir)
    if os.path.normcase(out_dir) == os.path.normcase(live_dir):
        sys.exit("⛔ --out-dir 不可以是正式資料夾，這支只能寫測試路徑")
    os.makedirs(out_dir, exist_ok=True)

    m = re.search(r"(\d{4})-s2-state", os.path.basename(args.file))
    today_mmdd = m.group(1) if m else ""
    if not today_mmdd:
        sys.exit("⛔ --file 檔名要含 {MMDD}-s2-state")

    entries = [(today_mmdd, args.file, True)] + [
        (mmdd, path, False) for mmdd, path in find_archive_dates(live_dir, args.days)
    ]

    def href_for(mmdd):
        return f"{mmdd}.html"

    written = []
    for mmdd, path, is_today in entries:
        state = R.load_state(path)
        win = R.window_from_state(state, mmdd) or state.get("window_local", "")
        page = H.build_html(state, mmdd, win)
        page = inject_datebar(page, build_datebar(entries, mmdd, href_for))
        out_path = os.path.join(out_dir, f"{mmdd}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(page)
        written.append(out_path)
        print(f"OK {mmdd}.html（{'今天' if is_today else '歷史'}）")

    print(f"\n本機測試：雙擊開 {written[0]}，頂端多一條「歷史」列，點其他日期可切換。")
    print("⚠️ 這是本機示範用相對檔名連結；正式上線後會改用 Apps Script 的 ?date= 參數，"
          "外觀與互動不變，但要另外部署 Apps Script。")


if __name__ == "__main__":
    main()
