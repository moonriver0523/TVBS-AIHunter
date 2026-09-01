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
import concurrent.futures
import json
import re
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 🔴 2026-08-31 由 3000 提高到 8000（實測改的）：附錄 A-3 原本寫「超過 3,000 截斷，
# 目前實測最長 2,769 字元，尚未觸發過」——那個前提已經過期。0831 13:00–19:00 窗
# 48 則裡有 **9 則（19%）** 超過 3,000，最長 5,634。而 ENEX 的 dopesheet 排列是
# STORYLINE → SHOTLIST → **SOUNDBITE**，引言在最後面，截斷正好切掉它：
# 實測 ENEX928973 的 4 段 SOUNDBITE 只剩 2 段、ENEX928976 的 5 段剩 4 段。
# 而 18 檔 §2 明訂 src_text 是「事後離線查證的**唯一依據**、也是 sb_count 的判準」
# ——截在那一段上等於毀掉它唯一的存在理由。
# 成本可忽略：18 檔 §2 自己寫「瘦身後單則約 1–5KB」，一輪 48 則全存也才幾百 KB。
SRC_TEXT_MAX = 8000


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


# ffprobe 併發數。⚠️ 這是**網路 I/O 等待**不是 CPU 運算，所以開多執行緒有效
# （每條大部分時間都卡在等 CDN 回應，不會互相搶 CPU）。
# 8 是保守值：0831 實測 48 則序列跑 79 秒，這裡的瓶頸就是逐則往返。
# ⛔ 不要無限開——同時打太多連線可能被 CDN 限流，那會從「慢」變成「量不到」。
PROBE_WORKERS = 8


def probe_durations(urls, duration_fn=None, workers=PROBE_WORKERS):
    """一次量一批網址的時長，回傳 {網址: 秒數或 None}。

    🔴 2026-08-31 加：原本在主迴圈裡逐則 `ffprobe`，48 則要 **79 秒**——
    那是四站輪的純浪費（0811 那次加掛 ENEX 跑到 56.7 分鐘、NS token 在空窗期過期）。
    改成併發後同一批約 10–15 秒。

    ⚠️ **失敗一律回 None，絕不讓例外冒出來**——量不到時長是 `known_gaps` 的事，
    不能讓整支腳本掛掉（同 `probe_duration_seconds` 的既有哲學）。
    `workers<=1` 退回序列，給不想併發或要重現問題時用。
    """
    fn = duration_fn or probe_duration_seconds
    uniq = [u for u in dict.fromkeys(u for u in urls if u)]
    if not uniq:
        return {}
    if workers <= 1 or len(uniq) == 1:
        return {u: _safe_probe(fn, u) for u in uniq}
    out = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_safe_probe, fn, u): u for u in uniq}
        for f in concurrent.futures.as_completed(futs):
            out[futs[f]] = f.result()
    return out


def _safe_probe(fn, url):
    try:
        return fn(url)
    except Exception:
        return None


