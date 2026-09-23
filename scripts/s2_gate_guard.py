#!/usr/bin/env python3
"""S2 掃帶 agent 的 PreToolUse/PostToolUse hook：硬閘觸發後技術性鎖住 Edit
工具，不再只是文字建議（MASTER R43 遵守修法方向1，2026-09-18）。
同一個 hook 也攔截 ENEX/ABC entries 與候選衝生檔的逐筆 Edit，引導改走
`s2_platform_bridge.py rewrite-entry` 修骨架後整批重建。

背景：`s2_batch_prep.py` 的 `_enforce_build_hard_gate()` 偵測到同站機械格式錯誤
達各 reason code 門檻時印 ⛔ 並 `sys.exit(2)`。通用門檻是 5 則；少量但不可
交付的 `FMT_OPERATIONAL_NOTE` 是 1 則。連續 4 輪（0917-0430～0918-2200）觀察到
掃帶 agent 收到這則訊息仍選擇 Edit 逐筆修補——Edit/Write 只是文字建議，工具
層沒有任何機制擋，agent 可以自由忽略。

這支 hook 補上工具層攔截：
  PreToolUse（matcher: Edit）—— 目標檔案若對應到一個仍 active 的 gate lock
    （`<site>_gate_lock.json`，跟 entries.json 放同目錄，見
    `s2_batch_prep.py` 的 `_write_gate_lock`），直接 deny，訊息附「請改用
    Write 整批重寫」與手動解鎖逃生路徑。
  PostToolUse（matcher: Write）—— Write 成功寫入某檔案後，若該檔案對應到一個
    active gate lock，視為「一次完整 Write 已發生」，直接刪除該 lock（清除
    時機①）。清除時機②（重跑 build/--dry-run 確認 reason code 降到 0）由
    `s2_batch_prep.py` 的 `_clear_gate_lock()` 自己處理，不需要這支 hook。

逃生路徑：lock 卡死時可用
    python s2_batch_prep.py gate-clear --site <站> --entries <entries.json路徑>
手動清除，不會讓整輪掃帶完全卡住跑不完（方向1第4點）。

少於通用門檻時，改走 `s2_batch_prep.py rewrite-entry`；**有 lock** 時該指令
只接受 lock reason items 列出的 ID，並在寫入後用 build 共用 lint 歸零才清鎖。

2026-09-23（A41 續辦）：NS/AP/RT 的 `{site}_entries_{checkpoint}.json` 比照
ENEX/ABC，**不管有沒有 gate lock 一律技術性擋下逐筆 Edit/MultiEdit**——0923-0430
輪實測到 agent 在完全沒觸發 gate lock 的情況下，自發對 `ns_entries_0430.json`
連打 10 次 Edit（AP/RT 各 1 次），turns 124→224、cache read 37.7M→105.9M、
成本 $10.52→$26.32，新增則數卻完全一樣。沒有 lock 時的修補管道改走
`s2_batch_prep.py rewrite-entry` 的**自由模式**（見該檔 `cmd_rewrite_entry`）。
訊息優先序：有 lock → 維持原本 lock 解鎖訊息（更精確）；沒 lock → 才顯示
自由模式訊息，兩者不會同時出現。

2026-09-23（A41 第三種攔截）：`*_batch_*.json` 草稿（`build` 產的 add-batch
輸入）**只鎖 category／tc 兩個欄位**的逐筆 Edit/MultiEdit，其餘欄位（entry、
footage_type、status…）維持自由可改——batch 本來就是 draft，無條件全鎖會把
沒有替代指令的正常修正也卡死，夜間無人值守整輪掛掉的風險更大。
0923-1100 輪實測：`ns_batch_1100.json` 被連打 12 次 Edit（11 次擠在 40 秒內）、
`ap_batch_1100_full.json`／`rt_batch_1100.json` 各 1 次，14 次全部只在改一個
`"category"` 值——同一輪的 entries.json 逐筆 Edit 倒是被上面兩道鎖正確擋下
（AP 2 次、ABC 1 次，agent 都改走 `rewrite-entry`）。
判準是「category／tc 的**值真的有變**」而不是「字串出現 category」：整顆 item
物件重寫但這兩個值照抄，一樣放行。替代路徑見 `_batch_edit_reason` 的訊息。

2026-09-23（A41 第四種攔截＝通用兜底）：上面三條都是「等實測抓到破口才補一條」的
whack-a-mole，毛病每換一個檔名／欄位就要再補一次。這條改用**次數**當判準，不看檔名
也不看欄位：**同一輪掃帶（同一個 `claude -p` session）內，同一份 `.json` 檔累計收到
第 3 次（含）以後的 Edit／MultiEdit 一律擋下**。門檻預設 3，可用環境變數
`S2_GATE_EDIT_THRESHOLD` 調整（給使用者調，不寫進 deny 訊息裡，免得變成教 agent
繞過的說明書）。
  - 跨呼叫計數：這支 hook 每次工具呼叫都是全新的 python 行程，沒有記憶體可累計，
    所以把計數落在暫存檔 `<temp>/s2_gate_guard_tally/<session_id>.json`，內容是
    `{"檔案絕對路徑（_norm 過）": 次數}`。檔名綁 PreToolUse stdin 的 `session_id`
    （官方 hook 協定的共同欄位），保證①不同 S2 session／別的 `claude` 視窗互不汙染、
    ②每輪掃帶是新的 `claude -p` 行程＝新 session id＝計數自然歸零，不會跨輪疊加。
    `session_id` 缺席（舊版 CLI、單元測試直呼函式）→ 這條規則整條跳過，不計數也不擋。
  - 計數檔清理：每個 session 第一次建檔時順手掃一次同目錄，刪掉 mtime 超過 24 小時的
    舊計數檔（一輪掃帶約 1 小時，24 小時綽綽有餘）。放在系統暫存夾還有 OS 自身的
    清理機制當第二道保險，不需要另外排程。
  - 優先度**最低**：前四條（gate lock／ENEX-ABC／NS-AP-RT／batch 欄位）任一命中就
    直接回它們的精準訊息，**不計數**——那幾條一發就擋，用不到「累計到第 3 次」，
    而且計數只對「前面都放行」的 Edit 才有意義（要擋的是真的打出去的逐筆修補）。
  - 訊息誠實承認侷限：這條不知道是哪個檔案／哪個欄位，給不出精準指令，只能說
    「有專屬批次指令就改用它，沒有就用一次 Write 整份重寫」。
  - 被擋的那一次**也算進次數**：PreToolUse 本來就看不到 Edit 最後成功與否
    （字串沒對到也會失敗），所以計數只能是「嘗試次數」，誠實寫成「第 N 次嘗試」。
    這同時解掉「擋下就重置 → 門檻永遠打不到」的死結。

輸入輸出協議跟 `s2_bash_guard.py` 一致：stdin 一包 Claude Code hook JSON
（`tool_name`／`tool_input`／PostToolUse 另有 `tool_response`）；deny 時印
`permissionDecision=deny` 的 JSON（`ensure_ascii=True`）；放行／非目標事件
什麼都不印。任何解析失敗一律放行（exit 0）——hook 壞掉不准把整輪掃帶弄死，
沿用 `s2_bash_guard.py` 的 fail-open 原則。
"""
import glob
import hashlib
import json
import os
import re
import sys
import tempfile
import time

