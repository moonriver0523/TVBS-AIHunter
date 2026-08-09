# -*- coding: utf-8 -*-
"""S2 晚班交接品質掃／檔頭統計／三方比對腳本（V2）。

用法：
  python s2_validate.py check <晚班交接.txt>       格式異常掃描
  python s2_validate.py stats <晚班交接.txt> [--window "16:00 - 23:00"]
                             [--alert "▲ IN-23SU 希臘消防直升機空中相撞…"] [--clear-alerts]
                                                   輸出檔頭三／四行＋重大提醒行
                                                   （--alert 省略時沿用檔內既有重大行）

⚠️ 2026-08-03（WP1）起 txt 由 `s2_render.py` 從狀態檔全量渲染、人工不改，
`diff3` 三方比對與 `.snapshot.txt` 一併廢除（沒有「人工編輯過的行」可裁決了）。

規則依據 common/13-S2-定時掃帶.md「最終整併：稿未到清查＋品質掃」。
"""
import argparse
import os
import re
import sys
from datetime import datetime

# ⚠️ 用 reconfigure 不用 TextIOWrapper：包第二層時（例如 s2_state 匯入 s2_validate）
# 舊寫法會讓其中一個 wrapper 被回收時關掉底層 buffer，整支腳本以 "I/O operation on
# closed file" 掛掉（2026-08-03 WP1 實錯）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # py<3.7
        pass

# 素材代碼（行首）：RT#### / AP####### / APcctv###### / CNN Newsource 前綴-##XX / 側錄 CNN|NHK ######
# ⚠️ NS 代碼的字母前綴**不是固定兩碼**（2026-08-04 實錯）：除了常見的 `PY-03MO`／`WE-001TU`，
# 還有 `DIG-01TU`（數位專題）、`HIST-02TU`（史上的今天）這類三、四碼前綴。原本寫死 `[A-Z]{2}`，
# 那兩則就**整行不被辨識成素材行**——正文印得出來（render 直接輸出 raw_entry、不靠 CODE），
# 但檔頭則數少算、品質掃完全跳過它們，而且回報還是「0 命中」。這種漏是靜默的，
# 放寬成 2–6 碼；日後再冒出更長的前綴，症狀一樣是「txt 有這行但檔頭數字對不上」。
# ⚠️ **數字段同樣不是固定 2–3 碼（2026-08-07 實錯）**：NS 的 `SN-1000FR`（西語直式版，
# bitcentralId 原樣就是 4 位數）被 `\d{1,3}` 擋掉，症狀與上面那次一模一樣——txt 印得出來、
# 檔頭卻只算 4 則（實收 5 則）。已放寬成 1–4 碼。**這兩處是同一種靜默漏算，
# 看到「txt 行數與檔頭則數對不上」就先回來檢查這條正則。**
CODE = (r"(?:RT\d{4}|APcctv\d{6}|AP\d{7}|[A-Z]{2,6}-\d{1,4}[A-Z]{2}"
        r"|(?:YNA|CNA)\d{2,3}"                     # 韓聯社／CNA 網址素材（2026-08-09）
        r"|ENEX\d{4,8}"                            # ENEX（2026-08-09，人工下令才跑、不進固定掃帶）
        r"|(?:CNN|NHK) (?:\d{2}-\d{2} )?\d{6})")   # 側錄的日期段可有可無（2026-08-09）
LINE_RE = re.compile(rf"^{CODE}(?:\s*/\s*{CODE})*\s")

# 時段標記（2026-08-02 訂案，2026-08-03 補 △，2026-08-04 固定排程定案邊界＋補 ◆）：
# 素材代碼前帶一個時段符號。16:00–23:00 五輪皆晚班（`△`），23:00 是下班前最後一輪；
# △＝23:00 前晚班既有、▲＝23:00–07:00 無人值守新增、■＝07:00–09:00 晨班新增、
# ◆＝09:00–14:00 早班新增。固定排程細節見 `common/13`「隔夜續掃」節。
# ⚠️ 2026-08-03 起 △ 也要寫出來（原本是「無標記」），標記齊全才方便快速瀏覽；
# 「隔夜續掃 N 則」只統計 ▲／■／◆，△ 是基底不計入。
# 一律先剝掉再做其餘比對，否則整行會兩邊都漏辨識（同 SIDE_RE 踩過的坑）。
#
# ⚠️ **`●` 是舊符號，2026-08-04 起改用 `■`**（使用者反映 `●` 與其他圓形標記易混淆）。
# **只改生成、不改解析**：新的 render 一律產出 `■`，但這裡**必須繼續認得 `●`**——
# 已歸檔的舊 txt（0802／0803…）整份都是 `●`，正則不收的話那些行會 LINE_RE 不 match、
# 從品質掃與檔頭統計裡**靜默消失**（數量少算且不報錯，△ 上線時已經踩過一次）。
# 舊資料不回頭改（使用者訂案），所以這個相容分支要長期留著，不要當成過渡碼清掉。
LEGACY_MARKS = {"●": "■"}
# 順序＝檔頭圖例與「隔夜續掃」的列出順序，照時間排；`●` 緊接在同時段的 `■` 之後，
# 這樣舊檔重新渲染時圖例順序與原本一致（不放最後面，否則 ▲／●／◆ 會變成 ▲／◆／●）。
MARKS = {"△": "23:00 前既有", "▲": "23:00–07:00 新增", "■": "07:00–09:00 新增",
         "●": "07:00–09:00 新增（舊符號）", "◆": "09:00–14:00 新增"}
