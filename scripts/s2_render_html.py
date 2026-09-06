# -*- coding: utf-8 -*-
"""晚班交接 HTML 檢視版——搜尋／篩選／分層複製（2026-08-09）／歷史瀏覽（2026-08-11）。

**這是第二個投影，不是第二份真相。** WP1 之後 txt 已經是「從狀態檔全量渲染」，
這支只是多一個輸出目標：

    狀態檔（唯一真相源）
      ├─→ s2_render.py  → 晚班交接.txt   ← 權威產物，品質掃驗的是它
      └─→ 本支            → 晚班交接.html ← 純檢視層，衍生物

⛔ **絕不重寫排版邏輯**：分組、時段標記、素材行文字全部直接呼叫 `s2_render`
的現成函式（`group_items`／`render_item`／`mark_for`）。HTML 顯示的每一行
**與 txt 逐字相同**——所以複製出去貼到別的系統不會有格式差異，
也不會出現「兩份輸出各自演化」的維護地獄（`13b` 立案時就點名這個風險）。

使用情境（2026-08-09 使用者說明）：
  1. 編輯先在畫面上看整份列表
  2. 拆分派稿單給記者時**複製貼到別的系統**——顆粒度是「單則素材」或
     「整個中主題／小分題一起」，所以三種層級都要有複製鈕。

⚠️ **Google Drive 網頁預覽不會執行 JS**，篩選會失效。要開本機同步的那份
（`G:\\我的雲端硬碟\\...`），雙擊即可。

用法：
  python scripts/s2_render_html.py --file <state.json> --out <晚班交接.html>
  省略 --out 就印到 stdout。
"""
import argparse
import base64
import html
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_render as R  # noqa: E402

def hilite_of(text):
    """有沒有畫面亮點標記 🔖。有就回 `"🔖"`，沒有回空字串。

    **一個鈕就夠**（2026-08-11 使用者訂）：不分「畫面好」「搖晃瞬間」或日後新增的
    任何標籤，只要標了 🔖 就是「這則畫面值得看」，編輯要的就是這一份清單。
    ⛔ 不要再依括號裡的標籤拆成多個鈕——拆開的版本做過，兩個鈕反而讓人要點兩次
    才看得到全部，而且側錄兩行式沒有備註括號，會整批漏在篩選外。

    ⚠️ 只看**第一行**：🔖 標在素材代碼前面（🔴／🟡／⭐ 之後），一定在第一行；
    往下多看會把側錄內容行裡偶然出現的符號也算進來。
    """
    return "🔖" if "🔖" in (text or "").split("\n")[0] else ""


def fresh_info(state, base_mmdd):
    """本輪（最新一輪掃帶）是哪一輪：回傳 `(比對用鍵, 顯示用 checkpoint 字串)`。

    2026-09-04 使用者要求：側邊欄要能「只看最新」——只列最近一輪新入庫的素材。
    2026-09-04 追記：輪次之間人工要求整併的素材（CNN/NHK 側錄、韓聯社/CNA）
    也要算「最新」，直到下一輪掃帶把頂層 checkpoint 推進為止——所以下面
    `is_fresh()` 比的是「>= 本輪 checkpoint」的時間窗，不是精確相等。

    ⚠️ **頂層 `checkpoint` 是唯一真相**（agent 每輪 `set-top checkpoint` 寫的就是
    「現在這輪」）。它在、但沒有任何一則的 `first_seen_checkpoint` 對得上，
    正確答案就是「本輪 0 則新增」——⛔ 不可退回「取最晚的一則」，那會把上一輪
    整批改標成新一輪，比沒有這個篩選更糟。只有頂層完全沒有時才用最晚的當備援
    （沿用 `window_from_state()` 同一套備援語意）。

    比對用 `R.checkpoint_time()` 的 `(第幾天, HHMM)` 而不是字串相等：checkpoint
    標籤是 agent 自由命名的（`0904-1100`／`r13-0904-1100-RT補漏`），字串比對會把
    同一輪的兩種寫法當成兩輪。`hhmm is None`（整串認不出時間）一律不算數，
    否則兩個都認不出的字串會互相「相等」而被誤判成同一輪。
    """
    def key(cp):
        _day, hhmm = R.checkpoint_time(cp or "", base_mmdd)
        return None if hhmm is None else (_day, hhmm)

    top = (state.get("checkpoint") or "").strip()
    if top:
        return key(top), top
    items = state.get("items") or []
    vals = items.values() if isinstance(items, dict) else items
    best, best_cp = None, ""
    for it in vals:
        cp = (it or {}).get("first_seen_checkpoint") or ""
        k = key(cp)
        if k and (best is None or k > best):
            best, best_cp = k, cp
    return best, best_cp


def fresh_label(cp):
    """`0904-1100` → `09/04 11:00`；認不出格式就原樣回傳（不要空字串，
    使用者至少還看得到 agent 寫的原標籤）。"""
    m = re.search(r"(\d{2})(\d{2})-(\d{2})(\d{2})", cp or "")
    if not m:
        return cp or ""
    return f"{m.group(1)}/{m.group(2)} {m.group(3)}:{m.group(4)}"


def logo_data_uri():
    """左側篩選欄底部的 LOGO（2026-08-11 使用者要求，只在桌機顯示）。

    ⚠️ **一定要 base64 內嵌**，不能寫外部檔案路徑：這份 HTML 會被丟上 Google Drive、
    由 Apps Script 給編輯開，那個情境下相對路徑抓不到任何檔案，只會變破圖。

    ⚠️ **體積要顧**：HTML 每輪重產、每天十幾份留在 Drive。所以資產存 160px WebP
    （6.7KB → base64 約 8KB）；同一張圖存 PNG 要 45KB、base64 58KB，差七倍。
    顯示縮到 80px，等於 2x 圖，高解析螢幕也不糊。

    ⛔ 找不到檔案就回空字串——**LOGO 是裝飾，不能讓它害整份 HTML 產不出來**。
    """
    p = os.path.join(HERE, "assets", "logo_miniverse.webp")
    try:
        with open(p, "rb") as f:
            return "data:image/webp;base64," + base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return ""

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def ordered_groups(state, base_mmdd):
    """大分類依**樣板固定順序**回傳，與 txt 完全一致（2026-08-09 訂正）。

    ⚠️ 原本直接吃 `group_items()` 的 dict 順序，那是**素材出現順序**——
    每輪都可能不一樣，跟 txt 的固定 16 格對不起來（使用者實測發現）。
    txt 的順序邏輯在 `build_body()`：`[機動格] + FIXED`，樣板外的附在最後。
    這裡照抄同一套判斷，**不要自己另外排**——兩邊各排各的，遲早又會分岔。
    """
    groups = R.group_items(state, base_mmdd)
    special = (state.get("special_category") or "").strip()
    if not special:
        extra = [b for b in groups if b not in R.FIXED]
        special = extra[0] if extra else ""
    order = [special or R.SPECIAL_SLOT] + R.FIXED
    out = [(b, groups[b]) for b in order if groups.get(b)]      # 空格不進 HTML
    out += [(b, groups[b]) for b in groups if b not in order]   # 樣板外的附在最後
    return out


