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
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2_validate as sv  # noqa: E402  共用行辨識 regex 與檔頭生成，不重寫一套
import s2_topic_dedupe as td
import s2_pending  # noqa: E402  待整併偵測（零副作用，不會拉進 s2_state）  # noqa: E402  render 後同名小分題跨大分類重複偵測

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

MARK_RE = re.compile(r"^\s*([△▲■◆●])\s*")   # `●` 為舊符號，剝離時仍須認得
RED_RE = re.compile(r"^\s*(🔴)\s*")
AIRED_RE = re.compile(r"^\s*(🟤)\s*")
SUBALERT_RE = re.compile(r"^\s*(🟡)\s*")   # 次級重大：重大但未進檔頭
STAR_RE = re.compile(r"^\s*(⭐)\s*")        # 推薦（2026-08-19，與 🔴／🟡 三者互斥，見 s2_validate）


def load_state(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: 狀態檔讀取失敗（{e}）")
        sys.exit(2)


def strip_marks(entry):
    """剝掉 raw_entry 開頭既有的時段標記／🔴／🟡／⭐／🟤，
    回傳 (有無🔴, 有無🟡, 有無⭐, 有無🟤, 淨內容)。

    標記一律由 render 重算後補回：舊資料有的有、有的沒有，照抄會出現雙標記或漏標記。
    🟤 的正規來源是 item 的 `aired` 欄位（`set-aired` 寫入），但 raw_entry 裡若被手打
    進去也認得——認完就剝掉，避免欄位與字串同時吃到而印出兩個 🟤。
    """
    e = entry.lstrip("\ufeff")
    m = MARK_RE.match(e)
    if m:
        e = e[m.end():]
    red = bool(RED_RE.match(e))
    if red:
        e = RED_RE.sub("", e, count=1)
    orange = bool(SUBALERT_RE.match(e))
    if orange:
        e = SUBALERT_RE.sub("", e, count=1)
    star = bool(STAR_RE.match(e))
    if star:
        e = STAR_RE.sub("", e, count=1)
    aired = bool(AIRED_RE.match(e))
    if aired:
        e = AIRED_RE.sub("", e, count=1)
    # 🔴／🟡／⭐ 三者互斥：升進檔頭就是 🔴，不會同時掛兩個。萬一內容裡不只一個都寫了，
    # 取較高層級的 🔴 或 🟡——降級會讓「曾進過檔頭」這個永久註記憑空消失；
    # ⭐ 是使用者事後另外標的推薦，優先度排在 🔴／🟡 之後（見 s2_validate STAR_RE 說明）。
    return red, (orange and not red), (star and not red and not orange), aired, e


def mmdd_shift(mmdd, days):
    """MMDD ± 天數（跨月正確；年份用今年，只影響閏月邊界）。"""
    d = datetime(datetime.now().year, int(mmdd[:2]), int(mmdd[2:])) + timedelta(days=days)
    return d.strftime("%m%d")


def checkpoint_time(checkpoint, base_mmdd):
    """checkpoint 標籤 → `(第幾天, HHMM)`；認不出時間回 `(0, None)`。

    標籤是 agent 自由命名的字串（`0802-1700`／`r8-0803-0100`／`exp-0803-0000`／
    `r13-0803-0910-RT補漏`），所以只認裡面的 4 位數字群：認得出當天／隔天 MMDD
    就據以判日，認不出才退回「用最後一組數字當 HHMM」。
    """
    toks = re.findall(r"\d{4}", checkpoint or "")
    nxt = mmdd_shift(base_mmdd, 1) if base_mmdd else None
    for n, t in enumerate(toks):
        if t == base_mmdd:
            return 0, (int(toks[n + 1]) if n + 1 < len(toks) else None)
        if t == nxt:
            return 1, (int(toks[n + 1]) if n + 1 < len(toks) else None)
    return 0, (int(toks[-1]) if toks else None)   # 認不出日期：假設當天


def window_from_state(state, base_mmdd):
    """算出**開檔至今**的累計時間窗字串，供檔頭第 2 行使用（2026-08-04 訂正）。

    ⚠️ 原本是直接印狀態檔的 `window_local`，但那個欄位存的是**單輪**掃描區間
    （agent 每輪覆蓋成 `16:00-18:00` 這種），所以檔頭永遠只反映最後一輪、
    看不出這份交接檔累積掃了多久——使用者 2026-08-04 指出。

    起點：`_top.window_start`（第一輪建檔時寫一次，格式 `YYYY-MM-DD HH:MM` 或 `HH:MM`）；
    沒有就退回**最早的 checkpoint**。⚠️ 退路會少算第一輪往前涵蓋的那段
    （例：16:00 那輪掃的是 13:00–16:00，checkpoint 只看得到 16:00），
    所以第一輪應該把 `window_start` 設好。
    終點：頂層 `checkpoint`（目前這輪），沒有就取最晚的 checkpoint。
    """
    times = [checkpoint_time(v.get("first_seen_checkpoint"), base_mmdd)
             for v in state.get("items", [])
             if isinstance(v, dict) and v.get("first_seen_checkpoint")]
    times = [t for t in times if t[1] is not None]

    end = checkpoint_time(state.get("checkpoint"), base_mmdd)
    if end[1] is None:
        end = max(times) if times else None
    if end is None:
        return ""

    start_txt = (state.get("window_start") or "").strip()
    m = re.search(r"(\d{1,2}):(\d{2})", start_txt)
    if m:
        sday = 1 if (base_mmdd and mmdd_shift(base_mmdd, 1) in start_txt) else 0
        start = (sday, int(m.group(1)) * 100 + int(m.group(2)))
    elif times:
        start = min(times)
    else:
        return ""

    def fmt(t):
        d = mmdd_shift(base_mmdd, t[0]) if base_mmdd else ""
        hm = f"{t[1] // 100:02d}:{t[1] % 100:02d}"
        return f"{datetime.now().year}-{d[:2]}-{d[2:]} {hm}" if d else hm

    # 只回傳起訖，**不要**自己補「（約N hrs）」——時數由 header_from_lines 算，
    # 這裡先補上會被它當成終點字串的一部分，變成「18:00（約5hrs）（約5hrs）」。
    return f"{fmt(start)}–{fmt(end)}"


def mark_for(checkpoint, base_mmdd):
    """依 `first_seen_checkpoint` 推時段標記（WP1 前提三：由 render 自動補）。

    判準沿用 `13` 隔夜續掃節（2026-08-04 定案固定排程，推翻 2026-08-03 晚一度改成
    22:00／05:00 的訂正，也推翻更早「23:00 那輪算▲」的原始規則——使用者確認
    16:00～23:00 全部仍算晚班有人值班、一律 `△`，23:00 是下班前最後一輪；
    早班上班時間維持 07:00，不是 2026-08-03 晚一度改過的 05:00）：
    23:00（含）前＝`△`、隔天 07:00 前＝`▲`、07:00–09:00＝`■`、09:00–14:00＝`◆`。
    固定排程（原則性，使用者可當天隨時特例調整）：
    16:00／18:00／20:00／22:00／23:00＝晚班（`△`，23:00 是下班前最後一輪）；
    01:00／04:30＝無人值守（`▲`）；07:00／08:00＝晨班（`■`）；
    10:00／12:00／13:00＝早班（`◆`）。
    checkpoint 標籤是 agent 自由命名的字串（`0802-1700`／`r8-0803-0100`／
    `exp-0803-0000`／`r13-0803-0910-RT補漏`），所以只認裡面的 4 位數字群：
    認得出當天／隔天 MMDD 就據以判日，認不出才退回「用最後一組數字當 HHMM」。
    補掃輪（例如 09:10 的 `r13-…-RT補掃` 撈回稍早漏掉的素材）用 checkpoint 判會標成 `■`，
    但它們其實屬更早的時段——這種要用 `s2_state.py set-mark` 在該則上寫死標記，見下方 override。
    """
    day, hhmm = checkpoint_time(checkpoint, base_mmdd)
    if hhmm is None:
        return "△"
    if day >= 1:
        if hhmm < 700:
            return "▲"
        return "■" if hhmm < 900 else "◆"
    return "△"  # 同一晚班日：16:00～23:00 全部仍算晚班有人值班，一律 △


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
    """素材行／側錄段落：`{時段標記} {🔴|🟡|⭐ 若有} {raw_entry 原文}`。

    raw_entry **零加工**輸出（側錄逐字不壓縮、不加 `▎`、TC 冒號格式照留，見 14-S2b）；
    側錄是多行的，標記只加在第一行（TC 行）行首。
    YouTube 兩行式（13b §4c）的網址行**照樣帶時段標記**，但標記與網址之間
    一定要有半形空格——`△https://…` 會黏成一串、網址點不開（2026-08-03 使用者訂正）。
    """
    red, orange, star, aired_txt, body = strip_marks(it.get("raw_entry", "") or "")
    # 該則若有寫死的 `mark`（補掃輪等 checkpoint 判不準的情形，見 set-mark）優先用它
    mk = it.get("mark") if it.get("mark") in ("△", "▲", "■", "◆", "●") else         mark_for(it.get("first_seen_checkpoint"), base_mmdd)
    prefix = mk + " "
    if red:
        prefix += "🔴 "
    elif orange:
        prefix += "🟡 "          # 重大但未進檔頭（2026-08-05），與 🔴 互斥
    elif star:
        prefix += "⭐ "          # 推薦（2026-08-19），與 🔴／🟡 互斥
    # 🟤 已播：正規來源是 `aired` 欄位（set-aired 寫入），raw_entry 手打的也認
    if it.get("aired") or aired_txt:
        prefix += "🟤 "
    lines = body.split("\n")
    # lstrip：raw_entry 首行若自帶前導空白，補上標記後會變成「△  內容」或讓網址位移；
    # prefix 固定以一個半形空格收尾，確保 `△ https://…` 不會黏在一起
    lines[0] = prefix + lines[0].lstrip()
    return lines


def _lcs_len(a, b):
    """最長共同**連續**子字串長度。中文短名用這個比 bigram 準：
    `野火`⊂`歐洲野火`＝2、`熱浪`⊂`亞洲熱浪`＝2、`華州野火`vs`加州野火`＝3。
    """
    if not a or not b:
        return 0
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


# 相近判準：共同連續子字串 ≥ 2 個字。1 個字太鬆（`美股`vs`亞股`只共用「股」、
# `政治`vs`政壇`只共用「政」都會被誤湊在一起），2 個字實測剛好：
# 熱浪／野火／事故／財報／動物 這類真正的同族詞都是 2 字以上。
_TOPIC_SIM_MIN = 2


def order_topics(mids, pinned=()):
    """中主題排序：**維持到貨順序，但新主題插到名稱最相近的既有主題旁邊**。

    `pinned`＝狀態檔 `topic_order[大分類]` 指定的人工順序（2026-08-10 加）。
    給了就**先照它排**，其餘（今天新出現、清單裡沒有的）再走下面的自動邏輯插進去。
    為什麼要存進狀態檔：中主題順序原本**完全是 render 當下推導的**，沒有任何地方
    存——手動排完，下一輪 render 照舊演算法重算就蓋掉了（跟「不要手改 txt」同一個
    道理，render 是狀態檔的單向投影）。要讓人工排序留得住，就得有個欄位。
    ⚠️ `pinned` 裡今天不存在的中主題**自動略過**，不會憑空生出空標題。

    2026-08-05 使用者訂案。原本純粹依素材到貨順序排，跨輪的相關主題必然散開——
    0804 實測【歐洲野火】(18:00 到) 與【野火】(22:00 到) 中間隔了 4 個不相干的主題，
    只因為晚了 4 小時；【亞洲熱浪】【歐洲熱浪】【熱浪】更是散在三處。

    做法：照到貨順序逐一放入，每個新主題找出**共同連續子字串最長**的既有主題；
    達門檻就插在**該族最後一個**的後面（插在最後一個而不是第一個，多個同族才會連成一片），
    沒達門檻就照舊接在最後。純顯示層調整，不動任何資料。
    """
    have = set(mids)
    out = [p for p in (pinned or ()) if p in have]      # 人工順序優先，不存在的跳過
    for m in mids:
        if m in out:                                     # 已被 pinned 放好
            continue
        best, best_at = 0, -1
        for idx, seen in enumerate(out):
            sc = _lcs_len(m, seen)
            if sc >= best:                 # `>=`：同分取較後者，同族才會連續
                best, best_at = sc, idx
        if best >= _TOPIC_SIM_MIN and best_at >= 0:
            out.insert(best_at + 1, m)
        else:
            out.append(m)
    return out


# 中主題重排的排除名單（2026-08-05 使用者訂案：**只從 0805 新檔起生效，不追溯**）。
# `0804` 那份當時正在跑（早班 10:00 輪剛更新），中途換排列會讓已經在看的編輯錯亂。
# ⚠️ 用明確的排除集合、不用 `mmdd >= "0805"` 比大小——後者跨年就壞掉
# （2027-01-01 的 `0101` 會小於 `0805`，整年都不重排）。
# 這份名單留著不必清：已歸檔的舊檔本來就不該重新渲染，留著剛好保住它們的原始排列。
TOPIC_ORDER_SKIP_MMDD = {"0804"}


def group_items(state, base_mmdd=""):
    """大分類 → 中主題 → 小分題 → [素材]，小分題與素材保原順序。

    中主題順序另外經 `order_topics()` 調整（相近名稱靠攏，見該函式）；
    `TOPIC_ORDER_SKIP_MMDD` 裡的日期維持原本的到貨順序。
    """
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
            if not mid:
                # ⚠️ 中主題留白會在交接單印出**一行空標題**，編輯完全看不出那底下是什麼
                # （0810-0100 實例：`PO-19SU` 稿未到、站方欄位全空，agent 沒給分類，
                #   話題格底下就冒出一個 `【】`）。給它一個看得懂的名字，
                #   讓「這則還沒歸位」變成**明講的狀態**而不是版面瑕疵。
                # ⛔ 不要在這裡猜它該掛哪一格——猜錯比留白更糟，那會讓錯的分類看起來像對的。
                mid = "未分類"
        groups.setdefault(big, {}).setdefault(mid, {}).setdefault(sub, []).append(it)
    # 常駐中主題（2026-08-11 使用者訂案）：`_top.resident_topics` 指定的中主題
    # 不論今天有沒有素材，都要在對應大分類底下出現空字典——render_block 遇到
    # 空字典只印【中主題】標題、不印任何素材行，跟真的有素材時同一套排版邏輯，
    # 不必另外處理。⚠️ 用 setdefault 不覆蓋：今天若已經有真素材掛在這個中主題，
    # 維持原本內容，不要把它清空。
    for big, resident_mids in (state.get("resident_topics") or {}).items():
        bucket = groups.setdefault(big, {})
        for mid in resident_mids:
            bucket.setdefault(mid, {})
    # 中主題重排：人工指定的 `topic_order` 優先，其餘相近名稱靠攏
    #（小分題與素材順序完全不動）
    if base_mmdd not in TOPIC_ORDER_SKIP_MMDD:
        pinned_all = state.get("topic_order") or {}
        for big in groups:
            mids = groups[big]
            order = order_topics(list(mids), pinned_all.get(big, ()))
            groups[big] = {m: mids[m] for m in order}
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
    groups = group_items(state, base_mmdd)
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


def backup_prev(path):
    """覆蓋前把現行 txt 另存 `{path}.prev.txt`（只留最近一版，不無限累積）。

    diff3／snapshot 廢除的理由是「不需要拿舊 txt 比對保留人工編輯」，但那跟
    「留一份東西讓 render 本身出包時能救」是兩件事——後者這裡補上。純檔案操作，
    不影響省 token 的設計、不涉及 AI 判斷。
    """
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8-sig") as f:
                prev = f.read()
            with open(path + ".prev.txt", "w", encoding="utf-8", newline="\n") as f:
                f.write(prev)
        except OSError as e:
            print(f"⚠️ 備份上一版失敗（{e}）——仍照常覆蓋，但這輪沒有 .prev.txt 可救",
                  file=sys.stderr)


def write_atomic(path, text):
    """先備份現行版（見 backup_prev），再 tmp + rename 覆蓋（中途失敗不留半殘 txt）。"""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    backup_prev(path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return f.read()
    except OSError:
        return None


def guard_manual_edit(out_path, state, force):
    """擋掉「手改 txt 被 render 無聲覆蓋」與「側錄只貼 txt 沒入狀態檔」。

    render 是狀態檔的單向投影，覆蓋是全量的——txt 上任何沒進狀態檔的東西，
    這一寫就永久消失且不會有任何錯誤訊息。所以覆蓋前先驗指紋：
    現行 txt 的 sha 對不上上次 render 存的 `last_render_sha` ＝ 有人動過，
    停下來要人確認（`--force` 才覆蓋）。
    """
    cur = read_text(out_path)
    if cur is None:
        return True                      # 檔案還不存在，直接寫
    want = state.get("last_render_sha")
    if want and sha(cur) == want:
        return True                      # 就是上一輪 render 的產物，沒被動過
    why = ("這份 txt 不是上一輪 render 的產物（sha 對不上）"
           if want else "狀態檔沒有 last_render_sha（這份 txt 可能是手寫的舊版）")
    if force:
        print(f"⚠️ {why}——依 --force 仍覆蓋（下方對帳會列出因此掉了什麼）。", file=sys.stderr)
        return True
    print(f"⛔ 拒絕覆蓋：{why}。", file=sys.stderr)
    print("   txt 上沒進狀態檔的內容一覆蓋就永久消失（最常見：手改 txt、側錄只貼 txt "
          "沒跑 add-side）。先把那些內容寫回狀態檔，或確認可以丟棄後加 --force。",
          file=sys.stderr)
    return False


def reconcile(old_text, new_text):
    """對帳：列出這次 render 相對現行 txt 的增減，掉東西當場看得見。"""
    def index(t):
        lines = (t or "").split("\n")
        mats = {re.match(sv.CODE, l).group(0) for _, l in sv.material_lines(lines)}
        # ⚠️ 這裡要跟 sv.SIDE_RE 用**同一套**日期段規則（2026-08-09 實錯）：
        #    側錄 TC 加日期後，這條漏了 `_SIDE_DATE`，`CNN 08-09 151439` 匹配不到
        #    → `.group(0)` 對 None 取值，整個 render 在寫完 txt 之後才崩，
        #    品質掃／HTML／對帳查核全部沒跑，離開碼還變成非 0。
        #    **側錄的格式規則只要有一處沒同步，就會在別處炸掉或隱形。**
        sides = {re.match(rf"^(?:CNN|NHK) {sv._SIDE_DATE}{sv._TC}", l).group(0)
                 for _, l, _ in sv.side_lines(lines)}
        yts = {sv.YT_URL_RE.match(u).group(1) for _, u, _ in sv.yt_blocks(lines)}
        return mats, sides, yts
    (om, os_, oy), (nm, ns, ny) = index(old_text), index(new_text)
    print(f"對帳：素材 {len(nm)} 則（{len(nm) - len(om):+d}）／"
          f"側錄 {len(ns)} 段（{len(ns) - len(os_):+d}）／"
          f"YouTube {len(ny)} 支（{len(ny) - len(oy):+d}）")
    lost = [("素材", sorted(om - nm)), ("側錄", sorted(os_ - ns)), ("YouTube", sorted(oy - ny))]
    for name, ids in lost:
        if ids:
            print(f"⚠️ 現行 txt 有、本次 render 沒有的{name} {len(ids)} 筆："
                  f"{'／'.join(ids[:8])}{' …' if len(ids) > 8 else ''}", file=sys.stderr)
            print(f"   →（多半是沒進狀態檔）確認是不是漏了 add-side／update-entry",
                  file=sys.stderr)


def touch_last_render(state_path, text):
    """在狀態檔記下這次 render 的時間與指紋（resume 計數與手改偵測靠它）。"""
    try:
        with open(state_path, encoding="utf-8-sig") as f:
            raw = json.load(f)
        raw["last_render_ts"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")
        raw["last_render_sha"] = sha(text)
        tmp = state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=1)
        os.replace(tmp, state_path)
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ last_render_ts 未寫入（{e}）——txt 已產出，不影響本輪", file=sys.stderr)


def warn_unreconciled(state):
    """收工時把「這一輪沒做清單對帳」喊出來。

    2026-08-06 立。**清單對帳是唯一能機械驗證「窗內真的全撈到」的步驟**，但它不會
    自動觸發、得靠當輪 agent 主動跑——0806 RT 兩次漏收都倒在這裡：07:00／08:00 是
    「還不知道有這工具」，10:41 是**知道、寫下「留待下次補做」、然後直接 render 收工**。

    ⚠️ **只警告不擋**：無人值守時段（`▲`）硬擋會讓整輪卡死，違反 §5「半夜禁問」。
    要的是「忘記回頭補」在收工那一刻現形，而不是等別人事後查。
    """
    # ⚠️ 兩種形狀都要吃：render 的 load_state() 回的是**扁平的原始 JSON**，
    # s2_state.load() 回的是包在 `_top` 底下的。0806 實測時就是踩到這個——
    # 只認 `_top` 的話 checkpoint 永遠讀成空字串、**每一輪都誤報沒對帳**，
    # 而誤報的下場是這個警告被當成雜訊、然後被忽略，等於白做。
    top = state.get("_top") if isinstance(state.get("_top"), dict) else state
    cp = top.get("checkpoint") or ""

    # 🔴 **先確認 checkpoint 有推進，否則底下的對帳查核會被騙過去**（2026-08-09 實錯）。
    # 0809-0800 那輪：agent 收了 13 則、也做了三站對帳，**但忘了 set-top**，
    # 頂層 checkpoint 停在 `0809-0700`。於是這道防線去查 0700 的紀錄、看到齊全就放行——
    # **漏做 set-top 會順便讓對帳查核失效**，兩個問題疊在一起變成無聲通過。
    # 判準：狀態檔裡若存在「比頂層 checkpoint 還新」的 first_seen_checkpoint，
    # 就代表有輪次寫了東西進來卻沒登記。
    items = state.get("items") or []
    seen = {str(i.get("first_seen_checkpoint")) for i in items if isinstance(i, dict)}
    seen.discard("None")
    newer = sorted(c for c in seen if c > cp) if cp else []
    if newer:
        bar = "!" * 60
        print(f"\n{bar}\n⚠️  頂層 checkpoint 是 {cp}，但狀態檔裡已有更新的輪次：{'／'.join(newer)}")
        print("    → 那一輪忘了 set-top。後果有三個，第三個最危險：")
        print("      ① 外殼查核找不到狀態檔，誤報「本輪 0 則／txt 沒產出」")
        print("      ② 對帳留痕被記到上一輪的格子裡")
        print("      ③ **下面的對帳查核會去查上一輪的紀錄，看到齊全就放行**")
        print(f"    補救：python scripts/s2_state.py set-top checkpoint {newer[-1]}\n{bar}")

    log = top.get("reconcile_log")
    log = log if isinstance(log, dict) else {}   # 手改過的狀態檔什麼型別都可能
    done = log.get(cp)
    done = done if isinstance(done, dict) else {}
    miss = [s for s in ("RT", "AP", "NS") if s not in done]
    if not miss:
        print(f"OK 清單對帳三站齊全（{cp}）")
        return
    bar = "!" * 60
    tail = "：" + "／".join(miss) + " 缺" if done else "（三站全缺）"
    print(f"\n{bar}\n⚠️  這一輪（{cp}）沒有做清單對帳{tail}")
    print("    對帳是唯一能機械驗證「窗內真的全撈到」的步驟。0806 沒做的那幾輪，")
    print("    事後補到 RT 2 則、NS 19 則——當輪全都回報「正常完成」。")
    print("    補做：撈清單存檔後跑")
    print("      python scripts/s2_audit.py --mmdd {MMDD} --rt-list <檔> "
          "--ap-list <檔> --ns-list <檔>")
    print(f"    真的做不了就 needs-review add 寫明原因，不要無聲跳過。\n{bar}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", default=DEFAULT_FILE, help="狀態檔路徑")
    p.add_argument("--out", help="輸出 txt 路徑（省略＝印到 stdout 預覽，不寫檔）")
    p.add_argument("--window", default="",
                   help='時間窗，如 "14:00 - 09:00"；省略取狀態檔 window_local')
    p.add_argument("--base-date", default="", help="晚班當天 MMDD；省略由 --out 檔名或狀態檔推得")
    p.add_argument("--date", default="", help="YYYY-MM-DD，檔頭時間窗前綴用")
    p.add_argument("--no-touch-state", action="store_true", help="不回寫 last_render_ts")
    p.add_argument("--force", action="store_true",
                   help="現行 txt 被手改過也照樣覆蓋（會永久丟掉那些沒進狀態檔的內容）")
    p.add_argument("--no-check", action="store_true", help="render 後不自動跑品質掃")
    p.add_argument("--no-topic-check", action="store_true",
                   help="render 後不自動跑同名小分題跨大分類重複偵測")
    p.add_argument("--no-html", action="store_true",
                   help="不順便產出 HTML 檢視版（預設會產，給編輯用手機看的那份）")
    args = p.parse_args()

    state = load_state(args.file)
    base = args.base_date
    if not base and args.out:
        m = re.search(r"(\d{4})晚班交接", os.path.basename(args.out))
        base = m.group(1) if m else ""
    if not base:
        m = re.search(r"(\d{4})-s2-state", os.path.basename(args.file))
        base = m.group(1) if m else state.get("date", "")
    # 時間窗優先序：--window 明確指定 > 由狀態檔算出的累計窗 > 舊的 window_local。
    # ⚠️ `window_local` 是**單輪**區間（agent 每輪覆蓋），拿它當檔頭會讓交接檔
    # 看起來只掃了兩小時——2026-08-04 使用者指出，改由 window_from_state() 算。
    win = args.window or window_from_state(state, base) or state.get("window_local", "")
    text = render(state, win, base, args.date)
    if not args.out:
        sys.stdout.write(text)
        return
    old = read_text(args.out)
    if not guard_manual_edit(args.out, state, args.force):
        sys.exit(3)
    write_atomic(args.out, text)
    if not args.no_touch_state:
        touch_last_render(args.file, text)
    print(f"OK 已渲染 {args.out}（{len(text.splitlines())} 行 / {len(text)} 字元）")
    # 收工保險（2026-08-26）：agent 不保證每輪都跑 resume（0825-2200 就沒跑）。
    # ⛔ 只警告不擋——無人值守的排程硬擋會讓整輪產不出交接檔。
    s2_pending.warn(where="render")
    reconcile(old, text)
    if not args.no_check:
        sv.check(args.out)
    if not args.no_topic_check:
        today_hits, cross_hits = td.check(args.file)
        n = len(today_hits) + len(cross_hits)
        if n:
            print(f"⚠️ 主題重複偵測 {n} 組命中，跑 "
                  f"`python s2_topic_dedupe.py --file \"{args.file}\"` 看詳情、"
                  f"確認後用 set-category 手動改（純提示，不影響本次已寫入的 txt）")
        else:
            print("OK 主題重複偵測 0 命中")

    # 機動 T 的觸發點：跟覆蓋率同一個位置報，agent 才會知道今天有這一格。
    # ⛔ 只是**告知**，不是授權 agent 自己開——開／收一律使用者下令。
    try:
        _sp = __import__("s2_state").load_special_t()[0]
        if _sp:
            print(f"📌 今天有機動 T：{'、'.join(_sp)}"
                  f"（**加掛**不是取代，符合的素材連同既有固定 T 一起下）")
    except Exception:
        pass

    # ── T/C 覆蓋率閘門（A10 v2，2026-08-24 上線當晚加）─────────────────────
    # 🔴 為什麼需要這道閘門：0824-2000 輪實證，`13f` 的 T/C 判準**完整進了 context**
    #    （rule_shas 相符、transcript 裡讀得到判準段與指令範例），agent 也照常下了
    #    4 次 `set-category`，但 `set-tc` **一次都沒呼叫**（以 tool_calls_by_name
    #    與 transcript 逐行掃描兩種獨立方法交叉驗證過，比照 R17 的教訓）。
    #    屬 T7／A23 家族：規則已改、行為沒跟上。**光把判準寫進規則不夠，要有觸發點。**
    #
    # 設計取自 `list-topics` 的成功模式：它執行率高，是因為有「開新中主題前」這種
    # 明確觸發時機。這裡就是幫 `set-tc` 造一個——每輪 render 完固定報一次，
    # 並且**把可以直接貼的指令印出來**，不要只說「請去標」。
    #
    # ⛔ 純提示，不影響已寫入的 txt。txt 是權威產物，不能為了附屬品讓收工失敗
    #    （同本檔 HTML 那段的理由）。
    try:
        import s2_render_matrix as _rm
        _n, _stored, _mixed, _heur, _diff = _rm.tc_stats(state, base)
        if _heur:
            print(f"⚠️ T/C 覆蓋率 {(_n - _heur) * 100 // max(_n, 1)}%"
                  f"（{_n} 則裡有 {_heur} 則還沒標，網頁上那些會退回關鍵詞兜底／未分類）")
            print(f"   ⛔ 收工前請補標。查沒標的是哪幾則：")
            print(f'   python scripts/s2_state.py --file "{args.file}" show --fields id,cat,T,C')
            print("   補標（⚠️ 整批一次下，每 checkpoint 有呼叫次數上限）：")
            print(f'   python scripts/s2_state.py --file "{args.file}" '
                  f'set-tc --pairs "id1=政治,社會/臺灣;id2=天災天氣/日本"')
            print(f"   判準與名單見 common/13f「T／C 標籤」節。")
            # 🔴 2026-08-25：這道閘門把 set-tc 的觸發點放在 render **之後**，
            #    於是本輪新增的那一批一定是「render 完才標」，而沒有人再 render
            #    一次——0825-1200 實測頁面 618 列有 53 列落回關鍵詞兜底
            #    （22 列 C＝未分類），狀態檔卻是 100% 標好的。使用者看到的
            #    「大量未分類」就是這個時序造成的，不是 agent 沒標。
            print("   🔴 補標完**一定要再跑一次本指令**（render），否則網頁與 txt "
                  "停在上面那個覆蓋率——狀態檔標好了，頁面不會自己更新。")
        else:
            print(f"OK T/C 覆蓋率 100%（{_n} 則全部已標）")
    except Exception as e:                                  # noqa: BLE001
        print(f"⚠️ T/C 覆蓋率檢查失敗（不影響 txt）：{type(e).__name__}: {e}")

    # HTML 檢視版：txt 旁邊順手產一份（2026-08-09）。編輯用手機開 Apps Script
    # 網址看的就是它，所以**每輪都要跟著更新**，否則手機上看到的是舊資料。
    # ⛔ **失敗絕不可以影響 txt**——txt 是權威產物、HTML 只是衍生檢視層，
    #    為了一個附屬品讓收工整個失敗是本末倒置。所以整段包在 try 裡。
    if not args.no_html:
        try:
            import s2_render_html as rh
            html_out = re.sub(r"\.txt$", ".html", args.out)
            if html_out == args.out:          # --out 不是 .txt 結尾就別亂猜
                html_out = args.out + ".html"
            # 🔴 歷史列一定要在這裡算（2026-08-11 實錯）：歷史列上線那天只驗了
            #    `python s2_render_html.py` 那條獨立入口，**但排程每輪走的是這裡**，
            #    而這裡當時直接呼叫 `build_html(state, base, win)`、沒帶 datebar——
            #    結果功能「上線」了卻在正式流程裡從來沒生效過，每輪產出的 html
            #    都沒有歷史列。⛔ 兩條路都會產出正式檔案，**新功能兩邊都要接**。
            live_dir = os.path.dirname(os.path.abspath(args.file))
            datebar = rh.build_datebar(base, rh.find_archive_dates(live_dir))
            # A10 v2（2026-08-24 使用者裁決）：線上版換成 T/C 矩陣版。
            # ⛔ 這不是第三條 render 路——`s2_render_html.py --matrix` 那條獨立入口
            #    也呼叫同一支 build_html（2026-08-11 事故就是只接一條）。
            # 緊急開關：設環境變數 S2_HTML_LEGACY=1 就退回舊版面，不必改程式、
            # 不必 git revert——排程輪次中途也能用。
            if os.environ.get("S2_HTML_LEGACY") == "1":
                html_body = rh.build_html(state, base, win, datebar)
                print("⚠️ S2_HTML_LEGACY=1，本輪 HTML 用舊版面")
            else:
                import s2_render_matrix as rm
                html_body = rm.build_html(state, base, win, datebar)
            with open(html_out, "w", encoding="utf-8") as f:
                f.write(html_body)
            print(f"OK 已產出 HTML 檢視版 {html_out}")
            # ⚠️ 側錄「則數」現在有**兩份算法**：txt 檔頭走 sv.side_units（解析文字），
            #    網頁版走 JS（篩選會變動，必須在瀏覽器端算）。兩份遲早會漂移，
            #    而症狀是「txt 說 X 則、網頁說 Y 則」——同一份資料兩個數字，
            #    這種不一致最傷信任。所以每輪拿狀態檔的欄位再算一次當對照。
            with open(args.out, encoding="utf-8") as f:
                txt_units = sv.side_units(f.read().splitlines())
            rows = [r for r in rh.collect(state, base) if r.get("kind") == "side"]
            prev, js_units = None, 0
            for r in rows:
                k = (r["src"], r["big"], r["mid"], r["sub"])
                if k != prev:
                    js_units += 1
                prev = k
            if txt_units != js_units:
                print(f"⚠️ 側錄則數兩邊不一致：txt 檔頭 {txt_units} 則／"
                      f"網頁版 {js_units} 則——合併規則漂移了，看 sv.side_units")
        except Exception as e:                # noqa: BLE001
            print(f"⚠️ HTML 檢視版產出失敗（不影響 txt）：{type(e).__name__}: {e}")

    warn_unreconciled(state)      # 放最後：收工前最後看到的就是這行


if __name__ == "__main__":
    main()