OVERNIGHT_MARKS = ("▲", "■", "●", "◆")  # 計入檔頭「隔夜續掃」的，不含 △
# 素材行的重大標記（2026-08-03 使用者訂案）：時段標記之後、代碼之前插一個 🔴，
# 讓編輯在正文區也能一眼找到檔頭 `🔴 重大：` 點名的那幾則。行首對齊不變。
#   `▲ 🔴 IN-23SU (…) ▎…`
# ⚠️ 一併剝掉才不會讓整行漏辨識——不剝的話 LINE_RE 不 match，該行會從品質掃與
# 檔頭統計裡整個消失（△ 上線時已經踩過一次，數量會少算）。
RED_RE = re.compile(r"^(🔴)\s*")
MARK_RE = re.compile(r"^([△▲■◆●])\s*")   # `●` 為舊符號，見上方說明，不可移除
# 已播標記（2026-08-04 使用者訂案）：本台已經做過這則新聞的素材。
# **仍然照常摘要入庫**——後續發展可能還要再做，只是優先度降低，讓編輯一眼略過已處理的。
# 位置在 🔴 之後、代碼之前，兩者可並存：`▲ 🔴 🟤 IN-23SU (…) ▎…`
# ⚠️ 跟 🔴 同樣必須一併剝掉，否則 LINE_RE 不 match，整行會從品質掃與檔頭統計裡消失。
AIRED_RE = re.compile(r"^(🟤)\s*")
# 次級重大標記 🟡（2026-08-05 使用者訂案）：**重大、但沒擠進檔頭前三**。
# ⚠️ 一度用過 🟠 橘圓（同日稍早），使用者反映與 🔴 對比不夠明顯，當天即改為 🟡。
#    上線範圍：**0805 新開的晚班交接起**，0804 以前不追溯（那幾天本來就沒有任何一則標過）。
# 為什麼要分兩層：檔頭只有 3 行上限，但一晚常有 10 幾件重大事件——單一層級下，
# agent 判斷「這則排不進前三」時會連正文標記一起放棄（0804 整晚只標 1 則的機制）。
# 拆開之後標 🟡 不必宣稱自己是今天前三，門檻的綁架就解除了。
#   🔴＝曾進過檔頭（最高層級，永久保留）／🟡＝重大但未進檔頭（同樣永久保留）
# ⚠️ 兩者互斥：升進檔頭就改標 🔴，不會同時出現。
SUBALERT_RE = re.compile(r"^(🟡)\s*")


def strip_mark(l):
    """回傳 (時段標記或空字串, 去掉時段標記／🔴／🟡／🟤 之後的行)。"""
    m = MARK_RE.match(l)
    mark, rest = (m.group(1), l[m.end():]) if m else ("", l)
    for rx in (RED_RE, SUBALERT_RE, AIRED_RE):
        r = rx.match(rest)
        if r:
            rest = rest[r.end():]
    return (mark, rest)


def _after_mark(l):
    m = MARK_RE.match(l)
    return l[m.end():] if m else l


def is_red(l):
    """素材行是否帶重大標記（時段標記後、代碼前的 🔴）。"""
    return bool(RED_RE.match(_after_mark(l)))


def is_subalert(l):
    """素材行是否帶次級重大標記 🟡（時段標記之後、代碼之前）。"""
    return bool(SUBALERT_RE.match(_after_mark(l)))


def is_aired(l):
    """素材行是否帶已播標記 🟤（時段標記與 🔴／🟡 之後、代碼之前）。"""
    rest = _after_mark(l)
    for rx in (RED_RE, SUBALERT_RE):
        r = rx.match(rest)
        if r:
            rest = rest[r.end():]
    return bool(AIRED_RE.match(rest))