_UNLOCK_HINT = (
    '\n⚠️ 這不是文字建議，是工具層技術鎖定——這個檔案在 gate lock 清除前，'
    'Edit 一律被拒絕。若 lock 合計少於 5 項，可用 `rewrite-entry` 精準修補 lock '
    '列出的 ID，修後 lint 歸零會自動解鎖：\n'
    '  python E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py rewrite-entry '
    '--site <站> --entries <entries.json路徑> --id <ID> --set <ID>=<新內容>\n'
    '達 5 項以上請改用 `Write` 整批重寫該站 entries.json（重寫後 lock '
    '會自動清除）；真的需要人工介入才卡住時，用：\n'
    '  python E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py gate-clear '
    '--site <站> --entries <entries.json路徑>\n'
    '手動解鎖，不要換個包法（MultiEdit、先 Read 再 Write 單一小段…）繞過去。'
)

_PLATFORM_ENTRIES_NAME_RE = re.compile(
    r'(?:^|[_-])(enex|abc)[_-]entries(?:[_-][^.]+)?\.json$', re.IGNORECASE)
_PLATFORM_CANDIDATE_JSON_RE = re.compile(
    r'^\d{4}-(enex|abc)-state\.json$', re.IGNORECASE)
_PLATFORM_CANDIDATE_TXT_RE = re.compile(
    r'^\d{4}-(enex|abc)\.txt$', re.IGNORECASE)


