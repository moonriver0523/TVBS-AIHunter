# -*- coding: utf-8 -*-
"""s2_rundown_propose.py — S4 稿單提案生成器：評分器（唯讀、每天一次，全檢 §10／MASTER A33）。

**兩段式的第一段**：機械評分產 `{MMDD}-稿單候選.json`／`.txt`，供獨立 agent
（`s2_rundown_prompt.md`）讀了寫題目／角度／形式，產出真正給編輯看的稿單 txt。
本檔只算分數、只讀既有欄位，**不判讀內容、不寫狀態檔、不開中主題、不搶
`.s2-scan.lock`**（0819／0825 議題包不變式，見 MASTER A33）。

**判準（全部從狀態檔既有欄位機械算）：**
  `score(items)`：🔴+5／🟡+3（同題取最高，互斥）；`distinct sources` +1 each
  （上限 +3）；有 BITE +1；🔖+1；`tc.C` 含「臺灣」+3；🟤-2；則數≥8 +1。
  `qualifies(items)`：題目底下至少一則帶 🔴／🟡／🔖／🟤 其中之一才入榜——
  純機械訊號掃視用的關卡，不是「這題重不重要」的判斷（那是 prompt agent 的事）。
  `missing_of(items)`：無 BITE→「缺SOT」；畫面欄全是受訪／連線類詞（或全空）
  →「缺現場畫面」（詞表借用 `s2_pretag.FOOTAGE_NEG_KW`，R19 同一份，不重寫一套）；
  僅一個來源→「單一來源」。

**聚合：以中主題登記簿 canonical 為 key，跨大分類合併**（沒登記或沒別名對上
就用中主題名本身當 key）。⚠️ **本檔登記簿存取刻意比 `s2_state.canonical_of()`
更嚴格唯讀**：登記簿檔不存在時只回空登記簿，**不落地生成種子檔**（`s2_state`
那份的 auto-seed 行為是它自己的職責，本檔不重複、也不觸發，維持「全程唯讀」
更乾淨的邊界）。也**不 import `s2_state` 模組**——它在 module import 階段就會
跑 `default_file()`，17:00 後找不到今天檔案會直接 `SystemExit`，這支腳本沒有
理由承擔那個風險（見 `s2_state.py` 該函式的長篇註解）。

**CTV 候選整合**：`ctv_ids` 優先讀同目錄既有 `{MMDD}-CTV候選.json`（A34
`s2_ctv_candidates.py` 產出）；沒有就呼叫該檔的 `run(file_path, out_dir=None)`
在記憶體內算一次，**不落地寫檔**（落檔是 A34 自己的職責，這裡只是借用判準）。

用法：
    python -X utf8 s2_rundown_propose.py --file "…\\0906-s2-state.json"
    （不給 --out 就寫到狀態檔同目錄下 `_稿單提案/`；--top 預設 12）
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_ctv_candidates as cc  # noqa: E402  is_candidate／rank_key／_marks／derive_mmdd 唯一來源
import s2_pretag as pretag      # noqa: E402  FOOTAGE_NEG_KW（R19），畫面欄負面詞表唯一來源
import s2_render as sr          # noqa: E402  load_state／cat_of

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

# 中主題登記簿：路徑與 s2_state.REGISTRY_PATH 同一份檔案（單一真相源），
# 但本檔只讀，見檔頭說明——刻意不 import s2_state。
REGISTRY_PATH = os.path.join(HERE, "s2_topic_registry.json")

MIN_SRC_LEN_FOR_TOP = 8  # 則數 ≥8 才加分（Task 2 判準）


def _load_registry(path=None):
    """讀登記簿，檔案不存在／壞掉都回空登記簿——**不落地、不新建**任何檔案。"""
    p = path or REGISTRY_PATH
    if not os.path.exists(p):
        return {"topics": []}
    try:
        with open(p, encoding="utf-8-sig") as f:
            reg = json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {"topics": []}
    if not isinstance(reg, dict) or not isinstance(reg.get("topics"), list):
        return {"topics": []}
    return reg


def _canonical_of(name, registry):
    """回傳 (canonical 名, 改寫說明或 None)——邏輯同 `s2_state.canonical_of()`。"""
    for t in registry.get("topics", []):
        if name == t.get("name"):
            return name, None
        if name in (t.get("aliases") or []):
            return t["name"], f"{name}→{t['name']}（alias）"
    return name, None


def group_by_canonical(items, registry):
    """大分類/中主題/小分題 → canonical 中主題 分組。跳過 `note` 殼與空 `raw_entry`
    （同 `s2_render.group_items` 的殼判準），跳過沒有中主題的則（無法聚合評分）。

    回傳 `{canonical: {"items": [...], "bigs": {大分類, ...}}}`。
    """
    groups = {}
    for it in items:
        if it.get("script_status") == "note" or not (it.get("raw_entry") or "").strip():
            continue
        big, mid, _sub = sr.cat_of(it)
        if not mid:
            continue
        canonical, _rewrite = _canonical_of(mid, registry)
        g = groups.setdefault(canonical, {"items": [], "bigs": set()})
        g["items"].append(it)
        if big:
            g["bigs"].add(big)
    return groups


def _flags(items):
    """一次掃過整題的素材，抓出評分／入榜／缺什麼共用的訊號。"""
    best = 0  # 0=無 1=🟡 2=🔴（互斥，取本題最高）
    hilite = False
    aired = False
    bite = False
    taiwan = False
    sources = set()
    for it in items:
        red, orange, hl, ar = cc._marks(it.get("raw_entry"))
        if red:
            best = max(best, 2)
        elif orange:
            best = max(best, 1)
        hilite = hilite or hl
        aired = aired or ar
        fields = it.get("fields") or {}
        if fields.get("bite"):
            bite = True
        if "臺灣" in ((it.get("tc") or {}).get("C") or []):
            taiwan = True
        src = it.get("source") or ""
        if src:
            sources.add(src)
    return {"best": best, "hilite": hilite, "aired": aired, "bite": bite,
            "taiwan": taiwan, "sources": sources}


def score(items):
    """回傳 `(分數, reasons list)`——Task 2 加分規則，`reasons` 每項加分記一行。"""
    f = _flags(items)
    total = 0
    reasons = []
    if f["best"] == 2:
        total += 5
        reasons.append("🔴 +5")
    elif f["best"] == 1:
        total += 3
        reasons.append("🟡 +3")
    n_src = len(f["sources"])
    src_bonus = min(n_src, 3)
    if src_bonus:
        total += src_bonus
        reasons.append(f"來源{n_src}種 +{src_bonus}")
    if f["bite"]:
        total += 1
        reasons.append("有BITE +1")
    if f["hilite"]:
        total += 1
        reasons.append("🔖 +1")
    if f["taiwan"]:
        total += 3
        reasons.append("涉臺 +3")
    if f["aired"]:
        total -= 2
        reasons.append("🟤已播 -2")
    if len(items) >= MIN_SRC_LEN_FOR_TOP:
        total += 1
        reasons.append(f"則數{len(items)}(≥8) +1")
    return total, reasons


def qualifies(items):
    """入榜門檻：至少一則帶 🔴／🟡／🔖／🟤 其中之一。"""
    f = _flags(items)
    return f["best"] > 0 or f["hilite"] or f["aired"]


def missing_of(items):
    """缺什麼——`reasons` 之外另一份人可讀提示，Task 2 判準三條。"""
    f = _flags(items)
    missing = []
    if not f["bite"]:
        missing.append("缺SOT")
    tokens = []
    for it in items:
        footage = (it.get("fields") or {}).get("footage") or ""
        tokens.extend(t.strip() for t in re.split(r"[、,，]", footage) if t.strip())
    if not tokens or all(any(kw in t for kw in pretag.FOOTAGE_NEG_KW) for t in tokens):
        missing.append("缺現場畫面")
    if len(f["sources"]) <= 1:
        missing.append("單一來源")
    return missing


def _item_row(it):
    red, orange, hilite, _aired = cc._marks(it.get("raw_entry"))
    fields = it.get("fields") or {}
    return {
        "id": it.get("id") or "",
        "alert": "🔴" if red else ("🟡" if orange else ""),
        "hilite": bool(hilite),
        "bite": bool(fields.get("bite")),
        "dur": fields.get("duration") or "",
        "src": it.get("source") or "",
    }


def _load_ctv_ids(file_path, mmdd, out_dir):
    """`ctv_ids` 資料來源：優先讀同目錄既有 A34 產物，沒有才在記憶體內算一次
    （`cc.run(..., out_dir=None)` 不落地寫檔）。"""
    ctv_path = os.path.join(out_dir, f"{mmdd}-CTV候選.json") if (out_dir and mmdd) else None
    if ctv_path and os.path.exists(ctv_path):
        try:
            with open(ctv_path, encoding="utf-8-sig") as f:
                data = json.load(f)
            if isinstance(data, list):
                return {it.get("id") for it in data
                        if isinstance(it, dict) and it.get("id")}
        except (OSError, json.JSONDecodeError):
            pass
    result = cc.run(file_path, out_dir=None)
    return {it.get("id") for it in (result.get("candidates") or []) if it.get("id")}


def _txt_row(c):
    n_items = len(c["items"])
    n_sources = len({it["src"] for it in c["items"] if it["src"]})
    missing_str = "、".join(c["missing"]) if c["missing"] else "—"
    return f"{c['score']}｜{c['topic']}｜{n_items}｜{n_sources}｜{missing_str}"


def run(file_path, out_dir=None, top=12, registry_path=None):
    """核心流程：讀狀態檔（唯讀）→ 聚合＋評分＋入榜篩 → 排序截斷 →
    寫 json／txt（`out_dir` 給了才寫）→ 回傳結果 dict。"""
    raw = sr.load_state(file_path)
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        print("ERROR: 狀態檔 items 不是陣列（非正式 schema）")
        sys.exit(2)

    registry = _load_registry(registry_path)
    groups = group_by_canonical(items, registry)
    mmdd = cc.derive_mmdd(raw, file_path)

    ctv_ids_all = None  # 延後算，沒有入榜候選就不必花這個成本
    candidates = []
    for canonical, g in groups.items():
        its = g["items"]
        if not qualifies(its):
            continue
        if ctv_ids_all is None:
            ctv_ids_all = _load_ctv_ids(file_path, mmdd, out_dir)
        s, reasons = score(its)
        item_ids = {it.get("id") for it in its}
        candidates.append({
            "topic": canonical,
            "canonical": canonical,
            "score": s,
            "reasons": reasons,
            "items": [_item_row(it) for it in its],
            "ctv_ids": sorted(item_ids & ctv_ids_all),
            "missing": missing_of(its),
            "bigs": sorted(g["bigs"]),
        })

    candidates.sort(key=lambda c: (-c["score"], c["topic"]))
    candidates = candidates[:top]

    print(f"{len(groups)} 個中主題（含跨大分類聚合）→ 入榜 {len(candidates)} 題"
          f"（--top {top}{'，已截斷' if len(groups) > top else ''}）")

    result = {"candidate_count": len(candidates), "candidates": candidates, "mmdd": mmdd}

    if out_dir is not None:
        if not mmdd:
            print("ERROR: 無法判斷 {MMDD}（狀態檔缺 checkpoint、檔名也不是 4 位數字開頭），"
                  "不寫檔——請確認 --file 對象正確")
            sys.exit(2)
        os.makedirs(out_dir, exist_ok=True)
        json_path = os.path.join(out_dir, f"{mmdd}-稿單候選.json")
        txt_path = os.path.join(out_dir, f"{mmdd}-稿單候選.txt")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(candidates, f, ensure_ascii=False, indent=1)
        with open(txt_path, "w", encoding="utf-8") as f:
            for c in candidates:
                f.write(_txt_row(c) + "\n")
        print(f"已寫出：{json_path}")
        print(f"已寫出：{txt_path}")
        result["json_path"] = json_path
        result["txt_path"] = txt_path

    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", required=True, help="狀態檔路徑（{MMDD}-s2-state.json）")
    ap.add_argument("--out", default=None,
                     help="輸出目錄（預設：狀態檔同目錄下 _稿單提案/）")
    ap.add_argument("--top", type=int, default=12, help="提案題數上限（預設 12）")
    ap.add_argument("--registry", default=None,
                     help="中主題登記簿路徑（預設：scripts/s2_topic_registry.json，唯讀）")
    args = ap.parse_args()

    out_dir = args.out
    if out_dir is None:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(args.file)), "_稿單提案")
    run(args.file, out_dir=out_dir, top=args.top, registry_path=args.registry)


if __name__ == "__main__":
    main()