def collect(state, base_mmdd):
    """把狀態檔攤成 HTML 要的扁平結構。

    每一則都帶著 `text`＝**txt 裡那一行的逐字內容**（複製出去就是它），
    外加篩選要用的欄位。分組順序完全交給 `R.group_items()`，不自己排。
    """
    rows = []
    fkey, _fcp = fresh_info(state, base_mmdd)

    def is_fresh(cp):
        if not fkey:
            return ""
        day, hhmm = R.checkpoint_time(cp or "", base_mmdd)
        # 圖示用 🔥 不用 🆕（2026-09-04 使用者回報 🆕 在他的環境顯示成空白方框）。
        # ⚠️ 比 `>=` 不是 `==`（2026-09-04 追記）：輪次中途人工整併進來的素材
        # （CNN/NHK 側錄、韓聯社/CNA）first_seen_checkpoint 會晚於本輪 checkpoint
        # （agent 掃帶收工才 set-top，整併是收工後才做的），但編輯仍要看到它們
        # 算「最新」，直到下一輪 set-top 把頂層 checkpoint 推進、fkey 跟著變大
        # 為止——那時這批間隔期間的素材才會連同上一輪一起自然掉出「只看最新」。
        return "🔥" if (hhmm is not None and (day, hhmm) >= fkey) else ""

    for big, mids in ordered_groups(state, base_mmdd):
        for mid, subs in mids.items():
            if not subs:
                # 常駐中主題（2026-08-11）：今天 0 則，group_items() 塞了空字典進來。
                # HTML 是純資料驅動（前端只認 rows），不塞一個佔位 row 這個空標題
                # 在網頁版就會直接消失——kind='empty' 讓前端只印標題、不算則數、
                # 不出項目行，跟 txt 的 render_block 行為對齊。
                rows.append({
                    "big": big or "", "mid": mid or "", "sub": "", "id": "",
                    "src": "", "kind": "empty", "mark": "", "alert": "", "hilite": "",
                    "fresh": "",
                    "cp": "", "dur": "", "bite": False, "text": "",
                    "q": f"{big} {mid}".strip().lower(),
                })
                continue
            for sub, its in subs.items():
                for it in its:
                    lines = R.render_item(it, base_mmdd)
                    if not lines:
                        continue
                    text = "\n".join(lines)
                    f = it.get("fields") or {}
                    src = it.get("source") or ""
                    # 三類要分開算、也要能分開篩（2026-08-09）：
                    #   wire＝通訊社三段式素材／url＝YouTube 等網址素材／side＝CNN、NHK 側錄
                    # ⚠️ 檔頭的「收錄外電共 N 則」**含 YT（算「其他」）、不含側錄**
                    #   （0802 訂案：一段連線常切成十幾個 TC，計入會把則數灌爆）。
                    #   網頁版的筆數必須照同一套語意，否則同一份資料兩個數字，編輯會困惑。
                    item_id = it.get("id") or ""
                    is_oth = item_id.startswith("OTH")
                    kind = "side" if src.startswith("SIDE_") else ("url" if (src == "YT" or is_oth) else "wire")
                    # 顯示用來源代碼：source=="YT" 在狀態檔裡是解析器用的統一標記
                    # （見 s2_parse.py，跟 YNA/CNA 是不是網址素材無關），韓聯社／CNA
                    # 都會落在這裡，要另外從 id 前綴分出來才能對到 SRC_LABEL 顯示成
                    # 「韓聯社」「CNA」，否則全部顯示成籠統的「其他」。
                    # OTH（common/17，2026-09-05）：source 欄位是實際平台名（X／QAB／IG…），
                    # 五花八門不利篩選——一律併進同一個「其他」篩選鍵，不逐平台各開一個 chip。
                    if src == "YT" and item_id.startswith("YNA"):
                        display_src = "YNA"
                    elif src == "YT" and item_id.startswith("CNA"):
                        display_src = "CNA"
                    elif src == "YT" or is_oth:
                        display_src = "OTH"
                    else:
                        display_src = src
                    rows.append({
                        "big": big or "", "mid": mid or "", "sub": sub or "",
                        "id": item_id,
                        "src": display_src, "kind": kind,
                        "mark": R.mark_for(it.get("first_seen_checkpoint") or "", base_mmdd) or "",
                        # 重大層級（2026-08-09 使用者要求可篩）：🔴＝檔頭重大、🟡＝重大未進檔頭、
                        # ⭐＝推薦（2026-08-19，三者互斥）。從**渲染後的成品**認，不從
                        # raw_entry——render 會依 alerts 補標記，只看 raw_entry 會漏掉
                        # 那些「檔頭有、正文還沒補」的則。
                        "alert": ("🔴" if "🔴" in text[:8] else
                                  ("🟡" if "🟡" in text[:8] else
                                   ("⭐" if "⭐" in text[:8] else ""))),
                        # 畫面亮點（2026-08-11 使用者要求可篩）：見 hilite_of。
                        "hilite": hilite_of(text),
                        # 本輪新增（2026-09-04 使用者要求可篩）：見 fresh_info。
                        # 判準是 first_seen_checkpoint＝入庫那輪，不是 last_checked——
                        # 「新一輪」問的是「這輪多了什麼」，不是「這輪查過什麼」。
                        "fresh": is_fresh(it.get("first_seen_checkpoint") or ""),
                        "cp": it.get("first_seen_checkpoint") or "",
                        "dur": f.get("duration") or "",
                        "bite": bool(f.get("bite")),
                        "text": text,
                        # 搜尋用：把使用者可能會想找的字全串起來，前端只比對這一欄
                        "q": " ".join([
                            it.get("id") or "", f.get("summary") or "",
                            f.get("footage") or "", " ".join(f.get("notes") or []),
                            " ".join(f.get("bite") or []), text,
                        ]).lower(),
                    })
    return rows


def build_header(state, base_mmdd, window):
    """檔頭沿用 txt 的前幾行，不另外算——數字只有一個來源。"""
    text = R.render(state, window, base_mmdd, "")
    head = []
    for ln in text.split("\n"):
        if ln.startswith("======"):
            break
        if ln.strip():
            head.append(ln)
    return head