def _platform_artifact_kind(file_path):
    """辨識 ENEX/ABC 不得直接 Edit 的 entries 或候選衝生檔。

    檔名是正式流程的主判準；JSON 已存在時再用內容形狀接住臨時改名。
    任何讀檔失敗一律 fail-open，不准 hook 本身弄死掃帶輪。
    """
    if not file_path:
        return None
    base = os.path.basename(str(file_path))
    match = _PLATFORM_ENTRIES_NAME_RE.search(base)
    if match:
        return f'{match.group(1).upper()} entries'
    match = _PLATFORM_CANDIDATE_JSON_RE.match(base)
    if match:
        return f'{match.group(1).upper()} 候選 JSON'
    match = _PLATFORM_CANDIDATE_TXT_RE.match(base)
    if match:
        return f'{match.group(1).upper()} 候選 TXT'

    if not str(file_path).lower().endswith('.json'):
        return None
    try:
        with open(file_path, encoding='utf-8-sig') as f:
            data = json.load(f)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    source = str(data.get('source') or '').upper()
    if source in ('ENEX', 'ABC') and isinstance(data.get('items'), list):
        return f'{source} 候選 JSON'
    values = [v for k, v in data.items() if not str(k).startswith('_')]
    if values and all(isinstance(v, dict) for v in values) and any(
            'raw_entry' in v for v in values):
        upper_name = base.upper()
        if 'ENEX' in upper_name:
            return 'ENEX entries'
        if 'ABC' in upper_name or any(str(k).upper().startswith('ABC') for k in data):
            return 'ABC entries'
    return None


def _platform_edit_reason(file_path):
    kind = _platform_artifact_kind(file_path)
    if not kind:
        return None
    return (
        f'⛔ 【ENEX/ABC 批次修補鎖定】{kind} 是整批產物，禁止用 Edit 逐筆修補：'
        f'{file_path}。請修正 from-raw 產生的骨架，並整批重建 entries：\n'
        '  python E:/GitHub/TVBS-AIHunter/scripts/s2_platform_bridge.py rewrite-entry '
        '--site <enex|abc> --skeleton <skeleton.json> --entries <entries.json> '
        '--id <ID> --set <ID>={"entry":"...","category":"...","tc":"...","skip":""}\n'
        '多筆可重複帶 --id/--set；指令會保留完整骨架並整批重建 entries。'
        '若此檔是候選 JSON/TXT，重建 entries 後再用原參數重跑 '
        's2_platform_extract.py；候選檔不是人工修補來源。'
    )


_SITE_ENTRIES_NAME_RE = re.compile(
    r'(?:^|[_-])(ns|ap|rt)[_-](?:[A-Za-z0-9]+[_-])*entries\d*(?:[_.-][^/\\]*)?\.json$',
    re.IGNORECASE)


def _site_artifact_kind(file_path):
    """辨識 NS/AP/RT 不得直接 Edit 的 entries.json 草稿。

    檔名是主判準：production 實際出現過的形狀全部要接住（`ns_entries_0430.json`、
    `ns_entries_0430.renamed.json`、`rt_entries2_0700.json`、`ap_cctv_entries_1700.json`、
    `rt_backfill_entries_2359.json`、`ns_entries_1100_v2.json`、`rt_entries_2000b.json`
    ——全部取自 `_guard_calls.log` 的真實紀錄，不是臆測的命名規則）。
    ⛔ 不可誤擋：裸 `entries.json`（沒有站別前綴，既有測試 fixture 依賴放行）、
    `ns_batch_0430.json`、`ns_skeleton_0430.json`、`ns_gate_lock.json`，以及
    ENEX/ABC 的 `abc_entries_0430.json`（那條線由 `_platform_artifact_kind` 負責，
    兩邊判斷互不重疊）。

    檔名沒中時再用內容形狀接住臨時改名：NS/AP/RT 草稿頂層保留鍵 `_new_topics`
    （13c2 §「要開新中主題就在 entries.json 頂層放 `_new_topics`」）是這三站
    entries 草稿獨有的標記——`batch.json` 用的是不帶底線的 `new_topics`，不會撞。
    任何讀檔失敗一律 fail-open，不准 hook 本身弄死掃帶輪。
    """
    if not file_path:
        return None
    base = os.path.basename(str(file_path))
    match = _SITE_ENTRIES_NAME_RE.search(base)
    if match:
        return f'{match.group(1).upper()} entries'

    if not str(file_path).lower().endswith('.json'):
        return None
    try:
        with open(file_path, encoding='utf-8-sig') as f:
            data = json.load(f)
    except (OSError, ValueError, TypeError):
        return None
    if isinstance(data, dict) and '_new_topics' in data:
        return 'NS/AP/RT entries'
    return None