# 檔頭重大提醒行（2026-08-03 使用者訂案）：`🔴 重大：{標記}{代碼} {一句話}`
# 放在檔頭最後（圖例行之後）、最多 3 行。編輯開檔第一眼就要看到今天最該處理的素材，
# 不必自己在近百行素材裡找。stats 預設「沿用檔內既有重大行」，避免每次重算檔頭把它洗掉。
ALERT_RE = re.compile(r"^\s*🔴\s*重大：")
ALERT_MAX = 3


def header_lines(lines):
    """檔頭＝第一個 `======` 大分類之前的所有行。"""
    out = []
    for l in lines:
        if l.startswith("="):
            break
        out.append(l)
    return out


def alert_lines(lines):
    """回傳 [(行號, 原文)]，行號 1-based。"""
    return [(n, l) for n, l in enumerate(lines, 1) if ALERT_RE.match(l)]

# 側錄行（S2b）：{來源} {6碼}[ 小標]，格式與通訊社三段式完全不同——
# 通訊社的畫面/BITE/150字檢查一律不適用，需分流（2026-08-02 訂正）
# 全形括號可緊貼 TC（`CNN 160106（主播）`），不強制空白，否則整行會兩邊都漏辨識
# ⚠️ TC 兩種寫法都要認（2026-08-03 補，原本只認 6 碼是長期盲區）：
#   6 碼 `160106`／冒號 `16:01:06`／範圍 `16:53:50-16:56:38`
# ⚠️ 6 碼格式的範圍也要認（2026-08-03 深夜補，原本只有冒號範圍有 `-訖點`分支）：
#   `211313-211522` 這種已經是 6 碼的範圍，之前只吃得到起點 `211313`，
#   `-211522` 會被當成沒吃到的殘餘文字，誤判成獨立一行內容混進 normalize_side 輸出
#   （見 s2_state.py normalize_side「範圍取起點」那段，取起點的邏輯沒問題，
#   問題出在這裡的正則根本沒把整個範圍匹配進來，rest 才會多出一截）。
# 認不得會讓整段側錄在品質掃與統計裡隱形，回報的「0 命中」是假的。
_TC = r"(?:\d{6}(?:\s*[-–~]\s*\d{6})?|\d{1,2}:\d{2}:\d{2}(?:\s*[-–~]\s*\d{1,2}:\d{2}:\d{2})?)"
# 日期是 2026-08-09 加的（側錄跨夜，光看 `151542` 分不出是哪一天）。
# ⛔ **舊格式必須繼續認得**：歷史上有 141 段側錄是無日期的 `CNN 151542`，
#    認不得的話它們會在品質掃與統計裡整批隱形，而回報的「0 命中」是假的
#    ——那正是 0802 踩過的坑，不要再踩一次。所以日期段是**可有可無**。
_SIDE_DATE = r"(?:\d{2}-\d{2}\s+)?"
SIDE_RE = re.compile(rf"^(?:CNN|NHK) {_SIDE_DATE}{_TC}(?:[\s（]|$)")
# ⚠️ 側錄 SUPER 一律照搬、不檢查、不修正（2026-08-02 使用者訂正）：
# 貼進來的內容已經人工篩選校正過，agent 改 SUPER（含「角色標錯就改」與「缺 SUPER 就補」）
# 都是擅自竄改。角色誤判要修，是在上游 15-歐印萬掃帶／人工那一關做，不是這裡。
# 唯一例外：使用者當次明說「允許自行整理 SUPER」才可自行修正（見 14-S2b）。
# 原本的 SIDE_ROLE_OK／SIDE_ROLE_BAD 白黑名單已移除。

# YouTube 兩行式（4c）：第一行網址、第二行 ({來源} {形式} {MM:SS}) 摘要
YT_URL_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]{6,})")
YT_NOTE_RE = re.compile(r"^\((\S+)\s+(記者連線|SOT|主播BS)\s+(\d{1,3}:\d{2})\)\s*\S")


