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

    ⚠️ 只看**第一行**：🔖 標在素材代碼前面（🔴／🟡 之後），一定在第一行；
    往下多看會把側錄內容行裡偶然出現的符號也算進來。
    """
    return "🔖" if "🔖" in (text or "").split("\n")[0] else ""


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
                    kind = "side" if src.startswith("SIDE_") else ("url" if src == "YT" else "wire")
                    rows.append({
                        "big": big or "", "mid": mid or "", "sub": sub or "",
                        "id": it.get("id") or "",
                        "src": src, "kind": kind,
                        "mark": R.mark_for(it.get("first_seen_checkpoint") or "", base_mmdd) or "",
                        # 重大層級（2026-08-09 使用者要求可篩）：🔴＝檔頭重大、🟡＝重大未進檔頭。
                        # 從**渲染後的成品**認，不從 raw_entry——render 會依 alerts 補標記，
                        # 只看 raw_entry 會漏掉那些「檔頭有、正文還沒補」的則。
                        "alert": ("🔴" if "🔴" in text[:8] else
                                  ("🟡" if "🟡" in text[:8] else "")),
                        # 畫面亮點（2026-08-11 使用者要求可篩）：見 hilite_of。
                        "hilite": hilite_of(text),
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
:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#e3e3e3;--card:#fafafa;
      --accent:#0b62d0;--chip:#eef2f7;--chipon:#0b62d0;--warn:#c00;
      --big:#d94a1f;--subbg:#e8eaed;--subfg:#2b2f36;
      --midbg:#0b62d0;--midfg:#fff}
@media (prefers-color-scheme:dark){
:root{--bg:#16181c;--fg:#e8e8e8;--mut:#9aa0a6;--line:#2c3038;--card:#1d2026;
      --accent:#6aa9ff;--chip:#252a32;--chipon:#2b6cb0;--warn:#ff6b6b;
      --big:#ff7a4d;--subbg:#333941;--subfg:#e8e8e8;
      --midbg:#2b6cb0;--midfg:#fff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
     font:15px/1.7 "Noto Sans TC","Microsoft JhengHei",system-ui,sans-serif}
/* 檔頭分兩塊：標題與檔頭資訊**隨頁面捲走**，只有搜尋列釘在頂端。
   原本整組（標題＋檔頭＋三排篩選＋兩個鈕）都 sticky，手機上吃掉半個螢幕，
   素材瀏覽空間所剩無幾（2026-08-09 使用者實測回報）。 */
.top{padding:10px 14px 4px}
.sticky{position:sticky;top:var(--histh);z-index:9;background:var(--bg);
        border-bottom:1px solid var(--line);padding:6px 14px 8px}
h1{font-size:17px;margin:0}
.tgl{display:flex;align-items:center;gap:6px;cursor:pointer;user-select:none}
.caret{color:var(--mut);font-size:12px;transition:transform .15s}
.caret.open{transform:rotate(180deg)}
.meta{color:var(--mut);font-size:13px;white-space:pre-wrap;margin-top:3px}
/* 產出時間要**永遠看得到**：它藏在收合的檔頭裡就失去警示作用了。
   資料若停在幾小時前，編輯一眼就該察覺，而不是照著舊清單發稿。 */
.stamp{margin-left:auto;color:var(--mut);font-size:12px;white-space:nowrap}
.stamp.stale{color:var(--warn);font-weight:600}
.off{display:none!important}

/* 歷史列（2026-08-11 上線）：跟會收合的檔頭（.top）是兩件事——檔頭捲走就捲走，
   歷史列跟下面的搜尋列一樣永遠釘頂。兩條 sticky 疊在一起不能都用 top:0（會互相
   蓋住），下面的搜尋列要讓出「歷史列的高度」——用行內 script 量測實際高度寫進
   --histh，不是猜一個 px 值，字級／螢幕寬度變動時才不會兩者間出現縫隙或重疊。 */
:root{--histh:0px}
.histbar{display:flex;gap:6px;overflow-x:auto;padding:6px 14px 10px;
         border-bottom:1px solid var(--line);-webkit-overflow-scrolling:touch;
         position:sticky;top:0;z-index:11;background:var(--bg)}
.histbar::-webkit-scrollbar{height:4px}
.hlabel{flex:none;font-size:12px;color:var(--mut);align-self:center;margin-right:2px}
.dpill{flex:none;padding:4px 11px;font-size:12px;border:1px solid var(--line);
       border-radius:12px;color:var(--mut);text-decoration:none;white-space:nowrap}
.dpill.on{background:var(--chipon);color:#fff;border-color:var(--chipon);font-weight:600}

/* ══ 篩選面板 ══════════════════════════════════════════════════
   桌機：常駐左側欄（橫向空間本來就有，不必開關）
   手機：下方彈出，**蓋住**下半螢幕而不推擠內容——「一展開就把素材往下推」
        正是 2026-08-09 使用者回報的痛點，換成側邊只是把方向改成往旁邊推，
        同樣沒解決，所以用覆蓋式。拇指落點也在螢幕下方，比側邊好按。 */
#panel{}
.grip{display:none}
.phead{display:none}
.fgroup{margin-bottom:10px}
.flabel{font-size:12px;color:var(--mut);margin-bottom:2px}
#scrim{display:none}
#fab{display:none}
/* LOGO：**預設不顯示**。手機版是下方彈出的操作面板，高度本來就吃緊
   （max-height:62vh），多一塊裝飾只會把篩選鈕擠出可視範圍——使用者明確說
   「PC 版就好，手機版不用改」。所以只在桌機那段 media query 裡打開。 */
.brand{display:none}

/* ── 桌機：常駐左側欄 ── */
@media (min-width:820px) and (hover:hover){
  body{display:grid;grid-template-columns:200px 1fr;
       grid-template-areas:"panel top" "panel hist" "panel sticky" "panel main"}
  .top{grid-area:top}
  .histbar{grid-area:hist}
  .sticky{grid-area:sticky}
  main{grid-area:main}
  #panel{grid-area:panel;position:sticky;top:0;align-self:start;max-height:100vh;
         overflow:auto;padding:12px;border-right:1px solid var(--line)}
  #panel .bar{margin-top:2px}
  .chip{font-size:12px;padding:3px 8px}
  /* LOGO 收在左欄最下方。`margin-top:auto` 需要 #panel 是 flex 縱向排列，
     所以這裡一起把它改成 flex——原本是預設 block，不影響上面各群組的排版。
     圖是圓形構圖、四角是黑底，`border-radius:50%` 把黑角切掉，
     淺色主題下才不會變成一塊突兀的黑方塊。 */
  #panel{display:flex;flex-direction:column}
  .brand{display:block;margin:18px auto 4px;text-align:center;
         opacity:.85;transition:opacity .2s}
  .brand:hover{opacity:1}
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
       padding:11px 18px;font-size:14px;font-weight:700;border:none;border-radius:22px;
       background:var(--accent);color:#fff;box-shadow:0 3px 12px rgba(0,0,0,.3)}
  #fab.on{background:var(--warn)}
  main{padding-bottom:76px}   /* 別讓最後一則被浮動鈕蓋住 */
}
.alert{color:var(--warn);font-weight:600}
.bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:8px}
input[type=search]{flex:1;min-width:180px;padding:7px 10px;font-size:14px;
  border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg)}
.chip{padding:4px 10px;font-size:13px;border:1px solid var(--line);border-radius:14px;
      background:var(--chip);color:var(--fg);cursor:pointer;user-select:none}
.chip.on{background:var(--chipon);color:#fff;border-color:var(--chipon)}
.count{color:var(--mut);font-size:13px;margin-left:auto}
button.act{padding:4px 10px;font-size:12px;border:1px solid var(--line);
  border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer}
button.act:hover{border-color:var(--accent);color:var(--accent)}
main{padding:6px 14px 60px}
/* 三層各給一種辨識方式（2026-08-09 使用者訂）：
   大分類＝橘紅色字＋同色底線／中主題＝維持原本的 accent 色／小分題＝深底反白框。
   ⚠️ 顏色要用 token 定義，深色模式才不會變成黑底上的深橘。 */
.big{margin:22px 0 8px;padding:5px 0;
     border-top:2px solid var(--big);border-bottom:2px solid var(--big);
     font-size:16px;font-weight:700;letter-spacing:2px;color:var(--big)}
.mid{margin:12px 0 4px;font-weight:700}
/* 中主題＝藍底白字色塊，去掉【】（2026-08-09 使用者訂）。
   前後各留一個半形空格才不會貼著色塊邊緣；空格寫在文字裡而不是靠 padding，
   使用者要的就是「 新加坡國慶 」這個形狀。⚠️ 只有網頁版這樣，TXT 版仍是【】。 */
.mid .midtxt{display:inline-block;padding:2px 6px;border-radius:4px;
     background:var(--midbg);color:var(--midfg)}
.sub{margin:8px 0 2px;font-size:13px;color:var(--mut)}  /* 空清單提示沿用這個灰 */
/* 小分題反白：底色掛在文字本身（inline-block），不是整條橫幅——
   橫幅會跟上面的大分類底線打架，而且小分題常常很短，整條反白看起來像錯誤訊息。
   ⚠️ 底色**淺灰配深字**（2026-08-09 使用者訂正，原本是深灰配白字太重）：
   小分題只是第三層標題，配色比大分類還搶眼會把視覺層級整個弄反。
   深色模式反過來（深底淺字），但同樣是「比背景稍亮一階」而非高對比。 */
.sub .subtxt{display:inline-block;padding:2px 8px;border-radius:4px;
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
.item{display:flex;gap:8px;padding:6px 8px;border:1px solid transparent;
      border-radius:6px;align-items:flex-start}
.item:hover{background:var(--card);border-color:var(--line)}
.item .txt{flex:1;white-space:pre-wrap;word-break:break-word}
/* 側錄／網址素材與三段式素材行視覺區隔——側錄是逐字稿、篇幅大得多，
   不分開的話會在清單裡壓過真正的外電素材（0802 實測占 30%）。 */
.item.side{border-left:3px solid var(--mut);padding-left:8px}
.item.url{border-left:3px solid var(--accent);padding-left:8px}
/* 側錄摺疊：預設只露第一行＋一小段內容，點開才看全文 */
.sumline{cursor:pointer;user-select:none;color:var(--mut)}
.sumline .caret{display:inline-block;margin-right:4px;transition:transform .15s}
.sidebody{margin-top:4px;white-space:pre-wrap}
.mark{flex:none;width:1.4em;text-align:center;font-size:15px}
.item button{visibility:hidden;flex:none}
.item:hover button{visibility:visible}
.hide{display:none}
.toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);
  background:var(--accent);color:#fff;padding:7px 16px;border-radius:16px;
  font-size:13px;opacity:0;transition:.2s;pointer-events:none;z-index:99}
.toast.on{opacity:1}
/* 剪貼簿被擋時的最後退路：把文字攤開、全選好，讓人長按「複製」 */
#modal{position:fixed;inset:0;background:rgba(0,0,0,.5);display:none;
  z-index:100;padding:16px;align-items:center;justify-content:center}
#modal.on{display:flex}
#modal .box{background:var(--bg);border-radius:8px;padding:12px;width:100%;
  max-width:680px;max-height:80vh;display:flex;flex-direction:column;gap:8px}
#modal textarea{width:100%;height:52vh;font:13px/1.6 monospace;padding:8px;
  border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg)}
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
  <div class="fgroup"><div class="flabel">來源</div><div class="bar" id="fsrc"></div></div>
  <div class="fgroup"><div class="flabel">重大</div><div class="bar" id="falert"></div></div>
  <div class="fgroup"><div class="flabel">畫面亮點</div><div class="bar" id="fhilite"></div></div>
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
const MARK_LABEL = {"△":"△ 晚班既有","▲":"▲ 無人值守","■":"■ 晨班","◆":"◆ 早班"};
// 篩選鈕上不要出現 SIDE_CNN 這種內部代碼——那是給程式看的，不是給編輯看的
const SRC_LABEL = {"SIDE_CNN":"CNN側錄","SIDE_NHK":"NHK側錄","YT":"網址素材",
                   "CNN_newsource":"NS","CNN":"NS",
                   "YNA":"韓聯社","CNA":"CNA","ENEX":"ENEX","ABC":"ABC"};
const F = {src:new Set(), mark:new Set(), big:new Set(), alert:new Set(),
           hilite:new Set(), q:""};

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
  const nf=F.src.size+F.mark.size+F.big.size+(F.q?1:0);
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
      if(mid){
        const mh=document.createElement('div'); mh.className='mid hd';
        // 藍底白字色塊只包文字，複製鈕留在色塊外（跟小分題同一套做法）
        const mt=document.createElement('span'); mt.className='midtxt';
        mt.textContent=` ${mid} `;
        mh.append(mt);
        const n=[...subs.values()].flat().filter(r=>r.kind!=='empty').length;
        mh.append(btn(`複製（${n}）`,()=>copy(midText(mid,subs),`已複製「${mid}」${n} 則`)));
        list.append(mh);
      }
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
        // 側錄要「同段落同主題算一則、預設只顯示第一行、可展開」（2026-08-09 使用者訂）。
        // 連續且同來源的側錄併成一個區塊——資料裡本來就照 TC 順序排、也帶三層分類，
        // 所以「連續同類」直接就是一則連線報導，不必另外標記。
        const units=[];
        its.forEach(r=>{
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
          const tx=document.createElement('div'); tx.className='txt';
          const bare=full.replace(/^\\s*[△▲■◆●]\\s*/,'');

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
          d.append(mk,tx,btn('複製',()=>copy(full,`已複製 ${first.id}`)));
          list.append(d);
        });
      });
    });
  });
  if(!rows.length){
    const e=document.createElement('div'); e.className='sub';
    e.textContent='沒有符合條件的素材。'; list.append(e);
  }
}

// 以下三個組字串的函式，輸出格式與 txt 完全一致（小分題之間用 +）
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
  F.src.clear();F.mark.clear();F.big.clear();F.alert.clear();F.hilite.clear();F.q="";
  document.getElementById('q').value="";
  document.querySelectorAll('.chip.on').forEach(c=>c.classList.remove('on'));
  draw();
};
// 來源排序：**明確寫死順序**（2026-08-09 使用者訂）。
// AP／RT／NS 三站一定排最前面（那是每天的主力、編輯第一眼要找的），
// 接著側錄 CNN／NHK，再來網址素材 YNA／CNA、交換平台 ENEX／ABC。名單外的排最後、按字母。
// ⚠️ 不要改用 localeCompare 之類的「自動排序」——那會讓 AP 之外的來源
//    隨著當天有沒有收到而跳來跳去，編輯每天看到的位置不一樣。
const SRC_ORDER=['AP','RT','NS','SIDE_CNN','SIDE_NHK','YNA','CNA','ENEX','ABC'];
chips('fsrc','src',uniq('src').sort((a,b)=>{
  const w=s=>{const i=SRC_ORDER.indexOf(s);return i<0?SRC_ORDER.length:i;};
  return w(a)-w(b) || a.localeCompare(b);
}),SRC_LABEL);
chips('fmark','mark',uniq('mark'),MARK_LABEL);
// 重大：🔴 在前、🟡 在後（輕重順序，不用字母序）
chips('falert','alert',uniq('alert').sort((a,b)=>(a==='🔴'?0:1)-(b==='🔴'?0:1)),
      {"🔴":"🔴 重大","🟡":"🟡 次重大"});
// 畫面亮點：**只有一個鈕**，涵蓋所有標了 🔖 的（畫面好／搖晃瞬間／日後新增的標籤）。
// 那天沒有任何 🔖 就不會長出鈕。
chips('fhilite','hilite',uniq('hilite'),{"🔖":"🔖 畫面好"});
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
    # LOGO 抓不到就整塊不輸出（而不是留一個 src="" 的破圖）
    uri = logo_data_uri()
    logo_html = (f'<div class="brand"><img src="{uri}" alt="Miniverse" '
                 f'width="80" height="80" loading="lazy"></div>') if uri else ""
    return (TEMPLATE
            .replace("__TITLE__", html.escape(title))
            .replace("__H1__", html.escape(title))
            .replace("__META__", meta_html)
            .replace("__BUILT__", datetime.now().strftime("%Y-%m-%d %H:%M"))
            .replace("__LOGO__", logo_html)
            .replace("__DATEBAR__", datebar_html)
            .replace("__ROWS__", json.dumps(rows, ensure_ascii=False)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", default=R.DEFAULT_FILE, help="狀態檔路徑")
    p.add_argument("--out", help="輸出 html 路徑（省略＝印到 stdout）")
    p.add_argument("--base-date", default="", help="晚班當天 MMDD；省略自動推得")
    p.add_argument("--window", default="", help="時間窗；省略取狀態檔算出的累計窗")
    args = p.parse_args()

    state = R.load_state(args.file)
    base = args.base_date
    if not base:
        m = re.search(r"(\d{4})-s2-state", os.path.basename(args.file))
        base = m.group(1) if m else state.get("date", "")
    win = args.window or R.window_from_state(state, base) or state.get("window_local", "")
    live_dir = os.path.dirname(os.path.abspath(args.file))
    datebar = build_datebar(base, find_archive_dates(live_dir))
    out = build_html(state, base, win, datebar)

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