def _site_edit_reason(file_path):
    kind = _site_artifact_kind(file_path)
    if not kind:
        return None
    return (
        f'⛔ 【NS/AP/RT 批次修補鎖定】{kind} 是整批產物，禁止用 Edit／MultiEdit '
        f'逐筆修補：{file_path}。\n'
        'ℹ️ 目前**沒有** gate lock，`rewrite-entry` 走自由模式（可自行指定要改的 ID，'
        '不受 lock reason items 限制）：\n'
        '  python E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py rewrite-entry '
        '--site <ns|ap|rt> --entries <entries.json路徑> '
        '--id <ID> --set <ID>={"entry":"...","category":"...","tc":"..."}\n'
        '多筆可重複帶 --id/--set；只准改 entry／category／tc（其餘欄位一律拒絕），'
        '落檔前會重跑 build 那套共用 lint，修出新的白名單格式錯誤達門檻就整個拒絕、不寫檔。\n'
        'ℹ️ 自由模式**也能新增則、也能補 `_new_topics`**，不必為了這兩件事去重寫整份檔案：\n'
        '  • 新增一則：`--id <新ID> --new-id <新ID> --set <新ID>={"entry":"...",'
        '"category":"..."}`（--new-id 是明示新增的旗標；沒帶它而 ID 不存在＝當打錯字拒絕）。\n'
        '  • 開新中主題：`--new-topics \'{"題名":{"charter":"這題收什麼、不收什麼",'
        '"big":"大分類"}}\'`（可單獨使用，不必給 --id；逐題逐欄合併）。\n'
        '  兩者可以跟一般修補混在**同一次**呼叫裡。\n'
        '要整份大改就用一次 `Write` 整批重寫，不要換個包法'
        '（MultiEdit、先 Read 再 Write 單一小段…）繞過去。'
    )


_BATCH_DRAFT_NAME_RE = re.compile(
    r'(?:^|[_-])(ns|ap|rt|enex|abc)[_-](?:[A-Za-z0-9]+[_-])*batch\d*(?:[_.-][^/\\]*)?\.json$',
    re.IGNORECASE)

# JSON 裡 `"category": <值>` / `"tc": <值>` 的鍵＋值。值依序試：物件（R25 的
# `{"大分類":…}` 形狀）→ 帶跳脫的字串 → 兜底吃到逗號／換行／右大括號為止
# （Edit 片段常常是被截斷的半截值，兜底這條保證「鍵有出現就一定抓得到值」，
# 兩側才比得出差異）。
_BATCH_FIELD_RE = re.compile(
    r'"(category|tc)"\s*:\s*(\{[^{}]*\}|"(?:[^"\\]|\\.)*"|[^,\n}]*)',
    re.IGNORECASE)
_BATCH_FIELD_KEY_RE = re.compile(r'"(category|tc)"\s*:', re.IGNORECASE)


def _batch_artifact_kind(file_path):
    """辨識 NS/AP/RT/ENEX/ABC 的 batch.json 草稿（`build` 產的 add-batch 輸入）。

    檔名是**唯一**判準——刻意不做上面兩支那種「內容形狀 fallback」，因為
    `from-raw` 產的骨架（`*_skeleton_*.json`）每筆也是
    `{id, source, checkpoint, status, src_text, entry, category, tc, hint}`，
    跟 batch 草稿同形狀，加形狀判斷只會把 skeleton 誤認成 batch、回錯訊息。
    production 的 batch 檔名一律照命名慣例走（下列全取自真實紀錄）：
    production 實際出現過的形狀全部要接住（`ns_batch_1100.json`、
    `ap_batch_1100_full.json`、`ap_batch_1100_extra.json`、`ap_batch_1100b.json`、
    `ns_batch_2000b.json`、`rt_backfill_batch_2359.json`、`ap_batch_0100_sntv.json`、
    `_rt_batch_1000.json`——取自 `_guard_calls.log` 與 `s2_batch_prep.py` docstring
    的真實紀錄，不是臆測的命名規則）。
    ⛔ 不可誤擋：`ns_entries_0430.json`（`_site_artifact_kind` 的線）、
    `ns_skeleton_0430.json`、`ns_gate_lock.json`、`0922-s2-state.json`，以及
    非這五站的 `yc_batch_2200.json`／`yna_cna_batch_2000.json`（YouTube／YNA-CNA
    另有各自流程，不在這次範圍）。
    註：ENEX/ABC 目前實際上不產 `*_batch_*.json`（那兩站走 skeleton→entries→
    add-batch），寫進 regex 只是為了將來改流程時不會漏接。
    """
    if not file_path:
        return None
    base = os.path.basename(str(file_path))
    match = _BATCH_DRAFT_NAME_RE.search(base)
    if match:
        return f'{match.group(1).upper()} batch 草稿'
    return None


