#!/usr/bin/env python3
"""S2 掃帶三站批次整備工具（②，2026-08-12）。

🧪 v2 測試版（2026-09-22，未正式套用）：`build` 內建機械 autofix（見
`_apply_mechanical_autofix`），把 `autofix-tags` 的兩種機械修補（補
(BITE)括號、NS站補SOT字樣）直接搬進 `build`（含 `--dry-run`）跑 lint
之前自動套用，不再只靠 `from-raw` 印建議文字指望 agent 主動去跑
`autofix-tags`。只改記憶體中的 entry_text（不寫回 entries.json 原始
檔），並在 stderr 印出修補筆數與 ID（不悄悄改稿）。經Codex sol覆核方向
（同意：build落點對、不要靜默、不需依賴--skeleton）。測試通過前不要
覆蓋回 `s2_batch_prep.py`。

三站（NS／AP／RT）都要走同一組流程：先看 raw 抽取結果判斷要不要收、
sb_count／has_sot／footage_type 這些機械欄位，再把 agent 自己寫的 `entry`
（中文三段式摘要，這是編輯判斷，不可能機械生成）併回去、湊成能直接
`add-batch` 的 batch.json。0730 那輪這五步被拆成 15 次臨時 `python -c`
（含兩次純重複），這支腳本把「機械的部分」收成兩個子指令：

    dump   讀 raw.json，印出（或存成 .txt）每則的關鍵欄位，取代
           手打 print 確認格式那幾步。**只印機械欄位，不判斷、不寫 entry**。
    build  讀 raw.json ＋ agent 自己寫的 entries.json（{id: entry 文字}），
           機械併出最終 batch.json：id／source／checkpoint／status／
           站別專屬欄位（sb_count／has_sot／footage_type）／entry／src_text。

⚠️ **`entry` 欄位（中文三段式摘要、BITE 判斷、分類措辭）永遠是 agent 自己
寫**，這支腳本不生成、不翻譯、不判斷 BITE——那是編輯判斷，機械做不到。
腳本只負責「把 agent 已經判斷完的結果，跟 raw 裡的機械欄位對好、湊成
add-batch 吃得下的格式」，正是原本 15 次臨時 python 裡唯一真正機械、
可以收成固定流程的那部分。

用法：
    python s2_batch_prep.py dump --site ap --raw ap_batch_0730_raw.json
    python s2_batch_prep.py dump --site ap --raw ap_batch_0730_raw.json --out ap_dump_0730.txt

    python s2_batch_prep.py build --site ap --raw ap_batch_0730_raw.json \\
        --entries ap_entries_0730.json --checkpoint 0812-0730 \\
        --out ap_batch_0730.json

entries.json 格式：`{"AP4677906": "◆ AP4677906 (…) …"}`；
值也可以是 `{"entry": "…", "status": "pending"}` 這種物件，
用來覆蓋機械推導出的 status（例如初稿還沒補正式稿）。物件還可以帶
`category`（`"大分類/中主題[/小分題]"`）／`tc`（`"T1,T2/C1,C2"`）兩鍵，
`build` 會原樣帶進 batch row，交給 `add-batch` 一次入庫＋分類＋標 T/C
（2026-09-07 T12）。

三站欄位不統一，per-site adapter 寫死在 SITE_SPEC 裡；raw.json 的欄位名
以 13c 規則檔為準（NS: id/ft/dur_ms/desc/script/skip；
AP: id/head/cap/script/role/sb_count/has_sot/prelim；
RT: code/head/story/sb_count/early）。

── raw 檢查工具層（③，2026-08-13）──────────────────────────
掃帶 agent 每輪要反覆檢查 scratch 目錄裡的 raw json（站方清單／詳情／
batch 檔），實測發現三站清單原始檔各包一層不同的站方外殼：
    AP 清單：dict，實際陣列在 `Items` 鍵下（AP Newsroom API 原生回應）。
    RT 清單：dict，實際陣列在 `items` 鍵下（`{boxFound,count,items}`）。
    NS 清單：常常根本不是 JSON，是 `id|日期` 逐行純文字（.json 副檔名誤導）。
    已抽取的 detail／batch 檔則多半已經是裸陣列，不必卸殼。
這三個子指令把「先搞清楚這份檔案的殼長什麼樣」跟「從一堆欄位裡挑出要看的
那幾筆」收成固定流程，取代逐輪用 Read 整檔／PowerShell 切片／`python -c`
即興重寫。

    unwrap  <檔> [--out 檔]
        自動偵測外殼（Items／items／裸陣列／NS 純文字清單）並卸成規範化
        的裸陣列，寫回同目錄、檔名加 `_unwrapped`（或用 --out 指定）。
        偵測不出已知殼型時，回報實際看到的頂層型別／鍵，不靜默假裝成功。

    inspect <檔> [--ids A,B | --ids A B] [--fields f1,f2] [--limit N] [--index i]
        讀取（會自動卸殼，不必先跑 unwrap）並精準印出指定項目／欄位。
        不給 --ids/--index/--fields 時預設印摘要：筆數＋每筆 id＋標題行。
        🔴 **`--ids` 請一次帶多則**（`--ids A,B,C,…` 或 `--ids A B C …`）。全文總長吃得下
        28,000 字元就**整批印全文**；塞不下才退回 200 字元預覽，並明講、
        附上前 N 筆的分批指令。一次只查一則跟一次查 20 則**成本一樣**
        （每次呼叫都要重付整個 context ≈ $0.089），所以逐則翻是純浪費。

    search  <檔> --contains 關鍵字 [--field script|story|head|all]
        列出命中項的 id＋命中欄位裡關鍵字前後片段。

    python s2_batch_prep.py unwrap _ap_list_1000.json
    python s2_batch_prep.py inspect _rt_batch_1000.json --limit 5
    python s2_batch_prep.py inspect ap_detail_0430.json --ids AP4678110 --fields head,script
    python s2_batch_prep.py search rt_raw_1600.json --contains "Milei" --field all

── 稽核快照與比對（A2，2026-08-17）─────────────────────────

    snapshot <檔> [--site ns|ap|rt] [--checkpoint 0817-1600] [--out 檔]
        把 raw 壓成純文字快照（標頭記殼型／筆數，之後每行 `id\t標題`），
        供事後對帳比對，不必重開瀏覽器重抓。不給 --out 就用 --checkpoint
        組 `_audit_{site}_{HHMM}.txt`。**已存在的快照一律不覆寫**——
        覆寫等於靜默銷毀稽核依據。

    compare --raw <raw檔> --batch <batch檔> [--site ns|ap|rt] [--require 欄位,…]
        只印差異：raw 有 batch 沒有的 id、batch 有 raw 沒有的 id、
        batch 內重複 id、batch 缺欄位（預設查
        id/source/checkpoint/status/entry/src_text）。乾淨就一行「無差異」。
        在 `add-batch` 之前跑，一次擋掉漏收與整批漏帶 src_text 兩種坑。

    python s2_batch_prep.py snapshot _rt_list_1600.json --site rt --checkpoint 0817-1600
    python s2_batch_prep.py compare --raw _rt_list_1600.json --batch rt_batch_1600.json --site rt

── 去重比對（D9 第一步，2026-08-17）────────────────────────

    dedup-check <檔> --ids A,B[,C…] [--site ns|ap|rt] [--fields script,desc,…]
        兩則以上的指定欄位逐字比對，回答「是不是同一則的不同版本」。
        四種判定分開講，不混為一談：
            ✓ 逐字相同
            ≈ 只差空白／換行
            ≈ 只差 HTML 標記／空白（NS 的 script 夾 <p>／<b>）
            ✗ 不同——並指出剝掉標記後第幾字起不同、印出兩邊該處前後文
        **只回答機械問題。要不要當重複、留哪一則，是編輯判斷，這裡不做。**
        id 打錯／找不到／欄位不存在一律明確失敗中止，不會只比得出來的那幾則
        ——否則「打錯 id」跟「兩則不同」看起來會一樣。
        AP 清單檔是 ES 形狀，會自動看穿 `_source` 並用 `AP<editorialid>`
        當 id（跟 state 對得起來），不是頂層的 `_id` 雜湊。

    python s2_batch_prep.py dedup-check ns_full_2200.json --site ns --ids EN-32MO,EN-31MO
    python s2_batch_prep.py dedup-check ap_list_2200.json --site ap --ids AP5467677,AP5467678 --fields title,headline
"""
import argparse
import copy
import datetime
import glob
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2_state  # noqa: E402  from-raw 讀狀態檔（唯讀，D12 已在庫標記）
import s2_pretag as pretag  # noqa: E402  機械 T/C 建議＋(BITE)建議，見 A31
import s2_patch_file as patch_file  # noqa: E402  A43 共用 patch schema／SHA／atomic write
from s2_material_schema import (  # noqa: E402
    RawLoadResult,
    merge_concat_metadata,
    select_payload_key,
    serialize_raw_result,
    validate_src_text,
)

# Windows 主控台常是 cp950，print() 中文欄位（entry／script 原文）會直接炸掉。
# 這不影響 --out 落檔（那條路本來就明寫 UTF-8），只補救不帶 --out 直接印到終端機的情境。
#
# 🔴 2026-08-31 改（全流程 locale 編碼稽核）：原本用 `io.TextIOWrapper` 包一層，
# 那正是 WP1（2026-08-03）記過的寫法——包第二層時其中一個 wrapper 被回收會關掉
# 底層 buffer，整支腳本以 "I/O operation on closed file" 掛掉。本檔目前沒有 import
# 其他 s2 模組所以還沒踩到，但這是最常被呼叫的工具（inspect 每輪 25–34 次），
# 哪天有人加一行 `import s2_state` 就會炸。統一改成 repo 其餘 20 支在用的
# `reconfigure` 寫法，順便補 `errors="replace"`（外電原文偶爾夾代理字元）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # py<3.7
        pass

# src_text 是「瘦身後的站方原文」留存用（13c 規則：只准站方原文，不准判斷／說明）。
# 跟正文擷取（script 正文取前 4,000 字元）用同一個上限，避免落檔無限長。
SRC_TEXT_LIMIT = 4000


# RT 站方稿的引言區段結構標記，跟 s2_state.sb_applicable() 用同一組判準
# （只認結構標記如 `SHOTLIST:`／`(SOUNDBITE`，不認裸字——RT4131 教訓：裸字比對
# 會被 agent 自己寫進 src_text 的中文說明騙倒）。SUPERS 是 CNN/NS 側常見的同類欄位，
# 一併收，行為對 NS/AP 沒有 SOUNDBITE 段的稿子不影響（下面找不到就直接走原本截斷）。
SOUNDBITE_RE = re.compile(r"\(\s*SOUNDBITE|SOUNDBITE\s*:|SUPERS\s*:", re.IGNORECASE)

# 硬保留的頭段長度：逐字引言區段太靠前面時直接原樣收（走 plain cut 那條路即可），
# 只有「頭段還沒截到就會先把引言砍掉」時才切換成保留策略。
HEAD_KEEP = 500

# `inspect --fields` 一次能印多少字元的全文預算（T9，2026-08-25）。
# 沿用 R15 的 `SAFE_BUDGET`＝28,000 同一個數字：Read 結果約 30,000 字元會**靜默**
# 截斷，超過就等於白花一次呼叫。
INSPECT_TEXT_BUDGET = 28000

# 塞不下預算時每個欄位的預覽長度（原本的固定行為，現在只在超預算時才走）。
INSPECT_PREVIEW_CHARS = 200


def _lint_row(entry_text, row):
    """§四（R31/T12）：`build` 出口跑一次跟 `add-batch` 入庫時**同一套**共用
    lint——直接呼叫 `s2_state.fmt_issues`／`pretag.lint` 這兩個既有純函式，
    不複製規則、不另立一份會漂移的判準。呼叫參數對齊 `s2_state.cmd_add_batch`
    實際呼叫 `pretag.lint()` 那一行（含 `source`／`duration_ms`／`src_text`），
    只是這裡拿的是 build 當下手上的 row 欄位，不是 add-batch 那邊算好的 `sb`
    （那邊會依 `sb_applicable()` 把「數不出來」轉成 None，build 沒有原始
    src_text 可判，直接傳 row 既有的 sb_count／footage_type／duration_ms，兩邊在多數情況
    結果一致，差異只在 build 這關可能多幾則「數不出來」也照樣被當數字檢查——
    這支只警告不擋，多印幾行提示不算壞事）。

    ⚠️ **白名單格式類原因達門檻才擋，其餘維持只警告**——跟 `add-batch` 寫入時
    的既有原則相同；檢查本身壞掉也不能拖累 build（外層已包 try/except）。
    """
    msgs = list(s2_state.fmt_issues(entry_text))
    try:
        msgs += list(pretag.lint(entry_text, sb_count=row.get('sb_count'),
                                  footage_type=row.get('footage_type'),
                                  tc=row.get('tc'),
                                  duration_ms=row.get('duration_ms'),
                                  src_text=row.get('src_text'),
                                  source=row.get('source')))
    except Exception:
        pass
    return msgs


HARD_GATE_THRESHOLD = 5

# 🆕 2026-09-22（0922-1700輪返工追查）：`FMT_OPERATIONAL_NOTE`（agent 內部備註如
# 「完整引言待補」洩漏進成品）不是格式風格細節，是**絕對不該出現**的內容——出現
# 1 則就已經是錯，不該等累積到 5 則才擋。0922-1700 那輪正是因為單次 add-batch／
# update-entry 呼叫每次都零星 1-4 則、始終沒撞到全站門檻，全天下來悄悄累積成
# 120 則，直到收工 render 才被 `s2_validate.check()` 整批抓到，逼出一輪大返工
# （詳見該輪事後分析）。其餘白名單原因維持 5 則門檻（真的是格式風格細節，
# 1-4 則容忍換取不中斷整輪掃帶）。
HARD_GATE_THRESHOLD_OVERRIDES = {
    'FMT_OPERATIONAL_NOTE': 1,
}

# 白名單：僅限確認為機械格式類別的 reason_code，達到門檻（>=5，見上方 OVERRIDES 例外）
# 時觸發硬閘擋下。內容／語意／啟發式判斷（如引言翻譯、事實判斷、選材適當性、摘要字數）
# 嚴格排除於白名單外，維持只警告不擋
HARD_GATE_REASONS = {
    'FMT_FIRST_NOTE_BITE': '第一備註寫了 BITE',
    'FMT_MISSING_FOOTAGE_SEG': '缺 ▎畫面： 段',
    'FMT_BITE_TAG_WITHOUT_SEG': '有 (BITE) 但缺 ▎BITE： 段',
    'FMT_BITE_SEG_WITHOUT_TAG': '有 ▎BITE： 但缺 (BITE) 第二括號',
    'FMT_BITE_CONFLICT': '(BITE) 與 無BITE 矛盾',
    'FMT_NO_ENDING': '結尾既非 無BITE 也無 BITE： 段',
    'FMT_TRAILING_CONTENT': '行尾有多餘內容',
    'FMT_MISSING_SUMMARY_DELIM': '摘要前缺 ▎ 標記',
    'FMT_NOTE_FILE_USAGE': '備註用 FILE/檔案（應為 資料畫面）',
    'FMT_SECOND_PAREN_NOT_BITE': '第二括號不是 (BITE)',
    'FMT_CONTAINS_GMT': '素材行出現 GMT',
    'FMT_OPERATIONAL_NOTE': '操作/狀態備註寫進素材行',
    'FMT_BITE_NO_SPEAKER': '▎BITE：無講者',
    'FMT_WRAP_WITHOUT_NOTE': '出現 WRAP 但備註未標 整理包',
    'FMT_PKG_DONUT_NEED_SOT': 'PKG/DONUT且時長>1分鐘備註漏標SOT',
}


def classify_warning_reason(reason):
    """將警告原因文字分類為穩定的 reason_code。
    回傳 (reason_code, is_hard_gate, display_name)。
    若為白名單機械格式，is_hard_gate=True；內容/語意/未知警告 is_hard_gate=False。
    """
    r = (reason or '').strip()
    if r in HARD_GATE_REASONS:
        return r, True, HARD_GATE_REASONS[r]

    # 機械格式白名單匹配
    if '第一備註寫了 BITE' in r:
        return 'FMT_FIRST_NOTE_BITE', True, HARD_GATE_REASONS['FMT_FIRST_NOTE_BITE']
    if '缺 ▎畫面： 段' in r or '缺 ▎畫面:' in r:
        return 'FMT_MISSING_FOOTAGE_SEG', True, HARD_GATE_REASONS['FMT_MISSING_FOOTAGE_SEG']
    if '有 (BITE) 但缺 ▎BITE： 段' in r or '標了 (BITE) 但沒有 ▎BITE： 段' in r:
        return 'FMT_BITE_TAG_WITHOUT_SEG', True, HARD_GATE_REASONS['FMT_BITE_TAG_WITHOUT_SEG']
    if '有 ▎BITE： 但缺 (BITE) 第二括號' in r or '有 ▎BITE: 但缺 (BITE) 第二括號' in r:
        return 'FMT_BITE_SEG_WITHOUT_TAG', True, HARD_GATE_REASONS['FMT_BITE_SEG_WITHOUT_TAG']
    if '(BITE) 與 無BITE 矛盾' in r:
        return 'FMT_BITE_CONFLICT', True, HARD_GATE_REASONS['FMT_BITE_CONFLICT']
    if '結尾既非 無BITE 也無 BITE： 段' in r or '結尾既非 無BITE 也無 BITE:' in r:
        return 'FMT_NO_ENDING', True, HARD_GATE_REASONS['FMT_NO_ENDING']
    if '行尾有多餘內容' in r:
        return 'FMT_TRAILING_CONTENT', True, HARD_GATE_REASONS['FMT_TRAILING_CONTENT']
    if '摘要前缺 ▎ 標記' in r:
        return 'FMT_MISSING_SUMMARY_DELIM', True, HARD_GATE_REASONS['FMT_MISSING_SUMMARY_DELIM']
    if '備註用 FILE/檔案' in r:
        return 'FMT_NOTE_FILE_USAGE', True, HARD_GATE_REASONS['FMT_NOTE_FILE_USAGE']
    if r.startswith('第二括號不是 (BITE)'):
        return 'FMT_SECOND_PAREN_NOT_BITE', True, HARD_GATE_REASONS['FMT_SECOND_PAREN_NOT_BITE']
    if '素材行出現 GMT' in r:
        return 'FMT_CONTAINS_GMT', True, HARD_GATE_REASONS['FMT_CONTAINS_GMT']
    if '操作/狀態備註寫進素材行' in r or '操作備註寫進素材行' in r:
        return 'FMT_OPERATIONAL_NOTE', True, HARD_GATE_REASONS['FMT_OPERATIONAL_NOTE']
    if '▎BITE：無講者' in r or '▎BITE:無講者' in r:
        return 'FMT_BITE_NO_SPEAKER', True, HARD_GATE_REASONS['FMT_BITE_NO_SPEAKER']
    if '出現 WRAP 但備註未標 整理包' in r:
        return 'FMT_WRAP_WITHOUT_NOTE', True, HARD_GATE_REASONS['FMT_WRAP_WITHOUT_NOTE']
    if 'PKG/DONUT且時長>1分鐘' in r:
        return 'FMT_PKG_DONUT_NEED_SOT', True, HARD_GATE_REASONS['FMT_PKG_DONUT_NEED_SOT']

    # 內容／語意／啟發式判斷類（非白名單，不套硬閘）
    if 'BITE 引言疑似未翻譯成中文' in r:
        return 'SEM_BITE_UNTRANSLATED', False, 'BITE 引言疑似未翻譯成中文'
    if '超過 150 字' in r or '超過150字' in r:
        return 'SEM_SUMMARY_TOO_LONG', False, '摘要超過 150 字上限'
    if '個 SOUNDBITE 卻標「無BITE」' in r:
        return 'SEM_POSSIBLE_MISSING_BITE', False, '稿內有 SOUNDBITE 卻標無BITE'
    if '段 inline SOT 卻標「無BITE」' in r:
        return 'SEM_POSSIBLE_MISSING_INLINE_SOT', False, '全文有 inline SOT 卻標無BITE'
    if '通常必有訪問聲音卻標「無BITE」' in r:
        return 'SEM_POSSIBLE_MISSING_FT_BITE', False, 'footageType 通常必有訪問卻標無BITE'
    if '依 R19 不應標 🔖' in r:
        return 'SEM_INVALID_BOOKMARK', False, '受訪連線類畫面不應標 🔖'
    if '機動 T active' in r:
        return 'SEM_SPECIAL_T_SUGGESTION', False, '機動 T 建議'

    # 其他未知警告：預設為非硬閘類
    return 'WARN_OTHER', False, r


def collect_build_lint_reasons(warnings, site=None, threshold=HARD_GATE_THRESHOLD):
    """統計警告清單的原因分布，回傳 (grouped_reasons, hard_gate_reasons)。
    grouped_reasons: dict of {code: {'code': code, 'name': name, 'count': int,
                                      'is_hard_gate': bool, 'site': str, 'items': [id, ...]}}
    hard_gate_reasons: list of dict（僅包含 is_hard_gate 為 True 且 count >= threshold 的項目）
    """
    site_label = (site or '該站').upper()
    grouped = {}
    for warning in warnings or []:
        item_id, sep, reason = warning.partition(': ')
        raw_reason = reason if sep else warning
        code, is_hard_gate, name = classify_warning_reason(raw_reason)
        if code not in grouped:
            grouped[code] = {
                'code': code,
                'reason_code': code,
                'name': name,
                'count': 0,
                'is_hard_gate': is_hard_gate,
                'site': site_label,
                'items': [],
            }
        grouped[code]['count'] += 1
        if item_id:
            grouped[code]['items'].append(item_id)

    hard_gate_reasons = [
        info for info in grouped.values()
        if info['is_hard_gate']
        and info['count'] >= HARD_GATE_THRESHOLD_OVERRIDES.get(info['code'], threshold)
    ]
    return grouped, hard_gate_reasons


def _print_build_lint_warnings(warnings, site=None):
    """印一份精簡的『ID: 原因』警告清單，長度受 `INSPECT_TEXT_BUDGET` 封頂——
    跟 `inspect --fields` 同一個 28,000 字元預算（T9），避免這份警告本身
    塞爆 Bash 工具回傳的靜默截斷線。只印到 stderr，不影響 stdout／輸出檔。"""
    if not warnings:
        return
    header = (f'⚠️ 前置格式／lint 警告 {len(warnings)} 項（白名單格式類原因達門檻才擋，'
              f'其餘維持只警告、不改 entry；建議送 add-batch 之前先修，比事後 update-entry 便宜）：')
    lines = [header]
    site_label = (site or '該站').upper()
    grouped, _ = collect_build_lint_reasons(warnings, site=site_label)
    summaries = []
    for info in grouped.values():
        if info['count'] < HARD_GATE_THRESHOLD_OVERRIDES.get(info['code'], HARD_GATE_THRESHOLD):
            continue
        if info['count'] < HARD_GATE_THRESHOLD:
            summaries.append(
                f'⚠️ 上面 {info["count"]} 則都是 {site_label} 的「{info["name"]}」同類問題，'
                f'請用 rewrite-entry 精準修補 gate lock 列出的 ID')
        else:
            summaries.append(
                f'⚠️ 上面 {info["count"]} 則都是 {site_label} 的「{info["name"]}」同類問題，'
                f'請先累積到 rewrite-entry --patch-file，再一次 apply（見下方硬閘指令）')
    total_len = len(header) + 1
    reserved = sum(len(summary) + 1 for summary in summaries)
    warning_budget = max(total_len, INSPECT_TEXT_BUDGET - reserved)
    shown = 0
    for w in warnings:
        ln = '  ' + w
        if total_len + len(ln) + 1 > warning_budget:
            break
        lines.append(ln)
        total_len += len(ln) + 1
        shown += 1
    if shown < len(warnings):
        lines.append(f'…另 {len(warnings) - shown} 項略（總長度受 '
                     f'{INSPECT_TEXT_BUDGET:,} 字元預算限制，非全部截斷）')
    lines.extend(summaries)
    print('\n'.join(lines), file=sys.stderr)


GATE_LOCK_SUFFIX = '_gate_lock.json'


def _gate_lock_path(entries_path, site_label):
    """gate lock 跟 entries.json 放同一個目錄，檔名 `<站別小寫>_gate_lock.json`。"""
    d = os.path.dirname(os.path.abspath(entries_path))
    return os.path.join(d, f'{site_label.lower()}{GATE_LOCK_SUFFIX}')


