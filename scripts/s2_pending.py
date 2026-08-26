#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`_待整併/` 交件檔的偵測（2026-08-26 上線）。

## 要解決什麼

0825-2200 那輪：交件夾裡躺著 4 份當天的檔（ENEX 20:59／ABC 21:09／側錄候選 21:53／
韓聯社CNA 21:59），agent **一份都沒整併**，整輪從開工到收工沒有任何一步去看那個資料夾。
事後查出三層落差：

1. `s2_scan_prompt.md` 從開工到收工沒有任何一步要 agent 去看 `_待整併/`；
   「收工前必做」第 0 步的 `s2_mark_ingested.py --apply` 是**事後**改名，
   它假設整併**已經發生**了。
2. 規則寫在 `13`「`_待整併/`」節，但執行版 `13c` 只有一句「本輪照 §4b 整併即可」，
   而 `13c2` §4b 講的是「整併時分類歸錯位怎麼修」——**不是「怎麼發現有東西要整併」**。
3. 程式端零偵測：`s2_render.py`／`s2_audit.py` 都不掃這個資料夾。

## 為什麼修在程式而不是規則

⛔ **不要再往規則檔加字。** `13c2` §2 的指令表**早就**寫著

    s2_state.py … resume   # 開工必跑：時段、已收、pending、待整併

但 `cmd_resume` 從來沒印過待整併——**文件承諾了、程式沒做**。所以這支不是新規則，
是把既有承諾補上，規則字數增加 0，也沒有「載入 ≠ 遵守」的風險。

## 為什麼是 resume ＋ render 兩處

`resume` 開工跑，觸發點落在**掃站與 set-category 之前**，補整併進來的素材才來得及
跟當輪的 T/C 同一批下完（晚一步就要多花一次 `set-tc` 呼叫，那是 ~$0.11）。
但 agent 不保證每輪都跑 `resume`（0825-2200 那輪就沒跑），所以 `s2_render.py`
收工再喊一次當保險。

🔴 **render 那道只警告、不擋。** 比照清單對帳閘門：這是無人值守的排程，
硬擋會讓整輪產不出交接檔——**漏整併是少收素材，產不出檔是整晚白做**。

## 判準為什麼用 mtime 而不是檔名日期

檔名格式是外部交件端定的（`0825-ENEX.txt`／`0825-側錄候選_2237.txt`／
`0825-ABC-pairs.txt` 都在同一夾），拿檔名解日期等於把外部格式變成我方的依賴。
mtime 不受檔名影響，而且晚班跨夜時「今天」有兩個日期，檔名判斷還要處理跨日。
"""
import os
from datetime import datetime

BASE = r"G:\我的雲端硬碟\Claude共用\自動掃帶系統"
PEND = os.path.join(BASE, "_待整併")
DONE = "已入庫_"          # `s2_mark_ingested.py --apply` 標上的前綴


def pending_files(hours=24, pend_dir=None):
    """回傳 [(檔名, mtime, 位元組)]，只收「沒有 已入庫_ 前綴」且近 `hours` 小時內動過的。

    ⚠️ 中間產物（`-pairs.txt`／`-entries.json`／`-state.json`）也會列進來——
    那是刻意的：它們出現的當下，那批素材本來就還在整併途中。
    """
    d = pend_dir or PEND
    try:
        names = os.listdir(d)
    except OSError:
        return []                      # 雲端硬碟沒掛載就當沒事，⛔ 不要讓它擋住整輪
    cut = datetime.now().timestamp() - hours * 3600
    out = []
    for n in names:
        if n.startswith(DONE) or n.startswith("~$") or n.startswith("."):
            continue
        p = os.path.join(d, n)
        try:
            st = os.stat(p)
        except OSError:
            continue
        if not os.path.isfile(p) or st.st_mtime < cut:
            continue
        out.append((n, datetime.fromtimestamp(st.st_mtime), st.st_size))
    return sorted(out, key=lambda x: x[1])


def warn(hours=24, where="", pend_dir=None):
    """印出待整併提醒；回傳筆數（0 ＝ 沒東西，這時什麼都不印）。"""
    rows = pending_files(hours, pend_dir)
    if not rows:
        return 0
    print(f"⚠️ `_待整併/` 有 {len(rows)} 份還沒標記入庫的交件檔"
          f"（近 {hours} 小時內動過）：")
    for n, ts, sz in rows:
        print(f"   {ts:%m-%d %H:%M}  {n}  ({sz:,} bytes)")
    if where == "render":
        # 收工才看到＝補整併會發生在 render 之後，那份 txt 就少了這批。
        print("   🔴 這是**收工前的最後一道**：現在補整併，補完要**重跑 render**。")
    print("   整併方式看來源：ABC／ENEX 走 `s2_platform_merge.py`；"
          "側錄候選走 `s2_state.py add-side`；韓聯社／CNA 照 `common/17` 交件端判 T/C。")
    print("   ⛔ 整併完才跑 `s2_mark_ingested.py --apply` 改名——"
          "它會先逐筆比對狀態檔，缺一筆就整份不動。")
    return len(rows)
