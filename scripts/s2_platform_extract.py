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


def raw_list(data):
    """`--raw` 收到的可能是陣列，也可能是**包了一層的物件**。

    🔴 0901-2000 實錯的真正原因：`enex_raw_2000.json` 是
    `{"total":…, "count":…, "items":[…]}`——瀏覽器端回傳被卸載成檔案時就是這個形狀。
    agent 直接把整個物件餵進來，這支去迭代它就拿到 dict 的**鍵（字串）**，
    於是 `AttributeError: 'str' object has no attribute 'get'` 整支掛掉。
    `s2_state.py cmd_add_batch` 早就有 `data.get("entries")` 的解包慣例，
    這裡比照：包一層就拆一層，不要逼呼叫端先手工剝殼。
    """
    if isinstance(data, dict):
        for k in ("items", "hits", "rows", "results"):
            if isinstance(data.get(k), list):
                return data[k]
    return data


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


# 時段標記：由 render 依收錄時間補，候選檔／entries 自己帶就會變成兩個（18 §2）。
# 🔴／🟡／⭐／🟤／🔖 是**重大與畫面亮點標記**，性質不同，entries 本來就可以帶。
PERIOD_MARKS = "△▲◇■◆●"
SEVERITY_MARKS = "🔴🟡⭐🟤🔖"


def norm_category(v):
    """`category` 允許兩種寫法，統一成物件。

    🔴 0901-2000 實錯：agent 把 category 寫成 `"烏俄/國際外交/莫迪籲普欽止戰"`
    字串（那是 `set-category --pairs` 的語法，天天在用，寫串很自然），
    extract 照收、lint 才在**整份 23 則都寫完之後**吐 23 個「category 須為物件」，
    只好整份重寫一次（100 秒）。既然分隔語法本來就是 `/`、拆法唯一且無損，
    就在這裡收下來，不要讓它變成一次全量重寫。
    """
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip():
        parts = [p.strip() for p in v.split("/") if p.strip()][:3]
        return dict(zip(("大分類", "中主題", "小分題"), parts))
    return {}


def check_entries(entries):
    """`--entries` 的形狀預檢：**在動任何 ffprobe／寫任何檔之前**先擋下來。

    要解決的是 0901-2000 那個形狀：entries 整份寫完（118 秒）→ extract →
    lint 吐 51 項必修 → 整份重寫（100 秒）→ 再吐 4 項 → 再改。
    一輪 ENEX 7.9 分鐘裡約 2.5 分是這樣燒掉的。

    ⛔ 這裡只擋**確定要重寫**的形狀問題，不擋編輯判斷（分類對不對、摘要好不好）。
    `raw_entry` 沒填不在此列——那是既有設計（記 known_gaps，lint 才擋），
    因為站方還沒出稿時本來就填不了。
    """
    problems = []
    if not isinstance(entries, dict):
        return [f"--entries 應為物件（{{id: {{…}}}}），實得 {type(entries).__name__}"]
    for k, v in entries.items():
        if not isinstance(v, dict):
            problems.append(f"{k}: 值不是物件（實得 {type(v).__name__}）")
            continue
        if v.get("skip"):
            continue          # 排除的只需要 skip 理由，其餘欄位不要求
        cat = v.get("category")
        if cat is not None and not isinstance(cat, (dict, str)):
            problems.append(f"{k}: category 須為物件或 `大分類/中主題/小分題` 字串，"
                            f"實得 {type(cat).__name__}")
        else:
            c = norm_category(cat)
            for kk in ("大分類", "中主題"):
                if not str(c.get(kk) or "").strip():
                    problems.append(f"{k}: category 缺 `{kk}`")
            bad = [ch for ch in ";=" if any(ch in str(x) for x in c.values())]
            if bad:
                problems.append(f"{k}: category 含 {'／'.join(bad)}——"
                                f"set-category --pairs 會被切錯")
        if "sb_count" in v and not isinstance(v["sb_count"], int):
            problems.append(f"{k}: sb_count 須為整數，實得 {v['sb_count']!r}")
        raw = v.get("raw_entry")
        if raw is None or raw == "":
            continue          # 見上：不在此列
        if not isinstance(raw, str):
            problems.append(f"{k}: raw_entry 須為字串，實得 {type(raw).__name__}")
            continue
        first = raw.strip().split("\n")[0]
        if first[:1] in PERIOD_MARKS:
            problems.append(f"{k}: raw_entry 自帶時段標記「{first[:1]}」"
                            f"（render 會依收錄時間再補一個，18 §2）"
                            f"——🔴／🟡／🔖 可以帶，時段標記不行")
        head = first.lstrip(PERIOD_MARKS + SEVERITY_MARKS + " ").split(" ", 1)[0]
        bare = k[3:] if k.upper().startswith("ABC") else (k[4:] if k.upper().startswith("ENEX") else k)
        if head and head not in (k, "ENEX" + bare, "ABC" + bare):
            problems.append(f"{k}: raw_entry 行首代碼是 {head!r}，與鍵值不符")
    return problems


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