def _write_gate_lock(entries_path, site_label, hard_gate_reasons, dry_run, lint_rows=None):
    """硬閘觸發時落一份 lock 標記檔，供 PreToolUse hook（s2_gate_guard.py）
    技術性擋掉對同一 entries.json 的 Edit——不只是印訊息建議。"""
    if not entries_path:
        return
    lock = {
        'site': site_label,
        'entries_path': os.path.abspath(entries_path).replace('\\', '/'),
        'reasons': [
            {'code': r['reason_code'], 'name': r['name'], 'count': r['count'],
             'items': list(dict.fromkeys(r.get('items') or []))}
            for r in hard_gate_reasons
        ],
        'triggered_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'dry_run': bool(dry_run),
    }
    # rewrite-entry 只需重算「硬閘白名單」；其中唯一依賴 entry 以外欄位的規則
    # 是 NS PKG/DONUT 的 footage_type/duration_ms/source。刻意不存 src_text，
    # 避免 gate lock 複製整批全文；其餘語意警告不參與清鎖判定。
    lock['lint_contexts'] = {
        str(row.get('id')): {
            key: row.get(key) for key in ('source', 'footage_type', 'duration_ms')
            if row.get(key) is not None
        }
        for row in (lint_rows or []) if isinstance(row, dict) and row.get('id') is not None
    }
    try:
        with open(_gate_lock_path(entries_path, site_label), 'w', encoding='utf-8') as f:
            json.dump(lock, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        # lock 檔寫不出去不能拖累硬閘本身（硬閘攔截仍照常 exit 2）——
        # 只是這一次 Edit 技術鎖會失效，退化回純文字警告。
        print(f'⚠️ gate lock 寫入失敗（不影響硬閘攔截，但 Edit 技術鎖這次不會生效）：{exc}',
              file=sys.stderr)


def _clear_gate_lock(entries_path, site_label):
    """清除時機②：重跑 build/--dry-run 確認該站 reason code 計數已降到 0。
    （清除時機①「一次完整 Write 發生」由 s2_gate_guard.py 的 PostToolUse 處理。）"""
    if not entries_path:
        return
    path = _gate_lock_path(entries_path, site_label)
    try:
        if os.path.exists(path):
            os.remove(path)
            print(f'✅ {site_label} gate lock 已清除（reason code 計數已降到 0）：{path}',
                  file=sys.stderr)
    except OSError as exc:
        print(f'⚠️ gate lock 清除失敗：{exc}', file=sys.stderr)


def _remaining_active_lock_reasons(lock, grouped):
    """Return positive counts only for reason codes that originally triggered ``lock``.

    A different hard-gate-class warning below its own threshold must never inherit an
    existing lock.  It stays a warning until it independently reaches its threshold.
    """
    original_codes = {
        str(reason.get('code')) for reason in (lock or {}).get('reasons', [])
        if isinstance(reason, dict) and reason.get('code')
    }
    remaining = []
    for code in original_codes:
        info = (grouped or {}).get(code)
        if not isinstance(info, dict) or not info.get('is_hard_gate') or info.get('count', 0) <= 0:
            continue
        remaining.append(info)
    return sorted(remaining, key=lambda info: info.get('reason_code') or info.get('code') or '')


def _update_active_lock(lock_path, lock, remaining):
    lock['reasons'] = [
        {'code': r.get('reason_code') or r.get('code'), 'name': r['name'],
         'count': r['count'], 'items': list(dict.fromkeys(r.get('items') or []))}
        for r in remaining
    ]
    lock['last_checked_at'] = datetime.datetime.now().isoformat(timespec='seconds')
    _atomic_write_json(lock_path, lock)


def cmd_gate_clear(args):
    """逃生路徑：手動清除 gate lock，避免流程死鎖（方向1第4點）。"""
    site_label = args.site.upper()
    path = _gate_lock_path(args.entries, site_label)
    if not os.path.exists(path):
        print(f'ℹ️ 沒有找到 {site_label} 的 gate lock（{path}），無需清除。', file=sys.stderr)
        return
    os.remove(path)
    print(f'✅ 已手動清除 {site_label} gate lock：{path}', file=sys.stderr)


def _rewrite_entry_error(message):
    print(f'⛔ rewrite-entry 拒絕執行：{message}', file=sys.stderr)
    sys.exit(2)


def _parse_rewrite_sets(raw_sets):
    parsed = {}
    for raw in raw_sets or []:
        item_id, sep, value = str(raw).partition('=')
        item_id = item_id.strip()
        if not sep or not item_id or not value:
            _rewrite_entry_error('--set 必須是 `<ID>=<新 entry JSON 或純文字>`。')
        if item_id in parsed:
            _rewrite_entry_error(f'--set 重複指定 ID：{item_id}')
        try:
            payload = json.loads(value)
        except ValueError:
            payload = value
        if not isinstance(payload, (str, dict)):
            _rewrite_entry_error(f'{item_id} 的新內容必須是 JSON object 或純文字。')
        parsed[item_id] = payload
    return parsed


def _hard_gate_reasons_for_entries(entries, site_label, lint_contexts):
    """以 build 的 `_lint_row`＋`collect_build_lint_reasons` 重算白名單原因。"""
    warnings = []
    for item_id, payload in entries.items():
        if str(item_id).startswith('_'):
            continue
        entry_text, _category, _tc, _status, _converted = parse_draft_entry(item_id, payload)
        context = dict((lint_contexts or {}).get(str(item_id)) or {})
        context['source'] = context.get('source') or site_label
        for reason in _lint_row(entry_text, context):
            warnings.append(f'{item_id}: {reason}')
    grouped, _triggered = collect_build_lint_reasons(warnings, site=site_label)
    return [info for info in grouped.values()
            if info['is_hard_gate'] and info['count'] > 0]


# 自由模式（無 gate lock）可改的欄位白名單。
# NS/AP/RT 的 entries.json 草稿契約是 `{id: {entry, category, tc}}`（13c 步驟3／
# 13c2 §「agent 只寫 {id:{entry,category,tc}}」），三個都是人工判斷欄位；機械欄位
# （id／source／checkpoint／src_text／footage_type…）根本不在草稿裡，是 `build`
# 從骨架或 raw 併進去的，所以這裡不需要「禁止清單」，只要正面白名單即可。
# 刻意**不收** `status`（骨架已機械推導，草稿階段改它等於繞過 status_of）與
# `raw_entry`（那是狀態檔欄位、寫進草稿是既有筆誤來源，見 parse_draft_entry）。
_REWRITE_FREE_FIELDS = ('entry', 'category', 'tc')


def _parse_rewrite_sets_free(raw_sets):
    """自由模式的 `--set` 解析：回傳 {ID: {欄位: 新值}}（局部 patch，不是整份取代）。

    - `<ID>=<純文字>` → 視為 `{"entry": "<純文字>"}`（最常見的「只想改素材行」情境）。
    - `<ID>={"category":"…"}` → JSON object，鍵必須全在 `_REWRITE_FREE_FIELDS` 內。
    跟 lock 模式的 `_parse_rewrite_sets`（整份取代語意）刻意分開兩支，避免改到
    既有已上線路徑的行為。
    """
    parsed = {}
    for raw in raw_sets or []:
        item_id, sep, value = str(raw).partition('=')
        item_id = item_id.strip()
        if not sep or not item_id or not value:
            _rewrite_entry_error('--set 必須是 `<ID>=<新 entry 純文字>` 或 '
                                 '`<ID>={"entry":"…","category":"…","tc":"…"}`。')
        if item_id in parsed:
            _rewrite_entry_error(f'--set 重複指定 ID：{item_id}')
        try:
            payload = json.loads(value)
        except ValueError:
            payload = value
        if isinstance(payload, str):
            payload = {'entry': payload}
        elif isinstance(payload, dict):
            if not payload:
                _rewrite_entry_error(f'{item_id} 的新內容是空 object，沒有東西可改。')
            unknown = sorted(set(payload) - set(_REWRITE_FREE_FIELDS))
            if unknown:
                _rewrite_entry_error(
                    f'{item_id} 含不可修改欄位：{", ".join(unknown)}；自由模式只允許 '
                    f'{", ".join(_REWRITE_FREE_FIELDS)}（機械欄位由 build 從骨架／raw 產生，'
                    '不在草稿裡改）。')
        else:
            _rewrite_entry_error(f'{item_id} 的新內容必須是 JSON object 或純文字。')
        parsed[item_id] = payload
    return parsed


# `_new_topics` 頂層保留鍵的欄位白名單。形狀不是這裡自己定的，取自
# `cmd_build` 的 P1b-2 註解與 `s2_state.py`（`_reject_bare_gated` 的提示訊息、
# `cmd_add_batch` 真正讀的鍵、`_register_topic` 的簽名）：
#   {題名: {"charter": 這題收什麼／不收什麼, "big": 大分類[, "aliases": [別名…]]}}
# `build --skeleton` 把它原樣搬到 batch 頂層的 `new_topics`，`add-batch` 再拿去
# 登記中主題。add-batch 只讀這三個鍵，多寫的鍵一路被丟掉（寫了等於沒寫），
# 所以這裡用正面白名單擋下拼錯的欄位名，不讓它靜默消失。
_NEW_TOPIC_FIELDS = ('charter', 'big', 'aliases')


def _normalize_new_topic_aliases(name, aliases):
    """`--new-topics` 的 aliases 型別檢查，回傳原樣（不代替 add-batch 做切割）。

    `s2_state.cmd_add_batch` 兩種寫法都吃：list（直接用）與逗號／分號分隔的
    字串（它自己 `re.split`）。這裡照收兩種、只確認「不是空的、元素都是非空
    字串」，型別不對就當場拒絕——寫進去 add-batch 那邊會 `aliases = None`
    靜默吃掉，等於別名沒登記到。
    """
    if isinstance(aliases, str):
        if not aliases.strip():
            _rewrite_entry_error(f'--new-topics 的「{name}」aliases 是空字串。')
        return aliases
    if isinstance(aliases, list):
        if not aliases:
            _rewrite_entry_error(f'--new-topics 的「{name}」aliases 是空陣列。')
        if any(not (isinstance(a, str) and a.strip()) for a in aliases):
            _rewrite_entry_error(
                f'--new-topics 的「{name}」aliases 必須是「非空字串」的陣列。')
        return list(aliases)
    _rewrite_entry_error(
        f'--new-topics 的「{name}」aliases 必須是陣列（["別名1","別名2"]）'
        '或逗號分隔字串，不能是其他型別。')


def _parse_new_topics_patch(raw):
    """解析 `--new-topics <JSON字串>`，回傳 {題名: {欄位: 值}} 的逐欄 patch。

    `{}`（空 object）是合法輸入，語意＝「確保 `_new_topics` 這個頂層鍵存在」
    （沒有就建成 `{}`，有就原樣不動）——規則（13c2 §2）要求三站 entries.json
    一律帶這個鍵，而 `s2_gate_guard.py` 也拿它當 entries.json 的內容形狀判準。
    """
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        _rewrite_entry_error(f'--new-topics 必須是合法 JSON：{exc}')
    if not isinstance(payload, dict):
        _rewrite_entry_error(
            '--new-topics 必須是 JSON object：'
            '{"題名":{"charter":"這一題收什麼、不收什麼","big":"大分類"}}。')
    parsed = {}
    for name, spec in payload.items():
        if not isinstance(name, str) or not name.strip():
            _rewrite_entry_error('--new-topics 的題名必須是非空字串。')
        if name.startswith('_'):
            _rewrite_entry_error(f'--new-topics 的題名不可用底線開頭：{name}')
        if not isinstance(spec, dict):
            _rewrite_entry_error(
                f'--new-topics 的「{name}」必須是 object'
                '（{"charter":"…","big":"…"}）；add-batch 對非 object 的值是'
                '靜默跳過，寫進去等於沒登記。')
        if not spec:
            _rewrite_entry_error(f'--new-topics 的「{name}」是空 object，沒有東西可寫。')
        unknown = sorted(set(spec) - set(_NEW_TOPIC_FIELDS))
        if unknown:
            _rewrite_entry_error(
                f'--new-topics 的「{name}」含不支援欄位：{", ".join(unknown)}；'
                f'只允許 {", ".join(_NEW_TOPIC_FIELDS)}（add-batch 只讀這三個，'
                '其餘鍵會被靜默丟掉）。')
        clean = {}
        for field in ('charter', 'big'):
            if field in spec:
                value = spec[field]
                if not isinstance(value, str) or not value.strip():
                    _rewrite_entry_error(
                        f'--new-topics 的「{name}」{field} 必須是非空字串。')
                clean[field] = value
        if 'aliases' in spec:
            clean['aliases'] = _normalize_new_topic_aliases(name, spec['aliases'])
        parsed[name] = clean
    return parsed


def _apply_new_topics_patch(entries, patch, entries_path):
    """把 `--new-topics` 的 patch 併進 entries.json 頂層 `_new_topics`，回傳改到的題名。

    - **逐題、逐欄** merge：只帶 charter 就只換 charter，那一題原本的 big／
      aliases 留著；這樣「補一題的 charter」不必把整顆 spec 重打一次。
      （原值那一題不是 object＝壞資料，這次 patch 既然點名了它就整顆換掉。）
    - 合併**之後**每一題都必須同時有非空 `charter` 與 `big`：`_register_topic`
      對空值是「不覆寫」而不是報錯，放空殼進去會登記出一筆沒 charter 的中主題，
      正是 A10 P1b 要擋的東西。驗證放在合併後，才不會妨礙逐欄補件。
    - 既有 `_new_topics` 不是 object（壞檔）→ 直接拒絕，不靜默重建：那可能是
      agent 寫錯形狀，蓋掉等於銷毀證據。
    """
    current = entries.get('_new_topics')
    if '_new_topics' in entries and not isinstance(current, dict):
        _rewrite_entry_error(
            f'{entries_path} 既有的 `_new_topics` 不是 object'
            f'（是 {type(current).__name__}），不敢靜默覆蓋；'
            '請先用一次 `Write` 整批重寫把它修正。')
    merged = dict(current) if isinstance(current, dict) else {}
    for name, spec in patch.items():
        base = merged.get(name)
        new_spec = dict(base) if isinstance(base, dict) else {}
        new_spec.update(spec)
        missing = [field for field in ('charter', 'big')
                   if not str(new_spec.get(field) or '').strip()]
        if missing:
            _rewrite_entry_error(
                f'--new-topics 的「{name}」合併後仍缺：{"、".join(missing)}；'
                '中主題登記必須同時有 charter（這一題收什麼、不收什麼）與 '
                'big（大分類），少一個 add-batch 會登記出空殼。')
        merged[name] = new_spec
    entries['_new_topics'] = merged
    return sorted(patch)


def _apply_free_patch(existing, patch):
    """把白名單 patch 併進單筆草稿值，回傳新值（不就地改 `existing`）。

    - 原值是 dict → 複製後只覆寫 patch 指定的鍵，其餘（category／tc／status…）原樣保留。
    - 原值是純字串 → 只改 entry 時仍回純字串（維持舊格式草稿的形狀）；
      要一併改 category／tc 才升級成 dict，並把原字串放進 `entry`。
    - 原 dict 用的是 `raw_entry`（既有筆誤形態，`build` 會記憶體內自動轉正）而
      patch 要改 `entry` → 把 `raw_entry` 一起拿掉，否則兩鍵並存會被
      `parse_draft_entry` 當資料衝突 exit 2。
    """
    if isinstance(existing, dict):
        new_value = dict(existing)
        if 'entry' in patch and 'raw_entry' in new_value:
            new_value.pop('raw_entry')
        new_value.update(patch)
        return new_value
    base_text = existing if isinstance(existing, str) else ''
    if set(patch) == {'entry'}:
        return patch['entry']
    new_value = {'entry': base_text}
    new_value.update(patch)
    return new_value


def _hard_gate_counts_for_entries(entries, site_label, lint_contexts):
    """`{reason_code: count}`，只含白名單機械格式類（沿用 build 同一套 lint）。"""
    return {info['reason_code']: info['count']
            for info in _hard_gate_reasons_for_entries(entries, site_label, lint_contexts)}


def _reject_if_lint_regressed(before_counts, after_counts, entries_path):
    """自由模式的落檔前護欄：改出「新的、且已達硬閘門檻」的白名單格式錯誤就拒絕。

    判準＝某 reason code 修改後 **count 比修改前多** 且 **達到該 code 的門檻**
    （`HARD_GATE_THRESHOLD_OVERRIDES` 優先，`FMT_OPERATIONAL_NOTE` 是 1 則）。
    只看「變更後達門檻」而不是「一有變多就擋」，是為了不把「本來就髒、agent
    正在分批修」的檔案鎖死；真正的關卡仍是 `build` 的 `_enforce_build_hard_gate`，
    這裡只是不讓 rewrite-entry 成為繞過它的後門。
    """
    regressed = []
    for code, count in sorted(after_counts.items()):
        threshold = HARD_GATE_THRESHOLD_OVERRIDES.get(code, HARD_GATE_THRESHOLD)
        if count > before_counts.get(code, 0) and count >= threshold:
            regressed.append((code, before_counts.get(code, 0), count, threshold))
    if not regressed:
        return
    lines = [f'這次修改會讓白名單機械格式錯誤達到硬閘門檻，{entries_path} 未被修改：']
    for code, before, after, threshold in regressed:
        name = HARD_GATE_REASONS.get(code, code)
        lines.append(f'  • {code}（{name}）：{before} 則 → {after} 則（門檻 ≥{threshold}）')
    lines.append('  請修正 patch file 內容後重跑 rewrite-entry --patch-file；target 保持未修改。')
    _rewrite_entry_error('\n'.join(lines))


def _lock_owning_entries(entries_path):
    """同目錄掃 `*_gate_lock.json`，回傳「鎖住這份 entries.json」的那把 lock。

    判準跟 hook 端 `s2_gate_guard.py:_find_lock_for_path` 一致（比對 lock 記錄的
    `entries_path`，不看檔名的站別），用來擋掉**帶錯 `--site` 混進自由模式**：
    `rewrite-entry --site ap --entries ns_entries_0430.json` 只會去找
    `ap_gate_lock.json`，找不到就以為沒鎖——那份檔案其實被 `ns_gate_lock.json`
    鎖著，會整個繞過「只准改 lock reason items 列出的 ID」這道限制。
    讀不動的 lock 一律跳過（跟 hook 端同樣 fail-open，不讓壞檔卡死掃帶輪）。
    """
    target = os.path.normcase(os.path.abspath(entries_path)).replace('\\', '/')
    d = os.path.dirname(os.path.abspath(entries_path))
    if not os.path.isdir(d):
        return None
    for lock_path in glob.glob(os.path.join(d, f'*{GATE_LOCK_SUFFIX}')):
        try:
            with open(lock_path, encoding='utf-8') as f:
                lock = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(lock, dict):
            continue
        locked = lock.get('entries_path')
        if locked and os.path.normcase(os.path.abspath(locked)).replace('\\', '/') == target:
            return lock_path, lock
    return None


def _cmd_rewrite_entry_free(args, site_label):
    """自由模式（沒有 active gate lock）：可自行指定 ID 做局部欄位修補。

    2026-09-23（A41 續辦）：`s2_gate_guard.py` 改成 NS/AP/RT entries.json 無條件
    禁止逐筆 Edit 之後，「沒觸發 gate lock 但想微調幾則格式」這個情境必須有一條
    合法管道，否則只剩「整份 Write 重寫」一招——對只想改一兩個字的情況既不精準
    也浪費（0923-0430 輪那 10 次 NS Edit 正是這種微調）。

    與 lock 模式的差異（lock 模式那條路徑一行都沒動）：
      - 不要求 lock 存在、不檢查 ID 是否在 lock 的 reason items 裡。
      - `--set` 是**局部 patch**（只覆寫 entry／category／tc），不是整份取代。
      - 不寫、不清任何 lock；落檔前多一道「不准把 lint 改爛到達門檻」的護欄。

    2026-09-23 追加（0923-1300 輪實測代價）：原本「只能改既有 ID、不准碰
    `_new_topics`」的限制，讓那一輪 agent 只是想在 `ns_entries_1300.json` 加一個
    `_new_topics` 開新中主題，就被逼去重生成整份檔案（70 秒＋數千 output token），
    比那一筆小改動貴得多——鎖定反而變貴。所以自由模式另外開兩條路：
      - `--new-id <ID>`：**明示**這個 ID 是新增的（必須同時出現在 `--id`／`--set`）。
        刻意做成顯式旗標而不是「找不到就當新增」：後者會把 ID 打錯字靜默變成
        一則憑空長出來的素材，夜間無人值守時沒人會發現。有了這個旗標，兩個方向
        的錯都會大聲失敗——沒標卻不存在＝當打錯，標了卻已存在＝當打錯。
        新增與修改既有 ID **可以混在同一次呼叫**（同一批判斷本來就會同時產生
        「補一則」和「改一則」，拆成兩次呼叫只是多一次往返）。
      - `--new-topics <JSON>`：patch entries.json 頂層 `_new_topics` 保留鍵。
        跟 `--id`／`--set` 完全分開的機制（它不是素材則，套 `_apply_free_patch`
        的欄位白名單只會語意錯亂），可以跟新增 ID 同一次用，也可以單獨用
        （不帶任何 `--id`）。
    """
    other_lock = _lock_owning_entries(args.entries)
    if other_lock:
        lock_path, lock = other_lock
        _rewrite_entry_error(
            f'這份 entries.json 其實被 {lock.get("site", "?")} 站的 gate lock 鎖住'
            f'（{lock_path}），但 --site 給的是 {site_label}，站別不一致。'
            f'請改用 `--site {str(lock.get("site", "")).lower()}` 走 lock 模式，'
            '不要用錯站別混進自由模式。')

    raw_new_topics = getattr(args, 'new_topics', None)
    new_topics_patch = (_parse_new_topics_patch(raw_new_topics)
                        if raw_new_topics is not None else None)

    requested_ids = [str(item_id) for item_id in (args.ids or [])]
    if len(requested_ids) != len(set(requested_ids)):
        _rewrite_entry_error('--id 至少給一個且不可重複。')
    if not requested_ids and new_topics_patch is None:
        _rewrite_entry_error(
            '--id 至少給一個且不可重複'
            '（只想補頂層 `_new_topics`、一則素材都不改的話，'
            '改帶 `--new-topics <JSON>`，不用給 --id）。')
    reserved = sorted(item_id for item_id in requested_ids if item_id.startswith('_'))
    if reserved:
        _rewrite_entry_error(
            f'--id 不可指向底線開頭的保留鍵：{", ".join(reserved)}'
            '（`_new_topics` 這類頂層保留鍵不是素材則，請改用 `--new-topics <JSON>`；'
            '其餘底線開頭的鍵一律要用 Write 整批重寫）。')
    updates = _parse_rewrite_sets_free(args.sets)
    if set(requested_ids) != set(updates):
        _rewrite_entry_error('--id 與 --set 指定的 ID 必須完全一致。')

    # `--new-id` 只是「這個 ID 是新增的」這個意圖的標記，不另外帶內容——
    # 內容照舊走 `--set`，所以它必須是 `--id`／`--set` 的子集，
    # 「--id 與 --set 必須完全一致」這個既有不變量也就不用動。
    declared_new = [str(item_id) for item_id in (getattr(args, 'new_ids', None) or [])]
    if len(declared_new) != len(set(declared_new)):
        _rewrite_entry_error('--new-id 不可重複。')
    stray = sorted(set(declared_new) - set(requested_ids))
    if stray:
        _rewrite_entry_error(
            f'--new-id 必須同時出現在 --id／--set：{", ".join(stray)}'
            '（--new-id 只標記「這則是新增的」，內容一樣要用 --set 給）。')

    entries = load_json(args.entries)
    if not isinstance(entries, dict):
        if isinstance(entries, list):
            _rewrite_entry_error(
                '--entries 收到的是 batch/skeleton 陣列，不是 `{id:{entry,...}}` 的 '
                'entries.json。請把 `--entries` 改成 build 的上游 entries 草稿；'
                'batch 產物請回上游修正後重跑 build。')
        _rewrite_entry_error('entries.json 頂層必須是 object。')

    # 兩個方向的「ID 打錯字」都要大聲失敗，不准靜默走進另一種語意。
    collide = sorted(set(declared_new) & set(entries))
    if collide:
        _rewrite_entry_error(
            f'--new-id 指的 ID 其實已經在 entries.json 裡：{", ".join(collide)}。'
            '這通常是 ID 打錯字（想新增卻撞到既有則）；'
            '若真的是要改這幾則既有素材，拿掉 --new-id 再跑一次即可'
            '（拿掉之後就是局部欄位修補，不會整則被蓋掉）。')
    missing = sorted(set(requested_ids) - set(entries) - set(declared_new))
    if missing:
        _rewrite_entry_error(
            f'entries.json 找不到 ID：{", ".join(missing)}。'
            '若確實要**新增**這幾則，請同時帶 `--new-id <ID>` 明示'
            '（新增與修改既有則可以混在同一次呼叫）；'
            '沒帶這個旗標一律當成 ID 打錯，不會靜默生出新則。')

    # 新增則的必要欄位：`entry` 非空。`category`／`tc` 是允許晚點補的
    # （`parse_draft_entry` 兩個都容許 None，`build` 只在有值時才寫進 batch），
    # 但 entry 空的話 `cmd_build` 會把這則丟進 `missing` 整則消失——
    # 那等於「新增了一個看不見的洞」，所以在這裡就擋。
    for item_id in declared_new:
        entry_text = updates[item_id].get('entry')
        if not isinstance(entry_text, str) or not entry_text.strip():
            _rewrite_entry_error(
                f'新增的 {item_id} 沒有非空的 entry：--set 必須給素材行'
                f'（`--set {item_id}=<素材行純文字>`，等同 '
                '{"entry":"…"}；category／tc 可以晚點再補）。'
                'entry 空的話 build 會把這則當「缺素材行」整則丟掉。')

    changed_topics = (_apply_new_topics_patch(entries, new_topics_patch, args.entries)
                      if new_topics_patch is not None else [])

    # 「修改前」的基準要在套用 patch 之前算，否則比不出這次改壞了什麼。
    # （`_new_topics` 在 `_hard_gate_reasons_for_entries` 是被跳過的底線鍵，
    #   上面先併它不影響這裡的基準。）
    before_counts = _hard_gate_counts_for_entries(entries, site_label, {})
    for item_id in requested_ids:
        if item_id in entries:
            entries[item_id] = _apply_free_patch(entries[item_id], updates[item_id])
        else:
            # 新增則一律用 13c 的正規草稿形狀 `{entry[, category, tc]}`，
            # 不沿用 `_apply_free_patch` 對舊格式純字串的相容分支。
            entries[item_id] = dict(updates[item_id])
    # 新增則本身的格式問題也要被硬閘看到——`_hard_gate_counts_for_entries` 是
    # 掃整份 entries，新則寫進 dict 之後自然納入統計，不需要另外開一套。
    after_counts = _hard_gate_counts_for_entries(entries, site_label, {})
    _reject_if_lint_regressed(before_counts, after_counts, args.entries)

    try:
        _atomic_write_json(args.entries, entries)
    except OSError as exc:
        _rewrite_entry_error(f'entries.json 寫入失敗：{exc}')
    patched_ids = [item_id for item_id in requested_ids if item_id not in declared_new]
    summary = []
    if patched_ids:
        summary.append(f'局部修補 {len(patched_ids)} 則（{", ".join(patched_ids)}）')
    if declared_new:
        summary.append(f'新增 {len(declared_new)} 則（{", ".join(declared_new)}）')
    if new_topics_patch is not None:
        summary.append(f'_new_topics 寫入 {len(changed_topics)} 題'
                       + (f'（{"、".join(changed_topics)}）' if changed_topics
                          else '（空殼，只確保這個頂層鍵存在）'))
    print('✅ rewrite-entry（自由模式，無 gate lock）：' + '、'.join(summary),
          file=sys.stderr)
    if declared_new:
        print('ℹ️ 新增的 ID 必須同時存在於 `from-raw` 產的骨架裡——'
              '`build --skeleton` 是照骨架逐列走的，骨架沒有這個 id 就不會出現在 '
              'batch.json（不會報錯，是靜默略過）。新增前請先確認骨架有這一則。',
              file=sys.stderr)
    still = sorted((code, count) for code, count in after_counts.items() if count > 0)
    if still:
        detail = '、'.join(f'{code}（{count}則）' for code, count in still)
        print(f'⚠️ 這份 entries.json 仍有白名單格式警告（未達門檻、不擋落檔）：{detail}',
              file=sys.stderr)
    print('ℹ️ 修補完請重跑 `build --dry-run` 預檢，確認該站 reason code 降到 0 再跑正式 build。',
          file=sys.stderr)


def _load_active_rewrite_lock(entries_path, site_label):
    """Validate and return this site's active lock, or None when no lock exists."""
    lock_path = _gate_lock_path(entries_path, site_label)
    if not os.path.exists(lock_path):
        return None
    try:
        with open(lock_path, encoding='utf-8') as f:
            lock = json.load(f)
    except (OSError, ValueError) as exc:
        _rewrite_entry_error(f'gate lock 無法讀取：{exc}')
    if lock.get('site') != site_label:
        _rewrite_entry_error(f'gate lock 站別是 {lock.get("site")}，不是 {site_label}。')
    locked_entries = os.path.normcase(os.path.abspath(lock.get('entries_path') or ''))
    requested_entries = os.path.normcase(os.path.abspath(entries_path))
    if locked_entries != requested_entries:
        _rewrite_entry_error('gate lock 記錄的 entries_path 與 --entries 不一致。')
    return lock_path, lock


def _cmd_rewrite_entry_patch(args, site_label):
    """Apply patch schema v1 with partial-set semantics in lock and free modes."""
    other_lock = _lock_owning_entries(args.entries)
    if other_lock and str(other_lock[1].get('site') or '') != site_label:
        lock_path, lock = other_lock
        _rewrite_entry_error(
            f'這份 entries.json 其實被 {lock.get("site", "?")} 站的 gate lock 鎖住'
            f'（{lock_path}），但 --site 給的是 {site_label}，站別不一致。')
    try:
        document = patch_file.load_patch(
            args.patch_file,
            expected_site=args.site,
            canonicalize=lambda item_id: str(item_id).strip(),
            allowed_fields=_REWRITE_FREE_FIELDS,
        )
        if not document.changes:
            raise patch_file.PatchFileError(
                'changes 是空陣列；請先填入至少一筆 change 再 apply。')
        patch_file.require_target_sha(args.entries, document.target_sha256)
    except patch_file.PatchFileError as exc:
        _rewrite_entry_error(str(exc))

    entries = load_json(args.entries)
    if not isinstance(entries, dict):
        _rewrite_entry_error('entries.json 頂層必須是 object。')
    requested_ids = [change.canonical_id for change in document.changes]
    reserved = sorted(item_id for item_id in requested_ids if item_id.startswith('_'))
    if reserved:
        _rewrite_entry_error(f'patch change 不可指向底線開頭的保留鍵：{", ".join(reserved)}')
    missing = sorted(set(requested_ids) - set(entries))
    if missing:
        _rewrite_entry_error(f'entries.json 找不到 ID：{", ".join(missing)}')

    lock_info = _load_active_rewrite_lock(args.entries, site_label)
    lint_contexts = {}
    remaining = None
    if lock_info:
        _lock_path, lock = lock_info
        reasons = lock.get('reasons') or []
        try:
            counts = [int(reason.get('count', 0)) for reason in reasons]
        except (TypeError, ValueError):
            _rewrite_entry_error('gate lock 的 reason count 格式不合法；請重跑 build --dry-run。')
        # 舊 --id/--set 路徑在 >=5 項時仍要求整批 Write；file-backed patch 的
        # 目的正是安全承接大量 ID，所以不套該數量上限，改由 SHA＋全批 lint＋
        # 一次 atomic write 保護。lock 的 reason-items 權限邊界仍完整保留。
        allowed_ids = {
            str(item_id) for reason in reasons for item_id in (reason.get('items') or [])
        }
        if not allowed_ids:
            _rewrite_entry_error('gate lock 沒有 reason items；請先重跑 build --dry-run 更新 lock。')
        unauthorized = sorted(set(requested_ids) - allowed_ids)
        if unauthorized:
            _rewrite_entry_error(
                f'ID 不在 gate lock 的 reason items 清單：{", ".join(unauthorized)}')
        lint_contexts = lock.get('lint_contexts') or {}

    before_counts = _hard_gate_counts_for_entries(entries, site_label, lint_contexts)
    for change in document.changes:
        entries[change.canonical_id] = _apply_free_patch(
            entries[change.canonical_id], change.values)
    after_counts = _hard_gate_counts_for_entries(entries, site_label, lint_contexts)
    _reject_if_lint_regressed(before_counts, after_counts, args.entries)
    if lock_info:
        all_remaining = _hard_gate_reasons_for_entries(entries, site_label, lint_contexts)
        remaining = _remaining_active_lock_reasons(
            lock_info[1], {reason['reason_code']: reason for reason in all_remaining})

    summary = {
        'site': args.site,
        'dry_run': bool(args.dry_run),
        'changed': [
            {'id': change.canonical_id, 'fields': list(change.fields)}
            for change in document.changes
        ],
        'lint_reason_counts_before': before_counts,
        'lint_reason_counts_after': after_counts,
        'target_sha256_before': document.target_sha256,
        'target_sha256_after': patch_file.sha256_json(entries),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
    if args.dry_run:
        return
    try:
        patch_file.require_target_sha(args.entries, document.target_sha256)
        patch_file.atomic_write_json(args.entries, entries)
    except (OSError, patch_file.PatchFileError) as exc:
        _rewrite_entry_error(f'batch patch 寫入失敗，target 未被部分寫入：{exc}')

    if lock_info:
        if not remaining:
            _clear_gate_lock(args.entries, site_label)
        else:
            _update_active_lock(lock_info[0], lock_info[1], remaining)
    print(f'✅ rewrite-entry --patch-file 已一次更新 {len(document.changes)} 則：'
          f'{", ".join(requested_ids)}', file=sys.stderr)
    print('ℹ️ 下一步：重跑原本的 `build --dry-run`；reason code 歸零後再跑正式 build。',
          file=sys.stderr)


def cmd_rewrite_entry(args):
    """精準改少量 ID 的受控修補，分兩種模式：

      - **有 active gate lock**（既有、2026-09-18 上線路徑，邏輯一行未改）：
        只准改 lock reason items 列出的 ID；重跑共用 lint，歸零才自動解鎖。
      - **沒有 gate lock**（2026-09-23 新增自由模式，見 `_cmd_rewrite_entry_free`）：
        可自行指定 ID，做 entry／category／tc 的局部欄位修補；不碰 lock，
        落檔前擋「把 lint 改爛到達硬閘門檻」。
    """
    site_label = args.site.upper()
    if getattr(args, 'init_patch', None):
        if (getattr(args, 'patch_file', None) or getattr(args, 'ids', None)
                or getattr(args, 'sets', None) or getattr(args, 'new_ids', None)
                or getattr(args, 'new_topics', None) is not None
                or getattr(args, 'dry_run', False)):
            _rewrite_entry_error(
                '--init-patch 不可與 --patch-file／--id／--set／--new-id／'
                '--new-topics／--dry-run 併用。')
        try:
            patch_file.write_scaffold(args.init_patch, site=args.site, target=args.entries)
        except patch_file.PatchFileError as exc:
            _rewrite_entry_error(str(exc))
        print(f'✅ patch scaffold 已建立：{args.init_patch}\n'
              f'ℹ️ 填完 changes 後執行：python scripts/s2_batch_prep.py rewrite-entry '
              f'--site {args.site} --entries "{args.entries}" '
              f'--patch-file "{args.init_patch}"', file=sys.stderr)
        return
    if getattr(args, 'patch_file', None):
        if (getattr(args, 'ids', None) or getattr(args, 'sets', None)
                or getattr(args, 'new_ids', None)
                or getattr(args, 'new_topics', None) is not None):
            _rewrite_entry_error(
                '--patch-file 與舊的 --id／--set／--new-id／--new-topics 互斥。')
        return _cmd_rewrite_entry_patch(args, site_label)
    if getattr(args, 'dry_run', False):
        _rewrite_entry_error('--dry-run 只和 --patch-file 併用。')
    lock_path = _gate_lock_path(args.entries, site_label)
    if not os.path.exists(lock_path):
        return _cmd_rewrite_entry_free(args, site_label)
    try:
        with open(lock_path, encoding='utf-8') as f:
            lock = json.load(f)
    except (OSError, ValueError) as exc:
        _rewrite_entry_error(f'gate lock 無法讀取：{exc}')

    if lock.get('site') != site_label:
        _rewrite_entry_error(f'gate lock 站別是 {lock.get("site")}，不是 {site_label}。')
    locked_entries = os.path.normcase(os.path.abspath(lock.get('entries_path') or ''))
    requested_entries = os.path.normcase(os.path.abspath(args.entries))
    if locked_entries != requested_entries:
        _rewrite_entry_error('gate lock 記錄的 entries_path 與 --entries 不一致。')

    reasons = lock.get('reasons') or []
    try:
        counts = [int(r.get('count', 0)) for r in reasons]
    except (TypeError, ValueError):
        _rewrite_entry_error('gate lock 的 reason count 格式不合法；請重跑 build --dry-run。')
    if any(count >= HARD_GATE_THRESHOLD for count in counts) or sum(counts) >= HARD_GATE_THRESHOLD:
        _rewrite_entry_error(
            f'gate lock 記錄共 {sum(counts)} 項格式錯誤（通用門檻 ≥{HARD_GATE_THRESHOLD}），'
            '請改用整批 Write 重寫 entries.json。')

    allowed_ids = {
        str(item_id) for reason in reasons for item_id in (reason.get('items') or [])
    }
    if not allowed_ids:
        _rewrite_entry_error('gate lock 沒有 reason items；請先重跑 build --dry-run 更新 lock。')
    requested_ids = [str(item_id) for item_id in (args.ids or [])]
    if not requested_ids or len(requested_ids) != len(set(requested_ids)):
        _rewrite_entry_error('--id 至少給一個且不可重複。')
    updates = _parse_rewrite_sets(args.sets)
    if set(requested_ids) != set(updates):
        _rewrite_entry_error('--id 與 --set 指定的 ID 必須完全一致。')
    unauthorized = sorted(set(requested_ids) - allowed_ids)
    if unauthorized:
        _rewrite_entry_error(
            f'ID 不在 gate lock 的 reason items 清單：{", ".join(unauthorized)}')

    entries = load_json(args.entries)
    if not isinstance(entries, dict):
        if isinstance(entries, list):
            _rewrite_entry_error(
                '--entries 收到的是 batch/skeleton 陣列，不是 `{id:{entry,...}}` 的 '
                'entries.json。請把 `--entries` 改成 build 的上游 entries 草稿；'
                'batch 產物請回上游修正後重跑 build。')
        _rewrite_entry_error('entries.json 頂層必須是 object。')
    missing = sorted(set(requested_ids) - set(entries))
    if missing:
        _rewrite_entry_error(f'entries.json 找不到 ID：{", ".join(missing)}')
    for item_id in requested_ids:
        entries[item_id] = updates[item_id]

    all_remaining = _hard_gate_reasons_for_entries(
        entries, site_label, lock.get('lint_contexts') or {})
    remaining = _remaining_active_lock_reasons(
        lock, {r['reason_code']: r for r in all_remaining})
    try:
        _atomic_write_json(args.entries, entries)
    except OSError as exc:
        _rewrite_entry_error(f'entries.json 寫入失敗：{exc}')
    print(f'✅ rewrite-entry 已精準更新 {len(requested_ids)} 則：{", ".join(requested_ids)}',
          file=sys.stderr)

    if not remaining:
        _clear_gate_lock(args.entries, site_label)
        return

    _update_active_lock(lock_path, lock, remaining)
    print('⚠️ gate lock 保留；白名單格式問題尚未歸零：', file=sys.stderr)
    for reason in remaining:
        print(f'  {reason["reason_code"]}（{reason["count"]}則）：'
              f'{", ".join(reason.get("items") or [])}', file=sys.stderr)


def cmd_rewrite_entry_cli(args):
    """argparse 的入口薄殼：只擋「有 active gate lock 卻帶自由模式專屬旗標」。

    `--new-id`／`--new-topics` 只有自由模式看得懂；lock 模式那條路徑是刻意一行
    未動的既有已上線邏輯，它會**直接忽略**這兩個旗標——不擋的話
    `--id A --set A=… --new-id B --set B=…` 在有 lock 時會變成「A 改了、B 靜默
    消失」這種做一半的結果。這層只做這一件事，其餘一律原樣轉交
    `cmd_rewrite_entry`（所以既有測試直接呼叫 `cmd_rewrite_entry` 仍等價）。
    """
    free_only = []
    if getattr(args, 'new_ids', None):
        free_only.append('--new-id')
    if getattr(args, 'new_topics', None) is not None:
        free_only.append('--new-topics')
    if free_only:
        lock_path = _gate_lock_path(args.entries, args.site.upper())
        if os.path.exists(lock_path):
            _rewrite_entry_error(
                f'{"／".join(free_only)} 只在自由模式（沒有 gate lock）可用，'
                f'但這份 entries.json 目前有 active gate lock：{lock_path}。\n'
                '  請先用 `rewrite-entry --id/--set` 修完 lock 列出的 ID'
                '（白名單 lint 歸零會自動解鎖），解鎖後再新增則／補 `_new_topics`；'
                '真的要整份大改就用一次 `Write` 整批重寫。')
    return cmd_rewrite_entry(args)


def _enforce_build_hard_gate(warnings, site=None, dry_run=False, entries_path=None,
                             lint_rows=None):
    """正式 build 或 --dry-run 遇到白名單格式類 reason code 達門檻（>=5）時硬閘擋下。

    2026-09-18（R43 遵守修法方向1）：觸發時額外落一份 gate lock 標記檔
    （`_write_gate_lock`），交給 PreToolUse hook（s2_gate_guard.py）技術性擋掉
    對同一 entries.json 的 Edit——文字警告管不住 agent 選擇忽略指示逐筆修補
    這件事（連續 4 輪實錯），要在工具層真的擋下來。
    reason code 計數降到 0（含 warnings 整體變空）時，同一路徑自動清鎖
    （`_clear_gate_lock`）——這是清除時機②，時機①見 s2_gate_guard.py。"""
    site_label = (site or '該站').upper()
    grouped, hard_gate_reasons = collect_build_lint_reasons(warnings or [], site=site_label)
    if not hard_gate_reasons:
        owning = _lock_owning_entries(entries_path) if entries_path else None
        if owning:
            lock_path, lock = owning
            remaining = _remaining_active_lock_reasons(lock, grouped)
            if remaining:
                _update_active_lock(lock_path, lock, remaining)
            else:
                # A42: only the reason set that actually crossed a hard-gate threshold
                # may keep its lock.  Unrelated 1-4 count warnings never inherit it.
                _clear_gate_lock(entries_path, site_label)
        return

    if warnings:
        _print_build_lint_warnings(warnings, site=site_label)
    _write_gate_lock(entries_path, site_label, hard_gate_reasons, dry_run, lint_rows=lint_rows)
    lines = [
        f'⛔ 【建批硬閘攔截】{site_label} 站偵測到機械格式錯誤達到硬閘門檻，拒絕放行：'
    ]
    for r in hard_gate_reasons:
        threshold_note = HARD_GATE_THRESHOLD_OVERRIDES.get(r['reason_code'], HARD_GATE_THRESHOLD)
        items_str = ', '.join(r['items'][:10]) + ('…' if len(r['items']) > 10 else '')
        lines.append(
            f'  • 站別：{r["site"]} | 代碼：{r["reason_code"]}（{r["name"]}）'
            f'| 共 {r["count"]} 則（門檻 ≥{threshold_note}）\n'
            f'    涉及項目：{items_str}'
        )
    status_desc = ('--dry-run 預檢未通過，batch.json 尚未寫入！'
                   if dry_run else
                   '正式 build 已中斷，batch.json 尚未寫入！')
    entries_abs = os.path.abspath(entries_path)
    patch_path = os.path.splitext(entries_abs)[0] + '.patch.json'
    fix_steps = [
        f'    1. 先建立綁定目前 SHA 的空白 patch（可直接貼上執行）：',
        f'       python scripts/s2_batch_prep.py rewrite-entry --site {site_label.lower()} '
        f'--entries "{entries_abs}" --init-patch "{patch_path}"',
        f'    2. 把本批全部 ID／欄位填進 changes，再一次 apply：',
        f'       python scripts/s2_batch_prep.py rewrite-entry --site {site_label.lower()} '
        f'--entries "{entries_abs}" --patch-file "{patch_path}"',
        f'    3. apply 會一次驗證 lock 權限與 lint；完成後重跑原本的 build --dry-run。',
    ]
    lines.extend([
        f'  • 狀態：{status_desc}',
        f'  • 處置要求：',
    ] + fix_steps)
    print('\n'.join(lines), file=sys.stderr)
    sys.exit(2)


def truncate(s, limit=SRC_TEXT_LIMIT):
    """截斷標記絕對不能含中文。

    2026-08-12 0812-1600 輪實錯：原本用「…(截斷)」，直接踩到
    `s2_state.strip_agent_note()` 的判準——那條規則是 RT4131 連錯四輪換來的鐵律
    （三站原文一律英／西文，出現中文幾乎必然是 agent 混進去的判斷）。
    `strip_agent_note` 是整行砍，不是只砍標記本身，所以中文標記把它接上的
    整個最後一行（最長可達近 250 字的真實原文）一起當「agent 污染」剝掉，
    稽核（`s2_audit.py` §3）因此對 13 筆全部誤判成「混入中文說明」——
    查證後 13 筆全部是純英文站方原文被我這個標記拖累，沒有一筆是真的污染。

    2026-08-13 R4/R12 修正：
    - R4：原本 `s[:limit] + '...[TRUNCATED]'` 是「取滿 limit 字再加標記」，
      含標記總長會超過 limit（實錯 4014>4000）。改成標記也算在 limit 裡。
    - R12：RT 稿的 SOUNDBITE／SUPERS 段（逐字引言，寫稿驗 BITE 的唯一依據）
      常常落在 4000 字之後，傻取前 N 字會把它整段砍光（RT9878：sb_count=9
      但截斷文字內無任何引言，agent 只能標無BITE 送人工）。這種情況改成
      「頭段＋中段標記＋SOUNDBITE 起的區段」，SOUNDBITE 段本身超長時只保留
      它的前段——全部含標記仍 ≤ limit。中段標記同樣不能含中文（同上一條）。
    """
    s = s or ''
    if len(s) <= limit:
        return s
    end_marker = '...[TRUNCATED]'
    plain_cut = max(limit - len(end_marker), 0)

    anchors = []
    m = SOUNDBITE_RE.search(s)
    if m:
        anchors.append(m.start())
    inline_anchor = pretag.inline_sot_anchor(s)
    if inline_anchor is not None:
        anchors.append(inline_anchor)
    tail_start = min((pos for pos in anchors if pos >= plain_cut), default=None)
    if tail_start is not None:
        # 頭段截斷本來就會把逐字引言或 NS inline SOT 砍在外面，改保留策略
        mid_marker = '...[SNIP]...'
        head = s[:min(HEAD_KEEP, plain_cut)]
        budget_for_tail = limit - len(head) - len(mid_marker)
        tail = s[tail_start:]
        if len(tail) > budget_for_tail:
            tail_cut = max(budget_for_tail - len(end_marker), 0)
            tail = tail[:tail_cut] + end_marker
        result = head + mid_marker + tail
        return result[:limit]  # 保險：理論上不會超過，但不賭

    return s[:plain_cut] + end_marker


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


# ── per-site adapter ──────────────────────────────────────────────
# id_of：從 raw item 取狀態檔用的 id（三站前綴規則不同，見 13c）
# skip_of：機械排除判準（NS 的 AUDIO TRACK／GRAPHIC 初稿佔位；13c §3）；
#          回傳非空字串＝這則不收，不進 batch.json
# status_of：機械推導 script_status（prelim／early access → pending）
# extra_of：站別專屬欄位（NS: footage_type/duration_ms；AP: sb_count/has_sot；RT: sb_count）
# src_text_of：機械組「瘦身後的站方原文」，跟現行 batch.json 既有格式對齊


def _rt_code_or_edit(it):
    """RT 的編號：**清單**檔在 `code`，**detail** 檔在 `edit`——同一個坑
    `_id_of_any`（下面 raw 檢查工具層那條猜測路徑）在 T9（2026-08-25）就記過，
    但 `SITE_SPEC` 這條走的是明確欄位、沒吃到那個 fallback，於是 `dump`／
    `build`／`from-raw` 對 RT **detail** 檔的 `id_of` 一路回空字串——
    0907 A24 R22 用真實快照重跑 `from-raw` 才實測到：8 則全部因為 id 撞成
    同一個空字串，被 `dedup_by_id` 去重成 1 則。

    做法對齊 `_id_of_any`：`code` 有值就用 `code`；沒有才退 `edit`，
    且 `edit` 要求**含數字**才採信——上游這個欄位有退化值（`_id_of_any`
    旁的註解記過：純 `'RT'` 裸前綴、`'RTRT7400'` 雙前綴這類髒值），
    純字母、沒有數字的一律當沒有，不能比沒有 id 更糟（撞名比缺值危險）。
    清單檔（`code` 有值）行為完全不變。"""
    code = str(it.get('code') or '').strip()
    if code:
        return code
    edit = str(it.get('edit') or '').strip()
    if edit and re.search(r'\d', edit):
        return edit
    return ''


def _rt_extra(it):
    """A48：S2_SOURCE_META 預設 off；只在既有機械路徑附加 platform。"""
    extra = {'sb_count': it.get('sb_count', 0)}
    if os.environ.get('S2_SOURCE_META', 'off').strip().lower() != 'on':
        return extra
    # import 也在隔離範圍內；保存器故障不得阻塞整輪或觸發補抓。
    try:
        from s2_source_meta import rt_source_meta
        extra['platform'] = rt_source_meta(it)
    except Exception as exc:
        extra['platform'] = {
            'meta_schema_version': 1, 'site': 'RT', 'guid': it.get('guid'),
            'meta_missing_reason': [{'field': 'guid', 'code': 'extractor_error',
                                     'detail': f'RT 保存器失敗（{type(exc).__name__}）；原值保留，正文照舊'}],
        }
    return extra


SITE_SPEC = {
    'ns': {
        'source': 'NS',
        'id_of': lambda it: it.get('id', ''),
        'skip_of': lambda it: it.get('skip', '') or '',
        'status_of': lambda it: 'has_script',
        'extra_of': lambda it: {
            'footage_type': it.get('ft', ''),
            # NS API 的 duration 是毫秒；正式欄位保留原值，供後續 lint／稽核使用。
            'duration_ms': it.get('dur_ms', ''),
        },
        'src_text_of': lambda it: truncate(
            f"DESC: {it.get('desc', '')}\nSCRIPT: {it.get('script', '')}"
        ),
        'dump_fields': ['id', 'ft', 'dur_ms', 'created', 'skip', 'desc'],
    },
    'ap': {
        'source': 'AP',
        'id_of': lambda it: it.get('id', ''),
        'skip_of': lambda it: '',
        'status_of': lambda it: 'pending' if it.get('prelim') else 'has_script',
        'extra_of': lambda it: {
            'sb_count': it.get('sb_count', 0),
            'has_sot': bool(it.get('has_sot')),
        },
        'src_text_of': lambda it: truncate(
            f"HEAD: {it.get('head', '')}\nSCRIPT: {it.get('script', '')}"
        ),
        'dump_fields': ['id', 'role', 'sb_count', 'has_sot', 'prelim', 'dur', 'src', 'head'],
    },
    'rt': {
        'source': 'RT',
        'id_of': _rt_code_or_edit,
        'skip_of': lambda it: '',
        'status_of': lambda it: 'pending' if it.get('early') else 'has_script',
        'extra_of': _rt_extra,
        'src_text_of': lambda it: truncate(
            f"HEAD: {it.get('head', '')}\nSTORY: {it.get('story', '')}"
        ),
        'dump_fields': ['code', 'sb_count', 'early', 'dur', 'src', 'head'],
    },
}


def dedup_by_id(spec, items):
    """raw 裡不該有重複 id（13c：逐字完全相同才准跳過，抽取階段就該濾掉），但抽取端
    萬一分頁重疊、agent 重複收錄還是可能發生。保留第一次出現的那筆，其餘丟棄並警告，
    避免兩筆同 id 原樣送進 add-batch（下游行為未定義）。"""
    seen, kept, dups = set(), [], []
    for it in items:
        item_id = spec['id_of'](it)
        if item_id in seen:
            dups.append(item_id)
            continue
        seen.add(item_id)
        kept.append(it)
    if dups:
        print(f'⚠️ raw 裡有重複 id，只保留第一次出現的那筆：{", ".join(dups)}', file=sys.stderr)
    return kept


def cmd_dump(args):
    spec = SITE_SPEC[args.site]
    items = dedup_by_id(spec, load_json(args.raw))
    lines = []
    kept = skipped = 0
    for it in items:
        item_id = spec['id_of'](it)
        skip_reason = spec['skip_of'](it)
        if skip_reason:
            skipped += 1
            lines.append(f"[排除:{skip_reason}] {item_id}")
            continue
        kept += 1
        fields = {k: it.get(k) for k in spec['dump_fields']}
        lines.append(f"{item_id}\t{json.dumps(fields, ensure_ascii=False)}")
    lines.append(f"\n共 {len(items)} 則，收 {kept}、機械排除 {skipped}")
    out = '\n'.join(lines)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(out + '\n')
        print(f'已寫入 {args.out}（{kept} 則）', file=sys.stderr)
    else:
        print(out)


def _write_or_preview_build(args, out, note):
    """正式 build 寫輸出；`--dry-run` 只報預檢結果，不印／寫 batch。"""
    if getattr(args, 'dry_run', False):
        print(f'--dry-run：{note}；未寫入 batch 輸出')
    elif args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f'已寫入 {args.out}{note}', file=sys.stderr)
    else:
        print(out)


def parse_draft_entry(item_id, draft_payload):
    """解析 entries.json 中的單筆草稿項目，回傳：
      (entry_text, category, tc, status_override, was_converted)

    安全護欄：
    1. 若草稿物件同時包含 'entry' 與 'raw_entry'：
       視為資料衝突，不猜測、不覆蓋，直接以 exit code 2 終止並印出 ⛔ 錯誤。
    2. 若草稿物件無 'entry' 鍵、但有字串型別的 'raw_entry' 鍵：
       視為常見筆誤，記憶體內自動轉為 entry 使用（不改寫原檔），was_converted=True。
    3. raw_entry 非字串型別時不自動修復，entry_text 維持空字串，由下游缺欄位邏輯處理。
    4. 若草稿直接是字串，視為純文字 entry_text。
    5. 其他型別回傳空 entry_text。
    """
    if isinstance(draft_payload, dict):
        has_entry = 'entry' in draft_payload
        has_raw_entry = 'raw_entry' in draft_payload

        if has_entry and has_raw_entry:
            print(f'⛔ {item_id} entries.json 草稿同時包含 "entry" 與 "raw_entry" 鍵，'
                  f'資料衝突拒絕猜測或覆蓋；batch 尚未寫入。請確認保留正確內容後重試。',
                  file=sys.stderr)
            sys.exit(2)

        category = draft_payload.get('category')
        tc = draft_payload.get('tc')
        status_override = draft_payload.get('status')

        if has_entry:
            val = draft_payload.get('entry')
            entry_text = val if isinstance(val, str) else ''
            return entry_text, category, tc, status_override, False
        elif has_raw_entry:
            val = draft_payload.get('raw_entry')
            if isinstance(val, str):
                return val, category, tc, status_override, True
            else:
                return '', category, tc, status_override, False
        else:
            return '', category, tc, status_override, False

    elif isinstance(draft_payload, str):
        return draft_payload, None, None, None, False
    else:
        return '', None, None, None, False


def _report_raw_entry_conversions(converted_ids):
    """印出 raw_entry 自動修復為 entry 的彙總警告。"""
    if not converted_ids:
        return
    shown_ids = ', '.join(converted_ids[:10])
    if len(converted_ids) > 10:
        shown_ids += '…'
    print(f'⚠️ 偵測到 {len(converted_ids)} 筆工作草稿使用 raw_entry；'
          f'build 已暫轉為 entry，原 entries.json 未修改。（涉及 ID：{shown_ids}）',
          file=sys.stderr)


def _autofix_skeleton_lookup(skeleton_path):
    """讀 `from-raw` 產的骨架 json，回傳 {id: {'footage_type':…, 'duration_ms':…}}。
    只有 NS 站的 SOT 自動修補需要這個（判斷 PKG/DONUT 且時長>1分鐘要查
    `s2_pretag.pkg_donut_needs_sot()`，這兩個欄位不在 entries.json 草稿裡，
    只在骨架／raw 才有）。"""
    rows = load_json(skeleton_path)
    return {
        r.get('id'): {
            'footage_type': r.get('footage_type', ''),
            'duration_ms': r.get('duration_ms', ''),
        }
        for r in rows if isinstance(r, dict) and r.get('id')
    }


def _apply_mechanical_autofix(entry_text, site, footage_type=None, duration_ms=None):
    """R43層1治本 機械修補的共用純函式（v2，2026-09-22）——`cmd_autofix_tags`
    與 `cmd_build` 共用同一套判準，不複製一份會漂移的邏輯。

    只做兩種「有錨點、不用猜內容」的機械修補（詳見 `cmd_autofix_tags`
    docstring）：
      1. 有 `▎BITE：` 段但缺 `(BITE)` 第二括號 → 插入（任何站都做）。
      2. NS 站 PKG/DONUT 且時長>1分鐘但第一備註缺 SOT 字樣 → 插入。
         `footage_type`/`duration_ms` 傳 `None`＝呼叫端沒有這項資訊來源
         （例如 `autofix-tags` 沒帶 `--skeleton`），這關直接跳過；傳空字串
         `''` 也是有效值（照樣送進 `sot_marker_patchable` 判斷），因為
         `build` 兩條分支的 row 一律帶這兩個欄位（SITE_SPEC 的 NS
         `extra_of` 預設空字串，不是缺欄位），不需要額外依賴 `--skeleton`。

    回傳 `(new_entry_text, notes)`，`notes` 是 `['補(BITE)', '補SOT']` 的
    子集，沒修就是 `[]`——呼叫端用這個判斷要不要記進報告清單，避免
    「悄悄改稿」agent 看不到發生了什麼事。
    """
    notes = []
    ok, _why = s2_state.bite_tag_patchable(entry_text)
    if ok:
        entry_text = s2_state.insert_bite_tag(entry_text)
        notes.append('補(BITE)')

    if site == 'ns' and footage_type is not None and duration_ms is not None:
        ok2, _why2 = pretag.sot_marker_patchable(entry_text, footage_type, duration_ms)
        if ok2:
            entry_text = pretag.insert_sot_marker(entry_text)
            notes.append('補SOT')

    return entry_text, notes


def _print_build_autofix_summary(bite_ids, sot_ids):
    """v2：`build` 自動套用機械修補後的稽核輸出——只印到 stderr，不影響
    輸出檔本身；一定要列筆數＋ID，避免agent以為「格式不用管，反正build
    會偷偷幫你修」（Codex sol覆核意見）。"""
    if not bite_ids and not sot_ids:
        return
    parts = []
    if bite_ids:
        parts.append(f'補(BITE) {len(bite_ids)} 則：{", ".join(bite_ids[:20])}'
                      + ('…' if len(bite_ids) > 20 else ''))
    if sot_ids:
        parts.append(f'補SOT {len(sot_ids)} 則：{", ".join(sot_ids[:20])}'
                      + ('…' if len(sot_ids) > 20 else ''))
    print('🔧 build 已自動機械修補（僅補漏標記，不動內容判斷；entries.json '
          '原始檔未被寫回，agent仍應力求entries一次寫對，其餘問題照常警告/擋下）：\n  '
          + '\n  '.join(parts), file=sys.stderr)


def cmd_autofix_tags(args):
    """R43「層1治本」機械自動修補（2026-09-19，方向1/2的額外補強，非取代）。

    背景：0919-0430輪transcript查證確認，機械提示表標記（⚠️SOT／⚠️疑似BITE，
    見 `cmd_from_raw`）即使正確顯示給 agent，草稿階段仍會被漏套用——NS站
    5個PKG/DONUT>1分鐘項目的⚠️SOT標記100%有顯示，仍100%沒補SOT；同輪NS站
    另有26則`▎BITE：`段寫了卻漏`(BITE)`括號。**內容判斷本身是對的**（真的
    找到引言、寫進了▎BITE：段），漏的是機械標記這個動作本身——這正是「有
    錨點可插、純機械補、不需要編輯判斷」的情況，比照`s2_state.insert_bite_tag()`
    的既有哲學（R43方向1已由gate lock把「改用Write整批重寫」的合規行為逼出
    來，這支工具進一步把「重寫」的第一步做成機械可靠，不必agent從頭手key）。

    ⛔ 這不是萬能修補——只做兩種**有錨點、不用猜內容**的機械修補：
      1. 有 `▎BITE：` 段但缺 `(BITE)` 第二括號 → 插入（沿用
         `s2_state.bite_tag_patchable()`/`insert_bite_tag()`，同一套判準
         不重寫第二份）。
      2. NS 站 PKG/DONUT 且時長>1分鐘但第一備註缺 SOT 字樣 → 插入（沿用
         `pretag.sot_marker_patchable()`/`insert_sot_marker()`，跟硬閘
         `pkg_donut_needs_sot()` 同一個判準函式，不會漂移）。
    FMT_FIRST_NOTE_BITE（`(BITE)` 是唯一/第一個括號、沒有描述性第一備註）
    **刻意不自動修**——沒有資料可以機械生出「這則的地點/主題描述」該寫什麼，
    硬塞會比不修更糟；這類仍列在報告裡，交回 agent 自己補一個詞。
    """
    entries = load_json(args.entries)
    if not isinstance(entries, dict):
        print(f'✗ {args.entries} 頂層不是 dict（entries.json 草稿應為 '
              f'{{id: 值}} 或含 _new_topics 的物件），無法自動修補。', file=sys.stderr)
        sys.exit(2)

    skel_lookup = {}
    if args.skeleton:
        skel_lookup = _autofix_skeleton_lookup(args.skeleton)
    elif args.site == 'ns':
        print('ℹ️ NS 站未帶 --skeleton，SOT 自動修補這關略過（缺 footage_type／'
              'duration_ms 資料來源），只做 (BITE) 括號修補。', file=sys.stderr)

    fixed_bite, fixed_sot, remaining = [], [], []
    for item_id, draft_payload in entries.items():
        if item_id == '_new_topics':
            continue
        entry_text, category, tc, status_override, was_converted = parse_draft_entry(
            item_id, draft_payload)
        if not entry_text:
            continue

        skel_info = skel_lookup.get(item_id) if args.site == 'ns' else None
        entry_text, notes = _apply_mechanical_autofix(
            entry_text, args.site,
            footage_type=skel_info.get('footage_type') if skel_info else None,
            duration_ms=skel_info.get('duration_ms') if skel_info else None,
        )
        if '補(BITE)' in notes:
            fixed_bite.append(item_id)
        if '補SOT' in notes:
            fixed_sot.append(item_id)

        if notes:
            field = 'raw_entry' if was_converted else 'entry'
            if isinstance(draft_payload, dict):
                draft_payload[field] = entry_text
            else:
                entries[item_id] = entry_text

        # 修完（或本來就沒得修）都再檢一次，把「白名單機械格式類、仍過不了」
        # 的項目報出來——這些是刻意不自動修的（FMT_FIRST_NOTE_BITE 之類）。
        remaining_msgs = list(s2_state.fmt_issues(entry_text))
        skel_info = skel_lookup.get(item_id)
        if args.site == 'ns' and skel_info:
            remaining_msgs += list(pretag.lint(
                entry_text, footage_type=skel_info.get('footage_type'),
                duration_ms=skel_info.get('duration_ms'), source='NS'))
        for msg in remaining_msgs:
            code, is_hard_gate, name = classify_warning_reason(msg)
            if is_hard_gate:
                remaining.append(f'{item_id}: {name}（{code}，需人工判斷，未自動修）')

    out = args.out or args.entries
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    print(f'✅ 自動修補完成，已寫入 {out}：補(BITE) {len(fixed_bite)} 則'
          + (f'、補SOT {len(fixed_sot)} 則' if args.site == 'ns' else ''),
          file=sys.stderr)
    if fixed_bite:
        print(f'  補(BITE)：{", ".join(fixed_bite[:20])}'
              + ('…' if len(fixed_bite) > 20 else ''), file=sys.stderr)
    if fixed_sot:
        print(f'  補SOT：{", ".join(fixed_sot[:20])}'
              + ('…' if len(fixed_sot) > 20 else ''), file=sys.stderr)
    if remaining:
        print(f'⚠️ 仍有 {len(remaining)} 項機械格式問題無法自動修（需要編輯判斷，'
              f'請自行確認後用 Write 整批重寫，不要逐筆 Edit）：', file=sys.stderr)
        for line in remaining[:30]:
            print(f'  {line}', file=sys.stderr)
        if len(remaining) > 30:
            print(f'  …另 {len(remaining) - 30} 項略', file=sys.stderr)


def cmd_build(args):
    entries = load_json(args.entries)

    # A24（2026-09-07）：`from-raw` 產的骨架已經把機械欄位（id/source/checkpoint/
    # status/src_text/站別專屬欄位）全填好，agent 只需要寫極小的
    # `{id: {entry, category, tc}}`。這條路徑直接以骨架為底，不重讀 raw——
    # 骨架本身就是「dedup＋機械排除＋D12 已在庫標記」跑完之後的結果，
    # 沒有理由再對 raw 重跑一次同樣的判斷。
    if getattr(args, 'skeleton', None):
        rows = load_json(args.skeleton)
        batch, missing = [], []
        # P1b-2（2026-09-07）：entries.json 頂層保留鍵 `_new_topics`＝
        # {名: {"charter": …, "big": …[, "aliases": […]]}}，原樣搬到 batch 頂層
        # `new_topics`；輸出改成 {"entries": […], "new_topics": {…}} 新格式，
        # add-batch 讀到這個形狀才會走 A10 P1b 新題閘門（純陣列＝不閘）。
        # 軟上線（0907 e2e：22:00 真實 RT 批 23 則有 20 則、15 個中主題未登記）：
        # entries.json **有** `_new_topics` 鍵（沒新題就 `{}`）才出新格式／過閘；
        # 沒這個鍵＝agent 不知道閘門機制，維持純陣列舊行為，免得一輪 20 則沒分類
        # 又不知道怎麼救。規則（13c2 §2）要求一律放這個鍵。
        # 🔴 2026-09-08 硬上線：`build --site` 只吃 ns／ap／rt，而這三站的 batch
        # 已經不准是純陣列（`add-batch` 會當場退回），所以這裡**一律**出殼——
        # 軟上線那版（有 `_new_topics` 鍵才出殼）會讓沒寫那個鍵的 agent 拿到一份
        # 註定被退回的產物，等於把坑往下游搬。
        new_topics = entries.get('_new_topics') if isinstance(entries, dict) else None
        new_topics = new_topics if isinstance(new_topics, dict) else {}
        lint_warnings = []  # §四（R31/T12）：build 出口共用 lint，見 _lint_row
        raw_entry_converted_ids = []
        autofix_bite_ids, autofix_sot_ids = [], []  # v2：build內建機械autofix稽核用
        for row in rows:
            item_id = row.get('id')
            draft_payload = entries.get(item_id)
            (entry_text, category, tc,
             status_override, was_converted) = parse_draft_entry(item_id, draft_payload)
            if was_converted:
                raw_entry_converted_ids.append(item_id)
            if not entry_text:
                missing.append(item_id)
                continue
            # v2：lint前先套用機械autofix（骨架row本身就帶footage_type/
            # duration_ms，NS站不需要另外依賴--skeleton參數）。
            entry_text, _autofix_notes = _apply_mechanical_autofix(
                entry_text, args.site,
                footage_type=row.get('footage_type'), duration_ms=row.get('duration_ms'))
            if '補(BITE)' in _autofix_notes:
                autofix_bite_ids.append(item_id)
            if '補SOT' in _autofix_notes:
                autofix_sot_ids.append(item_id)
            # 骨架的 entry/category/tc 是留空的佔位鍵，hint／prev_status 是
            # 骨架內部給 agent 看的提示，三者都不該原樣流進 batch.json。
            new_row = {k: v for k, v in row.items()
                       if k not in ('entry', 'category', 'tc', 'hint', 'prev_status')}
            new_row['entry'] = entry_text
            if status_override is not None:
                new_row['status'] = status_override
            if category is not None:
                new_row['category'] = category
            if tc is not None:
                new_row['tc'] = tc
            # A31：機械 T/C／涉臺／(BITE) 建議，掛在 row["suggest"]——
            # add-batch 讀到只印，不存進狀態檔（見 s2_pretag.py 開頭）。
            # 壞掉不擋 build：這是建議，不是必要欄位。
            try:
                _sug = pretag.suggest_tc(entry_text, source=new_row.get('source'))
                new_row['suggest'] = {
                    'T': _sug['T'], 'C': _sug['C'],
                    'taiwan': bool(pretag.taiwan_hit(entry_text)),
                    'bite': pretag.bite_suggest(new_row.get('sb_count'),
                                                 new_row.get('has_sot'), entry_text),
                }
            except Exception:
                pass
            for _reason in _lint_row(entry_text, new_row):
                lint_warnings.append(f'{item_id}: {_reason}')
            batch.append(new_row)

        _report_raw_entry_conversions(raw_entry_converted_ids)
        # v2修正（Codex sol覆核②）：autofix摘要要在硬閘可能exit(2)之前印，
        # 否則同輪若還有別的白名單警告觸發硬閘，這輪autofix修補紀錄會
        # 隨著sys.exit消失，agent看不到「build幫你補了什麼」。
        _print_build_autofix_summary(autofix_bite_ids, autofix_sot_ids)
        _enforce_build_hard_gate(lint_warnings, args.site,
                                 dry_run=getattr(args, 'dry_run', False),
                                 entries_path=args.entries, lint_rows=batch)
        out = json.dumps({'entries': batch, 'new_topics': new_topics},
                         ensure_ascii=False, indent=2)
        note = f'（{len(batch)} 則，新格式、過閘；new_topics {len(new_topics)} 題）'
        _write_or_preview_build(args, out, note)
        if missing:
            print(f'⚠️ 骨架裡有、entries.json 沒填 entry 的 id（未填，不算錯，'
                  f'但確認是不是漏判，不進 batch）：{", ".join(str(m) for m in missing)}',
                  file=sys.stderr)
        _print_build_lint_warnings(lint_warnings, args.site)
        return

    spec = SITE_SPEC[args.site]
    items = dedup_by_id(spec, load_json(args.raw))

    batch = []
    missing = []
    excluded = 0
    lint_warnings = []  # §四（R31/T12）：build 出口共用 lint，見 _lint_row
    raw_entry_converted_ids = []
    autofix_bite_ids, autofix_sot_ids = [], []  # v2：build內建機械autofix稽核用
    for it in items:
        item_id = spec['id_of'](it)
        if spec['skip_of'](it):
            excluded += 1
            continue
        if item_id not in entries:
            missing.append(item_id)
            continue
        draft_payload = entries[item_id]
        (entry_text, category, tc,
         status_override, was_converted) = parse_draft_entry(item_id, draft_payload)
        if was_converted:
            raw_entry_converted_ids.append(item_id)

        # v2：lint前先套用機械autofix。extra_fields先算好重用（原本
        # row.update(spec['extra_of'](it))會重算一次，這裡只算一次），
        # NS站的extra_of一律帶footage_type/duration_ms（預設空字串，不是
        # 缺欄位），不需要額外依賴--skeleton。
        extra_fields = spec['extra_of'](it)
        if entry_text:
            entry_text, _autofix_notes = _apply_mechanical_autofix(
                entry_text, args.site,
                footage_type=extra_fields.get('footage_type'),
                duration_ms=extra_fields.get('duration_ms'))
            if '補(BITE)' in _autofix_notes:
                autofix_bite_ids.append(item_id)
            if '補SOT' in _autofix_notes:
                autofix_sot_ids.append(item_id)

        row = {
            'id': item_id,
            'source': spec['source'],
            'checkpoint': args.checkpoint,
            'status': status_override or spec['status_of'](it),
            'entry': entry_text,
            'src_text': spec['src_text_of'](it),
        }
        # T12（2026-09-07）：entries.json 的值若是物件，category／tc 兩鍵
        # 原樣帶進 batch row，交給 add-batch 一次入庫＋分類＋標 T/C。
        # 純字串 entries（舊格式）沒有這兩鍵可帶，行為完全不變。
        if category is not None:
            row['category'] = category
        if tc is not None:
            row['tc'] = tc
        row.update(extra_fields)
        if spec['source'] == 'NS':
            row['inline_sot_count'] = pretag.inline_sot_count(row['src_text'])
        # A31：機械 T/C／涉臺／(BITE) 建議，同 --skeleton 分支（見上）。
        try:
            _sug = pretag.suggest_tc(entry_text, source=row.get('source'))
            row['suggest'] = {
                'T': _sug['T'], 'C': _sug['C'],
                'taiwan': bool(pretag.taiwan_hit(entry_text)),
                'bite': pretag.bite_suggest(row.get('sb_count'), row.get('has_sot'), entry_text),
            }
        except Exception:
            pass
        for _reason in _lint_row(entry_text, row):
            lint_warnings.append(f'{item_id}: {_reason}')
        batch.append(row)

    _report_raw_entry_conversions(raw_entry_converted_ids)
    # v2修正（Codex sol覆核②）：同骨架分支，autofix摘要要在硬閘可能
    # exit(2)之前印，不然遇到硬閘這輪的修補紀錄就印不出來了。
    _print_build_autofix_summary(autofix_bite_ids, autofix_sot_ids)
    _enforce_build_hard_gate(lint_warnings, args.site,
                             dry_run=getattr(args, 'dry_run', False),
                             entries_path=args.entries, lint_rows=batch)
    # 🔴 2026-09-08 硬上線：跟 --skeleton 分支同一個理由，三站一律出新格式外殼。
    # 這條分支沒有 entries.json 可以帶 `_new_topics`，所以 new_topics 固定空的；
    # 要開新中主題就照退回訊息在 batch 頂層自己補。
    out = json.dumps({'entries': batch, 'new_topics': {}}, ensure_ascii=False, indent=2)
    _write_or_preview_build(args, out, f'（{len(batch)} 則，新格式、過閘）')

    if missing:
        _report_id_list(
            missing,
            small_heading='⚠️ raw 裡有但 entries.json 沒寫的 id（未收進 batch，不算錯，但確認是不是漏判）：',
            large_heading='⚠️ raw 裡有但 entries.json 沒寫',
            reason='未收進 batch，不算錯，但請確認是不是漏判',
            anchor_path=args.entries,
            suffix='_missing_ids.txt',
            stream=sys.stderr,
            small_inline=True,
        )
    if excluded:
        print(f'機械排除 {excluded} 則（見 dump 輸出的排除原因）', file=sys.stderr)
    _print_build_lint_warnings(lint_warnings, args.site)


def cmd_from_raw(args):
    """站方 detail raw ＋ 狀態檔 → 一次產出提示表＋骨架 JSON＋已在庫標記（A24，2026-09-07）。

    砍呼叫主線第二刀：`inspect` 逐則翻頁改成先看這支印出的提示表；agent
    只需要 Write 一份極小的 `{id: {entry, category, tc}}`（`build --skeleton`
    合併成 batch，見上）。

    **D12（跨批已查標記）**：`--state` 給了才排除——只排除狀態檔裡已經是
    `has_script` 的 id，`pending`／其他任何狀態一律保留（並標 `prev_status`），
    因為 prelim／early access 稿隨時可能補正式稿，機械排除等於永久漏收。
    """
    spec = SITE_SPEC[args.site]
    raw_data = load_json(args.raw)
    # 🔴 2026-09-14（複核 S3）：`--raw` 這裡吃的是 unwrap 後的裸陣列
    # （`from-raw` 不像 dump/inspect 等其他子指令走 `_load_raw_any` 自動
    # 卸殼），原本沒檢查形狀——殼沒卸乾淨、或給錯檔案（例如整份 offload
    # 殼、或 dict 而非 list）時，`dedup_by_id`／後續 `spec['id_of']` 會直接
    # 對非 dict 項目呼叫 `.get()` 炸出一整段 traceback，或者每一筆算出來
    # 的 id 都是空字串卻照樣生出一份「骨架」——那份骨架看起來像正常輸出，
    # 實際上是垃圾（agent 據此判斷已在庫/機械排除都會判錯）。改成先驗證
    # 形狀，錯就印清楚訊息、exit 2，不寫任何骨架檔。
    if not isinstance(raw_data, list) or not all(isinstance(x, dict) for x in raw_data):
        print(f'✗ {args.raw} 頂層不是「dict 陣列」（from-raw 只吃 unwrap 之後的'
              f'裸陣列；殼沒卸乾淨的話先跑 `unwrap --out` 再指過來）。'
              f'實際型別：{type(raw_data).__name__}', file=sys.stderr)
        sys.exit(2)

    items = dedup_by_id(spec, raw_data)
    if items and all(not spec['id_of'](it) for it in items):
        print(f'✗ {args.raw} 有 {len(items)} 筆，但每一筆算出的 id 都是空字串'
              f'（多半是欄位名不對，或這份檔案根本不是 --site {args.site} 站的 raw，'
              f'拒絕產出骨架，避免生出一份看起來正常、其實全空 id 的垃圾）',
              file=sys.stderr)
        sys.exit(2)

    have = {}
    if args.state:
        state = s2_state.load(args.state)
        have = {i: (v.get('script_status') or '') for i, v in state['items'].items()}

    skeleton = []
    machine_excluded = 0
    already_have = []
    pending_kept = []
    for it in items:
        item_id = spec['id_of'](it)
        if spec['skip_of'](it):
            machine_excluded += 1
            continue

        prev_status = have.get(item_id) if item_id in have else None
        if prev_status == 'has_script':
            already_have.append(item_id)
            continue

        src_text = spec['src_text_of'](it)
        row = {
            'id': item_id,
            'source': spec['source'],
            'checkpoint': args.checkpoint,
            'status': spec['status_of'](it),
            'src_text': src_text,
        }
        row.update(spec['extra_of'](it))
        if spec['source'] == 'NS':
            row['inline_sot_count'] = pretag.inline_sot_count(src_text)
        # entry／category／tc 是 agent 判斷欄位，骨架只留空位——
        # 這支腳本不生成、不翻譯、不判斷 BITE（同 build 開頭的說明）。
        row['entry'] = ''
        row['category'] = ''
        row['tc'] = ''
        if prev_status is not None:
            row['prev_status'] = prev_status
            if prev_status == 'pending':
                pending_kept.append(item_id)

        dur = it.get('dur')
        if dur is None:
            dur = it.get('dur_ms', '')
        extra = spec['extra_of'](it)
        # first150：src_text 正文前 150 字、去換行（提示表用，不是稽核落檔欄位）。
        first150 = re.sub(r'\s+', ' ', src_text).strip()[:150]
        row['hint'] = {
            'head': _title_of_any(it),
            'dur': dur,
            'first150': first150,
        }
        if spec['source'] == 'NS':
            # R43方向2（2026-09-18）：機械算出「PKG/DONUT且時長>1分鐘」門檻
            # 直接標在提示表上，agent 不用自己拿 dur_ms／ft 心算——跟硬閘
            # （`s2_pretag.lint()`）用**同一個** `pkg_donut_needs_sot()`，
            # 門檻不會漂移（見該函式 docstring）。
            row['hint'].update({
                'footage_type': row.get('footage_type', ''),
                'inline_sot_count': row['inline_sot_count'],
                'needs_sot': pretag.pkg_donut_needs_sot(
                    row.get('footage_type', ''), row.get('duration_ms', '')),
            })
        else:
            sb_count = extra.get('sb_count', 0)
            row['hint']['sb_count'] = sb_count
            # 同上（方向2）：AP／RT 用既有 `bite_suggest()` heuristic（sb_count／
            # has_sot 訊號）在**草稿寫之前**就標「疑似有 BITE」提醒——entry
            # 還沒寫、傳空字串，跟 `build` 階段 `row["suggest"]["bite"]` 用
            # 同一個函式，不重寫一份會漂移的判準。這只是提醒「該用兩段式
            # 括號結構」，不是「一定要標 BITE」的判定——那仍是 agent 的
            # 編輯判斷，heuristic 錯的方向（漏報／誤報）由 agent 自己收斂。
            row['hint']['bite_hint'] = bool(pretag.bite_suggest(
                sb_count=sb_count, has_sot=extra.get('has_sot'), entry=''))
        skeleton.append(row)

    out = args.out
    if not out:
        hhmm = args.checkpoint.split('-')[-1]
        base = os.path.dirname(os.path.abspath(args.raw))
        out = os.path.join(base, f'{args.site}_skeleton_{hhmm}.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2)

    # 提示表：#序｜id｜dur｜sb｜head｜first150｜T?｜C?｜🇹🇼（A31，2026-09-07）。
    # T?/C? 是機械建議、只是起點，照內容判；🇹🇼 只在涉臺詞表命中時才印一欄。
    # ⚠️ 這裡吃的是站方原文（head/first150，AP/RT/NS 多為英文），中文關鍵詞表
    # 在英文稿上命中率偏低是預期中的已知限制，不是這支腳本的 bug。
    # 壞掉不擋提示表本體：這欄是建議，不是必要輸出。
    all_lines = []
    for idx, row in enumerate(skeleton, 1):
        hint = row['hint']
        if row.get('source') == 'NS':
            line = (f"#{idx}｜{row['id']}｜dur_ms={hint['dur']}｜sb=n/a｜"
                    f"ft={hint['footage_type']}｜inline_sot={hint['inline_sot_count']}｜"
                    f"{hint['head']}｜{hint['first150']}")
            if hint.get('needs_sot'):
                line += "｜⚠️SOT（PKG/DONUT>1分鐘，第一備註要含SOT字樣）"
        else:
            line = (f"#{idx}｜{row['id']}｜{hint['dur']}｜{hint['sb_count']}｜"
                    f"{hint['head']}｜{hint['first150']}")
            if hint.get('bite_hint'):
                line += "｜⚠️疑似BITE（兩段式括號：(地點/主題)(BITE)）"
        try:
            _text = f"{row['hint']['head']} {row['hint']['first150']}"
            _sug = pretag.suggest_tc(_text, source=row.get('source'))
            line += f"｜T?={','.join(_sug['T'])}｜C?={','.join(_sug['C'])}"
            if pretag.taiwan_hit(_text):
                line += "｜🇹🇼"
        except Exception:
            pass
        all_lines.append(line)
    FROM_RAW_SCHEMA_CONTRACT = (
        'entries.json 每筆請填 {"<id>":{"entry":"…","category":"…","tc":"…"}}；'
        '工作草稿內容鍵一律用 entry，不是 raw_entry（raw_entry是狀態檔專用欄位，草稿階段不要用）。'
        '有BITE時第一備註別漏：CODE (地點/主題備註)(BITE) ▎摘要…▎畫面：…▎BITE：…（不是 CODE (BITE) ▎…，'
        '(BITE) 前面一定要有描述括號）；下表 ⚠️疑似BITE／⚠️SOT 是機械算好的提醒，不是判定，仍要自己確認內容。'
        '（v2）build 跑 lint 前會自動機械補上「漏(BITE)括號／NS站漏SOT字樣」這兩種有錨點可插的缺口'
        '（不猜內容，補完會印在 stderr），不必再手動先跑 autofix-tags；但entries仍應力求一次寫對，'
        '其餘真的需要判斷的問題（例如(BITE)是唯一括號、缺描述）不會自動修，一樣會被列出來讓你確認。'
    )
    contract_overhead = len(FROM_RAW_SCHEMA_CONTRACT) + 1
    page_budget = max(INSPECT_TEXT_BUDGET - contract_overhead, 200)
    pages, cur, cur_len = [], [], 0
    for ln in all_lines:
        ln_len = len(ln) + 1
        if cur and cur_len + ln_len > page_budget:
            pages.append(cur)
            cur, cur_len = [], 0
        cur.append(ln)
        cur_len += ln_len
    pages.append(cur)  # 0 則時也留一頁空的，--page 1 才有東西可選

    page_no = args.page or 1
    if page_no < 1 or page_no > len(pages):
        print(f'✗ --page {page_no} 超出範圍（共 {len(pages)} 頁）', file=sys.stderr)
        sys.exit(1)

    print(FROM_RAW_SCHEMA_CONTRACT)
    if pages[page_no - 1]:
        print('\n'.join(pages[page_no - 1]))
    if len(pages) > 1:
        if page_no < len(pages):
            print(f'— 第 {page_no}/{len(pages)} 頁，--page {page_no + 1} 看下一頁 —')
        else:
            print(f'— 第 {page_no}/{len(pages)} 頁（最後一頁）—')

    if already_have:
        print(f'已在庫略過 {len(already_have)} 則：{", ".join(already_have)}', file=sys.stderr)
    if pending_kept:
        print(f'pending 保留 {len(pending_kept)} 則：{", ".join(pending_kept)}', file=sys.stderr)
    if machine_excluded:
        print(f'機械排除 {machine_excluded} 則（見 dump 輸出的排除原因）', file=sys.stderr)
    print(f'骨架已寫 {out}（{len(skeleton)} 則）', file=sys.stderr)


# ── raw 檢查工具層：卸殼／inspect／search ──────────────────────

# 已知的站方外殼：頂層是 dict、實際陣列包在這些鍵之一底下。
# 依序嘗試，第一個「值是非空 list」的鍵勝出。
KNOWN_WRAPPER_KEYS = ['Items', 'items', 'PeopleItems', 'results', 'data', 'entries']

# Claude Code 「offload」殼（2026-09-14，複核 S3）：檔案太大時 Claude Code
# 把工具結果落成本機檔，形狀固定是
#   [{"type": "text", "text": "### Result\n<payload>\n### Page …"}]
# `<payload>` 可能是裸 JSON，也可能包一層 ```json fenced code block```；
# 兩種都要認。抓法：先找 `### Result` 這個標頭，內容取到下一個
# `\n### ` 標頭（或檔尾）為止；再看這段內容裡有沒有 fenced code block，
# 有就取 fence 內文，沒有就整段當 payload。解不出合法 JSON 一律丟
# `ValueError`，不悄悄原樣複製（那等於把殼字串當資料塞進下游）。
_OFFLOAD_RESULT_RE = re.compile(r'###\s*Result\s*\n(.*?)(?:\n###\s|\Z)', re.DOTALL)
_OFFLOAD_FENCE_RE = re.compile(r'```(?:json)?\s*\n(.*?)\n```', re.DOTALL)


def _extract_offload_payload(text):
    """從 offload 殼的 text 欄位裡切出 `### Result` 段落，回傳可能還沒
    解析的 JSON 字串（可能帶 fence）；找不到 `### Result` 標頭回 None。"""
    m = _OFFLOAD_RESULT_RE.search(text)
    if not m:
        return None
    body = m.group(1)
    fence = _OFFLOAD_FENCE_RE.search(body)
    return (fence.group(1) if fence else body).strip()


def _is_offload_shell(data):
    """判準刻意收緊：`data` 必須是**每一項**都是 `{"type": "text",
    "text": <str>}` 這個固定形狀（Claude Code offload 殼的實際樣子），
    不是「隨便一個 list 裡有個 dict 湊巧含 type/text 鍵」就中——避免把
    真正的站方 raw（裸陣列剛好有 type/text 欄位）誤判成殼。"""
    return bool(data) and all(
        isinstance(it, dict) and set(it.keys()) == {'type', 'text'}
        and it.get('type') == 'text' and isinstance(it.get('text'), str)
        for it in data)


_BARE_RAW_SHAPES = frozenset({'bare_list', 'offload_bare_list', 'ns_pipe_text'})
_DICT_RAW_SHAPES = frozenset({'dict_envelope', 'offload_dict_envelope'})


def _raw_from_payload(path, data, *, offload=False):
    """Classify a parsed JSON payload into RawLoadResult (no I/O)."""
    if isinstance(data, list):
        shape = 'offload_bare_list' if offload else 'bare_list'
        desc = (
            f'Claude Code offload 殼（### Result 內為裸陣列），{len(data)} 筆'
            if offload else
            f'裸陣列（無殼），{len(data)} 筆'
        )
        return RawLoadResult(
            items=data, shell_desc=desc, root_shape=shape,
            payload_key=None, envelope=None)
    if isinstance(data, dict):
        key, val = select_payload_key(data)
        if key is None:
            # entries.json is a flat ``{id: payload}`` map, not a broken list
            # envelope.  Make it directly inspectable/searchable and surface the
            # top-level key as ``id`` so callers do not have to hand-roll Python.
            material = [(item_id, payload) for item_id, payload in data.items()
                        if not str(item_id).startswith('_')]
            if material and all(isinstance(payload, (dict, str))
                                for _item_id, payload in material):
                items = []
                for item_id, payload in material:
                    row = dict(payload) if isinstance(payload, dict) else {'entry': payload}
                    row.setdefault('id', str(item_id))
                    items.append(row)
                return RawLoadResult(
                    items=items,
                    shell_desc=f'flat map（id→entry，共 {len(items)} 筆）',
                    root_shape='flat_map', payload_key=None, envelope=None)
            raise ValueError(
                f'{path} {val.message}。實際頂層鍵：{list(data.keys())}；'
                '若這是 entries.json，值必須是 object 或 entry 字串。')
        shape = 'offload_dict_envelope' if offload else 'dict_envelope'
        desc = (
            f'Claude Code offload 殼＋dict 殼，陣列在 "{key}" 鍵下，{len(val)} 筆'
            if offload else
            f'dict 殼，陣列在 "{key}" 鍵下，{len(val)} 筆'
        )
        return RawLoadResult(
            items=val, shell_desc=desc, root_shape=shape,
            payload_key=key, envelope=data)
    where = 'offload 殼內解出的內容' if offload else '頂層'
    raise ValueError(f'{path} {where}既非 list 也非 dict：{type(data)}')


def _load_raw_any(path):
    """讀 raw 檔，回傳 RawLoadResult。

    items：規範化後的裸陣列（list of dict）。
    shell_desc：人看得懂的殼型描述，供 unwrap/inspect 回報用；
    envelope：直接 dict 殼＝完整原始 root；offload dict 殼＝內層 dict。
    偵測不出已知殼型時丟 ValueError，附上實際看到的型別／鍵，不猜、不吞錯。
    """
    # 檔案打不開也要走 ValueError 這條路：呼叫端全都只接 ValueError，
    # 讓 OSError 逃出去只會噴一整段 traceback，agent 還得自己解讀
    # （2026-08-17 A2 測試抓到；unwrap／inspect／search 原本都有這個洞）。
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
    except OSError as e:
        raise ValueError(f'讀不到 {path}：{e}')

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        # NS 清單常見：不是 JSON，是 `id|日期` 逐行純文字（.json 副檔名誤導）。
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines and all('|' in ln for ln in lines[:5]):
            items = []
            for ln in lines:
                parts = ln.split('|', 1)
                items.append({'id': parts[0].strip(),
                              'created': parts[1].strip() if len(parts) > 1 else ''})
            return RawLoadResult(
                items=items,
                shell_desc=f'非 JSON，NS 純文字清單（id|日期），共 {len(items)} 行',
                root_shape='ns_pipe_text', payload_key=None, envelope=None)
        raise ValueError(
            f'{path} 不是合法 JSON，也不像 NS 的 id|日期 純文字清單。'
            f'原始錯誤：{e}；前 200 字元：{text[:200]!r}'
        )

    if isinstance(data, list) and _is_offload_shell(data):
        combined = '\n'.join(it['text'] for it in data)
        payload_str = _extract_offload_payload(combined)
        if payload_str is None:
            raise ValueError(
                f'{path} 看起來是 Claude Code offload 殼（type/text 陣列），'
                f'但找不到 "### Result" 標頭，解不出實際內容')
        try:
            inner = json.loads(payload_str)
        except json.JSONDecodeError as e:
            raise ValueError(
                f'{path} 是 offload 殼，"### Result" 段落解不出合法 JSON：{e}；'
                f'片段：{payload_str[:200]!r}')
        return _raw_from_payload(path, inner, offload=True)

    return _raw_from_payload(path, data, offload=False)


def cmd_unwrap(args):
    try:
        loaded = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ 卸殼失敗：{e}', file=sys.stderr)
        sys.exit(1)
    items, shell_desc = loaded.items, loaded.shell_desc
    meta_keys = [k for k in loaded.envelope_meta]
    if meta_keys:
        print(f'unwrap 將移除 root metadata：{", ".join(meta_keys)}',
              file=sys.stderr)

    if shell_desc.startswith('裸陣列'):
        note = '無殼，原樣複製'
    else:
        note = f'已卸殼（{shell_desc}）'

    out = args.out
    if not out:
        base, ext = os.path.splitext(args.raw)
        out = f'{base}_unwrapped{ext or ".json"}'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f'{note} → 已寫入 {out}（{len(items)} 筆）')


def _id_of_any(item, index):
    # `edit`（T9，2026-08-25）：RT **detail** 檔的素材編號存在 `edit`，清單檔才是
    # `code`，於是 `SITE_SPEC['rt']['id_of']` 在 detail 上永遠回空字串、掉到這裡
    # 又撿不到，最後變成 `#index`——`--ids` 因此對 RT detail 形同不存在，agent
    # 只剩 `--index` 一則一則翻。0825-0100 那 15 次 `--index N --fields story`
    # 的根因就是這個（既有缺陷，非本次改動造成）。
    for key in ('id', 'code', 'edit', '_id', 'itemid', 'guid'):
        v = item.get(key)
        if not v:
            continue
        s = str(v)
        # ⚠️ `edit` 上游有**退化值**：實測 20260824 六份 rt_detail 裡有五份含裸前綴
        #    `'RT'`（沒有編號），1800 那份 39 筆裡就有 19 筆。撞名的 id 比沒有 id
        #    更糟——`--ids RT` 會一次撈到 19 筆（爆預算）、`dedup-check` 會**靜默**
        #    拿第一個比（比錯還不報錯），而改動前 `'RT'` 不是合法 id、是 fail-loud 的。
        #    1600 那份還有 `RTRT7400` 雙前綴，可見上游值本來就髒。
        if key == 'edit' and not re.search(r'\d', s):
            continue
        return s
    return f'#{index}'


def _title_of_any(item):
    # AP 清單原始檔（Items 殼卸完後）是 Elasticsearch 風格，實際欄位包在
    # `_source` 底下（`_source.caption.nitf` 才是標題），不是頂層。
    candidates = [item]
    if isinstance(item.get('_source'), dict):
        candidates.append(item['_source'])
    for cand in candidates:
        for key in ('head', 'title', 'desc', 'story', 'cap', 'entry', 'src_text', 'text'):
            v = cand.get(key)
            if isinstance(v, str) and v:
                return v if len(v) <= 100 else v[:100] + '...'
            if isinstance(v, dict) and v.get('nitf'):
                return v['nitf'][:100]
    return ''


# ── AP 的一層 nitf 殼：三條查詢路徑共用同一份攤平邏輯（A13，2026-08-18）──
#
# 🔴 **為什麼要抽出來**：AP 詳情 API 的 `script`／`caption` 不是字串，是
# `{'words': 89, 'nitf': '<p>SHOTLIST:</p>…'}` 這種一層 dict。本檔原本有三條路徑
# 各自處理（或不處理）這件事，結果彼此不一致：
#   ✅ `_title_of_any`／`cmd_search --field all`  → 會看穿 `.nitf`
#   ❌ `cmd_inspect --lengths`                    → 只挑 `isinstance(v, str)`，dict 直接漏掉
#   ❌ `cmd_search --field <指名欄位>`             → 同樣只認 str，指名 script 永遠 0 命中
#
# 0818-2200 實錯就是踩這個：AP API **明明成功**、15/15 筆的 `_source.script.nitf`
# 都有完整 SHOTLIST／SOUNDBITE，但 `inspect --lengths` 沒列出 script／caption、
# `search --field script` 回 0 命中，掃帶 agent 兩個訊號都看到「沒有」，於是判定
# 「AP API 缺欄位」，照 13c §1a 退 §1b **逐則開了 14 個詳情頁**——整段白做，
# AP 那站 12 則燒掉 89 次呼叫／10.5 分（前一輪 14 則只要 31 次／5.7 分）。
# ⛔ **工具答錯比沒有工具更糟**：agent 沒有違規，它是照著工具給的答案做判斷的。
# 所以修法是把攤平邏輯收成這兩支共用 helper，不要再讓任何一條路徑自己寫一份。

def _nitf_text(value):
    """AP 一層 dict 殼 → 內文字串；不是這個形狀就回 None。"""
    if isinstance(value, dict) and isinstance(value.get('nitf'), str):
        return value['nitf']
    return None


def flatten_text_fields(item):
    """一筆 item 的所有文字欄位 → `[(欄位名, 文字)]`，含攤平後的 `{k}.nitf`。

    順序：先原生字串欄位，再 `.nitf`——跟 `cmd_search --field all` 原本的行為一致，
    改用本函式後輸出不變（既有測試據此把關）。
    """
    out = [(k, v) for k, v in item.items() if isinstance(v, str)]
    out += [(f'{k}.nitf', t) for k, v in item.items()
            if (t := _nitf_text(v)) is not None]
    return out


def text_field(item, key):
    """查某個具名欄位的文字內容，回傳 `(顯示名, 文字, 狀態)`。

    狀態三分，**呼叫端要能講出不同的話**——0818-2200 的誤導有一半來自
    「欄位不存在」與「欄位在、只是不是字串」共用同一句 `<無此欄位或非文字>`：
      `'str'`     欄位本身就是字串
      `'nitf'`    欄位是 AP 的 dict 殼，已取出 `.nitf`（顯示名會變成 `key.nitf`）
      `'absent'`  真的沒有這個欄位
      `'nontext'` 欄位存在但既非字串也不是 nitf 殼（例如 `shots` 是 list）
    """
    if key not in item:
        return (key, None, 'absent')
    v = item[key]
    if isinstance(v, str):
        return (key, v, 'str')
    t = _nitf_text(v)
    if t is not None:
        return (f'{key}.nitf', t, 'nitf')
    return (key, None, 'nontext')


def _plan_full_detail(shown, fields, site):
    """決定這批 `--fields` 查詢能不能**整批印全文**；塞不下就備妥可直接貼的分批指令。

    回傳 `(cap, note)`：`cap` 是每個欄位的截斷長度，`None`＝不截斷（整批全文）。
    `note` 不是 None 時，呼叫端要原樣印到 stderr。

    為什麼要有這個（T9，2026-08-25）：原本的判準是
    `fields is not None and len(indexed) <= 3`——**只有查 ≤3 筆才印全文**，於是
    「我要看完整 script」在操作上就等於「一次只能查 3 筆」。0825-0100 實測 56 次
    `inspect` 裡 **31 次是一次只看一則**（`ap_detail` 連續 11 次同 `--fields script`、
    `rt_detail` 連續 15 次 `--index N --fields story`，其中兩次參數完全重複），
    每次呼叫 ≈ 296k cache_read ≈ **$0.089**，光這一輪就 ≈ $2.5。

    ⛔ 塞不下時**不靜默截斷**——會明講並印出下一步指令。R15 的教訓是靜默截斷
    會讓 agent 合理地退回逐則查詢，那正是這一刀要消滅的形狀。
    """
    # ⚠️ 量的是**序列化後**的長度，不是 raw `len(v)` 總和——保證要落在真正印出去的
    #    那串位元組上。JSON escape（`\n` 變兩字元、引號）實測讓 NS 型內容膨脹 4.9%，
    #    近飽和時足以把「宣告整批全文」的輸出推破 Bash 的 30k 靜默截斷線。
    #    順帶解掉 dict 欄位（AP 的 nitf 殼）被算成 0 的洞：`json.dumps` 會把整包算進去。
    total_len, fit_ids = 0, []
    for i, it in shown:
        item_id = _dedup_id(site, it, i)
        one = len(json.dumps({k: it.get(k, '<無此欄位>') for k in fields},
                             ensure_ascii=False)) + len(item_id) + 2  # id + \t + \n
        if total_len + one > INSPECT_TEXT_BUDGET:
            break
        fit_ids.append(item_id)
        total_len += one
    if len(fit_ids) == len(shown):
        return None, None
    if not fit_ids:
        # 第一則自己就超過預算（RT 的 TIMELINE 長稿實測有 30,270 字元）。
        # ⛔ 這裡**不能**掉到 200 字元預覽——舊制單則查是印全文的，掉下去等於
        #    agent 再也拿不到這則的內容，是功能退步。改成截到預算為止，
        #    拿到的量跟舊制被工具攔下時差不多，但這次有明講截在哪。
        return INSPECT_TEXT_BUDGET, (
            f'ℹ️ 第一則的 {",".join(fields)} 自己就超過 {INSPECT_TEXT_BUDGET:,} 字元預算，'
            f'已截到預算為止（**不是**全文）。這種長稿逐則查是對的。')
    head = (f'ℹ️ 這 {len(shown)} 筆的 {",".join(fields)} 全文超過 {INSPECT_TEXT_BUDGET:,} '
            f'字元預算，已改印 {INSPECT_PREVIEW_CHARS} 字元預覽（**不是**全文）。')
    # ⚠️ 沒帶 `--site` 時 `_dedup_id` 回退成 `#index`，那不是能貼回 `--ids` 的東西
    #    ——印出來會變成一條**跑不動的**建議指令，比不給建議更糟。
    # ⚠️ 認不出 id 的筆數會是 `#N` 序號——那**也是可以貼回 `--ids` 的**（`cmd_inspect`
    #    一律受理 `#N`），所以不必因此拒絕給建議，照樣印出去就好。
    # 🔴 建議指令必須 **round-trip**：貼回去要剛好撈到這幾筆，不能多。
    #    id 撞名時貼回去會撈到一整群 → 再度爆預算 → 再印同一條壞建議，**不收斂**，
    #    agent 照做只是白燒呼叫，正好是這一刀要救的那條路。寧可不給建議，
    #    也不要給一條跑起來不對的指令。
    want = set(fit_ids)
    hit = sum(1 for i, it in shown if _dedup_id(site, it, i) in want)
    if len(want) != len(fit_ids) or hit != len(fit_ids):
        return INSPECT_PREVIEW_CHARS, (
            f'{head}\n'
            f'   ⚠️ 這個檔的 id 有重複，貼回 `--ids` 會撈到多餘的筆數，'
            f'因此不給分批指令。請改用 `--limit`／`--index` 逐段取。')
    return INSPECT_PREVIEW_CHARS, (
        f'{head}\n'
        f'   要全文請分批，前 {len(fit_ids)} 筆可一次取：\n'
        f'   --ids {",".join(fit_ids)}')


def _inspect_ids(values):
    """Normalize inspect's comma- and whitespace-separated ``--ids`` forms."""
    if not values:
        return set()
    if isinstance(values, str):
        values = [values]
    return {item.strip()
            for value in values
            for item in value.split(',')
            if item.strip()}


def cmd_inspect(args):
    try:
        loaded = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)
    items, shell_desc = loaded.items, loaded.shell_desc
    print(f'# {args.raw}：{shell_desc}', file=sys.stderr)

    site = getattr(args, 'site', None)
    # id 與欄位一律走 `_dedup_view` 合併視圖：AP 清單檔是 ES 形狀（欄位包在
    # `_source` 底下、頂層 `_id` 是雜湊），不看穿的話 `--ids AP5467681` 找不到、
    # `--fields` 全回「無此欄位」，agent 只會彈回 python -c（0817-2200 實測，
    # D9 步驟②的前置條件）。
    indexed = [(i, _dedup_view(it) if isinstance(it, dict) else {'value': it})
               for i, it in enumerate(items)]

    if args.index is not None:
        if not (0 <= args.index < len(items)):
            print(f'✗ --index {args.index} 超出範圍（共 {len(items)} 筆，0-based）', file=sys.stderr)
            sys.exit(1)
        indexed = [indexed[args.index]]
    elif args.ids:
        want = _inspect_ids(args.ids)
        # `#N` 序號定址一律受理：id 撲空時本工具自己就是印 `#0…#N`，只認真 id
        # 會讓自己印出來的東西貼不回去（RT detail 補了 `edit` 之後實測到的回歸）。
        indexed = [(i, it) for i, it in indexed
                   if _dedup_id(site, it, i) in want or f'#{i}' in want]
        found = set(_dedup_id(site, it, i) for i, it in indexed)
        found |= set(f'#{i}' for i, _ in indexed)
        missing = want - found
        if missing:
            print(f'⚠️ 找不到這些 id：{", ".join(sorted(missing))}', file=sys.stderr)

    fields = [f.strip() for f in args.fields.split(',')] if args.fields else None
    lengths = getattr(args, 'lengths', False)

    total = len(indexed)
    shown = _slice_inspect_rows(indexed, args)
    offset = getattr(args, 'offset', 0) or 0
    limit = args.limit or 100

    # 全文 vs 預覽改由**字元預算**決定，不再由筆數決定（T9，見 _plan_full_detail）。
    # `cap` 是每欄位截斷長度，None＝整批全文。
    cap, budget_note = (
        _plan_full_detail(shown, fields, site) if (fields and not lengths)
        else (INSPECT_PREVIEW_CHARS, None))

    lines = []
    for i, it in shown:
        item_id = _dedup_id(site, it, i)
        if lengths:
            # 字數模式：只印長度不印內容（例：檢查摘要有沒有超過 150 字）。
            # 這是 D9 查出的工具缺口——以前 agent 只能自己寫 python 數。
            # ⚠️ A13（2026-08-18）：這裡原本只挑 `isinstance(v, str)`，AP 的
            # `script`／`caption` 是 `{'words':N,'nitf':…}` dict，**整個沒被列出**，
            # 讓 agent 以為站方沒給稿。改走 `flatten_text_fields`／`text_field`
            # 共用 helper（見其上方大段說明），三條查詢路徑對齊。
            if fields:
                parts = []
                for k in fields:
                    name, text, state = text_field(it, k)
                    if text is not None:
                        parts.append(f'{name}=len:{len(text)}')
                    elif state == 'nontext':
                        # 跟「沒有這個欄位」講不同的話：欄位在，只是不是文字，
                        # 合起來講會被讀成「站方沒給」——那正是 0818-2200 的誤導源頭。
                        parts.append(f'{k}=<欄位存在但非文字>')
                    else:
                        parts.append(f'{k}=<無此欄位>')
                lines.append(f'{item_id}\t' + ' '.join(parts))
            else:
                flds = [(n, t) for n, t in flatten_text_fields(it)
                        if t and not n.startswith('_')]
                if not flds:
                    lines.append(f'{item_id}\t（無可量長度的文字欄位）')
                else:
                    lines.append(f'{item_id}\t' + ' '.join(
                        f'{n}=len:{len(t)}' for n, t in sorted(flds)))
        elif fields:
            picked = {}
            for k in fields:
                v = it.get(k, '<無此欄位>')
                if isinstance(v, str) and cap and len(v) > cap:
                    v = v[:cap] + '...[略]'
                picked[k] = v
            lines.append(f'{item_id}\t{json.dumps(picked, ensure_ascii=False)}')
        else:
            lines.append(f'{item_id}\t{_title_of_any(it)}')

    print('\n'.join(lines))
    if total > offset + limit:
        print(f'…另 {total - offset - limit} 筆略，用 --offset/--limit 調整', file=sys.stderr)
    print(f'共 {len(items)} 筆，本次顯示 {len(shown)} 筆（offset={offset}）', file=sys.stderr)
    if budget_note:
        print(budget_note, file=sys.stderr)
    # 逐則翻閱的觸發點（T9）。比照 A10 v2 的 T/C 覆蓋率閘門：光把「請批次」寫進
    # 規則檔沒有用（0824-2000 實證「載入 ≠ 遵守」），要在**用到的當下**給提示。
    elif fields and total == 1 and len(items) > 1:
        print(f'💡 這次只看了 1 則，同檔還有 {len(items) - 1} 筆。'
              f'`--ids a,b,c` 可一次取多則，總長吃得下 {INSPECT_TEXT_BUDGET:,} 字元'
              f'就整批印全文——分開叫每次都要重付一次 context。', file=sys.stderr)


