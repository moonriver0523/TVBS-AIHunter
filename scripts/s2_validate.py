# -*- coding: utf-8 -*-
"""S2 晚班交接品質掃／檔頭統計／三方比對腳本（V2）。

用法：
  python s2_validate.py check <晚班交接.txt>       格式異常掃描
  python s2_validate.py stats <晚班交接.txt> [--window "16:00 - 23:00"]
                                                   輸出檔頭兩行
  python s2_validate.py diff3 <現行.txt> <機器版快照.txt>
                                                   列出人工編輯過的行

規則依據 common/13-S2-定時掃帶.md「最終整併：稿未到清查＋品質掃」。
"""
import argparse
import difflib
import io
import os
import re
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 素材代碼（行首）：RT#### / AP####### / APcctv###### / CNN Newsource XX-##XX / 側錄 CNN|NHK ######
CODE = r"(?:RT\d{4}|APcctv\d{6}|AP\d{7}|[A-Z]{2}-\d{1,3}[A-Z]{2}|(?:CNN|NHK) \d{6})"
LINE_RE = re.compile(rf"^{CODE}(?:\s*/\s*{CODE})*\s")

# 隔夜續掃標記（2026-08-02 使用者訂案）：素材代碼前可帶一個時段符號，
# ▲＝23:00–07:00 新增、●＝07:00–09:00 新增，無標記＝23:00 前晚班既有。
# 一律先剝掉再做其餘比對，否則整行會兩邊都漏辨識（同 SIDE_RE 踩過的坑）。
MARKS = {"▲": "23:00–07:00", "●": "07:00–09:00"}
MARK_RE = re.compile(r"^([▲●])\s*")


def strip_mark(l):
    """回傳 (標記或空字串, 去掉標記後的行)。"""
    m = MARK_RE.match(l)
    return (m.group(1), l[m.end():]) if m else ("", l)

# 側錄行（S2b）：{來源} {6碼}[ 小標]，格式與通訊社三段式完全不同——
# 通訊社的畫面/BITE/150字檢查一律不適用，需分流（2026-08-02 訂正）
# 全形括號可緊貼 TC（`CNN 160106（主播）`），不強制空白，否則整行會兩邊都漏辨識
SIDE_RE = re.compile(r"^(?:CNN|NHK) \d{6}(?:[\s（]|$)")
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

    回傳的行**已剝掉隔夜標記**（▲／●），下游檢查與統計都當沒標記處理；
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

    # 隔夜標記（▲／●）：只要用了就必須在檔頭寫圖例，否則編輯看不懂那些符號
    used_marks = {m for _, m, _ in material_lines(lines, with_mark=True) if m}
    if used_marks:
        # 檔頭＝第一個 ====== 大分類之前；不能用「前 N 行」，素材行本身帶標記會假通過
        head = []
        for l in lines:
            if l.startswith("="):
                break
            head.append(l)
        head = "\n".join(head)
        for mk in sorted(used_marks):
            if mk not in head:
                hit(1, f"素材行用了隔夜標記「{mk}」但檔頭沒有對照圖例"
                       f"（應有 `標記：▲=23:00–07:00 新增　●=07:00–09:00 新增`）")

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

    # 側錄行（S2b 兩行式）：TC行＝{來源} {6碼}[ （SUPER）]，下一行起為內容
    seen_side = {}
    for n, l, block in side_lines(lines):
        src, tc = re.match(r"^(CNN|NHK) (\d{6})", l).groups()
        seen_side.setdefault(f"{src} {tc}", []).append(n)
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