def fmt_mmss(seconds):
    if seconds is None:
        return None
    total = round(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


_DUR_TAIL = re.compile(r"^\d{1,3}:\d{2}(?::\d{2})?$")


def with_duration(raw_entry, dur_str):
    """把量到的時長補成素材行最後一段 `▎MM:SS`。

    🔴 2026-09-01 實錯（0901-1700 首輪四站）：ffprobe 明明 23/23 都量到時長
    （存在候選檔 `enex.duration`），交接單上 25 則 ENEX **全部沒有時長**，
    而 AP／RT 每行都有。原因是那時只有「怎麼量」的規則、沒有「量到要放哪裡」，
    18 §140 還停在舊版「ENEX 抓不到時長→留白」，掃帶 agent 是照舊規則做對的事。

    時長是機械事實、`dur_str` 本來就在這支手上——就別再靠 agent 逐則手抄。
    ⛔ 兩種情況一律不動 raw_entry：
      1. 已經有時長結尾（agent 自己寫了就以它為準，這支不覆蓋）；
      2. `dur_str` 是 None（量不到就是留白，**不准補 `▎?`／`▎00:00` 佔位**，18 §140）。
    """
    if not raw_entry or not dur_str:
        return raw_entry
    tail = raw_entry.rstrip().rsplit("▎", 1)[-1].strip()
    if _DUR_TAIL.match(tail):
        return raw_entry
    return raw_entry.rstrip() + "▎" + dur_str


def build_counts(kept_n, skipped_n, dropped_n=0):
    """`掃描` ＝ 這一輪實際看過的 raw 則數 ＝ 收錄 ＋ 排除 ＋ **漏判**。

    🔴 2026-09-01 修（獨立複查抓到）：原本 `掃描 = 收錄 + 排除`，**把 dropped 漏掉了**。
    後果是抽取整段失敗（entries 鍵全對不上）時，48 則全進 dropped，
    候選檔卻寫成 `{掃描:0, 收錄:0, 排除:0}`——看起來就像「這輪站方沒素材」，
    跟真正的無聲全失敗**完全分不出來**，連 lint 想擋都沒有依據可擋。
    18 檔 §2 的範例本來就是 `掃描 73 / 收錄 14 / 排除 13`（三者不相等），
    所以「掃描比收錄+排除大」本來就是這個 schema 的原意。
    """
    return {"掃描": kept_n + skipped_n + dropped_n,
            "收錄": kept_n, "排除": skipped_n, "漏判": dropped_n}


def bare_enex_id(v):
    """把 `ENEX929038` 與 `929038` 一律正規化成裸 id。

    🔴 2026-08-31 修（實測 48 則全數蒸發）：本函式原本假設 `--raw` 的 `id` 是裸的，
    但上游 `slimEnex()`（附錄 A-3）產的是 `id: 'ENEX' + h._id`，**帶前綴**。
    兩種餵法都會壞，而且壞的方向不同：
      · entries 用裸鍵（文件說的正確用法）→ `entries.get("ENEX929038")` 找不到
        → 48 則全進 dropped → 候選檔 items 空的 → **extract 離開碼 0、lint 也 0**
        → 整輪 ENEX 無聲收 0 則，沒有任何一處會叫。
      · entries 用帶前綴的鍵 → code 變成 `ENEXENEX929038`（lint 有擋，離開碼 1）。
    修法刻意做成**兩邊都容忍**，而不是要求上游改格式——上游是規則文件裡給 agent
    照抄的 JS，改那裡只能靠自律，這裡一次擋住兩種形狀才是防呆。
    """
    s = str(v or "").strip()
    return s[4:] if s.upper().startswith("ENEX") else s


def enex_media_url(it):
    """量時長要用的網址。

    🔴 2026-08-31 修：原本量 `it["dl"]`，但 `slimEnex()` 的
    `dl = https://members.enex.news/download/{id}` 是**要登入的下載頁、不是影片**，
    ffprobe 一律回 `Invalid data found`（實測 48/48 全失敗）。
    真正能量的是 `videoLowResCdn`（公開、免登入、支援 Range）——那也正是
    `2026-08-26-ENEX-ABC技術落差更新規劃書` §35-41 查證後指定的欄位，
    只是實作當時接錯欄位。實測同一則：dl → rc=1；videoLowResCdn → 112.36 秒。
    `dl` 保留為退路，不主動用。
    """
    return it.get("url") or it.get("videoLowResCdn") or None


def lookup_entry(entries, rid):
    """entries 的查找**只有這一份**（2026-09-01 抽出）。

    🔴 前一版併發改動留下一個坑：預先挑網址的迴圈寫 `a or b`、主迴圈寫 `if a is None: b`，
    兩者對 **falsy 但存在**的值（例如佔位用的 `{}`）判斷不同——會出現
    「主迴圈用裸鍵那筆組素材，時長卻來自前綴鍵那筆」這種錯配。
    正常資料不會觸發，但兩段程式對同一件事有兩種答案，早晚會咬人。
    ⛔ 不要在別處再抄一份查找邏輯。
    """
    v = entries.get(rid)
    if v is None:
        v = entries.get("ENEX" + rid)
    return v


def extract_enex(raw_items, entries, duration_fn=probe_duration_seconds,
                 workers=PROBE_WORKERS):
    items, skipped, dropped, known_gaps = [], [], [], []
    # ⭐ 先把「真的要量」的網址挑出來一次量完（併發），再進主迴圈組候選。
    #    只量會被收錄的——skip 掉的（自家素材）與 entries 沒判斷的不必浪費一次往返。
    _need = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue          # 主迴圈會把它記進 dropped，這裡只是別讓 .get 炸掉
        _rid = bare_enex_id(it.get("id") or it.get("_id"))
        if not _rid:
            continue
        _ent = lookup_entry(entries, _rid)
        if _ent is None or _ent.get("skip"):
            continue
        _u = enex_media_url(it)
        if _u:
            _need.append(_u)
    dur_map = probe_durations(_need, duration_fn=duration_fn, workers=workers)

    for n, it in enumerate(raw_items, 1):
        # 🔴 0901-2000 實錯：`--raw` 裡的元素是字串（不是物件），這支直接吐
        # `AttributeError: 'str' object has no attribute 'get'` 一整支掛掉，
        # agent 還得回頭 grep 原始碼才看得懂。`s2_platform_lint.py` 早就有
        # 「第n筆: 不是物件」的護欄——比照辦理：記進 dropped、指名第幾筆，
        # 其餘照跑。⛔ 不要靜默跳過：漏判要看得見（同 dropped 的既有哲學）。
        if not isinstance(it, dict):
            dropped.append({"id": f"第{n}筆", "why":
                            f"不是物件（實得 {type(it).__name__}）——"
                            f"--raw 應為 slimEnex() 輸出的物件陣列，"
                            f"檢查是不是餵成字串陣列或多包了一層"})
            continue
        rid = bare_enex_id(it.get("id") or it.get("_id"))
        if not rid:
            dropped.append({"raw": it, "why": "缺 id"})
            continue
        code = "ENEX" + rid
        # entries 的鍵兩種都認（裸 id 優先，其次帶前綴），理由同 bare_enex_id
        ent = lookup_entry(entries, rid)
        if ent is None:
            dropped.append({"id": code, "why": "raw 有但 entries 沒判斷（未收進候選，不算排除，要確認是不是漏判）"})
            continue
        skip = ent.get("skip") or ""
        if skip:
            skipped.append({"id": code, "why": skip})
            continue

        media = enex_media_url(it)
        dur_sec = dur_map.get(media) if media else None
        dur_str = fmt_mmss(dur_sec)
        if dur_str is None:
            # ⚠️ 「還沒上架」跟「真的抓失敗」要分得出來：實測 editStatus=PUBLISHING NOW
            # 的素材就是還沒有檔案，沒有 videoLowResCdn 屬正常，不是故障。
            if not media:
                why = ("尚未上架（editStatus=PUBLISHING NOW，站方還沒產生檔案）"
                       if str(it.get("estat") or "").upper().startswith("PUBLISHING")
                       else "沒有 videoLowResCdn 網址")
            else:
                why = "ffprobe 失敗"
            known_gaps.append(f"{code}: 時長抓不到（{why}）")

        raw_entry = ent.get("raw_entry") or ""
        if not raw_entry:
            known_gaps.append(f"{code}: raw_entry 尚未填（三段式中文摘要是編輯判斷，這支不代寫，"
                               f"lint 會擋，交件前要補）")
        items.append({
            "id": code,
            "source": "ENEX",
            "first_seen_checkpoint": None,  # 呼叫端統一填 checkpoint
            "script_status": "has_script",
            "raw_entry": with_duration(raw_entry, dur_str),
            "category": ent.get("category") or {},
            "sb_count": ent.get("sb_count", 0),
            "src_text": truncate(it.get("desc", "")),
            "enex": {"newslinkId": it.get("nlid"), "duration": dur_str, "partner": it.get("partner")},
        })
    return items, skipped, dropped, known_gaps


STORY_NUM_RE = re.compile(r"^\d{6}\d{3}$")


def extract_abc(raw_rows, entries):
    items, skipped, dropped, known_gaps = [], [], [], []
    for n, row in enumerate(raw_rows, 1):
        if not isinstance(row, dict):   # 同 extract_enex，理由見那邊的註解
            dropped.append({"id": f"第{n}筆", "why":
                            f"不是物件（實得 {type(row).__name__}）——"
                            f"--raw 應為 CSV 轉出的物件陣列"})
            continue
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
    ap.add_argument("--probe-workers", type=int, default=PROBE_WORKERS,
                    help=f"ffprobe 併發數（預設 {PROBE_WORKERS}）。"
                         f"1 ＝退回序列；被 CDN 限流時調小")
    args = ap.parse_args()

    raw_items = load_json(args.raw)
    entries = load_json(args.entries)
    fn = EXTRACTORS[args.site]
    if args.site == "enex":
        items, skipped, dropped, known_gaps = fn(
            raw_items, entries, workers=max(1, args.probe_workers))
    else:
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
        "counts": build_counts(len(items), len(skipped), len(dropped)),
        "skipped": skipped,
        # 🔴 2026-09-01：dropped 一定要進候選檔。原本只印到 stderr，
        # 交件端與 lint 都看不到——「整批漏判」因此變成一份看起來正常的空檔。
        "dropped": dropped,
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
