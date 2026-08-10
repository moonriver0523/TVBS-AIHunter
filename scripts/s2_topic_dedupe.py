# -*- coding: utf-8 -*-
"""S2 同名小分題跨大分類重複偵測（render 前置檢查，2026-08-03 上線）。

只做「分級 A」——同一個小分題名稱同時出現在不同大分類底下，這是
「同一事件被拆到兩處」的高信度訊號（0803 回溯驗證：對含真實錯誤的樣本
精準命中、零誤報；曾試過的「不同名稱但內文模糊比對」雜訊過高，已放棄，
不要重新加回來）。純讀取＋比對，不寫 state、不動 render 產出。

種子來源：
  1. 今天狀態檔（`{MMDD}-s2-state.json`）自己的小分題
  2. 前一天狀態檔的小分題（找不到 json 才退回解析前一天的晚班交接 txt）
  只回看「前一天」這一份，不做多天累積，避免關鍵字池無限膨脹
  （common/13b「S2 提速計劃」的省 token 精神——這支也要遵守）。

用法：
  python s2_topic_dedupe.py --file "…/0803-s2-state.json"
  （省略 --yesterday-file 時自動用 MMDD-1 天推算同目錄檔名，找不到就跳過跨日檢查）
"""
import argparse
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # py<3.7
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2_validate as sv  # noqa: E402  共用行辨識 regex


def mmdd_shift(mmdd, days):
    d = datetime(datetime.now().year, int(mmdd[:2]), int(mmdd[2:])) + timedelta(days=days)
    return d.strftime("%m%d")


def cat_of(it):
    """與 s2_render.cat_of 同邏輯（故意不 import s2_render，避免互相耦合狀態檔路徑）。"""
    c = it.get("category")
    if isinstance(c, dict):
        return (c.get("大分類") or "", c.get("中主題") or "", c.get("小分題") or "")
    if isinstance(c, str) and "/" in c:
        p = [x.strip() for x in c.split("/", 2)] + ["", ""]
        return p[0], p[1], p[2]
    return "", "", ""


def sub_locs_from_state(path):
    """回傳 {小分題: [(大分類, 中主題, id), ...]}。找不到檔案回傳 None（給呼叫端判斷要不要跳過）。"""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8-sig") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    out = {}
    for it in raw.get("items", []):
        big, mid, sub = cat_of(it)
        if not sub:
            continue
        out.setdefault(sub, [])
        loc = (big, mid, it.get("id", "?"))
        if (big, mid) not in {(b, m) for b, m, _ in out[sub]}:
            out[sub].append(loc)
    return out


def sub_locs_from_txt(path):
    """退路：state.json 不存在時，解析前一天渲染出的 txt 結構取小分題位置。"""
    if not os.path.exists(path):
        return None
    lines = io.open(path, encoding="utf-8-sig").read().splitlines()
    out = {}
    big = mid = sub = ""
    seen_material_since_sub = False
    for raw in lines:
        l = sv.strip_mark(raw)[1]
        s = l.strip()
        if l.startswith("======") and l.endswith("======"):
            big, mid, sub = l.strip("=").strip(), "", ""
            continue
        if l.startswith("【") and l.endswith("】"):
            mid, sub = l.strip("【】").strip(), ""
            continue
        if not s:
            continue
        if s == "+":
            sub = ""
            continue
        if sv.LINE_RE.match(l) and not sv.SIDE_RE.match(l):
            if sub:
                out.setdefault(sub, [])
                if (big, mid) not in {(b, m) for b, m, _ in out[sub]}:
                    ids = re.findall(sv.CODE, l)
                    out[sub].append((big, mid, ids[0] if ids else "?"))
            continue
        if not sub:  # 非代碼、非空、非 + ：小分題標題
            sub = s
    return out


# 14-S2b 的形式標記全集。小分題**整個等於**其中一個＝只寫形式、沒有主題內容。
# ⚠️ 2026-08-10 補：規則（14-S2b「🔴 小分題不准只寫形式」）從 08-09 就寫死了，
#    但**沒有任何機械檢查**——0810 那批側錄 37 段全寫成 `主播BS`／`專家分析`
#    這種純形式，品質掃照樣回報 0 命中，是使用者肉眼看出來的。
#    這裡是那條規則的執法點：只比對「完全相等」，不做模糊比對，零誤報。
FORM_ONLY = {
    "主播BS", "主播開場BS", "主播BS+BITE", "主播BS+現場音", "主播訪談",
    "記者包裝SOT", "記者報導+BITE", "記者連線", "記者解說",
    "氣象主播分析", "專家分析", "主播開場BS+記者解說",
}