def _slice_inspect_rows(indexed, args):
    """Apply the discoverable ``--offset``/``--limit`` window used by inspect."""
    offset = getattr(args, 'offset', 0) or 0
    if offset < 0:
        raise ValueError('--offset 必須是 0 或正整數（0-based）。')
    limit = getattr(args, 'limit', None) or 100
    return indexed[offset:offset + limit]


def cmd_search(args):
    try:
        loaded = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)
    items, shell_desc = loaded.items, loaded.shell_desc
    print(f'# {args.raw}：{shell_desc}', file=sys.stderr)

    if args.field == 'all':
        field_candidates = None  # 每筆的所有字串欄位都搜
    elif args.field == 'script':
        field_candidates = ['script', 'story']  # RT 用 story 取代 script
    else:
        field_candidates = {
            'story': ['story', 'script'],
            'head': ['head', 'title'],
        }.get(args.field, [args.field])

    needle = args.contains.lower()
    site = getattr(args, 'site', None)
    hits = []
    for i, raw_it in enumerate(items):
        # 同 inspect：走 `_dedup_view` 看穿 AP 的 `_source` 殼，否則 AP 清單檔
        # 頂層沒有任何字串欄位，search 永遠空手（D9 步驟②前置）。
        it = _dedup_view(raw_it) if isinstance(raw_it, dict) else {}
        item_id = _dedup_id(site, it, i)
        # AP 的標題／內文在 `caption.nitf`／`script.nitf` 這種一層 dict 底下，
        # 一併攤出來搜（A13 起改走共用 helper，見其上方說明）。
        if field_candidates is None:
            fields_to_check = flatten_text_fields(it)
        else:
            # ⚠️ A13：這條**指名欄位**的路徑原本只認 `isinstance(str)`，於是
            # `search --contains SOUNDBITE --field script` 在 AP 檔上永遠 0 命中
            # （script 是 dict）——跟 `--field all` 行為不一致，同一份檔案換個參數
            # 就得到相反的答案。改用 `text_field` 後兩條路徑一致。
            fields_to_check = []
            for k in field_candidates:
                name, text, _ = text_field(it, k)
                if text is not None:
                    fields_to_check.append((name, text))
        for field_name, text in fields_to_check:
            pos = text.lower().find(needle)
            if pos == -1:
                continue
            start = max(0, pos - 40)
            end = min(len(text), pos + len(args.contains) + 40)
            snippet = text[start:end].replace('\n', ' ')
            hits.append(f'{item_id}\t[{field_name}]\t...{snippet}...')

    limit = args.limit or 100
    shown = hits[:limit]
    print('\n'.join(shown) if shown else '（無命中）')
    if len(hits) > limit:
        print(f'…另 {len(hits) - limit} 筆命中略，用 --limit 調整', file=sys.stderr)
    print(f'共 {len(items)} 筆項目，命中 {len(hits)} 處', file=sys.stderr)


