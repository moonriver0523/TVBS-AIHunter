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

少於通用門檻時，改走 `s2_batch_prep.py rewrite-entry`；該指令只接受 lock
reason items 列出的 ID，並在寫入後用 build 共用 lint 歸零才清鎖。

輸入輸出協議跟 `s2_bash_guard.py` 一致：stdin 一包 Claude Code hook JSON
（`tool_name`／`tool_input`／PostToolUse 另有 `tool_response`）；deny 時印
`permissionDecision=deny` 的 JSON（`ensure_ascii=True`）；放行／非目標事件
什麼都不印。任何解析失敗一律放行（exit 0）——hook 壞掉不准把整輪掃帶弄死，
沿用 `s2_bash_guard.py` 的 fail-open 原則。
"""
import glob
import json
import os
import re
import sys

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
        entries_path = lock.get('entries_path')
        if entries_path and _norm(entries_path) == target:
            return lock_path, lock
    return None


def decide_edit(file_path):
    """PreToolUse／Edit 專用：回傳 None＝放行；否則回傳 deny 理由字串。"""
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
    return _platform_edit_reason(file_path)


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

    reason = decide_edit(file_path)
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