def _batch_fields_of(text):
    """把一段 Edit 片段裡所有 `category`／`tc` 的鍵值抽成 [(鍵, 值)] 清單。

    鍵一律轉小寫、值去頭尾空白，讓「只是排版空白不同」不算改動。
    """
    if not isinstance(text, str) or not text:
        return []
    return [(m.group(1).lower(), m.group(2).strip())
            for m in _BATCH_FIELD_RE.finditer(text)]


def _batch_edit_touches_fields(old_string, new_string):
    """這一組 (old_string, new_string) 有沒有真的動到 category／tc 的值。

    判準刻意設計成「**值有變**才算」，不是「字串裡出現 category 就擋」：
      - 只改 entry／footage_type／status → 片段裡根本沒有 `"category":` 鍵樣式
        → 兩側清單都空 → 放行。
      - 整顆 item 物件重寫、但 category／tc 原值照抄 → 兩側清單相同 → 放行
        （真正被改的是別的欄位，符合「batch 是 draft、其他欄位保持彈性」）。
      - 改 category／tc 的值、或新增／刪掉這兩個鍵 → 兩側清單不同 → 擋。
    誤判風險：entry 內文如果剛好逐字包含 `"category":`（要同時有雙引號＋冒號）
    才可能誤命中，中文新聞素材行出現這種字串的機率極低；且即使命中，也還要
    「兩側的值不同」才會擋，比單純找關鍵字保守得多。
    """
    if not (isinstance(old_string, str) or isinstance(new_string, str)):
        return False
    old_text = old_string if isinstance(old_string, str) else ''
    new_text = new_string if isinstance(new_string, str) else ''
    if not (_BATCH_FIELD_KEY_RE.search(old_text)
            or _BATCH_FIELD_KEY_RE.search(new_text)):
        return False
    return _batch_fields_of(old_text) != _batch_fields_of(new_text)


def _batch_tool_input_touches_fields(tool_input):
    """Edit（old_string/new_string）與 MultiEdit（edits 陣列）共用的入口。

    MultiEdit **只要有任何一筆**動到 category／tc 就整組擋，理由有二：
      1. MultiEdit 在工具層是 all-or-nothing，放行等於讓那筆 category 改動過關；
      2. 否則只要在 category 改動旁邊塞一筆無關的 entry 改動就能繞過這道鎖。
    被擋時把不該擋的那幾筆拆出來單獨送即可，沒有「唯一路徑被封死」的風險。
    """
    if not isinstance(tool_input, dict):
        return False
    edits = tool_input.get('edits')
    if isinstance(edits, list):
        for edit in edits:
            if not isinstance(edit, dict):
                continue
            if _batch_edit_touches_fields(edit.get('old_string'),
                                          edit.get('new_string')):
                return True
        return False
    return _batch_edit_touches_fields(tool_input.get('old_string'),
                                      tool_input.get('new_string'))


def _batch_edit_reason(file_path, tool_input):
    kind = _batch_artifact_kind(file_path)
    if not kind:
        return None
    if not _batch_tool_input_touches_fields(tool_input):
        return None
    return (
        f'⛔ 【batch 草稿 category／tc 欄位鎖定】{kind} 的 category／tc 是整批欄位，'
        f'禁止用 Edit／MultiEdit 逐筆改值：{file_path}。\n'
        '（0923-1100 輪實測：ns_batch_1100.json 被連打 12 次 Edit、每次只改一個 '
        'category 值，其中 11 次擠在 40 秒內；ap_batch_1100_full.json／'
        'rt_batch_1100.json 各 1 次。同一件事一條批次指令就做得完。）\n'
        'ℹ️ 這道鎖**只鎖 category／tc**；batch 草稿的其他欄位（entry、footage_type、'
        'status…）照舊可以自由 Edit，不受影響。\n'
        '✅ 改走批次路徑，擇一：\n'
        '  1) 這份 batch 還沒 add-batch 進狀態檔 → 修上游 entries.json 草稿後重跑 build：\n'
        '     python E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py rewrite-entry '
        '--site <ns|ap|rt> --entries <entries.json路徑> '
        '--id <ID> --set <ID>={"category":"大分類/中主題/小分題","tc":"T1,T2/C1,C2"}\n'
        '     （多筆重複帶 --id/--set），再用原參數重跑 `build --out <batch.json>` 整批重建。\n'
        '  2) 已經 add-batch 進狀態檔 → 直接在狀態檔上整批改（分隔符優先認分號）：\n'
        '     python E:/GitHub/TVBS-AIHunter/scripts/s2_state.py --file <state.json路徑> '
        'set-category --pairs "ID1=大分類/中主題;ID2=大分類/中主題/小分題;…"\n'
        '     python E:/GitHub/TVBS-AIHunter/scripts/s2_state.py --file <state.json路徑> '
        'set-tc --pairs "ID1=T1,T2/C1,C2;ID2=/臺灣;…"\n'
        '     ⚠️ set-tc 每 checkpoint 有呼叫次數上限，務必整批一次下。batch 裡已標好的 '
        'category 可先用 `s2_batch_prep.py collate-category <batch.json…>` '
        '收成現成的 --pairs 字串。\n'
        '  3) 真的要整份大改 → 用一次 `Write` 重寫整個 batch.json，'
        '不要換個包法（MultiEdit、先 Read 再 Write 單一小段…）繞過去。'
    )