TEMPLATE = """<!doctype html>
<html lang="zh-Hant"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#fbfbfc;--panelbg:#f4f5f7;--fg:#1c1e22;--mut:#6b7078;--line:#e2e4e8;--card:#f1f2f5;
      --accent:#1558c4;--accent-fg:#fff;--chip:#eef0f4;--chipfg:#3a3e46;--chipon:#1558c4;--warn:#c02f2f;
      --warntint:#fdecec;--big:#c8481c;--subbg:#e6e8ec;--subfg:#2b2f36;
      --midbg:#1558c4;--midfg:#fff;--sidetint:#eef0f3;--urltint:#eaf1fd;--kindfg:#5b6068;
      --shadow:0 1px 2px rgba(20,22,26,.06)}
@media (prefers-color-scheme:dark){
:root{--bg:#15171b;--panelbg:#1a1c21;--fg:#e7e8ea;--mut:#9198a3;--line:#2b2e35;--card:#1d2026;
      --accent:#5d9bff;--accent-fg:#0b1220;--chip:#22252c;--chipfg:#c7cad0;--chipon:#3d6fc4;--warn:#ff6b6b;
      --warntint:#3a1f22;--big:#ff8a5c;--subbg:#2b2f37;--subfg:#e7e8ea;
      --midbg:#2c5fa8;--midfg:#fff;--sidetint:#20232a;--urltint:#1b2532;--kindfg:#9198a3;
      --shadow:0 1px 3px rgba(0,0,0,.35)}}
*{box-sizing:border-box}
::selection{background:var(--accent);color:var(--accent-fg)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
body{margin:0;background:var(--bg);color:var(--fg);
     font:15px/1.65 "Inter","Noto Sans TC","Microsoft JhengHei",system-ui,sans-serif;
     -webkit-font-smoothing:antialiased}
/* 檔頭分兩塊：標題與檔頭資訊**隨頁面捲走**，只有搜尋列釘在頂端。
   原本整組（標題＋檔頭＋三排篩選＋兩個鈕）都 sticky，手機上吃掉半個螢幕，
   素材瀏覽空間所剩無幾（2026-08-09 使用者實測回報）。 */
.top{padding:14px 16px 6px}
.sticky{position:sticky;top:var(--histh);z-index:9;background:var(--bg);
        border-bottom:1px solid var(--line);padding:8px 16px 10px}
h1{font-size:19px;font-weight:800;letter-spacing:-.01em;margin:0}
.tgl{display:flex;align-items:center;gap:7px;cursor:pointer;user-select:none}
.caret{color:var(--mut);font-size:12px;transition:transform .15s}
.caret.open{transform:rotate(180deg)}
.meta{color:var(--mut);font-size:13px;line-height:1.8;white-space:pre-wrap;margin-top:5px}
/* 產出時間要**永遠看得到**：它藏在收合的檔頭裡就失去警示作用了。
   資料若停在幾小時前，編輯一眼就該察覺，而不是照著舊清單發稿。 */
.stamp{margin-left:auto;color:var(--mut);font-size:12px;white-space:nowrap;
  padding:2px 9px;border-radius:10px;background:var(--chip)}
.stamp.stale{color:var(--warn);font-weight:700;background:var(--warntint)}
.off{display:none!important}

/* 歷史列（2026-08-11 上線）：跟會收合的檔頭（.top）是兩件事——檔頭捲走就捲走，
   歷史列跟下面的搜尋列一樣永遠釘頂。兩條 sticky 疊在一起不能都用 top:0（會互相
   蓋住），下面的搜尋列要讓出「歷史列的高度」——用行內 script 量測實際高度寫進
   --histh，不是猜一個 px 值，字級／螢幕寬度變動時才不會兩者間出現縫隙或重疊。 */
:root{--histh:0px}
.histbar{display:flex;gap:6px;overflow-x:auto;padding:8px 16px 11px;
         border-bottom:1px solid var(--line);-webkit-overflow-scrolling:touch;
         position:sticky;top:0;z-index:11;background:var(--bg)}
.histbar::-webkit-scrollbar{height:4px}
.hlabel{flex:none;font-size:12px;color:var(--mut);align-self:center;margin-right:2px}
.dpill{flex:none;padding:4px 12px;font-size:12px;border:1px solid var(--line);
       border-radius:999px;color:var(--mut);text-decoration:none;white-space:nowrap;
       transition:border-color .15s,color .15s}
.dpill:hover{border-color:var(--accent);color:var(--accent)}
.dpill.on{background:var(--chipon);color:#fff;border-color:var(--chipon);font-weight:700}
.dpill.on:hover{color:#fff}

/* ══ 篩選面板 ══════════════════════════════════════════════════
   桌機：常駐左側欄（橫向空間本來就有，不必開關）
   手機：下方彈出，**蓋住**下半螢幕而不推擠內容——「一展開就把素材往下推」
        正是 2026-08-09 使用者回報的痛點，換成側邊只是把方向改成往旁邊推，
        同樣沒解決，所以用覆蓋式。拇指落點也在螢幕下方，比側邊好按。 */
#panel{}
.grip{display:none}
.phead{display:none}
.fgroup{margin-bottom:14px}
.flabel{font-size:11px;font-weight:700;letter-spacing:.04em;color:var(--mut);margin-bottom:5px}
#scrim{display:none}
#fab{display:none}
/* LOGO：**預設不顯示**。手機版是下方彈出的操作面板，高度本來就吃緊
   （max-height:62vh），多一塊裝飾只會把篩選鈕擠出可視範圍——使用者明確說
   「PC 版就好，手機版不用改」。所以只在桌機那段 media query 裡打開。 */
.brand{display:none}

/* ── 桌機：常駐左側欄 ── */
@media (min-width:820px) and (hover:hover){
  body{display:grid;grid-template-columns:216px 1fr;
       grid-template-areas:"panel top" "panel hist" "panel sticky" "panel main"}
  .top{grid-area:top}
  .histbar{grid-area:hist}
  .sticky{grid-area:sticky}
  main{grid-area:main}
  #panel{grid-area:panel;position:sticky;top:0;align-self:start;max-height:100vh;
         overflow:auto;padding:16px 14px;background:var(--panelbg);
         border-right:1px solid var(--line)}
  #panel .bar{margin-top:2px}
  .chip{font-size:12px;padding:3px 8px}
  /* LOGO 收在左欄最下方。`margin-top:auto` 需要 #panel 是 flex 縱向排列，
     所以這裡一起把它改成 flex——原本是預設 block，不影響上面各群組的排版。
     圖是圓形構圖、四角是黑底，`border-radius:50%` 把黑角切掉，
     淺色主題下才不會變成一塊突兀的黑方塊。 */
  #panel{display:flex;flex-direction:column}
  .brand{display:block;margin:18px auto 4px;text-align:center;text-decoration:none;
         opacity:.85;transition:opacity .2s,transform .2s}
  .brand:hover{opacity:1;transform:translateY(-1px)}
  .brand img{width:80px;height:80px;border-radius:50%;display:block;margin:0 auto}
}

/* ── 手機／窄螢幕：下方彈出 ── */
@media (max-width:819px),(hover:none),(pointer:coarse){
  #panel{position:fixed;left:0;right:0;bottom:0;z-index:60;background:var(--bg);
         border-top:1px solid var(--line);border-radius:14px 14px 0 0;
         padding:6px 14px 18px;max-height:62vh;overflow:auto;
         box-shadow:0 -6px 24px rgba(0,0,0,.25);
         transform:translateY(102%);transition:transform .22s ease}
  #panel.open{transform:translateY(0)}
  .grip{display:block;width:38px;height:4px;border-radius:2px;background:var(--line);
        margin:2px auto 8px}
  .phead{display:flex;align-items:center;justify-content:space-between;
         font-weight:700;margin-bottom:8px}
  #scrim{display:block;position:fixed;inset:0;background:rgba(0,0,0,.35);
         z-index:59;opacity:0;pointer-events:none;transition:opacity .22s}
  #scrim.open{opacity:1;pointer-events:auto}
  /* 浮動鈕放右下角＝拇指自然落點 */
  #fab{display:block;position:fixed;right:14px;bottom:16px;z-index:58;
       padding:11px 18px;font-size:14px;font-weight:700;border:none;border-radius:999px;
       background:var(--accent);color:var(--accent-fg);box-shadow:0 3px 14px rgba(0,0,0,.3);
       transition:background .15s}
  #fab.on{background:var(--warn);color:#fff}
  main{padding-bottom:76px}   /* 別讓最後一則被浮動鈕蓋住 */
}
.alert{color:var(--warn);font-weight:700}
.bar{display:flex;flex-wrap:wrap;gap:7px;align-items:center;margin-top:8px}
input[type=search]{flex:1;min-width:180px;padding:8px 12px;font-size:14px;
  border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);
  transition:border-color .15s,box-shadow .15s}
input[type=search]:focus-visible{border-color:var(--accent);
  box-shadow:0 0 0 3px color-mix(in oklab,var(--accent) 22%,transparent);outline:none}
.chip{padding:4px 11px;font-size:12.5px;border:1px solid var(--line);border-radius:999px;
      background:var(--chip);color:var(--chipfg);cursor:pointer;user-select:none;
      transition:border-color .15s,background .15s,color .15s}
.chip:hover{border-color:var(--accent);color:var(--accent)}
.chip.on{background:var(--chipon);color:#fff;border-color:var(--chipon)}
.chip.on:hover{color:#fff}
.count{color:var(--mut);font-size:12.5px;font-variant-numeric:tabular-nums;margin-left:auto}
button.act{padding:5px 11px;font-size:12px;font-weight:600;border:1px solid var(--line);
  border-radius:7px;background:var(--card);color:var(--fg);cursor:pointer;
  transition:border-color .15s,color .15s,background .15s}
button.act:hover{border-color:var(--accent);color:var(--accent);background:var(--urltint)}
main{padding:10px 16px 60px}
/* 三層各給一種辨識方式（2026-08-09 使用者訂）：
   大分類＝橘紅色字＋同色底線／中主題＝維持原本的 accent 色／小分題＝深底反白框。
   ⚠️ 顏色要用 token 定義，深色模式才不會變成黑底上的深橘。 */
.big{margin:26px 0 10px;padding:6px 0;
     border-top:2px solid var(--big);border-bottom:2px solid var(--big);
     font-size:15px;font-weight:800;letter-spacing:.06em;color:var(--big)}
.big:first-child{margin-top:4px}
.mid{margin:16px 0 6px;font-weight:700}
/* 中主題＝藍底白字色塊，去掉【】（2026-08-09 使用者訂）。
   前後各留一個半形空格才不會貼著色塊邊緣；空格寫在文字裡而不是靠 padding，
   使用者要的就是「 新加坡國慶 」這個形狀。⚠️ 只有網頁版這樣，TXT 版仍是【】。 */
.mid .midtxt{display:inline-block;padding:3px 8px;border-radius:5px;font-size:13.5px;
     background:var(--midbg);color:var(--midfg)}
/* A32 折疊鈕：跟旁邊的「複製」用同一顆 .act，但顏色調成次要色——
   別讓「＋N 則」搶了「複製」的視覺份量，那顆才是編輯常用的（2026-09-07）。 */
.mid button.foldbtn{color:var(--mut)}
.mid button.foldbtn:hover{color:var(--accent);background:var(--urltint)}
.sub{margin:10px 0 3px;font-size:13px;color:var(--mut)}  /* 空清單提示沿用這個灰 */
/* 小分題反白：底色掛在文字本身（inline-block），不是整條橫幅——
   橫幅會跟上面的大分類底線打架，而且小分題常常很短，整條反白看起來像錯誤訊息。
   ⚠️ 底色**淺灰配深字**（2026-08-09 使用者訂正，原本是深灰配白字太重）：
   小分題只是第三層標題，配色比大分類還搶眼會把視覺層級整個弄反。
   深色模式反過來（深底淺字），但同樣是「比背景稍亮一階」而非高對比。 */
.sub .subtxt{display:inline-block;padding:3px 9px;border-radius:5px;
     background:var(--subbg);color:var(--subfg);font-weight:600}
.hd{display:flex;align-items:center;gap:8px}
.hd button{visibility:hidden}
.hd:hover button{visibility:visible}
/* ⚠️ 手機沒有 hover——只靠 :hover 顯示等於按不到（本檔主要使用情境就是手機），
   所以觸控裝置一律常駐顯示。 */
@media (hover:none),(pointer:coarse){
  .hd button,.item button{visibility:visible!important}
  body{font-size:16px}          /* 手機閱讀尺寸 */
  .item{padding:8px 6px}        /* 觸控目標放大 */
}
.item{display:flex;gap:9px;padding:7px 9px;margin:1px 0;border:1px solid transparent;
      border-radius:8px;align-items:flex-start;transition:background .12s,border-color .12s}
.item:hover{background:var(--card);border-color:var(--line)}
.item .txt{flex:1;white-space:pre-wrap;word-break:break-word}
/* 側錄／網址素材與三段式素材行視覺區隔——側錄是逐字稿、篇幅大得多，
   不分開的話會在清單裡壓過真正的外電素材（0802 實測占 30%）。
   ⚠️ 不用 border-left 色條（那是裝飾性側邊線，統一改用底色調 + 小標籤，
   辨識力不輸色條、也不會在清單裡長出一整排彩色豎線）。 */
.item.side{background:var(--sidetint)}
.item.side:hover{background:var(--sidetint);filter:brightness(.97)}
.item.url{background:var(--urltint)}
.item.url:hover{background:var(--urltint);filter:brightness(.97)}
.kindtag{flex:none;align-self:flex-start;margin-top:1px;padding:1px 6px;font-size:11px;
  font-weight:700;border-radius:4px;color:var(--kindfg);background:var(--chip)}
/* 側錄摺疊：預設只露第一行＋一小段內容，點開才看全文 */
.sumline{cursor:pointer;user-select:none;color:var(--mut)}
.sumline .caret{display:inline-block;margin-right:4px;transition:transform .15s}
.sidebody{margin-top:4px;white-space:pre-wrap}
.mark{flex:none;width:1.4em;text-align:center;font-size:15px}
.item button{visibility:hidden;flex:none}
.item:hover button{visibility:visible}
.hide{display:none}
.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);
  background:var(--accent);color:var(--accent-fg);padding:8px 18px;border-radius:999px;
  font-size:13px;font-weight:600;box-shadow:var(--shadow);
  opacity:0;transition:opacity .2s,transform .2s;pointer-events:none;z-index:99}
.toast.on{opacity:1;transform:translateX(-50%) translateY(-2px)}
/* 剪貼簿被擋時的最後退路：把文字攤開、全選好，讓人長按「複製」 */
#modal{position:fixed;inset:0;background:rgba(10,12,16,.55);display:none;
  z-index:100;padding:16px;align-items:center;justify-content:center}
#modal.on{display:flex}
#modal .box{background:var(--bg);border-radius:12px;padding:14px;width:100%;
  max-width:680px;max-height:80vh;display:flex;flex-direction:column;gap:9px;
  box-shadow:0 12px 40px rgba(0,0,0,.35)}
#modal textarea{width:100%;height:52vh;font:13px/1.6 monospace;padding:10px;
  border:1px solid var(--line);border-radius:7px;background:var(--card);color:var(--fg)}
#modal .hint{color:var(--mut);font-size:13px}
</style></head><body>
<div class="top">
  <div class="tgl" id="metaTgl"><h1>__H1__</h1><span class="caret" id="metaCaret">▾</span>
    <span class="stamp" id="stamp"></span></div>
  <div class="meta" id="meta">__META__</div>
</div>
__DATEBAR__
<div class="sticky">
  <div class="bar">
    <input type="search" id="q" placeholder="搜尋代碼、摘要、畫面、BITE…">
    <span id="cnt" class="count"></span>
  </div>
</div>

<!-- 篩選面板：手機＝下方彈出（蓋住下半、不推擠內容）；桌機＝常駐左側欄。
     兩種版型共用同一段 DOM，差別全在 CSS，避免維護兩套。 -->
<div id="scrim"></div>
<aside id="panel">
  <div class="grip" id="grip"></div>
  <div class="phead">篩選<button class="act" id="closeF">關閉</button></div>
  <!-- 🔴 重大／畫面亮點／本輪新增**同一段**（2026-09-04 使用者要求，不要拆開）。
       三者仍是各自獨立的篩選維度（F.alert／F.hilite／F.fresh，可疊加），只是共用一條 bar。 -->
  <div class="fgroup"><div class="flabel" id="lmix">重點篩選</div><div class="bar" id="fmix"></div></div>
  <div class="fgroup"><div class="flabel">來源</div><div class="bar" id="fsrc"></div></div>
  <div class="fgroup"><div class="flabel">時段</div><div class="bar" id="fmark"></div></div>
  <div class="fgroup"><div class="flabel">大分類</div><div class="bar" id="fbig"></div></div>
  <div class="fgroup bar">
    <button class="act" id="copyAll">複製目前篩選結果</button>
    <button class="act" id="reset">清除篩選</button>
  </div>
__LOGO__
</aside>
<button id="fab">篩選</button>
<main id="list"></main>
<div class="toast" id="toast"></div>
<div id="modal"><div class="box">
  <div class="hint">此環境擋住了自動複製。文字已全選——長按選取區選「複製」即可。</div>
  <textarea readonly></textarea>
  <div><button class="act" onclick="document.getElementById('modal').classList.remove('on')">關閉</button></div>
</div></div>
<script>
const ROWS = __ROWS__;
// `■`（2026-08-04–09-04）與 `●`（更早）是晨班的舊符號，歷史檔案還在用，label 要留著。
const MARK_LABEL = {"△":"△ 晚班既有","▲":"▲ 無人值守","◇":"◇ 晨班",
                    "■":"■ 晨班（舊）","●":"● 晨班（舊）","◆":"◆ 早班"};
// 篩選鈕上不要出現 SIDE_CNN 這種內部代碼——那是給程式看的，不是給編輯看的
const SRC_LABEL = {"SIDE_CNN":"CNN側錄","SIDE_NHK":"NHK側錄","OTH":"其他",
                   "CNN_newsource":"NS","CNN":"NS",
                   "YNA":"韓聯社","CNA":"CNA","ENEX":"ENEX","ABC":"ABC"};
const F = {src:new Set(), mark:new Set(), big:new Set(), alert:new Set(),
           hilite:new Set(), fresh:new Set(), q:""};
// 最新一輪的 checkpoint（顯示用；空字串＝狀態檔沒有頂層 checkpoint）
const FRESH_CP = __FRESH_CP__;

function uniq(k){return [...new Set(ROWS.map(r=>r[k]).filter(Boolean))];}

function chips(host, key, vals, label){
  const el = document.getElementById(host);
  vals.forEach(v=>{
    const b = document.createElement('span');
    b.className='chip'; b.textContent = label ? (label[v]||v) : v;
    b.onclick = ()=>{ F[key].has(v) ? F[key].delete(v) : F[key].add(v);
                      b.classList.toggle('on'); draw(); };
    el.appendChild(b);
  });
}

function pass(r){
  if(F.src.size && !F.src.has(r.src)) return false;
  if(F.mark.size && !F.mark.has(r.mark)) return false;
  if(F.big.size && !F.big.has(r.big)) return false;
  if(F.alert.size && !F.alert.has(r.alert)) return false;
  if(F.hilite.size && !F.hilite.has(r.hilite)) return false;
  if(F.fresh.size && !F.fresh.has(r.fresh)) return false;
  if(F.q && !r.q.includes(F.q)) return false;
  return true;
}

function toast(m){const t=document.getElementById('toast');
  t.textContent=m; t.classList.add('on'); setTimeout(()=>t.classList.remove('on'),1300);}

// 複製是本檔的核心用途（拆稿單貼到別的系統），而**它最容易在別的環境壞掉**：
// file:// 下、Apps Script 的 iframe 沙箱裡、手機瀏覽器上，剪貼簿 API 都可能被權限
// 政策擋掉。所以做三層退路，最後一層保證「一定拿得到文字」而不是靜默失敗。
function copy(text, msg){
  const legacy = ()=>{                       // ② 舊招：textarea + execCommand
    try{
      const ta=document.createElement('textarea');
      ta.value=text; ta.style.position='fixed'; ta.style.opacity='0';
      document.body.appendChild(ta); ta.select();
      const ok=document.execCommand('copy'); ta.remove();
      if(ok){toast(msg);return;}
    }catch(e){}
    manual();                                // ③ 都不行就攤開來讓人自己複製
  };
  const manual = ()=>{                       // ③ 手動：全選好的文字框＋長按複製
    const m=document.getElementById('modal');
    m.querySelector('textarea').value=text;
    m.classList.add('on');
    const ta=m.querySelector('textarea');
    ta.focus(); ta.select(); ta.setSelectionRange(0, text.length);  // iOS 要這行才選得起來
  };
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(text).then(()=>toast(msg)).catch(legacy);  // ①
  }else legacy();
}

function btn(label, fn){
  const b=document.createElement('button'); b.className='act'; b.textContent=label;
  b.onclick=e=>{e.stopPropagation(); fn();}; return b;
}

// A32（2026-09-07，只影響這份 HTML 的 DOM 顯示，txt／狀態檔一字不動）：
// 中主題 ≥8 則時，畫面預設只展開「🔴／🟡／⭐／🔖 標記過的則」與「跨小分題累計
// 前 3 則沒標記的則」，其餘摺起來給一顆「＋N 則」鈕，避免一次刷出幾十則。
// ⚠️ 這個 8 是姊妹常數，跟 s2_topic_review.py 的 BIG_N 意義相同（都是「巨格」
// 判斷的則數門檻），但 Python／JS 兩邊各自維護一份——兩邊如果之後要調門檻，
// 記得一起改，這裡不會自動同步。
const BIG_MID_N=8;
// 排序只影響「這顆中主題底下、這個小分題」自己的顯示順序（不跨小分題重排、
// 不動 its 本身、複製功能永遠用 its 原序）——見 draw() 內 order 那行的註解。
function _alertRank(r){ return r.alert==='🔴'?0:(r.alert==='🟡'?1:2); }
function _hiliteRank(r){ return r.hilite==='🔖'?0:1; }

function draw(){
  const list=document.getElementById('list'); list.innerHTML='';
  const rows=ROWS.filter(pass);
  // 筆數照 txt 檔頭的語意算：素材（含網址素材）與側錄**分開報**。
  // 混在一起算，就會出現「txt 說 222 則、網頁說 292 則」這種同資料兩個數字。
  // kind='empty'＝常駐中主題的佔位標題，不是真素材，兩邊筆數都要排除，
  // 否則「N 則」會因為掛了幾個常駐空標題而多報。
  const nWire=rows.filter(r=>r.kind!=='side'&&r.kind!=='empty').length;
  const nSide=rows.filter(r=>r.kind==='side').length;
  const tWire=ROWS.filter(r=>r.kind!=='side'&&r.kind!=='empty').length;
  // ⛔ 側錄**只報「則」，不准把「段」加回來**（2026-08-09 使用者兩度要求）：
  // 「段」是資料格式的內部單位，AI 自己知道就好，出現在編輯畫面上只是雜訊。
  // 要核帳看段數請看 s2_render.py 的對帳行——那個是印給 agent 的，要留著。
  let sideUnits=0, prev=null;
  rows.filter(r=>r.kind==='side').forEach(r=>{
    const k=[r.src,r.big,r.mid,r.sub].join('|');
    if(k!==prev) sideUnits++;
    prev=k;
  });
  document.getElementById('cnt').textContent =
    `${nWire} / ${tWire} 則` + (nSide ? `　側錄 ${sideUnits} 則` : '');
  // 面板關起來時，光看浮動鈕就要知道有沒有在篩、篩了幾項——
  // 否則使用者會對著變少的清單納悶「東西怎麼變少了」。有篩時連顏色一起換。
  const nf=F.src.size+F.mark.size+F.big.size+F.alert.size+F.hilite.size+F.fresh.size+(F.q?1:0);
  const fab=document.getElementById('fab');
  fab.textContent = nf ? `篩選 (${nf})` : '篩選';
  fab.classList.toggle('on', nf>0);
  // 分組時保持 ROWS 的原順序（那就是 txt 的順序）
  const tree=new Map();
  rows.forEach(r=>{
    if(!tree.has(r.big)) tree.set(r.big,new Map());
    const m=tree.get(r.big);
    if(!m.has(r.mid)) m.set(r.mid,new Map());
    const s=m.get(r.mid);
    if(!s.has(r.sub)) s.set(r.sub,[]);
    s.get(r.sub).push(r);
  });
  tree.forEach((mids,big)=>{
    const bh=document.createElement('div'); bh.className='big hd';
    bh.append(document.createTextNode(big));   // ⚠️ 不印 `======`：那是 txt 的分隔寫法，
                                              // 網頁版靠上下兩條橘紅線就夠明顯（2026-08-09 使用者訂）
                                              // ⛔ 但**複製出去的文字仍要帶 ======**（見 blockText），
                                              //    編輯是把它貼進別的系統，格式不能少。
    // 常駐空標題（kind='empty'）不算則數，只在版面上占一行標題
    const all=[...mids.values()].flatMap(s=>[...s.values()].flat()).filter(r=>r.kind!=='empty');
    bh.append(btn(`複製整格（${all.length}）`,()=>copy(blockText(big,mids),`已複製「${big}」${all.length} 則`)));
    list.append(bh);
    mids.forEach((subs,mid)=>{
      const n=[...subs.values()].flat().filter(r=>r.kind!=='empty').length;
      let mh=null;
      if(mid){
        mh=document.createElement('div'); mh.className='mid hd';
        // 藍底白字色塊只包文字，複製鈕留在色塊外（跟小分題同一套做法）
        const mt=document.createElement('span'); mt.className='midtxt';
        mt.textContent=` ${mid} `;
        mh.append(mt);
        mh.append(btn(`複製（${n}）`,()=>copy(midText(mid,subs),`已複製「${mid}」${n} 則`)));
        list.append(mh);
      }
      // A32：中主題 ≥8 則、且側欄沒在篩（nf===0）才折——有篩選時使用者已經在
      // 縮小範圍看，篩出來的東西不該再被二次隱藏（見 Global Constraints）。
      // ⚠️ 必須有 `mid`（有標題色塊）才折：折起來的東西要有地方放「＋N 則」鈕，
      // 否則像「(無中主題)」這種沒有標題列的異常分組會摺起來卻沒有展開的入口。
      const foldOn = !!mh && n>=BIG_MID_N && nf===0;
      let shown=0;              // 跨小分題累計「前 3 則」名額，只花在非標記則上
      const foldedEls=[];       // 這個中主題被摺起來的 .item，供「＋N 則」鈕統一 toggle
      subs.forEach((its,sub)=>{
        if(its.length===1 && its[0].kind==='empty') return;   // 常駐標題今天 0 則：只留標題，不出空白項目
        if(sub){
          const sh=document.createElement('div'); sh.className='sub hd';
          // 反白底只包住文字本身，不要吃掉旁邊的「複製」鈕
          const st=document.createElement('span'); st.className='subtxt'; st.textContent=sub;
          sh.append(st);
          sh.append(btn(`複製（${its.length}）`,()=>copy(subText(sub,its),`已複製「${sub}」${its.length} 則`)));
          list.append(sh);
        }
        // A32 排序：只在折疊有效時，重排「這個小分題自己」的顯示順序
        // （🔴→🟡→🔖→其餘），讓標記過的則先出現在摺疊線以上。⚠️ 只建一份
        // 給 DOM 用的副本——`its` 本身不動，subText()/midText() 複製時
        // 仍照 s2_state.py 原始順序、複製全部（含被摺起來的）。
        const order = foldOn
          ? its.map((r,i)=>({r,i})).sort((a,b)=>
              _alertRank(a.r)-_alertRank(b.r) || _hiliteRank(a.r)-_hiliteRank(b.r) || a.i-b.i
            ).map(x=>x.r)
          : its;
        // 側錄要「同段落同主題算一則、預設只顯示第一行、可展開」（2026-08-09 使用者訂）。
        // 連續且同來源的側錄併成一個區塊——資料裡本來就照 TC 順序排、也帶三層分類，
        // 所以「連續同類」直接就是一則連線報導，不必另外標記。
        const units=[];
        order.forEach(r=>{
          const last=units[units.length-1];
          if(r.kind==='side' && last && last.kind==='side' && last.rows[0].src===r.src){
            last.rows.push(r);
          }else units.push({kind:r.kind, rows:[r]});
        });

        units.forEach(u=>{
          const first=u.rows[0];
          const full=u.rows.map(x=>x.text).join('\\n');
          const d=document.createElement('div');
          d.className='item'+(u.kind==='side'?' side':'')+(u.kind==='url'?' url':'');
          const mk=document.createElement('span'); mk.className='mark'; mk.textContent=first.mark;
          // 底色調取代了原本的 border-left 色條，額外補一顆小標籤讓「這是側錄／網址
          // 素材」不必靠底色深淺猜——尤其淺色主題下兩種底色調本來就很接近。
          const kt = u.kind==='side' ? '側' : (u.kind==='url' ? '網址' : '');
          const ktEl = kt ? (()=>{const s=document.createElement('span');
            s.className='kindtag'; s.textContent=kt; return s;})() : null;
          const tx=document.createElement('div'); tx.className='txt';
          const bare=full.replace(/^\\s*[△▲◇■◆●]\\s*/,'');

          if(u.kind==='side'){
            // 摺疊：側錄中位數 401 字、最長 1442（0802 實測），而一則三段式素材才 150–250 字。
            // **單段也要摺**——27/42 個區塊本來就是單段，長度一樣壓過素材。
            const head=bare.split('\\n')[0];                    // 「CNN 151542 （主播）」
            const body=bare.split('\\n').slice(1).join('\\n');
            const peek=body.replace(/\\s+/g,' ').slice(0,28);
            const sum=document.createElement('div');
            sum.className='sumline';
            sum.innerHTML='<span class="caret">▾</span>';
            sum.append(document.createTextNode(
              `${head}${u.rows.length>1?`　共 ${u.rows.length} 段`:''}　${peek}…`));
            const bodyEl=document.createElement('div');
            bodyEl.className='sidebody off'; bodyEl.textContent=bare;
            sum.onclick=()=>{
              bodyEl.classList.toggle('off');
              sum.querySelector('.caret').classList.toggle('open', !bodyEl.classList.contains('off'));
            };
            tx.append(sum, bodyEl);
          }else{
            tx.textContent=bare;
          }
          // ⛔ 複製一律給**全文**，不是預覽——摺疊是顯示層的事，貼出去必須完整
          if(ktEl) d.append(mk,ktEl,tx,btn('複製',()=>copy(full,`已複製 ${first.id}`)));
          else d.append(mk,tx,btn('複製',()=>copy(full,`已複製 ${first.id}`)));
          // A32 折疊：🔴／🟡／⭐／🔖 標記過的則永遠展開、不佔「前 3 則」名額；
          // 沒標記的則跨小分題累計到第 3 則之後一律摺起來。
          if(foldOn){
            const marked = u.rows.some(r=>r.alert||r.hilite);
            if(!marked && shown>=3){
              d.classList.add('fold','off');
              foldedEls.push(d);
            }
            if(!marked) shown++;
          }
          list.append(d);
        });
      });
      if(mh && foldedEls.length){
        const b=btn(`＋${foldedEls.length} 則`, ()=>{
          const willOpen = foldedEls[0].classList.contains('off');
          foldedEls.forEach(el=>toggle(el));
          b.textContent = willOpen ? '收合' : `＋${foldedEls.length} 則`;
        });
        b.classList.add('foldbtn');
        mh.append(b);
      }
    });
  });
  if(!rows.length){
    const e=document.createElement('div'); e.className='sub';
    e.textContent='沒有符合條件的素材。'; list.append(e);
  }
}

// 以下三個組字串的函式，輸出格式與 txt 完全一致（小分題之間用 +）
// A32 斷言：這三支永遠吃 `subs`／`its` 這兩個原始 Map／陣列（draw() 裡建 tree 時
// push 進去、從未重排的那份），不是 draw() 為了顯示折疊而另外 sort 出來的 `order`
// 副本——所以複製一律是**全部**（含被摺起來的）、**原始順序**（不受 A32 排序／
// 折疊影響）。摺疊只碰 `d.classList`（單一 .item 的顯示狀態），不碰這裡的資料來源。
function subText(sub,its){return (sub?sub+"\\n":"")+its.map(r=>r.text).join("\\n");}
function midText(mid,subs){
  const parts=[...subs.entries()].map(([s,i])=>subText(s,i));
  return (mid?`【${mid}】\\n`:"")+parts.join("\\n+\\n");
}
function blockText(big,mids){
  const parts=[...mids.entries()].map(([m,s])=>midText(m,s));
  return `======${big}======\\n\\n`+parts.join("\\n\\n");
}

document.getElementById('q').oninput=e=>{F.q=e.target.value.trim().toLowerCase();draw();};
document.getElementById('copyAll').onclick=()=>{
  const rows=ROWS.filter(pass);
  copy(rows.map(r=>r.text).join("\\n"),`已複製篩選結果 ${rows.length} 則`);
};
document.getElementById('reset').onclick=()=>{
  F.src.clear();F.mark.clear();F.big.clear();F.alert.clear();F.hilite.clear();F.fresh.clear();F.q="";
  document.getElementById('q').value="";
  document.querySelectorAll('.chip.on').forEach(c=>c.classList.remove('on'));
  draw();
};
// 來源排序：**明確寫死順序**（2026-08-09 使用者訂）。
// AP／RT／NS 三站一定排最前面（那是每天的主力、編輯第一眼要找的），
// 接著側錄 CNN／NHK，再來網址素材 YNA／CNA、交換平台 ENEX／ABC。名單外的排最後、按字母。
// ⚠️ 不要改用 localeCompare 之類的「自動排序」——那會讓 AP 之外的來源
//    隨著當天有沒有收到而跳來跳去，編輯每天看到的位置不一樣。
const SRC_ORDER=['AP','RT','NS','SIDE_CNN','SIDE_NHK','YNA','CNA','ENEX','ABC','OTH'];
chips('fsrc','src',uniq('src').sort((a,b)=>{
  const w=s=>{const i=SRC_ORDER.indexOf(s);return i<0?SRC_ORDER.length:i;};
  return w(a)-w(b) || a.localeCompare(b);
}),SRC_LABEL);
chips('fmark','mark',uniq('mark'),MARK_LABEL);
// ── 重點篩選（一段三維度，2026-09-04 使用者要求不要拆開）──────────────
// 重大／推薦：⭐ 在最前（編輯先看推薦、才看紅黃標）、🔴 次之、🟡 在後（2026-08-19 使用者訂案）
const ALERT_ORDER={"⭐":0,"🔴":1,"🟡":2};
chips('fmix','alert',uniq('alert').sort((a,b)=>ALERT_ORDER[a]-ALERT_ORDER[b]),
      {"⭐":"⭐ 推薦","🔴":"🔴 重大","🟡":"🟡 次重大"});
// 畫面亮點：**只有一個鈕**，涵蓋所有標了 🔖 的（畫面好／搖晃瞬間／日後新增的標籤）。
// 那天沒有任何 🔖 就不會長出鈕。
chips('fmix','hilite',uniq('hilite'),{"🔖":"🔖 畫面好"});
// 本輪新增：一顆鈕（🔥）。那輪 0 則新增時 uniq 是空的，鈕自己不會出現。
chips('fmix','fresh',uniq('fresh'),{"🔥":"🔥 只看最新"});
(function(){
  const bar=document.getElementById('fmix');
  const lab=document.getElementById('lmix');
  if(FRESH_CP && [...bar.children].some(c=>c.textContent.includes('只看最新')))
    lab.textContent='重點篩選（本輪 '+FRESH_CP+'）';
  if(!bar.children.length) lab.parentElement.style.display='none';
})();
chips('fbig','big',uniq('big'));

// ── 產出時間：停太久要主動變紅，不能只是印在那裡 ────────────────────
// 掃帶最長間隔是 3 小時（13:00→16:00），超過就代表管線停了或 html 沒更新，
// 而 Apps Script 會**無聲**退回昨天那份——不主動示警，編輯會照著舊清單發稿。
const BUILT = "__BUILT__";
(function(){
  const el=document.getElementById('stamp');
  el.textContent='更新於 '+BUILT.slice(5);          // 去掉年份，手機省空間
  const age=(Date.now()-new Date(BUILT.replace(/-/g,'/')).getTime())/36e5;
  if(age>3.5){ el.classList.add('stale'); el.textContent='⚠ '+el.textContent+`（${age.toFixed(0)} 小時前）`; }
})();

// ── 收合：手機上預設兩塊都收起來，把螢幕讓給素材 ──────────────────
const $=id=>document.getElementById(id);
const isTouch = window.matchMedia('(hover:none),(pointer:coarse)').matches;

function toggle(el, caret){
  el.classList.toggle('off');
  if(caret) caret.classList.toggle('open', !el.classList.contains('off'));
}
$('metaTgl').onclick=()=>toggle($('meta'), $('metaCaret'));

// ── 篩選面板開關（手機才需要；桌機是常駐側欄，這些 class 不影響它）──
function openF(on){
  $('panel').classList.toggle('open', on);
  $('scrim').classList.toggle('open', on);
}
$('fab').onclick   = ()=>openF(!$('panel').classList.contains('open'));
$('closeF').onclick= ()=>openF(false);
$('scrim').onclick = ()=>openF(false);          // 點外面關閉
// 下滑關閉：手機上比找關閉鈕自然
let ty0=null;
$('grip').addEventListener('touchstart',e=>{ty0=e.touches[0].clientY;},{passive:true});
$('grip').addEventListener('touchmove',e=>{
  if(ty0!==null && e.touches[0].clientY-ty0>40){ openF(false); ty0=null; }
},{passive:true});
document.addEventListener('keydown',e=>{ if(e.key==='Escape') openF(false); });

// 檔頭資訊：手機、桌機**一律預設攤開**（2026-08-09 使用者訂）。
// 原本手機自動收起，但檔頭有當天則數與 🔴 重大三行——那是開檔第一眼最該看到的，
// 自動收起等於把重點藏起來。要不要收由使用者自己點。
// ⚠️ 篩選面板不在這裡控制——它的開關由 CSS 版型決定（桌機常駐、手機彈出），
//    用 JS 加 .off 會把桌機的側欄也一起藏掉。
$('metaCaret').classList.add('open');
draw();
</script></body></html>
"""