def cmd_check_entries(args):
    """Delegate the commonly guessed command to the canonical platform validator."""
    try:
        with open(args.entries, encoding='utf-8-sig') as f:
            entries = json.load(f)
    except (OSError, ValueError) as exc:
        print(f'✗ check-entries 讀取失敗：{exc}', file=sys.stderr)
        sys.exit(2)
    import s2_platform_extract
    problems = s2_platform_extract.check_entries(entries)
    if problems:
        print('⛔ entries 形狀預檢未通過：', file=sys.stderr)
        for problem in problems:
            print(f'  • {problem}', file=sys.stderr)
        sys.exit(2)
    print('✅ entries 形狀預檢通過。', file=sys.stderr)


# ── 稽核快照與比對（A2，2026-08-17）──────────────────────────

# ENEX／ABC 只在 `concat --site` 的去重用得到（兩站的 raw→候選檔走
# `s2_platform_extract.py`，不經 SITE_SPEC 的 dump／build）。所以**不塞進
# SITE_SPEC**——那份的每個鍵都被 dump／build 當必備欄位讀，補半套只會讓
# `--site abc dump` 死在 KeyError，比現在的 invalid choice 更難查。
# 🔴 2026-09-05（0905-0430）：ABC 進固定輪後，agent 要合併分頁清單時
# `concat --site abc` 回 invalid choice，只能改用不去重的純合併。
PLATFORM_ID_OF = {
    'abc': lambda it: (str(it.get('News Story') or it.get('storyNumber') or '').strip()
                       and 'ABC' + str(it.get('News Story')
                                       or it.get('storyNumber')).strip()),
    'enex': lambda it: (str(it.get('id') or it.get('itemId') or '').strip()
                        and 'ENEX' + str(it.get('id') or it.get('itemId')).strip()
                        .removeprefix('ENEX')),
}