def _norm(path):
    """正規化成絕對路徑＋正斜線＋大小寫不敏感比較，跟 s2_bash_guard.py
    既有慣例一致（Windows 路徑分隔字元與大小寫都不可靠）。"""
    return os.path.normcase(os.path.abspath(path)).replace('\\', '/')


def _find_lock_for_path(file_path):
    """在 file_path 所在目錄找 `*_gate_lock.json`，比對其中記的 entries_path
    是否正規化後等於 file_path。回傳 (lock_json_path, lock_dict) 或 None。"""
    if not file_path:
        return None
    d = os.path.dirname(os.path.abspath(file_path))
    if not os.path.isdir(d):
        return None
    target = _norm(file_path)
    for lock_path in glob.glob(os.path.join(d, '*_gate_lock.json')):
        try:
            with open(lock_path, encoding='utf-8') as f:
                lock = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(lock, dict):
            continue
        entries_path = lock.get('entries_path')
        if entries_path and _norm(entries_path) == target:
            return lock_path, lock
    return None


# ── 通用兜底：同一 session 同一份 JSON 的 Edit／MultiEdit 次數上限 ──────────
# 門檻＝「第幾次（含）開始擋」。3 ＝前兩次放行，第 3 次起擋。
_EDIT_TALLY_DEFAULT_THRESHOLD = 3
# 計數檔保留時間；超過就在下一個 session 建檔時順手清掉。一輪掃帶約 1 小時。
_EDIT_TALLY_TTL_SECONDS = 24 * 60 * 60
_EDIT_TALLY_DIR_NAME = 's2_gate_guard_tally'
_TALLY_NAME_UNSAFE_RE = re.compile(r'[^A-Za-z0-9_-]')


def _edit_tally_threshold():
    """門檻可用環境變數調整（`S2_GATE_EDIT_THRESHOLD`）。

    刻意**不**寫進 deny 訊息：那是給使用者調參數用的，寫進訊息等於教 agent
    怎麼繞過這道鎖。任何解析失敗一律退回預設值 3。
    """
    raw = os.environ.get('S2_GATE_EDIT_THRESHOLD')
    if raw is None:
        return _EDIT_TALLY_DEFAULT_THRESHOLD
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return _EDIT_TALLY_DEFAULT_THRESHOLD
    return value if value >= 1 else _EDIT_TALLY_DEFAULT_THRESHOLD


def _edit_tally_dir():
    """計數檔放系統暫存夾（`S2_GATE_TALLY_DIR` 可覆寫，單元測試用）。

    刻意不放在目標檔案同目錄：掃帶的目標檔在 G:\\ 雲端同步夾，丟計數檔進去會
    被同步上雲、也會混進當輪產物清單裡。
    """
    return (os.environ.get('S2_GATE_TALLY_DIR')
            or os.path.join(tempfile.gettempdir(), _EDIT_TALLY_DIR_NAME))


def _edit_tally_file(dir_, session_id):
    """session id → 計數檔路徑。

    先把非 `[A-Za-z0-9_-]` 的字元換成底線（session id 理論上是 UUID，但不能假設），
    再接一段原始值的 sha1 短碼——避免「清洗後撞名」把兩個 session 併成同一份計數。
    """
    raw = str(session_id)
    safe = _TALLY_NAME_UNSAFE_RE.sub('_', raw)[:64]
    digest = hashlib.sha1(raw.encode('utf-8', 'replace')).hexdigest()[:10]
    return os.path.join(dir_, '%s-%s.json' % (safe, digest))


def _sweep_stale_tallies(dir_, keep_path):
    """刪掉同目錄裡過期的舊計數檔；只在某個 session 第一次建檔時呼叫一次。

    單檔失敗（權限、別的行程正在寫）不准影響判定，逐檔 try/except 吞掉。
    """
    now = time.time()
    keep = _norm(keep_path)
    try:
        names = os.listdir(dir_)
    except OSError:
        return
    for name in names:
        path = os.path.join(dir_, name)
        if _norm(path) == keep:
            continue
        try:
            if now - os.path.getmtime(path) > _EDIT_TALLY_TTL_SECONDS:
                os.remove(path)
        except OSError:
            pass


