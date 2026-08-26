#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ENEX／ABC 候選檔擷取工具（MASTER A9 子項②）。

## 要解決什麼

18 檔落差報告 §3：ENEX／ABC 的端點規格、抽取白名單、逐字保真驗證目前**只存在於
兩份計畫書的文字裡**（`plans/2026-08-09-ENEX-...`／`plans/2026-08-10-ABC-...`），
沒有程式碼封裝——每輪都要 agent 在 `browser_evaluate` 裡憑記憶重寫一次。

## 這支腳本的分工邊界（跟三站的 `s2_batch_prep.py` 不同一件事）

三站的 agent 會被排程呼叫，`build` 直接餵 `s2_state.py add-batch`。
ENEX／ABC 是「人工下令才跑、獨立流程」（18 檔 §0），輸出目標是**候選檔**
（`common/18-交換平台素材整併.md` §2 那個 schema），拿去餵 `s2_platform_lint.py`
／`s2_platform_merge.py`，不是直接 add-batch——所以這支腳本輸出候選 JSON 的
完整形狀（`window_start`／`counts`／`items[]`…），跟 `s2_batch_prep.py` 的
`build` 輸出的 add-batch batch.json 不是同一種東西，兩者不要混用。

## 抽取責任怎麼分（機械 vs 編輯判斷，跟 `s2_batch_prep.py` 同一條原則）

- **ENEX**：`desc`（STORYLINE＋SHOTLIST＋引言，站方原文全文）本來就是逐字擷取
  的原文，機械直接拿來當 `src_text`，不需要 agent 重寫。**時長**改用
  `videoLowResCdn` 直連 mp4 跑 `ffprobe` 機械取得（見 §10 查證：這個 URL
  公開、免登入，不需要 freecaster uuid 對映——原計畫書那條路走錯方向）。
  `category`／`sb_count`／整則排除判斷仍是 agent 的編輯判斷，走 `--entries`。
- **ABC**：CSV 清單只有 `Length`（機械直接用）跟 `Slug`／`Story Number`，
  **沒有全文**——`src_text`（Script 全文）必須是 agent 自己去 Detail 頁抓的，
  這支腳本不生成、不代抓，一樣走 `--entries`。

## 用法

    python s2_platform_extract.py enex --raw enex_items.json --entries enex_entries.json \\
        --checkpoint 0826-1600 --window-start "2026-08-26 13:00" --window-end "2026-08-26 16:00" \\
        --out "…\\0826-ENEX-state.json"

    python s2_platform_extract.py abc --raw abc_rows.json --entries abc_entries.json \\
        --checkpoint 0826-1600 --window-start "2026-08-26 13:00" --window-end "2026-08-26 16:00" \\
        --out "…\\0826-ABC-state.json"

`--raw`：
  enex＝附錄 A §A-3 `slimEnex()` 的輸出陣列（每筆至少 `id`／`title`／`desc`／
         `partner`／`cat`／`loc`／`tags`／`ts`／`dl`）。
  abc ＝ 18 檔 §10 `fetchAbcWindowRows()` 的輸出陣列（CSV 欄位原樣）。

`--entries`：`{識別碼: {category:{...}, sb_count, src_text(ABC必填), skip}}`，
  識別碼 enex 用 `id`（不含 ENEX 前綴）、abc 用 `News Story`（Story Number）。
  沒在 entries 裡出現的 raw 項目**不會**被靜默排除——會列進 `dropped`，
  提醒漏判（同 `s2_platform_merge.py` 的護欄精神：缺欄位不靜默丟）。