def stats(path, window, date=""):
    lines = read(path)
    counts = {"AP": 0, "RT": 0, "NS": 0, "其他": 0}
    for _, l in material_lines(lines):
        first = re.match(CODE, l).group(0)
        if first.startswith(("AP", "APcctv")):
            counts["AP"] += 1
        elif first.startswith("RT"):
            counts["RT"] += 1
        elif re.match(r"[A-Z]{2}-\d", first):
            counts["NS"] += 1
        else:
            counts["其他"] += 1
    counts["其他"] += len(yt_blocks(lines))   # YouTube 兩行式（4c）歸「其他」
    # ⚠️ 側錄段落（S2b／CNN‧NHK）一律不計入檔頭則數（2026-08-02 使用者訂正）：
    # 側錄一段連線常被切成十幾個 TC，計進去會把「收錄外電共X則」灌爆、失去掃視價值。
    # 檔頭統計的是「通訊社素材則數」，側錄是另一條料源，完全不納入。
    total = sum(counts.values())
    # 檔頭三行（2026-08-02 使用者定案）：標題／時間窗（含時數）／則數統計
    mmdd = re.search(r"(\d{4})晚班交接", os.path.basename(path))
    mmdd = mmdd.group(1) if mmdd else ""
    if not date and mmdd:
        date = f"{datetime.now().year}-{mmdd[:2]}-{mmdd[2:]}"
    if mmdd:
        print(f"{mmdd} 晚班交接")
    if window:
        # 起訖可帶日期（跨夜續掃：`2026-08-02 14:00 - 2026-08-03 09:00`），
        # 所以只拿全形連接號或「空白-空白」當分隔，不能直接 split("-")（日期裡也有）
        halves = re.split(r"\s*–\s*|\s+-\s+", window.strip())
        times = [re.search(r"(\d{1,2}):(\d{2})", h) for h in halves]
        if len(halves) == 2 and all(times):
            s, e = [h.strip() for h in halves]
            mins = [int(t.group(1)) * 60 + int(t.group(2)) for t in times]
            span = mins[1] - mins[0]
            if span < 0:          # 跨午夜（23:00→09:00）
                span += 24 * 60
            # 起訖任一邊自帶日期時，就不再補檔名推得的日期，避免 `2026-08-02 2026-08-02 14:00`
            pre = "" if re.search(r"\d{4}-\d{2}-\d{2}", window) else (date + " " if date else "")
            print(f"時間窗：{pre}{s}–{e}（約{span / 60:g}hrs）")
        else:
            print(f"時間窗：{date + ' ' if date else ''}{window}")
    parts = [f"AP {counts['AP']}則", f"RT {counts['RT']}則", f"NS {counts['NS']}則"]
    if counts["其他"]:
        parts.append(f"其他 {counts['其他']}則")
    marked = {m: 0 for m in MARKS}
    for _, m, _ in material_lines(lines, with_mark=True):
        if m:
            marked[m] += 1
    tail = ""
    if any(marked.values()):
        tail = "；隔夜續掃 " + "／".join(
            f"{m} {marked[m]}則" for m in MARKS if marked[m])
    print(f"收錄外電共{total}則（{'／'.join(parts)}）{tail}")
    # 第 4 行圖例：只要當份有用到隔夜標記就印，沒用到就不印（純晚班檔維持三行）
    if any(marked.values()):
        print("標記：" + "　".join(f"{m}={MARKS[m]} 新增" for m in MARKS
                                   if marked[m]) + "（無標記＝23:00 前晚班既有）")


def diff3(cur_path, snap_path):
    cur, snap = read(cur_path), read(snap_path)
    edited = [l for l in difflib.unified_diff(snap, cur, lineterm="", n=0)
              if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
    if not edited:
        print("OK 無人工編輯，整併可直接以機器版為底")
    else:
        print(f"人工編輯 {len(edited)} 行（-為快照原文、+為現行；整併時保留人工版）：")
        for l in edited:
            print("  " + l)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("path")
    s = sub.add_parser("stats")
    s.add_argument("path")
    s.add_argument("--window", default="")
    s.add_argument("--date", default="", help="YYYY-MM-DD；預設由檔名 MMDD 推得")
    d = sub.add_parser("diff3")
    d.add_argument("current")
    d.add_argument("snapshot")
    args = p.parse_args()
    if args.cmd == "check":
        check(args.path)
    elif args.cmd == "stats":
        stats(args.path, args.window, args.date)
    else:
        diff3(args.current, args.snapshot)


if __name__ == "__main__":
    main()