def _bump_edit_tally(session_id, file_path):
    """把 (session, 檔案) 的計數 +1 並回傳新值。

    寫檔走「寫 `.tmp` → `os.replace()` 原子換名」：Claude Code 可能同時送出多個
    工具呼叫，兩個 hook 行程並行讀改寫同一份計數檔時，直接覆寫有機率留下半截
    JSON，下次讀取解析失敗就被當成「沒有計數」靜默歸零。原子換名讓讀到的永遠
    是某一次完整的內容。
    ⚠️ 已知殘留風險：並行下兩邊各自讀到 1、各自寫回 2 → 少算一次。方向是
    「少擋」而不是「誤擋」，符合整支 hook 的 fail-open 原則，不為此加檔案鎖
    （鎖失敗或卡住的代價遠大於偶爾少算一次）。
    """
    dir_ = _edit_tally_dir()
    path = _edit_tally_file(dir_, session_id)
    os.makedirs(dir_, exist_ok=True)
    first_time = not os.path.exists(path)

    data = {}
    if not first_time:
        try:
            with open(path, encoding='utf-8') as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, ValueError):
            data = {}  # 計數檔壞掉＝重新從 0 算起，寧可少擋不可誤擋

    key = _norm(file_path)
    prev = data.get(key)
    count = (prev if isinstance(prev, int) and prev > 0 else 0) + 1
    data[key] = count

    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=True)
    os.replace(tmp, path)

    if first_time:
        _sweep_stale_tallies(dir_, path)
    return count


def _generic_edit_reason(file_path, session_id):
    """第五條（優先度最低）：同一 session 同一份 JSON 的逐筆 Edit 次數上限。

    只在前四條全部放行後才會被呼叫，所以：
      - 已經被 gate lock／ENEX-ABC／NS-AP-RT／batch 欄位鎖擋下的 Edit **不計數**，
        訊息也不會被這條搶走（那四條的訊息更精準）。
      - 只管 `.json`：其餘副檔名（.md／.py／.txt…）完全不碰，逐筆改文件是正常行為。
      - `session_id` 缺席一律跳過——沒有 session 就沒有「同一輪」的定義，
        用全域計數檔會跨輪疊加，比不擋更糟。
    整段包 try/except：計數機制自己壞掉不准弄死掃帶輪，也不准誤擋。
    """
    if not session_id or not file_path:
        return None
    if not str(file_path).lower().endswith('.json'):
        return None
    threshold = _edit_tally_threshold()
    try:
        count = _bump_edit_tally(session_id, file_path)
    except Exception:
        return None
    if not isinstance(count, int) or count < threshold:
        return None
    return (
        f'⛔ 【同檔逐筆 Edit 次數上限】這一輪（同一個 claude session）已經對同一份檔案'
        f'發出第 {count} 次 Edit／MultiEdit 嘗試，達到上限 {threshold} 次，'
        f'第 {threshold} 次（含）以後一律擋下：{file_path}\n'
        '（算的是「嘗試次數」——PreToolUse 看不到 Edit 最後成功與否，被擋的這次也算進去。）\n'
        'ℹ️ 誠實說明：這是**通用兜底規則**，不分檔名也不分欄位，'
        '所以它**不知道**這份檔案對應哪一支批次指令，沒辦法像其他幾道鎖那樣直接把指令給你。'
        '請自己判斷，擇一：\n'
        '  1) 這份檔案**有**專屬的批次指令（s2_batch_prep.py／s2_state.py／'
        's2_platform_bridge.py 的子指令等）→ 改用那支指令，一次把剩下的修改做完。\n'
        '  2) **沒有**對應的批次指令 → 用一次 `Write` 整份重寫這個檔案，'
        '把剩下的修改全部一起寫進去。\n'
        '⚠️ 不要換個包法（改用 MultiEdit、拆更小段、先 Read 再 Edit…）繼續逐筆改：'
        '逐筆 Edit 每一筆都要多開一輪 assistant turn，cache read token 跟著整輪翻倍，'
        '這正是這道鎖要擋的成本破口。'
    )