def form_only_hits(state_path):
    """小分題只寫形式（沒有主題內容）→ [(小分題, [(大分類,中主題,id), ...])]。"""
    locs = sub_locs_from_state(state_path)
    if not locs:
        return []
    return [(name, ls) for name, ls in locs.items() if name.strip() in FORM_ONLY]


# 操作備註／向使用者提問，被寫進**分類名稱**的痕跡（2026-08-10 補）。
# ⚠️ 0810 實例：側錄 agent 不確定新主題該不該併，就把問題寫進中主題名稱——
#   `美籍退伍軍人吉爾曼遭俄羈押安危】（新題，不確定是否已有既有子題可併，請裁定）`
#   三個中主題中招、共 20 段素材，render 照樣把整串印進交接單當標題。
#   `13` 早就禁止「操作備註寫進素材行」且 `s2_validate` 有查，但**分類名稱是另一條路徑**，
#   完全沒人看——不確定就寫 `needs-review`，不要寫進成品欄位。
NOTE_IN_NAME = re.compile(r"(請裁定|待裁定|待確認|待人工|待補|不確定|新題|暫定|TODO|待議|請確認)"
                          r"|[】\]]\s*[（(]|^[^【]*】")


def note_in_name_hits(state_path):
    """分類名稱裡混進操作備註／提問 → [(層級, 名稱, [id, ...])]。"""
    if not os.path.exists(state_path):
        return []
    try:
        with open(state_path, encoding="utf-8-sig") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    bad = {}
    for it in raw.get("items", []):
        big, mid, sub = cat_of(it)
        for lvl, name in (("大分類", big), ("中主題", mid), ("小分題", sub)):
            if name and NOTE_IN_NAME.search(name):
                bad.setdefault((lvl, name), []).append(it.get("id", "?"))
    return [(lvl, name, ids) for (lvl, name), ids in bad.items()]


def missing_sub_hits(state_path):
    """完全沒開小分題的素材 → [(大分類, 中主題, [id, ...])]。

    ⚠️ 2026-08-10 補。`sub_locs_from_state()` 對沒有小分題的項目是 `continue` 跳過，
    於是「整天沒人開小分題」這種**最嚴重**的情況反而完全偵測不到——0810 當天 97 則
    全裸，品質掃與本支都回報 0 命中，是使用者自己看出來的（根因是 13b 曾把小分題
    寫成「選填」）。三層骨架見 13「素材行掛在小分題底下」。
    """
    if not os.path.exists(state_path):
        return []
    try:
        with open(state_path, encoding="utf-8-sig") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    grouped = {}
    for it in raw.get("items", []):
        if it.get("script_status") == "note":
            continue            # needs-review 備註殼，本來就沒有內容要分類
        if not (it.get("raw_entry") or "").strip():
            continue            # 沒有內容的殼同理
        big, mid, sub = cat_of(it)
        # 🔴 **完全沒分類的要單獨大聲報**（2026-08-10 補）。
        #    舊版寫 `if not big: continue`——沒有大分類的直接跳過，於是
        #    「整輪忘了呼叫 set-category」這種**最嚴重**的情況反而完全偵測不到。
        #    0810-2200 實錯：那輪 `add-batch` 三次、`set-category` **0 次**，
        #    46 則素材連大分類都沒有；render 把它們默默丟進「話題／未分類」，
        #    品質掃、本支、`s2_topic_review` 全數 0 命中，是使用者自己發現的。
        if not big:
            grouped.setdefault(("（完全沒分類）", "⚠️ 這輪可能漏跑 set-category"), []) \
                   .append(it.get("id", "?"))
            continue
        if sub:
            continue
        grouped.setdefault((big, mid), []).append(it.get("id", "?"))
    return [(b, m, ids) for (b, m), ids in grouped.items()]