def _site_id_of(site, item, index):
    """有 --site 就走 per-site adapter（RT 用 `code` 不是 `id`），
    沒有就走通用猜測。猜測只在沒指定站別時用，指定了就以規則為準。"""
    if site in PLATFORM_ID_OF:
        return PLATFORM_ID_OF[site](item) or _id_of_any(item, index)
    if site:
        return SITE_SPEC[site]['id_of'](item) or _id_of_any(item, index)
    return _id_of_any(item, index)


def cmd_snapshot(args):
    """把一份 raw 檔壓成穩定、可事後比對的純文字快照。

    用途是稽核留痕：這一輪站方清單「當時長什麼樣」。之後對帳有爭議時
    可以直接比兩份快照，不必重開瀏覽器重抓。"""
    try:
        loaded = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)
    items, shell_desc = loaded.items, loaded.shell_desc
    env_cp = loaded.envelope_meta.get('checkpoint')
    cli_cp = getattr(args, 'checkpoint', None)
    if env_cp not in (None, '') and cli_cp not in (None, '') and str(env_cp) != str(cli_cp):
        print(f'✗ snapshot checkpoint 衝突：檔內 {env_cp} vs CLI {cli_cp}',
              file=sys.stderr)
        sys.exit(2)

    out = args.out
    if not out:
        if not args.checkpoint:
            print('✗ 要嘛給 --out，要嘛給 --checkpoint（用來組 _audit_{site}_{HHMM}.txt）',
                  file=sys.stderr)
            sys.exit(1)
        hhmm = args.checkpoint.split('-')[-1]
        site = args.site or 'raw'
        out = os.path.join(os.path.dirname(os.path.abspath(args.raw)),
                           f'_audit_{site}_{hhmm}.txt')

    # 護欄：**不覆寫舊快照**。快照的價值就在於它是當時的樣子，
    # 覆寫掉等於把稽核依據銷毀，而且是靜默銷毀。
    if os.path.exists(out):
        print(f'✗ {out} 已存在，快照不覆寫舊檔（那會靜默銷毀稽核依據）。'
              f'要另存請給不同的 --out', file=sys.stderr)
        sys.exit(1)

    lines = [
        f'# 來源：{os.path.basename(args.raw)}',
        f'# 殼型：{shell_desc}',
        f'# 站別：{args.site or "（未指定，id 用通用猜測）"}',
        f'# 輪次：{args.checkpoint or "（未指定）"}',
        f'# 筆數：{len(items)}',
        '',
    ]
    for i, raw_it in enumerate(items):
        # 同 inspect／search：AP 清單檔（ES 形狀）要看穿 `_source`，否則快照
        # 印出的是 `_id` 雜湊，agent 對不回 state 只能自己重造（0817-2200 實錯）。
        it = _dedup_view(raw_it) if isinstance(raw_it, dict) else {}
        item_id = _dedup_id(args.site, it, i)
        desc = _title_of_any(it)
        if not desc:
            # 清單檔常常只有 `code` ＋ `at`（沒有標題欄）。這種時候印剩下的短欄位，
            # 比留一整排空白有用——快照的用途是「當時清單長什麼樣」。
            desc = ' '.join(
                f'{k}={v}' for k, v in it.items()
                if k != 'id' and not k.startswith('_')
                and isinstance(v, (str, int, float, bool))
                and len(str(v)) <= 40 and str(v) != item_id)
        lines.append(f'{item_id}\t{desc}')

    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'快照已寫入 {out}（{len(items)} 筆）')