def find_archive_dates(live_dir, n=6):
    """live_dir/Archive/{YYYYMMDD}/{MMDD}-s2-state.json 裡找過去 n 天，回傳新到舊。

    只認「有狀態檔」的日期——html 沒產出但 state 在的日子仍可用（渲染邏輯本來就
    只需要 state），state 也沒有的日子代表那天沒掃過，不列進歷史選單。
    """
    archive_dir = os.path.join(live_dir, "Archive")
    out = []
    if not os.path.isdir(archive_dir):
        return out
    for name in sorted(os.listdir(archive_dir), reverse=True):
        if not re.match(r"^\d{8}$", name):
            continue
        mmdd = name[4:]
        if os.path.isfile(os.path.join(archive_dir, name, f"{mmdd}-s2-state.json")):
            out.append(mmdd)
        if len(out) >= n:
            break
    return out


def build_datebar(today_mmdd, archive_mmdds):
    """歷史列 HTML（2026-08-11 上線）。連結用 `?date=MMDD` 查詢參數——網頁是靠
    Google Apps Script 代管（`scripts/appsscript/晚班交接WebApp.gs`），同一個固定
    網址接受這個參數時改抓指定日期那份檔案，不然一律抓「最新」。**沒有歷史檔案
    時整塊不輸出**（不是空殼），開站頭幾天 Archive 還沒累積起來不會冒出一條空列。
    """
    if not archive_mmdds:
        return ""
    # ⚠️ target="_top" 不夠（2026-08-11 實測訂正）：Apps Script 的 /exec 網址載入後
    # 會把「最上層瀏覽環境」導向一個 Google 沙盒網域（*.googleusercontent.com/
    # userCodeAppPanel），不是內容本身所在的那層——所以就算 target="_top" 正確跳出
    # 了 iframe，相對連結 `?date=0810` 解析基準也已經是那個沙盒網址，點下去變成
    # `.../userCodeAppPanel?date=0810`（doGet() 完全接不到），不是原本以為的
    # iframe 內部導航問題。改用絕對網址：`%%EXEC_URL%%` 是佔位字串，doGet() 會用
    # `ScriptApp.getService().getUrl()`（這個部署自己的固定網址）換掉它再回傳——
    # 不管當下最上層在哪個網域，都能導回正確的入口。本機雙擊測試沒有 Apps Script
    # 可以做這個換字，佔位字串會原樣留著、點了沒反應，這是已知限制，不是迴歸。
    parts = ['<div class="histbar" id="histbar"><span class="hlabel">歷史：</span>',
             f'<a class="dpill on" href="%%EXEC_URL%%" target="_top">今天 {today_mmdd[:2]}/{today_mmdd[2:]}</a>']
    for mmdd in archive_mmdds:
        parts.append(f'<a class="dpill" href="%%EXEC_URL%%?date={mmdd}" target="_top">{mmdd[:2]}/{mmdd[2:]}</a>')
    parts.append('</div>')
    parts.append(
        '<script>(function(){var h=document.getElementById("histbar");'
        'if(h)document.documentElement.style.setProperty("--histh",h.offsetHeight+"px");'
        '})();</script>'
    )
    return "".join(parts)