def lookup_entry(entries, rid, prefix="ENEX"):
    """entries 的查找**只有這一份**（2026-09-01 抽出）。

    🔴 前一版併發改動留下一個坑：預先挑網址的迴圈寫 `a or b`、主迴圈寫 `if a is None: b`，
    兩者對 **falsy 但存在**的值（例如佔位用的 `{}`）判斷不同——會出現
    「主迴圈用裸鍵那筆組素材，時長卻來自前綴鍵那筆」這種錯配。
    正常資料不會觸發，但兩段程式對同一件事有兩種答案，早晚會咬人。
    ⛔ 不要在別處再抄一份查找邏輯。

    🔴 2026-09-04（V7 準備）：`prefix` 參數是給 ABC 用的。原本 `extract_abc`
    自己寫 `entries.get(story)`，**只認裸 Story Number**——agent 若比照 ENEX
    的文件用 `ABC080926021` 當鍵，每一則都會落進 `dropped`、候選檔空的、
    extract 與 lint 都回 0，就是 2026-08-31 ENEX 那個「48 則無聲蒸發」的同類。
    """
    v = entries.get(rid)
    if v is None:
        v = entries.get(prefix + rid)
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
            "category": norm_category(ent.get("category")),
            "sb_count": ent.get("sb_count", 0),
            "src_text": truncate(it.get("desc", "")),
            "enex": {"newslinkId": it.get("nlid"), "duration": dur_str, "partner": it.get("partner")},
        })
    return items, skipped, dropped, known_gaps


# `MMDDYY` ＋ 3~10 碼序號。🔴 2026-09-05 沙箱實測訂正：原本寫死 `^\d{6}\d{3}$`（9 碼），
# 但當日 140 列裡有 **14 列是 14 碼**（`09042606422425` 這種，加盟台轉供，
# `s2_validate.py:44-48` 早就記著「加盟台 14 碼」而放寬到 `ABC\d{6,16}`）——
# 9 碼的規則會讓那 10% 全被誤記進 known_gaps 叫人工複核。
STORY_NUM_RE = re.compile(r"^\d{6}\d{3,10}$")

# ABC 清單 CSV 的 `Length`。0810 §二實測是 `05:00`，但站方沒有保證值域
# （0810 §六 Phase 0 第 6 項「`Length` 值域盤點」到現在還沒做），
# 所以 `00:05:00` 這種寫法要能吃、而且要**正規化成 MM:SS**——
# 直接原樣接上去會讓交接單上 ABC 寫 `▎00:05:00`、AP／RT 寫 `▎05:00`，兩種格式並存。
# 🔴 2026-09-05 沙箱實測（daily profile，9/4~9/5 共 140 列）：`Length` 只有兩種形狀，
#    `MM:SS`（94 列）與 **`:SS`（46 列，33%）**——後者是「只有秒」的寫法（`:33`）。
#    ⛔ 不要只認 `MM:SS`：`s2_platform_lint.py:288` 對 ABC 是**沒有時長就報錯**，
#    漏掉這一種等於每輪三分之一的 ABC 交件都被擋下來重寫。
_ABC_LEN_RE = re.compile(r"^(?:(\d{1,3}):)?(\d{0,3}):(\d{2})$")