# 三站清單各自的「上站時間」欄位＋格式。NS `created`＝ISO 帶微秒 UTC（13c/13d §8：
# `created: it.createdDate`）；AP `ts`＝ISO 秒 UTC（13c §2：`ts: s.firstcreated`）；
# RT `at`＝DOM 直接擷取的 `MM/DD/YYYY HH:MM`。
#
# 🔴 **2026-09-19 再訂正（0919-1700 輪現場覆核，推翻 0831 那次訂正）**：0831
# 那次改成 `utc: True` 的證據只查了 08/30 單一輪，且落地時間差（16:08 vs
# 07:57 的 8h11m）跟 AP 交叉比對的 19 分鐘落差本身就不精確。這次拉了
# 2026-08-11～09-18 全部歷史 `rt_list_*.json`（近 40 輪）逐輪核對：RT `at`
# 從有記錄以來**從未是 UTC**，每一輪的最大值都直接吻合擷取當下的台北時鐘
# （誤差幾分鐘內，屬清單截圖延遲，不是時區差）。0831 訂正上線後
# `timeline --site rt` 已經連續約 20 天輸出錯誤（多加 8 小時），但因為
# `timeline` 是純唯讀診斷指令、沒有被 `build`/`audit`/硬閘門等自動化流程
# 呼叫，沒有造成實際漏收——是未爆彈，不是已引爆的資料錯誤。**改回 RT `at`
# 免轉**，並在 `cmd_timeline` 加自我檢查：換算後若最大值離現在太遠就示警，
# 不要再靠人工翻歷史檔才發現。
TIMELINE_SPEC = {
    'ns': {'fields': ('created', 'createdDate'), 'utc': True,
           'fmt': '%Y-%m-%dT%H:%M:%S.%fZ'},
    'ap': {'fields': ('ts', 'firstcreated'), 'utc': True,
           'fmt': '%Y-%m-%dT%H:%M:%SZ'},
    'rt': {'fields': ('at',), 'utc': False, 'fmt': '%m/%d/%Y %H:%M'},
}

# `cmd_timeline` 自我檢查用：換算後最大值若比現在早/晚超過這麼多小時，代表
# `utc` 假設很可能又猜錯了（RT 0831→0919 那次錯了 20 天沒人發現，就是因為
# 沒有這道警告）。只示警不擋，因為 timeline 本來就是唯讀診斷工具。
TIMELINE_SANITY_HOURS = 3


def _parse_ts(raw_ts, spec):
    """回傳台北當地時間字串 `MM/DD/YYYY HH:MM`，解析失敗回 None（不猜、不吞）。"""
    if not raw_ts:
        return None
    if not spec['utc']:
        return raw_ts.strip() or None
    fmts = [spec['fmt'], '%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ',
            '%m/%d/%Y %H:%M']
    for fmt in fmts:
        try:
            dt = datetime.datetime.strptime(raw_ts, fmt) + datetime.timedelta(hours=8)
            return dt.strftime('%m/%d/%Y %H:%M')
        except ValueError:
            continue
    return None


def cmd_timeline(args):
    """把一份 raw 檔轉成「id｜台北當地時間」清單，供跨站對帳（窗內外／有沒有
    銜接落差）用。取代 0730 那種自寫 `_mk_*_snapshot.py` 逐站算時區的臨時腳本——
    三站欄位名與是否要 +8h 全部寫死在 TIMELINE_SPEC，不必每輪重寫換算邏輯。"""
    try:
        loaded = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)
    items, shell_desc = loaded.items, loaded.shell_desc
    meta = loaded.envelope_meta
    ctx_cp = meta.get('checkpoint') or getattr(args, 'checkpoint', None)
    ctx_lab = meta.get('checkpoint_label') or getattr(args, 'checkpoint_label', None)
    ctx_rid = meta.get('run_id') or getattr(args, 'run_id', None)
    if ctx_cp or ctx_lab or ctx_rid:
        print(f'# checkpoint: {ctx_cp or ""}')
        print(f'# checkpoint_label: {ctx_lab or ""}')
        print(f'# run_id: {ctx_rid or ""}')

    spec = TIMELINE_SPEC[args.site]
    rows = []
    no_ts = []
    for i, raw_it in enumerate(items):
        it = _dedup_view(raw_it) if isinstance(raw_it, dict) else {}
        item_id = _dedup_id(args.site, it, i)
        raw_ts = next((it[f] for f in spec['fields'] if it.get(f)), None)
        local = _parse_ts(raw_ts, spec)
        if local is None:
            no_ts.append(item_id)
        rows.append((item_id, local or ''))

    # 依時間排序（沒有時間的排最後，方便一眼看出哪些缺時間）——跟 raw 原始
    # 順序無關，跨站對帳要的是時間軸，不是抽取順序。
    rows.sort(key=lambda r: (r[1] == '', r[1]))

    lines = [f'{iid}|{ts}' for iid, ts in rows]
    out = args.out
    if out:
        with open(out, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        print(f'時間軸已寫入 {out}（{len(rows)} 筆，{shell_desc}）', file=sys.stderr)
    for ln in lines:
        print(ln)
    if no_ts:
        print(f'⚠️ {len(no_ts)} 筆解不出時間（欄位缺或格式不符，見 {spec["fields"]}）：'
              f'{", ".join(no_ts[:20])}', file=sys.stderr)

    parsed_ts = [ts for _, ts in rows if ts]
    if parsed_ts:
        try:
            max_dt = max(datetime.datetime.strptime(ts, '%m/%d/%Y %H:%M') for ts in parsed_ts)
        except ValueError:
            max_dt = None
        if max_dt is not None:
            delta_h = (max_dt - datetime.datetime.now()).total_seconds() / 3600
            if abs(delta_h) > TIMELINE_SANITY_HOURS:
                direction = '未來' if delta_h > 0 else '過去'
                print(f'⚠️ 換算後最新一筆時間 {max_dt.strftime("%m/%d %H:%M")} '
                      f'比現在偏{direction} {abs(delta_h):.1f} 小時，'
                      f'TIMELINE_SPEC 對 {args.site} 的 utc 假設可能猜錯，先別當真、回頭核對 raw 值。',
                      file=sys.stderr)


# 各站原始 detail 檔裡，正文欄位的名字（依序嘗試，第一個有內容的勝出）——
# 跟 SITE_SPEC 的 src_text_of 是同一組欄位，只是這裡不強制併成固定格式，
# 讓 fill-src-text 用 raw 的「一個」欄位就好（多欄位ときは join）。
FILL_SRC_FIELDS = {
    'ns': ('desc', 'script'),
    'ap': ('head', 'script'),
    'rt': ('head', 'story'),
}


def cmd_fill_src_text(args):
    """把 raw／detail 檔的正文，依 id 對應填進 batch.json 的 `src_text` 欄位——
    取代 0818/0820/0825/0828/0829 反覆出現的 `_merge_src_*.py`／`_fill_*srctext.py`／
    `_fix_src_*.py` 這批臨時腳本（都是同一件事：raw 有正文、batch 還沒填，逐 id 對應
    貼過去）。**只填空的**，不覆寫 batch 裡已經有內容的 `src_text`（避免蓋掉手動修過
    的原文）。"""
    try:
        raw_loaded = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ raw 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)
    raw_items, raw_shell = raw_loaded.items, raw_loaded.shell_desc
    try:
        batch_loaded = _load_raw_any(args.batch)
    except ValueError as e:
        print(f'✗ batch 讀不到：{e}', file=sys.stderr)
        sys.exit(1)
    batch = batch_loaded.items
    if not isinstance(batch, list):
        print(f'✗ {args.batch} 頂層不是陣列，不像 add-batch 用的 batch.json', file=sys.stderr)
        sys.exit(1)

    fields = ([f.strip() for f in args.fields.split(',') if f.strip()]
              if args.fields else list(FILL_SRC_FIELDS[args.site]))

    # 保留第一次出現的那筆、重複的丟掉並警告——跟 dedup_by_id／build 同一套
    # 規則（2026-08-31 review 修正：原本後面的會靜默蓋掉前面的，沒有任何提示）。
    raw_by_id = {}
    dup_ids = []
    for i, raw_it in enumerate(raw_items):
        it = _dedup_view(raw_it) if isinstance(raw_it, dict) else {}
        rid = _dedup_id(args.site, it, i)
        if rid in raw_by_id:
            dup_ids.append(rid)
            continue
        raw_by_id[rid] = it
    if dup_ids:
        print(f'⚠️ raw 裡有重複 id，只保留第一次出現的那筆：{", ".join(dup_ids)}',
              file=sys.stderr)

    filled, already, missing = [], [], []
    for item in batch:
        iid = item.get('id')
        if item.get('src_text'):
            already.append(iid)
            continue
        r = raw_by_id.get(iid)
        if not r:
            missing.append(iid)
            continue
        parts = [str(r[f]) for f in fields if r.get(f)]
        if not parts:
            missing.append(iid)
            continue
        item['src_text'] = truncate('\n---\n'.join(parts))
        filled.append(iid)

    out = args.out or args.batch
    written = batch_loaded.with_items(batch)
    payload = serialize_raw_result(written)
    with open(out, 'w', encoding='utf-8') as f:
        # indent=2 對齊 build 的輸出格式（2026-08-31 review 修正：原本 indent=1，
        # 就地覆寫時會把整份 batch.json 的排版跟 build 的產物不一致）。
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f'已寫入 {out}（raw：{raw_shell}）', file=sys.stderr)
    print(f'填入 {len(filled)} 則：{", ".join(filled) if filled else "（無）"}')
    if already:
        print(f'已有 src_text 未動 {len(already)} 則：{", ".join(already)}', file=sys.stderr)
    if missing:
        print(f'⚠️ raw 裡找不到或欄位都空、沒填到 {len(missing)} 則'
              f'（要嘛 id 對不起來、要嘛 raw 那批本來就沒收這幾則）：'
              f'{", ".join(missing)}', file=sys.stderr)