def decide_edit(file_path, tool_input=None, session_id=None):
    """PreToolUse／Edit 專用：回傳 None＝放行；否則回傳 deny 理由字串。

    判斷順序刻意固定為「gate lock → ENEX/ABC → NS/AP/RT → batch 草稿欄位
    → 通用次數上限」：
      1. 有 active gate lock 時一律優先回 lock 訊息（帶站別／reason code／
         `gate-clear` 逃生路徑，比泛用訊息精確），行為跟 2026-09-18 上線版完全相同。
      2. ENEX/ABC 既有判斷擺第二，結果不受後面新增分支影響。
      3. 沒有 lock 的 NS/AP/RT entries 走自由模式訊息。
      4. batch 草稿的 category／tc 欄位鎖擺**最後、優先度最低**（2026-09-23）：
         它是唯一「要看 Edit 內容才決定」的條件式分支，前三條都是純檔名／lock
         的無條件鎖。擺最後可以保證就算哪天命名規則撞在一起，前三條的行為
         一個字都不會變。實際上四條的檔名集合互斥（batch vs entries vs 候選檔），
         順序不具語意負擔。
      5. 通用次數上限（2026-09-23 新增）擺**最後、優先度最低**：它是唯一不看
         檔名也不看欄位的兜底規則，只有前四條全部放行才輪到它算數——也就是說
         被前四條擋下的 Edit 完全不進計數，訊息也不會被它搶走。
    ⚠️ `tool_input` 可略（預設 None）：舊呼叫端（只給 file_path）行為完全不變，
    沒有內容可判讀時第 4 條一律放行，沿用整支 hook 的 fail-open 原則。
    ⚠️ `session_id` 可略（預設 None）：不給就等於關掉第 5 條（不計數、不擋），
    所有既有呼叫端與既有測試的行為一個字都不會變。
    """
    found = _find_lock_for_path(file_path)
    if found:
        lock_path, lock = found
        site = lock.get('site', '?')
        reasons = lock.get('reasons') or []
        reason_str = '、'.join(
            f'{r.get("code")}（{r.get("count")}則）' for r in reasons
        ) or '（reason 記錄缺失）'
        return (
            f'⛔ 【Edit 技術鎖定】{site} 站的 gate lock 仍 active（{lock_path}），'
            f'觸發原因：{reason_str}。' + _UNLOCK_HINT
        )
    platform_reason = _platform_edit_reason(file_path)
    if platform_reason:
        return platform_reason
    site_reason = _site_edit_reason(file_path)
    if site_reason:
        return site_reason
    batch_reason = _batch_edit_reason(file_path, tool_input)
    if batch_reason:
        return batch_reason
    return _generic_edit_reason(file_path, session_id)


def _write_looked_successful(tool_response):
    """PostToolUse 的 tool_response 判斷是否為成功寫入——跟
    `.claude/helpers/hook-handler.cjs` 既有慣例（is_error/isError/success/
    error/exit_code 任一透露失敗就不算成功）一致，寧可漏清（fail-safe：
    保留 lock，Edit 繼續被擋）也不要誤清一次失敗的 Write。"""
    if not isinstance(tool_response, dict):
        return True  # 沒有可判讀的錯誤欄位，預設當成功（跟既有 PreToolUse fail-open 對稱）
    if tool_response.get('is_error') is True or tool_response.get('isError') is True:
        return False
    if tool_response.get('success') is False:
        return False
    if tool_response.get('error') is not None:
        return False
    code = tool_response.get('exit_code', tool_response.get('exitCode'))
    if isinstance(code, (int, float)) and code != 0:
        return False
    return True


def clear_lock_after_write(file_path):
    """PostToolUse／Write：對應 lock 存在就刪除（清除時機①）。"""
    found = _find_lock_for_path(file_path)
    if not found:
        return
    lock_path, _lock = found
    try:
        os.remove(lock_path)
    except OSError:
        pass


def main():
    try:
        raw = sys.stdin.buffer.read()
        payload = json.loads(raw.decode('utf-8', 'replace'))
        tool_name = payload.get('tool_name', '')
        tool_input = payload.get('tool_input') or {}
        file_path = tool_input.get('file_path', '')
        # 官方 hook 協定的共同欄位（PreToolUse/PostToolUse 都有）；舊版 CLI 沒有
        # 這個欄位時值是 None，第 5 條規則會整條跳過。
        session_id = payload.get('session_id')
    except Exception:
        return 0

    if tool_name == 'Write':
        # 這支 hook 只在 PostToolUse 被註冊給 Write（見 s2_guard_settings.json），
        # 不需要另外判斷 hook_event_name——由 matcher 保證只有這個事件會進來。
        if _write_looked_successful(payload.get('tool_response')):
            clear_lock_after_write(file_path)
        return 0

    if tool_name not in ('Edit', 'MultiEdit'):
        return 0

    reason = decide_edit(file_path, tool_input, session_id)
    if reason:
        print(json.dumps({
            'hookSpecificOutput': {
                'hookEventName': 'PreToolUse',
                'permissionDecision': 'deny',
                'permissionDecisionReason': reason,
            }
        }, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