def read(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return f.read().splitlines()
    except OSError as e:
        print(f"ERROR: 檔案讀取失敗（{e}）。請確認路徑後重跑，不要手動掃。")
        sys.exit(2)


def material_lines(lines, with_mark=False):
    """通訊社三段式素材行（不含側錄行——側錄走 side_lines）。

    回傳的行**已剝掉隔夜標記**（▲／●／◆），下游檢查與統計都當沒標記處理；
    需要標記本身時傳 with_mark=True，回傳 (行號, 標記, 去標記後的行)。
    """
    out = []
    for n, raw in enumerate(lines, 1):
        mark, l = strip_mark(raw)
        if LINE_RE.match(l) and not SIDE_RE.match(l):
            out.append((n, mark, l) if with_mark else (n, l))
    return out


def side_lines(lines):
    """側錄 TC 行（S2b）：回傳 [(行號, 該行, 內容區塊)]。

    區塊到下列任一情形為止（2026-08-02 修）：空行／小分題分隔 `+`／
    大分類或中主題標題／下一段側錄 TC 行／通訊社素材行。
    原本只看空行，會把 `+` 後面的小分題與下一則通訊社素材整段吃進來，
    害「側錄不該用 ▎ 分段」對著別人的 ▎ 誤命中。
    """
    out = []
    for n, raw in enumerate(lines, 1):
        _, l = strip_mark(raw)
        if SIDE_RE.match(l):
            block = []
            for nxt_raw in lines[n:]:
                _, nxt = strip_mark(nxt_raw)
                s = nxt.strip()
                if not s or s == "+" or s.startswith(("【", "=")):
                    break
                if SIDE_RE.match(nxt) or LINE_RE.match(nxt):
                    break
                block.append(nxt)
            out.append((n, l, block))
    return out


def side_units(lines):
    """側錄合併後的「則數」：連續、同來源、同三層歸位的 TC 段算**一則**。

    ⚠️ **這是網頁版與 txt 檔頭共用的唯一算法**（2026-08-09 抽出）。
    原本只有網頁版的 JS 有一份；txt 檔頭要報則數時若另寫一份，兩邊遲早算出
    不同的數字——「txt 說 222 則、網頁說 292 則」那類問題就是這樣來的。
    **要改合併規則就改這裡，不要在任何一端另外寫。**
    """
    big = mid = sub = ""
    prev, units = None, 0
    for raw in lines:
        _, l = strip_mark(raw)
        s = l.strip()
        if re.match(r"^=====+.+=====+$", s):
            big, mid, sub = s.strip("="), "", ""
            prev = None
            continue
        if re.match(r"^【.+】$", s):
            mid, sub = s, ""
            prev = None
            continue
        if s == "+":
            prev = None                       # 小分題換了，下一段一定另起一則
            continue
        if SIDE_RE.match(l):
            src = s.split()[0]                # CNN／NHK
            key = (src, big, mid, sub)
            if key != prev:
                units += 1
            prev = key
            continue
        # 不是結構行、也不是側錄 TC 行，且不是通訊社素材行 → 當成小分題標題
        if s and not LINE_RE.match(l):
            # 內容行會緊跟在 TC 行後面；小分題標題出現時 prev 必為 None 或剛換過
            if prev is None:
                sub = s
    return units


def yt_blocks(lines):
    """回傳 [(網址行號, 網址, 備註行或 None)]。"""
    out = []
    for n, raw in enumerate(lines, 1):
        _, l = strip_mark(raw.strip())
        if YT_URL_RE.match(l):
            nxt = strip_mark(lines[n].strip())[1] if n < len(lines) else ""
            out.append((n, l, nxt))
    return out


def check(path):
    lines = read(path)
    hits = []

    def hit(n, reason):
        hits.append((n, reason))

    # 側錄的 TC 鍵（`CNN 08-09 190145`）也要能被檔頭重大行指到，見下方 alerts 檢查
    seen_side_codes = {re.match(CODE, l).group(0)
                       for _, l, _ in side_lines(lines) if re.match(CODE, l)}
    seen_codes = {}
    for n, l in material_lines(lines):
        codes = re.findall(CODE, l.split("▎")[0])
        for c in codes:
            seen_codes.setdefault(c, []).append(n)

        has_bite_tag = "(BITE)" in l
        has_bite_seg = "▎BITE：" in l or "▎BITE:" in l
        has_nobite = "無BITE" in l

        if has_bite_tag and has_nobite:
            hit(n, "(BITE) 與 無BITE 矛盾")
        if has_bite_seg and not has_bite_tag:
            hit(n, "有 ▎BITE： 但缺 (BITE) 第二括號")
        if has_bite_tag and not has_bite_seg:
            hit(n, "有 (BITE) 但缺 ▎BITE： 段")
        if "▎畫面：" not in l and "▎畫面:" not in l:
            hit(n, "缺 ▎畫面： 段")
        if not has_bite_seg and not has_nobite:
            hit(n, "結尾既非 無BITE 也無 BITE： 段")
        # 行尾必須是 無BITE。／BITE 引號收尾／時長 ▎M:SS，其後不得再拖其他段
        if not re.search(r"(無BITE。|」|▎\d{1,3}:\d{2})\s*$", l):
            hit(n, "行尾有多餘內容（應以 無BITE。／」／▎MM:SS 結尾）")

        m_notes = re.match(rf"^{CODE}(?:\s*/\s*{CODE})*\s+(?:\([^)]*\)\s*)+", l)
        if m_notes:
            rest = l[m_notes.end():]
            if not rest.startswith("▎"):
                hit(n, "摘要前缺 ▎ 標記（應為 (備註)[(BITE)] ▎摘要▎畫面：…）")
            else:
                summary = rest[1:].split("▎", 1)[0]
                if len(summary) > 150:
                    hit(n, f"摘要超過150字硬上限（現{len(summary)}字，WRAP等長文不例外，需分句或移入畫面段）")

        m = re.match(rf"^{CODE}(?:\s*/\s*{CODE})*\s+\(([^)]*)\)", l)
        first_note = m.group(1) if m else ""
        if re.search(r"(?<![A-Za-z])BITE(?![A-Za-z])", first_note):
            hit(n, "第一備註寫了 BITE")
        if re.search(r"(?<![A-Za-z])(FILE|File)(?![A-Za-z])", first_note) or "檔案" in first_note:
            hit(n, "備註用 FILE/檔案（應為 資料畫面）")
        parens = re.findall(r"\(([^)]*)\)", l.split("▎")[0])
        if len(parens) >= 2 and parens[1].strip() != "BITE":
            hit(n, f"第二括號不是 (BITE)：({parens[1]})")
        if "GMT" in l:
            hit(n, "素材行出現 GMT")
        for bad in ("（列表摘要）", "（詳情頁待補）", "（急用請開Shotlist）",
                    "（script待補）", "（完整script待補）", "（early", "（待完整稿）"):
            if bad in l:
                hit(n, f"操作/狀態備註寫進素材行：{bad}")
        # 操作備註通式（半形或全形括號皆抓）：列表級／未開詳情／待補／待確認…
        m_op = re.search(r"[（(][^）)]*(列表級|未開詳情|列表摘要|詳情頁待補|待補|待確認|待人工|TODO)[^（(]*?[）)]", l)
        if m_op:
            hit(n, f"操作備註寫進素材行：{m_op.group(0)}（給 agent 看的註記不進成品）")
        if re.search(r"▎BITE[：:]\s*「", l):
            hit(n, "▎BITE：無講者（引號前必須有講者）")
        wrap_note = "整理包" in first_note
        if re.search(r"(?<![A-Za-z])WRAP(?![A-Za-z])", l) and not wrap_note:
            hit(n, "出現 WRAP 但備註未標 整理包")

    for c, ns in seen_codes.items():
        if len(ns) > 1:
            hit(ns[-1], f"重複代碼 {c}（另見行 {ns[:-1]}）")

    # 檔頭重大提醒行：代碼必須在正文找得到，且只能待在檔頭
    head_n = len(header_lines(lines))
    alerts = alert_lines(lines)
    if len(alerts) > ALERT_MAX:
        hit(alerts[ALERT_MAX][0],
            f"重大提醒行 {len(alerts)} 行超過上限 {ALERT_MAX} 行"
            f"（全都重大＝都不重大，只留當班最該先處理的）")
    for n, l in alerts:
        if n > head_n:
            hit(n, "重大提醒行不在檔頭（應放在檔頭最後、圖例行之後，不可落在大分類區塊裡）")
        codes = re.findall(CODE, l)
        if not codes:
            hit(n, "重大提醒行未寫素材代碼（格式：`🔴 重大：{標記}{代碼} {一句話}`）")
        for c in codes:
            # ⚠️ 檔頭重大**也可以指向側錄**（2026-08-09 實錯）：側錄不算「素材行」，
            #    只查 seen_codes 會把 `CNN 08-09 190145` 這種誤報成「正文找不到」。
            #    側錄照樣可能是今天最重大的一則（那次是自由女神像外船難 2 死）。
            if c not in seen_codes and c not in seen_side_codes:
                hit(n, f"重大提醒行的代碼 {c} 在正文找不到對應素材行或側錄段（漏寫或已被刪）")

    # 檔頭 🔴 → 正文 🔴 單向檢查（2026-08-03 訂案）：檔頭點名的，正文那行必須也標 🔴，
    # 否則編輯得自己在近百則裡找。
    # ⚠️ **反向不檢查**（2026-08-03 使用者訂正）：素材行的 🔴 **標過就永久保留**，
    # 檔頭的重大提醒行則每輪汰換——所以「正文有 🔴、檔頭沒有」是輪替後的正常狀態，
    # 不是錯。曾短暫把它當錯誤命中，那會逼 agent 去刪掉不該刪的 🔴。
    alert_codes = {c for _, l in alerts for c in re.findall(CODE, l)}
    red_body = {}
    for n, raw in enumerate(lines, 1):
        _, l = strip_mark(raw)
        if LINE_RE.match(l) and not SIDE_RE.match(l) and is_red(raw):
            # 只取行首的代碼（LINE_RE 已保證在行首，含 A/B 並列）。
            # ⚠️ 不可對整個備註段 findall——備註文字順帶提到的其他代碼
            # （如「另有前版AP4676258」）會被誤認成「該則有標 🔴」，
            # 讓檔頭點名它時誤判已標（0803 工作 agent 實抓）。
            m = re.match(rf"{CODE}(?:\s*/\s*{CODE})*", l)
            for c in re.findall(CODE, m.group(0) if m else ""):
                red_body.setdefault(c, n)
    for c in alert_codes:
        if c in seen_codes and c not in red_body:
            hit(seen_codes[c][0],
                f"檔頭標了 🔴 重大：{c}，但正文該行沒有 🔴（應寫成「{{時段標記}} 🔴 {c} …」）")

    # 隔夜標記（▲／■／◆，舊檔的 ● 亦同）：只要用了就必須在檔頭寫圖例，否則編輯看不懂
    used_marks = {m for _, m, _ in material_lines(lines, with_mark=True) if m}
    if used_marks:
        # 檔頭＝第一個 ====== 大分類之前；不能用「前 N 行」，素材行本身帶標記會假通過
        head = "\n".join(header_lines(lines))
        for mk in sorted(used_marks):
            if mk not in head:
                hit(1, f"素材行用了隔夜標記「{mk}」但檔頭沒有對照圖例"
                       f"（應有 `標記：▲=23:00–07:00 新增　■=07:00–09:00 新增　◆=09:00–14:00 新增`）")

    # YouTube 兩行式（4c）
    seen_urls = {}
    for n, url, note in yt_blocks(lines):
        vid = YT_URL_RE.match(url).group(1)  # 以 video ID 去重（watch?v= 與 youtu.be 視為同一支）
        seen_urls.setdefault(vid, []).append(n)
        if not note:
            hit(n, "YouTube 網址下方缺備註行 ({來源} {形式} {MM:SS}) ＋摘要")
            continue
        m = YT_NOTE_RE.match(note)
        if not m:
            if YT_URL_RE.match(note):
                hit(n, "YouTube 網址下方直接接另一個網址（缺備註行）")
            else:
                hit(n + 1, "YouTube 備註行格式錯（應為 ({來源} {形式} {MM:SS}) ＋200字摘要，形式限 記者連線／SOT／主播BS）")
            continue
        summary = note[m.end(3) + 1:].strip()
        if len(summary) < 60:
            hit(n + 1, f"YouTube 摘要過短（{len(summary)}字，應約200字）")
        if "▎" in note:
            hit(n + 1, "YouTube 兩行式不應使用 ▎畫面／BITE 分段（那是通訊社單行式）")
        if re.search(r"[（(](?:約?\s*\d+\s*字(?:摘要)?|AI摘要|摘要待補|待補摘要)[）)]", note):
            hit(n + 1, "YouTube 摘要出現佔位／字數字樣（如（200字摘要）），應直接寫內容")
    for v, ns in seen_urls.items():
        if len(ns) > 1:
            hit(ns[-1], f"重複 YouTube 影片 {v}（另見行 {ns[:-1]}）")

    # 側錄行（S2b 兩行式）：TC行＝{來源} {TC}[ （SUPER）]，下一行起為內容
    # TC 三種寫法（6碼／冒號／範圍）都要認，見 _TC
    seen_side = {}
    for n, l, block in side_lines(lines):
        # 日期段可有可無——沒吃進來的話 `CNN 08-09 151439` 匹配失敗、直接崩
        src, dt, tc = re.match(rf"^(CNN|NHK) (?:(\d{{2}}-\d{{2}}) )?({_TC})", l).groups()
        seen_side.setdefault(" ".join(x for x in (src, dt or "", tc) if x), []).append(n)
        if "▎" in l or any("▎" in b for b in block):
            hit(n, "側錄段落不該用 ▎ 分段（那是通訊社三段式，側錄走 TC＋SUPER行/內容行）")
        if not block:
            hit(n, "側錄 TC 行下方沒有內容（第二行起應為逐字內容）")
        # ⚠️ SUPER 內容不檢查：角色是否「合法」、有沒有 SUPER，一律不命中。
        # 這兩條檢查以前會逼 agent 改角色／無中生有補一個講者，已於 2026-08-02 移除。
        # 舊三行式殘留：第二行整行只有講者標示、沒有內容（純格式歸位，不涉改字）
        if block and re.fullmatch(r"(?:CNN|NHK)(?:主播|記者|受訪者|專家)[^\s]*(?:\s+\S+)?", block[0].strip()):
            hit(n + 1, "疑似舊三行式殘留（講者獨占一行）——SUPER 應移到 TC 同一行、寫成全形括號")
    for k, ns in seen_side.items():
        if len(ns) > 1:
            hit(ns[-1], f"重複側錄段落 {k}（另見行 {ns[:-1]}）")

    hits.sort()
    if not hits:
        print("OK 品質掃 0 命中")
    else:
        print(f"HIT {len(hits)} 項，逐項回站核對後修正：")
        for n, r in hits:
            print(f"  行{n}: {r}")


def header_from_lines(lines, window="", date="", mmdd="", alerts=()):
    """由正文行算出檔頭各行，回傳 list[str]（不印）。

    ⚠️ 這是檔頭生成的**唯一**實作：`stats`（讀 txt）與 `s2_render.render`（讀狀態檔
    渲染出的正文）都走這裡，避免兩套邏輯分叉。`alerts` 由呼叫端決定來源——
    stats 從舊 txt 檔頭沿用、render 從狀態檔 `_top.alerts` 取（見 13b §2）。
    """
    counts = {"AP": 0, "RT": 0, "NS": 0, "其他": 0}
    for _, l in material_lines(lines):
        first = re.match(CODE, l).group(0)
        if first.startswith(("AP", "APcctv")):
            counts["AP"] += 1
        elif first.startswith("RT"):
            counts["RT"] += 1
        elif re.match(r"[A-Z]{2,6}-\d", first):   # 前綴不是固定兩碼，見 CODE 的說明
            counts["NS"] += 1
        else:
            counts["其他"] += 1
    counts["其他"] += len(yt_blocks(lines))   # YouTube 兩行式（4c）歸「其他」
    # ⚠️ 側錄段落（S2b／CNN‧NHK）一律不計入檔頭則數（2026-08-02 使用者訂正）：
    # 側錄一段連線常被切成十幾個 TC，計進去會把「收錄外電共X則」灌爆、失去掃視價值。
    # 檔頭統計的是「通訊社素材則數」，側錄是另一條料源，完全不納入。
    total = sum(counts.values())
    out = []
    # 檔頭三行（2026-08-02 使用者定案）：標題／時間窗（含時數）／則數統計
    if not date and mmdd:
        date = f"{datetime.now().year}-{mmdd[:2]}-{mmdd[2:]}"
    if mmdd:
        out.append(f"{mmdd} 晚班交接")
    if window:
        # 起訖可帶日期（跨夜續掃：`2026-08-02 14:00 - 2026-08-03 09:00`），
        # 所以只拿全形連接號或「空白-空白」當分隔，不能直接 split("-")（日期裡也有）
        halves = re.split(r"\s*–\s*|\s+-\s+", window.strip())
        times = [re.search(r"(\d{1,2}):(\d{2})", h) for h in halves]
        if len(halves) == 2 and all(times):
            s, e = [h.strip() for h in halves]
            # 🎯 兩邊都帶完整日期時，**直接用日期算**（2026-08-09 實錯修正）。
            # 底下那個「span < 0 就 +24h」只是單日資訊下的猜測，**只有在「終點時刻
            # 比起點早」時才剛好對**。0809-0900 實錯：窗是 `08-08 08:00 → 08-09 09:00`，
            # 實際 25 小時，但 09:00 > 08:00 → 不補 24 小時 → 印成「約1hrs」。
            # 更早那版 `08:00→07:00` 印出正確的 23hrs，純粹是因為它算出負數、誤打誤撞。
            ds = re.findall(r"(\d{4})-(\d{2})-(\d{2})[ T]+(\d{1,2}):(\d{2})", window)
            span = None
            if len(ds) == 2:
                try:
                    a, b = [datetime(int(y), int(mo), int(d), int(hh), int(mi))
                            for (y, mo, d, hh, mi) in ds]
                    span = (b - a).total_seconds() / 60
                except ValueError:
                    span = None      # 日期本身不合法（手改壞了）就退回舊算法
            if span is None:
                mins = [int(t.group(1)) * 60 + int(t.group(2)) for t in times]
                span = mins[1] - mins[0]
                if span < 0:          # 跨午夜（23:00→09:00）
                    span += 24 * 60
            # 起訖任一邊自帶日期時，就不再補檔名推得的日期，避免 `2026-08-02 2026-08-02 14:00`
            pre = "" if re.search(r"\d{4}-\d{2}-\d{2}", window) else (date + " " if date else "")
            # 「時數取整數小時」（`13`「晚班交接檔頭」第 2 行）——起訖不是整點時
            # `:g` 會印出 `約12.6667hrs`（0808-manual-test 實例，該輪 checkpoint 無
            # HHMM、終點用 20:40 特例覆寫）。四捨五入到整數小時才合規。
            out.append(f"時間窗：{pre}{s}–{e}（約{int(round(span / 60))}hrs）")
        else:
            out.append(f"時間窗：{date + ' ' if date else ''}{window}")
    parts = [f"AP {counts['AP']}則", f"RT {counts['RT']}則", f"NS {counts['NS']}則"]
    if counts["其他"]:
        parts.append(f"其他 {counts['其他']}則")
    marked = {m: 0 for m in MARKS}
    for _, m, _ in material_lines(lines, with_mark=True):
        if m:
            marked[m] += 1
    tail = ""
    if any(marked[m] for m in OVERNIGHT_MARKS):
        tail = "；隔夜續掃 " + "／".join(
            f"{m} {marked[m]}則" for m in OVERNIGHT_MARKS if marked[m])
    # 側錄則數**分開報、不併進總數**（2026-08-09 使用者選 A）：「共X則」是三站
    # 清單對帳的依據，側錄沒有清單可對，併進去那個數字就不能拿來對帳了。
    su = side_units(lines)
    side_txt = f"　側錄 {su}則" if su else ""
    out.append(f"收錄外電共{total}則（{'／'.join(parts)}）{side_txt}{tail}")
    # 第 4 行圖例：只要當份有用到任一時段標記就印（含 △），沒用到就不印
    legend = [f"{m}={MARKS[m]}" for m in MARKS if marked[m]]
    # 🟤 已播（2026-08-04）：同樣「有用到才印」——沒標到的日子不要多一段沒用的圖例。
    # 🔴 不進圖例：它已經有檔頭「🔴 重大：」那幾行自我說明，再列一次是贅字。
    # 🟡 有用到才印圖例——它沒有檔頭那幾行可以自我說明，編輯不看圖例會不懂
    if any(is_subalert(raw) for raw in lines):
        # 用字與網頁版篩選 chip 一致（2026-08-09 使用者要求）——同一件事兩種說法，
        # 編輯在 txt 與網頁之間切換時會以為是兩種標記。
        legend.append("🔴=重大　🟡=次重大")
    if any(is_aired(raw) for raw in lines):
        legend.append("🟤=已做過")
    if legend:
        out.append("標記：" + "　".join(legend))
    # 最後才是重大提醒行（來源由呼叫端決定，見 docstring）
    al = [a if ALERT_RE.match(a) else f"🔴 重大：{a}" for a in (alerts or [])]
    if len(al) > ALERT_MAX:
        print(f"(略過 {len(al) - ALERT_MAX} 行：重大提醒上限 {ALERT_MAX} 行)",
              file=sys.stderr)
    return out + al[:ALERT_MAX]


def stats(path, window, date="", alerts=None, clear_alerts=False):
    lines = read(path)
    mmdd = re.search(r"(\d{4})晚班交接", os.path.basename(path))
    mmdd = mmdd.group(1) if mmdd else ""
    # ⚠️ 重大提醒行預設沿用檔內既有的，不是每次重生——檔頭每輪整併都要重算覆寫，
    # 若不沿用，一次例行 stats 就會把上一輪標的重大洗掉。
    # 要改內容才傳 --alert（可重複，會整組取代）；要撤掉傳 --clear-alerts。
    # （render 路徑不走這裡：它從狀態檔 `_top.alerts` 取，見 WP1 前提四。）
    if clear_alerts:
        al = []
    elif alerts:
        al = alerts
    else:
        al = [l for l in header_lines(lines) if ALERT_RE.match(l)]
    for l in header_from_lines(lines, window, date, mmdd, al):
        print(l)


def resolve_path(args):
    """`path` 位置參數與 `--file` 旗標擇一，兩者都給以 `--file` 優先。

    2026-08-04 補：s2_state.py／s2_render.py 都用 `--file`，只有這支腳本原本是
    純位置參數，三支姊妹腳本介面不一致，agent 常照另外兩支的慣例猜錯（實錯回報）。
    這裡兩種都收，不用逼 agent 記住哪支是例外。
    """
    p = args.file or args.path
    if not p:
        print("ERROR: 需要指定路徑（位置參數或 --file 都可以）")
        sys.exit(2)
    return p


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("path", nargs="?")
    c.add_argument("--file", help="與 path 位置參數擇一，同時給以 --file 優先")
    s = sub.add_parser("stats")
    s.add_argument("path", nargs="?")
    s.add_argument("--file", help="與 path 位置參數擇一，同時給以 --file 優先")
    s.add_argument("--window", default="")
    s.add_argument("--date", default="", help="YYYY-MM-DD；預設由檔名 MMDD 推得")
    s.add_argument("--alert", action="append", default=[],
                   help="重大提醒行內容（可重複，最多3則；會整組取代舊的）。"
                        "省略＝沿用檔內既有重大行")
    s.add_argument("--clear-alerts", action="store_true",
                   help="撤掉全部重大提醒行（事件退燒／隔日換檔時用）")
    args = p.parse_args()
    if args.cmd == "check":
        check(resolve_path(args))
    else:
        stats(resolve_path(args), args.window, args.date, args.alert, args.clear_alerts)


if __name__ == "__main__":
    main()