def cmd_collate_category(args):
    """把一批（或多批）batch.json 裡各則自己標好的 `category`
    （`{"大分類":…, "中主題":…, "小分題":…}`）收成一條可以直接貼給
    `s2_state.py set-category --pairs` 的字串。取代 0810／0827-1000 那種
    `run_setcat_1000.py`／`_tmp_ns_cat.py`——手動把三站 batch 掃過一遍拼字串
    再自己 subprocess 呼叫 set-category 的臨時腳本。**只組字串，不呼叫
    set-category**——送不送、送之前要不要再看一眼，仍是 agent 的判斷。"""
    pairs = []
    skipped = []
    for path in args.batches:
        try:
            with open(path, encoding='utf-8') as f:
                items = json.load(f)
        except OSError as e:
            print(f'✗ 讀不到 {path}：{e}', file=sys.stderr)
            sys.exit(1)
        if isinstance(items, dict) and isinstance(items.get('entries'), list):
            items = items['entries']   # P1b-2 新格式殼
        if not isinstance(items, list):
            print(f'✗ {path} 頂層不是陣列，不像 batch.json', file=sys.stderr)
            sys.exit(1)
        for item in items:
            iid = item.get('id')
            cat = item.get('category') or {}
            if isinstance(cat, str):   # R25：batch 的 category 也可能是字串「大/中/小」
                _p = [x.strip() for x in cat.split('/', 2)] + ['', '', '']
                cat = {'大分類': _p[0], '中主題': _p[1], '小分題': _p[2]}
            big, mid, sub = cat.get('大分類'), cat.get('中主題'), cat.get('小分題')
            if not (big and mid):
                skipped.append(iid or f'({path} 裡無 id 的一筆)')
                continue
            seg = f'{big}/{mid}' + (f'/{sub}' if sub else '')
            pairs.append(f'{iid}={seg}')

    if not pairs:
        print('✗ 一則可用的 category 都沒收到——batch.json 裡的 items 要先自己標好'
              ' `category` 欄位，這支只負責收集、不負責判斷分類', file=sys.stderr)
        sys.exit(1)

    print(';'.join(pairs))
    print(f'共 {len(pairs)} 則可送出', file=sys.stderr)
    if skipped:
        print(f'⚠️ {len(skipped)} 則缺 category（或缺大分類／中主題），沒收進來：'
              f'{", ".join(str(s) for s in skipped)}', file=sys.stderr)


def _concat_shape_group(shape):
    if shape in _BARE_RAW_SHAPES:
        return 'bare'
    if shape in _DICT_RAW_SHAPES:
        return 'dict'
    return None


def cmd_concat(args):
    """把兩份以上的 json 陣列檔案（分頁清單、多來源分批的 batch 等）合併成一份。
    取代 0813／0814／0820／0821／0825／0827／0829／0831 反覆出現的
    `python -c "a=json.load(...); b=json.load(...); json.dump(a+b, ...)"`
    這批臨時合併腳本——出現頻率比 fill-src-text 還高（23 個命中／約 9-10 個
    不同日期），形狀卻更單純：純粹合併陣列，頂多再去重，沒有 timeline 那種
    per-site 時區假設要猜（那次猜錯過一次，這支刻意不猜任何語意）。

    給 `--site` 才會去重（保留第一次出現的 id，其餘丟棄並警告）；不給就是
    純合併、保留全部（例如合併 batch.json 這種本來就不該去重的用途）。

    dict 殼必須同 payload_key、同形狀組；未知 metadata 型別敏感 deep-equal，
    衝突 exit 2 且不寫檔。"""
    loaded_list = []
    for path in args.files:
        try:
            loaded = _load_raw_any(path)
        except ValueError as e:
            print(f'✗ 讀取失敗 {path}：{e}', file=sys.stderr)
            sys.exit(1)
        loaded_list.append((path, loaded))

    groups = [_concat_shape_group(ld.root_shape) for _, ld in loaded_list]
    if any(g is None for g in groups) or len(set(groups)) > 1:
        print('✗ concat root_shape 不相容：'
              + '、'.join(f'{os.path.basename(p)}={ld.root_shape}'
                          for p, ld in loaded_list),
              file=sys.stderr)
        sys.exit(2)
    keys = {ld.payload_key for _, ld in loaded_list}
    if len(keys) > 1:
        print('✗ concat payload_key 不相容：'
              + '、'.join(f'{os.path.basename(p)}={ld.payload_key!r}'
                          for p, ld in loaded_list),
              file=sys.stderr)
        sys.exit(2)

    merged, err = merge_concat_metadata(
        [(path, loaded.envelope_meta) for path, loaded in loaded_list])
    if err:
        print(err, file=sys.stderr)
        sys.exit(2)

    all_items = []
    shells = []
    for path, loaded in loaded_list:
        shells.append(f'{os.path.basename(path)}（{loaded.shell_desc}）')
        all_items.extend(loaded.items)

    dup_ids = []
    if args.site:
        seen = {}
        kept = []
        for i, it in enumerate(all_items):
            view = _dedup_view(it) if isinstance(it, dict) else {}
            rid = _dedup_id(args.site, view, i)
            if rid in seen:
                dup_ids.append(rid)
                continue
            seen[rid] = True
            kept.append(it)
        all_items = kept

    keep_shell = groups[0] == 'dict'
    if keep_shell:
        first = next(ld for _, ld in loaded_list if ld.envelope is not None)
        env = copy.deepcopy(first.envelope)
        payload_key = first.payload_key
        payload = {}
        for k in env:
            if k == payload_key:
                payload[k] = all_items
            elif k in merged:
                payload[k] = merged[k]
        for k, v in merged.items():
            if k not in payload:
                payload[k] = v
        _note = '，新格式外殼保留'
    else:
        payload = all_items
        _note = ''
    out = args.out
    if out:
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f'已寫入 {out}（{len(all_items)} 筆{_note}，來源：{"、".join(shells)}）',
              file=sys.stderr)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f'共 {len(all_items)} 筆{_note}（來源：{"、".join(shells)}）', file=sys.stderr)
    if dup_ids:
        print(f'⚠️ 給了 --site，去重時丟掉 {len(dup_ids)} 個重複 id（保留第一次出現的）：'
              f'{", ".join(dup_ids)}', file=sys.stderr)


# batch 每筆該有的欄位。src_text 是 13d §5 的鐵律（事後查證的唯一依據），
# 漏帶過兩次整批（0812-2200 的 65 則、0813-1200 的 80 則），所以預設就要查。
DEFAULT_REQUIRED = ('id', 'source', 'checkpoint', 'status', 'entry', 'src_text')


def _atomic_write_json(path, obj):
    """Atomic tmp+replace. Prefix `.s2json_tmp_` so compare --json-result
    never leaves a half-written destination."""
    out_dir = os.path.dirname(os.path.abspath(path)) or '.'
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=out_dir, prefix='.s2json_tmp_', suffix='.json')
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _compare_side_block(loaded):
    return {
        'shell': loaded.shell_desc,
        'root_shape': loaded.root_shape,
        'payload_key': loaded.payload_key,
        'metadata': loaded.envelope_meta,
    }


def _advisory_key(item):
    if isinstance(item, dict):
        return (item.get('code'), item.get('site'),
                item.get('id'), item.get('message'))
    return (None, None, None, repr(item))


ID_LIST_INLINE_LIMIT = 10


def _id_list_output_path(anchor_path, suffix):
    """將大量 ID 清單放在輸入檔旁；路徑不可用時才退回 CWD。"""
    try:
        anchor_abs = os.path.abspath(os.fspath(anchor_path))
        directory = os.path.dirname(anchor_abs)
        stem = os.path.splitext(os.path.basename(anchor_abs))[0]
        if directory and os.path.isdir(directory) and stem:
            return os.path.join(directory, stem + suffix)
    except (TypeError, ValueError, OSError):
        pass
    return os.path.join(os.getcwd(), 's2' + suffix)


def _report_id_list(ids, *, small_heading, large_heading, reason, anchor_path,
                    suffix, stream=None, small_inline=False):
    """少量 ID 維持舊 stdout/stderr 格式；大量時寫旁檔、只印摘要。"""
    if stream is None:
        # 不在函式定義時綁死 sys.stdout，讓 redirect_stdout／呼叫端接得到。
        stream = sys.stdout
    if len(ids) <= ID_LIST_INLINE_LIMIT:
        if small_inline:
            print(small_heading + ', '.join(ids), file=stream)
        else:
            print(small_heading, file=stream)
            for item_id in ids:
                print(f'  - {item_id}', file=stream)
        return None

    out_path = _id_list_output_path(anchor_path, suffix)
    body = small_heading + '\n' + ''.join(f'  - {item_id}\n' for item_id in ids)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(body)
    print(f'{large_heading}（{len(ids)} 則，清單已寫入 {out_path}；{reason}）', file=stream)
    return out_path


def cmd_compare(args):
    """raw 與 batch 對照，**只印差異**：raw 有 batch 沒有的 id、batch 有 raw
    沒有的 id、batch 缺欄位的則。乾淨就一行「無差異」，不印整批。

    AP/RT 缺 src_text：預設 advisory（`--require` 未給時）；明確
    `--require src_text` 升 blocking。NS 缺／型別錯／污染一律 blocking。
    有 `--json-result` 時原子寫 schema_version=1 文件。"""
    try:
        raw_loaded = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ raw 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)
    try:
        batch_loaded = _load_raw_any(args.batch)
    except ValueError as e:
        print(f'✗ batch 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)
    raw_items, raw_shell = raw_loaded.items, raw_loaded.shell_desc
    batch_items, batch_shell = batch_loaded.items, batch_loaded.shell_desc

    print(f'# raw  ：{os.path.basename(args.raw)}（{raw_shell}）', file=sys.stderr)
    print(f'# batch：{os.path.basename(args.batch)}（{batch_shell}）', file=sys.stderr)

    raw_ids = [_site_id_of(args.site, it, i) for i, it in enumerate(raw_items)]
    batch_ids = [(it.get('id') or _id_of_any(it, i)) for i, it in enumerate(batch_items)]
    raw_set, batch_set = set(raw_ids), set(batch_ids)

    required = ([f.strip() for f in args.require.split(',') if f.strip()]
                if args.require else list(DEFAULT_REQUIRED))
    explicit_require = args.require is not None

    missing = [i for i in raw_ids if i not in batch_set]
    extra = [i for i in batch_ids if i not in raw_set]

    issues = []
    gaps = []
    advisory_human = []
    new_advisory = []
    for i, it in enumerate(batch_items):
        if not isinstance(it, dict):
            continue
        item_id = it.get('id') or _id_of_any(it, i)
        lack = []
        for f in required:
            if f == 'src_text':
                source = (it.get('source')
                          or (args.site.upper() if args.site else '')
                          or '')
                issue = validate_src_text(source, it.get('src_text'))
                if issue is None:
                    continue
                d = issue.to_dict()
                d['id'] = item_id
                if (issue.code == 'SRC_TEXT_MISSING'
                        and issue.severity == 'advisory'
                        and not explicit_require):
                    new_advisory.append(d)
                    advisory_human.append(item_id)
                    continue
                if issue.code == 'SRC_TEXT_MISSING':
                    lack.append('src_text')
                    issues.append({
                        'kind': 'missing_field', 'id': item_id,
                        'field': 'src_text',
                    })
                else:
                    issues.append({
                        'kind': 'src_text', 'id': item_id,
                        'code': issue.code, 'field': 'src_text',
                    })
                    lack.append('src_text')
                continue
            if it.get(f) in (None, '', [], {}):
                lack.append(f)
                issues.append({
                    'kind': 'missing_field', 'id': item_id, 'field': f,
                })
        if lack:
            gaps.append((item_id, lack))

    dup_batch = sorted({i for i in batch_ids if batch_ids.count(i) > 1})
    for i in missing:
        issues.append({'kind': 'missing_in_batch', 'id': i})
    for i in extra:
        issues.append({'kind': 'extra_in_batch', 'id': i})
    for i in dup_batch:
        issues.append({'kind': 'dup_id', 'id': i})

    found = False
    if missing:
        found = True
        _report_id_list(
            missing,
            small_heading=f'raw 有、batch 沒有（{len(missing)} 則——可能是刻意排除，但要說得出理由）：',
            large_heading='raw 有、batch 沒有',
            reason='可能是刻意排除，但要說得出理由',
            anchor_path=args.raw,
            suffix='_missing_ids.txt',
        )
    if extra:
        found = True
        _report_id_list(
            extra,
            small_heading=f'batch 有、raw 沒有（{len(extra)} 則——來源不明，要查）：',
            large_heading='batch 有、raw 沒有',
            reason='來源不明，要查',
            anchor_path=args.raw,
            suffix='_extra_ids.txt',
        )
    if dup_batch:
        found = True
        _report_id_list(
            dup_batch,
            small_heading=f'batch 內重複 id（{len(dup_batch)} 個）：',
            large_heading='batch 內重複 id',
            reason='請檢查 batch 產生流程',
            anchor_path=args.raw,
            suffix='_duplicate_ids.txt',
            small_inline=True,
        )
    if gaps:
        found = True
        print(f'batch 缺欄位（{len(gaps)} 則，查的是 {"/".join(required)}）：')
        for item_id, lack in gaps:
            print(f'  - {item_id}：缺 {", ".join(lack)}')
    if advisory_human:
        print(f'advisory（{len(advisory_human)} 則，不擋）：')
        for item_id in advisory_human:
            print(f'  - {item_id}：缺 src_text')

    if not found:
        print(f'無差異（raw {len(raw_items)} 筆、batch {len(batch_items)} 筆，'
              f'id 全對得上，{"/".join(required)} 都有）')

    json_path = getattr(args, 'json_result', None)
    if json_path:
        batch_adv = batch_loaded.envelope_meta.get('advisory_issues')
        combined = []
        seen_adv = set()
        if isinstance(batch_adv, list):
            for item in batch_adv:
                k = _advisory_key(item)
                if k in seen_adv:
                    continue
                seen_adv.add(k)
                combined.append(item)
        for item in new_advisory:
            k = _advisory_key(item)
            if k in seen_adv:
                continue
            seen_adv.add(k)
            combined.append(item)
        doc = {
            'schema_version': 1,
            'raw': _compare_side_block(raw_loaded),
            'batch': _compare_side_block(batch_loaded),
            'issues': issues,
            'advisory_issues': combined,
        }
        try:
            _atomic_write_json(json_path, doc)
        except OSError as e:
            print(f'✗ --json-result 寫入失敗：{e}', file=sys.stderr)
            sys.exit(1)

    if found:
        sys.exit(2)


DEDUP_FIELDS = ('script', 'desc', 'head', 'headline', 'story', 'cap', 'title')


def _dedup_view(item):
    """AP 清單檔是 Elasticsearch 形狀，真正的欄位包在 `_source` 底下，
    頂層只有 `_id` 這種雜湊。不看穿這層的話，AP 清單上的去重完全比不動——
    而 0817-2200 的 AP 去重正是在清單檔上做的。"""
    src = item.get('_source')
    if isinstance(src, dict):
        merged = dict(item)
        merged.update(src)
        return merged
    return item


def _dedup_id(site, item, index):
    """去重比對用的 id。AP 站的人看的是 `AP<editorialid>`（state 裡也是這個），
    不是 ES 的 `_id` 雜湊——比對時要用人看得懂、跟 state 對得起來的那個。
    沒給 --site 但看得到 `editorialid` 時也走 AP 規則：那個欄位只有 AP 的
    ES 清單檔才有，靠它自動判站比回傳雜湊有用（D9 步驟②前置）。"""
    view = _dedup_view(item)
    if site in (None, 'ap') and view.get('editorialid'):
        return 'AP' + str(view['editorialid'])
    return _site_id_of(site, view, index)


def _norm(s):
    """去重比對用的正規化：吃掉全形/半形空白與換行差異，其餘不動。
    只用來回答「排版不同但內容相同嗎」，不改變逐字比對的結論。"""
    return ''.join(str(s).split())


TAG_RE = re.compile(r'<[^>]+>')


def _norm_markup(s):
    """再多剝一層 HTML 標記。NS 的 script 夾著 <p>／<b>，同一則的不同剪輯版
    常常只差在標記上——不剝掉的話，「第一個差異」會指到 `<b>` 這種雜訊，
    而不是真正的內容差異（0817-2200 EN-32MO vs EN-31MO 就是這樣）。"""
    return _norm(TAG_RE.sub('', str(s)))


def _first_diff(a, b):
    """回傳第一個相異字元的 0-based 位置；完全相同回 None。
    其中一邊是另一邊的前綴時，位置就是較短那邊的長度。"""
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def cmd_dedup_check(args):
    """兩則以上的指定欄位逐字比對，回答「是不是同一則的不同版本」。

    0817-2200 那輪 NS 去重花了 5 次臨時 python 做這件事（撈出兩則 script
    再自己算 a==b）——`inspect` 能把兩段印出來，但沒有「相同與否」的答案，
    agent 只能自己算。這個子指令補的就是那個洞。

    **只回答機械問題（逐字是否相同、差在哪）；要不要當成重複、留哪一則，
    是編輯判斷，這裡不做也不建議。**"""
    try:
        loaded = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)
    items, shell_desc = loaded.items, loaded.shell_desc
    print(f'# {os.path.basename(args.raw)}：{shell_desc}', file=sys.stderr)

    ids = [i.strip() for i in args.ids.split(',') if i.strip()]
    if len(ids) < 2:
        print(f'✗ --ids 至少要兩個才比得出來（收到 {len(ids)} 個）', file=sys.stderr)
        sys.exit(1)
    dup_in_arg = sorted({i for i in ids if ids.count(i) > 1})
    if dup_in_arg:
        print(f'✗ --ids 裡有重複：{", ".join(dup_in_arg)}', file=sys.stderr)
        sys.exit(1)

    table = {}
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        table.setdefault(_dedup_id(args.site, it, idx), _dedup_view(it))

    absent = [i for i in ids if i not in table]
    if absent:
        # 找不到就明講並中止，不能只比得出來的那幾則——那會讓
        # 「打錯 id」跟「兩則不同」看起來一樣。
        print(f'✗ 這些 id 不在 {os.path.basename(args.raw)} 裡：{", ".join(absent)}',
              file=sys.stderr)
        print(f'  （檔內共 {len(table)} 個 id，可用 inspect 確認拼法）', file=sys.stderr)
        sys.exit(1)

    picked = [(i, table[i]) for i in ids]

    if args.fields:
        fields = [f.strip() for f in args.fields.split(',') if f.strip()]
        lacking = [f for f in fields
                   if not any(isinstance(it.get(f), str) for _, it in picked)]
        if lacking:
            print(f'✗ 指定的欄位在這幾則裡都不是文字或不存在：{", ".join(lacking)}',
                  file=sys.stderr)
            sys.exit(1)
    else:
        fields = [f for f in DEDUP_FIELDS
                  if any(isinstance(it.get(f), str) and it.get(f) for _, it in picked)]
        if not fields:
            print(f'✗ 這幾則裡找不到任何可比對的文字欄位'
                  f'（找過 {"/".join(DEDUP_FIELDS)}），請用 --fields 指定',
                  file=sys.stderr)
            sys.exit(1)

    pairs = [(a, b) for x, a in enumerate(ids) for b in ids[x + 1:]]
    verdicts = {}

    for f in fields:
        print(f'── {f} ──')
        for i, it in picked:
            v = it.get(f)
            if isinstance(v, str):
                print(f'  {i}  len={len(v)}')
            else:
                print(f'  {i}  （無此欄位或不是文字：{type(v).__name__}）')
        for a, b in pairs:
            va, vb = table[a].get(f), table[b].get(f)
            if not isinstance(va, str) or not isinstance(vb, str):
                verdicts[(f, a, b)] = 'n/a'
                print(f'  ? {a} vs {b}：有一邊沒有這個欄位，無法比對')
                continue
            if not va and not vb:
                # 兩邊都空「逐字相同」在機械上成立，但拿來當去重依據是假訊號。
                verdicts[(f, a, b)] = 'both_empty'
                print(f'  ? {a} vs {b}：兩邊這個欄位都是空的，不足以判斷重複')
            elif va == vb:
                verdicts[(f, a, b)] = 'same'
                print(f'  ✓ {a} vs {b}：逐字相同')
            elif _norm(va) == _norm(vb):
                verdicts[(f, a, b)] = 'same_normalized'
                print(f'  ≈ {a} vs {b}：**只差空白／換行**，去掉空白後逐字相同')
            elif _norm_markup(va) == _norm_markup(vb):
                verdicts[(f, a, b)] = 'same_markup'
                print(f'  ≈ {a} vs {b}：**只差 HTML 標記／空白**，剝掉標記後逐字相同')
            else:
                verdicts[(f, a, b)] = 'diff'
                # 差異位置一律算在「剝掉標記與空白」之後的文字上，否則
                # 指標會停在 <b> 這種排版雜訊，看不到真正差在哪。
                ca, cb = _norm_markup(va), _norm_markup(vb)
                pos = _first_diff(ca, cb)
                print(f'  ✗ {a} vs {b}：不同（剝掉標記後第 {pos} 字起不同）')
                lo = max(0, pos - 30)
                print(f'      {a}：…{ca[lo:pos + 30]}…')
                print(f'      {b}：…{cb[lo:pos + 30]}…')
        print()

    print('── 結論（機械判斷，收不收由編輯決定）──')
    # 四種判定在結論行也要分開講——折成「相同」會讓「逐字相同」跟
    # 「剝掉標記才相同」看起來一樣，而這支工具存在的理由就是把它們分開。
    labels = [('same', '相同'), ('same_normalized', '去空白後相同'),
              ('same_markup', '剝標記後相同'), ('diff', '不同'),
              ('both_empty', '兩邊皆空'), ('n/a', '無法比')]
    for a, b in pairs:
        bits = []
        for key, word in labels:
            hit = [f for f in fields if verdicts.get((f, a, b)) == key]
            if hit:
                bits.append(f'{"/".join(hit)} {word}')
        unresolved = [f for f in fields if (f, a, b) not in verdicts]
        if unresolved:
            # 結論行是掃帶 agent 唯一會讀的一行，寧可炸掉也不能印半行空白。
            print(f'✗ 內部錯誤：{a} vs {b} 的 {"/".join(unresolved)} 沒有判定結果',
                  file=sys.stderr)
            sys.exit(1)
        print(f'  {a} vs {b}：{"、".join(bits)}')


# ── R33 窄工具出口：工作 batch 欄位改名（2026-09-14）─────────────────────
#
# 背景：0909-0700 那輪 agent 想把 `ns_batch_0700.json` 裡打錯的鍵名
# `raw_entry` 整批改成 `entry`，手寫 `python -c` 讀檔改字串再回寫被
# `s2_bash_guard.py` 依 13d §4 攔下（guard 本身沒問題，是攔下之後沒有標準
# 工具可走）。這支只做「把 entry 物件裡的一個鍵改名」這一件機械事：
# 不是任意 JSON path 的 set-value，不執行任何程式碼，也不碰生產 state。
#
# 支援的形狀（跟 add-batch／build 已經在吃的一致，不重造第三種）：
#   list     裸陣列 [ {...}, … ]（add-batch 舊格式／ENEX／ABC／側錄線）
#   wrapper  {"entries": [...], "new_topics": {...}}（add-batch 新格式 batch.json）
#   flatmap  {"ID1": {...}, "ID2": {...}, "_new_topics": {...}}（build --skeleton
#            吃的 entries.json；`_new_topics`／`new_topics` 是保留鍵，原樣不動）

_RENAME_RESERVED_KEYS = (
    '_new_topics', 'new_topics', 'checkpoint', 'checkpoint_label',
    'run_id', 'advisory_issues', 'window_start', 'window_end',
)


def _is_rename_reserved(k):
    return k in _RENAME_RESERVED_KEYS or str(k).startswith('window_')

# 生產狀態檔命名慣例：`{MMDD}-s2-state.json`（見 s2_state.default_file()／
# _yesterday_state_path()），不管落在哪個目錄都拒絕——工作 batch 不會湊巧
# 用這個檔名，誤判成本遠低於漏擋生產 state 的成本。
#
# 🔴 2026-09-14（複核 S2）：原本只認 `{MMDD}-s2-state.json`，漏了平台整併線
# 自己的狀態檔（ENEX／ABC，見 s2_platform_extract 等）——這兩站用的命名是
# `{MMDD}-ENEX-state.json`／`{MMDD}-ABC-state.json`，站名不是固定的
# `s2`，字面比對接不到，等於這兩站的生產 state 完全沒被這道檢查擋到。
# 放寬成 `{MMDD}-{任意英數字站名}-state.json`——`s2` 本身也是英數字，
# 舊行為完整涵蓋在新規則內，不是替換、是超集。
_STATE_FILE_RE = re.compile(r'^\d{4}-[A-Za-z0-9]+-state\.json$', re.IGNORECASE)