def build_html(state, base_mmdd, window, datebar_html=""):
    head = build_header(state, base_mmdd, window)
    # 🔴 產出時間一定要印在畫面上（2026-08-09）：編輯用的 Apps Script 網址是抓
    # 「最後修改時間最新」的那份 html，萬一今天的 html 因故沒產出，網址會**無聲
    # 退回昨天的資料**——編輯照著舊清單發稿卻毫無察覺。有這一行就一眼看得出來。
    head.append("本頁產出時間：" + datetime.now().strftime("%Y-%m-%d %H:%M"))
    rows = collect(state, base_mmdd)
    title = head[0] if head else "晚班交接"
    meta = "\n".join(head[1:])
    alerts = [h for h in head[1:] if h.startswith("🔴")]
    meta_html = html.escape(meta)
    for a in alerts:                       # 重大提醒要跳出來，不要跟一般檔頭同色
        meta_html = meta_html.replace(html.escape(a),
                                      f'<span class="alert">{html.escape(a)}</span>')
    # LOGO 抓不到就整塊不輸出（而不是留一個 src="" 的破圖）。
    # 2026-08-19 使用者要求：按下 LOGO 回到「今天」的晚班交接主頁——跟歷史列
    # 「今天」那顆鈕共用同一個 %%EXEC_URL%% 佔位字串（doGet() 換成部署固定網址），
    # target="_top" 理由見 build_datebar() 的說明：Apps Script 的 /exec 頁面
    # 最上層在一個 Google 沙盒網域，相對連結解析基準是那層，必須用絕對網址換掉。
    uri = logo_data_uri()
    logo_html = (f'<a class="brand" href="%%EXEC_URL%%" target="_top" '
                 f'title="回到今天的晚班交接"><img src="{uri}" alt="Miniverse" '
                 f'width="80" height="80" loading="lazy"></a>') if uri else ""
    return (TEMPLATE
            .replace("__TITLE__", html.escape(title))
            .replace("__H1__", html.escape(title))
            .replace("__META__", meta_html)
            .replace("__BUILT__", datetime.now().strftime("%Y-%m-%d %H:%M"))
            .replace("__LOGO__", logo_html)
            .replace("__DATEBAR__", datebar_html)
            .replace("__FRESH_CP__",
                     json.dumps(fresh_label(fresh_info(state, base_mmdd)[1]),
                                ensure_ascii=False))
            .replace("__ROWS__", json.dumps(rows, ensure_ascii=False)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", default=R.DEFAULT_FILE, help="狀態檔路徑")
    p.add_argument("--out", help="輸出 html 路徑（省略＝印到 stdout）")
    p.add_argument("--base-date", default="", help="晚班當天 MMDD；省略自動推得")
    p.add_argument("--window", default="", help="時間窗；省略取狀態檔算出的累計窗")
    p.add_argument("--legacy", action="store_true",
                   help="用舊版面（預設＝T/C 矩陣版，跟排程每輪產出的那份一致）")
    args = p.parse_args()

    state = R.load_state(args.file)
    base = args.base_date
    if not base:
        m = re.search(r"(\d{4})-s2-state", os.path.basename(args.file))
        base = m.group(1) if m else state.get("date", "")
    win = args.window or R.window_from_state(state, base) or state.get("window_local", "")
    live_dir = os.path.dirname(os.path.abspath(args.file))
    datebar = build_datebar(base, find_archive_dates(live_dir))
    # A10 v2（2026-08-24）：預設產矩陣版，跟 `s2_render.py` 排程那條路**同一支**。
    # ⛔ 兩條路都會產出正式檔案，新版面兩邊都要接——2026-08-11 歷史列就是只接了
    #    這條獨立入口、排程那條沒接，功能「上線」卻從來沒生效過。
    if args.legacy or os.environ.get("S2_HTML_LEGACY") == "1":
        out = build_html(state, base, win, datebar)
    else:
        import s2_render_matrix as rm
        out = rm.build_html(state, base, win, datebar)

    if not args.out:
        sys.stdout.write(out)
        return
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(out)
    # 常駐中主題（2026-08-11）的佔位 row 也帶 "id" 鍵（值是空字串），
    # 用 kind:"empty" 出現次數扣掉，不然這行診斷數字會比真正則數多報。
    n = out.count('"id":') - out.count('"kind": "empty"')
    print(f"OK 已產出 {args.out}（{n} 則 / {len(out)} 字元）")
    print("⚠️ 從 Google Drive 網頁預覽開不會執行 JS，要開本機同步的那份檔案。")


if __name__ == "__main__":
    main()