"""
import argparse
import json
import re
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

SRC_TEXT_MAX = 3000


def truncate(s, n=SRC_TEXT_MAX):
    s = s or ""
    return s if len(s) <= n else s[:n] + "(內容過長已截斷)"


def load_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def probe_duration_seconds(url):
    """對公開 CDN 網址跑 ffprobe 拿時長（秒）。失敗回傳 None，不拋例外——
    呼叫端要能把「量不到」明確記進 known_gaps，不是讓整支腳本掛掉。"""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", url],
            capture_output=True, text=True, timeout=20, check=True,
        )
        return float(out.stdout.strip())
    except Exception:
        return None


def fmt_mmss(seconds):
    if seconds is None:
        return None
    total = round(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def build_counts(kept_n, skipped_n):
    return {"掃描": kept_n + skipped_n, "收錄": kept_n, "排除": skipped_n}


def extract_enex(raw_items, entries, duration_fn=probe_duration_seconds):
    items, skipped, dropped, known_gaps = [], [], [], []
    for it in raw_items:
        rid = str(it.get("id") or it.get("_id") or "")
        if not rid:
            dropped.append({"raw": it, "why": "缺 id"})
            continue
        code = "ENEX" + rid
        ent = entries.get(rid)
        if ent is None:
            dropped.append({"id": code, "why": "raw 有但 entries 沒判斷（未收進候選，不算排除，要確認是不是漏判）"})
            continue
        skip = ent.get("skip") or ""
        if skip:
            skipped.append({"id": code, "why": skip})
            continue

        dur_sec = duration_fn(it.get("dl")) if it.get("dl") else None
        dur_str = fmt_mmss(dur_sec)
        if dur_str is None:
            known_gaps.append(f"{code}: 時長抓不到（{'無 dl 網址' if not it.get('dl') else 'ffprobe 失敗'}）")

        raw_entry = ent.get("raw_entry") or ""
        if not raw_entry:
            known_gaps.append(f"{code}: raw_entry 尚未填（三段式中文摘要是編輯判斷，這支不代寫，"
                               f"lint 會擋，交件前要補）")
        items.append({
            "id": code,
            "source": "ENEX",
            "first_seen_checkpoint": None,  # 呼叫端統一填 checkpoint
            "script_status": "has_script",
            "raw_entry": raw_entry,
            "category": ent.get("category") or {},
            "sb_count": ent.get("sb_count", 0),
            "src_text": truncate(it.get("desc", "")),
            "enex": {"newslinkId": it.get("nlid"), "duration": dur_str, "partner": it.get("partner")},
        })
    return items, skipped, dropped, known_gaps


STORY_NUM_RE = re.compile(r"^\d{6}\d{3}$")


def extract_abc(raw_rows, entries):
    items, skipped, dropped, known_gaps = [], [], [], []
    for row in raw_rows:
        story = str(row.get("News Story") or "").strip()
        if not story:
            dropped.append({"raw": row, "why": "缺 News Story（Story Number）"})
            continue
        if not STORY_NUM_RE.match(story):
            known_gaps.append(f"ABC{story}: Story Number 前 6 碼不是合法 MMDDYY 格式，人工複核")
        code = "ABC" + story
        ent = entries.get(story)
        if ent is None:
            dropped.append({"id": code, "why": "raw 有但 entries 沒判斷（未收進候選，不算排除，要確認是不是漏判）"})
            continue
        skip = ent.get("skip") or ""
        if skip:
            skipped.append({"id": code, "why": skip})
            continue
        src_text = ent.get("src_text") or ""
        if not src_text:
            known_gaps.append(f"{code}: 缺 src_text（ABC 全文要 agent 自己去 Detail 頁抓，這支不代抓）")
        raw_entry = ent.get("raw_entry") or ""
        if not raw_entry:
            known_gaps.append(f"{code}: raw_entry 尚未填（三段式中文摘要是編輯判斷，這支不代寫，"
                               f"lint 會擋，交件前要補）")

        items.append({
            "id": code,
            "source": "ABC",
            "first_seen_checkpoint": None,
            "script_status": "has_script",
            "raw_entry": raw_entry,
            "category": ent.get("category") or {},
            "sb_count": ent.get("sb_count", 0),
            "src_text": truncate(src_text),
            "abc": {"slug": row.get("Slug"), "storyNumber": story,
                    "duration": row.get("Length"), "detailId": ent.get("detailId")},
        })
    return items, skipped, dropped, known_gaps


EXTRACTORS = {"enex": extract_enex, "abc": extract_abc}


def main():
    ap = argparse.ArgumentParser(description="ENEX／ABC 候選檔擷取（機械欄位封裝）")
    ap.add_argument("site", choices=sorted(EXTRACTORS))
    ap.add_argument("--raw", required=True)
    ap.add_argument("--entries", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--window-start", required=True)
    ap.add_argument("--window-end", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()

    raw_items = load_json(args.raw)
    entries = load_json(args.entries)
    fn = EXTRACTORS[args.site]
    items, skipped, dropped, known_gaps = fn(raw_items, entries)

    for it in items:
        it["first_seen_checkpoint"] = args.checkpoint

    doc = {
        "window_start": args.window_start,
        "window_end": args.window_end,
        "checkpoint": args.checkpoint,
        "source": args.site.upper(),
        "merged_into_handover": False,
        "reviewed": False,
        "counts": build_counts(len(items), len(skipped)),
        "skipped": skipped,
        "needs_review": [],
        "known_gaps": known_gaps,
        "items": items,
    }

    out = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"已寫入 {args.out}（收 {len(items)}、排除 {len(skipped)} 則）", file=sys.stderr)
    else:
        print(out)

    if dropped:
        print(f"⚠️ {len(dropped)} 筆 raw 有但 entries 沒判斷（未收進候選，確認是不是漏判）：",
              file=sys.stderr)
        for d in dropped[:10]:
            print(f"   {d}", file=sys.stderr)
    if known_gaps:
        print(f"⚠️ known_gaps {len(known_gaps)} 項，已寫進候選檔：" + "；".join(known_gaps[:5]),
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