def _load_batch_any(path):
    """讀『工作 batch JSON』，辨識四種形狀，回傳 `(kind, payload)`。

    1. 頂層 list → list
    2. dict 且 entries 是 list → wrapper
    3. dict 且 entries 是 dict → entries_map_envelope（空 map 仍是此形，
       不是 flatmap）
    4. dict 沒有 entries、且有非保留鍵 → flatmap
    其餘丟 ValueError，不猜、不假裝成功。"""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list):
        return 'list', data
    if isinstance(data, dict):
        if 'entries' in data:
            ent = data['entries']
            if isinstance(ent, list):
                return 'wrapper', data
            if isinstance(ent, dict):
                return 'entries_map_envelope', data
            raise ValueError(
                f'{path} entries 存在但不是 list 也不是 dict：{type(ent)}')
        # 扁平 map：至少要有一個非保留鍵，否則跟「空物件」／「只有 new_topics
        # 的殼」分不出來——那種情況直接留給下面「找不到可改的項目」去擋。
        if any(not _is_rename_reserved(k) for k in data):
            return 'flatmap', data
    raise ValueError(
        f'{path} 頂層形狀認不出來（不是陣列、不是含 entries 陣列／map 的物件，'
        f'也不是扁平 {{id: {{...}}}} map）')


def _iter_rename_entries(kind, payload):
    """回傳 `[(標籤, entry_dict)]`，entry_dict 是可以直接原地改的物件參照。

    非 dict 的項目（例如舊格式 entries.json 裡的純字串 entry）沒有鍵可改，
    直接跳過——不算錯，只是這一則沒有可改名的目標。
    entries_map_envelope 只掃 `payload['entries'].items()` 的 dict 值。"""
    if kind == 'list':
        return [(it.get('id', f'#{i}') if isinstance(it, dict) else f'#{i}', it)
                for i, it in enumerate(payload) if isinstance(it, dict)]
    if kind in ('wrapper', 'wrapper_list'):
        return [(it.get('id', f'#{i}') if isinstance(it, dict) else f'#{i}', it)
                for i, it in enumerate(payload['entries']) if isinstance(it, dict)]
    if kind == 'entries_map_envelope':
        entries = payload.get('entries') or {}
        return [(k, v) for k, v in entries.items() if isinstance(v, dict)]
    if kind == 'flatmap':
        return [(k, v) for k, v in payload.items()
                if not _is_rename_reserved(k) and isinstance(v, dict)]
    return []


def _refuse_if_production_state(path):
    """拒絕操作生產狀態檔（R33 明文：禁止改生產 state、不繞 guard）。

    判準沿用 `s2_state.py` 自己找狀態檔的方式：
      (a) 檔名符合 `{MMDD}-<線別>-state.json`（s2／ENEX／ABC…；`default_file()`／
          `_yesterday_state_path()`）——不管落在哪個目錄都拒絕；
      (b) 檔案**直接**落在 `s2_state.STATE_DIR` 根目錄底下——掃帶輪次的
          正式狀態檔就放在這一層；
      (c) 檔案落在 `s2_state.STATE_DIR/Archive/**` 封存底下。
    三者任一命中就拒絕，不判斷內容——寧可誤擋一份湊巧同名的工作檔，
    不能漏擋生產 state。

    🔴 2026-09-14 修正：原本用 `commonpath(ab, state_dir) == state_dir` 判「在
    STATE_DIR 底下」，這連**帶日期的子資料夾**（`STATE_DIR\\20260909\\
    ns_batch_0700.json` 這種掃帶輪次的工作 batch，`s2_scan.ps1` 每輪 cwd 就設
    在這一層）都一併擋掉——掃帶當輪的工作檔反而全部被誤判成生產 state，
    rc=2、什麼都沒寫。改成只擋「根目錄直接落檔」與「Archive 底下」這兩種
    真正的生產路徑，帶日期的子資料夾（不是 Archive）維持放行。"""
    ab = os.path.abspath(path)
    base = os.path.basename(ab)

    if _STATE_FILE_RE.match(base):
        print(f'✗ 拒絕操作：{path} 看起來是生產狀態檔（檔名符合 '
              f'{{MMDD}}-<s2|ENEX|ABC…>-state.json 命名慣例）。'
              f'rename-field 只准動工作 batch／entries.json，不准碰生產 state '
              f'（R33 明文界線；真的要修生產 state 請走 s2_state.py 的正常子指令）。',
              file=sys.stderr)
        sys.exit(2)

    try:
        state_dir = os.path.abspath(s2_state.STATE_DIR)
    except Exception:
        state_dir = None
    if not state_dir:
        return

    state_dir_l = state_dir.lower()
    ab_l = ab.lower()
    parent_l = os.path.dirname(ab_l)
    archive_l = os.path.join(state_dir_l, 'archive')

    where = None
    if parent_l == state_dir_l:
        where = f'直接落在 {s2_state.STATE_DIR} 根目錄底下'
    else:
        try:
            if os.path.commonpath([ab_l, archive_l]) == archive_l:
                where = f'落在 {s2_state.STATE_DIR} 的 Archive 封存底下'
        except ValueError:
            pass  # 不同磁碟機（Windows），commonpath 會炸，視為不在底下

    if where:
        print(f'✗ 拒絕操作：{path} 看起來是生產狀態檔（{where}）。'
              f'rename-field 只准動工作 batch／entries.json，不准碰生產 state '
              f'（R33 明文界線；真的要修生產 state 請走 s2_state.py 的正常子指令）。',
              file=sys.stderr)
        sys.exit(2)


def cmd_rename_field(args):
    """把工作 batch JSON 裡每一則 entry 物件的一個鍵改名，輸出到新檔。

    只做「改鍵名」這一件事：不接受任意 JSON path，不能順帶塞值、不執行
    任何程式碼。來源鍵在全部項目裡都不存在、或目的鍵已經在任何一項存在，
    一律整批拒絕、不寫任何檔案（見下方檢查順序）。"""
    _refuse_if_production_state(args.batch)

    # 🔴 2026-09-14（複核 S1）：原本只用 `os.path.abspath(out) == in_abs` 做字串
    # 比較，Windows 路徑大小寫不敏感——`--out NS_BATCH_1100.JSON` 對輸入
    # `ns_batch_1100.json`（或它的 8.3 短檔名）字串比較不相等，實際上是同一
    # 個檔案，於是「--out 等於輸入檔」的保護被繞過：先原地覆寫掉輸入檔，
    # 再印「原檔未動」——比沒做這個檢查更糟（假安全感）。改成：
    #   (a) `os.path.normcase(os.path.realpath(...))` 比較——解掉大小寫與
    #       符號連結/8.3 短檔名，且不要求檔案存在（--out 常常還沒建立）；
    #   (b) 兩邊都已存在時再用 `os.path.samefile` 補一刀，涵蓋 (a) 沒解開
    #       的 hardlink／junction 等價情形。
    in_real = os.path.normcase(os.path.realpath(args.batch))

    def _same_as_input(candidate):
        cand_real = os.path.normcase(os.path.realpath(candidate))
        if cand_real == in_real:
            return True
        try:
            return (os.path.exists(candidate) and os.path.exists(args.batch)
                    and os.path.samefile(candidate, args.batch))
        except OSError:
            return False

    explicit_out = args.out is not None
    out = args.out
    if out:
        if _same_as_input(out):
            print('✗ --out 不能等於輸入檔——rename-field 一律輸出新檔，'
                  '不原地覆寫（避免改壞了連原檔都救不回來）', file=sys.stderr)
            sys.exit(2)
    else:
        base, ext = os.path.splitext(args.batch)
        out = f'{base}.renamed{ext or ".json"}'
        if _same_as_input(out):
            print(f'✗ 預設輸出檔名剛好等於輸入檔（{out}），請改用 --out 指定別的路徑',
                  file=sys.stderr)
            sys.exit(2)

    # `--out` 也是寫入路徑，一樣要擋生產 state——不然 `--out 0914-s2-state.json`
    # 會繞過上面對 `args.batch`（輸入檔）的檢查，直接把生產狀態檔當輸出目標覆寫掉。
    _refuse_if_production_state(out)

    # 只在**用預設輸出路徑**時檔案已存在才拒絕：明確指定 `--out` 是使用者的
    # 主動選擇，維持既有行為（直接覆寫，不多此一舉檢查）；沒帶 --out 卻湊巧
    # 撞到已存在的 `<name>.renamed.json`，代表這個檔名已經被別的東西用過，
    # 悄悄覆寫掉比拒絕危險（R33 同一個「寧可誤擋」原則）。
    if not explicit_out and os.path.exists(out) and not getattr(args, 'dry_run', False):
        print(f'✗ 預設輸出檔 {out} 已存在，拒絕覆寫——請明確帶 --out 指到別的路徑'
              f'（或指到這個路徑，代表你確認要覆寫）。', file=sys.stderr)
        sys.exit(2)

    try:
        kind, payload = _load_batch_any(args.batch)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f'✗ 讀取失敗：{e}', file=sys.stderr)
        sys.exit(2)

    entries = _iter_rename_entries(kind, payload)
    if not entries:
        print(f'✗ {args.batch} 裡沒有可改項目（辨識出的形狀是 '
              f'{kind}，但沒有 dict 型的 entry）', file=sys.stderr)
        sys.exit(2)

    src, dst = args.from_key, args.to_key

    conflict = [label for label, e in entries if dst in e]
    if conflict:
        print(f'✗ 目的鍵 {dst!r} 已經在 {len(conflict)} 筆裡存在，拒絕改名'
              f'（改下去會覆蓋既有值）：{", ".join(str(x) for x in conflict[:20])}'
              + ('…' if len(conflict) > 20 else ''), file=sys.stderr)
        sys.exit(2)

    have_src = [label for label, e in entries if src in e]
    if not have_src:
        print(f'✗ 來源鍵 {src!r} 在全部 {len(entries)} 筆裡都不存在，拒絕改名'
              f'（可能是鍵名打錯，或這份檔案本來就不是要改的那份）', file=sys.stderr)
        sys.exit(2)

    renamed, skipped = [], []
    for label, e in entries:
        if src in e:
            e[dst] = e.pop(src)
            renamed.append(label)
        else:
            skipped.append(label)

    prefix = '（--dry-run，未寫檔）' if getattr(args, 'dry_run', False) else ''
    print(f'{prefix}改名 {src!r} → {dst!r}：{len(renamed)} 筆改到、'
          f'{len(skipped)} 筆沒有這個鍵（跳過，不算錯）')
    for label in renamed:
        print(f'  ✓ {label}')
    if skipped:
        print(f'  沒有 {src!r} 這個鍵、跳過：{", ".join(str(x) for x in skipped)}',
              file=sys.stderr)

    if getattr(args, 'dry_run', False):
        return

    # 原子寫入：先寫同目錄下的暫存檔，成功後才 `os.replace` 蓋到目的檔——
    # 寫到一半（磁碟滿／權限問題／中途被砍）不會留下一份半寫壞的 `out`。
    # 同目錄是刻意的：`os.replace` 跨磁碟機不保證原子，暫存檔留在同一個
    # 磁碟機／同一個檔案系統才成立。
    out_dir = os.path.dirname(os.path.abspath(out)) or '.'
    # 🔴 2026-09-14（複核 N3）：`--out` 帶不合法路徑（例如
    # `x.json::$DATA` 這種 NTFS 保留字元組合）原本會讓 `mkstemp`／
    # `os.replace` 炸出的 `OSError` 直接往外噴一整段 traceback——跟這支
    # 工具其餘所有錯誤都印中文一行訊息＋乾淨 exit 2 的風格不一致，agent
    # 也得自己解讀 traceback。改成明確接住 `OSError`，印友善訊息、
    # 清掉暫存檔、exit 2；其他例外（例如 ⑭ 測試模擬的寫檔中途失敗）
    # 維持原行為往外傳，不吞掉。
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=out_dir, prefix='.s2rf_tmp_', suffix='.json')
    except OSError as e:
        print(f'✗ 寫入失敗：--out 路徑 {out!r} 建不了暫存檔（{e}）'
              f'——檢查路徑是否合法、目錄是否存在', file=sys.stderr)
        sys.exit(2)
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, out)
    except OSError as e:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        print(f'✗ 寫入失敗：--out 路徑 {out!r} 寫不進去（{e}）', file=sys.stderr)
        sys.exit(2)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    print(f'已寫入 {out}（原檔 {args.batch} 未動）', file=sys.stderr)


def _nonnegative_int(raw):
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError('必須是 0 或正整數')
    return value


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_dump = sub.add_parser('dump', help='印出/存出 raw.json 的機械欄位摘要')
    p_dump.add_argument('--site', required=True, choices=['ns', 'ap', 'rt'])
    p_dump.add_argument('--raw', required=True)
    p_dump.add_argument('--out')
    p_dump.set_defaults(func=cmd_dump)

    p_build = sub.add_parser('build', help='raw.json ＋ entries.json 併成 add-batch 用的 batch.json')
    p_build.add_argument('--site', required=True, choices=['ns', 'ap', 'rt'])
    p_build.add_argument('--raw', required=True)
    p_build.add_argument('--entries', required=True)
    p_build.add_argument('--checkpoint', required=True)
    p_build.add_argument('--out')
    p_build.add_argument('--dry-run', action='store_true',
                         help='只跑預檢與印警告，不印／寫 batch 輸出')
    p_build.add_argument('--skeleton', help='from-raw 產的骨架 json；給了就以它為底，'
                          '--entries 只需 {id:{entry,category,tc}} 覆蓋（A24）')
    p_build.set_defaults(func=cmd_build)

    p_fr = sub.add_parser('from-raw', help='raw ＋ 狀態檔一次產出提示表＋骨架 JSON＋已在庫標記（D12，A24）')
    p_fr.add_argument('--site', required=True, choices=['ns', 'ap', 'rt'])
    p_fr.add_argument('--raw', required=True)
    p_fr.add_argument('--checkpoint', required=True)
    p_fr.add_argument('--state', help='狀態檔路徑；給了才排除已 has_script 的 id'
                       '（D12：pending／其他狀態一律保留並標 prev_status）')
    p_fr.add_argument('--out', help='骨架 json 路徑；不給就用 raw 所在目錄組 {site}_skeleton_{HHMM}.json')
    p_fr.add_argument('--page', type=int, help='提示表分頁（每頁 ≤28,000 字元），預設第 1 頁')
    p_fr.set_defaults(func=cmd_from_raw)

    p_unwrap = sub.add_parser('unwrap', help='自動偵測外殼並卸成規範化裸陣列')
    p_unwrap.add_argument('raw')
    p_unwrap.add_argument('--out')
    p_unwrap.set_defaults(func=cmd_unwrap)

    p_inspect = sub.add_parser('inspect', help='精準印出 raw 檔的指定項目/欄位')
    p_inspect.add_argument('raw')
    p_inspect.add_argument('--ids', nargs='+',
                           help='id 清單；可用逗號或空白分隔')
    p_inspect.add_argument('--fields', help='逗號分隔的欄位名清單')
    p_inspect.add_argument('--limit', type=int, help='最多顯示幾筆，預設 100')
    p_inspect.add_argument('--offset', type=_nonnegative_int, default=0,
                           help='略過前 N 筆後再套 --limit（0-based，預設 0）')
    p_inspect.add_argument('--index', type=int, help='只看第 i 筆（0-based）')
    p_inspect.add_argument('--site', choices=['ns', 'ap', 'rt', 'enex', 'abc'],
                           help='per-site id 規則（RT 是 code；AP 清單檔自動看穿 _source；'
                                'enex/abc 走 PLATFORM_ID_OF）')
    p_inspect.add_argument('--lengths', action='store_true',
                           help='只印各欄位字數不印內容（檢查摘要 150 字上限這類需求）')
    p_inspect.set_defaults(func=cmd_inspect)

    p_search = sub.add_parser('search', help='在 raw 檔的指定欄位裡找關鍵字')
    p_search.add_argument('raw')
    p_search.add_argument('--contains', required=True)
    p_search.add_argument('--field', default='all', choices=['script', 'story', 'head', 'all'])
    p_search.add_argument('--limit', type=int, help='最多顯示幾筆命中，預設 100')
    p_search.add_argument('--site', choices=['ns', 'ap', 'rt'],
                          help='per-site id 規則（RT 是 code；AP 清單檔自動看穿 _source）')

    p_snap = sub.add_parser('snapshot', help='把 raw 檔壓成純文字稽核快照（不覆寫舊檔）')
    p_snap.add_argument('raw')
    p_snap.add_argument('--site', choices=['ns', 'ap', 'rt'], help='指定站別才用得到 per-site id 規則（RT 是 code）')
    p_snap.add_argument('--checkpoint', help='用來組預設檔名 _audit_{site}_{HHMM}.txt')
    p_snap.add_argument('--out', help='輸出路徑；不給就用 --checkpoint 組')
    p_snap.set_defaults(func=cmd_snapshot)

    p_tl = sub.add_parser('timeline', help='raw 檔轉成「id｜台北當地時間」清單，供跨站對帳窗內外用')
    p_tl.add_argument('raw')
    p_tl.add_argument('--site', required=True, choices=['ns', 'ap', 'rt'])
    p_tl.add_argument('--out', help='同時存成檔案（不給只印到 stdout）')
    p_tl.set_defaults(func=cmd_timeline)

    p_fill = sub.add_parser('fill-src-text', help='raw／detail 檔的正文依 id 填進 batch.json 的 src_text（只填空的）')
    p_fill.add_argument('--batch', required=True)
    p_fill.add_argument('--raw', required=True)
    p_fill.add_argument('--site', required=True, choices=['ns', 'ap', 'rt'])
    p_fill.add_argument('--fields', help='raw 裡取正文的欄位，逗號分隔、依序取第一個有內容的；不給用預設 (desc/script、head/script、head/story)')
    p_fill.add_argument('--out', help='輸出路徑；不給就地覆寫 --batch')
    p_fill.set_defaults(func=cmd_fill_src_text)

    p_cat = sub.add_parser('collate-category', help='把 batch.json 裡各則的 category 收成 set-category --pairs 吃得下的字串')
    p_cat.add_argument('batches', nargs='+', help='一或多個 batch.json（例如三站各一個）')
    p_cat.set_defaults(func=cmd_collate_category)

    p_cat_c = sub.add_parser('concat', help='合併兩份以上 json 陣列檔案（分頁清單、多來源分批 batch）')
    p_cat_c.add_argument('files', nargs='+', help='兩個以上的檔案（裸陣列或已知殼型皆可）')
    p_cat_c.add_argument('--site', choices=['ns', 'ap', 'rt', 'enex', 'abc'],
                         help='給了才去重（保留第一次出現的 id）；不給就純合併。'
                              'enex／abc 只有這個子指令支援（其餘子指令走 SITE_SPEC，不含這兩站）')
    p_cat_c.add_argument('--out', help='輸出路徑；不給就印到 stdout')
    p_cat_c.set_defaults(func=cmd_concat)

    p_cmp = sub.add_parser('compare', help='raw 與 batch 對照，只印缺 id／缺欄位')
    p_cmp.add_argument('--raw', required=True)
    p_cmp.add_argument('--batch', required=True)
    p_cmp.add_argument('--site', choices=['ns', 'ap', 'rt'])
    p_cmp.add_argument('--require', help=f'要檢查的欄位，逗號分隔。預設 {",".join(DEFAULT_REQUIRED)}')
    p_cmp.add_argument('--json-result', dest='json_result',
                       help='把對照結果寫成 schema_version=1 JSON（原子 tmp+replace）')

    p_dc = sub.add_parser('dedup-check', help='兩則以上的指定欄位逐字比對，判斷是不是同一則的不同版本')
    p_dc.add_argument('raw')
    p_dc.add_argument('--ids', required=True, help='逗號分隔，至少兩個')
    p_dc.add_argument('--site', choices=['ns', 'ap', 'rt'], help='指定站別才用得到 per-site id 規則（RT 是 code）')
    p_dc.add_argument('--fields', help=f'要比的欄位，逗號分隔。不給就自動挑 {"/".join(DEDUP_FIELDS)} 裡有內容的')
    p_cmp.set_defaults(func=cmd_compare)
    p_dc.set_defaults(func=cmd_dedup_check)
    p_search.set_defaults(func=cmd_search)

    p_check = sub.add_parser(
        'check-entries',
        help='相容入口：委派 s2_platform_extract.py 的 entries 形狀預檢')
    p_check.add_argument('--entries', required=True)
    p_check.set_defaults(func=cmd_check_entries)

    p_rf = sub.add_parser('rename-field',
                          help='工作 batch JSON（entries.json／batch.json）裡把一個鍵改名，輸出到新檔（R33）')
    p_rf.add_argument('batch', help='工作 batch JSON（list／wrapper／flatmap 三種既有形狀皆可，不可為生產 state）')
    p_rf.add_argument('--from', dest='from_key', required=True, help='要改掉的舊鍵名')
    p_rf.add_argument('--to', dest='to_key', required=True, help='改成的新鍵名')
    p_rf.add_argument('--out', help='輸出路徑；不給就用 <檔名>.renamed.json（永不覆寫輸入檔）。'
                       '不給 --out 時若預設輸出檔已存在會拒絕（避免誤覆寫）；'
                       '明確帶 --out 則一律直接覆寫該路徑，不檢查是否已存在。'
                       '--out 與輸入檔同樣會被擋生產 state（R33）。')
    p_rf.add_argument('--dry-run', action='store_true', help='只印預覽（改到/跳過筆數），不寫任何檔案')
    p_rf.set_defaults(func=cmd_rename_field)

    p_gc = sub.add_parser('gate-clear', help='手動清除硬閘 gate lock（逃生路徑；正常應由整批 Write '
                          '或 dry-run 歸零自動清除，見 _clear_gate_lock）')
    p_gc.add_argument('--site', required=True, choices=['ns', 'ap', 'rt'])
    p_gc.add_argument('--entries', required=True, help='entries.json 路徑，用來定位同目錄下的 gate lock 檔')
    p_gc.set_defaults(func=cmd_gate_clear)

    p_rw = sub.add_parser('rewrite-entry',
                          help='entries.json 的受控精準修補：有 gate lock 時只准改 lock 列出的 ID；'
                               '沒有 lock 時走自由模式（自選 ID 改 entry/category/tc，'
                               '另可 --new-id 新增則、--new-topics 補 _new_topics）')
    p_rw.add_argument('--site', required=True, choices=['ns', 'ap', 'rt'])
    p_rw.add_argument('--entries', required=True,
                      help='要修補的 entries.json；有 active gate lock 時必須跟 lock 記錄的路徑一致')
    # --id/--set 刻意不設 required：自由模式允許「只補 --new-topics、不動任何素材則」。
    # 兩種模式缺 --id 時仍各自以 exit 2 明確報錯（lock 模式的那句一個字未改）。
    p_rw.add_argument('--id', dest='ids', action='append',
                      help='要改的 ID；多筆時重複帶 --id')
    p_rw.add_argument('--set', dest='sets', action='append',
                      help='<ID>=<新 entry JSON 或純文字>；每個 --id 各帶一組。'
                           '有 lock＝整份取代該則的值；無 lock（自由模式）＝局部覆寫，'
                           '純文字等同 {"entry":"…"}，object 只允許 entry/category/tc')
    p_rw.add_argument('--new-id', dest='new_ids', action='append',
                      help='【自由模式限定】明示這個 ID 是**新增**的（必須同時出現在 '
                           '--id/--set，且 --set 要帶非空 entry）。不帶這個旗標時，'
                           '--id 指到不存在的 ID 一律當成打錯字拒絕，不會靜默新增。'
                           '新增與修改既有則可以混在同一次呼叫')
    p_rw.add_argument('--new-topics', dest='new_topics',
                      help='【自由模式限定】patch entries.json 頂層 `_new_topics` 保留鍵，'
                           '值是 JSON 字串 {"題名":{"charter":"這題收什麼、不收什麼",'
                           '"big":"大分類","aliases":["別名"]}}；逐題逐欄合併，'
                           '合併後每題都要有非空 charter 與 big。'
                           '`{}` ＝只確保這個頂層鍵存在。可單獨使用（不給 --id）')
    p_rw.add_argument('--patch-file', help='patch schema v1 JSON；與既有 --id/--set 路徑互斥')
    p_rw.add_argument('--init-patch', metavar='OUT',
                      help='依目前 entries SHA 建立 changes=[] 的空白 patch scaffold')
    p_rw.add_argument('--dry-run', action='store_true',
                      help='驗證 patch、lock、lint 並列出預期 hash，但不寫檔／不清 lock')
    p_rw.set_defaults(func=cmd_rewrite_entry_cli)

    p_af = sub.add_parser('autofix-tags', help='R43層1治本：機械修補entries.json草稿裡「有錨點可插」的'
                          '(BITE)/SOT標記缺口（build --dry-run前建議先跑一次；不猜內容，修不了的列出來）')
    p_af.add_argument('--site', required=True, choices=['ns', 'ap', 'rt'])
    p_af.add_argument('--entries', required=True, help='要修補的 entries.json 草稿路徑')
    p_af.add_argument('--skeleton', help='NS站SOT修補需要（footage_type/duration_ms來源）；'
                       'AP/RT的(BITE)修補不需要')
    p_af.add_argument('--out', help='輸出路徑；不給就地覆寫 --entries')
    p_af.set_defaults(func=cmd_autofix_tags)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