def check(state_path, yesterday_path=""):
    """回傳 (today_hits, cross_day_hits)，兩者都是 [(小分題, [(大分類,中主題,id), ...])]。"""
    today = sub_locs_from_state(state_path)
    if today is None:
        print(f"ERROR: 讀不到今天狀態檔 {state_path}", file=sys.stderr)
        return [], []

    # ⚠️ 只比對「大分類」，不比中主題——中主題名稱本來就允許每天微調措辭
    # （0803 實測：「歐洲野火」→「希臘野火」這種改名會被誤判成跨天拆散，
    # 真正嚴重的是整個大分類跑掉，像「烏俄」被拆成「話題」那種）。
    today_hits = [(name, locs) for name, locs in today.items()
                  if len({b for b, _m, _i in locs}) > 1]

    if not yesterday_path:
        m = re.search(r"(\d{4})-s2-state", os.path.basename(state_path))
        if m:
            prev = mmdd_shift(m.group(1), -1)
            d = os.path.dirname(state_path)
            cand_json = os.path.join(d, f"{prev}-s2-state.json")
            cand_txt = os.path.join(d, f"{prev}晚班交接.txt")
            yesterday_path = cand_json if os.path.exists(cand_json) else cand_txt

    cross_hits = []
    if yesterday_path and os.path.exists(yesterday_path):
        yesterday = (sub_locs_from_state(yesterday_path)
                     if yesterday_path.endswith(".json")
                     else sub_locs_from_txt(yesterday_path))
        if yesterday:
            for name, locs in today.items():
                if name not in yesterday:
                    continue
                today_big = {b for b, _m, _i in locs}
                yday_big = {b for b, _m, _i in yesterday[name]}
                if not (today_big & yday_big):  # 大分類完全不重疊才算跨天被拆
                    cross_hits.append((name, locs, yesterday[name]))
    else:
        print(f"(跳過跨日檢查：找不到前一天檔案 {yesterday_path or '（無法推算）'})", file=sys.stderr)

    return today_hits, cross_hits


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True, help="今天的狀態檔路徑")
    p.add_argument("--yesterday-file", default="",
                   help="前一天狀態檔或 txt 路徑；省略＝自動用 MMDD-1 天推算同目錄檔名")
    args = p.parse_args()

    today_hits, cross_hits = check(args.file, args.yesterday_file)

    print("【今天內部】同一小分題出現在不同大分類")
    if not today_hits:
        print("0 命中")
    for name, locs in today_hits:
        loc_str = "／".join(f"{b}／{m}（如 {i}）" for b, m, i in locs)
        print(f"⚠️ 「{name}」同時出現在：{loc_str}，請覆核是否應合併")

    print("-" * 60)
    print("【跨天】前一天有的小分題，今天換了大分類位置")
    if not cross_hits:
        print("0 命中")
    for name, locs, yloc in cross_hits:
        today_str = "／".join(f"{b}／{m}（如 {i}）" for b, m, i in locs)
        yday_str = "／".join(f"{b}／{m}" for b, m, _ in yloc)
        print(f"⚠️ 「{name}」昨天在 {yday_str}，今天卻在 {today_str}，請覆核是否為延續故事被拆開")

    note_hits = note_in_name_hits(args.file)
    print("-" * 60)
    print("【備註寫進分類名稱】不確定要寫 needs-review，不要寫進成品欄位")
    if not note_hits:
        print("0 命中")
    for lvl, name, ids in note_hits:
        shown = "、".join(ids[:4]) + ("…" if len(ids) > 4 else "")
        print(f"⚠️ {lvl}「{name}」共 {len(ids)} 則（{shown}）")

    miss_hits = missing_sub_hits(args.file)
    print("-" * 60)
    print("【沒開小分題】素材直接掛在中主題底下（13 三層骨架要求）")
    if not miss_hits:
        print("0 命中")
    for b, m, ids in miss_hits:
        shown = "、".join(ids[:6]) + ("…" if len(ids) > 6 else "")
        print(f"⚠️ {b}／{m}：{len(ids)} 則沒有小分題（{shown}）")

    form_hits = form_only_hits(args.file)
    print("-" * 60)
    print("【只寫形式】小分題沒有主題內容（14-S2b 明文禁止）")
    if not form_hits:
        print("0 命中")
    for name, locs in form_hits:
        loc_str = "／".join(f"{b}／{m}（如 {i}）" for b, m, i in locs)
        print(f"⚠️ 「{name}」只有形式標記沒有主題內容：{loc_str}，"
              f"應改成「主題內容 ＋ 形式」（如 女兒控卡斯楚殺害 主播開場BS）")

    print("-" * 60)
    total = (len(today_hits) + len(cross_hits) + len(form_hits)
             + len(miss_hits) + len(note_hits))
    print(f"共 {total} 組命中（純提示，不改 state；確認後用 s2_state.py set-category 手動改）")


if __name__ == "__main__":
    main()