def abc_length_mmss(v):
    """`05:00`／`:33`／`00:05:00`／`1:02:03` → `MM:SS`；認不得或 0 秒回 None。

    🔴 2026-09-05（V7 首輪驗收）：站方真的會給 `Length = 00:00`
    （`ABC090426064` ClancyTrialFriMiniPKG，0904-2300 那批），照補就會在交接單上
    寫出 `▎00:00`——而 `18 §140` 明訂「量不到就留白，⛔ 不要編數字、不要 `▎?`／
    `▎00:00` 佔位」。**0 秒一律當成抓不到**，改記 known_gaps 讓人看得見。
    """
    m = _ABC_LEN_RE.match(str(v or "").strip())
    if not m:
        return None
    h, mi, se = m.groups()
    total = int(h or 0) * 3600 + int(mi or 0) * 60 + int(se)
    if total <= 0:
        return None
    return fmt_mmss(total)


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
        # 裸 Story Number 與帶 `ABC` 前綴的鍵都認（同 extract_enex，理由見 lookup_entry）
        ent = lookup_entry(entries, story, "ABC")
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
        # 🔴 時長：ABC 的 `Length` 是清單 CSV 現成的機械欄位，比照 ENEX 的
        # `with_duration()` 自動補成素材行行尾 `▎MM:SS`——0901-1700 那次
        # 「量到了卻只活在子物件裡、交接單一則都沒有時長」不要在 ABC 重演。
        _len = str(row.get("Length") or "").strip()
        _mmss = abc_length_mmss(_len)
        if _mmss:
            raw_entry = with_duration(raw_entry, _mmss)
        elif _len:
            why = ("站方給 00:00（等於沒有時長）" if _len.strip(":0") == ""
                   else "不是 MM:SS／:SS／HH:MM:SS")
            known_gaps.append(f"{code}: Length 值 `{_len}` {why}，未自動補進素材行——"
                              f"⛔ 不要手動補 `▎00:00` 佔位（18 §140），留白就好")

        items.append({
            "id": code,
            "source": "ABC",
            "first_seen_checkpoint": None,
            "script_status": "has_script",
            "raw_entry": raw_entry,
            "category": norm_category(ent.get("category")),
            "sb_count": ent.get("sb_count", 0),
            "src_text": truncate(src_text),
            "abc": {"slug": row.get("Slug"), "storyNumber": story,
                    "duration": row.get("Length"), "detailId": ent.get("detailId")},
        })
    return items, skipped, dropped, known_gaps


EXTRACTORS = {"enex": extract_enex, "abc": extract_abc}


def main():
    ap = argparse.ArgumentParser(description="ENEX／ABC 候選檔擷取（機械欄位封裝）")
    ap.add_argument("site", choices=sorted(EXTRACTORS) + ["check-entries"],
                    help="enex／abc＝擷取；check-entries＝只驗 --entries 形狀就結束")
    ap.add_argument("--raw")
    ap.add_argument("--entries", required=True)
    ap.add_argument("--checkpoint")
    ap.add_argument("--window-start")
    ap.add_argument("--window-end")
    ap.add_argument("--out")
    ap.add_argument("--probe-workers", type=int, default=PROBE_WORKERS,
                    help=f"ffprobe 併發數（預設 {PROBE_WORKERS}）。"
                         f"1 ＝退回序列；被 CDN 限流時調小")
    args = ap.parse_args()

    entries = load_json(args.entries)
    # ⭐ 形狀預檢一律先跑（`check-entries` 只跑這一段就結束）：擋在 ffprobe 與
    # 寫檔之前，錯了當場就知道，不必等 lint 在整份寫完之後才吐一長串。
    problems = check_entries(entries)
    if problems:
        print(f"⛔ --entries 形狀有 {len(problems)} 項要改（在跑 extract 之前先修）：",
              file=sys.stderr)
        for p in problems:
            print(f"   {p}", file=sys.stderr)
        print("   ⚠️ 這些都是**形狀**問題，改完不必重寫摘要——"
              "只要動到出問題的那幾筆（13g V5-2）。", file=sys.stderr)
        return 2
    if args.site == "check-entries":
        print(f"✅ --entries 形狀沒問題（{len(entries)} 筆）")
        return 0

    missing = [n for n, v in (("--raw", args.raw), ("--checkpoint", args.checkpoint),
                              ("--window-start", args.window_start),
                              ("--window-end", args.window_end)) if not v]
    if missing:
        ap.error("擷取模式需要 " + "、".join(missing))

    raw_items = raw_list(load_json(args.raw))
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
